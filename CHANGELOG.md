# PC2 변경 이력

이 문서는 현재 `main` 기준 PC2 저장소의 변경 이력을 정리한 파일입니다.  
`old_main_docs/CHANGELOG.md`에 남아 있던 기존 `main` 문서 기록도 현재 문서에 흡수했습니다.

## 2026-05-22

### 브랜치 기준 재정리

- 기존 GitHub `main` 브랜치는 `main-old`로 이동해 보존했습니다.
- 작업 브랜치였던 `pc2/rag-gateway-engine`을 현재 기준 브랜치 `main`으로 승격해 병합했습니다.
- 병합 결과 현재 `main` HEAD는 `6c08d0c`이며, 병합 커밋 메시지는 `merge: pc2/rag-gateway-engine into main`입니다.
- 문서 이전 기준 스냅샷은 `old_main_docs/`에 보존했습니다.

### 문서 갱신

- 루트 `README.md`, `CHANGELOG.md`, `FLOW_CHANGES.md`를 현재 PC2 구조 기준으로 재작성했습니다.
- `old_main_docs/README.md`, `old_main_docs/CHANGELOG.md`, `old_main_docs/FLOW_CHANGES.md`의 내용을 현재 역할과 실행 구조에 맞게 흡수했습니다.
- README 상단에 이 저장소가 PC2 전용임을 명시하고 PC1, PC3 리포 주소를 적을 수 있는 자리 표시자를 추가했습니다.
- README를 제출/포트폴리오용 형식으로 재정리해 프로젝트 소개, 문제 정의, 내 역할, 핵심 성과, 아키텍처, 실행 방법이 앞에서 바로 보이도록 구성했습니다.
- PC1 리포와 PC3 리포의 실제 GitHub 주소를 README 상단에 반영했습니다.
- README에서 중복되는 핵심 성과 섹션과 저수준 로깅 설정 노출을 줄여 제출용 문서 톤에 맞게 간소화했습니다.

### 로깅 설정 보강

- `logging.yaml`을 추가해 Uvicorn 기본 로그와 access 로그 포맷을 분리했습니다.
- `requirements.txt`에 `PyYAML`을 추가했습니다.

## 2026-05-20

### 루틴 날짜 배정 정책 변경

- `app/services.py`의 루틴 생성 응답에서 `pc3_payload.scheduled_dates` 계산 규칙을 조정했습니다.
- `available_days_per_week`가 4 이하일 때는 연속 날짜 대신 하루 휴식을 둔 격일 배정을 사용합니다.
- `available_days_per_week`가 5 이상일 때는 기존처럼 연속 날짜 배정을 유지합니다.
- 응답 키 구조와 필드명은 유지하고 `scheduled_dates` 값만 변경했습니다.

## 2026-05-19

### 역할 재정리

- PC2를 PC3가 호출하는 NVIDIA/RAG 생성 엔진으로 재정의했습니다.
- PC1은 PC2를 직접 호출하지 않도록 구조를 고정했습니다.
- 사용자 프로필, 루틴, 달력, 몸무게, 운동 결과, 코칭 로그의 원본 책임을 PC3 쪽으로 명확히 분리했습니다.
- PC2 PostgreSQL/pgvector는 운동 지식 검색과 생성 근거 보강용 저장소로 사용합니다.

### 구조 단순화

- 예전 `pc2_coach_server/` 중첩 구조를 제거하고 루트 `app/` 기준 단일 FastAPI 앱으로 정리했습니다.
- 오래된 통합 문서, 발표 자료, 보조 스크립트, 테스트 아티팩트, 예전 서버 디렉터리를 정리했습니다.
- WebSocket, baseline 분석, signal 분석, fallback vLLM 중심 구조 대신 단순한 NVIDIA/RAG 엔진 구조로 전환했습니다.

### PostgreSQL/pgvector RAG 정비

- Docker `pgvector/pgvector:pg16` 기준으로 로컬 DB 기준을 맞췄습니다.
- `knowledge_sources`, `knowledge_chunks`에 운동 지식을 저장하는 흐름으로 정리했습니다.
- seed 운동 지식은 75개 이상 chunk를 포함하며 `squat`, `lunge`, `pushup`, `jumping_jack`, `knee_raise`를 포함합니다.
- query embedding, vector search, rerank를 거쳐 evidence를 prompt에 주입하는 구조를 정리했습니다.

### NVIDIA 호출 기준 정리

- chat model 기본값을 `meta/llama-3.3-70b-instruct`로 맞췄습니다.
- embedding, rerank 모델과 API URL을 `.env.example`에 정리했습니다.
- timeout 기준을 `PRIMARY_LLM_TIMEOUT_SECONDS=90`, `ROUTINE_PROFILE_TIMEOUT_SECONDS=90`, `REQUEST_DEADLINE_SECONDS=120`으로 정리했습니다.

