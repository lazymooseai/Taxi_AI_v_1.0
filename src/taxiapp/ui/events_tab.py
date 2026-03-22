"""
events_tab.py - Tapahtumat-välilehti
Helsinki Taxi AI

Näyttää tapahtumat neljässä kategoriavälilehdessä:
   Kulttuuri   - konsertit, teatterit, festivaalit
   Urheilu     - jääkiekko, jalkapallo, yleisurheilu
   Politiikka  - eduskunta, valtuusto, mielenosoitukset
   Kaikki      - kaikki tapahtumat aikajärjestyksessä

Jokainen tapahtuma näyttää:
  - Otsikko + venue + alue
  - Alkamisaika (Helsingin aika)
  - Kapasiteetti + loppuunmyyty-status
  - CEO-signaali jos relevantti (loppuu pian / alkaa pian)
  - Linkki lippuihin/tietoihin
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st

from src.taxiapp.base_agent import AgentResult


# ==============================================================
# TYYLIVAKIOT (jaettu dashboard.py:n kanssa)
# ==============================================================

COLOR_RED   = "#FF4B4B"
COLOR_GOLD  = "#FFD700"
COLOR_BLUE  = "#00B4D8"
COLOR_BG    = "#0e1117"
COLOR_CARD  = "#1a1d27"
COLOR_TEXT  = "#FAFAFA"
COLOR_MUTED = "#888899"
COLOR_GREEN = "#21C55D"

EVENTS_TAB_CSS = """
<style>
.evt-card {
    background: #1a1d27;
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 10px;
    border-left: 4px solid #2a2d3d;
    transition: border-color 0.2s;
    position: relative;
}
.evt-card:hover { border-left-color: #00B4D8; }
.evt-card.ending-soon  { border-left-color: #FF4B4B; }
.evt-card.starting-soon{ border-left-color: #FFD700; }
.evt-card.large-event  { border-left-color: #21C55D; }

.evt-title {
    font-size: 1.05rem;
    font-weight: 700;
    line-height: 1.3;
    margin-bottom: 4px;
}
.evt-meta {
    font-size: 0.78rem;
    color: #888899;
    margin-bottom: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
}
.evt-time-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.evt-status-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
    align-items: center;
}
.evt-badge {
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
}
.evt-sold-out  { background: #FF4B4B22; color: #FF4B4B; }
.evt-large     { background: #21C55D22; color: #21C55D; }
.evt-soon      { background: #FFD70022; color: #FFD700; }
.evt-ending    { background: #FF4B4B22; color: #FF4B4B; }
.evt-link {
    font-size: 0.75rem;
    color: #00B4D8;
    text-decoration: none;
    opacity: 0.8;
}
.evt-link:hover { opacity: 1; }

.cat-header {
    font-size: 0.78rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #888899;
    padding: 12px 0 8px;
    border-bottom: 1px solid #2a2d3d;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.evt-empty {
    text-align: center;
    padding: 40px 20px;
    color: #888899;
    font-size: 0.9rem;
}
.timeline-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
    flex-shrink: 0;
}
.search-hint {
    background: #1a1d27;
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 0.8rem;
    color: #888899;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
</style>
"""


# ==============================================================
# APUFUNKTIOT
# ==============================================================

def _tz_offset() -> int:
    return 3 if _time.daylight else 2


def _to_local(dt: datetime) -> datetime:
    return dt + timedelta(hours=_tz_offset())


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(
            s.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _format_time(dt: Optional[datetime]) -> str:
    if dt is None:
        return "-"
    local = _to_local(dt)
    return local.strftime("%H:%M")


def _format_datetime(dt: Optional[datetime]) -> str:
    if dt is None:
        return "-"
    local = _to_local(dt)
    now_local = _to_local(datetime.now(timezone.utc))
    if local.date() == now_local.date():
        return local.strftime("Tänään %H:%M")
    elif (local.date() - now_local.date()).days == 1:
        return local.strftime("Huomenna %H:%M")
    return local.strftime("%d.%m. %H:%M")


def _minutes_to(dt: Optional[datetime]) -> Optional[float]:
    if dt is None:
        return None
    return (dt - datetime.now(timezone.utc)).total_seconds() / 60


def _event_state(ev: dict) -> str:
    """
    Palauta tapahtuman tila:
      'ending'  - loppuu alle 30min
      'active'  - käynnissä
      'soon'    - alkaa alle 30min
      'upcoming'- alkaa 30min-3h
      'future'  - myöhemmin tänään
      'past'    - jo ohitse
    """
    starts = _parse_dt(ev.get("starts_at"))
    ends   = _parse_dt(ev.get("ends_at"))
    now    = datetime.now(timezone.utc)

    if starts is None:
        return "unknown"

    mins_start = _minutes_to(starts)
    mins_end   = _minutes_to(ends) if ends else None

    if mins_end is not None and mins_end < -5:
        return "past"
    if mins_end is not None and 0 <= mins_end <= 30:
        return "ending"
    if mins_start is not None and mins_start < 0 and (mins_end is None or mins_end > 0):
        return "active"
    if mins_start is not None and 0 <= mins_start <= 30:
        return "soon"
    if mins_start is not None and 30 < mins_start <= 180:
        return "upcoming"
    if mins_start is not None and 180 < mins_start <= 1440:
        return "future"
    return "unknown"


def _state_config(state: str) -> tuple[str, str, str]:
    """(css_class, time_chip_color, state_label)"""
    return {
        "ending":   ("ending-soon",   COLOR_RED,  " Loppuu pian"),
        "active":   ("large-event",   COLOR_GREEN," Käynnissä"),
        "soon":     ("starting-soon", COLOR_GOLD, " Alkaa pian"),
        "upcoming": ("",              COLOR_BLUE, ""),
        "future":   ("",              COLOR_MUTED,""),
        "past":     ("",              COLOR_MUTED,""),
        "unknown":  ("",              COLOR_MUTED,""),
    }.get(state, ("", COLOR_MUTED, ""))


def _capacity_str(cap: int) -> str:
    if cap <= 0:
        return ""
    if cap >= 1000:
        return f"~{cap//1000}k hlö"
    return f"~{cap} hlö"


def _collect_events(
    agent_results: list[AgentResult],
) -> dict[str, list[dict]]:
    """
    Kerää tapahtumat EventsAgent-tuloksesta.
    Palauttaa dict[kategoria -> lista].
    """
    events_result = next(
        (r for r in agent_results if r.agent_name == "EventsAgent"),
        None
    )
    if not events_result or events_result.status == "error":
        return {"kulttuuri": [], "urheilu": [], "politiikka": []}

    by_cat = events_result.raw_data.get("by_category", {})
    result = {}
    for cat in ("kulttuuri", "urheilu", "politiikka"):
        evs = by_cat.get(cat, [])
        # Lisää kategoria-avain jokaiseen tapahtumaan
        for ev in evs:
            ev["_cat"] = cat
        result[cat] = evs

    return result


def _sort_events(events: list[dict]) -> list[dict]:
    """Järjestä tapahtumat: ensin käynnissä/loppuu pian, sitten aikajärjestys."""
    def sort_key(ev):
        state = _event_state(ev)
        starts = _parse_dt(ev.get("starts_at"))
        ends   = _parse_dt(ev.get("ends_at"))
        now    = datetime.now(timezone.utc)

        priority = {
            "ending": 0, "active": 1, "soon": 2,
            "upcoming": 3, "future": 4, "past": 99, "unknown": 50,
        }.get(state, 50)

        # Sekundaarinen järjestys: alkamisaika
        if starts:
            secs = (starts - now).total_seconds()
        else:
            secs = 99999
        return (priority, secs)

    return sorted(events, key=sort_key)


# ==============================================================
# TAPAHTUMA-KORTTI
# ==============================================================

def render_event_card(ev: dict) -> None:
    """Renderöi yksi tapahtumakortti."""
    title    = ev.get("title", "Nimetön")[:80]
    venue    = ev.get("venue", "")[:50]
    area     = ev.get("area", "")
    capacity = ev.get("capacity", 0)
    sold_out = ev.get("sold_out", False)
    url      = ev.get("source_url", "#")
    cat      = ev.get("_cat", "")

    starts = _parse_dt(ev.get("starts_at"))
    ends   = _parse_dt(ev.get("ends_at"))

    state                         = _event_state(ev)
    css_class, chip_color, state_lbl = _state_config(state)

    # Aikaformaatti
    start_str = _format_datetime(starts)
    end_str   = _format_time(ends) if ends else None

    time_range = start_str
    if end_str:
        time_range += f" - {end_str}"

    # Kapasiteetti
    cap_str = _capacity_str(capacity)

    # Kategoria-emoji
    cat_icon = {"kulttuuri": "", "urheilu": "", "politiikka": ""}.get(cat, "")

    # Dot-väri
    dot_color = chip_color if state in ("ending", "active", "soon") else "#2a2d3d"

    # Badges
    badges_html = ""
    if sold_out:
        badges_html += '<span class="evt-badge evt-sold-out"> Loppuunmyyty</span>'
    if capacity >= 5000:
        badges_html += f'<span class="evt-badge evt-large"> {cap_str}</span>'
    elif cap_str:
        badges_html += f'<span class="evt-badge" style="background:#2a2d3d22;color:{COLOR_MUTED}">{cap_str}</span>'
    if state_lbl:
        state_css = "evt-ending" if state == "ending" else "evt-soon"
        badges_html += f'<span class="evt-badge {state_css}">{state_lbl}</span>'

    # Aikachip
    mins = _minutes_to(ends if state in ("ending","active") else starts)
    if mins is not None and state in ("ending", "soon") and abs(mins) <= 60:
        mins_abs = abs(int(mins))
        chip_label = (
            f"Loppuu {mins_abs}min"
            if state == "ending"
            else f"Alkaa {mins_abs}min"
        )
    elif state == "active":
        chip_label = " Käynnissä"
    else:
        chip_label = time_range

    link_html = (
        f'<a class="evt-link" href="{url}" target="_blank">-> tiedot</a>'
        if url and url != "#"
        else ""
    )

    st.markdown(f"""
    <div class="evt-card {css_class}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
            <div style="flex:1;min-width:0">
                <div class="evt-title">
                    <span class="timeline-dot"
                          style="background:{dot_color}"></span>
                    {cat_icon} {title}
                </div>
                <div class="evt-meta">
                    <span> {venue}</span>
                    {f'<span> {area}</span>' if area and area != venue else ''}
                </div>
            </div>
            <div style="text-align:right;flex-shrink:0">
                <div class="evt-time-chip"
                     style="background:{chip_color}18;color:{chip_color}">
                     {chip_label}
                </div>
            </div>
        </div>
        <div class="evt-status-row">
            {badges_html}
            {link_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ==============================================================
# KATEGORIANÄKYMÄ
# ==============================================================

def render_category_view(
    events: list[dict],
    category_label: str,
    emoji: str,
    search_query: str = "",
) -> None:
    """Renderöi yhden kategorian tapahtumalista."""
    # Suodata hakusanalla
    if search_query:
        q = search_query.lower()
        events = [
            ev for ev in events
            if q in ev.get("title", "").lower()
            or q in ev.get("venue", "").lower()
            or q in ev.get("area", "").lower()
        ]

    # Suodata menneet pois (paitsi Kaikki-välilehdellä näytetään aktiiviset)
    events = [ev for ev in events if _event_state(ev) != "past"]

    # Lajittele
    events = _sort_events(events)

    # Header
    count_active = sum(
        1 for ev in events
        if _event_state(ev) in ("ending", "active", "soon")
    )
    count_str = f"{len(events)} tapahtumaa"
    if count_active:
        count_str += f"  {count_active} aktiivinen"

    st.markdown(f"""
    <div class="cat-header">
        <span>{emoji} {category_label}</span>
        <span style="font-size:0.75rem;color:#888899">{count_str}</span>
    </div>
    """, unsafe_allow_html=True)

    if not events:
        st.markdown(
            f'<div class="evt-empty">'
            f'<div style="font-size:2rem;margin-bottom:8px">{emoji}</div>'
            f'<div>Ei tulevia tapahtumia</div>'
            f'<div style="font-size:0.75rem;margin-top:4px">Tiedot päivittyvät 30 min välein</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        return

    for ev in events:
        render_event_card(ev)


# ==============================================================
# YHTEENVETOTILASTO
# ==============================================================

def render_events_summary(by_cat: dict[str, list[dict]]) -> None:
    """Yhteenvetomittarit välilehden yläosaan."""
    all_events = []
    for evs in by_cat.values():
        all_events.extend(evs)

    total     = len(all_events)
    ending    = sum(1 for e in all_events if _event_state(e) == "ending")
    active    = sum(1 for e in all_events if _event_state(e) == "active")
    soon      = sum(1 for e in all_events if _event_state(e) == "soon")
    sold_out  = sum(1 for e in all_events if e.get("sold_out"))
    large     = sum(1 for e in all_events if e.get("capacity", 0) >= 5000)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric(" Yhteensä", total)
    with c2:
        st.metric(" Käynnissä", active, delta=f"+{soon} alkaa pian" if soon else None)
    with c3:
        st.metric(" Loppuu pian", ending)
    with c4:
        st.metric(" Iso tapahtuma", large)
    with c5:
        st.metric(" Loppuunmyyty", sold_out)


# ==============================================================
# PÄÄFUNKTIO
# ==============================================================

def render_events_tab(agent_results: list[AgentResult]) -> None:
    """
    Tapahtumat-välilehden pääfunktio.
    Kutsutaan app.py:stä kun välilehti = "Tapahtumat".
    """
    st.markdown(EVENTS_TAB_CSS, unsafe_allow_html=True)

    # == Kerää data ==========================================
    by_cat = _collect_events(agent_results)
    all_events = []
    for cat, evs in by_cat.items():
        for ev in evs:
            ev["_cat"] = cat
        all_events.extend(evs)

    # == Yhteenvetomittarit ==================================
    render_events_summary(by_cat)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # == Hakukenttä ==========================================
    _raw_search = st.text_input(
        "",
        placeholder=" Hae tapahtumaa, paikkaa tai aluetta...",
        label_visibility="collapsed",
        key="events_search",
    )
    search = str(_raw_search) if _raw_search and not callable(_raw_search) else ""

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # == Kategoriatabs =======================================
    kulttuuri_n  = len([e for e in by_cat.get("kulttuuri",[])  if _event_state(e) != "past"])
    urheilu_n    = len([e for e in by_cat.get("urheilu",[])    if _event_state(e) != "past"])
    politiikka_n = len([e for e in by_cat.get("politiikka",[]) if _event_state(e) != "past"])
    kaikki_n     = kulttuuri_n + urheilu_n + politiikka_n

    tab1, tab2, tab3, tab4 = st.tabs([
        f" Kulttuuri ({kulttuuri_n})",
        f" Urheilu ({urheilu_n})",
        f" Politiikka ({politiikka_n})",
        f" Kaikki ({kaikki_n})",
    ])

    with tab1:
        render_category_view(
            list(by_cat.get("kulttuuri", [])),
            "Kulttuuri & viihde",
            "",
            search,
        )

    with tab2:
        render_category_view(
            list(by_cat.get("urheilu", [])),
            "Urheilu",
            "",
            search,
        )

    with tab3:
        render_category_view(
            list(by_cat.get("politiikka", [])),
            "Politiikka & yhteiskunta",
            "",
            search,
        )

    with tab4:
        # Kaikki-välilehdellä näytetään kaikki kategoriat yhdessä
        render_category_view(
            list(all_events),
            "Kaikki tapahtumat",
            "",
            search,
        )

    # == Päivitysajankohta ===================================
    events_result = next(
        (r for r in agent_results if r.agent_name == "EventsAgent"),
        None
    )
    if events_result and events_result.fetched_at:
        local = _to_local(events_result.fetched_at)
        errors = events_result.raw_data.get("errors", [])
        status_color = COLOR_MUTED if not errors else COLOR_RED
        status_txt = (
            f"Päivitetty {local.strftime('%H:%M')}"
            + (f"   {len(errors)} virhettä" if errors else "")
        )
        st.markdown(
            f'<div style="font-size:0.72rem;color:{status_color};'
            f'margin-top:16px;text-align:right">'
            f'{status_txt}</div>',
            unsafe_allow_html=True
        )
