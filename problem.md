# LLM Failure Analysis

## 목적

이 문서는 PC2에서 시도한 모델들과 각 실패 원인을 정리한 메모입니다.
주 대상은 아래 두 endpoint입니다.

- `POST /api/coach/generate`
- `POST /api/routine/profile`

기준 환경:

- PC2 API: `pc2_coach_server`
- 로컬 GPU: `RTX 4060 Laptop 8GB`
- 로컬 서빙: `vLLM OpenAI-compatible API`

---

## 요약

현재까지의 결론은 아래와 같습니다.

- 현재 기본 primary 모델은 NVIDIA hosted `mistralai/mistral-nemotron`으로 다시 맞춰 둔 상태다.
- 2026-05-14 기준 NVIDIA Build 페이지 `https://build.nvidia.com/mistralai/mistral-nemotron`와 API reference 기본 모델명이 `mistralai/mistral-nemotron`으로 안내된다.
- `Ctrl+C`로 프로세스가 중단되더라도 코드/문서 변경은 워크스페이스에 남으므로, 재기동 시 `.env`와 `app/config.py` 기준 모델값만 다시 확인하면 된다.
- `LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct`는 로컬 vLLM에서 기동 가능하다.
- 하지만 `coach/generate`에서는 JSON 스키마 안정성이 부족해 자주 `local fallback JSON`으로 떨어진다.
- 같은 모델이라도 `routine/profile`은 비교적 잘 동작한다.
- `minimaxai/minimax-m2.7`는 NVIDIA `chat.completions` 경로에서 `content` 없이 `reasoning_content`만 반환하는 사례가 확인됐다.
- 그래서 MiniMax M2.7의 primary parsing 실패는 파서보다 provider 응답 형태 문제에 가깝다.
- `Qwen/Qwen2.5-1.5B-Instruct-AWQ`는 fallback 한 줄 응답 용도로는 되지만, primary 대체에는 맞지 않는다.
- Hugging Face 공용 router/serverless API에서는 `EXAONE-3.5-2.4B-Instruct`가 지원되지 않았다.
- Hugging Face Inference Endpoint는 가능하지만 무료가 아니다.

---

## 모델별 분석

### 1. NVIDIA primary: `mistralai/mistral-nemotron`

시도 방식:

- `PRIMARY_LLM_BASE_URL=https://integrate.api.nvidia.com/v1`
- `PRIMARY_LLM_MODEL_NAME=mistralai/mistral-nemotron`

관찰:

- `/health`에서는 정상 인식된다.
- 2026-05-14 smoke 중 실제 `POST /api/coach/generate` 호출에서는 NVIDIA provider가 `400`과 함께 `DEGRADED function cannot be invoked`를 반환한 사례가 있었다.
- `routine/profile` 쪽에서 timeout이 발생한 적이 있다.
- `coach/generate` 자체는 primary -> fallback -> local fallback 체인의 일부로 동작했다.

실패 원인:

- 모델 자체 불능보다는 외부 API 응답 지연/timeout 이슈에 가깝다.
- 로컬 GPU와 무관한 외부 provider latency 영향이 있다.
- provider health는 `ok`여도 실제 inference 함수가 `DEGRADED` 상태면 호출이 실패할 수 있다.

판정:

- 구조적으로는 문제 없다.
- 다만 외부 API 의존이라 속도/비용/안정성 측면에서 로컬 EXAONE 검토가 시작됐다.
- NVIDIA 문서상 `chat/completions` 기본 모델이 `mistralai/mistral-nemotron`으로 안내된다.
- 현재 기준 기본 primary 선택지는 `mistralai/mistral-nemotron`이다.

---

### 1-1. NVIDIA primary: `minimaxai/minimax-m2.7`

시도 방식:

- `PRIMARY_LLM_BASE_URL=https://integrate.api.nvidia.com/v1`
- `PRIMARY_LLM_MODEL_NAME=minimaxai/minimax-m2.7`
- fallback Qwen 활성화 상태에서 `coach/generate`, `routine/profile` 재시험

기존 관찰:

- `/health`에서는 정상 인식된다.
- `coach/generate`는 최종적으로 fallback 또는 local fallback JSON으로 귀결됐다.
- `routine/profile`도 최종적으로 local routine fallback JSON으로 내려간 적이 있다.

raw 응답 직접 검증:

