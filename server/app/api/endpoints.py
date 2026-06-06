from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header, Request, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import SECRET_KEY, ALGORITHM
from app.services.logic import AuthService, AnalyzeService, APIKeyManagementService
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging
import time
import redis.asyncio as redis
import os

_log = logging.getLogger("api")

# demo 엔드포인트 IP 기반 Rate Limit
_redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6380/0"), decode_responses=True)
DEMO_TPS_LIMIT   = 5    # IP당 초당 5번
DEMO_DAILY_LIMIT = 100  # IP당 하루 100번

async def check_demo_rate_limit(request: Request):
    ip = request.client.host
    now = int(time.time())
    tps_key   = f"demo_tps:{ip}:{now}"
    daily_key = f"demo_daily:{ip}:{time.strftime('%Y%m%d')}"
    try:
        tps = await _redis.incr(tps_key)
        if tps == 1:
            await _redis.expire(tps_key, 1)
        if tps > DEMO_TPS_LIMIT:
            raise HTTPException(status_code=429, detail="요청이 너무 많습니다. 잠시 후 다시 시도해주세요.")

        daily = await _redis.incr(daily_key)
        if daily == 1:
            await _redis.expire(daily_key, 86400)
        if daily > DEMO_DAILY_LIMIT:
            raise HTTPException(status_code=429, detail="일일 데모 한도를 초과했습니다.")
    except HTTPException:
        raise
    except Exception:
        pass  # Redis 장애 시 통과

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="users/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        return user_id
    except JWTError:
        raise credentials_exception

class UserAuth(BaseModel):
    email: EmailStr
    password: str

from pydantic import BaseModel, EmailStr, Field

# ...

class PromptAnalysisRequest(BaseModel):
    prompt: str = Field(..., description="분석할 원본 텍스트 프롬프트")
    model: str = Field("intfloat/multilingual-e5-small", description="사용할 AI 모델 버전 (small/large)")
    include_xai: bool = Field(False, description="XAI(설명 가능한 AI) 결과를 포함할지 여부 (위험 단어 가중치 배열 반환)")
    include_sanitized: bool = Field(False, description="LLM을 활용한 순화된(Sanitized) 프롬프트를 포함할지 여부")

class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., description="생성할 API 키의 식별용 이름")

