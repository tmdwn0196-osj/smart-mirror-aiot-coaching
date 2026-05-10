# PC2 가이드

이 문서는 현재 프로젝트의 PC2 서버 구조, 실행 방법, 환경변수 처리 방식, PC3 연동 방법을 한글로 정리한 안내서입니다.

## 1. PC2가 하는 일

PC2는 `exercise` 전용 운동 계획 생성 서버입니다.

역할은 다음과 같습니다.

- PC3가 계산한 운동 feature를 입력으로 받음
- 사용자별 baseline을 저장하고 조회함
- 현재 운동 상태와 baseline 차이를 계산함
- 로컬 운동 지식 컨텍스트를 검색함
- LLM 또는 로컬 규칙 기반 fallback으로 운동 계획표를 생성함
- 결과를 DB에 기록하고 PC3에 JSON으로 반환함

현재 지원 운동 타입은 아래 5개입니다.

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

## 2. 프로젝트 구조

핵심 디렉터리:

- `pc2_coach_server/app/`
  서버 코드
- `pc2_coach_server/docs/`
  연동 문서
- `pc2_coach_server/scripts/`
  실행 및 스모크 테스트 스크립트
- `pc2_coach_server/data/`
  SQLite DB 등 로컬 데이터
- `prompt/`
  발표/정리용 문서와 다이어그램

핵심 파일:

- `pc2_coach_server/app/main.py`
  FastAPI 엔드포인트와 전체 흐름 오케스트레이션
- `pc2_coach_server/app/schemas/coaching.py`
  요청/응답 스키마
- `pc2_coach_server/app/exercise_planning.py`
  baseline 계산, 로컬 지식 검색, 계획 보조 로직
- `pc2_coach_server/app/signal_service.py`
  운동 신호 해석
- `pc2_coach_server/app/llm_client.py`
  LLM 호출
- `pc2_coach_server/app/db.py`
  DB 저장/조회

## 3. 실행 방법

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
cp ../.env.example .env
./scripts/run_pc2.sh
```

기본 실행 주소:

- `http://0.0.0.0:7000`

상태 확인:

```bash
curl http://127.0.0.1:7000/health
```

## 4. 환경변수 처리 방식

환경변수가 없거나 비어 있어도 서버는 동작하도록 처리되어 있습니다.

기본 원칙:

- `pc2_coach_server/.env`를 우선 로드
- `.env`가 없어도 실행 가능
- 값이 비어 있으면 안전한 기본값 사용
- 숫자형 env가 잘못되어도 기본값으로 복구
- LLM 설정이 없거나 호출 실패 시 로컬 규칙 기반 fallback 사용

기본값 예시:

- `HOST=0.0.0.0`
- `PORT=7000`
- `SERVICE_NAME=pc2-coach-api`
- `DB_PATH=./data/pc2_coach.db`
- `PRIMARY_LLM_BASE_URL=https://integrate.api.nvidia.com/v1`
- `PRIMARY_LLM_MODEL_NAME=google/gemma-4-31b-it`

권장:

- 루트의 `.env.example`을 복사해 `pc2_coach_server/.env`로 사용
- legacy 변수(`NVIDIA_API_KEY`, `LLM_*`, `VLLM_*`)는 호환용으로만 사용

## 5. LLM이 없어도 동작하는 방식

현재 서버는 아래 경우에도 `/api/coach/generate` 요청을 처리합니다.

- `PRIMARY_LLM_API_KEY` 없음
- fallback LLM 설정 없음
- 외부 네트워크 실패
- LLM 응답 파싱 실패

이 경우 PC2는 로컬 규칙 기반 계획 생성으로 자동 전환합니다.

즉:

- 서버는 뜸
- baseline 저장 가능
- 운동 계획 생성 가능
- 단지 `served_by=local` 성격의 fallback 응답이 생성됨

`/health`에서는 `local_fallback.status = ok`가 함께 표시됩니다.

## 6. API 목록

### 6-1. baseline 저장

```http
POST /api/exercise/baseline
```

### 6-2. 최신 baseline 조회

```http
GET /api/exercise/baseline/{user_id}?exercise_type=squat
```

### 6-3. 운동 계획 생성

```http
POST /api/coach/generate
```

### 6-4. 로그 조회

```http
GET /api/coach/logs/{user_id}?limit=10
```

- `limit`는 `1` 이상 `100` 이하

### 6-5. 상태 확인

```http
GET /health
```

## 7. PC3 연동 방식

PC3는 원본 이미지가 아니라 구조화된 운동 feature만 PC2로 보냅니다.

호출 규칙:

- `mode`는 항상 `exercise`
- `event`는 항상 `session_completed`
- `features.exercise`와 `features.exercise.type`을 반드시 포함
- 실시간 프레임마다 호출하지 않음
- 세션 종료 시점에 1회 호출

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
  "purpose": "운동 계획 생성"
}
```

## 8. PC2 응답 방식

PC2는 다음 정보를 반환합니다.

- `summary`
- `priority`
- `exercise_plan`
- `mirror_message`
- `warnings`
- `pc2_payload`

`pc2_payload`는 미러/화면 표시용으로 바로 쓸 수 있습니다.

## 9. DB에 저장되는 내용

PC2는 생성 이력을 SQLite에 저장합니다.

저장 항목:

- 원본 요청 payload
- detected signals
- baseline snapshot
- analysis context
- LLM prompt
- raw LLM response
- 최종 응답
- PC2 표시용 payload

## 10. 스모크 테스트

기본 테스트:

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
../.venv/bin/python -m unittest -q
```

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
../.venv/bin/python scripts/smoke_pc2.py --base-url http://127.0.0.1:7000
```

## 11. 참고 문서

- `PC3_PC2_INTEGRATION.md`
  PC3 담당자 전달용 연동 명세
- `pc2_coach_server/README.md`
  서비스 개요
- `pc2_coach_server/docs/pc3_payload_request.md`
  PC3 요청 형식
- `pc2_coach_server/docs/pc2_integration_guide.md`
  PC2 연결 가이드
- `pc2_coach_server/docs/pc2_prompt_contract.md`
  prompt/payload 계약
