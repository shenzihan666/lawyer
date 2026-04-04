import json
from typing import Any

from app.core.config import Settings

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency during partial installs
    redis = None


class RedisCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None

    def _get_client(self):
        if redis is None:
            return None
        if self._client is None:
            self._client = redis.Redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
            )
        return self._client

    def _key(self, key: str) -> str:
        return f"{self.settings.redis_key_prefix}:{key}"

    def get_json(self, key: str) -> Any | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            value = client.get(self._key(key))
            if not value:
                return None
            return json.loads(value)
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False)
            client.setex(
                self._key(key),
                ttl or self.settings.redis_cache_ttl_seconds,
                payload,
            )
        except Exception:
            return

    def delete(self, key: str) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            client.delete(self._key(key))
        except Exception:
            return

    def delete_pattern(self, pattern: str) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            keys = client.keys(self._key(pattern))
            if keys:
                client.delete(*keys)
        except Exception:
            return
