import argparse
import json

import requests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:7000")
    args = parser.parse_args()

    baseline_payload = {
        "user_id": "exercise_user",
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
    baseline_response = requests.post(
        f"{args.base_url}/api/exercise/baseline",
        json=baseline_payload,
        timeout=30,
    )
    print("baseline", baseline_response.status_code)
    print(json.dumps(baseline_response.json(), ensure_ascii=False, indent=2))
    baseline_response.raise_for_status()

    payload = {
        "session_id": "sess_exercise_001",
        "user_id": "exercise_user",
        "mode": "exercise",
        "event": "session_completed",
        "features": {
            "exercise": {
                "type": "squat",
                "count": 8,
                "rep_count": 8,
                "stability_score": 0.64,
                "posture_errors": ["knees_caving_in"],
                "squat_depth": 0.49,
                "knee_angle": 118,
                "back_angle": "forward",
                "duration_sec": 42,
                "tempo": "fast",
            }
        },
        "environment": {
            "temperature": 24.5,
            "humidity": 48,
            "illuminance": 360,
        },
        "purpose": "하체 루틴 자세 점검 후 다음 운동 계획 생성",
    }
    response = requests.post(
        f"{args.base_url}/api/coach/generate",
        json=payload,
        timeout=30,
    )
    print("plan", response.status_code)
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    response.raise_for_status()


if __name__ == "__main__":
    main()
