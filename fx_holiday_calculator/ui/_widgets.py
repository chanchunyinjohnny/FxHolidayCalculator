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
    btn_col.write("")  # spacer so the button aligns below the label, not with it
    btn_col.button("Today", key=f"{key}__today", on_click=_make_today_setter(key))
    return value


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


def render_pair_conventions(pair) -> None:
    """Render the pair-specific conventions section, if any are documented.

    Each entry shows its rule, a short description, and a source link.
    Renders nothing if the pair has no documented conventions.
    """
    if not pair.conventions:
        return
    st.markdown("### Pair conventions")
    for conv in pair.conventions:
        st.markdown(f"**{conv.rule}** — {conv.description}")
        st.caption(f"Source: [{conv.source.doc_title}]({conv.source.url})")
