"""Small Streamlit widget helpers shared across product sub-tabs."""

from __future__ import annotations

from datetime import date

import streamlit as st

REF_CURRENCY_HELP = (
    "Additional currency whose holiday calendar is consulted for settlement "
    "of this pair (per market convention). Only meaningful when neither "
    "leg of the pair is the reference currency."
)


def _make_today_setter(key: str):
    def _setter():
        st.session_state[key] = date.today()

    return _setter


def date_input_with_today(container, label: str, key: str, *, default: date | None = None) -> date:
    """Render a date_input with a 'Today' shortcut button beside it.

    Clicking Today resets the widget value to today's date via an on_click
    callback (which fires before the next rerun, so the widget picks up the
    new session_state value cleanly).
    """
    if default is None:
        default = date.today()
    input_col, btn_col = container.columns([3, 1])
    value = input_col.date_input(label, value=default, key=key)
    # Streamlit 1.30: an empty `write("")` collapses to ~0px, so the button
    # ends up next to the label. A non-breaking space inside a sized markdown
    # reserves a label-row's worth of height so the button lines up with the
    # input box on the same row.
    btn_col.markdown("<div style='height: 1.85em'>&nbsp;</div>", unsafe_allow_html=True)
    btn_col.button("Today", key=f"{key}__today", on_click=_make_today_setter(key))
    return value


def days_caption(target: date, anchor: date, *, anchor_label: str = "T") -> str:
    """Return a short ` — T+N days` suffix for inline date display.

    Counts calendar days from ``anchor`` to ``target``. Returns an empty
    string when the two dates coincide (no useful information to add).
    """
    delta = (target - anchor).days
    if delta == 0:
        return ""
    sign = "+" if delta > 0 else "−"
    plural = "day" if abs(delta) == 1 else "days"
    return f" — {anchor_label}{sign}{abs(delta)} calendar {plural}"


def render_calendar_coverage(
    items: list[tuple[str, date, date]],
    *,
    trade_date: date | None = None,
    target_date: date | None = None,
) -> None:
    """Render a coverage block summarising the validity window of every
    calendar that will participate in the calculation.

    ``items`` is an ordered list of ``(label, valid_from, valid_until)``
    tuples. ``label`` is free-form (e.g. ``"USD RTGS (Federal Reserve)"`` or
    ``"CME (Exchange)"``). The block shows each calendar's window plus the
    effective intersected window — outside that intersection at least one
    lookup will raise :class:`CalendarRangeError`.

    The block is shown as an ``st.info`` by default and escalates to
    ``st.warning`` when any of the following hold:
      - the calendars do not overlap at all
      - ``trade_date`` or ``target_date`` falls outside the effective window
      - less than 90 days of coverage remain from today
    """
    if not items:
        return

    eff_from = max(vf for _, vf, _ in items)
    eff_until = min(vu for _, _, vu in items)
    today = date.today()

    per_cal_lines = [
        f"- **{label}**: {vf.isoformat()} → {vu.isoformat()}" for label, vf, vu in items
    ]

    reasons: list[str] = []
    if eff_until < eff_from:
        reasons.append(
            f"Calendars do not overlap — latest start {eff_from.isoformat()} "
            f"is after earliest end {eff_until.isoformat()}. No usable window."
        )
    else:
        for d, label_d in ((trade_date, "Trade date"), (target_date, "Target date")):
            if d is None:
                continue
            if d < eff_from or d > eff_until:
                reasons.append(
                    f"{label_d} {d.isoformat()} is outside the effective coverage "
                    f"({eff_from.isoformat()} → {eff_until.isoformat()}). "
                    "The calculation will fail with a CalendarRangeError; "
                    "refresh the calendar data via the sidebar."
                )
        days_left = (eff_until - today).days
        if not reasons and 0 <= days_left < 90:
            reasons.append(
                f"Only {days_left} day(s) of coverage remain after today "
                f"({eff_until.isoformat()}). Forward / long-tenor calculations "
                "are likely to land outside the window — refresh via the sidebar."
            )
        elif not reasons and days_left < 0:
            reasons.append(
                f"All bundled coverage ended {(-days_left)} day(s) ago "
                f"({eff_until.isoformat()}). Refresh the calendar data via "
                "the sidebar before relying on any dates."
            )

    if eff_until >= eff_from:
        effective_line = (
            f"\n\n**Effective window (intersection):** "
            f"{eff_from.isoformat()} → {eff_until.isoformat()}"
        )
    else:
        effective_line = "\n\n**Effective window:** (none — calendars do not overlap)"

    body = "**Holiday-data coverage**\n\n" + "\n".join(per_cal_lines) + effective_line
    if reasons:
        body += "\n\n" + "\n".join(f"- {r}" for r in reasons)
        st.warning(body)
    else:
        st.info(body)


