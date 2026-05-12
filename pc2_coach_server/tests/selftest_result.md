# PC2 Self Test Result (Archived)

실행일: 2026-05-11

이 문서는 과거 시점의 self-test 수행 결과를 보관한 아카이브입니다.
현재 기준 문서는 `tests/selftest.md`이며, 이 파일의 수치와 설정은 최신 코드/운영 기준과 다를 수 있습니다.

## 1. 테스트 환경

작업 디렉터리:

```bash
/home/osj/smart-mirror-aiot-coaching/pc2_coach_server
```

테스트 서버:

```bash
127.0.0.1:7000
```

확장 HTTP 점검은 당시 재현성을 위해 아래 설정으로 실행했다.

```bash
DB_PATH=/tmp/pc2_extended_selftest.db
PRIMARY_LLM_API_KEY=
NVIDIA_API_KEY=
LLM_API_KEY=
FALLBACK_LLM_ENABLED=false
FALLBACK_LLM_API_KEY=
```

의도:

- 외부 LLM 응답 시간과 품질에 묶이지 않게 함
- 로컬 규칙 fallback 경로에서 PC3 payload 계약을 빠르게 검증함
- 실제 PC3 연결 전 PC2의 입력 수용 범위와 거부 조건을 확인함

## 2. 유닛 테스트 결과

실행 명령:

```bash
../.venv/bin/python -m unittest -q
```

결과:

```text
Ran 11 tests in 0.980s
OK
```

주의:

- 현재 테스트 개수와 다를 수 있습니다.
- 현재 표준 실행 문서는 fallback vLLM Docker 포함 순서를 기준으로 설명합니다.

판정:

- 통과

확인 범위:

- baseline 생성
- 정상 계획 생성
- 잘못된 event 거부
- 필수 exercise payload 누락 거부
- baseline sample type 불일치 거부
- LLM 실패 시 local fallback
- fallback plain message 처리
- 로그 저장
- output validator 동작

## 3. 기본 HTTP self-test 결과

서버 실행:

```bash
/home/osj/smart-mirror-aiot-coaching/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 7000
```

샌드박스 환경에서는 포트 바인딩과 Python `requests` 로컬 접속에 승인 권한이 필요했다.

### 3-1. Health

요청:

```bash
GET /health
```

결과:

- `200 OK`
- `service=pc2-coach-api`
- `local_fallback.status=ok`

판정:

- 통과

### 3-2. Baseline 저장

요청:

```bash
POST /api/exercise/baseline
```

결과:

- `200 OK`
- `baseline_id` 생성
- `exercise_type=squat`
- `baseline_profile` 집계값 생성

판정:

- 통과

### 3-3. 운동 계획 생성

요청:

```bash
POST /api/coach/generate
```

결과:

- `200 OK`
- `summary` 반환
- `priority` 반환
- `exercise_plan` 반환
- `mirror_message` 반환
- `pc2_payload.message` 반환

판정:

- 통과

### 3-4. 로그 조회

요청:

```bash
GET /api/coach/logs/exercise_user?limit=10
```

결과:

- `200 OK`
- `detected_signals` 저장 확인
- `analysis_context` 저장 확인
- `baseline_snapshot` 저장 확인
- `pc2_output` 저장 확인
- `final_response` 저장 확인
- `llm_route`, `fallback_used`, `primary_error` 기록 확인

판정:

- 통과

### 3-5. 입력 검증 실패

잘못된 event:

- 요청: `event=frame_update`
- 결과: `422`
- 판정: 통과

exercise payload 누락:

- 요청: `features.exercise` 누락
- 결과: `422`
- 판정: 통과

baseline sample type 불일치:

- 요청: `exercise_type=squat`, `samples[0].type=pushup`
- 결과: `422`
- 판정: 통과

## 4. PC3 연결 전 확장 점검 결과

확장 점검은 PC3 mock payload를 직접 PC2에 보내는 방식으로 수행했다.

요약:

```text
SUMMARY passed=47 failed=0 total=47
```

판정:

- 통과

### 4-1. 지원 운동 5종 generate

대상:

- `squat`
- `jumping_jack`
- `knee_raise`
- `lunge`
- `pushup`

결과:

- 5개 운동 모두 `200`
- 모두 `CoachingResponse` key 반환
- 모두 `pc2_payload.message` 반환

판정:

- 통과

### 4-2. baseline 없는 신규 사용자

대상:

- `user_id=no_baseline_user`

결과:

- `200`
- baseline 없음 warning 확인
- `pc2_payload.message` 생성 확인

