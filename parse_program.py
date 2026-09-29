"""
Parses Triathlon_Program.xlsx ("Weekly Program" sheet) into a flat list of
planned sessions with dates, sport tags, session types, and (where present)
numeric watt targets. Re-run this any time the plan spreadsheet changes.

Design note: the plan is kept as the source of truth in the spreadsheet.
This parser is intentionally tolerant (regex-based, keyword tagging)
rather than assuming a rigid text format, since programs get hand-edited.
"""
import re
from datetime import timedelta

import pandas as pd

from config import PROGRAM_START_DATE, PROGRAM_XLSX_PATH

DAY_COLUMNS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

SPORT_KEYWORDS = [
    ("bike", ["bike", "cycl", "ftp"]),
    ("run", ["run"]),
    ("swim", ["swim", "css"]),
    ("strength", ["strength"]),
]

WATTS_RE = re.compile(r"(\d+)(?:[–-](\d+))?\s*W\b")
MIN_RANGE_RE = re.compile(r"(\d+)(?:[–-](\d+))?\s*min")
HOUR_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)(?:[–-](\d+(?:\.\d+)?))?\s*h\b")


def _tag_sport(text: str) -> str:
    lower = text.lower()
    for sport, keywords in SPORT_KEYWORDS:
        if any(k in lower for k in keywords):
            return sport
    return "other"


def _tag_session_type(text: str) -> str:
    lower = text.lower()
    if "test" in lower:
        return "ftp_test" if "ftp" in lower else ("css_test" if "css" in lower else "run_threshold_test")
    if "deload" in lower:
        return "deload"
    if "brick" in lower:
        return "brick"
    if "threshold" in lower:
        return "threshold"
    if "css" in lower:
        return "css"
    if re.search(r"\bz2\b", lower):
        return "z2"
    if "strength a" in lower:
        return "strength_a"
    if "strength b" in lower:
        return "strength_b"
    if "easy" in lower:
        return "easy"
    return "other"


def _extract_watts(text: str):
    m = WATTS_RE.search(text)
    if not m:
        return None, None
    low = float(m.group(1))
    high = float(m.group(2)) if m.group(2) else low
    return low, high


def _extract_duration_min(text: str):
    """
    A session description can mention several time spans (e.g. interval
    length, recovery length, AND total session time: "3x12 min @ 323W,
    4 min recovery. ~65 min total"). We want the total, which is reliably
    the largest number mentioned, so take the max across all matches
    rather than the first.
    """
    candidates = []
    for m in HOUR_RANGE_RE.finditer(text):
        low = float(m.group(1)) * 60
        high = float(m.group(2)) * 60 if m.group(2) else low
        candidates.append((low + high) / 2)
    for m in MIN_RANGE_RE.finditer(text):
        low = float(m.group(1))
        high = float(m.group(2)) if m.group(2) else low
        candidates.append((low + high) / 2)
    return max(candidates) if candidates else None


def parse_plan(xlsx_path: str = None) -> list[dict]:
    xlsx_path = xlsx_path or PROGRAM_XLSX_PATH
    df = pd.read_excel(xlsx_path, sheet_name="Weekly Program")

    sessions = []
    for _, row in df.iterrows():
        try:
            week = int(row["Week"])
        except (ValueError, TypeError):
            continue

        week_start = PROGRAM_START_DATE + timedelta(weeks=week)

        for i, day_col in enumerate(DAY_COLUMNS):
            cell = row.get(day_col)
            if not isinstance(cell, str) or cell.strip() in ("-", "", "nan"):
                continue

            session_date = week_start + timedelta(days=i)

            # A day can contain multiple sessions, e.g. "Strength A + easy swim".
            # A chunk with no sport keyword of its own (e.g. "20 min brick",
            # "warm-up/cooldown") is a continuation of the previous chunk's sport.
            last_sport = "other"
            for chunk in cell.split("+"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                watts_low, watts_high = _extract_watts(chunk)
                sport = _tag_sport(chunk)
                if sport == "other":
                    sport = last_sport
                else:
                    last_sport = sport
                sessions.append(
                    {
                        "week": week,
                        "date": session_date.isoformat(),
                        "day_of_week": day_col,
                        "sport": sport,
                        "session_type": _tag_session_type(chunk),
                        "target_watts_low": watts_low,
                        "target_watts_high": watts_high,
                        "estimated_duration_min": _extract_duration_min(chunk),
                        "description": chunk,
                    }
                )
    return sessions


if __name__ == "__main__":
    from db import init_db, get_conn, replace_planned_sessions

    init_db()
    parsed = parse_plan()
    with get_conn() as conn:
        replace_planned_sessions(conn, parsed)
    print(f"Parsed and stored {len(parsed)} planned sessions.")
