# PC2 변경 이력

이 문서는 `git log`와 현재 작업 내용을 기준으로 PC2가 어떻게 바뀌었는지 정리합니다.

## 2026-05-20

### 루틴 날짜 배정 정책 변경

- `app/services.py`의 루틴 생성 응답에서 `pc3_payload.scheduled_dates` 계산 규칙을 조정했습니다.
- `available_days_per_week`가 4 이하일 때는 연속 날짜 대신 하루 휴식을 둔 격일 배정으로 날짜를 만듭니다.
- `available_days_per_week`가 5 이상일 때는 기존처럼 연속 날짜 배정을 유지합니다.
- 응답 키 구조와 필드명은 유지하고 `scheduled_dates` 값만 바꿨습니다.

## 2026-05-19

### 역할 재정리

- PC2를 PC3가 호출하는 NVIDIA/RAG 생성 엔진으로 정리했습니다.
- PC1은 PC2를 직접 호출하지 않습니다.
- 사용자 프로필, 루틴, 달력, 몸무게, 운동 결과, 코칭 로그의 원본은 PC3로 넘겼습니다.
- PC2 PostgreSQL/pgvector는 운동 지식 검색과 생성 근거를 위한 저장소로 사용합니다.

### 구조 단순화

- 예전 `pc2_coach_server/` 중첩 구조를 제거하고 루트의 `app/` 기준 단일 FastAPI 앱으로 정리했습니다.
- WebSocket, baseline 분석, signal 분석, local rule fallback, fallback vLLM, 오래된 smoke/test 문서와 복잡한 실행 경로를 제거했습니다.
- 새 서버, queue, worker, LangChain, LangGraph 없이 PC2 내부 함수로만 RAG와 생성 흐름을 처리합니다.

### PostgreSQL/pgvector RAG

- Docker `pgvector/pgvector:pg16` 기준으로 로컬 DB 설정을 맞췄습니다.
- `knowledge_sources`, `knowledge_chunks`에 운동 지식을 저장합니다.
- seed 운동 지식은 75개 이상이며 아래 운동을 포함합니다.
  - squat
  - lunge
  - pushup
  - jumping_jack
  - knee_raise
- 요청 시 query embedding, vector search, rerank를 거쳐 top evidence를 prompt에 넣습니다.

### NVIDIA 호출

- chat model 기본값을 `meta/llama-3.3-70b-instruct`로 맞췄습니다.
- embedding/rerank 모델과 API URL을 `.env.example`에 정리했습니다.
- timeout은 primary/routine 90초, 전체 요청 120초 기준으로 정리했습니다.

### 한국어 루틴/코칭

- 사용자에게 보이는 루틴, 코칭, 근거 요약은 한국어로 나오도록 prompt와 validator를 강화했습니다.
- 영어 응답이 섞이면 같은 JSON 구조로 한국어 재요청을 시도합니다.
- 운동 후 코칭은 `pc2_payload.display_lines` 최소 4줄 이상을 보장합니다.
- `pc2_payload.evidence`에 RAG 근거를 포함합니다.

### 주간 조절

- 최근 기록과 몸무게 흐름을 받아 주간 조절값을 만들 수 있게 했습니다.
- `increase`, `decrease`, `hold`, `hold_or_decrease` 방향과 이유를 루틴 응답의 `weekly_adjustment`에 포함합니다.
- 판단은 PC2 내부 규칙 함수로 처리하고, NVIDIA는 그 판단을 반영해 문장을 구성합니다.

## 최근 커밋 흐름

- `docs: 프로필 루틴 503 계약 복원 흐름 기록`
  - 실패를 성공처럼 숨기지 않는 계약을 문서화했습니다.
- `fix(pc2): 프로필 루틴 실패 시 503 계약 복원`
  - PC2 루틴 생성 실패가 명확히 실패로 전달되도록 맞췄습니다.
- `fix(pc2): 프로필 루틴 응답 정규화`
  - PC3가 읽을 수 있는 루틴 응답 형태로 정규화했습니다.
- `feat(pc2): 코치 응답 형식 고정 강화`
  - 코칭 응답 shape와 표시 필드를 더 안정적으로 맞췄습니다.
- `feat(pc2): 프롬프트 압축과 루틴 호출량 최적화`
  - NVIDIA 호출 prompt를 줄이고 루틴 생성 부담을 낮췄습니다.

## 현재 확인 기준

- PostgreSQL/pgvector 컨테이너가 떠 있어야 합니다.
- `/health`에서 primary LLM, PostgreSQL, pgvector 상태를 확인합니다.
- `POST /api/knowledge/ingest` 후 `knowledge_chunks >= 75`여야 합니다.
- `GET /api/knowledge/search` 결과에 `score`, `rerank_logit`이 있어야 합니다.
- `.env`, 로그, DB 파일은 커밋하지 않습니다.
