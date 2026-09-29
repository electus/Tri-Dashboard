# Triathlon Garmin Dashboard

Pulls your Garmin Connect activities and wellness data, compares them against
your training plan (`Triathlon_Program.xlsx`), and shows fitness/fatigue
trends, recovery signals, and plan compliance in a Streamlit web app.

## 1. Local setup

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in your Garmin login + FTP/pace baselines
```

Edit `.env`:
- `GARMIN_EMAIL` / `GARMIN_PASSWORD` — your Garmin Connect login
- `FTP_WATTS`, `RUN_THRESHOLD_PACE_MIN_PER_KM`, `CSS_PACE_MIN_PER_100M` — your
  current baselines (update these after each retest — the program has FTP,
  run threshold, and CSS retests built in at weeks 5, 10, and 15)
- `PROGRAM_START_DATE` — the Monday your Week 0 begins. **Must be a Monday**;
  the parser assumes Monday→Sunday columns map onto 7 consecutive calendar days
  starting there.

Put your plan spreadsheet in the project folder as `Triathlon_Program.xlsx`
(or point `PROGRAM_XLSX_PATH` at it).

## 2. Load the plan and pull your data

```bash
python parse_program.py   # parses the xlsx into planned_sessions
python garmin_sync.py     # logs into Garmin Connect, pulls activities + wellness
```

Re-run `parse_program.py` any time you edit the plan spreadsheet.
Re-run `garmin_sync.py` daily (see scheduling below) to keep the dashboard current.

## 3. Run the dashboard

```bash
streamlit run app.py
```

## Scheduling the sync

The dashboard only shows what's in the local database — it doesn't call
Garmin live on page load. Run `garmin_sync.py` on a schedule:
- **Cron** (simplest, if self-hosting on a VPS): `0 6 * * * cd /path/to/project && python garmin_sync.py`
- **GitHub Actions** on a schedule trigger, committing/pushing the updated `.db` file or writing to an external DB
- **Render/Railway cron jobs** if you deploy the app there too

## Deploying so you can check it from anywhere

**Streamlit Community Cloud** (free, fastest):
1. Push this repo to GitHub — **do not commit `.env` or `garmin_data.db`** (add both to `.gitignore`)
2. Connect the repo at share.streamlit.io
3. Add `GARMIN_EMAIL`, `GARMIN_PASSWORD`, `FTP_WATTS`, etc. as Streamlit "Secrets" (Settings → Secrets), not in the repo
4. You'll still need something else running `garmin_sync.py` on a schedule (Community Cloud won't run background jobs) — a small VPS cron job or GitHub Action is the common pattern: sync writes to a DB the app reads from

**Self-hosted (Render / Railway / a VPS + Docker)** gives you more control:
run both the sync cron job and the Streamlit app in the same place, so they
share the same SQLite file directly, no external DB needed for this scale of data.

## Known limitations / things worth checking before you rely on this

- **`garminconnect` field names drift between library versions** — I couldn't
  test `garmin_sync.py` against live Garmin servers in this environment (no
  network access to Garmin's domains here). Before your first real sync, run
  it once and check the printed activity/wellness rows look sane; if a field
  comes back `None` unexpectedly, print `act` or `stats` raw and adjust the
  key names in `garmin_sync.py` — Garmin's undocumented API does change.
- **Training load** prefers Garmin's own `activityTrainingLoad` field, falling
  back to a rough duration×HR proxy when it's missing. This is directionally
  useful for the CTL/ATL/TSB trend but isn't a true TSS — if you want power-
  and pace-based TSS specifically, that's a worthwhile v2 addition.
- **The plan parser is regex/keyword-based**, tuned to this spreadsheet's
  phrasing ("Z2", "threshold", "CSS", "~65 min total", "323 W"). If you
  restructure the sheet significantly, spot-check `parse_program.py`'s output
  (`python parse_program.py` prints a session count) before trusting it.
- **Sleep score**: Garmin's detailed sleep score isn't in the basic `get_stats`
  payload used here; `sleep_duration_min` is populated but `sleep_score` is a
  placeholder — `client.get_sleep_data(date)` has the real score if you want it.

## Project structure

```
config.py           # env-var driven settings (credentials, baselines, paths)
db.py                # SQLite schema + upsert helpers
parse_program.py     # xlsx -> planned_sessions table
garmin_sync.py        # Garmin Connect -> activities + wellness tables
analysis.py           # CTL/ATL/TSB, planned-vs-actual matching, volume by sport
app.py                # Streamlit dashboard (Overview / Plan vs Actual / Load / Recovery / By Sport)
```
