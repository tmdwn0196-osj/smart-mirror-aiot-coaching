# PC3 -> PC2 요청 명세

## 목적

PC3는 운동 자세 분석과 feature 추출을 담당합니다.
PC2는 PC3가 보낸 운동 feature, 저장된 baseline, 로컬 검색 컨텍스트를 사용해 LLM 기반 운동 계획표를 생성합니다.
또한 PC1 프론트의 사용자 프로필 값을 PC3가 전달하면 primary LLM으로 주간 루틴 JSON을 생성합니다.

운동 세션 기반 계획 생성은 `exercise` 전용입니다.
프로필 기반 주간 루틴 생성은 `/api/routine/profile`을 사용합니다.

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
6. PC1 프로필 기반 루틴이 필요하면 PC3가 프로필 값을 `/api/routine/profile`로 전달

## 엔드포인트

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

요청 필수:

- `user_id`
- `event`
- `features.exercise`
- `features.exercise.type`

요청 선택:

- `session_id`
- `mode` (`exercise` 기본값)
- `features.exercise.count`
- `features.exercise.rep_count`
- `features.exercise.state`
- `features.exercise.stability_score`
- `features.exercise.posture_errors`
- `features.exercise.squat_depth`
- `features.exercise.knee_angle`
- `features.exercise.back_angle`
- `features.exercise.duration_sec`
- `features.exercise.duration_seconds`
- `features.exercise.tempo`
- `baseline_diff.exercise`
- `environment`
- `purpose`

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

fallback 경로에서도 PC2는 raw plain text를 직접 반환하지 않습니다.
항상 `CoachingResponse` JSON을 유지합니다.
현재 구현 기준으로 fallback LLM 응답은 구조화된 계획 대신 아래와 같은 최소 응답으로 정규화됩니다.

```json
{
  "summary": "무릎 정렬을 먼저 맞추고 천천히 진행하세요.",
  "priority": "무릎 정렬을 먼저 맞추고 천천히 진행하세요.",
  "exercise_plan": [],
  "mirror_message": "무릎 정렬을 먼저 맞추고 천천히 진행하세요.",
  "warnings": [],
  "pc2_payload": {
    "message": "무릎 정렬을 먼저 맞추고 천천히 진행하세요.",
    "display_lines": ["무릎 정렬을 먼저 맞추고 천천히 진행하세요."]
  }
}
```

반면 LLM 설정이 없거나 LLM 호출 또는 파싱이 실패해 로컬 규칙 기반 fallback이 사용되면, 응답은 계속 `CoachingResponse` JSON이며 보통 `exercise_plan`을 포함한 계획 형태를 유지합니다.

## 프로필 기반 루틴 생성

이 endpoint는 PC1 프론트에서 받은 사용자 목표, 운동 경험, 주당 운동 가능 횟수, 제한 부위를 PC3가 PC2로 전달할 때 사용합니다.
운동 feature, baseline, `mode`, `event`는 사용하지 않습니다.

```http
POST /api/routine/profile
Content-Type: application/json
```

요청 필수:

- `user_id`
- `user_goal`
- `exercise_experience`
- `available_days_per_week`

요청 선택:

- `profile_name`
- `weight_kg`
- `restricted_body_parts` (`[]` 권장)
- `purpose`

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

실패 정책:

- primary LLM이 설정되지 않았으면 `503`과 `reason=primary_llm_unconfigured`
- primary LLM 호출 실패 시 `503`과 `reason=primary_llm_call_failed`
- primary LLM 응답 파싱 실패 시 `503`과 `reason=primary_llm_parse_failed`
- 로컬 fallback 루틴은 생성하지 않음

## DB 기록 항목

`/api/coach/generate` 성공 요청은 아래 항목으로 저장합니다.
`/api/routine/profile`은 현재 coach log DB에 저장하지 않고 서버 로그에 성공/실패 사유만 남깁니다.

- 원본 FeaturePayload
- baseline 스냅샷
- 감지 신호
- analysis_context
- 원본 LLM 응답
- final_response_json
- pc2_output_json
- `is_duplicate_session`
- `duplicate_of_request_id`

같은 `user_id + session_id`가 다시 들어오면 요청은 차단하지 않고, 후속 로그 항목에만 중복 여부가 표시됩니다.

## 주의사항

- 원본 이미지, 영상, landmark 배열은 보내지 않음
- PC3에서 계산한 수치와 상태값만 전달
- baseline이 없어도 계획 생성은 가능하지만 경고가 추가됨
- fallback 시에도 PC3는 plain text가 아니라 JSON 응답을 받음