확인된 warning:

```text
저장된 baseline이 없어 현재 입력만으로 계획을 생성했습니다.
```

판정:

- 통과

### 4-3. baseline_diff 포함/생략 비교

대상:

- `baseline_diff` 생략
- `baseline_diff.exercise.count_change`, `stability_change` 포함

결과:

- 둘 다 `200`
- 둘 다 `CoachingResponse` key 반환
- 둘 다 `pc2_payload.message` 반환

판정:

- 통과

### 4-4. count-only payload

대상:

- `rep_count` 없이 `count`만 포함

결과:

- `200`
- 응답 형식 정상
- `pc2_payload.message` 반환

판정:

- 통과

### 4-5. duration_seconds-only payload

대상:

- `duration_sec` 없이 `duration_seconds`만 포함

결과:

- `200`
- 응답 형식 정상
- `pc2_payload.message` 반환

판정:

- 통과

### 4-6. environment warning

대상:

```json
{
  "environment": {
    "illuminance": 80,
    "humidity": 82
  }
}
```

결과:

- `200`
- 낮은 조도 warning 확인
- 높은 습도 signal이 로그 `detected_signals`에 저장됨

확인된 warning:

```text
조도가 낮아 비전 feature 신뢰도가 낮을 수 있습니다.
```

확인된 signal category:

```text
humidity
```

판정:

- 통과

### 4-7. 잘못된 운동 타입

대상:

```json
{
  "features": {
    "exercise": {
      "type": "burpee"
    }
  }
}
```

결과:

- `422`
- literal validation error 반환

응답 요지:

```text
Input should be 'squat', 'jumping_jack', 'knee_raise', 'lunge' or 'pushup'
```

판정:

- 통과

### 4-8. extra field 거부

대상:

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

결과:

- `422`
- `extra_forbidden` 반환

응답 요지:

```text
Extra inputs are not permitted
```

판정:

- 통과

### 4-9. 로그 추적성

확인 항목:

- `detected_signals`
- `analysis_context`
- `baseline_snapshot`
- `pc2_output`
- `final_response`
- `llm_route`

결과:

- 성공한 generate 요청 로그 저장 확인
- `422` 요청은 FastAPI 요청 검증 단계에서 거부되므로 coach log에 남지 않을 수 있음

판정:

- 통과

## 5. Smoke Test 결과

실행 명령:

```bash
/home/osj/smart-mirror-aiot-coaching/.venv/bin/python scripts/smoke_pc2.py --base-url http://127.0.0.1:7000
```

결과:

```text
baseline 저장 응답 200
운동 계획 응답 200
```

운동 계획 응답은 LLM 비활성 설정에서 로컬 규칙 fallback으로 생성되었다.

확인된 주요 응답:

```text
summary=환경변수 없이도 동작하도록 로컬 규칙 기반 운동 계획을 생성했습니다.
priority=무릎 정렬 안정화
pc2_payload.message=무릎 정렬 안정화부터 잡고 4세트만 정확히 진행하세요.
```

판정:

- 통과

## 6. 최종 판정

PC2 단독 self-test 결과:

- 통과

PC3 연결 전 확인된 상태:

- PC2 서버 기동 가능
- baseline 저장 가능
- 5개 지원 운동 타입 모두 generate 가능
- baseline 없는 사용자도 처리 가능
- `baseline_diff` 포함/생략 모두 처리 가능
- `count` only, `duration_seconds` only payload 처리 가능
- 환경 warning 및 signal 기록 가능
- 잘못된 운동 타입은 `422`로 거부
- 계약에 없는 extra field는 `422 extra_forbidden`으로 거부
- 성공 요청은 로그 추적 가능
- LLM이 없어도 `CoachingResponse` JSON 형식 유지

## 7. 주의 사항

현재 PC2 스키마는 `extra="forbid"`다.

따라서 PC3가 아래 같은 계약 외 필드를 보내면 `422`로 거부된다.

- `landmarks`
- `frame_path`
- `image`
- `base64`
- `segmentation_mask`
- `camera_stream_url`
- 기타 `FeaturePayload`에 정의되지 않은 필드

PC3 연결 전에는 PC3가 실제로 보내는 JSON이 `FeaturePayload` 계약과 일치하는지 반드시 확인해야 한다.

PC3 연결값 기준:

```env
PC2_COACH_API_URL=http://<PC2_HOST>:7000/api/coach/generate
```

PC3는 운동 세션 종료 시점에만 호출해야 한다.

```text
mode=exercise
event=session_completed
```
