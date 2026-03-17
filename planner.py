from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Tuple


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class PriorityTask:
    title: str
    category: str
    hours: float
    enjoyment: int  # 1-5
    energy: str  # "High" | "Medium" | "Low"
    deadline: Optional[date]
    must_do: bool


@dataclass(frozen=True)
class Commitment:
    day: str  # "Mon"..."Sun"
    start_hour: int  # 0-23
    end_hour: int  # 1-24
    label: str


@dataclass(frozen=True)
class Slot:
    day: str
    start: datetime
    end: datetime
    label: str
    kind: str  # "task" | "commitment" | "break" | "buffer" | "fun"
    task_title: Optional[str] = None


def week_start_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _day_date_map(week_start: date) -> Dict[str, date]:
    return {WEEKDAYS[i]: week_start + timedelta(days=i) for i in range(7)}


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def _task_score(t: PriorityTask, now: date) -> float:
    """
    Higher = schedule earlier.
    Heuristic:
      - must_do boosts
      - nearer deadlines boost
      - higher energy tasks get earlier-day preference (handled later by slot ordering)
      - enjoyment lightly boosts to keep it fun
    """
    must = 3.0 if t.must_do else 0.0
    enjoy = (t.enjoyment - 3) * 0.15  # small
    deadline_boost = 0.0
    if t.deadline:
        days = max(0, (t.deadline - now).days)
        # 0 days -> big boost; 14+ days -> small boost
        deadline_boost = _clamp(2.5 - (days / 7.0), 0.2, 2.5)
    size = _clamp(t.hours / 6.0, 0.0, 1.0) * 0.25  # bigger tasks slightly earlier
    return must + deadline_boost + enjoy + size


def _hour_blocks(
    week_start: date,
    day: str,
    start_hour: int,
    end_hour: int,
) -> List[Tuple[datetime, datetime]]:
    dd = _day_date_map(week_start)[day]
    blocks: List[Tuple[datetime, datetime]] = []
    for h in range(start_hour, end_hour):
        s = datetime.combine(dd, time(hour=h))
        e = s + timedelta(hours=1)
        blocks.append((s, e))
    return blocks


