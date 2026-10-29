from fastapi import HTTPException,status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

import hashlib

from datetime import datetime, timezone

from app.auth.models import (User,
                             Tenant,
                             RefreshToken)

from app.core.schemas import  MessageResponse
from app.auth.schemas import (RegisterRequest,
                              RegisterResponse,
                              VerifyEmailRequest,
                              ResendVerificationOTPRequest,
                              LoginRequest,
                              LoginResponse,
                              RefreshTokenRequest,
                              RefreshTokenResponse,
                              LogoutRequest,
                              ForgotPasswordRequest,
                              VerifyResetOTPRequest,
                              ResendResetOTPRequest,
                              ResetPasswordRequest,
                              ChangePasswordRequest,
                              UserResponse,
                              TokenResponse,)

from app.auth.utils import (normalize_email,
                            normalize_username,
                            validate_password_strength,
                            generate_otp,
                            generate_user_id,
                            generate_tenant_id,
                            get_next_user_sequence,)

from app.core.security import (hash_password,
                               verify_password,
                               create_access_token,
                               create_refresh_token,
                               verify_token,
                               REFRESH_TOKEN_TYPE,
                               ACCESS_TOKEN_TYPE,)

from app.infra.redis.otp import (set_email_verification_otp,
                                 get_email_verification_otp,
                                 delete_email_verification_otp,
                                 set_password_reset_otp,
                                 get_password_reset_otp,
                                 delete_password_reset_otp,)

from app.infra.redis.blacklist import (blacklist_token,
                                       is_token_blacklisted,
                                       remove_blacklisted_token)

from app.infra.redis.rate_limit import (is_email_verify_resend_on_cooldown,
                                        get_email_verify_resend_ttl,
                                        set_email_verify_resend_cooldown,
                                        increment_login_attempts,
                                        get_login_attempts,
                                        reset_login_attempts,
                                        get_login_attempts_ttl,
                                        is_password_reset_resend_on_cooldown,
                                        get_password_reset_resend_ttl,
                                        set_password_reset_resend_cooldown,)

from app.infra.celery.email_tasks import (send_verification_email,
                                          send_welcome_email,
                                          send_account_locked_email,
                                          send_password_changed_email,
                                          send_password_reset_email)





async def register_user(db: Session, request:RegisterRequest,)-> RegisterResponse:

    email = normalize_email(request.email)
    username = normalize_username(request.username)

    try: validate_password_strength(request.password)
    except ValueError as exc: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                            detail=str(exc),)
    
    existing_user = (db.query(User).filter(or_(
        User.email == email,
        User.username == username,
    )).first()
    )

    if existing_user:
        if existing_user.email == email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Email already registered.")
    
        if existing_user.username == username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists.",)
        
    sequence = get_next_user_sequence(db)
    user_id = generate_user_id(sequence)

    hashed_password = hash_password(request.password)

    tenant = Tenant(
                tenant_id = generate_tenant_id(sequence),
                name = username,)

    user = User( 
                user_id = user_id,
                tenant_id = tenant.tenant_id,
                email = email,
                username = username,
                password_hash = hashed_password,)
    
    try: 
        db.add(tenant)
        db.flush()
        db.add(user)
        db.commit()
    
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user.",
        )

    otp = generate_otp()

    set_email_verification_otp(email=user.email,otp=otp,)
    try: 
        send_verification_email.delay(email = user.email,
                                      username = user.username,
                                      otp=otp,)
    except Exception:
        pass

    return RegisterResponse(message="Registration successful. Please verify your email.",
                            user_id=user.user_id,
                            email=user.email,)


async def verify_email(db:Session, request: VerifyEmailRequest,)-> MessageResponse:
    
    email = normalize_email(request.email)

    user = (db.query(User).filter(User.email == email).first())
    if user is None: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="User not found.",)
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified.",
        )
    
    otp = get_email_verification_otp(email)

    if otp is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="OTP expired or not found.",)
    
    if otp != request.otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail= "Invalid OTP.",)
    
    user.is_verified = True

    try: db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail= " Failed to verify email.",)
    
    try: delete_email_verification_otp(email)

    except Exception: pass

    try: 
        send_welcome_email.delay(email=user.email,
                                 username = user.username,)
    except Exception: pass
    
    return MessageResponse(message="Email verified successfully.")


