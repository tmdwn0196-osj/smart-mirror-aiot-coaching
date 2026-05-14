# 변경 이력

이 문서는 이 저장소의 변경 이력을 현재 Git 기준으로 정리한 파일입니다.
PC3 저장소 문서 스타일에 맞춰 저장소 기준 정보와 주요 변경을 날짜/커밋 단위로 간결하게 정리합니다.

## 저장소 기준

- 현재 브랜치: `main`
- 현재 HEAD: `df12985ca0140c6cee2fa0f9a983f4641e86e9c3`
- `origin/main`: `df12985ca0140c6cee2fa0f9a983f4641e86e9c3`
- origin URL: `https://github.com/tmdwn0196-osj/smart-mirror-aiot-coaching.git`
- 기준 명령: `git log --date=iso-strict --format="%h %ad %s"`

## 커밋 이력

### 미커밋 작업

아직 커밋하지 않았지만 현재 워크트리에 반영된 주요 변경은 아래와 같습니다.

- PC2 primary 모델 기본값을 NVIDIA hosted `mistralai/mistral-nemotron`으로 변경했습니다.
- `PRIMARY_LLM_TIMEOUT_SECONDS`, `ROUTINE_PROFILE_TIMEOUT_SECONDS`, `REQUEST_DEADLINE_SECONDS`, `ROUTINE_DAY_DETAIL_TIMEOUT_SECONDS` 기본값을 상향해 primary LLM을 더 현실적으로 사용할 수 있게 조정했습니다.
- `llm_client`에서 `reasoning_content`만 있고 최종 `content`가 없는 provider 응답을 즉시 예외 처리하도록 바꿨습니다.
- `/api/routine/profile`은 primary 호출 실패나 파싱 실패 시 `503`으로 종료하지 않고 local rule fallback 루틴을 반환하도록 바뀌었습니다.
- profile routine day 상세 확장은 전체 요청 deadline 안에서 남은 시간 기준으로 재시도하도록 조정했습니다.
- 테스트 헬퍼가 `postgresql+psycopg://` DSN과 `psycopg.connect()`를 함께 처리하도록 보정했습니다.
- PostgreSQL 연결 기준 전체 `unittest` 26개를 다시 실행해 통과를 확인했습니다.
- no-LLM 모드로 `scripts/smoke_pc2.py`를 다시 실행해 baseline, generate, duplicate session, logs, `422` rejection까지 통과를 확인했습니다.

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
