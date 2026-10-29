from app.infra.redis.client import redis_client
from app.infra.redis.constants import (
    EMAIL_VERIFY_OTP_PREFIX,
    EMAIL_VERIFY_OTP_TTL,
    PASSWORD_RESET_OTP_PREFIX,
    PASSWORD_RESET_OTP_TTL,
)



# Email Verification OTP
def set_email_verification_otp(email: str, otp: str) -> None:
    key = f"{EMAIL_VERIFY_OTP_PREFIX}:{email}"
    redis_client.setex(key, EMAIL_VERIFY_OTP_TTL, otp)


def get_email_verification_otp(email: str) -> str | None:
    key = f"{EMAIL_VERIFY_OTP_PREFIX}:{email}"
    return redis_client.get(key)


def delete_email_verification_otp(email: str) -> None:
    key = f"{EMAIL_VERIFY_OTP_PREFIX}:{email}"
    redis_client.delete(key)


# Password Reset OTP
def set_password_reset_otp(email: str, otp: str) -> None:
    key = f"{PASSWORD_RESET_OTP_PREFIX}:{email}"
    redis_client.setex(key, PASSWORD_RESET_OTP_TTL, otp)


def get_password_reset_otp(email: str) -> str | None:
    key = f"{PASSWORD_RESET_OTP_PREFIX}:{email}"
    return redis_client.get(key)


def delete_password_reset_otp(email: str) -> None:
    key = f"{PASSWORD_RESET_OTP_PREFIX}:{email}"
    redis_client.delete(key)