from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    verify_token,
    ACCESS_TOKEN_TYPE,
)

from app.auth.models import User

# Clients send "Authorization: Bearer <access_token>". tokenUrl lets Swagger's
# Authorize button log in with email + password and fill the header itself.
security = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(
    token: str = Depends(security),
    db: Session = Depends(get_db),
) -> User:

    payload = verify_token(
        token,
        token_type=ACCESS_TOKEN_TYPE,
    )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        )

    user = (
        db.query(User)
        .filter(User.user_id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    
    if not user.is_verified:
        raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Email is not verified.",
    )

    return user