- `build_profile_routine_prompt(...)`로 만든 실제 프롬프트를 MiniMax에 직접 넣어 확인했다.
- `response_format={"type":"json_object"}`를 줘도 `message.content`는 `None`이었다.
- 대신 `message.reasoning_content`에 긴 내부 추론 텍스트만 들어갔다.
- `finish_reason`은 1차, 2차 호출 모두 `length`였다.

직접 확인값:

- 1차 호출
  - `content=None`
  - `reasoning_content` 길이 약 `3102`
  - `finish_reason="length"`
- 2차 호출
  - reasoning trace를 assistant로 넣고 "최종 JSON만 반환"을 다시 요청해도 동일
  - `content=None`
  - `reasoning_content` 길이 약 `2655`
  - `finish_reason="length"`

추가 확인:

- `reasoning_content` 내부에는 `{` 자체가 없었고 최종 JSON이 숨겨져 있지도 않았다.
- `/no_think`를 user prompt에 넣은 기존 방식도 효과가 없었다.
- `/no_think`를 system prompt 앞에 붙여도 결과는 동일했다.
- NVIDIA MiniMax 경로에서 `completions` endpoint 우회는 `404`였다.

실패 원인:

- 이 조합에서는 모델이 구조화 최종 답변 대신 reasoning trace 생성에 토큰을 다 사용한다.
- 그래서 `parse_profile_routine_json(...)`이나 `parse_coaching_json(...)`이 읽을 `message.content`가 아예 비어 있다.
- parse 실패는 후단 증상이고, 근본 원인은 provider response shape mismatch다.

적용한 수정:

- [pc2_coach_server/app/llm_client.py](/home/osj/smart-mirror-aiot-coaching/pc2_coach_server/app/llm_client.py:135)
- `reasoning_content`만 있고 `content`가 비어 있는 경우를 명시적으로 감지하도록 변경
- 더 이상 이 응답을 빈 문자열로 넘겨 늦게 파싱 실패시키지 않고
- 즉시 `structured JSON output is unavailable on this route` 예외를 올리게 했다

검증 결과:

- `call_primary_profile_routine_llm(...)`
  - `minimaxai/minimax-m2.7 returned reasoning_content without final content; structured JSON output is unavailable on this route.`
- `call_llm_with_fallback(...)`
  - `served_by=fallback`
  - `fallback_used=True`

판정:

- 현재 NVIDIA MiniMax M2.7 chat route는 PC2의 strict JSON primary로 부적합
- 자유 텍스트 응답에는 쓸 수 있어도 `routine/profile` 같은 structured endpoint에는 맞지 않다

---

### 2. fallback vLLM: `Qwen/Qwen2.5-1.5B-Instruct-AWQ`

시도 방식:

- `pc2_coach_server/docker-compose.vllm.yml`
- `max_model_len=256`
- fallback 응답은 짧은 한 줄 한국어 문장용

관찰:

- `/v1/models` 정상 응답
- fallback 경로 자체는 정상 동작
- 하지만 `coach/generate`에서 prompt가 조금만 길어져도 바로 context 초과가 났다

대표 증상:

- `This model's maximum context length is 256 tokens ...`

실패 원인:

- 설계상 fallback 문장 한 줄 생성용이라 context 창이 너무 작다.
- primary 대체 모델로 쓸 수 있는 구조가 아니다.

판정:

- fallback 용도는 맞음
- primary 용도는 부적합

---

### 3. 로컬 primary vLLM: `LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct`

시도 방식:

- `pc2_coach_server/docker-compose.primary.exaone.yml`
- `trust_remote_code=true`
- `enforce_eager=true`
- `max_model_len`은 `1024`, `2048`, `4096`을 각각 시험

관찰:

- vLLM이 `ExaoneForCausalLM`으로 아키텍처를 정상 해석했다.
- `/v1/models` 응답 정상
- 직접 `chat/completions` 호출 정상
- `response_format={"type":"json_object"}` 직접 호출도 정상

즉:

- 모델 기동 자체는 성공
- 기본적인 OpenAI 호환 API 응답도 성공

#### 3-1. `max_model_len=1024`

관찰:

- 서버는 올라옴
- 하지만 PC2 요청에서 길이 제한에 자주 걸림

대표 증상:

- `max_tokens=1800 cannot be greater than max_model_len=1024`
- `input + output > 1024`

실패 원인:

