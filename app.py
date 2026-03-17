from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Tuple

import json
from collections import defaultdict
from math import ceil
import pandas as pd
import streamlit as st

from planner import Commitment, PriorityTask, WEEKDAYS, build_week_plan, slots_to_ics, slots_to_table, week_start_monday


st.set_page_config(page_title="Weekly Plan Executor", page_icon="🗓️", layout="wide")


def _default_availability() -> Dict[str, Tuple[int, int]]:
    # Reasonable defaults: workdays 9-18, weekends 10-16
    out: Dict[str, Tuple[int, int]] = {}
    for d in WEEKDAYS:
        out[d] = (9, 18) if d in ["Mon", "Tue", "Wed", "Thu", "Fri"] else (10, 16)
    return out


def _df_to_tasks(df: pd.DataFrame) -> List[PriorityTask]:
    tasks: List[PriorityTask] = []
    for _, r in df.iterrows():
        title = str(r.get("Priority", "")).strip()
        if not title:
            continue
        category = str(r.get("Category", "General")).strip() or "General"
        hours = float(r.get("Hours", 0) or 0)
        enjoyment = int(r.get("Fun (1-5)", 3) or 3)
        energy = str(r.get("Energy", "Medium")).strip() or "Medium"
        deadline_val = r.get("Deadline", None)
        deadline = None
        if isinstance(deadline_val, (date, datetime)):
            deadline = deadline_val if isinstance(deadline_val, date) else deadline_val.date()
        must_do = bool(r.get("Must do", False))
        tasks.append(
            PriorityTask(
                title=title,
                category=category,
                hours=max(0.0, hours),
                enjoyment=max(1, min(5, enjoyment)),
                energy=energy if energy in ["High", "Medium", "Low"] else "Medium",
                deadline=deadline,
                must_do=must_do,
            )
        )
    return tasks


def _df_to_commitments(df: pd.DataFrame) -> List[Commitment]:
    out: List[Commitment] = []
    for _, r in df.iterrows():
        day = str(r.get("Day", "")).strip()
        if day not in WEEKDAYS:
            continue
        label = str(r.get("Label", "")).strip() or "Commitment"
        try:
            start_h = int(r.get("Start hour", 0))
            end_h = int(r.get("End hour", 0))
        except Exception:
            continue
        start_h = max(0, min(23, start_h))
        end_h = max(start_h + 1, min(24, end_h))
        out.append(Commitment(day=day, start_hour=start_h, end_hour=end_h, label=label))
    return out


def _calendar_matrix(slots) -> pd.DataFrame:
    """
    Build a simple hour x weekday grid DataFrame for calendar-style viewing.
    """
    slots = list(slots or [])
    if not slots:
        return pd.DataFrame(columns=WEEKDAYS)

    min_hour = min(s.start.hour for s in slots)
    max_hour = max(s.end.hour for s in slots)
    hours = list(range(min_hour, max_hour))

    # initialise empty grid
    data: Dict[str, List[str]] = {d: ["" for _ in hours] for d in WEEKDAYS}
    hour_to_idx = {h: i for i, h in enumerate(hours)}

    for s in slots:
        idx = hour_to_idx.get(s.start.hour)
        if idx is None or s.day not in data:
            continue
        kind_prefix = {
            "task": "",
            "commitment": "[Fix] ",
            "break": "[Break] ",
            "buffer": "[Buf] ",
            "fun": "[Fun] ",
        }.get(s.kind, "")
        label = kind_prefix + s.label
        # keep labels short-ish
        if len(label) > 40:
            label = label[:37] + "..."
        existing = data[s.day][idx]
        data[s.day][idx] = f"{existing} | {label}" if existing else label

    df = pd.DataFrame(data, index=[f"{h:02d}:00" for h in hours])
    df.index.name = "Hour"
    return df


