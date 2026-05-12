# PC3 -> PC2 Integration Spec

이 문서는 PC3가 PC2 Coach API와 연결할 때 필요한 요청 형식, 호출 시점, 응답 활용 방식을 한 번에 정리한 명세서입니다.

## 목적

PC3는 운동 분석을 수행하고 구조화된 운동 feature를 생성합니다.
PC2는 PC3가 보낸 feature, 저장된 baseline, 로컬 운동 지식 검색 결과를 바탕으로 LLM 운동 계획표를 생성합니다.
또한 PC1 프론트의 사용자 프로필 값을 PC3가 전달하면 primary LLM으로 주간 루틴 JSON을 생성합니다.

운동 세션 기반 계획 생성은 `exercise` 전용입니다.
프로필 기반 주간 루틴 생성은 별도 endpoint인 `/api/routine/profile`을 사용합니다.

## 호출 대상

- Baseline 저장: `POST http://<PC2_HOST>:7000/api/exercise/baseline`
- 운동 계획 생성: `POST http://<PC2_HOST>:7000/api/coach/generate`
- 프로필 기반 루틴 생성: `POST http://<PC2_HOST>:7000/api/routine/profile`
- Health check: `GET http://<PC2_HOST>:7000/health`
- Debug logs: `GET http://<PC2_HOST>:7000/api/coach/logs/{user_id}?limit=10`

## 호출 시점

### 1. Baseline 저장

사용자별 baseline 샘플이 충분히 모였을 때 호출합니다.

### 2. 운동 계획 생성

운동 세션 종료 시점에 1회 호출합니다.

필수 조건:

- `mode = exercise`
- `event = session_completed`

### 3. 프로필 기반 루틴 생성

PC1 프론트에서 사용자가 프로필을 선택하거나 수정한 뒤, PC3가 해당 프로필 값을 그대로 묶어서 호출합니다.
이 경로는 운동 feature나 baseline 없이도 사용할 수 있으며, primary LLM 기준으로 주간 루틴 JSON을 생성합니다.

주의:

- `/api/coach/generate`의 `mode`, `event`, `features.exercise`를 보내지 않습니다.
- primary LLM이 없거나 실패하면 루틴을 대체 생성하지 않고 `503`으로 실패합니다.
- 실시간 count/state/feedback은 이 endpoint와 무관합니다.

## 지원 운동 타입

`features.exercise.type`과 `exercise_type`에는 아래 5개만 허용됩니다.

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

## 금지 입력

PC3는 아래 데이터를 PC2로 보내지 않습니다.

- 원본 이미지
- base64 이미지
- 비디오 파일
- frame path
- 전체 landmark 배열
- segmentation mask
- camera stream URL

PC2는 PC3가 계산한 수치형/상태형 feature만 받습니다.
현재 PC2 요청 스키마는 계약에 없는 extra field를 허용하지 않습니다.
즉 `landmarks`, `frame_path`뿐 아니라 명세에 없는 어떤 필드라도 들어오면 `422`로 거부됩니다.

## 1. Baseline 저장 요청

### Endpoint

```http
POST /api/exercise/baseline
Content-Type: application/json
```

