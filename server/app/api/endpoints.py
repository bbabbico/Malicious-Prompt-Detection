from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import SECRET_KEY, ALGORITHM
from app.services.logic import AuthService, AnalyzeService, APIKeyManagementService
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from typing import Optional

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

class PromptAnalysisRequest(BaseModel):
    prompt: str

class APIKeyCreateRequest(BaseModel):
    name: str

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

class PromptAnalysisDemoRequest(BaseModel):
    prompt: str
    model: str = "intfloat/multilingual-e5-small"

@router.post("/v1/analyze/demo")
async def analyze_demo(request: PromptAnalysisDemoRequest):
    import time
    from app.core.ai_core import analyze_prompt_threat
    
    start_time = time.time()
    model_type = 1 if "large" in request.model.lower() else 0
    
    # 1. 실제 AI 보안 분석 엔진 호출
    analysis_res = analyze_prompt_threat(request.prompt, model_type=model_type)
    process_time = int((time.time() - start_time) * 1000)
    
    is_malicious = analysis_res["is_malicious"]
    risk_score = analysis_res["risk_score"]
    category = analysis_res["category"]
    is_anomaly = analysis_res["is_anomaly"]
    
    # 2. UI 하위 호환성을 완벽히 보장하면서도 실제 탐지 데이터를 기반으로 다이나믹 매핑
    # 기존 고정 카테고리에 '실제 탐지된 악성 카테고리'와 '신종 이상치 감지 여부'를 온전히 투영합니다.
    confidence_val = risk_score / 100.0 if is_malicious else 0.01
    
    # 2. 실시간 군집 매핑 결과를 바탕으로 세부 카테고리 다이나믹 동적 빌드 (29개 위협 전면 개방)
    categories = []
    
    # 2-1) Prompt Injection 지표
    categories.append({
        "name": "Prompt Injection / Obfuscation (지능형 우회 검사)",
        "detected": is_malicious and (is_anomaly or "Bypassing" in str(category)),
        "confidence": confidence_val * 0.95 if is_malicious else 0.01
    })
    
    # 2-2) Jailbreak 및 Anomaly 경보 동적 탑재
    if is_anomaly:
        categories.append({
            "name": "⚠️ SHIELD ALERT (미지의 신종 변종 제로데이)",
            "detected": True,
            "confidence": 0.98
        })
    else:
        categories.append({
            "name": "Jailbreak: Known Type (기존 탐색된 보안 위협)",
            "detected": is_malicious,
            "confidence": confidence_val * 0.85 if is_malicious else 0.01
        })
        
    # 2-3) 백엔드 HDBSCAN 군집 엔진이 분류해 낸 진짜 29개 실측 위반 카테고리 동적 주입!
    if is_malicious:
        categories.append({
            "name": f"Harmful Content: {category}",
            "detected": True,
            "confidence": confidence_val
        })
    else:
        categories.append({
            "name": "Harmful Content: Safe (유해 콘텐츠 미검출)",
            "detected": False,
            "confidence": 0.01
        })
    
    return {
        "safe": not is_malicious,
        "score": risk_score / 100.0,
        "categories": categories,
        "processingTime": process_time,
        "cluster_id": analysis_res["cluster_id"],
        "is_anomaly": is_anomaly,
        "violation_type": category
    }

@router.post("/v1/analyze")
async def analyze(
    request: PromptAnalysisRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    service = AnalyzeService(db)
    result = await service.analyze_prompt(x_api_key, request.prompt)
    
    if "error" in result:
        raise HTTPException(status_code=result["status"], detail=result["error"])
    
    # Background log save
    log_data = result.pop("log_data")
    background_tasks.add_task(service.log_repo.create, log_data)
    
    return result
