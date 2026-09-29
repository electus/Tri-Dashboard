"""
Central config. Values come from environment variables (.env locally,
or your host's secrets manager in production). Nothing sensitive is
hardcoded here.
"""
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

GARMIN_EMAIL = os.environ.get("GARMIN_EMAIL")
GARMIN_PASSWORD = os.environ.get("GARMIN_PASSWORD")

FTP_WATTS = float(os.environ.get("FTP_WATTS", 250))
RUN_THRESHOLD_PACE_MIN_PER_KM = float(os.environ.get("RUN_THRESHOLD_PACE_MIN_PER_KM", 4.5))
CSS_PACE_MIN_PER_100M = float(os.environ.get("CSS_PACE_MIN_PER_100M", 1.6))

PROGRAM_START_DATE = date.fromisoformat(
    os.environ.get("PROGRAM_START_DATE", date.today().isoformat())
)

DB_PATH = os.environ.get("DB_PATH", "garmin_data.db")
PROGRAM_XLSX_PATH = os.environ.get("PROGRAM_XLSX_PATH", "Triathlon_Program.xlsx")

# How far back to sync activities/wellness on each run
SYNC_LOOKBACK_DAYS = int(os.environ.get("SYNC_LOOKBACK_DAYS", 21))