def _render_day(week_df: pd.DataFrame, day: str, key_prefix: str) -> None:
    day_df = week_df[week_df["day"] == day].copy()
    if day_df.empty:
        st.caption("No scheduled items.")
        return

    # Sort by start time within day
    day_df["start_dt"] = pd.to_datetime(day_df["start"])
    day_df = day_df.sort_values(["start_dt", "kind"], ascending=[True, True])

    # Executor: checkboxes for "task" items only
    for i, row in day_df.iterrows():
        start_dt = pd.to_datetime(row["start"])
        end_dt = pd.to_datetime(row["end"])
        start = start_dt.strftime("%H:%M")
        end = end_dt.strftime("%H:%M")
        label = row["label"]
        kind = row["kind"]
        line = f"{start}–{end}  ·  {label}"

        if kind == "task":
            ck_key = f"{key_prefix}:{day}:{row['start']}:{label}"
            st.checkbox(line, key=ck_key)
        else:
            badge = {
                "commitment": "Fixed",
                "break": "Break",
                "buffer": "Buffer",
                "fun": "Fun",
            }.get(kind, kind)
            st.markdown(f"- **{badge}**: {line}")


st.title("Weekly Plan Executor")
st.caption("Tell me what matters this week. I’ll turn it into an hour-by-hour plan you can execute.")

if "availability" not in st.session_state:
    st.session_state["availability"] = _default_availability()
if "working_days" not in st.session_state:
    # Default: standard Mon–Fri workweek
    st.session_state["working_days"] = WEEKDAYS[:5]

tab_build, tab_week, tab_calendar, tab_execute = st.tabs(
    ["Build", "Week view", "Calendar view", "Execute today"]
)

