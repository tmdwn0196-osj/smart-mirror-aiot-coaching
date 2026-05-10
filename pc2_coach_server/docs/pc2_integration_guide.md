# PC2 연결 가이드

이 문서는 현재 `exercise` 전용 PC2 Exercise Planning API를 PC3 Vision Gateway에 연결할 때 필요한 endpoint, payload, 응답 규칙을 정리합니다.

## 연결 방향

```text
PC1 -> PC3 Vision Gateway -> PC2 Exercise Planning API
```

PC2는 PC3에서 전달하는 운동 `FeaturePayload`만 받아 운동 계획표 JSON을 생성합니다.
PC2는 저장된 baseline과 로컬 운동 지식 검색 결과를 함께 사용합니다.

## Endpoint

```http
POST /api/coach/generate
Content-Type: application/json
```

PC3 설정:

```env
PC2_COACH_API_URL=http://<PC2_HOST>:7000/api/coach/generate
```

## Runtime

PC2 내부 구조:

```text
Coach API
  -> Baseline Lookup
  -> Signal Detection
  -> Local Knowledge Retrieval
  -> Prompt Manager
  -> NVIDIA Gemma 4 31B IT
  -> Output Validator
```

## 입력: FeaturePayload

PC2는 원본 이미지를 받지 않습니다. 입력은 반드시 `FeaturePayload` JSON 하나입니다.

지원 운동 타입:

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

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
      "rep_count": 12,
      "stability_score": 0.64,
      "posture_errors": ["knees_caving_in"],
      "squat_depth": 0.49,
      "knee_angle": 118,
      "back_angle": "forward",
      "duration_sec": 46,
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
  "purpose": "하체 루틴 자세 점검"
}
```

금지 입력:

- raw image file
- base64 image
- frame path
- video path
- full landmark list
- segmentation mask
- camera stream URL

## 출력: CoachingResponse

PC2는 반드시 `CoachingResponse` JSON만 반환합니다.

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
  "warnings": [
    "조도가 낮아 비전 feature 신뢰도가 낮을 수 있습니다."
  ],
  "pc2_payload": {
    "message": "무릎 정렬부터 잡고 천천히 진행하세요.",
    "display_lines": [
      "하강 3초",
      "무릎-발끝 정렬"
    ]
  }
}
```

## PC2 호출 시점

| mode | event | PC2 호출 여부 |
| --- | --- | --- |
| `exercise` | `session_completed` | 호출 |

운동 실시간 count/state/feedback은 PC3가 직접 처리합니다. PC2는 세션 종료 후 최종 계획 생성만 담당합니다.