- `routine/profile`는 `ROUTINE_PROFILE_MAX_TOKENS=1800` 기본값과 맞지 않음
- `coach/generate`도 입력 프롬프트가 길어서 여유가 부족함

판정:

- PC2 기본 설정과는 부적합

#### 3-2. `max_model_len=4096`

관찰:

- 길이 제한 문제는 사라짐
- 그러나 PC2 기준 `coach/generate`, `routine/profile`에서 timeout이 발생함

대표 증상:

- `Request timed out.`

실패 원인:

- 2.4B 모델이라도 긴 구조화 JSON 생성은 시간이 걸림
- 특히 `routine/profile`은 본문 생성 후 day detail 확장까지 반복 호출이 있어 총 latency가 크다

판정:

- 가능은 하나 timeout 튜닝 필수

---

## 현재 적용 상태

현재 코드 기본값은 아래처럼 정리돼 있다.

- [pc2_coach_server/app/config.py](/home/osj/smart-mirror-aiot-coaching/pc2_coach_server/app/config.py:60)
  - `PRIMARY_LLM_MODEL_NAME="mistralai/mistral-nemotron"`
  - `LLM_TIMEOUT_SECONDS=10`
  - `ROUTINE_PROFILE_TIMEOUT_SECONDS=10`
  - `REQUEST_DEADLINE_SECONDS=20`
  - `LLM_MAX_RETRIES=0`
- [pc2_coach_server/.env.example](/home/osj/smart-mirror-aiot-coaching/pc2_coach_server/.env.example:10)
  - 운영 기본 예시도 같은 Mistral Nemotron 모델 기준으로 맞춰 둠

의도:

- primary는 NVIDIA hosted `mistralai/mistral-nemotron`을 우선 사용
- 실패 시 짧은 timeout 안에 빠르게 이탈
- fallback vLLM 또는 local rule-based 응답으로 서비스 가용성을 유지

---

## Provider 장애 해결법

여기서 provider 장애는 아래를 포함한다.

- NVIDIA API timeout
- provider 모델 응답 shape 불일치
- provider health는 살아 있지만 실제 structured JSON 생성 실패
- 일시적 rate limit 또는 외부 latency 급증

실제 대응 순서는 아래처럼 가져간다.

### 1. 가장 먼저 확인할 것

- `PRIMARY_LLM_BASE_URL`
- `PRIMARY_LLM_MODEL_NAME`
- `PRIMARY_LLM_API_KEY` 또는 `NVIDIA_API_KEY`
- `/health`가 아니라 실제 `chat/completions` JSON 응답이 나오는지

핵심:

- `/health` 정상만으로 충분하지 않다.
- provider가 살아 있어도 `message.content` 없이 `reasoning_content`만 주면 PC2 structured endpoint에서는 실패다.

### 2. Mistral Nemotron 기준 장애 완화 방법

- timeout을 짧게 유지한다.
  - 현재 `LLM_TIMEOUT_SECONDS=10`
  - `ROUTINE_PROFILE_TIMEOUT_SECONDS=10`
  - `REQUEST_DEADLINE_SECONDS=20`
- retry를 무리하게 늘리지 않는다.
  - 현재 `LLM_MAX_RETRIES=0`
  - 긴 외부 timeout 재시도는 총 지연만 키우고 UX를 망친다.
- `routine/profile`은 실패 시 `503`로 죽이지 말고 local fallback routine으로 내려 서비스는 계속 살린다.

현재 primary가 `mistralai/mistral-nemotron`으로 바뀐 뒤에도 원칙은 동일하다.

- provider가 느리거나 `DEGRADED function cannot be invoked`를 반환하면 local fallback으로 즉시 이탈
- smoke 또는 운영 확인은 no-LLM 모드에서도 먼저 통과시켜 API/DB 경로와 fallback 경로를 분리 검증

### 3. provider response shape mismatch 대응

MiniMax 사례처럼 아래 증상이 나오면 provider incompatibility로 본다.

- `message.content is None`
- `message.reasoning_content`만 존재
- `finish_reason="length"`

이 경우 해결 원칙:

- 파서 보정으로 억지 복구하지 않는다.
- [pc2_coach_server/app/llm_client.py](/home/osj/smart-mirror-aiot-coaching/pc2_coach_server/app/llm_client.py:135)처럼 즉시 예외 처리한다.
- structured JSON endpoint의 primary 모델에서 제외한다.
- 구조화 JSON 응답이 안정적이면 `mistralai/mistral-nemotron`을 유지하고, shape mismatch가 재발하면 다른 안정 모델로 되돌린다.