with tab_build:
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.subheader("1) Week + availability")
        today = date.today()
        week_start = st.date_input("Week starts (Monday)", value=week_start_monday(today))
        week_start = week_start_monday(week_start)

        # Working days + availability presets
        working_days = st.multiselect(
            "Working days",
            options=WEEKDAYS,
            default=st.session_state["working_days"],
            help="Days you want to schedule tasks on.",
        )
        if not working_days:
            working_days = WEEKDAYS[:5]
        st.session_state["working_days"] = working_days

        preset = st.selectbox(
            "Availability preset",
            options=["Custom", "Standard 9–5 weekdays"],
            index=1,
            help="Quickly set a typical work schedule.",
        )

        st.write("Availability (hours you want to schedule within):")
        avail = st.session_state["availability"]

        if preset == "Standard 9–5 weekdays":
            for d in WEEKDAYS:
                if d in WEEKDAYS[:5]:
                    avail[d] = (9, 17)

        for d in WEEKDAYS:
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                st.write(f"**{d}**")
            with c2:
                start_h = st.number_input(f"{d} start", min_value=0, max_value=23, value=int(avail[d][0]), key=f"avail:{d}:s")
            with c3:
                end_h = st.number_input(f"{d} end", min_value=1, max_value=24, value=int(avail[d][1]), key=f"avail:{d}:e")
            if end_h <= start_h:
                end_h = min(24, start_h + 1)
            avail[d] = (int(start_h), int(end_h))
        st.session_state["availability"] = avail

        st.subheader("2) Strategy knobs")
        buffer_ratio = st.slider(
            "Weekly buffer (flex time)",
            min_value=0.0,
            max_value=0.35,
            value=0.12,
            step=0.01,
            help="Fraction of free hours kept as slack / catch‑up time.",
        )
        fun_hours = st.slider(
            "Target fun / recharge hours per week",
            min_value=0,
            max_value=14,
            value=5,
            step=1,
        )
        max_focus_hours = st.slider(
            "Max consecutive focus hours before a break",
            min_value=1,
            max_value=4,
            value=2,
            step=1,
        )

    with right:
        st.subheader("3) Priorities")
        st.write("Add what matters. Put rough hours — the app schedules in **hour chunks**.")

        default_tasks = pd.DataFrame(
            [
                {"Priority": "Main project", "Category": "Deep work", "Hours": 6, "Energy": "High", "Fun (1-5)": 3, "Deadline": None, "Must do": True},
                {"Priority": "Admin + email batch", "Category": "Admin", "Hours": 2, "Energy": "Low", "Fun (1-5)": 2, "Deadline": None, "Must do": False},
                {"Priority": "Workout", "Category": "Health", "Hours": 3, "Energy": "Medium", "Fun (1-5)": 4, "Deadline": None, "Must do": True},
            ]
        )

        if "tasks_df" not in st.session_state:
            st.session_state["tasks_df"] = default_tasks

        tasks_df = st.data_editor(
            st.session_state["tasks_df"],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Energy": st.column_config.SelectboxColumn(options=["High", "Medium", "Low"]),
                "Fun (1-5)": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
                "Deadline": st.column_config.DateColumn(),
                "Must do": st.column_config.CheckboxColumn(),
                "Hours": st.column_config.NumberColumn(min_value=0, step=1),
            },
        )
        st.session_state["tasks_df"] = tasks_df

        st.subheader("4) Fixed commitments")
        default_commit = pd.DataFrame(
            [
                {"Day": "Mon", "Start hour": 12, "End hour": 13, "Label": "Lunch / break"},
            ]
        )
        if "commit_df" not in st.session_state:
            st.session_state["commit_df"] = default_commit

        commit_df = st.data_editor(
            st.session_state["commit_df"],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Day": st.column_config.SelectboxColumn(options=WEEKDAYS),
                "Start hour": st.column_config.NumberColumn(min_value=0, max_value=23, step=1),
                "End hour": st.column_config.NumberColumn(min_value=1, max_value=24, step=1),
            },
        )
        st.session_state["commit_df"] = commit_df

    st.divider()
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        generate = st.button("Generate plan", type="primary", use_container_width=True)
    with c2:
        clear_checks = st.button("Reset executor checkboxes", use_container_width=True)
    with c3:
        st.caption("Tip: Put hard tasks first and give them enough hours. Buffers + fun hours keep the plan realistic.")

    if clear_checks:
        # Remove only checkbox states (keep data)
        keys_to_del = [k for k in st.session_state.keys() if str(k).startswith("exec:")]
        for k in keys_to_del:
            del st.session_state[k]
        st.success("Executor checkboxes reset.")

    if generate:
        tasks = _df_to_tasks(tasks_df)
        commits = _df_to_commitments(commit_df)

        slots = build_week_plan(
            week_start=week_start,
            availability=st.session_state["availability"],
            tasks=tasks,
            commitments=commits,
            buffer_ratio=buffer_ratio,
            add_fun_daily=fun_hours > 0,
            working_days=st.session_state["working_days"],
            fun_hours_per_week=fun_hours,
            max_consecutive_focus_hours=max_focus_hours,
        )

        week_table = pd.DataFrame(slots_to_table(slots))
        st.session_state["generated_slots"] = slots
        st.session_state["week_table"] = week_table
        st.session_state["week_start"] = week_start

        # Compute simple capacity & overflow summary for Week view.
        hours_by_title: Dict[str, float] = defaultdict(float)
        for t in tasks:
            hours_by_title[t.title] += max(0.0, t.hours)

        scheduled_by_title: Dict[str, int] = defaultdict(int)
        for s in slots:
            if s.kind == "task" and s.task_title:
                scheduled_by_title[s.task_title] += 1

        overflow_rows: List[Dict[str, int]] = []
        requested_total = 0
        for title, hrs in hours_by_title.items():
            target = ceil(hrs)
            requested_total += target
            scheduled = scheduled_by_title.get(title, 0)
            unscheduled = max(0, target - scheduled)
            if unscheduled > 0:
                overflow_rows.append(
                    {
                        "Task": title,
                        "Target hours": target,
                        "Scheduled hours": scheduled,
                        "Unscheduled hours": unscheduled,
                    }
                )

        avail_hours_window = 0
        for d in st.session_state["working_days"]:
            start_h, end_h = st.session_state["availability"][d]
            avail_hours_window += max(0, end_h - start_h)

        summary = {
            "total_available_window_hours": avail_hours_window,
            "requested_task_hours": requested_total,
            "scheduled_task_hours": sum(scheduled_by_title.values()),
            "unscheduled_task_hours": max(
                0, requested_total - sum(scheduled_by_title.values())
            ),
            "fun_hours": len([s for s in slots if s.kind == "fun"]),
            "buffer_hours": len([s for s in slots if s.kind == "buffer"]),
            "overflow_rows": overflow_rows,
        }
        st.session_state["plan_summary"] = summary

        st.success("Plan generated. Check the Week view / Execute today tabs.")

