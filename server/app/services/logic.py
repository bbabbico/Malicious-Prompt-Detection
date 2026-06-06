from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import UserRepository, APIKeyRepository, LogRepository
from app.models.domain import User, APIKey, DetectionLog
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.rate_limit import RateLimiter
from app.core.ai_core import analyze_prompt_threat
import time
import hashlib
import uuid
import logging

logger = logging.getLogger("sanitize")

class AuthService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def signup(self, email, password):
        hashed = get_password_hash(password)
        user = User(email=email, password_hash=hashed)
        return await self.repo.create(user)

    async def login(self, email, password):
        user = await self.repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            return None
        return create_access_token({"sub": user.email, "user_id": user.user_id})

class AnalyzeService:
    def __init__(self, db: AsyncSession):
        self.key_repo = APIKeyRepository(db)
        self.log_repo = LogRepository(db)

    async def analyze_prompt(self, api_key_str: str, prompt: str, model_type: int = 0):
        start_time = time.time()
        model_name = "large" if model_type == 1 else "small"
        logger.info(f"[analyze] 요청 수신 — 모델: e5-{model_name}  프롬프트: {prompt[:50]}...")

        # 1. API Key Validation
        logger.info("[analyze] [1/3] API 키 검증 중...")
        key_hash = hashlib.sha256(api_key_str.encode()).hexdigest()
        api_key = await self.key_repo.get_by_hash(key_hash)
        if not api_key:
            logger.warning("[analyze] API 키 인증 실패")
            return {"error": "Invalid API Key", "status": 401}

        # 2. Rate Limiting
        logger.info("[analyze] [2/3] Rate limit 확인 중...")
        from sqlalchemy.future import select
        from app.models.domain import User
        user_result = await self.key_repo.db.execute(select(User).where(User.user_id == api_key.user_id))
        user = user_result.scalars().first()

        if not await RateLimiter.check_limits(user.user_id, user.tps_limit, user.daily_quota):
            logger.warning("[analyze] Rate limit 초과")
            return {"error": "Rate limit exceeded", "status": 429}

        # 3. Content Analysis
        logger.info("[analyze] [3/3] 악성 여부 탐지 중...")
        t0 = time.time()
        is_malicious, risk_score = analyze_prompt_threat(prompt, model_type=model_type)
        action = "blocked" if is_malicious else "allowed"
        process_time = int((time.time() - start_time) * 1000)
        logger.info(f"[analyze] 탐지 완료 — {'악성' if is_malicious else '정상'} (위험도: {risk_score}%)  [{time.time()-t0:.2f}s]  → {action}")

        # 4. Asynchronous Logging
        used_track = "large" if model_type == 1 else "small"
        log = DetectionLog(
            key_id=api_key.key_id,
            raw_prompt=prompt,
            used_track=used_track,
            risk_score_pct=float(risk_score),
            action_taken=action,
            process_time_ms=process_time
        )
        
        return {
            "is_malicious": is_malicious,
            "risk_score": risk_score,
            "action": action,
            "process_time_ms": process_time,
            "log_data": log,
            "model_type": model_type
        }

    async def sanitize_prompt(self, api_key_str: str, prompt: str, model_type: int = 0):
        import asyncio
        from app.core.ai_core import analyze_prompt_xai, sanitize_prompt_with_llm

        key_hash = hashlib.sha256(api_key_str.encode()).hexdigest()
        api_key = await self.key_repo.get_by_hash(key_hash)
        if not api_key:
            return {"error": "Invalid API Key", "status": 401}

        # [1단계] 악성 여부 탐지
        logger.info("[1/4] 악성 여부 탐지 중...")
        t0 = time.time()
        is_malicious, risk_score = analyze_prompt_threat(prompt, model_type)
        logger.info(f"[1/4] 탐지 완료 — {'악성' if is_malicious else '정상'} (위험도 {risk_score}%) [{time.time()-t0:.2f}s]")

        if not is_malicious:
            logger.info("[완료] 이미 정상 프롬프트 — sanitize 불필요")
            return {
                "original_prompt": prompt,
                "is_malicious": False,
                "risk_score": risk_score,
                "sanitized_prompt": prompt,
                "sanitized_is_malicious": False,
                "sanitized_risk_score": risk_score,
                "sanitize_success": True,
                "already_safe": True,
            }

        # [2단계] XAI — 악성 핵심 단어 선정
        logger.info("[2/4] XAI 분석 중 — 악성 기여 단어 추출...")
        t0 = time.time()
        loop = asyncio.get_running_loop()
        highlights = await loop.run_in_executor(None, analyze_prompt_xai, prompt, model_type)
        flagged_words = [h["text"] for h in highlights if h["weight"] > 0.1]
        logger.info(f"[2/4] XAI 완료 — 악성 단어: {flagged_words} [{time.time()-t0:.2f}s]")

        # [3단계] LLM — 악성 부분을 정상으로 변환
        logger.info("[3/4] LLM 변환 중 — OpenRouter API 호출...")
        t0 = time.time()
        sanitized = await sanitize_prompt_with_llm(prompt, highlights)
        logger.info(f"[3/4] LLM 변환 완료 [{time.time()-t0:.2f}s]")
        logger.info(f"[3/4] 변환 결과: {sanitized}")

        # [4단계] 변환된 프롬프트 재검증
        logger.info("[4/4] 변환 결과 재검증 중...")
        t0 = time.time()
        sanitized_is_malicious, sanitized_risk_score = await loop.run_in_executor(
            None, analyze_prompt_threat, sanitized, model_type
        )
        logger.info(f"[4/4] 재검증 완료 — {'악성' if sanitized_is_malicious else '정상'} (위험도 {sanitized_risk_score}%) [{time.time()-t0:.2f}s]")
        logger.info(f"[완료] sanitize {'성공' if not sanitized_is_malicious else '실패'} — {risk_score}% → {sanitized_risk_score}%")

        return {
            "original_prompt": prompt,
            "is_malicious": is_malicious,
            "risk_score": risk_score,
            "xai_highlights": highlights,
            "sanitized_prompt": sanitized,
            "sanitized_is_malicious": sanitized_is_malicious,
            "sanitized_risk_score": sanitized_risk_score,
            "sanitize_success": not sanitized_is_malicious,
            "already_safe": False,
        }

    async def process_xai_and_log(self, log_data: DetectionLog, model_type: int):
        import asyncio
        from app.core.ai_core import analyze_prompt_xai
        
        # risk_score가 50 초과 (즉, 악성)일 때만 XAI 실행
        if log_data.risk_score_pct > 50:
            loop = asyncio.get_running_loop()
            # XAI 분석은 CPU 바운드이므로 executor에서 실행
            highlights = await loop.run_in_executor(
                None, 
                analyze_prompt_xai, 
                log_data.raw_prompt, 
                model_type
            )
            log_data.xai_highlights = highlights
            
        await self.log_repo.create(log_data)

