import datetime

from app.infra.redis.client import redis_client
from app.infra.redis.constants import (
    TOKEN_BLACKLIST_PREFIX,
    TOKEN_BLACKLIST_TTL,
)


def blacklist_token(jti: str,expires_at : datetime.datetime | None = None) -> None:
    key = f"{TOKEN_BLACKLIST_PREFIX}:{jti}"
    ttl = TOKEN_BLACKLIST_TTL
    redis_client.setex(
        key,
        ttl,
        "blacklisted",
    )


def is_token_blacklisted(jti: str) -> bool:
    key = f"{TOKEN_BLACKLIST_PREFIX}:{jti}"

    return redis_client.exists(key) == 1


def remove_blacklisted_token(jti: str) -> None:
    key = f"{TOKEN_BLACKLIST_PREFIX}:{jti}"

    redis_client.delete(key)