### JSON 예시

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
      "posture_errors": [],
      "squat_depth": 0.62,
      "knee_angle": 96,
      "back_angle": "neutral",
      "duration_sec": 48,
      "tempo": "controlled"
    },
    {
      "type": "squat",
      "rep_count": 10,
      "stability_score": 0.80,
      "posture_errors": ["knees_in"],
      "squat_depth": 0.60,
      "knee_angle": 98,
      "back_angle": "neutral",
      "duration_sec": 46,
      "tempo": "controlled"
    }
  ]
}
```

## 2. 운동 계획 생성 요청

### Endpoint

```http
POST /api/coach/generate
Content-Type: application/json
```

### 요청 필드

필수:

- `user_id`: 사용자 ID
- `event`: 항상 `session_completed`
- `features.exercise`
- `features.exercise.type`: 지원 운동 타입 5개 중 하나

선택:

- `session_id`: 운동 세션 ID
- `mode`: 생략 시 기본값 `exercise`
- `features.exercise.rep_count` 또는 `count`
- `features.exercise.state`
- `features.exercise.stability_score`
- `features.exercise.posture_errors`
- `features.exercise.squat_depth`
- `features.exercise.knee_angle`
- `features.exercise.back_angle`
- `features.exercise.duration_sec` 또는 `duration_seconds`
- `features.exercise.tempo`
- `baseline_diff.exercise`
- `environment`
- `purpose`

`baseline_diff.exercise`는 PC3가 계산해서 넣어도 되고, 생략해도 됩니다. 생략 시 PC2가 저장된 baseline을 기준으로 내부 계산을 보완합니다.
`environment`는 선택 필드입니다. 생략해도 운동 계획 생성은 가능합니다.

`environment`에 허용되는 필드는 아래 3개입니다.

- `temperature`
- `humidity`
- `illuminance`

낮은 `illuminance`는 응답 `warnings`에 반영될 수 있습니다.
높은 `humidity`는 로그의 `detected_signals`에 저장됩니다.
baseline이 없는 사용자는 계획 생성이 실패하지 않고 `200`으로 처리되며, 응답 `warnings`에 baseline 없음 경고가 포함됩니다.

### JSON 예시

```json
{
  "user_id": "exercise_user",
  "session_id": "sess_exercise_001",
  "mode": "exercise",
  "event": "session_completed",
  "features": {
    "exercise": {
      "type": "squat",
      "count": 8,
      "rep_count": 8,
      "state": "down",
      "stability_score": 0.64,
      "posture_errors": ["knees_caving_in"],
      "squat_depth": 0.49,
      "knee_angle": 118,
      "back_angle": "forward",
      "duration_sec": 42,
      "tempo": "fast"
    }
  },
  "baseline_diff": {
    "exercise": {
      "count_change": -3,
      "stability_change": -0.05
    }
  },
  "environment": {
    "temperature": 24.5,
    "humidity": 48,
    "illuminance": 360
  },
  "purpose": "하체 루틴 자세 점검 후 다음 운동 계획 생성"
}
```

## 3. PC2 응답 형식

### JSON 예시

```json
{
  "summary": "현재 자세 상태와 baseline 차이를 바탕으로 교정 중심 계획을 생성했습니다.",
  "priority": "무릎 정렬 안정화",
  "exercise_plan": [
    {
      "exercise": "tempo squat",
      "sets": 3,
      "reps": 6,
      "duration_sec": null,
      "rest_sec": 90,
      "focus": "하강 3초 유지",
      "reason": "깊이와 무릎 정렬을 동시에 교정하기 좋습니다."
    }
  ],
  "mirror_message": "오늘은 개수보다 자세를 안정적으로 잡는 데 집중하세요!",
  "warnings": [],
  "pc2_payload": {
    "message": "무릎 정렬부터 잡고 천천히 진행하세요.",
    "display_lines": [
      "하강 3초",
      "무릎-발끝 정렬"
    ]
  }
}
```

### 보조 LLM fallback 응답 규칙

fallback 경로에서도 PC2는 raw plain text를 직접 반환하지 않습니다.
PC3에는 항상 JSON 응답을 반환합니다.
현재 구현 기준으로 보조 fallback LLM이 선택되면 응답은 구조화된 계획 대신 아래처럼 한 줄 문장을 담은 최소 `CoachingResponse` 형태로 정규화됩니다.

```json
{
  "summary": "무릎 정렬을 먼저 맞추고 천천히 진행하세요.",
  "priority": "무릎 정렬을 먼저 맞추고 천천히 진행하세요.",
  "exercise_plan": [],
  "mirror_message": "무릎 정렬을 먼저 맞추고 천천히 진행하세요.",
  "warnings": [],
  "pc2_payload": {
    "message": "무릎 정렬을 먼저 맞추고 천천히 진행하세요.",
    "display_lines": [
      "무릎 정렬을 먼저 맞추고 천천히 진행하세요."
    ]
  }
}
```

즉 PC3는 항상 JSON으로 받고, fallback 시에는 `pc2_payload.message`의 한 줄 문장을 우선 사용하면 됩니다.

LLM 설정이 없거나 LLM 호출이 실패해도 PC2는 로컬 규칙 기반 fallback으로 응답을 생성할 수 있습니다.
이 경우 `/health.status`는 `degraded`일 수 있지만, `/health.local_fallback.status`가 `ok`이면 PC2의 기본 운동 계획 생성 경로는 사용할 수 있습니다.
로컬 규칙 기반 fallback은 보조 fallback LLM과 다르게 보통 `exercise_plan`을 포함한 계획 응답을 반환합니다.

## 4. 프로필 기반 루틴 생성 요청

### Endpoint

```http
POST /api/routine/profile
Content-Type: application/json
```

이 endpoint는 primary LLM 전용입니다.
primary LLM이 설정되지 않았거나 호출/응답 파싱에 실패하면 로컬 fallback 루틴을 생성하지 않고 `503`으로 실패를 반환합니다.

### 요청 필드

- `user_id`: 사용자 ID
- `profile_name`: 화면 표시 이름, 선택
- `weight_kg`: 체중, 선택
- `user_goal`: 사용자 목표
- `exercise_experience`: 운동 경험
- `available_days_per_week`: 주당 운동 가능 횟수, 1~7
- `restricted_body_parts`: 제한 부위 배열, 없으면 `[]`
- `purpose`: 호출 목적, 선택

### JSON 예시

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

### 응답 예시

```json
{
  "summary": "운동 습관 형성을 위한 주간 루틴입니다.",
  "weekly_focus": "주 5회 리듬 유지와 전신 밸런스 확보",
  "weekly_routine": [
    {
      "day_index": 1,
      "day_label": "Day 1",
      "focus": "하체와 코어",
      "exercises": [
        {
          "exercise": "goblet squat",
          "sets": 4,
          "reps": 10,
          "duration_sec": null,
          "rest_sec": 75,
          "focus": "하체 안정성",
          "reason": "기초 하체 근력 유지에 적합합니다."
        }
      ]
    }
  ],
  "cautions": [],
  "pc3_payload": {
    "summary": "운동 습관 형성을 위한 주간 루틴입니다.",
    "weekly_focus": "주 5회 리듬 유지와 전신 밸런스 확보",
    "available_days_per_week": 5,
    "restricted_body_parts": [],
    "weekly_routine": [
      {
        "day_index": 1,
        "day_label": "Day 1",
        "focus": "하체와 코어",
        "exercises": [
          {
            "exercise": "goblet squat",
            "sets": 4,
            "reps": 10,
            "duration_sec": null,
            "rest_sec": 75,
            "focus": "하체 안정성",
            "reason": "기초 하체 근력 유지에 적합합니다."
          }
        ]
      }
    ]
  }
}
```

PC3는 이 응답에서 `pc3_payload`를 그대로 프론트에 넘기거나, `summary`, `weekly_focus`, `weekly_routine`, `cautions`만 골라서 가공해도 됩니다.
현재 이 endpoint는 `/api/coach/logs/{user_id}` 조회 대상이 아니며, 성공/실패 사유는 PC2 서버 로그에 남습니다.

### 실패 응답 예시

```json
{
  "detail": {
    "message": "루틴 생성에 실패했습니다.",
    "reason": "primary_llm_call_failed"
  }
}
```

가능한 `reason`:

- `primary_llm_unconfigured`
- `primary_llm_call_failed`
- `primary_llm_parse_failed`

## 5. PC3에서 응답 활용 방식

### 운동 계획 응답

서버 로직용:

- `summary`
- `priority`
- `exercise_plan`
- `warnings`

화면 표시용:

- `mirror_message`
- `pc2_payload.message`
- `pc2_payload.display_lines`

fallback 한 줄 응답일 때는 `pc2_payload.message`와 `display_lines[0]`이 같은 문장일 수 있습니다.
로컬 규칙 기반 fallback 응답일 때는 `exercise_plan`이 비어 있지 않을 수 있습니다.

### 프로필 루틴 응답

PC3는 `pc3_payload`를 프론트에 그대로 전달할 수 있습니다.
필요하면 아래 top-level 필드만 골라 가공해도 됩니다.

- `summary`
- `weekly_focus`
- `weekly_routine`
- `cautions`

프로필 루틴 생성은 primary LLM 전용이므로 실패 시 `CoachingResponse` fallback이 아니라 `503` 오류 JSON을 받습니다.

## 6. 오류 응답 규칙

PC3 요청이 계약과 맞지 않으면 PC2는 `422 Unprocessable Entity`를 반환합니다.

대표적인 `422` 조건:

- `event`가 `session_completed`가 아님
- `features.exercise` 누락
- `features.exercise.type` 누락
- `features.exercise.type`이 지원 운동 5개 중 하나가 아님
- `exercise_type`과 baseline `samples[*].type`이 다름
- 계약에 없는 extra field 포함

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

위 요청은 `landmarks`가 계약에 없는 필드이므로 `422 extra_forbidden`으로 거부됩니다.

성공한 `/api/coach/generate` 요청은 coach log에 저장됩니다.
요청 검증 단계에서 거부된 `422` 요청은 coach log에 남지 않을 수 있습니다.

## 7. Python 호출 예시

```python
import requests