async def resend_verification_otp(db: Session,request:ResendVerificationOTPRequest, )-> MessageResponse:
    email = normalize_email(request.email)

    user = (db.query(User).filter(User.email == email).first())

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="User not found.")
    
    if user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail= "Email is already verified.",) 
    
    if is_email_verify_resend_on_cooldown(email):
        ttl = get_email_verify_resend_ttl(email)
        
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
           detail={
                "message": "Verification OTP resend is temporarily blocked.",
                "retry_after": ttl,
            },
        )
    
    otp = generate_otp()

    set_email_verification_otp(email,otp)

    set_email_verify_resend_cooldown(email)

    try:
        send_verification_email.delay(
            email = user.email,
            username = user.username,
            otp = otp,
        )
    except Exception: pass 

    return MessageResponse(message= "Verification OTP sent successfully.")


async def login_user(db: Session , request: LoginRequest )-> LoginResponse:
    email = normalize_email(request.email)

    user = (db.query(User).filter(User.email == email).first())

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid email or password.",)
    
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Email is not verified.",)
    
    if get_login_attempts(email) >= 5:
        ttl = get_login_attempts_ttl(email)
        
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
           detail={
                "message": "Login attempts are temporarily blocked due to multiple failed attempts.",
                "retry_after": ttl,
           })
    
    if not verify_password(request.password, user.password_hash) :
        attempts = increment_login_attempts(email)

        if attempts >= 5:
            try: send_account_locked_email.delay(email=user.email,
                                                username=user.username,)
            except Exception: pass

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid email or password.",)
    
    
    reset_login_attempts(email)

    access_token = create_access_token(subject=user.user_id)
    refresh_token = create_refresh_token(subject=user.user_id)

    payload = verify_token(refresh_token,
                           token_type=REFRESH_TOKEN_TYPE,)
    
    jti = payload.get("jti")

    if not jti:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid refresh token.",
        )
    
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    refresh = RefreshToken(user_id=user.user_id,
                           jti=jti,
                           token_hash=token_hash,
                           expires_at=datetime.utcfromtimestamp(payload["exp"]),)

    try:
        db.add(refresh)
        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login.",
        )
    
    return LoginResponse(message= "Login successful.",tokens =TokenResponse(access_token=access_token,
                                                                            refresh_token=refresh_token,),
                                 user = UserResponse.model_validate(user),)


async def refresh_access_token(db: Session, request: RefreshTokenRequest) -> RefreshTokenResponse:
    refresh_token = request.refresh_token
 
    payload = verify_token(refresh_token, token_type=REFRESH_TOKEN_TYPE)
 
    user_id = payload['sub']
    jti = payload['jti']
    exp = payload['exp']
 
    if is_token_blacklisted(jti):
          raise HTTPException(
                 status_code=status.HTTP_401_UNAUTHORIZED,
                 detail="Refresh token has been revoked.",
           )
    
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
 
 
    stored_token = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.token_hash == token_hash,
    ).first()
 
    if stored_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found.",
        )
    
    if stored_token.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked.",
        )
    
    if stored_token.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired.",
        )
    
    access_token = create_access_token(subject=user_id)
    new_refresh_token = create_refresh_token(subject=user_id)
 
    new_payload = verify_token(new_refresh_token, token_type=REFRESH_TOKEN_TYPE)
    new_hash = hashlib.sha256(new_refresh_token.encode()).hexdigest()
    blacklist_token(jti)
    stored_token.is_revoked = True
    new_token = RefreshToken(
        user_id=user_id,
          jti=new_payload['jti'],
          token_hash=new_hash,
          expires_at = datetime.utcfromtimestamp(new_payload["exp"]),)
    
    try: 
       db.add(new_token)
       db.commit()

    except SQLAlchemyError:
       db.rollback()
       raise HTTPException(
              status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
              detail="Failed to refresh access token.",
         )
   
    return RefreshTokenResponse(message="Access token refreshed successfully.",
                               tokens =TokenResponse(access_token=access_token,
                                                    refresh_token=new_refresh_token,),)



