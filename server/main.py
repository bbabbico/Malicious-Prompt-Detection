from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router
from app.core.database import engine, Base
import uvicorn
import logging
import os
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(title="Malicious Prompt Detection API")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "x-api-key", "Content-Type"],
)

@app.exception_handler(RuntimeError)
async def model_error_handler(request: Request, exc: RuntimeError):
    logging.getLogger("api").error(f"[모델 오류] {exc}")
    return JSONResponse(
        status_code=503,
        content={"error": "탐지 모델 오류로 요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요.", "detail": str(exc)},
    )

@app.on_event("startup")
async def startup():
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Preload AI models to prevent timeout on first API request
    from app.core.ai_core import preload_all_models
    import asyncio
    print("Starting background model preloading...")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, preload_all_models)

app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Enterprise Malicious Prompt Detection API is running"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, workers=4)