def render_reasoning(steps: list[str]) -> None:
    """Render an engine-emitted plain-English reasoning summary.

    Each entry is a self-contained markdown bullet that explains one step of
    the date derivation — anchor used, rule applied, raw vs adjusted, etc.
    Renders nothing if the list is empty.
    """
    if not steps:
        return
    st.markdown("### Reasoning")
    for s in steps:
        st.markdown(f"- {s}")


def render_trace(steps, label: str) -> None:
    """Render an adjustment trace expander.

    Each step shows the candidate date, weekday, per-calendar status with
    holiday names, and the engine's decision (accepted / reject_holiday /
    reject_weekend / rolled_eom). Source citations appear as captions when
    the underlying holiday entry carries provenance.
    """
    if not steps:
        st.write(f"_{label}: no adjustment steps_")
        return
    with st.expander(f"{label} — {len(steps)} candidate(s)", expanded=True):
        for s in steps:
            cols = st.columns([1.4, 0.5, 4, 1])
            cols[0].write(s.candidate_date.isoformat())
            cols[1].write(s.weekday)
            cells = []
            for cal_label, status in s.statuses.items():
                if status.is_good:
                    cells.append(f"{cal_label}: ✓")
                else:
                    cells.append(f"{cal_label}: ✘ {status.holiday_name}")
            cols[2].write("  ·  ".join(cells))
            cols[3].write(s.decision)
            for cal_label, status in s.statuses.items():
                if status.source is not None:
                    st.caption(
                        f"{cal_label}: [{status.source.doc_title}]({status.source.url}) · "
                        f"fetched {status.source.fetched_at.isoformat()} · "
                        f"{status.source_origin}"
                    )


def render_reference_status(
    *,
    pair,
    selected_ref: str,
    named_traces: list[tuple[str, list]],
) -> None:
    """Show whether the reference calendar applied for each derived date.

    - ``pair``: the Pair being calculated against
    - ``selected_ref``: the ref-currency the user chose ("none" or a code)
    - ``named_traces``: ordered (label, trace) pairs, e.g.
      [("Spot offset", spot_trace), ("Far leg", far_trace)]

    Renders a small section explaining:
      * which reference currency (if any) is in force
      * for each derived date, whether the ref calendar bound (caused a
        rejection) or merely applied without impact, plus the list of
        ref-currency holidays consulted in the window.
    """
    st.markdown("### Reference calendar")

    leg_ccys = {pair.base, pair.quote}
    pair_default = pair.default_ref_currency

    # Static pair-level attribute: what the convention says for this pair.
    if pair_default is None or pair_default in leg_ccys:
        if pair_default in leg_ccys:
            reason = (
                f"{pair_default} is already one of the pair's legs, so its calendar "
                "is consulted as a leg — there is no separate third-currency check."
            )
        else:
            reason = "No third-currency convention is documented for this pair."
        st.caption(f"**No third-currency rule** — {reason}")
        return

    # Pair has a meaningful default reference currency.
    ref_src = pair.ref_currency_source
    if ref_src is not None:
        st.caption(
            f"**Documented convention:** {pair.base}/{pair.quote} consults "
            f"**{pair_default}**'s calendar as a third-currency check "
            f"([{ref_src.doc_title}]({ref_src.url}))."
        )
    else:
        st.caption(
            f"**Documented convention:** {pair.base}/{pair.quote} consults "
            f"**{pair_default}**'s calendar as a third-currency check."
        )

    if selected_ref == "none":
        st.info(
            f"You opted out — **{pair_default}**'s calendar was not checked for this calculation."
        )
        return

    if selected_ref != pair_default:
        st.warning(
            f"You picked **{selected_ref}** instead of the documented default "
            f"**{pair_default}**."
        )

    # Per-date status: did the ref calendar get checked, and did it move
    # the date? Phrased to read like a quant's pre-trade verification note.
    holidays_in_window: dict[str, str] = {}
    rows: list[tuple[str, str]] = []
    for label, trace in named_traces:
        if not trace:
            continue
        checked = False
        moved = False
        for step in trace:
            if selected_ref in step.statuses:
                checked = True
                status = step.statuses[selected_ref]
                if not status.is_good and step.decision == "reject_holiday":
                    moved = True
                    holidays_in_window[step.candidate_date.isoformat()] = (
                        status.holiday_name or "(unnamed)"
                    )
        if not checked:
            verdict = f"{selected_ref} calendar was not checked"
        elif moved:
            verdict = f"{selected_ref} holiday moved this date"
        else:
            verdict = f"{selected_ref} calendar was checked — no {selected_ref} holidays in window"
        rows.append((label, verdict))

    for label, verdict in rows:
        st.write(f"- **{label}:** {verdict}")

    if holidays_in_window:
        st.caption(
            f"**{selected_ref} holidays that moved a date:** "
            + " · ".join(f"{d} ({n})" for d, n in sorted(holidays_in_window.items()))
        )