async def logout_user(db: Session, request: LogoutRequest) -> MessageResponse:
    refresh_token = request.refresh_token

    payload = verify_token(refresh_token, token_type=REFRESH_TOKEN_TYPE)

    jti = payload['jti']
    user_id = payload['sub']

    if is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has already been revoked.",
        )
    
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    stored_token = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.token_hash == token_hash,
    ).first()

    if stored_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found.",
        )

    if stored_token.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has already been revoked.",
        )

    blacklist_token(jti)
    stored_token.is_revoked = True

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to logout.",
        )

    return MessageResponse(message="Logout successful.")


async def forgot_password(db: Session, request: ForgotPasswordRequest) -> MessageResponse:
    email = normalize_email(request.email)

    user = db.query(User).filter(User.email == email).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    
    if user.is_verified is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified.",
        )
    
    if is_password_reset_resend_on_cooldown(email):
        ttl = get_password_reset_resend_ttl(email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "Password reset OTP resend is temporarily blocked.",
                    "retry_after": ttl,},)
    
    otp = generate_otp()

    set_password_reset_otp(email=email, otp=otp)
    set_password_reset_resend_cooldown(email)

    try: 
        send_password_reset_email.delay(email=user.email,
                                        username=user.username,
                                        otp=otp,)
    except Exception: pass

    return MessageResponse(message="Password reset OTP sent successfully.")


async def verify_reset_otp(db: Session, request: VerifyResetOTPRequest) -> MessageResponse:
    email = normalize_email(request.email)

    user = db.query(User).filter(User.email == email).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    
    if user.is_verified is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified.",
        )
    
    otp = get_password_reset_otp(email)

    if otp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not found.",
        )
    
    if otp != request.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP.",
        )
    
    return MessageResponse(message="Password reset OTP verified successfully.")


async def resend_reset_otp(db: Session, request: ResendResetOTPRequest) -> MessageResponse:
    email = normalize_email(request.email)

    user = db.query(User).filter(User.email == email).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    
    if user.is_verified is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified.",
        )
    
    if is_password_reset_resend_on_cooldown(email):
        ttl = get_password_reset_resend_ttl(email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "Password reset OTP resend is temporarily blocked.",
                    "retry_after": ttl,},)
    
    otp = generate_otp()
    set_password_reset_otp(email=email, otp=otp)
    set_password_reset_resend_cooldown(email)

    try:
        send_password_reset_email.delay(email=user.email,
                                        username=user.username,
                                        otp=otp,)
    except Exception: pass

    return MessageResponse(message="Password reset OTP sent successfully.")


async def reset_password(db: Session, request: ResetPasswordRequest) -> MessageResponse:
    email = normalize_email(request.email)

    user = db.query(User).filter(User.email == email).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    
    if user.is_verified is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified.",
        )
    
    otp = get_password_reset_otp(email)

    if otp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not found.",
        )
    
    if otp != request.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP.",
        )
    
    try: 
        validate_password_strength(request.new_password)
        if verify_password(request.new_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password cannot be the same as the old password.",
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    
    user.password_hash = hash_password(request.new_password)

    refresh_tokens = db.query(RefreshToken).filter_by(user_id=user.user_id, is_revoked=False).all()

    for token in refresh_tokens:
        token.is_revoked = True
        blacklist_token(jti=token.jti,
                        expires_at=token.expires_at,)
        
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password.",
        )
    
    try:
        delete_password_reset_otp(email)
    except Exception: pass

    try:
        send_password_changed_email.delay(email=user.email,
                                          username=user.username,)
    except Exception: pass

    return MessageResponse(message="Password reset successfully.")


async def change_password(db: Session,user: User, request: ChangePasswordRequest) -> MessageResponse:
    
    if not verify_password(request.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Old password is incorrect.",
        )
    
    try:
        validate_password_strength(request.new_password)
        if verify_password(request.new_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password cannot be the same as the old password.",
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    
    user.password_hash = hash_password(request.new_password)

    refresh_tokens = db.query(RefreshToken).filter_by(user_id=user.user_id, is_revoked=False).all()

    for token in refresh_tokens:
        token.is_revoked = True
        blacklist_token(jti=token.jti,
                        expires_at=token.expires_at,)
        
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password.",
        )
    
    try:
        send_password_changed_email.delay(email=user.email,
                                          username=user.username,)
    except Exception: pass

    return MessageResponse(message="Password changed successfully.Please login again with your new password.")