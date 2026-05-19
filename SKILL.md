# PC2 작업 경계

PC2는 스마트 미러의 NVIDIA/RAG 생성 엔진이다.

```text
PC1 UI -> PC3 Vision Gateway -> PC2 NVIDIA/RAG Engine
```

PC1은 PC2를 직접 호출하지 않는다. PC3만 PC2를 호출한다.

## PC2 책임

- NVIDIA chat API로 루틴 JSON 생성
- NVIDIA chat API로 운동 후 코칭 JSON 생성
- PostgreSQL/pgvector 운동 지식 저장
- seed 운동 지식 ingest
- query embedding, vector search, rerank
- 루틴/코칭 prompt에 evidence 반영
- 사용자에게 보이는 루틴/코칭/근거 요약 한국어 유지
- 코칭 `display_lines` 최소 4줄 유지

## PC2가 원본으로 갖지 않는 것

사용자 앱 데이터의 원본은 PC3다.

- 프로필 원본
- 루틴 플랜 원본
- 날짜별 루틴 원본
- 몸무게 기록 원본
- 운동 결과 원본
- 코칭 로그 원본

PC2에 남아 있는 사용자 관련 API나 테이블은 호환/내부 확인용으로만 본다. 새 흐름에서 PC3는 사용자 원장을 PC2에 맡기지 않는다.

## 주요 API

- `GET /health`
- `POST /api/routine/profile`
- `POST /api/coach/generate`
- `POST /api/knowledge/ingest`
- `GET /api/knowledge/search`

## PostgreSQL/pgvector 기준

운영 기준은 PostgreSQL/pgvector다.

```env
DATABASE_URL=postgresql+psycopg://pc2:pc2_local_pw@127.0.0.1:5432/pc2_smart_mirror
```

로컬 컨테이너 기본값:

- container: `pc2-pgvector`
- db: `pc2_smart_mirror`
- user: `pc2`
- password: `pc2_local_pw`
- volume: `pc2_pgvector_data`

## NVIDIA 기본값

- Chat: `meta/llama-3.3-70b-instruct`
- Embedding: `nvidia/llama-nemotron-embed-1b-v2`
- Rerank: `nvidia/llama-nemotron-rerank-1b-v2`
- Embedding dimensions: `512`
- Vector top K: `30`
- RAG context K: `5`

## 금지

- PC1 직접 호출 경로 추가
- PC3 앱 DB를 PC2로 다시 옮기기
- local fallback으로 성공처럼 꾸미기
- 별도 RAG 서버 추가
- LangChain/LangGraph 추가
- queue, broker, worker 추가
- 로그인, 회원가입, JWT, OAuth, 권한 기능 추가
- 새 smoke/test/mock 파일 생성

## 확인

```powershell
uv run --with-requirements requirements.txt python -m compileall app
curl http://127.0.0.1:7000/health
curl "http://127.0.0.1:7000/api/knowledge/search?q=squat%20knee%20pain&exercise=squat"
```

`/health`에서 PostgreSQL, pgvector, NVIDIA 상태를 확인한다. knowledge ingest 이후에는 `knowledge_chunks >= 75`여야 한다.
