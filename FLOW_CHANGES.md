# PC2 흐름 변경 기록

이 문서는 PC2 저장소의 역할, API, 데이터, 런타임 흐름이 어떻게 바뀌었는지 정리한 문서입니다.  
`old_main_docs/FLOW_CHANGES.md`에 남아 있던 예전 `main` 기준 내용도 현재 구조에 맞게 흡수했습니다.

## 2026-05-22 기준 요약

현재 PC2 흐름은 아래 한 줄로 정리할 수 있습니다.

```text
PC1 UI -> PC3 Vision Gateway -> PC2 NVIDIA/RAG Engine -> PostgreSQL/pgvector
```

정리 포인트:

- PC1은 PC2를 직접 호출하지 않습니다.
- PC3가 프로필과 운동 분석 결과를 받아 PC2 API를 호출합니다.
- PC2는 루틴/코칭 생성과 운동 지식 검색을 담당합니다.
- 기존 문서 스냅샷은 `old_main_docs/`에 보관하고, 현재 문서는 새 `main` 기준으로 다시 정리했습니다.

## 브랜치와 문서 기준 변경

### 기존 `main` 아카이브와 새 `main` 승격

- 기존 GitHub `main`은 `main-old`로 분리해 보존했습니다.
- 작업 브랜치 `pc2/rag-gateway-engine`을 새 기준 브랜치 `main`으로 병합했습니다.
- 이 과정에서 루트 문서 `README.md`, `CHANGELOG.md`, `FLOW_CHANGES.md`를 현재 구조 기준으로 다시 작성했습니다.
- 이전 문서 원본은 추적용으로 `old_main_docs/`에 남겨 두었습니다.
- README는 운영 매뉴얼 중심 문서에서 제출/포트폴리오 중심 문서로 재구성해 전체 프로젝트 맥락과 PC2 역할을 먼저 설명하도록 흐름을 바꿨습니다.

## 역할 흐름 변화

### 1. 초기 레거시 흐름

초기 저장소는 단일 PC2 서버 저장소라기보다 워크스페이스 성격이 강했고, 아래 구성과 문서를 함께 관리했습니다.

- `pc2_coach_server/`
- `prompt/`
- 통합 문서
- 발표용/실험용 자료

초기 코칭 생성 흐름은 다음과 같았습니다.

```text
PC3 FeaturePayload
  -> baseline 조회
  -> signal 해석
  -> analysis_context 구성
  -> primary LLM
  -> fallback vLLM
  -> local rule fallback
  -> 코칭 응답 저장 및 반환
```

초기 프로필 루틴 흐름은 다음과 같았습니다.

```text
PC1 profile
  -> PC3
    -> PC2 /api/routine/profile
      -> weekly routine 생성
      -> day detail 확장
      -> DB 저장
      -> PC3
```

이 시기에는 fallback vLLM과 local fallback을 적극 사용해 가능한 한 `200` 응답을 유지하려는 성격이 강했습니다.

### 2. PostgreSQL 기반 루틴 저장 흐름 추가

이후 루틴 생성과 조회 흐름이 저장 중심으로 확장됐습니다.

```text
PC1 profile
  -> PC3
    -> /api/routine/profile
      -> profile_routines 저장
      -> profile_routine_days 저장
      -> scheduled_dates 반환
```

추가된 조회 흐름:

```text
GET /api/routine/profile/{user_id}/day
GET /api/routine/profile/{user_id}/calendar
```

이 단계의 핵심 변화:

- 주간 루틴 외에 날짜별 day 루틴 저장 구조 도입
- body metric, coach log, progress 조회 경로 보강
- PostgreSQL 중심 영속 계층 강화

### 3. 현재 단순화된 PC2 전용 흐름

2026-05-19 이후 현재 구조는 PC2를 PC3의 하위 생성/RAG 엔진으로 단순화한 형태입니다.

```text
PC3 profile or analysis payload
  -> PC2 FastAPI
    -> NVIDIA chat / embedding / rerank
    -> PostgreSQL/pgvector
    -> structured JSON response
  -> PC3
  -> PC1
```

제거되거나 뒤로 물러난 요소:

- `pc2_coach_server/` 중첩 디렉터리
- 발표/통합 문서 중심 구조
- fallback vLLM 운영 기준
- baseline 분석과 signal 분석 중심 설명
- 오래된 smoke 테스트와 보조 실행 문서

남겨진 핵심:

- 프로필 기반 루틴 생성
- 운동 후 코칭 생성
- RAG 지식 적재/검색
- 코칭 로그와 body metric 저장

## API 흐름

### 헬스체크

