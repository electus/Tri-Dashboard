"""
Logs into Garmin Connect and syncs recent activities + daily wellness
metrics into SQLite. Run manually (`python garmin_sync.py`) or on a
schedule (cron / GitHub Actions / your host's scheduler).

Session tokens are cached to ~/.garminconnect by garth after first login,
so this won't re-authenticate (or trip MFA) every single run.
"""
import json
from datetime import date, timedelta

from garminconnect import Garmin

from config import GARMIN_EMAIL, GARMIN_PASSWORD, SYNC_LOOKBACK_DAYS
from db import init_db, get_conn, upsert_activity, upsert_wellness

SPORT_MAP = {
    "running": "run",
    "trail_running": "run",
    "treadmill_running": "run",
    "cycling": "bike",
    "road_biking": "bike",
    "indoor_cycling": "bike",
    "virtual_ride": "bike",
    "lap_swimming": "swim",
    "open_water_swimming": "swim",
    "strength_training": "strength",
}


def _map_sport(activity_type: str) -> str:
    return SPORT_MAP.get(activity_type, "other")


def login() -> Garmin:
    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        raise RuntimeError("Set GARMIN_EMAIL and GARMIN_PASSWORD (see .env.example).")
    client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
    client.login()
    return client


def sync_activities(client: Garmin, conn, days: int):
    activities = client.get_activities(0, 200)  # most recent 200; filtered below
    cutoff = date.today() - timedelta(days=days)

    for act in activities:
        act_date = date.fromisoformat(act["startTimeLocal"].split(" ")[0])
        if act_date < cutoff:
            continue

        row = {
            "activity_id": str(act["activityId"]),
            "date": act_date.isoformat(),
            "start_time": act.get("startTimeLocal"),
            "sport": _map_sport(act.get("activityType", {}).get("typeKey", "")),
            "name": act.get("activityName"),
            "duration_sec": act.get("duration"),
            "distance_m": act.get("distance"),
            "avg_hr": act.get("averageHR"),
            "max_hr": act.get("maxHR"),
            "avg_power": act.get("avgPower"),
            "normalized_power": act.get("normPower"),
            "avg_pace_min_km": (1000 / act["averageSpeed"] / 60) if act.get("averageSpeed") else None,
            "calories": act.get("calories"),
            "training_load": act.get("activityTrainingLoad"),
            "aerobic_te": act.get("aerobicTrainingEffect"),
            "anaerobic_te": act.get("anaerobicTrainingEffect"),
            "raw_json": json.dumps(act),
        }
        upsert_activity(conn, row)

    print(f"Synced {len(activities)} recent activities (filtered to last {days} days).")


def sync_wellness(client: Garmin, conn, days: int):
    for i in range(days):
        d = date.today() - timedelta(days=i)
        d_iso = d.isoformat()
        try:
            stats = client.get_stats(d_iso)
            readiness = client.get_training_readiness(d_iso)
            hrv = client.get_hrv_data(d_iso)
            max_metrics = client.get_max_metrics(d_iso)
        except Exception as e:  # Garmin's API 404s for days with no data
            continue

        readiness_score = None
        if readiness and isinstance(readiness, list) and readiness:
            readiness_score = readiness[0].get("score")

        hrv_avg = None
        if hrv and isinstance(hrv, dict):
            hrv_avg = hrv.get("hrvSummary", {}).get("lastNightAvg")

        vo2max_run, vo2max_cycle = None, None
        if max_metrics and isinstance(max_metrics, list) and max_metrics:
            mm = max_metrics[0]
            vo2max_run = mm.get("generic", {}).get("vo2MaxValue")
            vo2max_cycle = mm.get("cycling", {}).get("vo2MaxValue")

        row = {
            "date": d_iso,
            "resting_hr": stats.get("restingHeartRate") if stats else None,
            "hrv_avg": hrv_avg,
            "sleep_score": stats.get("sleepingSeconds") if stats else None,  # placeholder if score unavailable
            "sleep_duration_min": (stats.get("sleepingSeconds", 0) / 60) if stats and stats.get("sleepingSeconds") else None,
            "body_battery_max": stats.get("bodyBatteryHighestValue") if stats else None,
            "body_battery_min": stats.get("bodyBatteryLowestValue") if stats else None,
            "stress_avg": stats.get("averageStressLevel") if stats else None,
            "training_readiness": readiness_score,
            "vo2max_run": vo2max_run,
            "vo2max_cycle": vo2max_cycle,
            "raw_json": json.dumps({"stats": stats, "readiness": readiness}, default=str),
        }
        upsert_wellness(conn, row)

    print(f"Synced wellness metrics for last {days} days.")


def main():
    init_db()
    client = login()
    with get_conn() as conn:
        sync_activities(client, conn, SYNC_LOOKBACK_DAYS)
        sync_wellness(client, conn, SYNC_LOOKBACK_DAYS)


if __name__ == "__main__":
    main()
