# PC2 Prompt Contract

이 문서는 현재 `exercise` 전용 PC2 Exercise Planning API의 prompt/payload 계약입니다.

## 입력 계약

PC2는 정확히 하나의 JSON 객체인 `FeaturePayload`만 입력으로 받습니다.

허용 입력:

- `user_id`
- `session_id`
- `mode`
- `event`
- `features.exercise`
- `baseline_diff.exercise`
- `environment`
- `purpose`

지원 운동 타입:

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

금지 입력:

- 원본 이미지 파일
- base64 이미지 문자열
- frame path 또는 local image path
- 영상 파일
- 전체 landmark list
- segmentation mask
- camera stream URL
- `FeaturePayload`에 표현되지 않은 숨은 시각 정보

PC2는 LLM이 이미지를 직접 보지 않는다고 가정합니다. LLM은 PC3가 전달한 운동 feature, baseline_diff, environment, purpose만 사용합니다.

## 출력 계약

PC2는 `CoachingResponse` JSON 객체만 반환해야 합니다.

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

JSON 밖에 Markdown, 설명문, 추가 자연어 문장을 붙이지 않습니다.

## 안전 규칙

PC2 모델은 다음을 하면 안 됩니다.

- 의학적 진단처럼 말하기
- 입력에 없는 사실 추측하기
- 원본 이미지를 봤다고 말하기
- 약물, 치료, 임상 조치 권하기
- 근거 없이 운동 강도를 과도하게 올리기

## 응답 방향

사용 데이터:

- `features.exercise`
- `baseline_diff.exercise`
- 저장된 baseline profile
- 검색된 운동 지식 컨텍스트

응답 초점:

- 현재 운동 기록
- 자세 오류 우선순위
- baseline 대비 변화
- 다음 운동 계획
- PC2 화면 표시용 짧은 메시지

PC3는 `exercise`에서 `session_completed` 시점에만 PC2를 호출합니다.

## Prompt 작성 원칙

PC2 system prompt에는 최소한 다음 원칙을 포함합니다.

```text
너는 스마트미러 운동 계획 API다.
너는 이미지를 직접 보지 않는다.
입력은 PC3가 만든 운동 feature, 저장된 baseline, 검색된 운동 지식뿐이다.
운동 계획은 현재 자세 상태와 baseline 차이를 바탕으로 안전한 범위에서 작성한다.
출력은 CoachingResponse JSON만 허용된다.
입력에 없는 사실 추측은 금지한다.
```
