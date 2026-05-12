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

### 계획표 생성 변수 의미

Top-level:

| 변수 | 의미 | PC3 작성 기준 |
| --- | --- | --- |
| `user_id` | 사용자 식별자 | PC1/PC3에서 쓰는 동일 사용자 ID |
| `session_id` | 운동 세션 식별자 | 중복 요청 로그 표시 기준. 세션마다 고유값 권장 |
| `mode` | 요청 모드 | 운동 계획 생성은 `exercise` |
| `event` | 호출 이벤트 | 세션 종료 후 `session_completed`만 허용 |
| `features.exercise` | 운동 분석 feature | 원본 이미지/landmark 제외, PC3가 계산한 수치와 상태만 포함 |
| `baseline_diff.exercise` | baseline 대비 변화량 | PC3가 계산했으면 전달, 생략하면 PC2가 저장 baseline으로 보완 |
| `environment` | 환경 센서 값 | 온도, 습도, 조도 선택 전달 |
| `purpose` | 호출 목적 | 로그와 프롬프트 참고용 |

`features.exercise`:

| 변수 | 의미 |
| --- | --- |
| `type` | 운동 타입. `squat`, `jumping_jack`, `knee_raise`, `lunge`, `pushup` 중 하나 |
| `count` | PC3 카운터 기준 반복 수 |
| `rep_count` | 반복 수. `count`와 같은 의미이며 둘 다 보낼 경우 같은 값 권장 |
| `state` | 종료 시점 대표 운동 상태 |
| `stability_score` | 자세 안정도. 0~1 범위 사용 권장, 높을수록 안정 |
| `posture_errors` | 자세 오류 코드 문자열 배열 |
| `squat_depth` | 스쿼트 깊이 정규화 지표. 같은 산식 유지 필요 |
| `knee_angle` | 무릎 각도 |
| `back_angle` | 상체/등 상태 문자열 |
| `duration_sec` | 초 단위 지속 시간 |
| `duration_seconds` | `duration_sec`와 같은 의미 |
| `tempo` | 운동 속도/리듬 |

`baseline_diff.exercise`:

| 변수 | 의미 |
| --- | --- |
| `count_change` | 현재 반복 수 - baseline 반복 수 |
| `stability_change` | 현재 안정도 - baseline 안정도 |
| `knee_angle_change` | 현재 무릎 각도 - baseline 무릎 각도 |
| `squat_depth_change` | 현재 깊이 - baseline 깊이 |
| `duration_change` | 현재 지속 시간 - baseline 지속 시간 |

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

응답 변수 의미:

| 변수 | 의미 | PC3 사용 기준 |
| --- | --- | --- |
| `summary` | 현재 세션 분석과 계획 방향 요약 | 화면 요약 또는 서버 로직 참고 |
| `priority` | 가장 먼저 교정할 포인트 | 자세 우선순위 표시 |
| `exercise_plan` | 다음 운동 계획 배열 | fallback 시 빈 배열 가능 |
| `mirror_message` | 미러 표시용 짧은 문장 | 화면 표시용 |
| `warnings` | baseline 없음, 낮은 조도 등 경고 | 사용자/로그 표시 |
| `pc2_payload.message` | 대표 표시 문장 | PC3 화면 표시에서 우선 사용 권장 |
| `pc2_payload.display_lines` | 짧은 지시문 배열 | UI 핵심 지시로 사용 |

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

### 프로필 루틴 변수 의미

요청:

| 변수 | 의미 | PC3 작성 기준 |
| --- | --- | --- |
| `user_id` | 사용자 식별자 | PC1/PC3에서 쓰는 동일 사용자 ID |
| `profile_name` | 사용자 표시 이름 | 선택 값 |
| `weight_kg` | 체중 | kg 단위, 선택 값, 1~500 허용 |
| `user_goal` | 사용자 목표 | 루틴 방향을 결정하는 핵심 값 |
| `exercise_experience` | 운동 경험 수준/설명 | 난이도와 볼륨 조절 기준 |
| `available_days_per_week` | 주당 운동 가능 횟수 | 1~7 허용. 루틴은 이 값 이하 일수로 생성 |
| `restricted_body_parts` | 제한 부위 배열 | 없으면 `[]` 권장. 예: `["무릎", "허리"]` |
| `purpose` | 호출 목적 | 로그와 프롬프트 참고용 |

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

응답:

| 변수 | 의미 | PC3 사용 기준 |
| --- | --- | --- |
| `summary` | 루틴 전체 요약 | 프론트 상단 요약 |
| `weekly_focus` | 이번 주 핵심 방향 | 주간 목표 문구 |
| `weekly_routine` | 일자별 루틴 배열 | 최대 `available_days_per_week`개 |
| `weekly_routine[].day_index` | 루틴 일차 번호 | 1~7, UI 정렬 기준 |
| `weekly_routine[].day_label` | 화면 표시용 일차 라벨 | 예: `Day 1`, `1일차` |
| `weekly_routine[].focus` | 해당 일차 운동 초점 | 카드 제목/설명 |
| `weekly_routine[].exercises` | 해당 일차 운동 목록 | 기존 운동 계획 item 구조 |
| `cautions` | 제한 부위 관련 주의사항 | 사용자 주의 문구 |
| `pc3_payload` | 프론트 전달용 payload | PC3가 그대로 전달 가능 |

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
