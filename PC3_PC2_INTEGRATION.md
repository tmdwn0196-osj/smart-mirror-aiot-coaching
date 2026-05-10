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
- `features.exercise.duration_sec`
- `features.exercise.tempo`
- `environment`
- `purpose`

`baseline_diff.exercise`는 PC3가 계산해서 넣어도 되고, 생략해도 됩니다. 생략 시 PC2가 저장된 baseline을 기준으로 내부 계산을 보완합니다.

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

## 5. Python 호출 예시

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

## 6. 연동 체크리스트

- PC2 서버 `/health`가 `ok`인지 확인
- PC3 환경변수에 `PC2_COACH_API_URL` 설정
- baseline 저장 endpoint 먼저 연결
- 계획 생성 endpoint는 세션 종료 시점에만 호출
- `type`이 지원 운동 5개 중 하나인지 확인
- 이미지/비디오/landmark 원본은 보내지 않음
