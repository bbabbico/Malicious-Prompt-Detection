# 🚀 B2B 악성 프롬프트 탐지 SaaS 백엔드 구현 명세서 (Enterprise-Ready)

당신은 대규모 트래픽을 처리하는 시니어 파이썬 백엔드 엔지니어입니다. 아래 명세된 요구사항을 바탕으로, FastAPI 기반의 B2B 악성 프롬프트 탐지 서비스 백엔드 코드를 도메인 주도 설계(DDD) 및 계층형 아키텍처(Layered Architecture)로 작성해 주세요.

## 1. 아키텍처 및 다층 방어(Defense in Depth) 전략
본 시스템은 트래픽과 어뷰징을 방어하기 위해 Nginx와 Redis를 활용한 투 트랙(Two-Track) 방어선을 구축합니다.
* **1차 방어선 (Nginx):** IP 기반의 원초적인 트래픽 제한 (`limit_req_zone` 사용) 및 리버스 프록시 역할.
* **2차 방어선 (Redis + FastAPI):** 로그인한 유저의 API Key를 기준으로 DB에 설정된 `tps_limit`과 `daily_quota`를 제어하는 비즈니스 레벨 Rate Limiting.
* **AI 코어 (FastAPI):** `intfloat/multilingual-e5-small` & `large` 모델 + LightGBM을 사용한 2단계 추론 엔진 (싱글톤 패턴으로 메모리 로드).

## 2. 데이터베이스 (ERD 및 MySQL/SQLAlchemy 2.0 Async)
* `USERS`: `user_id`(PK), `email`(Unique), `password_hash`, `daily_quota`(int), `tps_limit`(int), `created_at`
* `API_KEYS`: `key_id`(PK), `user_id`(FK), `key_name`, `key_prefix`, `key_hash`(Unique Index), `expires_at`, `created_at`
* `DETECTION_LOGS`: `log_id`(PK), `key_id`(FK), `raw_prompt`, `used_track`, `risk_score_pct`, `action_taken`, `process_time_ms`, `xai_highlights`(JSON), `created_at` (Index: key_id + created_at)

## 3. 계층형 폴더 구조 (Strict Layering)
* `app/api`: 엔드포인트 라우팅 및 Pydantic 스키마 검증 (`endpoints.py`)
* `app/services`: 비즈니스 로직 및 트랜잭션 처리 (Router에서 DB Session을 직접 호출하지 않고 Service를 거침)
* `app/repositories`: SQLAlchemy DB I/O 전담
* `app/core`: JWT/Bcrypt 보안, DB/Redis 연결 설정, AI 모델 싱글톤 클래스

## 4. 핵심 구현 지시사항
1.  **JWT 인증:** 프론트엔드 연동을 위해 `POST /api/users/login`, `POST /api/users/signup` 구현.
2.  **API Key 관리:** `POST /api/keys` (키 해시 저장), `GET /api/keys`, `DELETE /api/keys/{id}`. 토큰 보유자만 접근 가능.
3.  **오픈 API (`POST /api/v1/analyze`):**
    * `X-API-Key` 헤더를 해싱하여 DB/Redis에서 캐싱 및 유효성 검증.
    * Redis를 사용해 유저의 `daily_quota`와 `tps_limit` 차감. 한도 초과 시 429 에러 반환.
    * Rule-based 필터링 후 통과된 텍스트만 AI 모델로 추론.
    * 파라미터(`include_xai`, `include_sanitized`)에 따라 동기적 XAI 분석 및 LLM 자가 피드백 루프(Self-Correction)를 통한 문맥 맞춤형 순화(Sanitization) 기능 지원.
    * 추론 완료 후 `BackgroundTasks`를 통해 `DETECTION_LOGS`에 비동기로 인서트하여 응답 지연 방지.
4.  **B2B 로그 조회 API (`GET /api/v1/logs`):**
    * `X-API-Key` 헤더를 통해 외부 B2B 고객이 자사 서버에서 발생한 탐지 및 순화 로그 내역을 연동 및 조회할 수 있도록 제공.

### 5. 참고 파일
1. docker-compose에 인프라 스트럭쳐 뼈대가 있으니 이거 참고해서 작업.
2. nginx.conf 이건 nginx 구성 파일임. 나중에 수정 할꺼 수정하고, 파일 위치 옮겨도 됨.