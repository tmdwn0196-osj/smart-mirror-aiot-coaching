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
- 날짜별 루틴 조회: `GET http://<PC2_HOST>:7000/api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD`
- Health check: `GET http://<PC2_HOST>:7000/health`
- Debug logs: `GET http://<PC2_HOST>:7000/api/coach/logs/{user_id}?limit=10`

## PC3 DTO 예시

PC3에서 바로 구현할 수 있도록 요청/응답 DTO 예시를 아래처럼 권장합니다.

### PC3 -> PC2 루틴 생성 요청 DTO

```json
{
  "user_id": "user_001",
  "profile_name": "홍길동",
  "weight_kg": 68,
  "user_goal": "운동 습관 만들기",
  "exercise_experience": "초보",
  "available_days_per_week": 5,
  "restricted_body_parts": ["무릎"],
  "start_date": "2026-05-13",
  "purpose": "프로필 기반 주간 루틴 추천"
}
```

### PC2 -> PC3 주간 루틴 응답 DTO

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
          "exercise": "squat",
          "sets": 4,
          "reps": 10,
          "duration_sec": null,
          "rest_sec": 75,
          "focus": "하체 안정성",
          "reason": "기초 하체 근력 유지에 적합합니다.",
          "how_to": "발을 어깨너비로 벌리고 엉덩이를 뒤로 빼며 천천히 앉았다가 올라옵니다.",
          "tips": "발바닥 전체로 밀고 무릎 방향을 발끝과 맞춥니다."
        }
      ]
    }
  ],
  "cautions": ["통증이 있으면 강도를 낮추세요."],
  "pc3_payload": {
    "routine_id": "routine_abcd1234",
    "start_date": "2026-05-13",
    "scheduled_dates": ["2026-05-13", "2026-05-14", "2026-05-15"]
  }
}
```

### PC3 -> PC2 날짜별 루틴 조회 DTO

```http
GET /api/routine/profile/user_001/day?target_date=2026-05-14
```

### PC2 -> PC3 날짜별 루틴 응답 DTO

```json
{
  "routine_id": "routine_abcd1234",
  "user_id": "user_001",
  "scheduled_date": "2026-05-14",
  "day_index": 2,
  "day_label": "Day 2",
  "focus": "상체 밀기와 코어 고정",
  "exercises": [
    {
      "exercise": "pushup",
      "sets": 3,
      "reps": 8,
      "duration_sec": null,
      "rest_sec": 60,
      "focus": "상체 볼륨 확보",
      "reason": "주간 빈도를 유지하기 좋은 난이도입니다.",
      "how_to": "손을 어깨보다 약간 넓게 두고 몸통을 일직선으로 유지한 채 내려갔다가 밀어 올립니다.",
      "tips": "복부에 힘을 주고 내려갈 때 들이마시고 밀어낼 때 내쉽니다."
    }
  ],
  "summary": "운동 습관 형성을 위한 주간 루틴입니다.",
  "weekly_focus": "주 5회 리듬 유지와 전신 밸런스 확보",
  "message": "오늘은 상체 밀기와 코어 고정 루틴으로 pushup를 진행할 예정입니다."
}
```

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

PC1 -> PC3 초기 입력 권장값:

- `user_id`
- `profile_name`
- `weight_kg`
- `user_goal`
- `exercise_experience`
- `available_days_per_week`
- `restricted_body_parts`
- `start_date`
- `purpose`

PC3 중계 규칙:

- PC3는 PC1에서 받은 위 필드를 `/api/routine/profile` 요청 본문으로 그대로 전달합니다.
- `start_date`가 있으면 Day 1 시작일로 사용하기 위해 그대로 전달합니다.
- `start_date`가 없으면 필드를 생략할 수 있으며, 이 경우 PC2가 서버 기준 오늘 날짜를 Day 1로 사용합니다.
- PC3는 `summary`, `weekly_focus`, `weekly_routine`, `cautions`와 함께 `pc3_payload.routine_id`, `pc3_payload.start_date`, `pc3_payload.scheduled_dates`를 보관하거나 PC1에 전달할 수 있습니다.
- 특정 날짜 루틴이 필요하면 PC3가 `/api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD`를 다시 조회해 PC1에 전달합니다.

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

### 운동 계획 요청 변수 의미

Top-level:

| 변수 | 의미 | PC3 작성 기준 |
| --- | --- | --- |
| `user_id` | 사용자 식별자 | PC1/PC3에서 사용하는 동일 사용자 ID를 전달합니다. |
| `session_id` | 운동 세션 식별자 | 같은 운동 세션 재전송 여부를 로그에서 구분하는 값입니다. 가능하면 세션마다 고유하게 전달합니다. |
| `mode` | 요청 모드 | 운동 계획 생성은 `exercise`만 사용합니다. 생략하면 `exercise`로 처리됩니다. |
| `event` | 호출 이벤트 | 세션 종료 후 `session_completed`만 허용합니다. 실시간 프레임 이벤트는 보내지 않습니다. |
| `features.exercise` | PC3가 계산한 운동 분석 결과 | 원본 이미지나 landmark가 아니라 최종 수치/상태 feature만 담습니다. |
| `baseline_diff.exercise` | 현재 세션과 baseline의 차이 | PC3가 이미 계산했다면 전달합니다. 생략하면 PC2가 저장된 baseline으로 보완합니다. |
| `environment` | 센서/환경 정보 | 조도, 습도, 온도 같은 선택 값입니다. 없어도 계획 생성은 가능합니다. |
| `purpose` | 호출 목적 설명 | 로그와 프롬프트 참고용입니다. 기능 분기에는 사용하지 않습니다. |

`features.exercise`:

| 변수 | 의미 | PC3 작성 기준 |
| --- | --- | --- |
| `type` | 운동 타입 | `squat`, `jumping_jack`, `knee_raise`, `lunge`, `pushup` 중 하나만 허용합니다. |
| `count` | 반복 횟수 | PC3 카운터 기준 반복 수입니다. `rep_count`와 둘 중 하나 이상 전달을 권장합니다. |
| `rep_count` | 반복 횟수 | `count`와 같은 의미입니다. 둘 다 보낼 경우 같은 값으로 맞추는 것을 권장합니다. |
| `state` | 종료 시점 대표 상태 | 예: `up`, `down`, `ready`. PC2는 문자열로 참고만 합니다. |
| `stability_score` | 자세 안정도 점수 | 0~1 범위 사용을 권장하며, 높을수록 안정적인 상태로 해석합니다. |
| `posture_errors` | 자세 오류 코드 배열 | 예: `knees_caving_in`, `back_forward`. PC3 내부 오류 코드를 문자열 배열로 보냅니다. |
| `squat_depth` | 스쿼트 깊이 지표 | 스쿼트에서 사용하는 정규화 지표입니다. 같은 사용자/baseline 비교가 가능하도록 같은 산식으로 보내야 합니다. |
| `knee_angle` | 무릎 각도 | 각도 단위 숫자입니다. 자세 오류와 강도 조절 참고에 사용합니다. |
| `back_angle` | 상체/등 상태 | 예: `neutral`, `forward`. 문자열 상태값으로 전달합니다. |
| `duration_sec` | 세션 또는 동작 지속 시간 | 초 단위 숫자입니다. |
| `duration_seconds` | 세션 또는 동작 지속 시간 | `duration_sec`와 같은 의미입니다. 둘 중 하나만 사용해도 됩니다. |
| `tempo` | 운동 속도/리듬 | 예: `slow`, `controlled`, `fast`. 속도 조절 피드백에 사용합니다. |

`baseline_diff.exercise`:

| 변수 | 의미 |
| --- | --- |
| `count_change` | 현재 반복 수 - baseline 반복 수 |
| `stability_change` | 현재 안정도 - baseline 안정도 |
| `knee_angle_change` | 현재 무릎 각도 - baseline 무릎 각도 |
| `squat_depth_change` | 현재 깊이 - baseline 깊이 |
| `duration_change` | 현재 지속 시간 - baseline 지속 시간 |

`environment`:

| 변수 | 의미 |
| --- | --- |
| `temperature` | 온도 |
| `humidity` | 습도 |
| `illuminance` | 조도. 낮으면 비전 feature 신뢰도 경고에 반영될 수 있습니다. |

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

### 운동 계획 응답 변수 의미

| 변수 | 의미 | PC3 사용 기준 |
| --- | --- | --- |
| `summary` | 현재 세션 분석과 계획 방향 요약 | 서버 로직/화면 요약에 사용합니다. |
| `priority` | 가장 먼저 교정할 포인트 | 운동 자세 우선순위 표시용입니다. |
| `exercise_plan` | 다음 운동 계획 배열 | 각 item의 운동명, 세트, 반복/시간, 휴식, 이유를 표시할 수 있습니다. fallback 시 비어 있을 수 있습니다. |
| `mirror_message` | 미러에 바로 표시할 짧은 문장 | 화면 표시용 한 줄 메시지로 사용 가능합니다. |
| `warnings` | 불확실성 또는 주의 경고 | baseline 없음, 낮은 조도 같은 조건을 사용자/로그에 표시할 때 사용합니다. |
| `pc2_payload.message` | PC2/미러 표시용 대표 문장 | fallback까지 고려하면 PC3 화면 표시는 이 값을 우선 사용하면 됩니다. |
| `pc2_payload.display_lines` | 화면용 짧은 지시문 배열 | UI에서 2~3줄 핵심 지시로 표시할 수 있습니다. |

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
- `start_date`: 루틴 시작 날짜, 선택

### 프로필 루틴 요청 변수 의미

| 변수 | 의미 | PC3 작성 기준 |
| --- | --- | --- |
| `user_id` | 사용자 식별자 | PC1/PC3에서 사용하는 동일 사용자 ID를 전달합니다. |
| `profile_name` | 사용자 표시 이름 | 루틴 생성 참고용 선택 값입니다. 없어도 됩니다. |
| `weight_kg` | 체중 | kg 단위 숫자입니다. 선택 값이며 1~500 범위만 허용됩니다. |
| `user_goal` | 사용자 목표 | 예: `체중 감량`, `근력 향상`, `운동 습관 만들기`. 루틴 방향을 결정하는 핵심 값입니다. |
| `exercise_experience` | 운동 경험 수준/설명 | 예: `초보`, `가끔 운동함`, `꾸준히 운동함`. 볼륨과 난이도 조절에 사용합니다. |
| `available_days_per_week` | 주당 운동 가능 횟수 | 1~7만 허용합니다. PC2는 응답 `weekly_routine` 일수가 이 값을 초과하면 파싱 실패로 처리합니다. |
| `restricted_body_parts` | 제한 부위 배열 | 예: `["무릎", "허리"]`. 없으면 `[]`로 보내는 것을 권장합니다. 해당 부위 부담을 낮추는 데 사용합니다. |
| `purpose` | 호출 목적 설명 | 로그와 프롬프트 참고용 선택 값입니다. |
| `start_date` | Day 1을 배정할 시작 날짜 | 선택 값입니다. 없으면 PC2 서버 기준 오늘 날짜를 사용합니다. |

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
  "purpose": "프로필 기반 주간 루틴 추천",
  "start_date": "2026-05-13"
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
          "exercise": "squat",
          "sets": 4,
          "reps": 10,
          "duration_sec": null,
          "rest_sec": 75,
          "focus": "하체 안정성",
          "reason": "기초 하체 근력 유지에 적합합니다.",
          "how_to": "발을 어깨너비로 벌리고 엉덩이를 뒤로 빼며 천천히 앉았다가 올라옵니다.",
          "tips": "발바닥 전체로 밀고 무릎 방향을 발끝과 맞춥니다."
        }
      ]
    }
  ],
  "cautions": [],
  "pc3_payload": {
    "summary": "운동 습관 형성을 위한 주간 루틴입니다.",
    "weekly_focus": "주 5회 리듬 유지와 전신 밸런스 확보",
    "routine_id": "routine_abcd1234",
    "start_date": "2026-05-13",
    "scheduled_dates": ["2026-05-13", "2026-05-14", "2026-05-15"],
    "weekly_routine": [
      {
        "day_index": 1,
        "day_label": "Day 1",
        "focus": "하체와 코어",
        "exercises": [
          {
            "exercise": "squat",
            "sets": 4,
            "reps": 10,
            "duration_sec": null,
            "rest_sec": 75,
            "focus": "하체 안정성",
            "reason": "기초 하체 근력 유지에 적합합니다.",
            "how_to": "발을 어깨너비로 벌리고 엉덩이를 뒤로 빼며 천천히 앉았다가 올라옵니다.",
            "tips": "발바닥 전체로 밀고 무릎 방향을 발끝과 맞춥니다."
          }
        ]
      }
    ]
  }
}
```

