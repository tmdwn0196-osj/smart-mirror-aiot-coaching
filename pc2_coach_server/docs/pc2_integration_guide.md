# PC2 연결 가이드

이 문서는 PC2 Coach API를 PC3 Vision Gateway에 연결할 때 필요한 엔드포인트, payload, 응답 규칙을 정리합니다.

## 연결 방향

```text
PC1 -> PC3 Vision Gateway -> PC2 Coach API
```

PC2는 PC3에서 전달하는 운동 `FeaturePayload`를 받아 운동 계획표 JSON을 생성합니다.
PC2는 저장된 baseline과 로컬 운동 지식 검색 결과를 함께 사용합니다.
PC1 프론트의 사용자 프로필 값은 PC3를 거쳐 `/api/routine/profile`로 전달되며, primary LLM으로 주간 루틴 JSON을 생성합니다.
운영 기준으로 `POST /api/coach/generate`는 `primary LLM -> fallback vLLM -> local rule fallback` 순서를 사용합니다.

## 엔드포인트

운동 계획 생성:

```http
POST /api/coach/generate
Content-Type: application/json
```

프로필 기반 주간 루틴 생성:

```http
POST /api/routine/profile
Content-Type: application/json
```

PC3 설정:

```env
PC2_COACH_API_URL=http://<PC2_HOST>:7000/api/coach/generate
PC2_ROUTINE_PROFILE_API_URL=http://<PC2_HOST>:7000/api/routine/profile
PC2_ROUTINE_DAY_API_URL=http://<PC2_HOST>:7000/api/routine/profile/{user_id}/day?target_date={YYYY-MM-DD}
```

PC2 서버 표준 실행:

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
cp .env.example .env
docker compose -f docker-compose.vllm.yml up -d
./scripts/run_pc2.sh
```

표준 `.env.example`은 `FALLBACK_LLM_ENABLED=true` 기준입니다.
fallback vLLM 모델 기준값은 `Qwen/Qwen2.5-1.5B-Instruct-AWQ`입니다.

## 실행 구조

PC2 내부 구조:

```text
Coach API
  -> Baseline 조회
  -> 신호 감지
  -> 로컬 지식 검색
  -> 프롬프트 구성
  -> NVIDIA Gemma 4 31B IT
  -> 출력 검증
```

## 입력: FeaturePayload

PC2는 원본 이미지를 받지 않습니다. 입력은 반드시 `FeaturePayload` JSON 하나입니다.

필수 필드:

- `user_id`
- `event`
- `features.exercise`
- `features.exercise.type`

선택 필드:

- `session_id`
- `mode` (`exercise` 기본값)
- `baseline_diff.exercise`
- `environment`
- `purpose`
- 그 외 `features.exercise` 내부 세부 측정값들 (`count`, `rep_count`, `state`, `stability_score`, `posture_errors`, `squat_depth`, `knee_angle`, `back_angle`, `duration_sec`, `duration_seconds`, `tempo`)

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

- 원본 이미지 파일
- base64 이미지
- 프레임 경로
- 영상 경로
- 전체 landmark 목록
- 분할 마스크
- 카메라 스트림 URL

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

보조 LLM fallback 시에도 응답 형식은 그대로 `CoachingResponse` JSON입니다.
현재 구현 기준으로 fallback LLM이 사용되면 구조화된 운동 계획 대신 한 줄 문장을 최소 응답으로 채워 반환합니다.

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

반면 로컬 규칙 기반 fallback이 사용되면 응답은 계속 `CoachingResponse` JSON이며, 보통 `exercise_plan`을 포함한 계획 응답으로 내려갑니다.

## 입력: RoutineProfileRequest

프로필 기반 루틴 생성은 운동 feature를 받지 않습니다.
PC3는 PC1 프론트에서 받은 프로필 값을 아래 형식으로 전달합니다.

필수 필드:

- `user_id`
- `user_goal`
- `exercise_experience`
- `available_days_per_week`

선택 필드:

- `profile_name`
- `weight_kg`
- `restricted_body_parts`
- `purpose`
- `start_date`

PC3 전달 규칙:

- PC3는 PC1 프론트에서 받은 프로필 필드를 가능한 한 가공 없이 그대로 전달합니다.
- `start_date`가 있으면 Day 1 시작일로 사용하기 위해 그대로 전달합니다.
- `start_date`가 없으면 생략할 수 있으며, 이 경우 PC2가 서버 기준 오늘 날짜를 사용합니다.

예시:

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

## 출력: RoutineProfileResponse

```json
{
  "summary": "string",
  "weekly_focus": "string",
  "weekly_routine": [
    {
      "day_index": 1,
      "day_label": "Day 1",
      "focus": "string",
      "exercises": []
    }
  ],
  "cautions": ["string"],
  "pc3_payload": {
    "routine_id": "string",
    "start_date": "2026-05-13",
    "scheduled_dates": ["2026-05-13", "2026-05-14"]
  }
}
```

`pc3_payload`는 PC2가 top-level 루틴 결과와 요청값을 기준으로 재구성한 루틴 표시용 payload입니다.
즉 `summary`, `weekly_focus`, `weekly_routine`는 top-level 응답과 일치하고, `available_days_per_week`, `restricted_body_parts`, `routine_id`, `start_date`, `scheduled_dates`는 PC3/PC1 일정 처리용으로 함께 내려갑니다.
이 endpoint는 primary LLM 전용이며, primary LLM 미설정/호출 실패/파싱 실패 시 `503`을 반환합니다.
로컬 fallback 루틴은 생성하지 않습니다.

## 출력: RoutineProfileDayRecord

```http
GET /api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD
```

```json
{
  "routine_id": "string",
  "user_id": "exercise_user",
  "scheduled_date": "2026-05-14",
  "day_index": 2,
  "day_label": "Day 2",
  "focus": "상체 밀기와 코어 고정",
  "exercises": [],
  "summary": "string",
  "weekly_focus": "string",
  "message": "오늘은 상체 밀기와 코어 고정 루틴으로 pushup를 진행할 예정입니다."
}
```

## PC2 호출 시점

| mode | event | PC2 호출 여부 |
| --- | --- | --- |
| `exercise` | `session_completed` | 호출 |

운동 실시간 count/state/feedback은 PC3가 직접 처리합니다. PC2는 세션 종료 후 최종 계획 생성만 담당합니다.

PC3가 화면에 바로 표시할 때는 `pc2_payload.message`를 우선 사용하면 됩니다.
`/api/coach/generate`에서 같은 `user_id + session_id`가 재전송되면 요청은 계속 처리되고, `/api/coach/logs/{user_id}` 결과에서 `is_duplicate_session`와 `duplicate_of_request_id`로 중복 여부를 확인할 수 있습니다.
`/api/routine/profile`은 현재 coach log DB에 저장하지 않고 서버 로그에 성공/실패 사유만 남깁니다.
