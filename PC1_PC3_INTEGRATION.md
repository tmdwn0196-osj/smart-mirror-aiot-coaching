# PC1 -> PC3 Integration Spec

이 문서는 PC1 프론트가 PC3 Vision Gateway와 연결할 때 필요한 프로필 루틴 요청 형식, 날짜별 루틴 조회 형식, 응답 활용 방식을 정리한 명세서입니다.

## 목적

PC1은 사용자 프로필과 일정 기준 날짜를 PC3에 전달합니다.
PC3는 이 값을 PC2로 중계해 주간 루틴을 생성하고, 다시 PC1이 필요한 날짜별 루틴을 조회할 수 있게 합니다.

연결 방향:

```text
PC1 -> PC3 Vision Gateway -> PC2 Coach API
```

## PC1이 처음 보내야 하는 값

루틴 생성 요청 시 아래 값을 보내는 것을 권장합니다.

- `user_id`
- `profile_name`
- `weight_kg`
- `user_goal`
- `exercise_experience`
- `available_days_per_week`
- `restricted_body_parts`
- `start_date`
- `purpose`

`start_date`는 선택 값입니다.
보내면 Day 1 시작 날짜를 직접 지정할 수 있고, 생략하면 PC2 서버 기준 오늘 날짜가 Day 1로 사용됩니다.

## 1. 주간 루틴 생성 요청

### PC1 -> PC3 요청 예시

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

### 필드 의미

| 필드 | 의미 | 비고 |
| --- | --- | --- |
| `user_id` | 사용자 식별자 | PC1, PC3, PC2 전체에서 동일하게 사용 |
| `profile_name` | 표시 이름 | 선택 |
| `weight_kg` | 체중 | 선택, kg 단위 숫자 |
| `user_goal` | 운동 목표 | 예: `체중 감량`, `운동 습관 만들기` |
| `exercise_experience` | 운동 경험 수준 | 예: `초보`, `꾸준히 운동함` |
| `available_days_per_week` | 주당 운동 가능 횟수 | 1~7 |
| `restricted_body_parts` | 제한 부위 배열 | 예: `["무릎", "허리"]` |
| `start_date` | Day 1 시작 날짜 | 선택, `YYYY-MM-DD` |
| `purpose` | 호출 목적 설명 | 선택 |

## 2. PC3가 PC1에 돌려줄 주간 루틴 응답 권장값

PC3는 아래 값을 그대로 전달하거나, 필요한 필드만 골라 가공해서 전달할 수 있습니다.

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
  "routine_id": "routine_abcd1234",
  "start_date": "2026-05-13",
  "scheduled_dates": ["2026-05-13", "2026-05-14", "2026-05-15"]
}
```

### PC1이 활용하면 좋은 값

- `summary`
- `weekly_focus`
- `weekly_routine`
- `cautions`
- `routine_id`
- `start_date`
- `scheduled_dates`

## 3. 특정 날짜 루틴 조회

PC1이 오늘 루틴 또는 임의 날짜 루틴이 필요하면, PC3가 날짜를 받아 다시 조회해 전달합니다.

### PC1 -> PC3 요청 예시

```json
{
  "user_id": "user_001",
  "target_date": "2026-05-14"
}
```

### PC3 -> PC1 응답 예시

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

### PC1에서 바로 표시하기 좋은 값

- `scheduled_date`
- `day_label`
- `focus`
- `exercises`
- `message`

## 권장 구현 규칙

- PC1은 `start_date`를 캘린더 선택값으로 보낼 수 있게 하는 것이 좋습니다.
- PC1은 `scheduled_dates`를 받아 주간 캘린더 표시 기준으로 사용할 수 있습니다.
- PC1은 특정 날짜를 눌렀을 때 `target_date`로 PC3에 날짜별 루틴 조회를 요청하면 됩니다.
- PC1은 `message`를 메인 카드 한 줄 안내 문구로 바로 사용할 수 있습니다.
