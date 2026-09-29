import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis import (
    load_activities_df,
    load_wellness_df,
    load_planned_df,
    compute_ctl_atl_tsb,
    planned_vs_actual,
    sport_zone_distribution,
)
from db import init_db

st.set_page_config(page_title="Triathlon Dashboard", layout="wide")
init_db()

activities = load_activities_df()
wellness = load_wellness_df()
planned = load_planned_df()

st.sidebar.title("Triathlon Dashboard")
page = st.sidebar.radio(
    "View", ["Overview", "Plan vs Actual", "Training Load", "Recovery", "By Sport"]
)

if activities.empty:
    st.warning(
        "No activity data yet. Run `python garmin_sync.py` to pull from Garmin Connect, "
        "and `python parse_program.py` to load the training plan."
    )

# ---------------------------------------------------------------- Overview
if page == "Overview":
    st.header("Overview")

    col1, col2, col3 = st.columns(3)
    if not activities.empty:
        last_7 = activities[activities["date"] >= pd.Timestamp.today() - pd.Timedelta(days=7)]
        col1.metric("Sessions (last 7d)", len(last_7))
        col2.metric("Training time (last 7d)", f"{last_7['duration_sec'].sum()/3600:.1f} h")
    if not wellness.empty and wellness["training_readiness"].notna().any():
        latest_readiness = wellness.sort_values("date")["training_readiness"].dropna()
        if not latest_readiness.empty:
            col3.metric("Training Readiness (latest)", int(latest_readiness.iloc[-1]))

    if not planned.empty:
        upcoming = planned[planned["date"] >= pd.Timestamp.today()].sort_values("date").head(7)
        st.subheader("Next 7 planned sessions")
        st.dataframe(
            upcoming[["date", "day_of_week", "sport", "session_type", "description"]],
            hide_index=True,
            use_container_width=True,
        )

    if not activities.empty:
        st.subheader("Recent activities")
        recent = activities.sort_values("date", ascending=False).head(10)
        st.dataframe(
            recent[["date", "sport", "name", "duration_sec", "distance_m", "avg_hr"]],
            hide_index=True,
            use_container_width=True,
        )

# ------------------------------------------------------------ Plan vs Actual
elif page == "Plan vs Actual":
    st.header("Plan vs Actual")

    if planned.empty:
        st.info("No plan loaded. Run `python parse_program.py` first.")
    else:
        weeks = sorted(planned["week"].unique())
        selected_week = st.selectbox("Week", weeks, index=min(len(weeks) - 1, 0))
        pva = planned_vs_actual(planned, activities)
        week_view = pva[pva["week"] == selected_week].sort_values("date")

        completed_count = week_view["completed"].sum()
        st.metric("Sessions completed this week", f"{completed_count} / {len(week_view)}")

        def highlight(row):
            color = "background-color: #d4edda" if row["completed"] else "background-color: #f8d7da"
            return [color] * len(row)

        st.dataframe(
            week_view[
                [
                    "date",
                    "day_of_week",
                    "sport",
                    "session_type",
                    "description",
                    "planned_duration_min",
                    "actual_duration_min",
                    "completion_pct",
                    "completed",
                ]
            ].style.apply(highlight, axis=1),
            hide_index=True,
            use_container_width=True,
        )

# ------------------------------------------------------------- Training Load
elif page == "Training Load":
    st.header("Training Load (CTL / ATL / TSB)")
    st.caption(
        "Fitness (CTL, 42-day trend), Fatigue (ATL, 7-day trend), and Form (TSB = CTL − ATL) — "
        "the same model TrainingPeaks / intervals.icu use for their PMC chart."
    )

    if activities.empty:
        st.info("No activity data yet.")
    else:
        pmc = compute_ctl_atl_tsb(activities)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=pmc["date"], y=pmc["ctl"], name="Fitness (CTL)", line=dict(color="blue")))
        fig.add_trace(go.Scatter(x=pmc["date"], y=pmc["atl"], name="Fatigue (ATL)", line=dict(color="orange")))
        fig.add_trace(go.Bar(x=pmc["date"], y=pmc["tsb"], name="Form (TSB)", opacity=0.4))
        fig.update_layout(height=450, legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "Note: training load uses Garmin's own activityTrainingLoad where available, "
            "with a rough duration/HR fallback otherwise — treat the trend as directionally "
            "useful rather than an exact TSS equivalent."
        )

# ----------------------------------------------------------------- Recovery
elif page == "Recovery":
    st.header("Recovery Signals")

    if wellness.empty:
        st.info("No wellness data yet.")
    else:
        metric = st.selectbox(
            "Metric",
            ["resting_hr", "hrv_avg", "training_readiness", "body_battery_max", "stress_avg"],
        )
        fig = px.line(wellness, x="date", y=metric, markers=True)
        st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------------------------- Sport
elif page == "By Sport":
    st.header("Volume by Sport")
    sport = st.selectbox("Sport", ["bike", "run", "swim", "strength"])
    dist = sport_zone_distribution(activities, sport)
    if dist.empty:
        st.info(f"No {sport} activities synced yet.")
    else:
        fig = px.bar(dist, x="week", y="minutes", title=f"Weekly {sport} minutes")
        st.plotly_chart(fig, use_container_width=True)
