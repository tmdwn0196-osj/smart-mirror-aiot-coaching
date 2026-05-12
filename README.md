# smart-mirror-aiot-coaching

스마트 미러 AIoT 코칭 작업용 저장소입니다.

이 저장소는 서버 코드만 있는 단일 앱 저장소가 아니라, 아래 내용을 함께 관리하는 워크스페이스입니다.

- `pc2_coach_server/`
  PC2 운동 계획 및 프로필 루틴 API 서버 코드
- `prompt/`
  발표/정리용 프롬프트 문서와 다이어그램
- `PC3_PC2_INTEGRATION.md`
  PC3 연동용 통합 문서
- `pc2_GUIDE.md`
  PC2 구조/운영 가이드

## 주요 실행 대상

실제로 실행하고 테스트하는 대상은 `pc2_coach_server/`입니다.

상세 실행 방법과 API 설명은 아래 문서를 기준으로 봅니다.

- [pc2_coach_server/README.md](/home/osj/smart-mirror-aiot-coaching/pc2_coach_server/README.md)
- [pc2_GUIDE.md](/home/osj/smart-mirror-aiot-coaching/pc2_GUIDE.md)

## 빠른 시작

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
cp ../.env.example .env
../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 7000
```

기본 테스트:

```bash
cd /home/osj/smart-mirror-aiot-coaching/pc2_coach_server
../.venv/bin/python -m unittest -q
```
