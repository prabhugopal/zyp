"""Link lifecycle: create/get/update/delete/list, backed entirely by Redis — no SQL. Codes are
Base62-encoded sequence numbers from an INCR'd counter. Listing avoids a full-table scan by
keeping a sorted set of codes ordered by creation time (ZADD/ZREVRANGE) instead of a SQL
ORDER BY + OFFSET/LIMIT.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_COUNTER_KEY = "zyp:code_counter"
_CREATED_INDEX_KEY = "zyp:links_by_created"
_RESERVED = {"api", "admin", "static", "health"}


def _encode_base62(n: int) -> str:
    if n == 0:
        return _ALPHABET[0]
    digits = []
    while n:
        n, rem = divmod(n, 62)
        digits.append(_ALPHABET[rem])
    return "".join(reversed(digits))


class LinkNotFoundError(Exception):
    pass


class LinkExpiredError(Exception):
    pass


class AliasTakenError(Exception):
    pass


class InvalidAliasError(Exception):
    pass


@dataclass
class ShortLink:
    code: str
    original_url: str
    created_at: float
    expires_at: float | None = None
    active: bool = True

    def is_usable(self) -> bool:
        if not self.active:
            return False
        return self.expires_at is None or time.time() <= self.expires_at

    @classmethod
    def from_redis_hash(cls, h: dict) -> "ShortLink":
        return cls(
            code=h["code"],
            original_url=h["original_url"],
            created_at=float(h["created_at"]),
            expires_at=float(h["expires_at"]) if h.get("expires_at") else None,
            active=h.get("active") == "1",
        )

    def to_redis_hash(self) -> dict:
        return {
            "code": self.code,
            "original_url": self.original_url,
            "created_at": self.created_at,
            "expires_at": self.expires_at if self.expires_at is not None else "",
            "active": "1" if self.active else "0",
        }


class LinkService:
    def __init__(self, redis_client, base_url: str):
        self.redis = redis_client
        self.base_url = base_url

    def _key(self, code: str) -> str:
        return f"zyp:link:{code}"

    def create(self, original_url: str, custom_alias: str | None = None,
               expires_at: float | None = None) -> ShortLink:
        if not (original_url.startswith("http://") or original_url.startswith("https://")):
            raise ValueError("originalUrl must be http:// or https://")

        if custom_alias:
            if not (4 <= len(custom_alias) <= 20) or custom_alias.lower() in _RESERVED:
                raise InvalidAliasError(f"alias '{custom_alias}' is invalid or reserved")
            code = custom_alias
            if not self.redis.hsetnx(self._key(code), "code", code):
                raise AliasTakenError(f"alias '{code}' is already in use")
        else:
            code = _encode_base62(self.redis.incr(_COUNTER_KEY))

        link = ShortLink(code=code, original_url=original_url, created_at=time.time(), expires_at=expires_at)
        self.redis.hset(self._key(code), mapping=link.to_redis_hash())
        self.redis.zadd(_CREATED_INDEX_KEY, {code: link.created_at})
        return link

    def get(self, code: str) -> ShortLink:
        h = self.redis.hgetall(self._key(code))
        if not h:
            raise LinkNotFoundError(code)
        return ShortLink.from_redis_hash(h)

    def get_for_redirect(self, code: str) -> ShortLink:
        link = self.get(code)
        if not link.is_usable():
            raise LinkExpiredError(code)
        return link

    def update(self, code: str, expires_at: float | None = None, active: bool | None = None) -> ShortLink:
        """A None argument leaves that field unchanged. There is no way to clear an already-set
        expiry via update — only to set a new one or leave it alone."""
        link = self.get(code)
        if expires_at is not None:
            link.expires_at = expires_at
        if active is not None:
            link.active = active
        self.redis.hset(self._key(code), mapping=link.to_redis_hash())
        return link

    def delete(self, code: str) -> None:
        self.update(code, active=False)

    def list(self, page: int = 0, size: int = 20) -> tuple[list[ShortLink], int]:
        total = self.redis.zcard(_CREATED_INDEX_KEY)
        start = page * size
        codes = self.redis.zrevrange(_CREATED_INDEX_KEY, start, start + size - 1)
        return [self.get(c) for c in codes], total

    def short_url(self, code: str) -> str:
        return f"{self.base_url}/{code}"
