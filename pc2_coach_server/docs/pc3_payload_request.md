# PC3 -> PC2 Exercise Planning Spec

## 목적

PC3는 운동 자세 분석과 feature 추출을 담당합니다.
PC2는 PC3가 보낸 운동 feature, 저장된 baseline, 로컬 검색 컨텍스트를 사용해 LLM 기반 운동 계획표를 생성합니다.

현재 연동은 `exercise` 전용입니다.

지원 운동 타입은 아래 5개입니다.

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

## 호출 순서

1. PC3가 사용자별 baseline 샘플을 모아 PC2에 저장
2. 실제 세션 완료 후 PC3가 현재 분석 결과를 PC2에 전달
3. PC2가 baseline 비교, 검색 컨텍스트 구성, 운동 계획 생성
4. PC2가 결과를 DB에 저장하고 응답 JSON을 PC3에 반환
5. PC3는 응답의 `pc2_payload`를 PC2 화면 또는 미러 메시지에 전달

## Endpoint

### Baseline 저장

```http
POST /api/exercise/baseline
Content-Type: application/json
```

요청 예시:

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
    }
  ]
}
```

### 계획표 생성

```http
POST /api/coach/generate
Content-Type: application/json
```

호출 조건:

- `mode=exercise`
- `event=session_completed`

요청 예시:

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

## 응답 스키마

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
    "display_lines": ["string", "string"]
  }
}
```

## DB 기록 항목

PC2는 아래를 저장합니다.

- 원본 FeaturePayload
- baseline snapshot
- detected signals
- analysis_context
- raw_llm_response
- final_response_json
- pc2_output_json

## 주의사항

- 원본 이미지, 영상, landmark 배열은 보내지 않음
- PC3에서 계산한 수치와 상태값만 전달
- baseline이 없어도 계획 생성은 가능하지만 warning이 추가됨