### 한국어 출력과 weekly adjustment 보강

- 루틴, 코칭, 근거 요약이 사용자 표시 기준 한국어로 나오도록 prompt와 validator를 강화했습니다.
- 영어 응답이 섞이면 같은 JSON 구조로 한국어 재요청을 시도하도록 보강했습니다.
- 운동 후 코칭은 `pc2_payload.display_lines` 최소 4줄 이상을 보장합니다.
- 루틴 응답의 `weekly_adjustment`에 `increase`, `decrease`, `hold`, `hold_or_decrease` 방향과 이유를 담도록 보강했습니다.

## 2026-05-15

### 프로필 루틴 실패 시 503 계약 복원

- `/api/routine/profile`에서 primary LLM 미설정 시 local fallback 루틴을 만들지 않고 `503`과 `detail.reason=primary_llm_unconfigured`를 반환하도록 정리했습니다.
- primary LLM 호출 실패는 `detail.reason=primary_llm_call_failed`, 응답 파싱 실패는 `detail.reason=primary_llm_parse_failed`로 구분했습니다.
- 프로필 루틴 관련 테스트 기대값도 이 계약에 맞춰 수정했습니다.

## 2026-05-14

### 프로필 루틴 응답 정규화

- 프로필 루틴 day 응답에서 `exercises`가 단일 객체로 와도 1개짜리 배열로 흡수하도록 정규화했습니다.
- day detail 응답의 `day_index`가 요청값과 다를 때 요청값으로 맞추도록 정리했습니다.
- 계약을 조금 벗어나더라도 즉시 fallback으로 버리지 않도록 검증을 완화했습니다.

### 코치 응답 형식 고정 강화

- `coach/generate`의 system/user prompt에 JSON 계약과 금지 규칙을 더 강하게 명시했습니다.
- fallback 응답도 먼저 JSON 파싱을 시도하고, 구조화 응답으로 처리할 수 있으면 우선 사용하도록 바꿨습니다.
- JSON이 아닌 응답만 최후 수단으로 평문 fallback 처리하도록 정리했습니다.

### 프롬프트 압축과 루틴 호출량 최적화

- `routine/profile`의 day-detail 확장을 첫 1일까지만 수행하도록 줄였습니다.
- `compact_for_prompt()`에서 prompt 문맥을 더 압축했습니다.
- `coach/generate`, `routine/profile` prompt를 줄이되 핵심 입력 변수는 유지했습니다.

## 2026-05-13

### 문서 이력 구조 정비

- 루트 `CHANGELOG.md`, `FLOW_CHANGES.md`를 Git 이력 기준으로 재구성했습니다.
- 날짜 기반 정리와 흐름 기반 정리를 분리했습니다.
- 문서 규칙 파일과 연동 문서를 보강했습니다.

### 날짜 기반 루틴 저장 구조 추가

- PostgreSQL 중심 구조로 전환했습니다.
- PostgreSQL Docker 구성을 추가하고 기본 포트를 정리했습니다.
- 주간 루틴 외에 날짜별 day 루틴 저장 구조를 추가했습니다.
- `GET /api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD` 조회 경로를 추가했습니다.

## 2026-05-12

### 프로필 루틴 생성과 저장 보강

- `POST /api/routine/profile` 기반 프로필 루틴 생성 기능을 도입했습니다.
- 루틴 저장 로직과 운동 타입 제한 반영을 추가했습니다.
- 루틴 생성 타임아웃 기본값을 상향했습니다.
- 프로필 루틴 응답 파서를 더 엄격하게 정리했습니다.

### 실행/문서 정합성 정리

- fallback vLLM 기준 문서와 환경 예시를 정리했습니다.
- 실행 설정과 문서 예시의 어긋남을 줄이도록 문서를 정비했습니다.
- 스모크 테스트, 환경 예시, 셀프 테스트 자료를 보강했습니다.

## 2026-05-10

### 초기 저장소와 LLM 안정화

- PC2 Coach API 초기 저장소를 구성했습니다.
- FastAPI 서버, DB 계층, LLM 호출 계층, 프롬프트 계층, 신호 해석 계층, 문서, 실행 스크립트, 테스트를 포함한 기본 구조를 추가했습니다.
- LLM 응답 파싱 안정성과 fallback 흐름을 보강했습니다.

## 문서 이관 메모

- 과거 `main` 기준 상세 문서 원본은 `old_main_docs/`에 보관했습니다.
- 현재 문서는 그 기록을 단순 복사하지 않고, 현재 `main` 구조와 코드 기준으로 재정리한 버전입니다.
