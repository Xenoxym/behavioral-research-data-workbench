"""Reproducible synthetic cohort and separately labelled corruption benchmark."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import random
import pandas as pd
from .schema import TABLE_COLUMNS, save_bundle

AS_OF = date(2026, 10, 16)


def generate_clean(seed=42, n=240):
    """Create n screenings; all names/contact details are deliberately absent.

    This is operational demonstration data, not an intervention-effect simulation.
    No arm effect is built in. All date/status decisions use a fixed reference date.
    """
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("n must be a positive integer")
    rng = random.Random(seed)
    records = {table: [] for table in TABLE_COLUMNS}
    for index in range(n):
        number = index + 1
        pid = f"SYN-{number:04d}"
        screening = date(2026, 7, 1) + timedelta(days=index % 105)
        underage = index % 12 == 0
        low_use = index % 12 == 6
        eligible = not (underage or low_use)
        declined = eligible and index % 11 == 0
        enrolled = screening + timedelta(days=2) if eligible and not declined else None
        withdrawal = None
        if enrolled is not None:
            candidate = enrolled + timedelta(days=10 if index % 23 == 0 else 45)
            if (index % 19 == 0 or index % 23 == 0) and candidate <= AS_OF:
                withdrawal = candidate
        person = {
            "row_id": f"P{number:04d}", "participant_id": pid,
            "age": rng.randint(16, 17) if underage else rng.randint(18, 76),
            "screening_date": screening.isoformat(), "eligible": int(eligible),
            "eligibility_reason": "underage" if underage else "low_use" if low_use else "declined" if declined else "eligible",
            "consent_date": (screening + timedelta(days=1)).isoformat() if enrolled else None,
            "enrollment_date": enrolled.isoformat() if enrolled else None,
            "arm": ("control" if index % 2 else "app") if enrolled else None,
            "withdrawal_date": withdrawal.isoformat() if withdrawal else None,
            "withdrawal_reason": "participant_request" if withdrawal else None,
        }
        records["participants"].append(person)
        records["contacts"].append({"row_id": f"C{number:04d}", "participant_id": pid,
            "contacted_at": screening.isoformat(), "channel": "phone" if index % 2 else "email",
            "outcome": "declined" if declined else "no_answer" if index % 9 == 0 else "reached",
            "note": "Synthetic contact log only; no communication sent."})
        if enrolled is None:
            continue
        cigarettes = rng.randint(5, 35)
        records["baseline"].append({"row_id": f"B{number:04d}", "participant_id": pid,
            "assessed_at": enrolled.isoformat(), "cigarettes_per_day": cigarettes,
            "readiness": rng.randint(0, 10), "co_ppm": round(rng.uniform(4, 35), 1),
            "nicotine_replacement": int(index % 4 == 0)})
        for code, offset in [("W04", 28), ("W12", 84)]:
            target = enrolled + timedelta(days=offset)
            start, end = target - timedelta(days=7), target + timedelta(days=7)
            completed, count, abstinent, co = None, None, None, None
            if withdrawal is not None and withdrawal < start:
                status, reason = "withdrawn", "not_applicable"
            elif start <= AS_OF and index % 7 != 0:
                completed = min(target + timedelta(days=rng.randint(-4, 4)), AS_OF)
                if withdrawal is not None and completed > withdrawal:
                    status, reason, completed = "missed", "unable_to_reach", None
                else:
                    status, reason = "completed", None
                    abstinent = int(rng.random() < 0.3)
                    count = 0 if abstinent else rng.randint(1, cigarettes * 7)
                    co = round(rng.uniform(0.3, 4.5) if abstinent else rng.uniform(2, 35), 1)
                    # A valid skipped CO assessment is explicitly reason-coded.
                    if index % 17 == 0:
                        co, reason = None, "declined"
            elif end < AS_OF:
                status, reason = "missed", "unable_to_reach"
            else:
                status, reason = "scheduled", None
            records["visits"].append({"row_id": f"V{number:04d}-{code}", "participant_id": pid,
                "visit_code": code, "target_date": target.isoformat(), "window_start": start.isoformat(),
                "window_end": end.isoformat(), "completed_at": completed.isoformat() if completed else None,
                "status": status, "cigarettes_7d": count, "abstinent_7d": abstinent, "co_ppm": co,
                "missing_reason": reason})
        for day in range(14):
            prompt_date = enrolled + timedelta(days=day)
            if prompt_date > AS_OF or (withdrawal is not None and prompt_date > withdrawal):
                continue
            prompt = datetime.combine(prompt_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)
            state = ("answered", "answered", "answered", "missed", "declined", "not_applicable")[(index + day) % 6]
            response = prompt + timedelta(minutes=rng.randint(1, 80)) if state == "answered" else None
            # A delayed upload is a legitimate offline response, not a late answer.
            upload = response + timedelta(hours=48 if (index + day) % 5 == 0 else 0, minutes=2) if response else None
            records["ema"].append({"row_id": f"E{number:04d}-{day + 1:02d}", "participant_id": pid,
                "prompted_at": prompt.isoformat(), "responded_at": response.isoformat() if response else None,
                "uploaded_at": upload.isoformat() if upload else None,
                "urge": rng.randint(0, 10) if response else None,
                "stress": rng.randint(0, 10) if response else None, "response_state": state})
    return {table: pd.DataFrame(rows, columns=TABLE_COLUMNS[table]) for table, rows in records.items()}


def inject_errors(clean):
    """Plant labelled defects without calling/importing the quality checker.

    Labels identify independently expected issue matches, including both sides of
    duplicated participant/event keys. A single mutation can produce several labels.
    The benchmark fixture needs at least 30 ordinary enrolled participants.
    """
    bundle = {table: frame.copy(deep=True).astype(object) for table, frame in clean.items()}
    participants = bundle["participants"]
    ordinary = participants[participants.enrollment_date.notna() & participants.withdrawal_date.isna()]
    if len(ordinary) < 30:
        raise ValueError("Error injection requires at least 30 nonwithdrawn enrolled participants; use n=60 or more.")
    people = ordinary.iloc[:30]
    ids = people.participant_id.tolist()
    labels = []

    def label(table, row_id, field, rule):
        labels.append({"table": table, "row_id": row_id, "field": field, "rule_id": rule})

    def choose(table, pid, **filters):
        mask = bundle[table].participant_id.eq(pid)
        for field, value in filters.items():
            mask &= bundle[table][field].eq(value)
        rows = bundle[table][mask]
        if rows.empty:
            raise ValueError(f"Cannot inject into {table}/{pid}/{filters}")
        return rows.index[0], rows.iloc[0].row_id

    def change(table, pid, field, value, rule, **filters):
        index, row_id = choose(table, pid, **filters)
        bundle[table].at[index, field] = value
        label(table, row_id, field, rule)
        return index, row_id

    # Repeated ID with distinct row IDs: report both members, no truth in runtime data.
    original = people.iloc[0].copy()
    duplicate = original.copy()
    duplicate["row_id"] = "P-DUPLICATE"
    bundle["participants"] = pd.concat([bundle["participants"], duplicate.to_frame().T], ignore_index=True)
    for row_id in [original.row_id, duplicate.row_id]:
        label("participants", row_id, "participant_id", "DUPLICATE_ID")
    change("participants", ids[1], "age", 17, "AGE_ELIGIBILITY")
    change("participants", ids[2], "age", 125, "RANGE")
    change("participants", ids[3], "eligible", 0, "ELIGIBILITY_CONFLICT")
    _, row_id = choose("participants", ids[3])
    label("participants", row_id, "eligibility_reason", "ELIGIBILITY_REASON")
    change("participants", ids[4], "consent_date", None, "MISSING_REQUIRED")
    index, row_id = choose("participants", ids[5])
    enrollment = date.fromisoformat(bundle["participants"].at[index, "enrollment_date"])
    change("participants", ids[5], "consent_date", (enrollment + timedelta(days=1)).isoformat(), "DATE_ORDER")
    # The failing order is attributed to enrollment_date, not the changed consent field.
    labels[-1]["field"] = "enrollment_date"
    change("participants", ids[6], "screening_date", "2026-02-30", "INVALID_DATE")
    change("participants", ids[7], "arm", "unknown", "INVALID_CATEGORY")
    change("baseline", ids[8], "cigarettes_per_day", -3, "RANGE")
    change("baseline", ids[9], "readiness", "high", "INVALID_NUMBER")
    change("baseline", ids[10], "co_ppm", None, "MISSING_REQUIRED")
    index, row_id = choose("baseline", ids[11])
    assessed = date.fromisoformat(bundle["baseline"].at[index, "assessed_at"])
    change("baseline", ids[11], "assessed_at", (assessed - timedelta(days=1)).isoformat(), "DATE_ORDER")
    # Separate complete baseline duplicate, two expected event-key flags.
    index, row_id = choose("baseline", ids[12])
    duplicate = bundle["baseline"].loc[index].copy()
    duplicate["row_id"] = "B-DUPLICATE"
    bundle["baseline"] = pd.concat([bundle["baseline"], duplicate.to_frame().T], ignore_index=True)
    for rid in [row_id, "B-DUPLICATE"]:
        label("baseline", rid, "participant_id", "DUPLICATE_EVENT")
    # Unknown participant: add an independent orphan instead of removing a required baseline.
    orphan = bundle["baseline"].iloc[0].copy()
    orphan["row_id"], orphan["participant_id"] = "B-ORPHAN", "SYN-UNKNOWN"
    bundle["baseline"] = pd.concat([bundle["baseline"], orphan.to_frame().T], ignore_index=True)
    label("baseline", "B-ORPHAN", "participant_id", "PARTICIPANT_ORPHAN")
    # Choose completed visits for all outcome mutations, even if generation varies.
    completed = bundle["visits"][bundle["visits"].status.eq("completed") & bundle["visits"].participant_id.isin(ids)]
    if len(completed) < 9:
        raise ValueError("Need at least 9 completed visits for injection.")
    completed_indices = completed.index[:9].tolist()

    def mutate_visit(position, field, value, rule):
        index = completed_indices[position]
        row_id = bundle["visits"].at[index, "row_id"]
        bundle["visits"].at[index, field] = value
        label("visits", row_id, field, rule)
        return index, row_id

    mutate_visit(0, "cigarettes_7d", 701, "RANGE")
    first = completed_indices[0]
    # Keep the count defect isolated from abstinence consistency rules.
    bundle["visits"].at[first, "abstinent_7d"] = 0
    mutate_visit(1, "completed_at", None, "MISSING_REQUIRED")
    index = completed_indices[2]
    end = date.fromisoformat(bundle["visits"].at[index, "window_end"])
    mutate_visit(2, "completed_at", (end + timedelta(days=1)).isoformat(), "VISIT_OUTSIDE_WINDOW")
    index, _ = mutate_visit(3, "abstinent_7d", 1, "ABSTINENCE_CONFLICT")
    bundle["visits"].at[index, "cigarettes_7d"] = 5
    bundle["visits"].at[index, "co_ppm"] = 2
    index, _ = mutate_visit(4, "co_ppm", 12, "BIOCHEMICAL_REVIEW")
    bundle["visits"].at[index, "abstinent_7d"] = 1
    bundle["visits"].at[index, "cigarettes_7d"] = 0
    index = completed_indices[5]
    end = date.fromisoformat(bundle["visits"].at[index, "window_end"])
    mutate_visit(5, "target_date", (end + timedelta(days=1)).isoformat(), "WINDOW_ORDER")
    mutate_visit(6, "status", "scheduled", "STATUS_CONFLICT")
    mutate_visit(7, "abstinent_7d", 2, "RANGE")
    index, _ = mutate_visit(8, "cigarettes_7d", None, "MISSING_REQUIRED")
    bundle["visits"].at[index, "missing_reason"] = None
    # EMA order, ranges, required content and skipped-content contradictions.
    answered = bundle["ema"][bundle["ema"].response_state.eq("answered")].index[:6].tolist()
    for index, field, value, rule in [
        (answered[0], "urge", 11, "RANGE"),
        (answered[1], "stress", None, "MISSING_REQUIRED"),
        (answered[2], "responded_at", "not-a-timestamp", "INVALID_DATE"),
        (answered[3], "responded_at", (datetime.fromisoformat(bundle["ema"].at[answered[3], "prompted_at"]) - timedelta(minutes=1)).isoformat(), "DATE_ORDER"),
        (answered[4], "uploaded_at", (datetime.fromisoformat(bundle["ema"].at[answered[4], "responded_at"]) - timedelta(seconds=1)).isoformat(), "DATE_ORDER"),
        (answered[5], "uploaded_at", None, "MISSING_REQUIRED"),
    ]:
        bundle["ema"].at[index, field] = value
        label("ema", bundle["ema"].at[index, "row_id"], field, rule)
    skipped = bundle["ema"][bundle["ema"].response_state.eq("declined")].index[0]
    bundle["ema"].at[skipped, "stress"] = 3
    label("ema", bundle["ema"].at[skipped, "row_id"], "stress", "NONRESPONSE_DATA")
    change("contacts", ids[13], "channel", "sms", "INVALID_CATEGORY")
    change("contacts", ids[14], "contacted_at", "2026-01-01", "DATE_ORDER")
    # A missing planned baseline and visit are not the same as item nonresponse.
    index, _ = choose("baseline", ids[15])
    bundle["baseline"] = bundle["baseline"].drop(index).reset_index(drop=True)
    _, row_id = choose("participants", ids[15])
    label("participants", row_id, "participant_id", "MISSING_BASELINE")
    index, _ = choose("visits", ids[16], visit_code="W12")
    bundle["visits"] = bundle["visits"].drop(index).reset_index(drop=True)
    _, row_id = choose("participants", ids[16])
    label("participants", row_id, "participant_id", "MISSING_VISIT")
    # A known withdrawal with an impermissible later visit and missing reason.
    withdrawn = bundle["participants"][bundle["participants"].withdrawal_date.notna()]
    candidates = bundle["visits"].merge(withdrawn[["participant_id", "withdrawal_date"]], on="participant_id")
    candidates = candidates[candidates.status.eq("completed") & candidates.visit_code.eq("W04")]
    if candidates.empty:
        raise ValueError("Need a withdrawn participant with a completed W04 for injection.")
    person = candidates.iloc[0]
    change("participants", person.participant_id, "withdrawal_reason", None, "MISSING_REQUIRED")
    index, row_id = choose("visits", person.participant_id, visit_code="W04")
    bundle["visits"].at[index, "completed_at"] = (date.fromisoformat(person.withdrawal_date) + timedelta(days=1)).isoformat()
    label("visits", row_id, "completed_at", "AFTER_WITHDRAWAL")
    label("visits", row_id, "completed_at", "VISIT_OUTSIDE_WINDOW")
    # An ineligible person's research record is distinct from an unknown ID.
    ineligible = participants[participants.eligible.eq(0)].iloc[0]
    unexpected = bundle["baseline"].iloc[0].copy()
    unexpected["row_id"], unexpected["participant_id"] = "B-NOT-ENROLLED", ineligible.participant_id
    bundle["baseline"] = pd.concat([bundle["baseline"], unexpected.to_frame().T], ignore_index=True)
    label("baseline", "B-NOT-ENROLLED", "participant_id", "NOT_ENROLLED")
    # Exact import duplication is detectable independently of duplicate subject IDs.
    contact = bundle["contacts"].iloc[-1].copy()
    bundle["contacts"] = pd.concat([bundle["contacts"], contact.to_frame().T], ignore_index=True)
    label("contacts", contact.row_id, "row_id", "DUPLICATE_ROW_ID")
    return bundle, pd.DataFrame(labels, columns=["table", "row_id", "field", "rule_id"]).drop_duplicates(ignore_index=True)


def generate_demo(output_dir, seed=42, n=240):
    root = Path(output_dir)
    clean = generate_clean(seed=seed, n=n)
    dirty, truth = inject_errors(clean)
    save_bundle(clean, root / "clean")
    save_bundle(dirty, root / "dirty")
    root.mkdir(parents=True, exist_ok=True)
    truth.to_csv(root / "truth.csv", index=False)
    return {"clean_dir": str(root / "clean"), "dirty_dir": str(root / "dirty"),
            "truth_path": str(root / "truth.csv"), "seed": seed, "as_of": AS_OF.isoformat(),
            "counts": {table: len(frame) for table, frame in clean.items()}, "labelled_defects": len(truth)}