import secrets

class APIKeyManagementService:
    def __init__(self, db: AsyncSession):
        self.key_repo = APIKeyRepository(db)
        self.log_repo = LogRepository(db)

    async def get_user_logs(self, user_id: int, limit: int = 50, offset: int = 0):
        logs = await self.log_repo.get_by_user_id(user_id, limit, offset)
        return [
            {
                "id": log.log_id,
                "prompt": log.raw_prompt,
                "risk_score": log.risk_score_pct,
                "action": log.action_taken,
                "process_time_ms": log.process_time_ms,
                "created_at": log.created_at,
                "xai_highlights": log.xai_highlights
            } for log in logs
        ]

    async def get_keys_for_user(self, user_id: int):
        from sqlalchemy.future import select
        from sqlalchemy import func
        from app.models.domain import DetectionLog
        from datetime import datetime, timezone
        
        keys = await self.key_repo.get_by_user_id(user_id)
        
        result_keys = []
        for k in keys:
            # Query usage count for this key (this month)
            now = datetime.now(timezone.utc)
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            stmt = select(func.count(DetectionLog.log_id)).where(
                DetectionLog.key_id == k.key_id,
                DetectionLog.created_at >= start_of_month
            )
            count_result = await self.key_repo.db.execute(stmt)
            usage_count = count_result.scalar() or 0
            
            # Query last used
            last_used_stmt = select(DetectionLog.created_at).where(
                DetectionLog.key_id == k.key_id
            ).order_by(DetectionLog.created_at.desc()).limit(1)
            last_used_result = await self.key_repo.db.execute(last_used_stmt)
            last_used = last_used_result.scalar()
            
            result_keys.append({
                "id": str(k.key_id),
                "name": k.key_name,
                "key": "", # omitted for security
                "maskedKey": f"{k.key_prefix}{'•'*20}****", # We don't have the last 4 chars in DB. It's just visual.
                "createdAt": k.created_at,
                "lastUsed": last_used,
                "usageCount": usage_count,
                "monthlyLimit": 10000,
                "status": "active",
                "permissions": ["detect"]
            })
        return result_keys

    async def get_user_stats(self, user_id: int):
        from sqlalchemy.future import select
        from sqlalchemy import func
        from app.models.domain import DetectionLog, APIKey
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Base join query
        base_query = select(DetectionLog).join(APIKey, DetectionLog.key_id == APIKey.key_id).where(APIKey.user_id == user_id)
        
        # Today requests
        today_stmt = select(func.count(DetectionLog.log_id)).select_from(DetectionLog).join(APIKey).where(
            APIKey.user_id == user_id,
            DetectionLog.created_at >= start_of_today
        )
        today_count = (await self.key_repo.db.execute(today_stmt)).scalar() or 0

        # Month requests
        month_stmt = select(func.count(DetectionLog.log_id)).select_from(DetectionLog).join(APIKey).where(
            APIKey.user_id == user_id,
            DetectionLog.created_at >= start_of_month
        )
        month_count = (await self.key_repo.db.execute(month_stmt)).scalar() or 0

        # Average response time
        avg_time_stmt = select(func.avg(DetectionLog.process_time_ms)).select_from(DetectionLog).join(APIKey).where(
            APIKey.user_id == user_id
        )
        avg_time = (await self.key_repo.db.execute(avg_time_stmt)).scalar() or 0

        return {
            "today_requests": today_count,
            "month_requests": month_count,
            "avg_response_time_ms": int(avg_time),
            "detection_success_rate": 99.7 # static as discussed
        }

    async def create_key(self, user_id: int, key_name: str):
        # Generate a real random API key
        raw_key = "pg-sk-" + secrets.token_urlsafe(36)
        key_prefix = raw_key[:10]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        
        api_key = APIKey(
            user_id=user_id,
            key_name=key_name,
            key_prefix=key_prefix,
            key_hash=key_hash
        )
        api_key_record = await self.key_repo.create(api_key)
        return raw_key, api_key_record

    async def delete_key(self, user_id: int, key_id: int):
        api_key = await self.key_repo.get_by_id_and_user_id(key_id, user_id)
        if api_key:
            await self.key_repo.delete(api_key)
            return True
        return False