```text
GET /health
  -> check_primary_llm_health()
  -> database_health()
  -> overall status 계산
```

확인 대상:

- `primary_llm.status`
- `storage.status`
- `service`

### 프로필 루틴 생성

```text
POST /api/routine/profile
  -> generate_profile_routine_response()
  -> NVIDIA primary LLM
  -> 응답 정규화와 검증
  -> weekly_adjustment 계산
  -> scheduled_dates 계산
  -> 결과 반환
```

현재 규칙:

- `available_days_per_week <= 4`
  - `start_date + 0, 2, 4, 6` 형태의 격일 배정
- `available_days_per_week >= 5`
  - 연속 날짜 배정

실패 계약:

- primary LLM 미설정
  - `503`, `detail.reason=primary_llm_unconfigured`
- primary LLM 호출 실패
  - `503`, `detail.reason=primary_llm_call_failed`
- primary LLM 응답 파싱 실패
  - `503`, `detail.reason=primary_llm_parse_failed`

즉 현재 프로필 루틴 경로는 과거와 달리 PC2가 성공처럼 꾸미는 fallback을 만들지 않고, 실패를 실패로 반환합니다.

### 루틴 조회

```text
GET /api/routine/profile/{user_id}/day
GET /api/routine/profile/{user_id}/calendar
  -> 저장된 routine/day record 조회
```

현재 문서 기준으로는 이 조회 경로들이 여전히 API 표면에 존재하며, PC3가 필요 시 중계할 수 있습니다.

### 운동 후 코칭 생성

```text
POST /api/coach/generate
  -> generate_coaching_response()
  -> RAG evidence 검색
  -> NVIDIA chat 응답 생성
  -> 구조 검증
  -> coach_logs 저장
  -> 응답 반환
```

현재 코칭 경로 특징:

- 사용자에게 보이는 코칭은 한국어 기준으로 보정합니다.
- `pc2_payload.display_lines`는 최소 4줄 이상을 보장합니다.
- `pc2_payload.evidence`에 RAG 근거를 포함합니다.

### body metric / progress / skip / logs

```text
POST /api/users/{user_id}/body-metrics
GET /api/users/{user_id}/progress
POST /api/workouts/skip
GET /api/coach/logs/{user_id}
```

이 경로들은 PC2가 보조 데이터를 저장하거나 조회하는 API입니다.

## 데이터 흐름

### 현재 저장 흐름

현재 코드 기준 저장 흐름은 아래처럼 볼 수 있습니다.

```text
coach/generate
  -> coach_logs 저장

body-metrics
  -> body metric 저장

routine/profile/day/calendar
  -> 루틴 관련 저장/조회

knowledge/ingest
  -> knowledge_sources, knowledge_chunks 적재
```

RAG 데이터 흐름:

```text
exercise_knowledge_seed.json
  -> embedding 생성
  -> knowledge_chunks 저장
  -> query embedding
  -> vector search
  -> rerank
  -> prompt evidence
```

## 런타임 흐름

### 초기 레거시 실행 기준

`old_main_docs/README.md` 기준 과거 권장 실행 순서는 아래였습니다.

```text
fallback vLLM Docker
  -> PC2 API
```

이 기준에서는 다음 순서가 중요했습니다.

- primary LLM
- fallback vLLM
- local rule fallback

### 현재 권장 실행 기준

현재 `main` 기준 권장 실행 순서는 아래입니다.

```text
PostgreSQL/pgvector
  -> PC2 FastAPI
  -> knowledge ingest
  -> PC3 연동
```

핵심 차이:

- fallback vLLM은 더 이상 현재 README의 표준 운영 경로가 아닙니다.
- NVIDIA OpenAI-compatible API가 기본 생성 경로입니다.
- PostgreSQL/pgvector를 중심으로 RAG 품질과 근거 관리를 수행합니다.
- `.env`에서 `DATABASE_URL`을 비우면 SQLite fallback이 가능하지만, 권장 기준은 PostgreSQL입니다.

## 문서 이관 메모

- `old_main_docs/README.md`
  - 예전 워크스페이스형 저장소 소개와 fallback vLLM 실행 기준을 담고 있었습니다.
- `old_main_docs/CHANGELOG.md`
  - 2026-05-10부터 2026-05-15까지의 과거 `main` 주요 커밋 이력을 담고 있었습니다.
- `old_main_docs/FLOW_CHANGES.md`
  - baseline, signal, fallback, 루틴 저장 중심의 예전 흐름 설명을 담고 있었습니다.

현재 루트 문서는 위 내용을 그대로 복사하지 않고, 새 `main` 구조와 실제 코드 기준으로 다시 정리한 결과물입니다.
