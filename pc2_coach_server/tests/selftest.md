# PC2 Self Test

이 문서는 PC3 없이 PC2 서버만 단독으로 검증할 때 사용하는 self-test 절차입니다.

대상:

- `pc2_coach_server/app/main.py`
- `pc2_coach_server/app/services.py`
- `pc2_coach_server/app/db.py`
- `pc2_coach_server/scripts/smoke_pc2.py`
- `pc2_coach_server/tests/test_api.py`

## 1. 목적

PC2가 다음을 정상 처리하는지 확인한다.

- 서버 기동
- health check
- baseline 저장
- 운동 계획 생성
- fallback 처리
- 프로필 기반 루틴 생성의 primary LLM 전용 실패 처리
- 로그 저장
- 입력 검증 실패 처리

PC3는 사용하지 않는다. PC3가 보낼 JSON을 직접 PC2에 POST해서 검증한다.

## 2. 사전 조건

- Python 실행 환경이 준비되어 있어야 한다.
- SQLite 파일을 생성할 수 있어야 한다.
- 포트 `7000`을 사용할 수 있어야 한다.

권장 실행 위치:

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
```

## 3. 서버 실행

```bash
../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 7000
```

서버 프로세스는 켜 둔 상태에서, 아래 `curl` 명령은 다른 터미널에서 실행한다.

health 확인:

```bash
curl http://127.0.0.1:7000/health
```

기대 결과:

- `status`가 `ok` 또는 `degraded`
- `service`가 `pc2-coach-api`
- `local_fallback.status`는 `ok`

## 4. baseline 저장 테스트

### 요청

```bash
curl -X POST http://127.0.0.1:7000/api/exercise/baseline \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"exercise_user",
    "exercise_type":"squat",
    "purpose":"하체 루틴 baseline 생성",
    "samples":[
      {
        "type":"squat",
        "rep_count":12,
        "stability_score":0.82,
        "posture_errors":[],
        "squat_depth":0.62,
        "knee_angle":96,
        "back_angle":"neutral",
        "duration_sec":48,
        "tempo":"controlled"
      },
      {
        "type":"squat",
        "rep_count":10,
        "stability_score":0.80,
        "posture_errors":["knees_in"],
        "squat_depth":0.60,
        "knee_angle":98,
        "back_angle":"neutral",
        "duration_sec":46,
        "tempo":"controlled"
      }
    ]
  }'
```

기대 결과:

- `baseline_id`가 생성된다.
- `exercise_type`이 `squat`로 내려온다.
- `baseline_profile.recommended_reps` 같은 집계값이 포함된다.

## 5. 운동 계획 생성 테스트

### 요청

```bash
curl -X POST http://127.0.0.1:7000/api/coach/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"exercise_user",
    "session_id":"sess_exercise_001",
    "mode":"exercise",
    "event":"session_completed",
    "features":{
      "exercise":{
        "type":"squat",
        "count":8,
        "rep_count":8,
        "stability_score":0.64,
        "posture_errors":["knees_caving_in"],
        "squat_depth":0.49,
        "knee_angle":118,
        "back_angle":"forward",
        "duration_sec":42,
        "tempo":"fast"
      }
    },
    "environment":{
      "temperature":24.5,
      "humidity":48,
      "illuminance":360
    },
    "purpose":"하체 루틴 자세 점검 후 다음 운동 계획 생성"
  }'
```

기대 결과:

- `summary`, `priority`, `mirror_message`가 반환된다.
- primary LLM 또는 로컬 규칙 fallback 경로에서는 보통 `exercise_plan`이 1개 이상 반환된다.
- fallback LLM이 한 줄 조언만 만든 경우에는 `exercise_plan`이 빈 배열일 수 있다.
- `pc2_payload.message`가 존재한다.
- `warnings`에 조도나 baseline 관련 경고가 들어갈 수 있다.

## 6. 로그 확인 테스트

계획 생성 후 로그를 확인한다.

```bash
curl http://127.0.0.1:7000/api/coach/logs/exercise_user?limit=10
```

기대 결과:

- 최신 요청이 `logs[0]`에 들어간다.
- `detected_signals`, `analysis_context`, `baseline_snapshot`, `pc2_output`, `final_response`가 저장된다.
- `llm_route`, `fallback_used`, `primary_error`가 함께 기록될 수 있다.

## 7. fallback 테스트

LLM이 없어도 PC2는 동작해야 한다.

확인 포인트:

- `PRIMARY_LLM_API_KEY`가 비어 있어도 서버가 뜬다.
- 외부 LLM 호출 실패 시 로컬 규칙 기반 계획으로 전환된다.
- 응답 형식은 계속 `CoachingResponse` JSON이다.

기대 결과 예시:

- `exercise_plan`이 비어 있어도 된다.
- `pc2_payload.message`에 한 줄 한국어 조언이 들어갈 수 있다.
- `warnings`에 fallback 관련 문구가 들어갈 수 있다.

## 8. 입력 검증 실패 테스트

### 8-1. 잘못된 event

```bash
curl -X POST http://127.0.0.1:7000/api/coach/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"exercise_user",
    "session_id":"sess_exercise_002",
    "mode":"exercise",
    "event":"frame_update",
    "features":{
      "exercise":{
        "type":"squat",
        "rep_count":8
      }
    }
  }'