### 프로필 루틴 응답 변수 의미

| 변수 | 의미 | PC3 사용 기준 |
| --- | --- | --- |
| `summary` | 루틴 전체 요약 | 프론트 상단 요약 문구로 사용합니다. |
| `weekly_focus` | 이번 주 핵심 방향 | 주간 목표/초점 문구로 표시합니다. |
| `weekly_routine` | 일자별 루틴 배열 | 최소 1일 이상이어야 하며, 일수는 `available_days_per_week`를 초과할 수 없습니다. |
| `weekly_routine[].day_index` | 루틴 일차 번호 | 1~7 범위입니다. UI 정렬 기준으로 사용합니다. |
| `weekly_routine[].day_label` | 화면 표시용 일차 라벨 | 예: `Day 1`, `1일차`. |
| `weekly_routine[].focus` | 해당 일차의 운동 초점 | 카드 제목 또는 설명으로 사용합니다. |
| `weekly_routine[].exercises` | 해당 일차 운동 목록 | 기존 `exercise_plan` item과 같은 구조입니다. |
| `weekly_routine[].exercises[].how_to` | 동작 수행 방법 | 자세 설명/운동 가이드로 표시합니다. |
| `weekly_routine[].exercises[].tips` | 핵심 요령 | 호흡, 속도, 정렬 팁으로 표시합니다. |
| `cautions` | 제한 부위 관련 주의사항 | 사용자에게 주의 문구로 표시합니다. |
| `pc3_payload` | PC3/프론트 전달용 payload | PC2 parser가 top-level 루틴 결과와 요청값을 기준으로 일관되게 재구성합니다. |
| `pc3_payload.routine_id` | 저장된 주간 루틴 ID | 날짜별 루틴 추적이나 로그 연결 시 사용할 수 있습니다. |
| `pc3_payload.start_date` | Day 1 시작 날짜 | PC1 캘린더/일정 표시 기준으로 사용합니다. |
| `pc3_payload.scheduled_dates` | Day별 배정 날짜 목록 | PC1/PC3가 날짜별 루틴 조회 기준으로 사용할 수 있습니다. |

