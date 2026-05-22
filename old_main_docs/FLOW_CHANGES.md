# 흐름 변경 정리

이 문서는 이 저장소의 역할 기준으로 데이터 흐름, API 흐름, 런타임 흐름이 어떻게 바뀌었는지 정리한 파일입니다.
이 저장소는 현재 PC2 중심 저장소이므로 routine 생성, day 조회, coach generate, DB 저장, LLM/fallback 흐름 중심으로 정리합니다.

## 역할

PC2는 두 가지 핵심 경로를 담당합니다.

- 분석 결과 기반 답변 생성
  - PC3가 보낸 운동 분석 결과를 받아 `/api/coach/generate` 응답을 생성
- 프로필 기반 루틴 생성
  - PC1 프로필을 PC3가 중계해 `/api/routine/profile`로 주간 루틴과 날짜별 루틴을 생성

## 2026-05-15 16:32:41 +09:00 - 프로필 루틴 실패 계약 복원

이번 변경에서는 `/api/routine/profile`의 실패 책임을 다시 PC3 쪽으로 분리할 수 있게 PC2 동작을 문서 계약에 맞춰 되돌렸습니다.

변경 전 흐름:

```text
PC1 profile
  -> PC3
    -> PC2 /api/routine/profile
      -> primary LLM 미설정 또는 실패
      -> PC2 local fallback routine 생성
      -> 200 응답
    -> PC1
```

변경 후 흐름:

```text
PC1 profile
  -> PC3
    -> PC2 /api/routine/profile
      -> primary LLM 미설정
         -> 503 detail.reason=primary_llm_unconfigured
      -> 또는 primary LLM 호출 실패
         -> 503 detail.reason=primary_llm_call_failed
      -> 또는 primary LLM 응답 파싱 실패
         -> 503 detail.reason=primary_llm_parse_failed
    -> PC3가 fallback owner로서 기본 루틴 또는 실패 UX 처리
```

정리 포인트:

- PC2는 프로필 루틴 생성 성공 또는 실패만 반환합니다.
- PC2는 `/api/routine/profile` 실패 시 로컬 fallback 루틴을 저장하거나 반환하지 않습니다.
- 프로필 루틴 저장과 `profile_routine_days` 저장은 primary LLM 결과 파싱이 성공한 경우에만 진행됩니다.
- PC3는 `503`을 보고 자기 저장소 기준 fallback 루틴 또는 사용자 안내를 처리할 수 있습니다.

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

현재 primary 기본 모델은 NVIDIA hosted `mistralai/mistral-nemotron`입니다.

### 세부 규칙

- `/api/coach/generate`
  - primary LLM 실패 시 fallback vLLM을 시도합니다.
  - fallback vLLM도 실패하면 local rule fallback으로 계속 처리합니다.
  - 즉 이 경로는 LLM이 불안정해도 응답을 유지하는 방향입니다.

- `/api/routine/profile`
  - primary LLM을 먼저 사용합니다.
  - 주간 루틴 본문 생성이 실패하면 local rule fallback으로 전체 weekly routine을 생성합니다.
  - day 상세 확장은 전체 요청 deadline 안에서 남은 시간을 계산해 추가 시도하고, 실패한 day는 기존 outline을 유지합니다.
  - 즉 이 경로도 이제는 provider 장애나 파싱 실패가 있어도 가능한 한 응답을 유지하는 방향으로 바뀌었습니다.

- timeout 흐름
  - `/api/coach/generate`의 primary 호출은 `PRIMARY_LLM_TIMEOUT_SECONDS`를 기준으로 동작합니다.
  - `/api/routine/profile`의 주간 루틴 생성은 `ROUTINE_PROFILE_TIMEOUT_SECONDS`와 전체 `REQUEST_DEADLINE_SECONDS` 안에서 동작합니다.
  - day 상세 생성은 각 day마다 `ROUTINE_DAY_DETAIL_TIMEOUT_SECONDS`와 남은 전체 deadline 중 더 작은 값을 사용합니다.
  - health 확인은 `LLM_HEALTH_TIMEOUT_SECONDS` 기준으로 `/models`를 조회합니다.

