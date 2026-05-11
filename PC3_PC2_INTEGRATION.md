# PC3 -> PC2 Integration Spec

이 문서는 PC3가 PC2 Exercise Planning API와 연결할 때 필요한 요청 형식, 호출 시점, 응답 활용 방식을 한 번에 정리한 명세서입니다.

## 목적

PC3는 운동 분석을 수행하고 구조화된 운동 feature를 생성합니다.
PC2는 PC3가 보낸 feature, 저장된 baseline, 로컬 운동 지식 검색 결과를 바탕으로 LLM 운동 계획표를 생성합니다.

현재 PC2는 `exercise` 전용입니다.

## 호출 대상

- Baseline 저장: `POST http://<PC2_HOST>:7000/api/exercise/baseline`
- 운동 계획 생성: `POST http://<PC2_HOST>:7000/api/coach/generate`
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

주의:

- 실시간 프레임마다 호출하지 않습니다.
- 실시간 count/state/feedback은 PC3가 직접 처리합니다.

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

- `user_id`: 사용자 ID
- `session_id`: 운동 세션 ID
- `mode`: 항상 `exercise`
- `event`: 항상 `session_completed`
- `features.exercise.type`: 지원 운동 타입 5개 중 하나
- `features.exercise.rep_count` 또는 `count`
- `features.exercise.stability_score`
- `features.exercise.posture_errors`
- `features.exercise.knee_angle`
- `features.exercise.back_angle`
- `features.exercise.duration_sec` 또는 `duration_seconds`
- `features.exercise.tempo`
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
PC3에는 항상 JSON 응답을 반환하며, fallback 모델이 구조화된 계획을 만들지 못하면 아래처럼 한 줄 문장을 담은 최소 `CoachingResponse` 형태로 응답합니다.

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

## 4. PC3에서 응답 활용 방식

### 서버 로직용

- `summary`
- `priority`
- `exercise_plan`
- `warnings`

### 화면 표시용

- `mirror_message`
- `pc2_payload.message`
- `pc2_payload.display_lines`

fallback 한 줄 응답일 때는 `pc2_payload.message`와 `display_lines[0]`이 같은 문장일 수 있습니다.

## 5. 오류 응답 규칙

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

## 6. Python 호출 예시

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

## 7. 연동 체크리스트

- PC2 서버 `/health.status`가 `ok`인지 확인
- `/health.status`가 `degraded`여도 `/health.local_fallback.status=ok`이면 LLM 없이 로컬 fallback으로 계획 생성 가능
- PC3 환경변수에 `PC2_COACH_API_URL` 설정
- baseline 저장 endpoint 먼저 연결
- 계획 생성 endpoint는 세션 종료 시점에만 호출
- `type`이 지원 운동 5개 중 하나인지 확인
- 이미지/비디오/landmark 원본은 보내지 않음
- 계약에 없는 extra field를 보내지 않음
- `environment`는 선택 필드이며, 보낼 경우 `temperature`, `humidity`, `illuminance`만 사용
- `rep_count`와 `count` 중 하나 이상을 보내는 것을 권장
- `duration_sec`와 `duration_seconds` 중 하나를 사용할 수 있음
- PC3 화면 표시는 `pc2_payload.message`를 우선 사용
- 연동 중 문제 확인은 `GET /api/coach/logs/{user_id}?limit=10`으로 조회

## 8. PC3 전달용 요약

PC2는 정상 경로와 fallback 경로 모두에서 항상 `CoachingResponse` JSON을 반환합니다. fallback이 발생해도 raw plain text를 직접 반환하지 않으며, 한 줄 조언만 생성된 경우 그 문장을 `summary`, `priority`, `mirror_message`, `pc2_payload.message`, `pc2_payload.display_lines[0]`에 담아 최소 응답 형태로 내려보냅니다. 이 경우 `exercise_plan`은 빈 배열일 수 있으므로, PC3 화면 표시는 `pc2_payload.message`를 우선 사용하면 됩니다.
