# 흐름 변경 정리

이 문서는 이 저장소의 주요 데이터 흐름, API 흐름, 런타임 흐름 변화를 한글로 정리한 파일입니다.
현재 로컬 Git 이력을 기준으로 흐름 변화를 단계별로 재구성했습니다.

## 1. 초기 흐름

초기 저장소의 중심 흐름은 PC3가 만든 운동 분석 결과를 PC2가 받아 코칭 응답을 생성하는 구조였습니다.

```text
PC3 운동 분석 결과
  -> PC2 /api/coach/generate
  -> baseline 조회
  -> signal 해석
  -> 로컬 지식 기반 analysis_context 구성
  -> LLM 응답 생성
  -> 결과 검증
  -> 코칭 응답 반환
```

초기부터 다음 흐름이 포함돼 있었습니다.

- baseline 저장/조회
- 운동 세션 기반 코칭 응답 생성
- fallback vLLM 경로
- local rule fallback 경로

## 2. 코칭 응답 흐름 안정화

초기 이후 가장 먼저 정리된 흐름은 `/api/coach/generate` 안정화였습니다.

### 변경점

- raw LLM 응답 파싱 실패 시 더 안전한 fallback 경로를 타도록 정리했습니다.
- 코칭 응답을 항상 JSON 형태로 유지하는 방향으로 강화했습니다.
- baseline이 없거나 외부 LLM이 실패해도 local fallback으로 응답을 계속 만들 수 있게 했습니다.

### 결과 흐름

```text
PC3 FeaturePayload
  -> baseline 조회
  -> baseline diff 계산
  -> signal 해석
  -> analysis_context 구성
  -> primary LLM 시도
    -> 실패 시 fallback vLLM 시도
      -> 실패 시 local rule fallback
  -> final_response 검증
  -> coach_logs 저장
  -> PC3 응답 반환
```

## 3. 프로필 기반 루틴 생성 흐름 추가

이후 저장소는 운동 세션 기반 응답 생성 외에, PC1 프로필 기반 주간 루틴 생성 흐름을 추가했습니다.

### 새로 추가된 API 흐름

```text
PC1
  -> PC3
    -> PC2 /api/routine/profile
      -> primary LLM
      -> 주간 루틴 응답 생성
      -> PC3
    -> PC1
```

### 특징

- 입력은 `RoutineProfileRequest`
- 출력은 `RoutineProfileResponse`
- 이 경로는 local fallback 없이 primary LLM 전용
- 실패 시 `503`

이 단계에서는 다음 흐름이 생겼습니다.

- PC1 프로필 값 전달
- PC3 passthrough
- 주간 루틴 JSON 생성
- 루틴 응답 검증

## 4. 루틴 저장과 검증 흐름 강화

프로필 루틴 기능이 붙은 뒤에는 “응답만 생성”하는 구조에서 “생성 결과를 저장하고 재사용”하는 구조로 확장됐습니다.

### 변경점

- 루틴 저장 로직 추가
- 허용 운동 타입 제한 반영
- 타임아웃 상향
- 루틴 응답 검증 강화

### 결과 흐름

```text
프로필 요청
  -> 주간 루틴 생성
  -> 응답 구조 검증
  -> 허용 운동 타입 검증
  -> DB 저장
  -> PC3 응답 반환
```

이 단계에서는 아직 주간 루틴이 중심이었고, 날짜별 조회 흐름은 없었습니다.

## 5. PostgreSQL 중심 흐름으로 전환

이후 저장소의 가장 큰 구조 변화는 SQLite 중심 흐름에서 PostgreSQL 중심 흐름으로 전환한 것입니다.

### 변경 전

```text
PC2
  -> SQLite 파일 저장
```

### 변경 후

```text
PC2
  -> PostgreSQL
    -> coach_logs
    -> exercise_baselines
    -> profile_routines
    -> profile_routine_days
```

### 영향

- 데이터 저장 위치가 파일 중심에서 서버형 DB 중심으로 이동했습니다.
- 연동 테스트와 운영 기준이 PostgreSQL Docker 기반으로 정리됐습니다.
- DB 흐름이 날짜 기반 루틴 저장 구조를 수용할 수 있게 바뀌었습니다.

## 6. 날짜 기반 루틴 흐름 추가

PostgreSQL 전환과 함께 루틴 생성 흐름은 “주간 루틴 1회 생성”에서 “주간 개요 + day별 상세 + 날짜 저장” 구조로 확장됐습니다.

### 현재 루틴 생성 흐름

```text
PC1 프로필
  -> PC3
    -> PC2 /api/routine/profile
      -> primary LLM으로 주간 개요 생성
      -> day 1 상세 생성
      -> day 2 상세 생성
      -> ...
      -> weekly_routine 전체 조립
      -> profile_routines 저장
      -> profile_routine_days 날짜별 저장
      -> routine_id / start_date / scheduled_dates 포함 응답 반환
```

### 새로 추가된 조회 흐름

```text
PC1 target_date
  -> PC3
    -> PC2 /api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD
      -> profile_routine_days 조회
      -> 오늘의 루틴 메시지 생성
      -> PC3
    -> PC1
```

### 결과

- 초기 생성 시 `1일차~N일차` 전체를 한 번에 내려줄 수 있습니다.
- 이후에는 특정 날짜만 따로 재조회할 수 있습니다.

## 7. 현재 데이터 흐름

현재 기준 주요 저장 테이블과 흐름은 아래와 같습니다.

### 운동 세션 기반 코칭

```text
PC3 FeaturePayload
  -> /api/coach/generate
  -> coach_logs 저장
```

저장 내용:

- 원본 요청
- baseline 스냅샷
- analysis_context
- raw LLM 응답
- 최종 코칭 응답

### baseline

```text
PC3 baseline 요청
  -> /api/exercise/baseline
  -> exercise_baselines 저장
```

### 프로필 루틴

```text
PC1 profile
  -> PC3
    -> /api/routine/profile
      -> profile_routines 저장
      -> profile_routine_days 저장
```

## 8. 현재 API 흐름

### 분석 결과 기반 답변 생성

```text
POST /api/coach/generate
```

- 입력: `FeaturePayload`
- 기준: `mode=exercise`, `event=session_completed`
- fallback 허용

### 프로필 기반 루틴 생성

```text
POST /api/routine/profile
```

- 입력: `RoutineProfileRequest`
- primary LLM 전용
- `weekly_routine` 전체 반환

### 날짜별 루틴 조회

```text
GET /api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD
```

- 입력: `user_id`, `target_date`
- 출력: 특정 날짜의 day 루틴 + 메시지

## 9. 현재 런타임 흐름

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
  - primary LLM이 실패해도 fallback vLLM 또는 local fallback으로 계속 처리 가능

- `/api/routine/profile`
  - primary LLM 설정, 호출, 파싱이 정상이어야 함
  - 실패 시 대체 생성 없이 `503`

- PC1은 PC2를 직접 호출하지 않고 PC3를 통해 중계합니다.
- PC3는 PC2 응답에서 필요한 메타를 꺼내 PC1용 형식으로 다시 전달할 수 있습니다.