### 4. 외부 provider 자체가 느리거나 자주 죽을 때

대응 옵션은 우선순위가 있다.

1. `mistralai/mistral-nemotron` 유지 + timeout 짧게 + local fallback 유지
2. 운영 비용/지연이 문제면 managed endpoint로 이동
3. 완전 자급형이 필요하면 EXAONE 로컬/전용 endpoint 별도 운영

운영 판단:

- 안정성이 우선이면 현재처럼 Mistral Large + fallback 체인이 가장 단순하다.
- 안정성이 우선이면 현재처럼 `mistralai/mistral-nemotron` + local fallback 체인이 가장 단순하다.
- 비용 절감이 우선이면 EXAONE endpoint를 별도로 세우되, structured JSON 안정성 검증을 다시 해야 한다.

### 5. 재기동 후 복구 체크리스트

`Ctrl+C` 등으로 프로세스가 꺼진 뒤 다시 이어갈 때는 아래만 보면 된다.

1. `pc2_coach_server/.env` 또는 기본값에서 `PRIMARY_LLM_MODEL_NAME` 확인
2. fallback vLLM 포트 `8000` 살아 있는지 확인
3. primary provider 실제 `chat/completions` 호출 확인
4. `POST /api/coach/generate`와 `POST /api/routine/profile` 둘 다 smoke test
5. provider가 불안정하면 모델을 다시 바꾸기 전에 timeout/fallback 동작부터 확인

#### 3-3. `max_model_len=2048` + timeout/token 튜닝

튜닝값 예시:

- `LLM_MAX_TOKENS=500`
- `PRIMARY_LLM_TIMEOUT_SECONDS=35`
- `ROUTINE_PROFILE_MAX_TOKENS=900`
- `ROUTINE_PROFILE_TIMEOUT_SECONDS=60`
- `ROUTINE_DAY_DETAIL_TIMEOUT_SECONDS=10`
- `REQUEST_DEADLINE_SECONDS=120`

관찰:

- `routine/profile`는 primary JSON 성공
- `coach/generate`는 여전히 불안정

실측:

- `/api/coach/generate`: 약 `16~21초`
- `/api/routine/profile`: 약 `40~59초`

실패 원인:

- `coach/generate` prompt가 길고 요구 스키마가 복잡하다
- EXAONE 2.4B가 `routine/profile`보다 `coach/generate`에서 더 흔들린다

판정:

- `routine/profile`: 실사용 가능성 있음
- `coach/generate`: 아직 불안정

---

### 4. Hugging Face router/serverless API + EXAONE

시도 방식:

- `https://router.huggingface.co/v1/chat/completions`
- 모델: `LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct`

관찰:

- 요청 자체는 갔지만 모델 지원 에러 반환

대표 증상:

- `The requested model 'LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct' is not supported by any provider you have enabled.`

실패 원인:

- Hugging Face 공용 provider/router 쪽에서 해당 모델을 hosted provider로 제공하지 않음

판정:

- 공용 무료/서버리스 API 경로는 불가

---

## endpoint별 상세 원인

### `POST /api/coach/generate`

현재 가장 큰 문제 endpoint.

문제 패턴은 세 가지였다.

1. context overflow

- prompt 고정 문구를 늘리면 곧바로 `2048` 한도를 넘음
- 예: 입력 약 `1549` + 출력 `500` => 최소 `2049`

2. LLM parse failed

- 로그:
  - `LLM 응답에서 JSON 객체를 찾지 못했습니다.`
  - `LLM 응답에 사용할 수 있는 내용이 없습니다.`

이 의미:

- 모델이 JSON이 아닌 자연어를 냈거나
- JSON처럼 보여도 추출 가능한 `{...}` 객체가 없었거나
- JSON이 있어도 `summary`, `priority`, `mirror_message`, `pc2_payload.message`, `exercise_plan` 중 쓸 만한 값이 비어 있었다

3. local fallback 강제 전환

- 위 두 문제로 인해 결국 `build_local_plan_response(...)` 결과가 내려감
- 그래서 응답은 계속 JSON이지만, primary 성공 JSON이 아니라 로컬 규칙 기반 결과가 내려간다

핵심 원인:

