# 변경 이력

이 문서는 이 저장소의 변경 이력을 현재 Git 기준으로 정리한 파일입니다.
PC3 저장소 문서 스타일에 맞춰 저장소 기준 정보와 주요 변경을 날짜/커밋 단위로 간결하게 정리합니다.

## 저장소 기준

- 현재 브랜치: `main`
- 현재 HEAD: `92fbc62b6e2ffb9dee06b706ee98ae0b915398d5`
- `origin/main`: `0cb6bcbb414f0460a63278669e2013961b98b91a`
- origin URL: `https://github.com/tmdwn0196-osj/smart-mirror-aiot-coaching.git`
- 기준 명령: `git log --date=iso-strict --format="%h %ad %s"`

## 커밋 이력

### 2026-05-15T16:32:41+09:00 `92fbc62`

`fix(pc2): 프로필 루틴 실패 시 503 계약 복원`

- `/api/routine/profile`에서 primary LLM 미설정 시 로컬 fallback 루틴을 만들지 않고 `503`과 `detail.reason=primary_llm_unconfigured`를 반환하도록 되돌렸습니다.
- primary LLM 호출 실패는 `503`과 `detail.reason=primary_llm_call_failed`로, 응답 파싱 실패는 `503`과 `detail.reason=primary_llm_parse_failed`로 구분해 반환하도록 정리했습니다.
- 프로필 루틴 관련 테스트 기대값도 local fallback 성공 응답에서 `503` 실패 계약 기준으로 수정했습니다.

### 2026-05-14T17:20:39+09:00 `0cb6bcb`

`fix(pc2): 프로필 루틴 응답 정규화`

- 프로필 루틴 day 응답에서 `exercises`가 단일 객체로 와도 1개짜리 배열로 흡수하도록 정규화했습니다.
- day detail 응답의 `day_index`가 요청값과 다를 때는 요청값으로 맞춰 저장되도록 정리했습니다.
- 프로필 루틴이 계약을 조금 벗어나도 즉시 fallback으로 떨어지지 않게 검증을 완화했습니다.

### 2026-05-14T16:53:49+09:00 `1899741`

`feat(pc2): 코치 응답 형식 고정 강화`

- `coach/generate`의 system/user prompt에 JSON 계약과 금지 규칙을 더 강하게 명시했습니다.
- fallback LLM 응답도 먼저 JSON 파싱을 시도하고, JSON일 때는 구조화 응답으로 우선 처리하도록 바꿨습니다.
- JSON이 아닌 fallback만 최후 수단으로 평문 처리하도록 해서 형식 이탈 가능성을 줄였습니다.

### 2026-05-14T15:24:26+09:00 `ba3662e`

`feat(pc2): 프롬프트 압축과 루틴 호출량 최적화`

- `routine/profile`의 day-detail 확장을 첫 1일까지만 수행하도록 줄여서 추가 LLM 호출 수를 낮췄습니다.
- `compact_for_prompt()`에서 prompt 입력에 들어가는 분석 문맥을 더 압축했습니다.
- `coach/generate`와 `routine/profile` prompt 문구를 줄이되 `mode`, `event`, `features.exercise`, `available_days_per_week`, `latest_profile_routine` 같은 핵심 변수는 유지했습니다.
- `routine/profile` day별 상세 생성 기본 문구를 간결하게 조정해 응답 길이와 토큰 사용량을 낮췄습니다.
- `test_generate_profile_routine_success_with_mocked_llm`의 기대 호출 수를 현재 동작에 맞게 조정했습니다.
- 전체 `unittest` 26개를 다시 실행해 통과를 확인했습니다.

### 2026-05-13T12:20:28+09:00 `df12985`

`docs: 변경 이력과 흐름 변경 문서에 과거 기록 반영`

- 루트 `CHANGELOG.md`, `FLOW_CHANGES.md`를 현재 Git 이력 기준으로 재구성했습니다.
- 날짜 기반 정리와 흐름 기반 정리를 분리해 문서 가독성을 높였습니다.

### 2026-05-13T12:09:30+09:00 `96d7baa`

`docs: 문서 규칙 파일 추가 및 PC1-PC3, PC3-PC2 연동 명세 보강`

- 루트 문서 `CHANGELOG.md`, `FLOW_CHANGES.md`, `SKILL.md`를 추가했습니다.
- PC1, PC3, PC2 연동 문서에 입력 범위와 `restricted_body_parts` 설명을 보강했습니다.
- 커밋/푸시 전 문서 확인 규칙을 루트 문서에 명시했습니다.

### 2026-05-13T10:48:00+09:00 `351cfef`

`docs: PC1-PC3, PC3-PC2 연동 명세에 DTO 예시 추가`

- `PC1_PC3_INTEGRATION.md`에 PC1 요청/응답 TypeScript DTO 예시를 추가했습니다.
- `PC3_PC2_INTEGRATION.md`에 PC3 요청/응답 TypeScript DTO 예시를 추가했습니다.

