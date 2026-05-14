import importlib
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from unittest.mock import patch
from uuid import uuid4

import psycopg

from fastapi import HTTPException
from pydantic import ValidationError
from app.output_validator import parse_coaching_json, parse_profile_routine_json


PROJECT_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


def _psycopg_conninfo(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def _schema_url(base_url: str, schema_name: str) -> str:
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema_name}"
    return urlunsplit(parts._replace(query=urlencode(query)))


def _create_schema(base_url: str, schema_name: str):
    with psycopg.connect(_psycopg_conninfo(base_url), autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema_name}"')


def _drop_schema(base_url: str, schema_name: str):
    with psycopg.connect(_psycopg_conninfo(base_url), autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


def load_main(database_url: str):
    sys.path.insert(0, str(PROJECT_DIR))
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name)

    os.environ["DATABASE_URL"] = database_url
    os.environ["PRIMARY_LLM_API_KEY"] = ""
    os.environ["NVIDIA_API_KEY"] = ""
    os.environ["LLM_API_KEY"] = ""
    os.environ["FALLBACK_LLM_ENABLED"] = "false"
    os.environ["FALLBACK_LLM_API_KEY"] = ""

    return importlib.import_module("app.main")


class PC2ApiTests(unittest.TestCase):
    def setUp(self):
        if not TEST_DATABASE_URL:
            self.skipTest("TEST_DATABASE_URL is required for PostgreSQL tests.")
        self.schema_name = f"test_{uuid4().hex[:12]}"
        _create_schema(TEST_DATABASE_URL, self.schema_name)
        self.database_url = _schema_url(TEST_DATABASE_URL, self.schema_name)
        self.main = load_main(self.database_url)
        self.schemas = importlib.import_module("app.schemas")

    def tearDown(self):
        if TEST_DATABASE_URL:
            _drop_schema(TEST_DATABASE_URL, self.schema_name)

    def _pc3_payload(self, **overrides):
        payload = {
            "user_id": "pc3_user",
            "session_id": "pc3_session_001",
            "mode": "exercise",
            "event": "session_completed",
            "features": {
                "exercise": {
                    "type": "squat",
                    "count": 8,
                    "rep_count": 8,
                    "state": "down",
                    "stability_score": 0.64,
                    "posture_errors": ["knees_caving_in"],
                    "squat_depth": 0.49,
                    "knee_angle": 118,
                    "back_angle": "forward",
                    "duration_sec": 42,
                    "tempo": "fast",
                }
            },
            "baseline_diff": {
                "exercise": {
                    "count_change": -3,
                    "stability_change": -0.05,
                }
            },
            "environment": {
                "temperature": 24.5,
                "humidity": 48,
                "illuminance": 360,
            },
            "purpose": "하체 루틴 자세 점검 후 다음 운동 계획 생성",
        }
        payload.update(overrides)
        return payload

    def _profile_payload(self, **overrides):
        payload = {
            "user_id": "profile_user",
            "profile_name": "양하준",
            "weight_kg": 65,
            "user_goal": "운동 습관 만들기",
            "exercise_experience": "꾸준히 운동함",
            "available_days_per_week": 5,
            "restricted_body_parts": [],
            "purpose": "프로필 기반 주간 루틴 추천",
        }
        payload.update(overrides)
        return payload

    def test_create_baseline(self):
        response = self.main.create_exercise_baseline(
            self.main.ExerciseBaselineCreateRequest(
                user_id="u1",
                exercise_type="squat",
                samples=[
                    self.schemas.ExerciseFeature(
                        type="squat",
                        rep_count=12,
                        stability_score=0.82,
                        squat_depth=0.62,
                        knee_angle=96,
                        duration_sec=48,
                        tempo="controlled",
                    )
                ],
            )
        )
        self.assertEqual(response["exercise_type"], "squat")
        self.assertEqual(response["baseline_profile"]["recommended_reps"], 12)

    def test_generate_plan_success_with_mocked_llm(self):
        self.main.create_exercise_baseline(
            self.main.ExerciseBaselineCreateRequest(
                user_id="u2",
                exercise_type="squat",
                samples=[
                    self.schemas.ExerciseFeature(
                        type="squat",
                        rep_count=10,
                        stability_score=0.8,
                        squat_depth=0.6,
                        knee_angle=95,
                        duration_sec=40,
                        tempo="controlled",
                    )
                ],
            )
        )

        llm_result = {
            "content": "{\"summary\":\"테스트 요약\",\"priority\":\"무릎 정렬\",\"exercise_plan\":[{\"exercise\":\"tempo squat\",\"sets\":3,\"reps\":6,\"duration_sec\":null,\"rest_sec\":90,\"focus\":\"하강 3초 유지\",\"reason\":\"교정이 필요합니다.\"}],\"mirror_message\":\"천천히 진행하세요!\",\"warnings\":[],\"pc2_payload\":{\"message\":\"정렬부터 잡으세요.\",\"display_lines\":[\"하강 3초\",\"무릎 정렬\"]}}",
            "served_by": "primary",
            "model_name": "mock-model",
            "fallback_used": False,
            "primary_error": None,
        }

        with patch("app.services.is_primary_llm_configured", return_value=True), patch(
            "app.services.call_llm_with_fallback", return_value=llm_result
        ):
            response = self.main.generate_coaching(
                self.schemas.FeaturePayload(
                    user_id="u2",
                    session_id="s1",
                    mode="exercise",
                    event="session_completed",
                    features=self.schemas.FeatureBundle(
                        exercise=self.schemas.ExerciseFeature(
                            type="squat",
                            rep_count=8,
                            stability_score=0.64,
                            posture_errors=["knees_caving_in"],
                            squat_depth=0.49,
                            knee_angle=118,
                            back_angle="forward",
                            duration_sec=42,
                            tempo="fast",
                        )
                    ),
                )
            )
        self.assertEqual(response["priority"], "무릎 정렬")
        self.assertEqual(response["exercise_plan"][0]["exercise"], "tempo squat")

    def test_invalid_event_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self.main.generate_coaching(
                self.schemas.FeaturePayload(
                    user_id="u3",
                    session_id="s1",
                    mode="exercise",
                    event="session_completed",
                    features=self.schemas.FeatureBundle(
                        exercise=self.schemas.ExerciseFeature(type="pushup", rep_count=5)
                    ),
                ).model_copy(update={"event": "frame_update"})
            )
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("session_completed", str(ctx.exception.detail))

    def test_missing_exercise_payload_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.schemas.FeaturePayload(
                user_id="u_missing",
                session_id="s1",
                mode="exercise",
                event="session_completed",
            )
        self.assertIn("features.exercise", str(ctx.exception))

    def test_baseline_sample_type_mismatch_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.main.ExerciseBaselineCreateRequest(
                user_id="u_bad",
                exercise_type="squat",
                samples=[
                    self.schemas.ExerciseFeature(
                        type="pushup",
                        rep_count=10,
                    )
                ],
            )
        self.assertIn("samples.type", str(ctx.exception))

    def test_local_fallback_when_llm_fails(self):
        with patch("app.services.call_llm_with_fallback", side_effect=RuntimeError("forced failure")):
            response = self.main.generate_coaching(
                self.schemas.FeaturePayload(
                    user_id="u4",
                    session_id="s1",
                    mode="exercise",
                    event="session_completed",
                    features=self.schemas.FeatureBundle(
                        exercise=self.schemas.ExerciseFeature(
                            type="pushup",
                            rep_count=5,
                            stability_score=0.6,
                            back_angle="forward",
                            duration_sec=20,
                            tempo="fast",
                        )
                    ),
                )
            )
        self.assertTrue(any("로컬 규칙 기반" in item for item in response["warnings"]))
        self.assertGreaterEqual(len(response["exercise_plan"]), 1)

    def test_fallback_llm_plain_message_response(self):
        llm_result = {
            "content": "오늘은 무릎 정렬만 신경 쓰고 천천히 진행하세요",
            "served_by": "fallback",
            "model_name": "fallback-model",
            "fallback_used": True,
            "primary_error": "primary timeout",
        }
        with patch("app.services.is_fallback_llm_configured", return_value=True), patch(
            "app.services.call_llm_with_fallback", return_value=llm_result
        ):
            response = self.main.generate_coaching(
                self.schemas.FeaturePayload(
                    user_id="u5",
                    session_id="s1",
                    mode="exercise",
                    event="session_completed",
                    features=self.schemas.FeatureBundle(
                        exercise=self.schemas.ExerciseFeature(
                            type="squat",
                            rep_count=8,
                            stability_score=0.64,
                            posture_errors=["knees_caving_in"],
                            squat_depth=0.49,
                            knee_angle=118,
                            back_angle="forward",
                            duration_sec=42,
                            tempo="fast",
                        )
                    ),
                )
            )
        self.assertEqual(response["exercise_plan"], [])
        self.assertEqual(response["pc2_payload"]["display_lines"], [response["pc2_payload"]["message"]])
        self.assertIn("천천히 진행하세요", response["pc2_payload"]["message"])

        logs = self.main.coach_logs("u5", limit=10)
        self.assertEqual(logs["logs"][0]["pc2_output"], {"message": response["pc2_payload"]["message"]})
        self.assertEqual(logs["logs"][0]["final_response"], {"message": response["pc2_payload"]["message"]})

    def test_logs_limit_out_of_range_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self.main.coach_logs("u1", limit=0)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_duplicate_session_id_is_marked_in_logs(self):
        payload = self.schemas.FeaturePayload(
            user_id="u_dup",
            session_id="dup-session-1",
            mode="exercise",
            event="session_completed",
            features=self.schemas.FeatureBundle(
                exercise=self.schemas.ExerciseFeature(
                    type="pushup",
                    rep_count=5,
                    stability_score=0.6,
                    back_angle="forward",
                    duration_sec=20,
                    tempo="fast",
                )
            ),
        )

        self.main.generate_coaching(payload)
        self.main.generate_coaching(payload)

        logs = self.main.coach_logs("u_dup", limit=10)
        self.assertEqual(len(logs["logs"]), 2)

        latest = logs["logs"][0]
        original = logs["logs"][1]
        self.assertTrue(latest["is_duplicate_session"])
        self.assertEqual(latest["duplicate_of_request_id"], original["request_id"])
        self.assertFalse(original["is_duplicate_session"])
        self.assertIsNone(original["duplicate_of_request_id"])

    def test_pc3_contract_payload_dict_is_accepted(self):
        payload = self.schemas.FeaturePayload(**self._pc3_payload())
        response = self.main.generate_coaching(payload)
        self.assertIn("summary", response)
        self.assertIn("pc2_payload", response)
        self.assertEqual(response["pc2_payload"]["message"], str(response["pc2_payload"]["message"]))

    def test_pc3_contract_rejects_extra_field(self):
        bad_payload = self._pc3_payload()
        bad_payload["features"]["exercise"]["landmarks"] = []

        with self.assertRaises(ValidationError) as ctx:
            self.schemas.FeaturePayload(**bad_payload)
        self.assertIn("landmarks", str(ctx.exception))

    def test_health_allows_degraded_with_local_fallback_ok(self):
        health = self.main.health()
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["local_fallback"]["status"], "ok")
        self.assertIn(health["primary_llm"]["status"], {"unconfigured", "unhealthy", "model_missing"})

    def test_parse_coaching_json_accepts_partial_fields(self):
        raw = '{"summary":"요약","priority":"무릎 정렬","plan":[{"exercise":"tempo squat","sets":3,"reps":6,"focus":"천천히","reason":"정렬 우선"}],"message":"천천히 진행하세요!"}'
        parsed = parse_coaching_json(raw, {"warnings": []})
        self.assertEqual(parsed["summary"], "요약")
        self.assertEqual(parsed["priority"], "무릎 정렬")
        self.assertEqual(parsed["mirror_message"], "천천히 진행하세요!")
        self.assertEqual(parsed["pc2_payload"]["message"], "천천히 진행하세요!")
        self.assertEqual(parsed["exercise_plan"][0]["exercise"], "tempo squat")

    def test_parse_coaching_json_rejects_empty_content(self):
        with self.assertRaises(ValueError) as ctx:
            parse_coaching_json("{}", {"warnings": []})
        self.assertIn("사용할 수 있는 내용", str(ctx.exception))

    def test_parse_coaching_json_accepts_wrapped_response(self):
        raw = '{"CoachingResponse":{"summary":"요약","priority":"무릎 정렬","exercise_plan":[{"exercise":"Tempo Squat","sets":3,"reps":6,"focus":"하강 3초","reason":"교정"}],"mirror_message":"천천히 내려가세요!","warnings":["주의"],"pc2_payload":{"message":"템포 조절부터 시작","display_lines":["하강 3초"]}}}'
        parsed = parse_coaching_json(raw, {"warnings": []})
        self.assertEqual(parsed["summary"], "요약")
        self.assertEqual(parsed["priority"], "무릎 정렬")
        self.assertEqual(parsed["exercise_plan"][0]["exercise"], "Tempo Squat")
        self.assertEqual(parsed["pc2_payload"]["message"], "템포 조절부터 시작")

    def test_generate_profile_routine_success_with_mocked_llm(self):
        weekly_llm_result = {
            "content": '{"summary":"운동 습관 형성을 위한 주간 루틴입니다.","weekly_focus":"주 5회 리듬 유지와 전신 밸런스 확보","weekly_routine":[{"day_index":1,"day_label":"Day 1","focus":"하체와 코어","exercises":[{"exercise":"squat","sets":4,"reps":10,"duration_sec":null,"rest_sec":75,"focus":"하체 안정성","reason":"기초 하체 근력 유지에 적합합니다.","how_to":"발을 어깨너비로 벌리고 가슴을 세운 채 엉덩이를 뒤로 빼며 천천히 앉았다가 발바닥으로 밀어 올라옵니다.","tips":"무릎이 안쪽으로 모이지 않게 하고 올라올 때 숨을 내쉽니다."}]},{"day_index":2,"day_label":"Day 2","focus":"상체 밀기","exercises":[{"exercise":"pushup","sets":3,"reps":12,"duration_sec":null,"rest_sec":60,"focus":"상체 볼륨 확보","reason":"주간 빈도를 유지하기 좋은 난이도입니다.","how_to":"손을 어깨보다 약간 넓게 두고 몸통을 일직선으로 유지한 채 가슴이 바닥 가까이 오도록 내려갔다가 밀어 올립니다.","tips":"복부에 힘을 주고 내려갈 때 들이마시고 밀어낼 때 내쉽니다."}]}],"cautions":["통증이 있으면 강도를 낮추세요."],"pc3_payload":{"summary":"운동 습관 형성을 위한 주간 루틴입니다.","weekly_focus":"주 5회 리듬 유지와 전신 밸런스 확보","available_days_per_week":5,"restricted_body_parts":[],"weekly_routine":[{"day_index":1,"day_label":"Day 1","focus":"하체와 코어","exercises":[{"exercise":"squat","sets":4,"reps":10,"duration_sec":null,"rest_sec":75,"focus":"하체 안정성","reason":"기초 하체 근력 유지에 적합합니다.","how_to":"발을 어깨너비로 벌리고 가슴을 세운 채 엉덩이를 뒤로 빼며 천천히 앉았다가 발바닥으로 밀어 올라옵니다.","tips":"무릎이 안쪽으로 모이지 않게 하고 올라올 때 숨을 내쉽니다."}]}]}}',
            "served_by": "primary",
            "model_name": "mock-model",
            "fallback_used": False,
            "primary_error": None,
        }
        day1_llm_result = {
            "content": '{"day_index":1,"day_label":"Day 1","focus":"하체와 코어 안정화","exercises":[{"exercise":"squat","sets":4,"reps":10,"duration_sec":null,"rest_sec":75,"focus":"하체 안정성","reason":"기초 하체 근력 유지에 적합합니다.","how_to":"발을 어깨너비로 벌리고 가슴을 세운 채 엉덩이를 뒤로 빼며 천천히 앉았다가 발바닥으로 밀어 올라옵니다.","tips":"무릎이 안쪽으로 모이지 않게 하고 올라올 때 숨을 내쉽니다."}]}',
            "served_by": "primary",
            "model_name": "mock-model",
            "fallback_used": False,
            "primary_error": None,
        }
        day2_llm_result = {
            "content": '{"day_index":2,"day_label":"Day 2","focus":"상체 밀기와 코어 고정","exercises":[{"exercise":"pushup","sets":3,"reps":12,"duration_sec":null,"rest_sec":60,"focus":"상체 볼륨 확보","reason":"주간 빈도를 유지하기 좋은 난이도입니다.","how_to":"손을 어깨보다 약간 넓게 두고 몸통을 일직선으로 유지한 채 가슴이 바닥 가까이 오도록 내려갔다가 밀어 올립니다.","tips":"복부에 힘을 주고 내려갈 때 들이마시고 밀어낼 때 내쉽니다."}]}',
            "served_by": "primary",
            "model_name": "mock-model",
            "fallback_used": False,
            "primary_error": None,
        }

        with patch("app.services.is_primary_llm_configured", return_value=True), patch(
            "app.services.call_primary_llm",
            side_effect=[weekly_llm_result, day1_llm_result, day2_llm_result],
        ) as mocked_call:
            response = self.main.generate_profile_routine(
                self.main.RoutineProfileRequest(**self._profile_payload(start_date="2026-05-13"))
            )

        self.assertEqual(mocked_call.call_count, 2)
        self.assertEqual(response["weekly_focus"], "주 5회 리듬 유지와 전신 밸런스 확보")
        self.assertEqual(response["weekly_routine"][0]["exercises"][0]["exercise"], "squat")
        self.assertEqual(response["weekly_routine"][0]["focus"], "하체와 코어 안정화")
        self.assertIn("천천히 앉았다가", response["weekly_routine"][0]["exercises"][0]["how_to"])
        self.assertIn("숨을 내쉽니다", response["weekly_routine"][0]["exercises"][0]["tips"])
        self.assertEqual(response["pc3_payload"]["available_days_per_week"], 5)
        self.assertEqual(response["pc3_payload"]["start_date"], "2026-05-13")
        self.assertEqual(response["pc3_payload"]["scheduled_dates"][:2], ["2026-05-13", "2026-05-14"])

        saved = self.main.get_profile_routine("profile_user")
        self.assertEqual(saved["user_goal"], "운동 습관 만들기")
        self.assertEqual(saved["start_date"], "2026-05-13")
        self.assertEqual(saved["scheduled_dates"][:2], ["2026-05-13", "2026-05-14"])
        self.assertEqual(saved["routine_response"]["weekly_focus"], response["weekly_focus"])
        self.assertEqual(saved["source_model"], "mock-model")

        day = self.main.get_profile_routine_day("profile_user", target_date=date(2026, 5, 14))
        self.assertEqual(day["day_index"], 2)
        self.assertIn("pushup", day["message"])

    def test_parse_profile_routine_json_backfills_pc3_payload(self):
        raw = (
            '{"summary":"주간 루틴입니다.","weekly_focus":"하체 안정성 유지",'
            '"weekly_routine":[{"day_index":1,"day_label":"Day 1","focus":"하체와 코어",'
            '"exercises":[{"exercise":"squat","sets":3,"reps":12,"rest_sec":60,"focus":"둔근 활성화","reason":"무릎 부담을 줄입니다.","how_to":"발을 어깨너비로 벌리고 엉덩이를 뒤로 빼며 천천히 앉았다가 올라옵니다.","tips":"발바닥 전체로 밀고 무릎 방향을 발끝과 맞춥니다."}]}],'
            '"cautions":["무릎 통증 시 강도 조절"]}'
        )
        parsed = parse_profile_routine_json(
            raw,
            {
                "cautions": ["무릎 통증 시 강도 조절"],
                "available_days_per_week": 4,
                "restricted_body_parts": ["무릎"],
            },
        )
        self.assertEqual(parsed["pc3_payload"]["available_days_per_week"], 4)
        self.assertEqual(parsed["pc3_payload"]["restricted_body_parts"], ["무릎"])
        self.assertEqual(parsed["pc3_payload"]["weekly_focus"], "하체 안정성 유지")
        self.assertEqual(parsed["pc3_payload"]["weekly_routine"][0]["day_label"], "Day 1")
        self.assertIn("천천히 앉았다가", parsed["weekly_routine"][0]["exercises"][0]["how_to"])
        self.assertIn("무릎 방향", parsed["weekly_routine"][0]["exercises"][0]["tips"])
        self.assertEqual(parsed["pc3_payload"]["weekly_routine"], parsed["weekly_routine"])

    def test_parse_profile_routine_json_normalizes_exercise_aliases(self):
        raw = (
            '{"summary":"주간 루틴입니다.","weekly_focus":"기본 루틴 유지",'
            '"weekly_routine":[{"day_index":1,"day_label":"Day 1","focus":"하체와 상체",'
            '"exercises":['
            '{"exercise":"스쿼트","sets":3,"reps":10,"rest_sec":60,"focus":"하체 안정성","reason":"기초 하체 자극입니다.","how_to":"천천히 앉았다가 올라옵니다.","tips":"무릎 정렬을 유지합니다."},'
            '{"exercise":"push-up","sets":3,"reps":8,"rest_sec":60,"focus":"상체 안정성","reason":"상체 기초 자극입니다.","how_to":"몸을 일직선으로 유지하며 내려갔다가 올라옵니다.","tips":"복부 힘을 유지합니다."}'
            ']}],'
            '"cautions":[]}'
        )
        parsed = parse_profile_routine_json(
            raw,
            {
                "cautions": [],
                "available_days_per_week": 2,
                "restricted_body_parts": [],
            },
        )
        self.assertEqual(parsed["weekly_routine"][0]["exercises"][0]["exercise"], "squat")
        self.assertEqual(parsed["weekly_routine"][0]["exercises"][1]["exercise"], "pushup")

    def test_parse_profile_routine_json_rejects_empty_routine_response(self):
        raw = '{"summary":"","weekly_focus":"","weekly_routine":[],"cautions":[]}'
        with self.assertRaises(ValueError) as ctx:
            parse_profile_routine_json(
                raw,
                {
                    "cautions": [],
                    "available_days_per_week": 4,
                    "restricted_body_parts": [],
                },
            )
        self.assertIn("summary", str(ctx.exception))

    def test_parse_profile_routine_json_rejects_excess_days(self):
        raw = (
            '{"summary":"주간 루틴입니다.","weekly_focus":"하체 안정성 유지",'
            '"weekly_routine":['
            '{"day_index":1,"day_label":"Day 1","focus":"하체와 코어","exercises":[{"exercise":"squat","sets":3,"reps":12,"rest_sec":60,"focus":"둔근 활성화","reason":"무릎 부담을 줄입니다.","how_to":"발을 어깨너비로 벌리고 엉덩이를 뒤로 빼며 천천히 앉았다가 올라옵니다.","tips":"발바닥 전체로 밀고 무릎 방향을 발끝과 맞춥니다."}]},'
            '{"day_index":2,"day_label":"Day 2","focus":"상체","exercises":[{"exercise":"pushup","sets":3,"reps":10,"rest_sec":60,"focus":"상체 안정성","reason":"기초 상체 근력 유지에 적합합니다.","how_to":"손을 어깨보다 약간 넓게 두고 몸통을 곧게 유지한 채 내려갔다가 밀어 올립니다.","tips":"허리가 꺾이지 않게 복부 힘을 유지합니다."}]}'
            '],"cautions":[]}'
        )
        with self.assertRaises(ValueError) as ctx:
            parse_profile_routine_json(
                raw,
                {
                    "cautions": [],
                    "available_days_per_week": 1,
                    "restricted_body_parts": [],
                },
            )
        self.assertIn("available_days_per_week", str(ctx.exception))

    def test_parse_profile_routine_json_rejects_non_exercise_type_name(self):
        raw = (
            '{"summary":"주간 루틴입니다.","weekly_focus":"하체 안정성 유지",'
            '"weekly_routine":[{"day_index":1,"day_label":"Day 1","focus":"하체와 코어",'
            '"exercises":[{"exercise":"bridge","sets":3,"reps":12,"rest_sec":60,"focus":"둔근 활성화","reason":"무릎 부담을 줄입니다.","how_to":"발을 바닥에 두고 엉덩이를 들어 올린 뒤 천천히 내립니다.","tips":"허리보다 엉덩이 수축에 집중합니다."}]}],'
            '"cautions":["무릎 통증 시 강도 조절"]}'
        )
        with self.assertRaises(ValueError) as ctx:
            parse_profile_routine_json(
                raw,
                {
                    "cautions": ["무릎 통증 시 강도 조절"],
                    "available_days_per_week": 4,
                    "restricted_body_parts": ["무릎"],
                },
            )
        self.assertIn("exercise는 squat, jumping_jack, knee_raise, lunge, pushup", str(ctx.exception))

    def test_generate_coaching_uses_saved_profile_routine_context(self):
        routine_llm_result = {
            "content": '{"summary":"하체 중심 루틴입니다.","weekly_focus":"하체 안정성과 코어 유지","weekly_routine":[{"day_index":1,"day_label":"Day 1","focus":"하체와 코어","exercises":[{"exercise":"squat","sets":4,"reps":10,"duration_sec":null,"rest_sec":75,"focus":"하체 안정성","reason":"기초 하체 근력 유지에 적합합니다."}]}],"cautions":["무릎 통증이 있으면 즉시 강도를 낮추세요."],"pc3_payload":{"summary":"하체 중심 루틴입니다.","weekly_focus":"하체 안정성과 코어 유지","weekly_routine":[{"day_index":1,"day_label":"Day 1","focus":"하체와 코어","exercises":[{"exercise":"squat","sets":4,"reps":10,"duration_sec":null,"rest_sec":75,"focus":"하체 안정성","reason":"기초 하체 근력 유지에 적합합니다."}]}]}}',
            "served_by": "primary",
            "model_name": "profile-model",
            "fallback_used": False,
            "primary_error": None,
        }
        coaching_llm_result = {
            "content": '{"summary":"루틴 맥락을 반영한 코칭입니다.","priority":"무릎 정렬","exercise_plan":[{"exercise":"tempo squat","sets":3,"reps":6,"duration_sec":null,"rest_sec":90,"focus":"무릎 정렬","reason":"저장된 주간 루틴의 하체 안정성 목표와 현재 자세 신호를 함께 반영했습니다."}],"mirror_message":"무릎 정렬부터 다시 잡으세요!","warnings":[],"pc2_payload":{"message":"하체 루틴 방향 유지, 무릎 정렬 우선","display_lines":["무릎 정렬","하체 안정성"]}}',
            "served_by": "primary",
            "model_name": "coach-model",
            "fallback_used": False,
            "primary_error": None,
        }

        with patch("app.services.is_primary_llm_configured", return_value=True), patch(
            "app.services.call_primary_llm", return_value=routine_llm_result
        ):
            self.main.generate_profile_routine(self.main.RoutineProfileRequest(**self._profile_payload()))

        with patch("app.services.is_primary_llm_configured", return_value=True), patch(
            "app.services.call_llm_with_fallback", return_value=coaching_llm_result
        ) as mocked_call:
            response = self.main.generate_coaching(self.schemas.FeaturePayload(**self._pc3_payload(user_id="profile_user")))

        self.assertEqual(response["priority"], "무릎 정렬")
        _, user_prompt = mocked_call.call_args.args[:2]
        self.assertIn("latest_profile_routine", user_prompt)
        self.assertIn("하체 안정성과 코어 유지", user_prompt)
        self.assertIn("squat", user_prompt)

        logs = self.main.coach_logs("profile_user", limit=10)
        self.assertEqual(
            logs["logs"][0]["routine_snapshot"]["routine_response"]["weekly_focus"],
            "하체 안정성과 코어 유지",
        )

    def test_generate_profile_routine_requires_primary_llm(self):
        response = self.main.generate_profile_routine(
            self.main.RoutineProfileRequest(**self._profile_payload())
        )
        self.assertIn("weekly_routine", response)
        self.assertIn("LLM 문제로 로컬 기본 루틴", response["cautions"][-1])

    def test_generate_profile_routine_primary_failure_returns_local_fallback(self):
        with patch("app.services.is_primary_llm_configured", return_value=True), patch(
            "app.services.call_primary_llm", side_effect=RuntimeError("forced failure")
        ):
            response = self.main.generate_profile_routine(
                self.main.RoutineProfileRequest(
                    **self._profile_payload(restricted_body_parts=["무릎", "어깨"])
                )
            )
        self.assertTrue(response["summary"].startswith("LLM 응답 문제가 있어"))
        self.assertIn("weekly_routine", response)
        self.assertEqual(response["weekly_routine"][0]["exercises"][0]["exercise"], "pushup")

    def test_generate_profile_routine_parse_failure_returns_local_fallback(self):
        llm_result = {
            "content": "not-json",
            "served_by": "primary",
            "model_name": "mock-model",
            "fallback_used": False,
            "primary_error": None,
        }
        with patch("app.services.is_primary_llm_configured", return_value=True), patch(
            "app.services.call_primary_llm", return_value=llm_result
        ):
            response = self.main.generate_profile_routine(
                self.main.RoutineProfileRequest(
                    **self._profile_payload(restricted_body_parts=["무릎", "어깨"])
                )
            )
        self.assertTrue(response["summary"].startswith("LLM 응답 문제가 있어"))
        self.assertEqual(response["pc3_payload"]["weekly_routine"][0]["exercises"][0]["exercise"], "pushup")

    def test_profile_routine_request_rejects_invalid_days(self):
        with self.assertRaises(ValidationError) as ctx:
            self.main.RoutineProfileRequest(**self._profile_payload(available_days_per_week=8))
        self.assertIn("available_days_per_week", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