pc2_url = "http://<PC2_HOST>:7000/api/coach/generate"

payload = {
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
    "purpose": "운동 계획 생성"
}

resp = requests.post(pc2_url, json=payload, timeout=30)
resp.raise_for_status()
result = resp.json()
```

## 8. 연동 체크리스트

- PC2 서버 `/health.status`가 `ok`인지 확인
- `/health.status`가 `degraded`여도 `/health.local_fallback.status=ok`이면 LLM 없이 로컬 fallback으로 계획 생성 가능
- PC3 환경변수에 `PC2_COACH_API_URL` 설정
- 프로필 루틴용 연결값은 `/api/routine/profile`을 별도로 설정
- baseline 저장 endpoint 먼저 연결
- 계획 생성 endpoint는 세션 종료 시점에만 호출
- 프로필 루틴 생성 endpoint는 PC1 사용자 프로필 값이 확정된 시점에 호출
- `type`이 지원 운동 5개 중 하나인지 확인
- 이미지/비디오/landmark 원본은 보내지 않음
- 계약에 없는 extra field를 보내지 않음
- `environment`는 선택 필드이며, 보낼 경우 `temperature`, `humidity`, `illuminance`만 사용
- `rep_count`와 `count` 중 하나 이상을 보내는 것을 권장
- `duration_sec`와 `duration_seconds` 중 하나를 사용할 수 있음
- PC3 화면 표시는 `pc2_payload.message`를 우선 사용
- 프로필 루틴 생성 실패 시 `503 detail.reason`을 확인하고 사용자에게 루틴 생성 실패로 표시
- 연동 중 문제 확인은 `GET /api/coach/logs/{user_id}?limit=10`으로 조회
- 같은 `user_id + session_id`가 재전송되면 coach log에 `is_duplicate_session=true`와 `duplicate_of_request_id`가 기록됨

## 9. PC3 전달용 요약

PC2는 정상 경로와 fallback 경로 모두에서 항상 `CoachingResponse` JSON을 반환합니다. fallback이 발생해도 raw plain text를 직접 반환하지 않으며, 한 줄 조언만 생성된 경우 그 문장을 `summary`, `priority`, `mirror_message`, `pc2_payload.message`, `pc2_payload.display_lines[0]`에 담아 최소 응답 형태로 내려보냅니다. 이 경우 `exercise_plan`은 빈 배열일 수 있으므로, PC3 화면 표시는 `pc2_payload.message`를 우선 사용하면 됩니다.
반대로 로컬 규칙 기반 fallback에서는 `exercise_plan`이 포함된 계획 응답이 반환될 수 있습니다.

프로필 기반 루틴 생성은 `/api/routine/profile`로 분리되어 있습니다.
이 endpoint는 primary LLM만 사용하며, 실패하면 `503`과 `detail.reason`을 반환합니다.