### 2026-05-13T10:38:17+09:00 `0c07ad3`

`feat(pc2): migrate persistence to postgres and add date-based routine scheduling`

- PC2 영속 계층을 PostgreSQL 중심 구조로 전환했습니다.
- PostgreSQL Docker 구성을 추가하고 기본 포트를 `5430`으로 정리했습니다.
- 주간 루틴 저장 외에 날짜별 day 루틴 저장 구조를 추가했습니다.
- `GET /api/routine/profile/{user_id}/day?target_date=YYYY-MM-DD` 조회 경로를 추가했습니다.
- PC1, PC3, PC2 연동 문서를 날짜 기반 루틴 흐름에 맞춰 보강했습니다.

### 2026-05-12T17:52:36+09:00 `da899dc`

`Tighten profile routine response validation`

- 프로필 루틴 응답 파서를 더 엄격하게 정리했습니다.
- 빈 응답, 일수 초과, 잘못된 운동 이름 같은 케이스를 더 강하게 검증하도록 보강했습니다.

### 2026-05-12T15:31:29+09:00 `12de0aa`

`fix(pc2): 루틴 생성 타임아웃 기본값 상향`

- 프로필 기반 루틴 생성용 타임아웃 기본값을 상향했습니다.
- 긴 주간 루틴 응답이 잘리거나 중도 실패할 가능성을 낮췄습니다.

### 2026-05-12T15:07:15+09:00 `5475a9c`

`feat(pc2): 루틴 저장과 운동 타입 제한 반영`

- 프로필 루틴 저장 로직을 추가했습니다.
- 루틴 응답에서 허용 운동 타입 제한을 반영했습니다.
- 관련 테스트와 설정을 함께 보강했습니다.

### 2026-05-12T12:10:39+09:00 `1938edf`

`chore(pc2): 불필요 파일과 환경 예시 정리`

- 불필요한 산출물과 예시 파일을 정리했습니다.
- 환경 예시와 저장소 정합성을 맞추는 정리 작업을 진행했습니다.

### 2026-05-12T12:02:20+09:00 `370afd6`

`fix(pc2): 스모크 테스트 세션 식별자 충돌 방지`

- 스모크 테스트 스크립트에서 세션 식별자 충돌을 피하도록 정리했습니다.

### 2026-05-12T11:40:34+09:00 `5bf52ff`

`docs(pc2): 실행 설정과 문서 기준 정합성 정리`

- 실행 설정과 문서 예시가 서로 어긋나지 않도록 조정했습니다.
- `.env.example`, README, 통합 문서의 기준값을 다시 맞췄습니다.

### 2026-05-12T11:26:24+09:00 `bca65e4`

`docs(pc2): fallback vLLM 표준 실행 기준 반영`

- fallback vLLM Docker 실행 기준을 문서와 환경 예시에 반영했습니다.
- PC2 운영 시 fallback LLM 사용 기준을 더 명확히 정리했습니다.

### 2026-05-12T10:39:07+09:00 `fb540c2`

`docs(pc2): PC3 요청 변수 의미 보강`

- PC3가 PC2에 보내는 요청 변수 의미를 더 자세히 문서화했습니다.
- 연동 시 필수값, 선택값, 금지값 설명을 보강했습니다.

### 2026-05-12T10:23:19+09:00 `2b26ad7`

`feat(pc2): 프로필 기반 루틴 생성 연동 추가`

- `POST /api/routine/profile` 기반의 프로필 루틴 생성 기능을 도입했습니다.
- 주간 요약, 주간 focus, day별 운동 배열, 주의사항을 포함하는 루틴 응답 구조를 추가했습니다.
- 이 경로를 primary LLM 전용으로 분리했습니다.

### 2026-05-11T12:19:48+09:00 `25b57da`

`docs(pc2): PC3 연동 및 셀프테스트 문서 보강`

- PC3 연동 문서를 보강했습니다.
- 셀프테스트 절차와 결과 문서를 추가해 실행 후 점검 흐름을 문서화했습니다.

### 2026-05-10T18:46:59+09:00 `c9794ec`

`fix(pc2): stabilize llm parsing and fallback flow`

- LLM 응답 파싱 안정성을 높였습니다.
- fallback vLLM과 local fallback 흐름을 더 안전하게 정리했습니다.
- 문서와 테스트도 함께 보강했습니다.

### 2026-05-10T16:49:20+09:00 `f3f1cb9`

`Initial commit`

- PC2 Coach API 초기 저장소를 구성했습니다.
- FastAPI 서버, DB 계층, LLM 호출 계층, 프롬프트 계층, 신호 해석 계층, 문서, 실행 스크립트, 테스트를 포함한 기본 구조를 추가했습니다.