def build_week_plan(
    *,
    week_start: date,
    availability: Dict[str, Tuple[int, int]],
    tasks: List[PriorityTask],
    commitments: List[Commitment],
    buffer_ratio: float = 0.12,
    add_fun_daily: bool = True,
    working_days: Optional[List[str]] = None,
    fun_hours_per_week: Optional[int] = None,
    max_consecutive_focus_hours: int = 2,
) -> List[Slot]:
    """
    Returns a flat list of Slots for the whole week.
    """
    if working_days is None:
        working_days = WEEKDAYS.copy()
    # Safety: avoid weird values
    max_consecutive_focus_hours = max(1, max_consecutive_focus_hours)

    day_dates = _day_date_map(week_start)

    # 1) Build free hour blocks from availability
    free_blocks: List[Tuple[str, datetime, datetime]] = []
    for day in working_days:
        start_h, end_h = availability[day]
        for s, e in _hour_blocks(week_start, day, start_h, end_h):
            free_blocks.append((day, s, e))

    # 2) Mark commitments as occupied
    occupied = set()  # (day, hour)
    commitment_slots: List[Slot] = []
    for c in commitments:
        c_day = c.day
        dd = day_dates[c_day]
        for h in range(c.start_hour, c.end_hour):
            occupied.add((c_day, h))
        commitment_slots.append(
            Slot(
                day=c_day,
                start=datetime.combine(dd, time(hour=c.start_hour)),
                end=datetime.combine(dd, time(hour=c.end_hour)),
                label=c.label,
                kind="commitment",
            )
        )

    # 3) Prepare free hourly slots excluding occupied
    candidate: List[Tuple[str, datetime, datetime]] = []
    for day, s, e in free_blocks:
        if (day, s.hour) in occupied:
            continue
        candidate.append((day, s, e))

    # Order slots for "efficiency": mornings first, then early afternoon, then late.
    # Also bias Mon/Tue earlier for big wins.
    day_rank = {d: i for i, d in enumerate(WEEKDAYS)}

    def slot_key(x: Tuple[str, datetime, datetime]) -> Tuple[int, int]:
        day, s, _ = x
        hour = s.hour
        # morning bucket: 5..11 -> best
        morning_bonus = 0 if 7 <= hour <= 11 else (1 if 12 <= hour <= 15 else 2)
        return (day_rank[day] * 10 + morning_bonus, hour)

    candidate.sort(key=slot_key)

    # 4) Reserve buffers
    buffer_count = int(round(len(candidate) * _clamp(buffer_ratio, 0.0, 0.35)))
    buffer_slots: List[Slot] = []
    reserved = set()
    # Put buffers near end-of-day to keep them flexible.
    for day in WEEKDAYS:
        day_slots = [x for x in candidate if x[0] == day]
        # choose latest hours first
        for (d, s, e) in sorted(day_slots, key=lambda x: x[1].hour, reverse=True):
            if len(reserved) >= buffer_count:
                break
            reserved.add((d, s))
            buffer_slots.append(
                Slot(day=d, start=s, end=e, label="Buffer / catch-up", kind="buffer")
            )
        if len(reserved) >= buffer_count:
            break

    candidate_for_tasks = [x for x in candidate if (x[0], x[1]) not in reserved]

    # 5) Optionally add fun slots across the week.
    # Decide how many fun hours to add: either an explicit weekly target or 1 per working day.
    total_free_slots = len(candidate_for_tasks)
    if fun_hours_per_week is not None:
        target_fun_slots = max(0, min(fun_hours_per_week, total_free_slots))
    elif add_fun_daily:
        target_fun_slots = min(len(working_days), total_free_slots)
    else:
        target_fun_slots = 0

    fun_slots: List[Slot] = []
    fun_reserved = set()
    if target_fun_slots > 0:
        remaining_fun = target_fun_slots

        # First pass: try to place at most one fun hour per working day in mid‑afternoon.
        for day in working_days:
            if remaining_fun <= 0:
                break
            day_slots = [x for x in candidate_for_tasks if x[0] == day]
            if not day_slots:
                continue
            # choose mid-afternoon if possible (more sustainable), else earliest
            preferred = [x for x in day_slots if 14 <= x[1].hour <= 17]
            pick = (preferred[0] if preferred else day_slots[0])
            fun_reserved.add((pick[0], pick[1]))
            fun_slots.append(
                Slot(
                    day=pick[0],
                    start=pick[1],
                    end=pick[2],
                    label="Fun recharge (walk/game/music/anything)",
                    kind="fun",
                )
            )
            remaining_fun -= 1

        # Second pass: if there is still fun time left, fill remaining free slots irrespective of day.
        if remaining_fun > 0:
            remaining_candidates = [
                x for x in candidate_for_tasks if (x[0], x[1]) not in fun_reserved
            ]
            # Prefer mid-afternoon slots overall, then earliest.
            def fun_key(x: Tuple[str, datetime, datetime]) -> Tuple[int, int]:
                _, s, _ = x
                hour = s.hour
                # mid-afternoon best, then other daytime, then everything else
                if 14 <= hour <= 17:
                    bucket = 0
                elif 9 <= hour <= 19:
                    bucket = 1
                else:
                    bucket = 2
                return (bucket, hour)

            remaining_candidates.sort(key=fun_key)
            for d, s, e in remaining_candidates:
                if remaining_fun <= 0:
                    break
                fun_reserved.add((d, s))
                fun_slots.append(
                    Slot(
                        day=d,
                        start=s,
                        end=e,
                        label="Fun recharge (walk/game/music/anything)",
                        kind="fun",
                    )
                )
                remaining_fun -= 1

        candidate_for_tasks = [
            x for x in candidate_for_tasks if (x[0], x[1]) not in fun_reserved
        ]

    # 6) Allocate tasks hour-by-hour
    now = week_start
    task_queue = sorted(tasks, key=lambda t: _task_score(t, now), reverse=True)

    # Expand tasks into remaining hours (rounded up)
    remaining: List[Tuple[PriorityTask, int]] = []
    for t in task_queue:
        hours = max(0, int((t.hours + 0.9999) // 1))  # ceil to hour chunks
        if hours <= 0:
            continue
        remaining.append((t, hours))

    # Split by energy to match time-of-day
    high = [(t, h) for t, h in remaining if t.energy == "High"]
    med = [(t, h) for t, h in remaining if t.energy == "Medium"]
    low = [(t, h) for t, h in remaining if t.energy == "Low"]

    def pop_next(pool: List[Tuple[PriorityTask, int]]) -> Optional[PriorityTask]:
        if not pool:
            return None
        t, hrs = pool[0]
        if hrs <= 1:
            pool.pop(0)
        else:
            pool[0] = (t, hrs - 1)
        return t

    task_slots: List[Slot] = []

    def choose_pool(hour: int) -> List[Tuple[PriorityTask, int]]:
        # Morning: high, midday: medium, late: low (but fall back if empty)
        if 7 <= hour <= 11:
            return high or med or low
        if 12 <= hour <= 15:
            return med or high or low
        return low or med or high

    # Light anti-burnout: after N consecutive task hours, prefer a break if available.
    consec_tasks = 0
    breaks: List[Slot] = []
    # Limit: at most one coffee chat per day
    coffee_per_day: Dict[str, int] = {}

    for day, s, e in candidate_for_tasks:
        hour = s.hour

        if consec_tasks >= max_consecutive_focus_hours:
            # Insert a break hour occasionally (only if we still have many task hours left)
            total_left = sum(h for _, h in high + med + low)
            if total_left >= 4:
                breaks.append(
                    Slot(
                        day=day,
                        start=s,
                        end=e,
                        label="Break / reset (stretch, snack, sunlight)",
                        kind="break",
                    )
                )
                consec_tasks = 0
                continue

        pool = choose_pool(hour)
        t = pop_next(pool)
        if not t:
            # nothing left to schedule
            continue

        is_coffee = (t.category.lower() == "coffee chat") or ("coffee" in t.title.lower())
        if is_coffee and coffee_per_day.get(day, 0) >= 1:
            # Skip extra coffee chats for this day; this hour stays free/unused.
            consec_tasks = 0
            continue

        label = f"{t.title} ({t.category})"
        task_slots.append(
            Slot(day=day, start=s, end=e, label=label, kind="task", task_title=t.title)
        )
        if is_coffee:
            coffee_per_day[day] = coffee_per_day.get(day, 0) + 1
        consec_tasks += 1

    # 7) Combine all slots (commitments may overlap; UI can render separately)
    all_slots = commitment_slots + buffer_slots + fun_slots + breaks + task_slots
    all_slots.sort(key=lambda sl: (day_rank[sl.day], sl.start, sl.kind))
    return all_slots


def slots_to_table(slots: Iterable[Slot]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for s in slots:
        out.append(
            {
                "day": s.day,
                "start": s.start.strftime("%Y-%m-%d %H:%M"),
                "end": s.end.strftime("%Y-%m-%d %H:%M"),
                "kind": s.kind,
                "label": s.label,
            }
        )
    return out


def slots_to_ics(slots: Iterable[Slot], calendar_name: str = "Weekly Plan") -> str:
    """
    Minimal ICS generator (no external deps). Works with most calendar apps.
    """
    def fmt(dt: datetime) -> str:
        # floating local time
        return dt.strftime("%Y%m%dT%H%M%S")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WeeklyPlanExecutor//EN",
        f"X-WR-CALNAME:{calendar_name}",
        "CALSCALE:GREGORIAN",
    ]
    now = datetime.now().strftime("%Y%m%dT%H%M%S")
    for i, s in enumerate(slots):
        uid = f"wpe-{s.day}-{s.start.strftime('%Y%m%dT%H%M')}-{i}@local"
        summary = s.label.replace("\n", " ").strip()
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now}",
                f"DTSTART:{fmt(s.start)}",
                f"DTEND:{fmt(s.end)}",
                f"SUMMARY:{summary}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
