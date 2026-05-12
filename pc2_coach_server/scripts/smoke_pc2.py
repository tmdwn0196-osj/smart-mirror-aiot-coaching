import argparse
import json
import sys
from uuid import uuid4

import requests


def _print_step(title: str) -> None:
    print(f"\n=== {title} ===")


def _dump_response(label: str, response: requests.Response) -> dict:
    print(label, response.status_code)
    try:
        payload = response.json()
    except ValueError:
        print(response.text)
        raise
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _make_pc3_payload(*, user_id: str, session_id: str) -> dict:
    return {
        "session_id": session_id,
        "user_id": user_id,
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:7000")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--user-id", default=None)
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args()

    run_suffix = uuid4().hex[:8]
    user_id = args.user_id or f"exercise_user_{run_suffix}"
    session_id = args.session_id or f"sess_exercise_{run_suffix}"

    baseline_payload = {
        "user_id": user_id,
        "exercise_type": "squat",
        "purpose": "하체 루틴 baseline 생성",
        "samples": [
            {
                "type": "squat",
                "rep_count": 12,
                "stability_score": 0.82,
                "posture_errors": [],
                "squat_depth": 0.62,
                "knee_angle": 96,
                "back_angle": "neutral",
                "duration_sec": 48,
                "tempo": "controlled",
            },
            {
                "type": "squat",
                "rep_count": 10,
                "stability_score": 0.8,
                "posture_errors": ["knees_in"],
                "squat_depth": 0.6,
                "knee_angle": 98,
                "back_angle": "neutral",
                "duration_sec": 46,
                "tempo": "controlled",
            },
        ],
    }

    session = requests.Session()

    _print_step("health")
    health_response = session.get(f"{args.base_url}/health", timeout=args.timeout)
    health = _dump_response("health 응답", health_response)
    health_response.raise_for_status()
    _expect(health["status"] in {"ok", "degraded"}, "health.status must be ok or degraded")
    _expect(health["local_fallback"]["status"] == "ok", "local_fallback.status must be ok")

    _print_step("baseline")
    baseline_response = session.post(
        f"{args.base_url}/api/exercise/baseline",
        json=baseline_payload,
        timeout=args.timeout,
    )
    baseline = _dump_response("baseline 저장 응답", baseline_response)
    baseline_response.raise_for_status()
    _expect(baseline["exercise_type"] == "squat", "baseline exercise_type mismatch")
    _expect(baseline["baseline_profile"]["recommended_reps"] >= 1, "baseline recommended_reps missing")

    payload = _make_pc3_payload(user_id=user_id, session_id=session_id)

    _print_step("generate")
    generate_response = session.post(
        f"{args.base_url}/api/coach/generate",
        json=payload,
        timeout=args.timeout,
    )
    generated = _dump_response("운동 계획 응답", generate_response)
    generate_response.raise_for_status()
    _expect(bool(generated.get("summary")), "summary missing")
    _expect(bool(generated.get("priority")), "priority missing")
    _expect(bool((generated.get("pc2_payload") or {}).get("message")), "pc2_payload.message missing")

    _print_step("duplicate session")
    duplicate_response = session.post(
        f"{args.base_url}/api/coach/generate",
        json=payload,
        timeout=args.timeout,
    )
    duplicate_generated = _dump_response("중복 session 응답", duplicate_response)
    duplicate_response.raise_for_status()
    _expect(bool((duplicate_generated.get("pc2_payload") or {}).get("message")), "duplicate response message missing")

    _print_step("logs")
    logs_response = session.get(
        f"{args.base_url}/api/coach/logs/{user_id}",
        params={"limit": 10},
        timeout=args.timeout,
    )
    logs_payload = _dump_response("로그 조회 응답", logs_response)
    logs_response.raise_for_status()
    logs = logs_payload["logs"]
    _expect(len(logs) >= 2, "expected at least two logs")
    _expect(logs[0]["is_duplicate_session"] is True, "latest log must be marked as duplicate session")
    _expect(
        logs[0]["duplicate_of_request_id"] == logs[1]["request_id"],
        "duplicate_of_request_id must point to original request_id",
    )

    _print_step("extra field rejection")
    bad_payload = _make_pc3_payload(user_id=user_id, session_id=f"{session_id}_bad")
    bad_payload["features"]["exercise"]["landmarks"] = []
    bad_response = session.post(
        f"{args.base_url}/api/coach/generate",
        json=bad_payload,
        timeout=args.timeout,
    )
    bad_result = _dump_response("extra field 거부 응답", bad_response)
    _expect(bad_response.status_code == 422, "extra field payload must be rejected with 422")
    _expect("detail" in bad_result, "422 response must contain detail")

    print("\nSMOKE OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nSMOKE FAILED: {exc}", file=sys.stderr)
        raise
