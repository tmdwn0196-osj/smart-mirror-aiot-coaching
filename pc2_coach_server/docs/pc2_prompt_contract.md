# PC2 프롬프트 계약

이 문서는 PC2 Coach API의 prompt/payload 계약입니다.
운동 세션 기반 계획 생성은 `FeaturePayload`, 프로필 기반 주간 루틴 생성은 `RoutineProfileRequest`를 사용합니다.

## 운동 계획 입력 계약

`/api/coach/generate`는 정확히 하나의 JSON 객체인 `FeaturePayload`만 입력으로 받습니다.

허용 입력:

- `user_id`
- `session_id`
- `mode`
- `event`
- `features.exercise`
- `baseline_diff.exercise`
- `environment`
- `purpose`

필수 입력:

- `user_id`
- `event`
- `features.exercise`
- `features.exercise.type`

선택 입력:

- `session_id`
- `mode` (`exercise` 기본값)
- `baseline_diff.exercise`
- `environment`
- `purpose`
- `features.exercise` 내부 세부 측정값들

지원 운동 타입:

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

금지 입력:

- 원본 이미지 파일
- base64 이미지 문자열
- frame 경로 또는 local image 경로
- 영상 파일
- 전체 landmark list
- segmentation mask
- camera stream URL
- `FeaturePayload`에 표현되지 않은 숨은 시각 정보

PC2는 LLM이 이미지를 직접 보지 않는다고 가정합니다. LLM은 PC3가 전달한 운동 feature, baseline_diff, environment, purpose만 사용합니다.

## 프로필 루틴 입력 계약

`/api/routine/profile`은 정확히 하나의 JSON 객체인 `RoutineProfileRequest`만 입력으로 받습니다.
이 입력은 PC1 프론트의 사용자 정보가 PC3를 거쳐 전달된 값입니다.

허용 입력:

- `user_id`
- `profile_name`
- `weight_kg`
- `user_goal`
- `exercise_experience`
- `available_days_per_week`
- `restricted_body_parts`
- `purpose`

필수 입력:

- `user_id`
- `user_goal`
- `exercise_experience`
- `available_days_per_week`

선택 입력:

- `profile_name`
- `weight_kg`
- `restricted_body_parts`
- `purpose`

사용 데이터:

- 사용자 목표
- 운동 경험
- 주당 운동 가능 횟수
- 제한 부위
- 선택 입력으로 전달된 이름, 체중, 목적

금지 입력:

- `features.exercise`
- `baseline_diff.exercise`
- 원본 이미지, 영상, landmark 배열
- 입력에 없는 건강 상태나 질병 정보 추측

프로필 루틴 생성은 primary LLM 전용입니다.
primary LLM 미설정, 호출 실패, 응답 파싱 실패 시 API는 `503`을 반환하고 로컬 fallback 루틴을 생성하지 않습니다.

## 운동 계획 출력 계약

`/api/coach/generate`는 `CoachingResponse` JSON 객체만 반환해야 합니다.

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

JSON 바깥에 Markdown, 설명문, 추가 자연어 문장을 붙이지 않습니다.

fallback 경로에서도 raw plain text를 직접 반환하지 않습니다.
현재 구현 기준으로 fallback LLM 응답은 구조화된 계획을 유지하지 않고, 한 줄 조언을 `CoachingResponse` 최소 형태에 담아 반환합니다.
로컬 규칙 기반 fallback 응답은 이와 다르게 `exercise_plan`을 포함한 계획 형태를 유지할 수 있습니다.

## 프로필 루틴 출력 계약

`/api/routine/profile`은 `RoutineProfileResponse` JSON 객체만 반환해야 합니다.

```json
{
  "summary": "string",
  "weekly_focus": "string",
  "weekly_routine": [
    {
      "day_index": 1,
      "day_label": "Day 1",
      "focus": "string",
      "exercises": [
        {
          "exercise": "string",
          "sets": 3,
          "reps": 8,
          "duration_sec": null,
          "rest_sec": 60,
          "focus": "string",
          "reason": "string"
        }
      ]
    }
  ],
  "cautions": ["string"],
  "pc3_payload": {}
}
```

JSON 바깥에 Markdown, 설명문, 추가 자연어 문장을 붙이지 않습니다.
`pc3_payload`에는 PC3가 프론트에 그대로 전달할 수 있는 루틴 표시용 값을 담습니다.

## 안전 규칙

PC2 모델은 다음을 하면 안 됩니다.

- 의학적 진단처럼 말하기
- 입력에 없는 사실 추측하기
- 원본 이미지를 봤다고 말하기
- 약물, 치료, 임상 조치 권하기
- 근거 없이 운동 강도를 과도하게 올리기

## 응답 방향

운동 계획 사용 데이터:

- `features.exercise`
- `baseline_diff.exercise`
- 저장된 baseline profile
- 검색된 운동 지식 컨텍스트

운동 계획 응답 초점:

- 현재 운동 기록
- 자세 오류 우선순위
- baseline 대비 변화
- 다음 운동 계획
- PC2 화면 표시용 짧은 메시지

fallback 경로에서는 `exercise_plan`이 비어 있을 수 있으며, 이 경우 `pc2_payload.message` 한 줄을 우선 사용합니다.

PC3는 `exercise`에서 `session_completed` 시점에만 PC2를 호출합니다.
프로필 기반 루틴은 PC1 사용자 프로필 값이 확정된 시점에 `/api/routine/profile`로 호출합니다.

## 프롬프트 작성 원칙

PC2 시스템 프롬프트에는 최소한 다음 원칙을 포함합니다.

```text
너는 스마트미러 운동 계획 API다.
너는 이미지를 직접 보지 않는다.
입력은 PC3가 만든 운동 feature, 저장된 baseline, 검색된 운동 지식뿐이다.
운동 계획은 현재 자세 상태와 baseline 차이를 바탕으로 안전한 범위에서 작성한다.
출력은 CoachingResponse JSON만 허용된다.
입력에 없는 사실 추측은 금지한다.
```

프로필 루틴 생성 프롬프트에는 최소한 다음 원칙을 포함합니다.

```text
너는 스마트미러 주간 루틴 생성 API다.
입력은 PC1 프론트에서 받은 사용자 목표, 운동 경험, 주당 운동 가능 횟수, 제한 부위다.
루틴은 primary LLM 응답으로만 생성한다.
제한 부위가 있으면 해당 부위를 무리하게 쓰는 운동을 피하거나 주의사항에 반영한다.
출력은 RoutineProfileResponse JSON만 허용된다.
입력에 없는 질병, 통증, 진단 정보 추측은 금지한다.
```