- `coach/generate`는 입력이 길다
- 요구 스키마가 `summary + priority + exercise_plan + mirror_message + warnings + pc2_payload`까지 넓다
- EXAONE 2.4B가 이 구조를 안정적으로 재현하지 못한다

---

### `POST /api/routine/profile`

이 endpoint는 상대적으로 성공률이 높았다.

성공 이유:

- 프롬프트가 허용 key를 더 강하게 제한함
- 운동 이름도 `squat, jumping_jack, knee_raise, lunge, pushup` 중 하나로 강제함
- day 구조도 상대적으로 일정하다

실패 패턴:

1. `max_model_len` 부족

- `ROUTINE_PROFILE_MAX_TOKENS`와 맞지 않으면 즉시 `400`

2. day detail timeout

- `_expand_profile_routine_days(...)`가 하루 단위로 다시 primary 호출
- `ROUTINE_DAY_DETAIL_TIMEOUT_SECONDS=2.5`일 때는 자주 잘렸다

해결:

- `ROUTINE_PROFILE_MAX_TOKENS=900`
- `ROUTINE_PROFILE_TIMEOUT_SECONDS=60`
- `ROUTINE_DAY_DETAIL_TIMEOUT_SECONDS=10`
- `REQUEST_DEADLINE_SECONDS=120`

결론:

- EXAONE 2.4B로도 `routine/profile`은 비교적 현실적이다

---

## 왜 `coach`는 실패하고 `profile`은 되나

차이는 두 가지다.

1. prompt 구조

- `profile`은 허용 key, allowed exercise, 예시 구조가 더 엄격하다
- `coach`는 입력 컨텍스트가 더 길고 요구 output이 넓다

2. output schema complexity

- `coach`는 한 번에 요약, 우선순위, 운동계획, 미러 메시지, 경고, 화면 payload까지 맞춰야 한다
- `profile`은 주간 루틴 구조가 반복적이라 작은 모델이 상대적으로 맞추기 쉽다

---

## 현재 최종 판단

### 안정적

- 로컬 vLLM + EXAONE 기동
- `/health`
- 직접 OpenAI 호환 `chat/completions`
- `routine/profile` JSON 반환

### 불안정

- `coach/generate` primary JSON 파싱 성공률

### 불가능 또는 비권장

- Hugging Face 공용 router/serverless로 EXAONE 사용
- `Qwen/Qwen2.5-1.5B-Instruct-AWQ`를 primary 대체로 사용

---

## 권장 다음 단계

1. `coach/generate`는 prompt를 더 늘리기보다 입력 payload를 줄인다

- `analysis_context`
- `latest_profile_routine`
- 불필요한 feature 중복

2. `coach` 파서를 완화한다

- EXAONE가 자주 내는 변형 JSON key 허용
- `exercise_plan`이 비어도 `summary/priority/message`만으로 최소 primary 응답 허용

3. `routine/profile`과 `coach`를 다른 모델로 분리하는 것도 검토한다

- `routine/profile`: EXAONE 2.4B 유지 가능
- `coach/generate`: 더 짧고 구조화 출력이 강한 모델 필요 가능

---

## 현재 운영 메모

현재 `.env` 기준:

- primary: `http://127.0.0.1:8100/v1`
- model: `LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct`
- fallback: disabled
- `LLM_MAX_TOKENS=300`
- `PRIMARY_LLM_TIMEOUT_SECONDS=35`
- `ROUTINE_PROFILE_TIMEOUT_SECONDS=60`
- `ROUTINE_PROFILE_MAX_TOKENS=900`
- `ROUTINE_DAY_DETAIL_TIMEOUT_SECONDS=10`
- `REQUEST_DEADLINE_SECONDS=120`

PC3 timeout 권장:

- `coach/generate`: `45초`
- `routine/profile`: `90초`
- 보수적으로는 둘 다 `120초`까지 고려 가능

---

## 2026-05-14 추가 메모

- MiniMax M2.7 parsing failure는 parser bug보다 provider 응답 형태 문제로 보는 것이 맞다.
- 같은 날 PC2 API end-to-end 재검증은 호스트에서 `DATABASE_URL=127.0.0.1:5430` 연결이 `psycopg.OperationalError`로 실패해 함수 단위 검증으로 대체했다.
- 따라서 이 날짜의 MiniMax 결론은 "raw provider response 확인 + `llm_client.py` 보호 로직 추가"까지 완료된 상태다.
