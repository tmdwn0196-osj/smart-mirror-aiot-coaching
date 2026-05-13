# 흐름 변경 정리

이 문서는 이 저장소의 주요 데이터 흐름, API 흐름, 런타임 흐름 변경 사항을 한글로 정리하기 위한 파일입니다.

## 1. 데이터 흐름 변경

- 기존 SQLite 파일 저장 중심 흐름에서 PostgreSQL 저장 흐름으로 전환했습니다.
- 운동 세션 기반 코칭 응답은 `coach_logs`에 기록되고, baseline 데이터는 `exercise_baselines`에 기록됩니다.
- 프로필 기반 주간 루틴은 `profile_routines`에 주간 단위로 저장되고, `profile_routine_days`에 날짜별 day 루틴으로 분리 저장됩니다.

## 2. API 흐름 변경

- `POST /api/coach/generate`
  - PC3의 운동 분석 결과를 받아 코칭 응답을 생성합니다.
  - primary LLM 실패 시 fallback vLLM, 그마저 실패 시 로컬 규칙 fallback으로 진행합니다.

- `POST /api/routine/profile`
  - PC1 프로필 정보를 PC3가 전달하면 주간 루틴을 생성합니다.
  - 주간 개요 생성 뒤 각 day 상세를 다시 생성해 최종 `weekly_routine` 전체를 한 번에 반환합니다.
  - 이 경로는 primary LLM 전용입니다.

- `GET /api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD`
  - 저장된 날짜별 루틴을 조회해 특정 일자의 루틴과 안내 메시지를 반환합니다.

## 3. 런타임 흐름 변경

- 권장 실행 순서는 `PostgreSQL -> fallback vLLM -> PC2 API`입니다.
- `/api/coach/generate`는 primary LLM 없이도 로컬 fallback으로 동작할 수 있습니다.
- `/api/routine/profile`은 primary LLM 설정과 응답 파싱이 정상이어야 하며, 실패 시 `503`을 반환합니다.
- PC1은 PC3를 통해 PC2를 호출하고, PC3는 PC2 응답을 다시 PC1에 전달하는 중계 흐름을 사용합니다.

