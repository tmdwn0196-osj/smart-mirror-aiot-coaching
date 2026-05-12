# PC2 Coach API
PC2는 PC3 Vision Gateway가 계산한 운동 feature를 입력으로 받아, 저장된 baseline과 로컬 운동 지식 검색 결과를 함께 사용해 LLM 기반 운동 계획표를 생성하는 FastAPI 서버입니다.
PC1 프론트의 사용자 프로필 값을 PC3가 전달하면 primary LLM으로 주간 루틴 JSON도 생성합니다.

운동 세션 기반 계획 생성은 `exercise` 전용입니다.
프로필 기반 주간 루틴 생성은 별도 endpoint인 `/api/routine/profile`에서 처리합니다.

지원 운동 타입은 아래 5개로 제한됩니다.

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

## 처리 흐름

```text
PC3 -> PC2 Coach API

FeaturePayload
  -> 저장된 운동 baseline
  -> 로컬 운동 지식 검색
  -> 프롬프트 구성
  -> NVIDIA Gemma 4 31B IT
  -> 출력 검증
  -> 코칭 응답
```

PC3는 운동 분석 결과를 `FeaturePayload` JSON으로 보내고, PC2는:

1. 사용자별 최신 baseline 조회
2. 현재 feature와 baseline 차이 계산
3. 로컬 지식 검색 기반 분석 컨텍스트 구성
4. primary LLM 호출 후 실패 시 fallback vLLM, 그마저 실패하면 로컬 규칙 fallback으로 운동 계획표 생성
5. 결과와 근거를 DB에 기록
6. PC3와 PC2 화면용 payload를 함께 반환

프로필 기반 루틴 생성은 `RoutineProfileRequest` JSON으로 받고, 운동 feature나 baseline 없이 primary LLM 응답을 `RoutineProfileResponse` JSON으로 반환합니다.
이 경로는 로컬 규칙 기반 fallback을 사용하지 않습니다.

문서 기준본은 [docs/README.md](/home/osj/smart-mirror-aiot-coaching/pc2_coach_server/docs/README.md:1) 를 참고합니다.

## 실행 방법

기본 기준은 `fallback vLLM Docker + PC2 API`를 함께 올리는 전체 실행입니다.

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
cp .env.example .env
docker compose -f docker-compose.vllm.yml up -d
./scripts/run_pc2.sh
```

- 환경변수 파일은 `pc2_coach_server/.env`를 우선 로드합니다.
- `.env`가 없어도 실행은 가능하며, 이 경우 기본값과 로컬 규칙 기반 대체 경로를 사용합니다.
- 서비스 기준 템플릿은 `pc2_coach_server/.env.example`입니다.
- 표준 `.env.example`은 `FALLBACK_LLM_ENABLED=true` 기준입니다.

실행 포트:

- `7000`: PC2 API
- `8000`: fallback vLLM Docker
- fallback vLLM 모델: `Qwen/Qwen2.5-1.5B-Instruct-AWQ`

확인 명령:

```bash
curl http://127.0.0.1:7000/health
curl http://127.0.0.1:8000/v1/models
```

직접 실행 명령:

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 7000
```

주의:

- `/api/coach/generate`의 표준 호출 순서는 `primary LLM -> fallback vLLM -> local rule fallback`입니다.
- `/api/routine/profile`은 primary LLM 전용입니다. 즉 Docker로 띄운 fallback vLLM이 아니라 `PRIMARY_LLM_*` 설정을 사용합니다.

## API

### 1. Baseline 저장

```text
POST /api/exercise/baseline
Content-Type: application/json
```

예시:

```json
{
  "user_id": "exercise_user",
  "exercise_type": "squat",
  "purpose": "하체 루틴 baseline 생성",
  "samples": [
    {
      "type": "squat",
      "rep_count": 12,
      "stability_score": 0.82,
      "squat_depth": 0.62,
      "knee_angle": 96,
      "back_angle": "neutral",
      "duration_sec": 48,
      "tempo": "controlled"
    }
  ]
}
```

제약:

- `samples`는 최소 1개 이상이어야 합니다.
- `samples[*].type`이 있으면 `exercise_type`과 같아야 합니다.

### 2. 최신 baseline 조회

```text
GET /api/exercise/baseline/{user_id}?exercise_type=squat
```

### 3. 운동 계획표 생성

```text
POST /api/coach/generate
Content-Type: application/json
```

허용 규칙:

| mode | event | 처리 |
| --- | --- | --- |
| `exercise` | `session_completed` | 허용 |

예시:

