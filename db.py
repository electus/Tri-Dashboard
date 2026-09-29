"""
SQLite storage layer. Kept deliberately simple (no ORM) since the
schema is small and stable.
"""
import sqlite3
import json
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id     TEXT PRIMARY KEY,
    date            TEXT NOT NULL,          -- ISO date
    start_time      TEXT,                   -- ISO datetime
    sport            TEXT,                   -- bike / run / swim / strength / other
    name            TEXT,
    duration_sec    REAL,
    distance_m      REAL,
    avg_hr          REAL,
    max_hr          REAL,
    avg_power       REAL,
    normalized_power REAL,
    avg_pace_min_km REAL,
    calories        REAL,
    training_load   REAL,                   -- Garmin's activityTrainingLoad if present
    aerobic_te      REAL,
    anaerobic_te    REAL,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS wellness (
    date                TEXT PRIMARY KEY,   -- ISO date
    resting_hr          REAL,
    hrv_avg             REAL,
    sleep_score         REAL,
    sleep_duration_min  REAL,
    body_battery_max    REAL,
    body_battery_min    REAL,
    stress_avg          REAL,
    training_readiness  REAL,
    vo2max_run          REAL,
    vo2max_cycle        REAL,
    raw_json            TEXT
);

CREATE TABLE IF NOT EXISTS planned_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    week                INTEGER NOT NULL,
    date                TEXT NOT NULL,       -- ISO date, derived from PROGRAM_START_DATE
    day_of_week         TEXT NOT NULL,
    sport               TEXT NOT NULL,       -- bike / run / swim / strength
    session_type        TEXT,                -- z2 / threshold / ftp_test / css / css_test / brick / deload / strength_a / strength_b / easy
    target_watts_low    REAL,
    target_watts_high   REAL,
    estimated_duration_min REAL,
    description         TEXT NOT NULL,       -- original text from the plan
    UNIQUE(date, sport, description)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_activity(conn, a: dict):
    cols = ", ".join(a.keys())
    placeholders = ", ".join(f":{k}" for k in a.keys())
    updates = ", ".join(f"{k}=excluded.{k}" for k in a.keys() if k != "activity_id")
    conn.execute(
        f"""INSERT INTO activities ({cols}) VALUES ({placeholders})
            ON CONFLICT(activity_id) DO UPDATE SET {updates}""",
        a,
    )


def upsert_wellness(conn, w: dict):
    cols = ", ".join(w.keys())
    placeholders = ", ".join(f":{k}" for k in w.keys())
    updates = ", ".join(f"{k}=excluded.{k}" for k in w.keys() if k != "date")
    conn.execute(
        f"""INSERT INTO wellness ({cols}) VALUES ({placeholders})
            ON CONFLICT(date) DO UPDATE SET {updates}""",
        w,
    )


def replace_planned_sessions(conn, sessions: list[dict]):
    """Wipe and reload planned_sessions. Call after re-parsing the plan xlsx."""
    conn.execute("DELETE FROM planned_sessions")
    for s in sessions:
        conn.execute(
            """INSERT OR IGNORE INTO planned_sessions
               (week, date, day_of_week, sport, session_type,
                target_watts_low, target_watts_high, estimated_duration_min, description)
               VALUES (:week, :date, :day_of_week, :sport, :session_type,
                       :target_watts_low, :target_watts_high, :estimated_duration_min, :description)""",
            s,
        )
