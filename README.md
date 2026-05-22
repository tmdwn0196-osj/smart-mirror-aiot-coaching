# PC2 Smart Mirror Coaching Engine

PC2는 스마트 미러의 운동 지식과 NVIDIA 생성 모델을 담당하는 서버입니다.

런타임 연결은 아래 구조로 고정합니다.

```text
PC1 UI -> PC3 Vision Gateway -> PC2 NVIDIA/RAG Engine
```

PC1은 PC2를 직접 호출하지 않습니다. PC3가 루틴 생성과 운동 후 코칭이 필요할 때만 PC2를 호출합니다.

현재 사용자 프로필, 루틴, 달력, 몸무게, 운동 결과, 코칭 로그의 원본 저장소는 PC3입니다. PC2의 PostgreSQL/pgvector는 운동 지식 RAG와 생성 품질을 위한 저장소로 사용합니다.

## PC2가 하는 일

- NVIDIA OpenAI-compatible chat API로 루틴과 코칭 JSON을 생성합니다.
- PostgreSQL/pgvector에 운동 지식 seed를 저장합니다.
- 요청마다 query embedding, vector search, rerank를 수행해서 근거를 붙입니다.
- 루틴과 코칭 문장은 사용자에게 보이는 값 기준으로 한국어를 강제합니다.
- 코칭 응답의 `pc2_payload.display_lines`는 최소 4줄 이상을 보장합니다.
- local fallback으로 성공처럼 꾸미지 않습니다. NVIDIA, RAG, DB가 실패하면 명확히 실패를 반환합니다.

## PC2가 하지 않는 일

- PC1 직접 연결
- 카메라, WebSocket, baseline, 자세 분석
- 로그인, 회원가입, JWT, OAuth, 권한 처리
- 별도 RAG 서버, LangChain, LangGraph, queue, worker
- PC3 앱 DB를 대체하는 사용자 원장 역할

## PostgreSQL/pgvector 실행

로컬 개발 기준 DB는 Docker `pgvector/pgvector:pg16` 컨테이너 하나로 맞춥니다.

```powershell
docker volume create pc2_pgvector_data
docker run --name pc2-pgvector `
  -e POSTGRES_DB=pc2_smart_mirror `
  -e POSTGRES_USER=pc2 `
  -e POSTGRES_PASSWORD=pc2_local_pw `
  -p 127.0.0.1:5432:5432 `
  -v pc2_pgvector_data:/var/lib/postgresql/data `
  -d pgvector/pgvector:pg16
```

이미 컨테이너가 있으면 시작만 합니다.

```powershell
docker start pc2-pgvector
```

`.env`의 DB 값은 아래처럼 둡니다.

```env
DATABASE_URL=postgresql+psycopg://pc2:pc2_local_pw@127.0.0.1:5432/pc2_smart_mirror
```

## NVIDIA/RAG 설정

`.env.example`을 복사해서 `.env`를 만들고 NVIDIA 키를 넣습니다.

```powershell
copy .env.example .env
notepad .env
```

핵심 설정은 아래와 같습니다.

```env
NVIDIA_API_KEY=<NVIDIA_API_KEY>
PRIMARY_LLM_BASE_URL=https://integrate.api.nvidia.com/v1
PRIMARY_LLM_MODEL_NAME=meta/llama-3.3-70b-instruct

EMBEDDING_MODEL_NAME=nvidia/llama-nemotron-embed-1b-v2
RERANK_MODEL_NAME=nvidia/llama-nemotron-rerank-1b-v2
EMBEDDING_API_URL=https://integrate.api.nvidia.com/v1/embeddings
RERANK_API_URL=https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking
EMBEDDING_DIMENSIONS=512
RAG_VECTOR_TOP_K=30
RAG_CONTEXT_K=5
```

timeout 기준:

- 일반 LLM timeout: `30초`
- primary LLM timeout: `90초`
- 루틴 생성 timeout: `90초`
- 전체 요청 deadline: `120초`
- health check timeout: `5초`

`PRIMARY_LLM_API_KEY`가 비어 있으면 `NVIDIA_API_KEY`를 사용합니다.

## 서버 실행

```powershell
cd C:\groom\pc2-smart-mirror-aiot-coaching
uv run --with-requirements requirements.txt python -m uvicorn app.main:app --host 0.0.0.0 --port 7000
```

같은 컴퓨터에서 PC1, PC2, PC3를 모두 띄울 때 PC3는 PC2를 `http://127.0.0.1:7000`으로 보면 됩니다.

물리적으로 분리하면 PC3 `.env`에서 PC2 주소를 아래처럼 바꿉니다.

```env
PC2_COACH_API_URL=http://<PC2_LAN_IP>:7000/api/coach/generate
PC2_ROUTINE_API_URL=http://<PC2_LAN_IP>:7000/api/routine/profile
```

## 운동 지식 적재와 검색

운동 지식 seed는 `data/exercise_knowledge_seed.json`에 있습니다. 최소 75개 chunk로 구성되어 있고, squat, lunge, pushup, jumping_jack, knee_raise를 포함합니다.

처음 DB를 만들었거나 지식을 다시 넣을 때 실행합니다.

```powershell
curl -X POST http://127.0.0.1:7000/api/knowledge/ingest
```

검색 확인:

```powershell
curl "http://127.0.0.1:7000/api/knowledge/search?q=squat%20knee%20pain&exercise=squat"
```

검색 결과에 `score`가 있으면 pgvector 검색이 동작한 것이고, `rerank_logit`이 있으면 NVIDIA rerank까지 동작한 것입니다.

## PC3가 호출하는 API

- `GET /health`
- `POST /api/routine/profile`
- `POST /api/coach/generate`
- `POST /api/knowledge/ingest`
- `GET /api/knowledge/search`

아래 API는 이전 호환과 내부 확인용으로 남아 있을 수 있지만, 현재 사용자 앱 데이터의 원본은 PC3입니다.

- `GET /api/routine/profile/{user_id}/day`
- `GET /api/routine/profile/{user_id}/calendar`
- `POST /api/users/{user_id}/body-metrics`
- `GET /api/users/{user_id}/progress`
- `GET /api/coach/logs/{user_id}`
- `POST /api/workouts/skip`

## 검증

```powershell
uv run --with-requirements requirements.txt python -m compileall app
curl http://127.0.0.1:7000/health
```

health에서 아래를 확인합니다.

- NVIDIA primary LLM 상태
- PostgreSQL 연결 상태
- pgvector 상태
- `knowledge_chunks >= 75`

## 변경 이력

이번 정리 흐름은 [CHANGELOG.md](CHANGELOG.md)에 정리했습니다.
