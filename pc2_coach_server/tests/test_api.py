import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError


PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_main(db_path: str):
    sys.path.insert(0, str(PROJECT_DIR))
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name)

    os.environ["DB_PATH"] = db_path
    os.environ["PRIMARY_LLM_API_KEY"] = ""
    os.environ["NVIDIA_API_KEY"] = ""
    os.environ["LLM_API_KEY"] = ""
    os.environ["FALLBACK_LLM_ENABLED"] = "false"
    os.environ["FALLBACK_LLM_API_KEY"] = ""

    return importlib.import_module("app.main")


class PC2ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.tmpdir.name) / "test_pc2.db")
        self.main = load_main(db_path)
        self.schemas = importlib.import_module("app.schemas")

    def tearDown(self):
        self.tmpdir.cleanup()

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

    def test_logs_limit_out_of_range_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self.main.coach_logs("u1", limit=0)
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