@router.post("/users/signup")
async def signup(user_data: UserAuth, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    user = await service.signup(user_data.email, user_data.password)
    return {"message": "User created", "user_id": user.user_id}

@router.post("/users/login")
async def login(user_data: UserAuth, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    token = await service.login(user_data.email, user_data.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": token, "token_type": "bearer"}

@router.get("/users/logs")
async def get_user_logs(
    limit: int = 50,
    offset: int = 0,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = APIKeyManagementService(db)
    logs = await service.get_user_logs(user_id, limit, offset)
    return logs

@router.get("/users/stats")
async def get_user_stats(user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = APIKeyManagementService(db)
    stats = await service.get_user_stats(user_id)
    return stats

@router.get("/users/keys")
async def get_api_keys(user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = APIKeyManagementService(db)
    keys = await service.get_keys_for_user(user_id)
    return keys

@router.post("/users/keys")
async def create_api_key(request: APIKeyCreateRequest, user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = APIKeyManagementService(db)
    new_key, api_key_record = await service.create_key(user_id, request.name)
    return {
        "id": str(api_key_record.key_id),
        "name": api_key_record.key_name,
        "key": new_key, # the raw key (only returned once)
        "maskedKey": f"{api_key_record.key_prefix}{'•'*20}{new_key[-4:]}",
        "createdAt": api_key_record.created_at,
        "lastUsed": None,
        "usageCount": 0,
        "monthlyLimit": 10000,
        "status": "active",
        "permissions": ["detect"]
    }

@router.delete("/users/keys/{key_id}")
async def delete_api_key(key_id: int, user_id: int = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = APIKeyManagementService(db)
    success = await service.delete_key(user_id, key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API Key not found")
    return {"message": "API Key deleted"}

class PromptSanitizeRequest(BaseModel):
    prompt: str = Field(..., description="순화할 원본 텍스트 프롬프트")
    model: str = Field("intfloat/multilingual-e5-small", description="사용할 AI 모델 버전")

class PromptAnalysisDemoRequest(BaseModel):
    prompt: str = Field(..., description="테스트용 원본 텍스트 프롬프트")
    model: str = Field("intfloat/multilingual-e5-small", description="사용할 AI 모델 버전")
    include_xai: bool = Field(False, description="XAI 결과 포함 여부")
    include_sanitized: bool = Field(False, description="순화된 프롬프트 포함 여부")

@router.post("/v1/sanitize")
async def sanitize(
    request: PromptSanitizeRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    service = AnalyzeService(db)
    model_type = 1 if "large" in request.model.lower() else 0
    result = await service.sanitize_prompt(x_api_key, request.prompt, model_type)

    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])

    return result

@router.post("/v1/analyze/demo")
async def analyze_demo(
    request: Request,
    body: PromptAnalysisDemoRequest,
    _: None = Depends(check_demo_rate_limit),
):
    from app.core.ai_core import analyze_prompt_threat
    model_type = 1 if "large" in body.model.lower() else 0
    model_name = "large" if model_type == 1 else "small"
    _log.info(f"[demo] 요청 수신 — IP: {request.client.host}  모델: e5-{model_name}  프롬프트: {body.prompt[:50]}...")
    t0 = time.time()
    is_malicious, risk_score = analyze_prompt_threat(body.prompt, model_type=model_type)
    process_time = int((time.time() - t0) * 1000)
    _log.info(f"[demo] 완료 — {'악성' if is_malicious else '정상'} (위험도: {risk_score}%)  [{process_time}ms]")
    response = {
        "safe": not is_malicious,
        "score": risk_score / 100.0,
        "processingTime": process_time
    }
    
    if (body.include_xai or body.include_sanitized) and is_malicious:
        import asyncio
        from app.core.ai_core import analyze_prompt_xai
        loop = asyncio.get_running_loop()
        highlights = await loop.run_in_executor(None, analyze_prompt_xai, body.prompt, model_type)
        if body.include_xai:
            response["xai_highlights"] = highlights
        if body.include_sanitized:
            from app.core.ai_core import sanitize_prompt_with_llm
            sanitized = await sanitize_prompt_with_llm(body.prompt, highlights, model_type=model_type, max_retries=5)
            response["sanitized_prompt"] = sanitized

    return response

@router.post("/v1/analyze", summary="프롬프트 위협 분석 (B2B)", tags=["AI Analysis"], description="API 키를 사용하여 프롬프트의 악성 여부를 판단하고, 옵션에 따라 XAI 결과 및 순화된 텍스트를 반환합니다.")
async def analyze(
    request: PromptAnalysisRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(..., description="발급받은 B2B 전용 API 키 (pg-sk-...)"),
    db: AsyncSession = Depends(get_db)
):
    service = AnalyzeService(db)
    model_type = 1 if "large" in request.model.lower() else 0
    result = await service.analyze_prompt(
        x_api_key, 
        request.prompt, 
        model_type, 
        include_xai=request.include_xai, 
        include_sanitized=request.include_sanitized
    )
    
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    
    # Background log save with optional XAI
    log_data = result.pop("log_data")
    model_type = result.pop("model_type")
    background_tasks.add_task(service.process_xai_and_log, log_data, model_type)
    
    return result

@router.get("/v1/logs", summary="탐지 로그 조회 (B2B)", tags=["AI Analysis"], description="API 키를 사용하여 해당 키로 발생한 과거의 탐지 및 순화 로그 내역을 조회합니다.")
async def get_api_logs(
    limit: int = Query(50, description="가져올 로그의 최대 개수"),
    offset: int = Query(0, description="페이징 오프셋"),
    x_api_key: str = Header(..., description="발급받은 B2B 전용 API 키"),
    db: AsyncSession = Depends(get_db)
):
    service = AnalyzeService(db)
    result = await service.get_logs_by_api_key(x_api_key, limit, offset)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    return result