- provider 장애 처리
  - provider `/models` health가 `ok`여도 실제 inference 함수가 `DEGRADED` 상태면 generate 호출이 실패할 수 있습니다.
  - 현재 코드는 이 경우 local fallback으로 내려가도록 되어 있어 API 레벨에서는 `200` 응답을 유지할 수 있습니다.
  - `reasoning_content`만 있고 최종 `content`가 없는 응답은 structured JSON 경로에서 즉시 실패로 판정합니다.

- `restricted_body_parts`
  - 루틴 생성 시 해당 부위 부담이 큰 동작을 피하거나 강도를 낮추는 기준으로 사용합니다.
  - `cautions` 생성에도 반영됩니다.

- `start_date`
  - 루틴 Day 1 시작 날짜 기준입니다.
  - 없으면 서버 기준 오늘 날짜를 사용합니다.

## 최근 최적화

### 2026-05-14T17:20:39+09:00 `0cb6bcb`

`fix(pc2): 프로필 루틴 응답 정규화`

이번 변경에서는 프로필 루틴 day 응답이 약간 흔들려도 가능한 한 계약에 맞춰 흡수하도록 흐름을 조정했습니다.

- `routine/profile` day detail
  - `exercises`가 단일 객체로 와도 배열로 정규화합니다.
  - `day_index`가 요청값과 다르면 요청값으로 맞춰 둡니다.
  - `day_label`과 `focus`가 비어 있으면 fallback day 값을 우선 사용합니다.

### 2026-05-14T16:53:49+09:00 `1899741`

`feat(pc2): 코치 응답 형식 고정 강화`

이번 변경에서는 `coach/generate`의 응답 형식을 더 강하게 고정했습니다.

- `coach/generate`
  - prompt에 허용 key, 필수 key, 금지 출력, item 구조를 더 명시했습니다.
  - fallback 응답도 먼저 JSON 파싱을 시도하도록 바꿔서 구조화 응답 가능성을 높였습니다.
  - JSON이 아니면 최후 수단으로만 평문 fallback을 사용합니다.

### 2026-05-14T15:24:26+09:00 `ba3662e`

`feat(pc2): 프롬프트 압축과 루틴 호출량 최적화`

이번 변경에서는 응답 계약 자체보다 prompt와 반복 호출량을 줄이는 쪽으로 흐름을 다듬었습니다.

- `coach/generate`
  - 입력 분석에 필요한 핵심 변수는 유지했습니다.
  - prompt 예시와 중복 설명을 줄여 토큰 수를 낮췄습니다.
  - `features.exercise`, `baseline_diff`, `analysis_context` 중심 구조는 그대로 유지합니다.

- `routine/profile`
  - 주간 루틴 본문 생성은 그대로 유지합니다.
  - day-detail 확장은 첫 1일까지만 수행해 추가 LLM 호출 수를 줄였습니다.
  - 응답이 실패하더라도 local fallback JSON을 유지하는 정책은 그대로 둡니다.

- signal 압축
  - prompt로 넘기기 전에 signal summary를 더 짧게 압축합니다.
  - baseline, latest routine, signal preview는 유지하되 길이만 줄였습니다.
  - 의미를 바꾸는 변수명은 그대로 두고, 설명성 텍스트만 압축했습니다.

## 현재 기준 요약

현재 저장소의 흐름을 한 줄로 정리하면 아래와 같습니다.

```text
PC3 분석 결과는 /api/coach/generate 로 들어와 코칭 응답과 로그 저장으로 이어지고,
PC1 프로필은 PC3를 거쳐 /api/routine/profile 로 들어와 주간 루틴 생성과 날짜별 루틴 저장/조회 흐름으로 이어집니다.
```