PC3는 이 응답에서 `pc3_payload`를 그대로 프론트에 넘기거나, `summary`, `weekly_focus`, `weekly_routine`, `cautions`만 골라서 가공해도 됩니다.
현재 이 endpoint는 `/api/coach/logs/{user_id}` 조회 대상이 아니며, 성공/실패 사유는 PC2 서버 로그에 남습니다.

### 날짜별 루틴 조회 응답 예시

```json
{
  "routine_id": "routine_abcd1234",
  "user_id": "exercise_user",
  "scheduled_date": "2026-05-14",
  "day_index": 2,
  "day_label": "Day 2",
  "focus": "상체 밀기와 코어 고정",
  "exercises": [
    {
      "exercise": "pushup",
      "sets": 3,
      "reps": 8,
      "duration_sec": null,
      "rest_sec": 60,
      "focus": "상체 볼륨 확보",
      "reason": "주간 빈도를 유지하기 좋은 난이도입니다.",
      "how_to": "손을 어깨보다 약간 넓게 두고 몸통을 일직선으로 유지한 채 내려갔다가 밀어 올립니다.",
      "tips": "복부에 힘을 주고 내려갈 때 들이마시고 밀어낼 때 내쉽니다."
    }
  ],
  "summary": "운동 습관 형성을 위한 주간 루틴입니다.",
  "weekly_focus": "주 5회 리듬 유지와 전신 밸런스 확보",
  "message": "오늘은 상체 밀기와 코어 고정 루틴으로 pushup를 진행할 예정입니다."
}
```

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
이 값은 LLM 원문을 그대로 신뢰하는 것이 아니라, PC2가 검증한 top-level 루틴 결과에서 다시 만든 payload입니다.
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
