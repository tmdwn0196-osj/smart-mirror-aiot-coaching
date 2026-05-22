# PC2 흐름 변경 기록

## 2026-05-20

### 루틴 생성 날짜 배정

- 루틴 생성 API `POST /api/routine/profile`는 `generate_profile_routine_response()`에서 `pc3_payload.scheduled_dates`를 계산합니다.
- 주 1회부터 4회까지는 `start_date + 0, 2, 4, 6` 형태의 격일 배정을 사용합니다.
- 주 5회 이상은 `start_date + 0, 1, 2, 3...` 형태의 연속 배정을 유지합니다.
- 이 변경은 PC3로 전달하는 응답 값 계산만 바꾸며 JSON shape와 필드명은 유지합니다.

### 현재 저장 흐름

- 현재 루틴 생성 API는 PC2 로컬 DB에 루틴 일정을 저장하지 않고 응답만 반환합니다.
- `save_profile_routine()`와 `save_profile_routine_days()`는 구현되어 있지만 현재 루틴 생성 경로에는 연결되어 있지 않습니다.
- 따라서 이번 날짜 정책 변경은 현재 기준으로 PC3가 받는 `scheduled_dates`에만 적용됩니다.
