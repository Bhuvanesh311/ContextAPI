from app.infra.redis.client import redis_client
from app.infra.redis.constants import (
    LOGIN_RATE_LIMIT_PREFIX,
    LOGIN_RATE_LIMIT_TTL,
    EMAIL_VERIFY_RESEND_PREFIX,
    EMAIL_VERIFY_RESEND_TTL,
    PASSWORD_RESET_RESEND_PREFIX,
    PASSWORD_RESET_RESEND_TTL,

)



#resend verification otp rate limiting
def set_email_verify_resend_cooldown(email: str) -> None:
    key = f"{EMAIL_VERIFY_RESEND_PREFIX}:{email}"

    redis_client.set(
        key,
        1,
        ex=EMAIL_VERIFY_RESEND_TTL,
    )


def is_email_verify_resend_on_cooldown(email: str) -> bool:
    key = f"{EMAIL_VERIFY_RESEND_PREFIX}:{email}"

    return redis_client.exists(key) == 1


def get_email_verify_resend_ttl(email: str) -> int:
    key = f"{EMAIL_VERIFY_RESEND_PREFIX}:{email}"

    ttl = redis_client.ttl(key)

    return max(ttl, 0)



# Login Rate Limiting
def increment_login_attempts(email: str) -> int:
    key = f"{LOGIN_RATE_LIMIT_PREFIX}:{email}"

    attempts = redis_client.incr(key)

    if attempts == 1:
        redis_client.expire(key, LOGIN_RATE_LIMIT_TTL)

    return attempts


def get_login_attempts(email: str) -> int:
    key = f"{LOGIN_RATE_LIMIT_PREFIX}:{email}"

    attempts = redis_client.get(key)

    return int(attempts) if attempts else 0

def get_login_attempts_ttl(email: str) -> int:
    key = f"{LOGIN_RATE_LIMIT_PREFIX}:{email}"

    ttl = redis_client.ttl(key)

    return max(ttl, 0)


def reset_login_attempts(email: str) -> None:
    key = f"{LOGIN_RATE_LIMIT_PREFIX}:{email}"

    redis_client.delete(key)


#resend password otp rate limiting 
def set_password_reset_resend_cooldown(email: str) -> None:
    key = f"{PASSWORD_RESET_RESEND_PREFIX}:{email}"

    redis_client.set(
        key,
        1,
        ex=PASSWORD_RESET_RESEND_TTL,
    )


def is_password_reset_resend_on_cooldown(email: str) -> bool:
    key = f"{PASSWORD_RESET_RESEND_PREFIX}:{email}"

    return redis_client.exists(key) == 1


def get_password_reset_resend_ttl(email: str) -> int:
    key = f"{PASSWORD_RESET_RESEND_PREFIX}:{email}"

    ttl = redis_client.ttl(key)

    return max(ttl, 0)