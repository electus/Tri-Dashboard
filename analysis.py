"""
Analysis functions: training load trend (CTL/ATL/TSB), planned vs actual
matching, and zone/target compliance for interval sessions.
"""
import pandas as pd

from db import get_conn


def load_activities_df() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM activities ORDER BY date", conn)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def load_wellness_df() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM wellness ORDER BY date", conn)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def load_planned_df() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM planned_sessions ORDER BY date", conn)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def daily_load(activities: pd.DataFrame) -> pd.Series:
    """
    Sum training load per day. Prefers Garmin's own activityTrainingLoad;
    falls back to a rough duration*intensity proxy (using avg HR effort as
    a stand-in for effort factor) when Garmin didn't report one, so gaps
    in the CTL/ATL curve don't appear as full rest days by accident.
    """
    if activities.empty:
        return pd.Series(dtype=float)

    def row_load(row):
        if pd.notnull(row.get("training_load")):
            return row["training_load"]
        if pd.notnull(row.get("duration_sec")) and pd.notnull(row.get("avg_hr")):
            # crude proxy: minutes * (avg_hr / 100), just to avoid a hard zero
            return (row["duration_sec"] / 60) * (row["avg_hr"] / 100)
        if pd.notnull(row.get("duration_sec")):
            return row["duration_sec"] / 60
        return 0.0

    activities = activities.copy()
    activities["load"] = activities.apply(row_load, axis=1)
    return activities.groupby(activities["date"].dt.date)["load"].sum()


def compute_ctl_atl_tsb(activities: pd.DataFrame) -> pd.DataFrame:
    """
    Standard exponentially-weighted CTL (fitness, 42-day time constant)
    and ATL (fatigue, 7-day time constant); TSB (form) = CTL - ATL.
    Same approach TrainingPeaks/intervals.icu use for TSS-based PMC charts.
    """
    load = daily_load(activities)
    if load.empty:
        return pd.DataFrame(columns=["date", "ctl", "atl", "tsb"])

    idx = pd.date_range(load.index.min(), load.index.max(), freq="D")
    load = load.reindex(idx.date, fill_value=0.0)

    ctl = load.ewm(span=42, adjust=False).mean()
    atl = load.ewm(span=7, adjust=False).mean()
    tsb = ctl - atl

    return pd.DataFrame(
        {"date": pd.to_datetime(idx), "ctl": ctl.values, "atl": atl.values, "tsb": tsb.values}
    )


def planned_vs_actual(planned: pd.DataFrame, activities: pd.DataFrame) -> pd.DataFrame:
    """
    For each planned session, find same-day activities of the same sport
    and report whether it was completed, and how actual duration compared
    to the plan's estimate (when the plan specified one).
    """
    if planned.empty:
        return pd.DataFrame()

    rows = []
    for _, p in planned.iterrows():
        same_day = activities[
            (activities["date"] == p["date"]) & (activities["sport"] == p["sport"])
        ] if not activities.empty else activities

        completed = not same_day.empty
        actual_duration = (same_day["duration_sec"].sum() / 60) if completed else 0.0
        planned_duration = p.get("estimated_duration_min")

        completion_pct = None
        if completed and planned_duration:
            completion_pct = round(100 * actual_duration / planned_duration, 1)

        rows.append(
            {
                "week": p["week"],
                "date": p["date"],
                "day_of_week": p["day_of_week"],
                "sport": p["sport"],
                "session_type": p["session_type"],
                "description": p["description"],
                "planned_duration_min": planned_duration,
                "completed": completed,
                "actual_duration_min": round(actual_duration, 1) if completed else None,
                "completion_pct": completion_pct,
            }
        )
    return pd.DataFrame(rows)


def sport_zone_distribution(activities: pd.DataFrame, sport: str) -> pd.DataFrame:
    """Weekly minutes for a given sport, as a basic volume-by-week check."""
    if activities.empty:
        return pd.DataFrame()
    df = activities[activities["sport"] == sport].copy()
    if df.empty:
        return pd.DataFrame()
    df["week"] = df["date"].dt.to_period("W-MON").apply(lambda p: p.start_time)
    return df.groupby("week")["duration_sec"].sum().div(60).reset_index(name="minutes")