```

기대 결과:

- `422` 응답
- HTTP 요청에서는 Pydantic 스키마 검증이 먼저 실행되므로, `detail`에 `session_completed` 허용값 또는 `event` 검증 오류가 포함된다.

### 8-2. exercise payload 누락

```bash
curl -X POST http://127.0.0.1:7000/api/coach/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"exercise_user",
    "session_id":"sess_exercise_003",
    "mode":"exercise",
    "event":"session_completed"
  }'
```

기대 결과:

- `422` 응답
- `features.exercise`가 필요하다는 메시지

### 8-3. baseline sample type 불일치

```bash
curl -X POST http://127.0.0.1:7000/api/exercise/baseline \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"exercise_user",
    "exercise_type":"squat",
    "samples":[
      {
        "type":"pushup",
        "rep_count":10
      }
    ]
  }'
```

기대 결과:

- `422` 응답
- `samples.type`이 `exercise_type`과 일치해야 한다는 메시지

## 9. 자동화 테스트

유닛 테스트는 서버를 켜지 않아도 실행할 수 있다.

```bash
../.venv/bin/python -m unittest -q
```

개별 테스트도 서버를 켜지 않아도 실행할 수 있다.

```bash
../.venv/bin/python -m unittest tests.test_api -q
```

스모크 테스트는 실행 중인 PC2 서버가 필요하다.

```bash
../.venv/bin/python scripts/smoke_pc2.py --base-url http://127.0.0.1:7000
```

현재 스모크 스크립트는 아래까지 자동으로 확인한다.

- `/health`에서 `status`와 `local_fallback.status`
- baseline 저장
- PC3 mock payload 기준 계획 생성
- 같은 `session_id` 재전송 시 로그의 `is_duplicate_session`, `duplicate_of_request_id`
- 계약 밖 extra field 전송 시 `422`

현재 스모크 스크립트는 `/api/routine/profile` 성공 경로를 자동 검증하지 않는다.
이 endpoint는 primary LLM 전용이므로, `PRIMARY_LLM_API_KEY`가 없으면 `503` 실패가 정상 동작이다.

## 10. 테스트 우선순위

권장 순서:

1. `python -m unittest -q`
2. PC2 서버 실행
3. `GET /health`
4. `POST /api/exercise/baseline`
5. `POST /api/coach/generate`
6. `GET /api/coach/logs/{user_id}`
7. `scripts/smoke_pc2.py`

## 11. 판정 기준

다음이 모두 만족되면 PC2 단독 self-test는 통과로 본다.

- 서버가 정상 기동한다.
- baseline 저장이 된다.
- 운동 계획 생성이 JSON으로 반환된다.
- LLM 설정 유무와 관계없이 응답 형식이 깨지지 않는다.
- 로그가 DB에 저장된다.
- 잘못된 입력은 422로 거부된다.

## 12. PC3 연결 전 확장 점검

PC3을 바로 연결할 수 없을 때는 PC3가 보낼 가능성이 있는 payload 변형을 PC2에 직접 넣어본다.

확장 점검 목적:

- 지원 운동 5종 전체가 `200`으로 처리되는지 확인
- baseline이 없는 사용자도 계획 생성이 가능한지 확인
- PC3가 `baseline_diff`를 보내거나 생략해도 처리되는지 확인
- PC3가 `count`만 보내거나 `duration_seconds`만 보내도 처리되는지 확인
- 환경값에 따라 warning이 생기는지 확인
- 잘못된 운동 타입과 불필요한 extra field가 `422`로 거부되는지 확인

### 12-1. 지원 운동 5종 generate

각 운동 타입별로 `features.exercise.type`만 바꿔서 호출한다.

기대 결과:

- `squat`, `jumping_jack`, `knee_raise`, `lunge`, `pushup` 모두 `200`
- 응답은 항상 `CoachingResponse` JSON
- `pc2_payload.message`가 비어 있지 않아야 한다.

점검 대상:

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

### 12-2. baseline 없는 신규 사용자

baseline을 저장하지 않은 `user_id`로 `/api/coach/generate`를 호출한다.

기대 결과:

- `200`
- `warnings`에 baseline이 없다는 경고가 포함된다.
- `exercise_plan` 또는 `pc2_payload.message`가 생성된다.

### 12-3. baseline_diff 포함/생략 비교

같은 사용자와 같은 운동 payload로 아래 두 가지를 비교한다.

- `baseline_diff` 생략
- `baseline_diff.exercise.count_change`, `stability_change` 포함

기대 결과:

- 둘 다 `200`
- `baseline_diff`를 생략하면 PC2가 저장된 baseline 기준으로 내부 계산을 보완한다.
- `baseline_diff`를 포함하면 입력값을 우선 사용하고 비어 있는 항목만 PC2가 보완한다.

### 12-4. count-only payload

PC3가 `rep_count` 대신 `count`만 보내는 상황을 확인한다.

기대 결과:

- `200`
- 반복 수 관련 신호가 감지된다.
- 응답 형식이 깨지지 않는다.

### 12-5. duration_seconds-only payload

PC3가 `duration_sec` 대신 `duration_seconds`만 보내는 상황을 확인한다.

기대 결과:

- `200`
- 지속 시간 관련 신호가 감지된다.
- 응답 형식이 깨지지 않는다.

### 12-6. environment warning

낮은 조도와 높은 습도를 넣어서 경고 처리 여부를 확인한다.

예시:

```json
{
  "environment": {
    "illuminance": 80,
    "humidity": 82
  }
}
```

기대 결과:

- `200`
- 낮은 조도 warning이 포함된다.
- 습도 신호가 `detected_signals`에 저장된다.

현재 응답 `warnings`에는 조도와 baseline 관련 경고만 직접 반영된다. 습도는 로그의 `detected_signals`에서 확인한다.

### 12-7. 잘못된 운동 타입

지원하지 않는 운동 타입을 보낸다.

예시:

```json
{
  "features": {
    "exercise": {
      "type": "burpee"
    }
  }
}
```

기대 결과:

- `422`
- `type` 필드의 literal 검증 오류가 반환된다.

### 12-8. extra field 거부

PC3가 계약에 없는 필드를 추가로 보내는 상황을 확인한다.

예시:

```json
{
  "features": {
    "exercise": {
      "type": "squat",
      "rep_count": 8,
      "landmarks": []
    }
  }
}
```

기대 결과:

- `422`
- `extra_forbidden` 또는 extra field 관련 오류가 반환된다.

현재 PC2 스키마는 `extra="forbid"`다. 즉 PC3가 문서에 없는 필드를 보내면 PC2는 의도적으로 거부한다.

### 12-9. 로그 추적성

확장 점검 후 로그를 확인한다.

```bash
curl 'http://127.0.0.1:7000/api/coach/logs/exercise_user?limit=10'
```

기대 결과:

- 성공한 generate 요청은 로그에 남는다.
- 실패한 `422` 요청은 FastAPI 요청 검증 단계에서 거부되므로 coach log에는 남지 않을 수 있다.
- 성공 로그에는 `detected_signals`, `analysis_context`, `baseline_snapshot`, `pc2_output`, `final_response`, `llm_route`가 포함된다.

### 12-10. PC3 연결 시 최종 확인값

PC3 쪽 연결값은 아래 형식을 기준으로 한다.

```env
PC2_COACH_API_URL=http://<PC2_HOST>:7000/api/coach/generate
```

PC3 연결 직전 확인할 내용:

- PC3에서 PC2 host와 port로 접근 가능한지
- PC3가 `session_completed` 시점에만 호출하는지
- PC3가 원본 이미지, base64, landmark 배열, frame path를 보내지 않는지
- PC3가 `Content-Type: application/json`으로 요청하는지
- PC3가 fallback 상황에서도 `pc2_payload.message`를 우선 표시하는지

### 12-11. 프로필 기반 루틴 생성

PC1 프론트의 사용자 프로필 값을 PC3가 전달하는 흐름을 확인한다.

```bash
curl -X POST http://127.0.0.1:7000/api/routine/profile \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id":"exercise_user",
    "profile_name":"양하준",
    "weight_kg":65,
    "user_goal":"운동 습관 만들기",
    "exercise_experience":"꾸준히 운동함",
    "available_days_per_week":5,
    "restricted_body_parts":[],
    "purpose":"프로필 기반 주간 루틴 추천"
  }'
```

기대 결과:

- primary LLM이 설정되어 있고 응답 파싱에 성공하면 `200`
- 응답은 `RoutineProfileResponse` JSON
- `pc3_payload`는 PC3가 프론트에 그대로 넘길 수 있음
- primary LLM 미설정이면 `503`과 `reason=primary_llm_unconfigured`
- primary LLM 호출 실패 시 `503`과 `reason=primary_llm_call_failed`
- primary LLM 응답 파싱 실패 시 `503`과 `reason=primary_llm_parse_failed`
- 이 endpoint는 로컬 fallback 루틴을 생성하지 않음
- 이 endpoint는 현재 coach log DB에 저장하지 않고 서버 로그에 성공/실패 사유만 남김