with tab_week:
    st.subheader("Week view (hour-by-hour)")
    week_table = st.session_state.get("week_table", None)
    slots = st.session_state.get("generated_slots", None)

    if week_table is None or slots is None:
        st.info("Generate a plan in the Build tab first.")
    else:
        summary = st.session_state.get("plan_summary")
        if summary:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric(
                    "Task hours scheduled",
                    f"{summary['scheduled_task_hours']}h",
                    delta=f"{summary['requested_task_hours'] - summary['scheduled_task_hours']}h remaining",
                )
            with c2:
                st.metric("Buffer hours", f"{summary['buffer_hours']}h")
            with c3:
                st.metric("Fun hours", f"{summary['fun_hours']}h")
            with c4:
                st.metric(
                    "Capacity window",
                    f"{summary['total_available_window_hours']}h",
                )

        st.dataframe(week_table, use_container_width=True, hide_index=True)

        csv_bytes = week_table.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv_bytes,
            file_name="weekly-plan.csv",
            mime="text/csv",
        )

        ics_text = slots_to_ics(slots, calendar_name="Weekly Plan Executor")
        st.download_button(
            "Download ICS (calendar)",
            data=ics_text.encode("utf-8"),
            file_name="weekly-plan.ics",
            mime="text/calendar",
        )

        if summary:
            st.markdown("#### Capacity & overflow")
            st.write(
                f"Requested task hours: **{summary['requested_task_hours']}h**, "
                f"scheduled: **{summary['scheduled_task_hours']}h**, "
                f"unscheduled: **{summary['unscheduled_task_hours']}h**."
            )
            overflow_rows = summary.get("overflow_rows") or []
            if overflow_rows:
                st.caption("Some tasks didn't fully fit into the week:")
                overflow_df = pd.DataFrame(overflow_rows)
                st.dataframe(overflow_df, use_container_width=True, hide_index=True)
            else:
                st.caption("All requested task hours fit inside your chosen window.")

with tab_calendar:
    st.subheader("Calendar view (grid)")
    week_table = st.session_state.get("week_table", None)
    slots = st.session_state.get("generated_slots", None)

    if week_table is None or slots is None:
        st.info("Generate a plan in the Build tab first.")
    else:
        cal_df = _calendar_matrix(slots)
        st.dataframe(cal_df, use_container_width=True)

with tab_execute:
    st.subheader("Execute today")
    week_table = st.session_state.get("week_table", None)
    if week_table is None:
        st.info("Generate a plan in the Build tab first.")
    else:
        # Determine today's weekday label
        today = date.today()
        # Map python weekday (Mon=0) to WEEKDAYS
        today_label = WEEKDAYS[today.weekday()]
        day = st.selectbox("Day", options=WEEKDAYS, index=WEEKDAYS.index(today_label))

        # Progress
        day_df = week_table[week_table["day"] == day]
        task_rows = day_df[day_df["kind"] == "task"]
        if len(task_rows) == 0:
            st.caption("No tasks scheduled for this day.")
        else:
            checked = 0
            for _, r in task_rows.iterrows():
                ck_key = f"exec:{day}:{r['start']}:{r['label']}"
                if st.session_state.get(ck_key, False):
                    checked += 1
            st.progress(checked / max(1, len(task_rows)), text=f"{checked}/{len(task_rows)} task-hours done")

        # Simple \"now\" and \"next\" indicators based on local time.
        if not day_df.empty:
            now = datetime.now()
            day_df_local = day_df.copy()
            day_df_local["start_dt"] = pd.to_datetime(day_df_local["start"])
            day_df_local["end_dt"] = pd.to_datetime(day_df_local["end"])
            current = day_df_local[
                (day_df_local["start_dt"] <= now) & (day_df_local["end_dt"] > now)
            ]
            upcoming = day_df_local[day_df_local["start_dt"] > now].sort_values(
                "start_dt"
            )

            if not current.empty:
                r = current.iloc[0]
                st.markdown(
                    f"**Now**: {r['start_dt']:%H:%M}–{r['end_dt']:%H:%M} · {r['label']} ({r['kind']})"
                )
            if not upcoming.empty:
                r_next = upcoming.iloc[0]
                st.markdown(
                    f"**Next**: {r_next['start_dt']:%H:%M}–{r_next['end_dt']:%H:%M} · {r_next['label']} ({r_next['kind']})"
                )

        st.divider()
        _render_day(week_table, day, key_prefix="exec")

