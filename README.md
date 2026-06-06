# Malicious Prompt Detection

악성 프롬프트 탐지를 위한 프론트엔드(React/Vite) 및 백엔드(FastAPI) 서비스입니다.

## 주요 기능

- **B2B 악성 프롬프트 탐지 API 제공**: 외부 기업이 자사 서비스에 연동하여 프롬프트 인젝션 및 악성 요청을 실시간으로 차단할 수 있는 RESTful API를 제공합니다.
- **2단계 AI 위협 분석 (XAI 포함)**: `intfloat/multilingual-e5` 모델과 LightGBM을 결합한 고속 추론 엔진으로 분석을 수행하며, 설명 가능한 AI(XAI) 기술을 통해 어떤 단어가 위험한지 하이라이트 결과를 함께 반환합니다.
- **LLM 기반 프롬프트 순화 및 자가 피드백**: 단순히 악성 프롬프트를 차단하는 것을 넘어, 문맥과 문장 구조를 유지하면서 안전한 단어로 치환(Sanitization)합니다. 순화된 문장은 다시 자체 탐지 모델을 통해 검증되는 자가 피드백 루프(최대 5회)를 거쳐 높은 안전성을 보장합니다.
- **엔터프라이즈급 트래픽 제어**: Nginx(1차 IP Rate Limit)와 Redis(2차 API Key 기반 TPS 및 Daily Quota 차감)를 결합한 투 트랙(Two-Track) 다층 방어 체계를 갖추고 있습니다.
- **관리자 대시보드 제공**: React 기반 프론트엔드 대시보드를 통해 API Key 발급/관리 및 자사 서비스에서 발생한 프롬프트 위협 탐지 로그를 실시간으로 모니터링할 수 있습니다.

## 프로젝트 구조

- `server`: FastAPI 기반의 백엔드 API 서버
- `client`: React 및 Vite를 사용한 프론트엔드 대시보드
- `backend`: AI 머신러닝 모델 학습 스크립트 및 추론 엔진 모듈
- `shared`: 프론트엔드와 백엔드에서 공유하는 상수 및 설정
- `nginx`: 리버스 프록시 및 트래픽 제어(Rate Limit)를 위한 서버 설정
- `AI`    : `server/app/core/ai_core.py`에 임베딩-모델 예측 로직과 OpenRouter API를 활용한 문맥 맞춤형 프롬프트 순화 및 자가 피드백 루프가 구현되어 있으며, 실제 추론 코드는 `backend` 디렉토리에 위치합니다.

## Docker로 실행하기

이 프로젝트는 Docker와 Docker Compose를 사용하여 간편하게 실행할 수 있습니다.

### 사전 준비

- [Docker](https://www.docker.com/get-started) 설치
- [Docker Compose](https://docs.docker.com/compose/install/) 설치

### 실행 방법

1. 프로젝트 루트 디렉토리에서 다음 명령어를 실행하여 컨테이너를 빌드하고 실행합니다:

   ```bash
   docker-compose up --build
   ```

2. 실행이 완료되면 다음 주소에서 서비스를 확인할 수 있습니다:

   - **프론트엔드**: [http://localhost](http://localhost)
   - **백엔드 API**: [http://localhost:8000](http://localhost:8000)
   - **API 문서 (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 서비스 구성

- **Backend (FastAPI)**:
  - Python 3.11 환경에서 실행됩니다.
  - 소스 코드는 `./server` 디렉토리에 위치하며, 실시간 변경 사항이 반영되도록 볼륨 마운트가 설정되어 있습니다.
- **Frontend (React/Vite)**:
  - `pnpm`을 사용하여 빌드되며, 최종 결과물은 `nginx`를 통해 서비스됩니다.

## 수동 설치 및 실행 (로컬 환경)

### Backend
```bash
cd server
pip install -r requirements.txt
python main.py
```

### Frontend
```bash
cd client
pnpm install
pnpm dev
```
