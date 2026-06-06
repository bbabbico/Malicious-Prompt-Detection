import redis.asyncio as redis
import logging
import os
import time

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

_log = logging.getLogger("rate_limit")

class RateLimiter:
    @staticmethod
    async def check_limits(user_id: int, tps_limit: int, daily_quota: int) -> bool:
        current_time = int(time.time())
        tps_key = f"tps:{user_id}:{current_time}"
        quota_key = f"quota:{user_id}:{time.strftime('%Y%m%d')}"

        try:
            # TPS Check
            current_tps = await redis_client.incr(tps_key)
            if current_tps == 1:
                await redis_client.expire(tps_key, 1)

            if current_tps > tps_limit:
                return False

            # Daily Quota Check
            current_quota = await redis_client.incr(quota_key)
            if current_quota == 1:
                await redis_client.expire(quota_key, 86400)

            if current_quota > daily_quota:
                return False

            return True

        except Exception as e:
            # Redis 연결 실패 시 Rate Limit을 건너뛰고 요청 허용
            _log.warning(f"[rate_limit] Redis 연결 실패 — Rate Limit 비활성화됨: {e}")
            return True
