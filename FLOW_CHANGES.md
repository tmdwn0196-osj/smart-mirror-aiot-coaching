# 흐름 변경 정리

이 문서는 이 저장소의 역할 기준으로 데이터 흐름, API 흐름, 런타임 흐름이 어떻게 바뀌었는지 정리한 파일입니다.
이 저장소는 현재 PC2 중심 저장소이므로 routine 생성, day 조회, coach generate, DB 저장, LLM/fallback 흐름 중심으로 정리합니다.

## 역할

PC2는 두 가지 핵심 경로를 담당합니다.

- 분석 결과 기반 답변 생성
  - PC3가 보낸 운동 분석 결과를 받아 `/api/coach/generate` 응답을 생성
- 프로필 기반 루틴 생성
  - PC1 프로필을 PC3가 중계해 `/api/routine/profile`로 주간 루틴과 날짜별 루틴을 생성

## 데이터 흐름 변경

### 초기 데이터 흐름

초기에는 PC3에서 보낸 `FeaturePayload`를 받아 코칭 응답을 만드는 흐름이 중심이었습니다.

```text
PC3 FeaturePayload
  -> baseline 조회
  -> signal 해석
  -> analysis_context 구성
  -> LLM 응답 생성
  -> 응답 검증
  -> 코칭 응답 반환
```

이 단계의 저장 중심은 다음이었습니다.

- baseline 저장/조회
- coach log 저장

### 프로필 루틴 데이터 흐름 추가

이후 프로필 기반 루틴 생성이 추가되면서 데이터 흐름이 두 갈래로 나뉘었습니다.

```text
PC1 profile
  -> PC3
    -> PC2 /api/routine/profile
      -> 주간 루틴 생성
      -> 응답 검증
      -> DB 저장
      -> PC3
    -> PC1
```

### PostgreSQL 전환 이후 데이터 흐름

현재는 PostgreSQL 중심으로 아래 테이블에 저장됩니다.

- `coach_logs`
  - `/api/coach/generate` 결과
- `exercise_baselines`
  - baseline 저장 결과
- `profile_routines`
  - 주간 루틴 전체
- `profile_routine_days`
  - 날짜별 day 루틴

현재 데이터 흐름은 아래처럼 정리됩니다.

```text
PC3 FeaturePayload
  -> /api/coach/generate
  -> coach_logs 저장

PC3 baseline 요청
  -> /api/exercise/baseline
  -> exercise_baselines 저장

PC1 profile
  -> PC3
    -> /api/routine/profile
      -> profile_routines 저장
      -> profile_routine_days 저장
```

## API 흐름 변경

### 1. 분석 결과 기반 답변 생성

이 경로는 저장소 초기부터 있던 핵심 흐름입니다.

```text
POST /api/coach/generate
```

입력 기준:

- `FeaturePayload`
- `mode=exercise`
- `event=session_completed`

처리 흐름:

```text
PC3 분석 결과
  -> baseline 조회
  -> baseline diff 계산
  -> signal 해석
  -> analysis_context 구성
  -> primary LLM 시도
  -> 실패 시 fallback vLLM
  -> 실패 시 local fallback
  -> final_response 검증
  -> coach_logs 저장
  -> PC3 응답 반환
```

### 2. 프로필 기반 루틴 생성

이 경로는 2026-05-12에 추가되고 2026-05-13에 날짜 기반 저장 구조까지 확장됐습니다.

```text
POST /api/routine/profile
```

입력 기준:

- `RoutineProfileRequest`
- `user_id`
- `user_goal`
- `exercise_experience`
- `available_days_per_week`
- 선택값: `profile_name`, `weight_kg`, `restricted_body_parts`, `purpose`, `start_date`

현재 처리 흐름:

```text
PC1 프로필
  -> PC3
    -> PC2 /api/routine/profile
      -> primary LLM으로 주간 개요 생성
      -> day 1 상세 생성
      -> day 2 상세 생성
      -> ...
      -> weekly_routine 전체 조립
      -> 응답 검증
      -> profile_routines 저장
      -> profile_routine_days 저장
      -> routine_id / start_date / scheduled_dates 포함 응답 반환
```

### 3. 날짜별 루틴 조회

이 경로는 PostgreSQL 전환과 함께 추가됐습니다.

```text
GET /api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD
```

현재 처리 흐름:

```text
PC1 target_date
  -> PC3
    -> PC2 day 조회
      -> profile_routine_days 조회
      -> 메시지 생성
      -> PC3
    -> PC1
```

결과:

- 초기 생성 시 `weekly_routine` 전체를 한 번에 받을 수 있습니다.
- 이후에는 특정 날짜만 따로 재조회할 수 있습니다.

## 런타임 흐름 변경

### 초기 런타임

초기에는 PC2 서버와 fallback vLLM 중심의 런타임 흐름이었습니다.

```text
PC3
  -> PC2 API
    -> primary LLM
    -> fallback vLLM
    -> local fallback
```

### 현재 런타임

현재 권장 런타임 순서는 아래와 같습니다.

```text
PostgreSQL Docker
  -> fallback vLLM Docker
    -> PC2 API
      -> PC3
        -> PC1
```

### 세부 규칙

- `/api/coach/generate`
  - primary LLM 실패 시 fallback vLLM을 시도합니다.
  - fallback vLLM도 실패하면 local rule fallback으로 계속 처리합니다.
  - 즉 이 경로는 LLM이 불안정해도 응답을 유지하는 방향입니다.

- `/api/routine/profile`
  - primary LLM 전용입니다.
  - 설정 누락, 호출 실패, 파싱 실패 시 local fallback 없이 `503`을 반환합니다.

- `restricted_body_parts`
  - 루틴 생성 시 해당 부위 부담이 큰 동작을 피하거나 강도를 낮추는 기준으로 사용합니다.
  - `cautions` 생성에도 반영됩니다.

- `start_date`
  - 루틴 Day 1 시작 날짜 기준입니다.
  - 없으면 서버 기준 오늘 날짜를 사용합니다.

## 현재 기준 요약

현재 저장소의 흐름을 한 줄로 정리하면 아래와 같습니다.

```text
PC3 분석 결과는 /api/coach/generate 로 들어와 코칭 응답과 로그 저장으로 이어지고,
PC1 프로필은 PC3를 거쳐 /api/routine/profile 로 들어와 주간 루틴 생성과 날짜별 루틴 저장/조회 흐름으로 이어집니다.
```

