# PC2 Smart Mirror Coaching Engine

> 이 리포는 **PC2 전용 저장소**입니다.  
> PC1 리포: [smart-mirror-exercise-only](https://github.com/dpgns9983-dot/smart-mirror-exercise-only)  
> PC3 리포: [smart-mirror-aiot-coaching](https://github.com/rad1092/smart-mirror-aiot-coaching)

PC2는 스마트 미러 프로젝트에서 운동 지식 검색과 AI 생성 응답을 담당하는 백엔드입니다.  
전체 시스템은 `PC1 -> PC3 -> PC2` 구조로 동작하며, PC2는 프로필 기반 루틴 생성과 운동 종료 후 코칭 생성을 맡습니다.

```text
PC1 UI -> PC3 Vision Gateway -> PC2 NVIDIA/RAG Engine
```

## 프로젝트 소개

이 프로젝트는 사용자의 운동 수행 데이터를 바탕으로 맞춤형 운동 루틴과 운동 후 코칭을 제공하는 스마트 미러 시스템의 일부입니다.

- `PC1`
  - 사용자 앱과 화면 UI를 담당합니다.
- `PC3`
  - 운동 분석, 중앙 오케스트레이션, 다른 서비스 연계를 담당합니다.
- `PC2`
  - 운동 지식 RAG, 루틴 생성, 코칭 생성 API를 담당합니다.

즉, PC2는 전체 프로젝트 안에서 "AI 생성 서버" 역할을 수행합니다.

## 문제 정의

운동 코칭 시스템은 단순히 문장을 생성하는 것만으로는 부족합니다. 실제 서비스에서는 아래 문제가 동시에 존재합니다.

- 사용자 프로필에 맞는 주간 루틴을 구조화된 형태로 안정적으로 생성해야 합니다.
- 운동 종료 후 분석 결과를 자연스러운 코칭 문장으로 바꿔야 합니다.
- 생성 결과가 흔들려도 PC3가 처리 가능한 JSON 계약을 유지해야 합니다.
- 근거 없는 문장 생성이 아니라 운동 지식 기반의 응답이 필요합니다.
- 모델 장애나 응답 파싱 실패 시 어떤 계층이 실패를 책임질지 명확해야 합니다.

이 저장소는 위 문제를 해결하기 위해 PC2를 RAG 기반 생성 엔진으로 정리한 결과물입니다.

## 역할

이 리포에서 맡은 역할은 PC2 백엔드의 구조 정리와 생성 파이프라인 안정화입니다.

- FastAPI 기반 PC2 API 구조 정리
- NVIDIA OpenAI-compatible API 연동
- PostgreSQL/pgvector 기반 RAG 흐름 구성
- 프로필 루틴 생성과 운동 후 코칭 생성 API 설계
- JSON 응답 계약 정규화와 validator 보강
- 문서 구조 재정리
- 기존 `main` 문서를 `main-old`로 분리하고 새 `main` 기준 문서 체계 정리

## PC2의 역할

PC2는 전체 프로젝트에서 "생성 엔진 + 운동 지식 검색 엔진" 역할을 맡습니다.

- 프로필 기반 주간 루틴을 생성합니다.
- 운동 완료 후 분석 결과를 바탕으로 코칭 문구를 생성합니다.
- PostgreSQL/pgvector와 NVIDIA API를 사용해 근거 기반 응답을 만듭니다.
- PC3가 바로 사용할 수 있는 API 응답 형태로 결과를 정리합니다.

PC2가 하지 않는 일:

- PC1 UI 처리
- 사용자 인증/인가
- 비전 추론과 자세 분석
- 중앙 비즈니스 오케스트레이션
- PC3 원장 데이터 저장소 역할

## 아키텍처

### 서비스 구조

```text
PC1 UI
  -> PC3 Vision Gateway / Orchestrator
    -> PC2 FastAPI
      -> NVIDIA Chat Model
      -> NVIDIA Embedding / Rerank
      -> PostgreSQL / pgvector
```

### PC2 내부 흐름

```text
Request from PC3
  -> schema validation
  -> prompt composition
  -> RAG retrieval
  -> NVIDIA generation
  -> output validation / normalization
  -> response to PC3
```

## 주요 기능

- `POST /api/routine/profile`
  - PC3가 전달한 사용자 프로필로 주간 루틴을 생성합니다.
- `GET /api/routine/profile/{user_id}/day`
  - 특정 날짜의 루틴 day record를 조회합니다.
- `GET /api/routine/profile/{user_id}/calendar`
  - 날짜 범위 기준 루틴 캘린더를 조회합니다.
- `POST /api/coach/generate`
  - 운동 완료 후 분석 결과를 바탕으로 한국어 코칭 응답을 생성합니다.
- `POST /api/workouts/skip`
  - 스킵 운동 기록을 저장합니다.
- `POST /api/users/{user_id}/body-metrics`
  - 체중 기록을 저장합니다.
- `GET /api/users/{user_id}/progress`
  - 체중 추이와 진행 상태를 조회합니다.
- `GET /api/coach/logs/{user_id}`
  - 최근 코칭 로그를 조회합니다.
- `POST /api/knowledge/ingest`
  - seed 운동 지식을 DB에 적재합니다.
- `GET /api/knowledge/search`
  - 운동 지식 검색과 rerank 결과를 확인합니다.

## 기술 스택

| 구분 | 사용 기술 |
| --- | --- |
| Language | Python 3.12 |
| API | FastAPI, Uvicorn |
| Validation | Pydantic |
| HTTP Client | httpx, OpenAI Python SDK |
| DB | PostgreSQL, pgvector, SQLite fallback |
| ORM/Core | SQLAlchemy |
| Config | python-dotenv |
| Logging | Python logging |
| AI Provider | NVIDIA OpenAI-compatible API |

## 디렉터리 구조

```text
.
├── app/
│   ├── main.py
│   ├── services.py
│   ├── rag.py
│   ├── llm_client.py
│   ├── db.py
│   ├── config.py
│   └── schemas/
├── data/
│   └── exercise_knowledge_seed.json
├── old_main_docs/
│   ├── README.md
│   ├── CHANGELOG.md
│   └── FLOW_CHANGES.md
├── CHANGELOG.md
├── FLOW_CHANGES.md
└── requirements.txt
```

## 실행 환경

권장 환경:

- Python `3.12`
- PostgreSQL `16` + `pgvector`
- NVIDIA API Key

기본 저장소 설정:

- `.env`에 `DATABASE_URL`이 없으면 `sqlite:///./data/pc2_local.sqlite3`를 사용합니다.
- 실사용과 RAG 검증 기준은 PostgreSQL/pgvector를 권장합니다.

## 실행 방법

### 1. 저장소 클론

```bash
git clone https://github.com/tmdwn0196-osj/smart-mirror-aiot-coaching.git
cd smart-mirror-aiot-coaching
```

### 2. 가상환경 생성과 의존성 설치

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 환경 변수 파일 생성

```bash
cp .env.example .env
```

핵심 환경 변수:

```env
SERVICE_NAME=pc2-coach-api
HOST=0.0.0.0
PORT=7000

DATABASE_URL=postgresql+psycopg://pc2:pc2_local_pw@127.0.0.1:5432/pc2_smart_mirror

NVIDIA_API_KEY=<NVIDIA_API_KEY>
PRIMARY_LLM_BASE_URL=https://integrate.api.nvidia.com/v1
PRIMARY_LLM_MODEL_NAME=meta/llama-3.3-70b-instruct

EMBEDDING_MODEL_NAME=nvidia/llama-nemotron-embed-1b-v2
RERANK_MODEL_NAME=nvidia/llama-nemotron-rerank-1b-v2
EMBEDDING_API_URL=https://integrate.api.nvidia.com/v1/embeddings
RERANK_API_URL=https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking
```

### 4. PostgreSQL/pgvector 실행

```bash
docker volume create pc2_pgvector_data
docker run --name pc2-pgvector \
  -e POSTGRES_DB=pc2_smart_mirror \
  -e POSTGRES_USER=pc2 \
  -e POSTGRES_PASSWORD=pc2_local_pw \
  -p 127.0.0.1:5432:5432 \
  -v pc2_pgvector_data:/var/lib/postgresql/data \
  -d pgvector/pgvector:pg16
```

### 5. 서버 실행

```bash
uvicorn app.main:app --host 0.0.0.0 --port 7000
```

### 6. RAG 초기 적재

```bash
curl -X POST http://127.0.0.1:7000/api/knowledge/ingest
```

## API 요약

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/health` | LLM, DB 상태 확인 |
| `POST` | `/api/routine/profile` | 프로필 기반 주간 루틴 생성 |
| `GET` | `/api/routine/profile/{user_id}/day` | 날짜별 day 루틴 조회 |
| `GET` | `/api/routine/profile/{user_id}/calendar` | 기간별 루틴 캘린더 조회 |
| `POST` | `/api/coach/generate` | 운동 종료 후 코칭 생성 |
| `POST` | `/api/workouts/skip` | 운동 스킵 저장 |
| `GET` | `/api/coach/logs/{user_id}` | 최근 코칭 로그 조회 |
| `POST` | `/api/users/{user_id}/body-metrics` | 체중 기록 저장 |
| `GET` | `/api/users/{user_id}/progress` | 체중 진행 상태 조회 |
| `POST` | `/api/knowledge/ingest` | seed 지식 적재 |
| `GET` | `/api/knowledge/search` | 운동 지식 검색 |

## 검증 방법

```bash
python -m compileall app
curl http://127.0.0.1:7000/health
curl "http://127.0.0.1:7000/api/knowledge/search?q=squat%20knee%20pain&exercise=squat"
```

확인 포인트:

- `primary_llm.status`
- `storage.status`
- `score`
- `rerank_logit`

## 문서와 브랜치 이력

- 현재 루트 문서 `README.md`, `CHANGELOG.md`, `FLOW_CHANGES.md`는 `old_main_docs/`의 내용을 현재 PC2 구조 기준으로 흡수해 갱신했습니다.
- 기존 기본 브랜치는 `main-old`로 분리하고, 현재 작업 브랜치를 새 `main`으로 병합해 기준 브랜치를 교체했습니다.
- 상세 변경 이력은 [CHANGELOG.md](CHANGELOG.md), 흐름 변화는 [FLOW_CHANGES.md](FLOW_CHANGES.md)에서 확인할 수 있습니다.