```json
{
  "user_id": "exercise_user",
  "session_id": "sess_exercise_001",
  "mode": "exercise",
  "event": "session_completed",
  "features": {
    "exercise": {
      "type": "squat",
      "rep_count": 8,
      "stability_score": 0.64,
      "posture_errors": ["knees_caving_in"],
      "squat_depth": 0.49,
      "knee_angle": 118,
      "back_angle": "forward",
      "duration_sec": 42,
      "tempo": "fast"
    }
  },
  "purpose": "하체 루틴 자세 점검 후 다음 운동 계획 생성"
}
```

제약:

- `mode`는 `exercise`만 허용합니다.
- `event`는 `session_completed`만 허용합니다.
- `features.exercise`와 `features.exercise.type`은 필수입니다.
- `user_id`는 필수입니다.
- 그 외 `features.exercise` 세부 필드와 `baseline_diff.exercise`, `environment`, `purpose`는 선택입니다.

응답 스키마:

```json
{
  "summary": "string",
  "priority": "string",
  "exercise_plan": [
    {
      "exercise": "string",
      "sets": 3,
      "reps": 8,
      "duration_sec": null,
      "rest_sec": 60,
      "focus": "string",
      "reason": "string"
    }
  ],
  "mirror_message": "string",
  "warnings": ["string"],
  "pc2_payload": {
    "message": "string",
    "display_lines": ["string"]
  }
}
```

fallback 동작:

- PC2는 fallback 시에도 raw plain text를 직접 반환하지 않습니다.
- 항상 `CoachingResponse` JSON을 유지합니다.
- 보조 fallback LLM이 사용되면 `exercise_plan`은 빈 배열이며, `pc2_payload.message`에 한 줄 문장이 들어갑니다.
- 로컬 규칙 기반 fallback이 사용되면 보통 `exercise_plan`이 포함된 계획 응답을 반환합니다.

### 4. 프로필 기반 주간 루틴 생성

```text
POST /api/routine/profile
Content-Type: application/json
```

요청 예시:

```json
{
  "user_id": "exercise_user",
  "profile_name": "양하준",
  "weight_kg": 65,
  "user_goal": "운동 습관 만들기",
  "exercise_experience": "꾸준히 운동함",
  "available_days_per_week": 5,
  "restricted_body_parts": [],
  "purpose": "프로필 기반 주간 루틴 추천"
}
```

필수:

- `user_id`
- `user_goal`
- `exercise_experience`
- `available_days_per_week`

선택:

- `profile_name`
- `weight_kg`
- `restricted_body_parts` (`[]` 권장)
- `purpose`

응답 스키마:

```json
{
  "summary": "string",
  "weekly_focus": "string",
  "weekly_routine": [
    {
      "day_index": 1,
      "day_label": "Day 1",
      "focus": "string",
      "exercises": []
    }
  ],
  "cautions": ["string"],
  "pc3_payload": {}
}
```

실패 정책:

- primary LLM이 설정되지 않았으면 `503`과 `reason=primary_llm_unconfigured` 반환
- primary LLM 호출 실패 시 `503`과 `reason=primary_llm_call_failed` 반환
- primary LLM 응답 파싱 실패 시 `503`과 `reason=primary_llm_parse_failed` 반환
- 이 endpoint는 로컬 fallback 루틴을 생성하지 않음

## 로그 조회

```text
GET /api/coach/logs/{user_id}?limit=10
```

- `limit`는 `1` 이상 `100` 이하만 허용합니다.

`/api/coach/generate` 성공 요청은 DB에 아래 항목으로 저장됩니다.
`/api/routine/profile`은 현재 coach log DB에 저장하지 않고 서버 로그에 성공/실패 사유만 남깁니다.

- PC3 입력 payload
- 감지 신호
- baseline 스냅샷
- 검색된 분석 컨텍스트
- LLM 프롬프트
- 원본 LLM 응답
- 최종 운동 계획 응답
- PC2 화면 전달용 payload
- `is_duplicate_session`, `duplicate_of_request_id`

같은 `user_id + session_id`가 다시 들어오면 요청은 차단하지 않고 계속 처리합니다.
대신 최신 coach log에 `is_duplicate_session=true`가 기록되고, 최초 요청의 `request_id`가 `duplicate_of_request_id`에 저장됩니다.

## 점검 테스트

기본 테스트:

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
../.venv/bin/python -m unittest -q
```

개별 테스트 모듈:

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
../.venv/bin/python -m unittest tests.test_api -q
```

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
../.venv/bin/python scripts/smoke_pc2.py --base-url http://127.0.0.1:7000
```
