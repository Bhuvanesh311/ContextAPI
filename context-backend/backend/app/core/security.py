from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext
from jwt import InvalidTokenError

from app.core.config import settings


ACCESS_TOKEN_TYPE ="access"
REFRESH_TOKEN_TYPE ="refresh"

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

#password security
def hash_password(password:str)->str:
    return pwd_context.hash(password)

def verify_password(plain_password:str, hashed_password:str)-> bool:
    return pwd_context.verify(plain_password,hashed_password,)

#token utilities
def generate_jti()->str:
    return str(uuid4())


#jwt token creation
def create_token(*,subject:str,token_type:str,expires_delta:timedelta,)->str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub":subject,
        "type": token_type,
        "jti": generate_jti(),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload,settings.JWT_SECRET_KEY,algorithm=settings.JWT_ALGORITHM,)

def create_access_token(subject:str)->str:
    return create_token(subject=subject,token_type=ACCESS_TOKEN_TYPE,expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,),)

def create_refresh_token(subject:str)->str:
    return create_token(subject=subject,token_type=REFRESH_TOKEN_TYPE,expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),)

#jwt validaiton
def decode_token(token:str)-> dict[str,Any]:
    return jwt.decode(token,settings.JWT_SECRET_KEY,algorithms =[settings.JWT_ALGORITHM],)

def verify_token(token:str,*,token_type:str | None = None)-> dict[str,Any]:
    # Malformed, tampered or expired tokens are the client's problem: 401, not 500.
    try:
        payload =decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    if token_type is not None:
        if payload.get("type") != token_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")
    return payload