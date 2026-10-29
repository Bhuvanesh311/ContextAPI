from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db

from app.auth.schemas import (
    RegisterRequest,
    RegisterResponse,
    VerifyEmailRequest,
    ResendVerificationOTPRequest,
    LoginResponse,
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    LogoutRequest,
    ForgotPasswordRequest,
    VerifyResetOTPRequest,
    ResendResetOTPRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,

)
from app.core.schemas import MessageResponse
from app.auth.services import (
    register_user,
    verify_email,
    resend_verification_otp,
    login_user,
    refresh_access_token,
    logout_user,
    forgot_password,
    verify_reset_otp, 
    resend_reset_otp,
    reset_password,
    change_password,
)

from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=201,
)
async def register_route(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    return await register_user(db, request)


@router.post(
    "/verify-email",
    response_model=MessageResponse,
)
async def verify_email_route(
    request: VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    return await verify_email(db, request)


@router.post(
    "/resend-verification-otp",
    response_model=MessageResponse,
)
async def resend_otp_route(
    request: ResendVerificationOTPRequest,
    db: Session = Depends(get_db),
):
    return await resend_verification_otp(db, request)

@router.post(
    "/login",
    response_model=LoginResponse,
)
async def login_route(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    return await login_user(db, request)


@router.post(
    "/token",
    summary="Login (OAuth2 form, used by Swagger's Authorize button)",
    description="Same checks as /auth/login. Put the email in `username`.",
)
async def token_route(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    try:
        credentials = LoginRequest(email=form.username, password=form.password)
    except ValidationError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    result = await login_user(db, credentials)
    return {
        "access_token": result.tokens.access_token,
        "token_type": "bearer",
        "refresh_token": result.tokens.refresh_token,
    }

@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
)
async def refresh_route(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    return await refresh_access_token(db, request)

@router.post(
    "/logout",
    response_model=MessageResponse,
)
async def logout_route(
    request: LogoutRequest,
    db: Session = Depends(get_db),
):
    return await logout_user(db, request)

@router.post(
    "/forgot-password",
    response_model=MessageResponse,
)  
async def forgot_password_route(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    return await forgot_password(db, request)

@router.post(
    "/verify-reset-otp",
    response_model=MessageResponse)
async def  verify_reset_otp_route(
    request: VerifyResetOTPRequest,
    db: Session = Depends(get_db),
):
    return await verify_reset_otp(db, request)

@router.post(
    "/resend-reset-otp",
    response_model=MessageResponse
)
async def resend_reset_otp_route(
    request: ResendResetOTPRequest,
    db: Session = Depends(get_db),
):
    return await resend_reset_otp(db, request)

@router.post(
    "/reset-password",
    response_model=MessageResponse
)
async def reset_password_route(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    return await reset_password(db, request)


@router.post(
    "/change-password",
    response_model=MessageResponse
)
async def change_password_route(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await change_password(db=db, request=request, user=user)