def render_liquidity_warnings(traces, calendars: dict) -> None:
    """Surface per-calendar liquidity flags across a set of adjustment traces.

    ``traces`` is an iterable of trace lists (each element a list of
    AdjustmentStep). ``calendars`` is a dict keyed by the leading token of
    the per-step ``cal_label`` (typically a currency code like ``"EUR"`` or
    a venue code) mapping to a calendar object exposing ``.get_holiday``.

    For each step whose per-calendar status carries a non-empty
    ``liquidity`` annotation, the helper emits one bullet listing the
    date, weekday, calendar label, liquidity flag and (when resolvable
    via ``calendars``) the holiday entry name. Duplicates across traces
    are collapsed. Renders nothing when no flags are present.
    """
    if not calendars:
        return
    alerts: list[str] = []
    for trace in traces:
        if not trace:
            continue
        for step in trace:
            for cal_label, status in step.statuses.items():
                if not status.liquidity:
                    continue
                token = cal_label.split(" ")[0]
                cal = calendars.get(token)
                entry_note = ""
                if cal is not None:
                    entry = cal.get_holiday(step.candidate_date)
                    if entry:
                        entry_note = f" — {entry.name}"
                alerts.append(
                    f"{step.candidate_date.isoformat()} ({step.weekday}) "
                    f"{cal_label}: {status.liquidity}{entry_note}"
                )

    if not alerts:
        return

    seen: set[str] = set()
    unique: list[str] = []
    for a in alerts:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    st.warning(
        "Liquidity warning — these dates are flagged as thin/halted trading "
        "even though they don't block the calculation:\n\n" + "\n".join(f"• {a}" for a in unique)
    )


def render_trade_date_weekend_warning(trade_date: date) -> None:
    """Render a pre-click warning if ``trade_date`` is a Saturday or Sunday.

    Calendar coverage may not extend far enough to flag holidays for every
    currency, so we only check weekends here. Most products require a good
    business day on the trade date; landing on a weekend usually means the
    calculation will fail or be rolled.
    """
    wd = trade_date.weekday()
    if wd == 5:
        day_name = "Saturday"
    elif wd == 6:
        day_name = "Sunday"
    else:
        return
    st.warning(
        f"Trade date {trade_date.isoformat()} falls on a {day_name} — most "
        "products require a good business day; calculation may fail or roll."
    )


def render_pair_conventions(pair) -> None:
    """Render the pair-specific conventions section, if any are documented.

    Entries are split into two visual treatments:
    - Engine-enforced conventions (e.g. USD/CAD T+1) render as plain
      informational text.
    - Conventions the engine does NOT enforce (those with a non-null
      ``engine_divergence_note``) render as a warning box so the user is
      aware the displayed dates may diverge from desk booking practice.
    """
    if not pair.conventions:
        return
    st.markdown("### Pair conventions")
    for conv in pair.conventions:
        if conv.engine_divergence_note is not None:
            st.warning(
                f"**{conv.rule}** — {conv.description}\n\n"
                f"**Tool behavior:** {conv.engine_divergence_note}\n\n"
                f"Source: [{conv.source.doc_title}]({conv.source.url})"
            )
        else:
            st.markdown(f"**{conv.rule}** — {conv.description}")
            st.caption(f"Source: [{conv.source.doc_title}]({conv.source.url})")
