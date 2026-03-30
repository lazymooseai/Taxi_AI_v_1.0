"""
events_tab.py - Tapahtumat-valilehti
Helsinki Taxi AI

KORJAUKSET (bugfix_9):
  - render_event_card(): st.markdown(unsafe_allow_html=True) EI renderoi
    <a href> -tageja Streamlit 1.55:ssa -- ne sanitoidaan pois.
    Ratkaisu: kortin HTML renderoitaan st.components.v1.html() -kutsulla
    joka suorittaa raaaa HTML:aa iframen sisaella.
    Linkki renderoitaan erikseen st.link_button():lla (Streamlit natiivi).
  - render_category_view() header: st.markdown -> st.components.v1.html()
  - CSS injektoitaan kerran sivun alussa (st.markdown toimii CSS:lle)
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

from src.taxiapp.base_agent import AgentResult


# ==============================================================
# TYYLIVAKIOT
# ==============================================================

COLOR_RED   = "#FF4B4B"
COLOR_GOLD  = "#FFD700"
COLOR_BLUE  = "#00B4D8"
COLOR_BG    = "#0e1117"
COLOR_CARD  = "#1a1d27"
COLOR_TEXT  = "#FAFAFA"
COLOR_MUTED = "#888899"
COLOR_GREEN = "#21C55D"

# CSS injektoidaan kerran render_events_tab():ssa st.markdown():lla.
# Korttien HTML renderoitaan components.html():lla.
EVENTS_TAB_CSS = """
<style>
.evt-card {
    background: #1a1d27;
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 10px;
    border-left: 4px solid #2a2d3d;
}
.evt-card.ending-soon  { border-left-color: #FF4B4B; }
.evt-card.starting-soon{ border-left-color: #FFD700; }
.evt-card.large-event  { border-left-color: #21C55D; }

.evt-title {
    font-size: 1.05rem;
    font-weight: 700;
    line-height: 1.3;
    margin-bottom: 4px;
    color: #FAFAFA;
    font-family: 'Inter', sans-serif;
}
.evt-meta {
    font-size: 0.78rem;
    color: #888899;
    margin-bottom: 8px;
    font-family: 'Inter', sans-serif;
}
.evt-time-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
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
    font-family: 'Inter', sans-serif;
}
.evt-sold-out  { background: #FF4B4B22; color: #FF4B4B; }
.evt-large     { background: #21C55D22; color: #21C55D; }
.evt-soon      { background: #FFD70022; color: #FFD700; }
.evt-ending    { background: #FF4B4B22; color: #FF4B4B; }

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
    font-family: 'Inter', sans-serif;
}
.evt-empty {
    text-align: center;
    padding: 40px 20px;
    color: #888899;
    font-size: 0.9rem;
    font-family: 'Inter', sans-serif;
}
.timeline-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
    flex-shrink: 0;
}
</style>
"""

# HTML-pohja yhdelle kortille -- renderoitaan components.html():lla
# Ei <a>-tageja tassa: linkki tulee st.link_button():lla erikseen
_CARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: transparent; font-family: 'Inter', -apple-system, sans-serif; }}
.evt-card {{
    background: #1a1d27;
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 4px;
    border-left: 4px solid {border_color};
}}
.top-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
}}
.evt-title {{
    font-size: 1.0rem;
    font-weight: 700;
    color: #FAFAFA;
    line-height: 1.3;
    margin-bottom: 4px;
}}
.evt-meta {{
    font-size: 0.75rem;
    color: #888899;
}}
.time-chip {{
    background: {chip_bg};
    color: {chip_color};
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    white-space: nowrap;
    flex-shrink: 0;
}}
.badge-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
    align-items: center;
}}
.badge {{
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
}}
.badge-soldout {{ background: #FF4B4B22; color: #FF4B4B; }}
.badge-large   {{ background: #21C55D22; color: #21C55D; }}
.badge-soon    {{ background: #FFD70022; color: #FFD700; }}
.badge-ending  {{ background: #FF4B4B22; color: #FF4B4B; }}
.badge-cap     {{ background: #2a2d3d; color: #888899; }}
</style>
</head>
<body>
<div class="evt-card">
  <div class="top-row">
    <div style="flex:1;min-width:0">
      <div class="evt-title">{title}</div>
      <div class="evt-meta">{venue_meta}</div>
    </div>
    <div class="time-chip">{chip_label}</div>
  </div>
  <div class="badge-row">{badges_html}</div>
</div>
</body>
</html>
"""


# ==============================================================
# APUFUNKTIOT
# ==============================================================

def _tz_offset() -> int:
    """Helsingin UTC-offset: 2 (EET) tai 3 (EEST)."""
    try:
        from zoneinfo import ZoneInfo
        hki = datetime.now(ZoneInfo("Europe/Helsinki"))
        return int(hki.utcoffset().total_seconds() // 3600)
    except Exception:
        utc_now = datetime.now(timezone.utc)
        year = utc_now.year
        mar_last = datetime(year, 3, 31, tzinfo=timezone.utc)
        while mar_last.weekday() != 6:
            mar_last -= timedelta(days=1)
        dst_start = mar_last.replace(hour=1)
        oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
        while oct_last.weekday() != 6:
            oct_last -= timedelta(days=1)
        dst_end = oct_last.replace(hour=1)
        return 3 if dst_start <= utc_now < dst_end else 2


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
    return _to_local(dt).strftime("%H:%M")


def _format_datetime(dt: Optional[datetime]) -> str:
    if dt is None:
        return "-"
    local = _to_local(dt)
    now_local = _to_local(datetime.now(timezone.utc))
    if local.date() == now_local.date():
        return local.strftime("Tanaan %H:%M")
    elif (local.date() - now_local.date()).days == 1:
        return local.strftime("Huomenna %H:%M")
    return local.strftime("%d.%m. %H:%M")


def _minutes_to(dt: Optional[datetime]) -> Optional[float]:
    if dt is None:
        return None
    return (dt - datetime.now(timezone.utc)).total_seconds() / 60


def _event_state(ev: dict) -> str:
    starts = _parse_dt(ev.get("starts_at"))
    ends   = _parse_dt(ev.get("ends_at"))

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
    """(border_color, chip_bg_hex, state_label)"""
    return {
        "ending":   (COLOR_RED,   COLOR_RED   + "18", "Loppuu pian"),
        "active":   (COLOR_GREEN, COLOR_GREEN + "18", "Kaynnissa"),
        "soon":     (COLOR_GOLD,  COLOR_GOLD  + "18", "Alkaa pian"),
        "upcoming": (COLOR_BLUE,  COLOR_BLUE  + "18", ""),
        "future":   ("#2a2d3d",   "#2a2d3d",          ""),
        "past":     ("#2a2d3d",   "#2a2d3d",          ""),
        "unknown":  ("#2a2d3d",   "#2a2d3d",          ""),
    }.get(state, ("#2a2d3d", "#2a2d3d", ""))


def _capacity_str(cap) -> str:
    try:
        cap = int(cap or 0)
    except (ValueError, TypeError):
        return ""
    if cap <= 0:
        return ""
    if cap >= 1000:
        return f"~{cap // 1000}k hlo"
    return f"~{cap} hlo"


def _escape(s: str) -> str:
    """HTML-escape yksinkertaisille merkeille."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ==============================================================
# TAPAHTUMA-KORTTI
# KORJAUS: components.html() + st.link_button() (ei st.markdown)
# ==============================================================

def render_event_card(ev: dict) -> None:
    """
    Renderoi yksi tapahtumakortti.

    KORJAUS (bugfix_9):
      Streamlit 1.55 sanitoi <a href> -tagit st.markdown():ssa.
      Kortti renderoitaan st.components.v1.html():lla joka nakyttaa
      raan HTML:n iframe-hiekkalaatikossa.
      Linkki renderoitaan erikseen st.link_button():lla.
    """
    title    = str(ev.get("title", "Nimetton"))[:80]
    venue    = str(ev.get("venue", ""))[:50]
    area     = str(ev.get("area", ""))
    capacity = ev.get("capacity", 0)
    sold_out = bool(ev.get("sold_out", False))
    url      = str(ev.get("source_url", ""))
    cat      = str(ev.get("_cat", ""))

    starts = _parse_dt(ev.get("starts_at"))
    ends   = _parse_dt(ev.get("ends_at"))

    state = _event_state(ev)
    border_color, chip_bg, state_lbl = _state_config(state)
    chip_color = border_color if state != "future" else COLOR_MUTED

    # Aikaformaatti
    start_str = _format_datetime(starts)
    end_str   = _format_time(ends) if ends else None
    time_range = start_str + (f" - {end_str}" if end_str else "")

    # Aikachip-teksti
    mins = _minutes_to(ends if state in ("ending", "active") else starts)
    if mins is not None and state in ("ending", "soon") and abs(mins) <= 60:
        mins_abs = abs(int(mins))
        chip_label = (
            f"Loppuu {mins_abs}min"
            if state == "ending"
            else f"Alkaa {mins_abs}min"
        )
    elif state == "active":
        chip_label = "Kaynnissa"
    else:
        chip_label = time_range

    # Kapasiteetti
    cap_str = _capacity_str(capacity)

    # Badges HTML
    badges_html = ""
    if sold_out:
        badges_html += '<span class="badge badge-soldout">Loppuunmyyty</span>'
    if capacity and int(capacity or 0) >= 5000:
        badges_html += f'<span class="badge badge-large">{_escape(cap_str)}</span>'
    elif cap_str:
        badges_html += f'<span class="badge badge-cap">{_escape(cap_str)}</span>'
    if state_lbl:
        cls = "badge-ending" if state == "ending" else "badge-soon"
        badges_html += f'<span class="badge {cls}">{_escape(state_lbl)}</span>'

    # Venue-meta
    venue_parts = []
    if venue:
        venue_parts.append(_escape(venue))
    if area and area != venue:
        venue_parts.append(_escape(area))
    venue_meta = " &nbsp; ".join(venue_parts) if venue_parts else ""

    # Rakenna HTML
    card_html = _CARD_TEMPLATE.format(
        border_color=border_color,
        chip_bg=chip_bg,
        chip_color=chip_color,
        title=_escape(title),
        venue_meta=venue_meta,
        chip_label=_escape(chip_label),
        badges_html=badges_html,
    )

    # Laske kortin korkeus dynaamisesti
    card_height = 110
    if badges_html:
        card_height += 36
    if venue_meta:
        card_height += 20

    # Renderoi kortti iframessa (tukee taydellistae HTML:aa)
    components.html(card_html, height=card_height, scrolling=False)

    # Linkki renderoitaan Streamlit-natiivilla link_button():lla
    if url and url.startswith("http"):
        # Luo lyhyt otsikko URL:sta tai venuestae
        lbl = (venue[:24] if venue else "Avaa") or "Avaa"
        st.link_button(
            "-> " + lbl,
            url,
            use_container_width=True,
        )


# ==============================================================
# KATEGORIANAKKYMA
# ==============================================================

def render_category_view(
    events: list[dict],
    category_label: str,
    emoji: str,
    search_query: str = "",
) -> None:
    """Renderoi yhden kategorian tapahtumalista."""
    # Suodata hakusanalla
    if search_query:
        q = search_query.lower()
        events = [
            ev for ev in events
            if q in ev.get("title", "").lower()
            or q in ev.get("venue", "").lower()
            or q in ev.get("area", "").lower()
        ]

    # Suodata menneet pois
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

    # Header: st.markdown toimii taman yksinkertaisen HTML:n kanssa (ei a-tageja)
    st.markdown(
        f'<div class="cat-header">'
        f'<span>{emoji} {category_label}</span>'
        f'<span style="font-size:0.75rem;color:#888899">{count_str}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not events:
        st.markdown(
            f'<div class="evt-empty">'
            f'<div style="font-size:2rem;margin-bottom:8px">{emoji}</div>'
            f'<div>Ei tulevia tapahtumia</div>'
            f'<div style="font-size:0.75rem;margin-top:4px">'
            f'Tiedot paivittyvat 30 min valein</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    for ev in events:
        render_event_card(ev)


# ==============================================================
# YHTEENVETOTILASTO
# ==============================================================

def render_events_summary(by_cat: dict[str, list[dict]]) -> None:
    """Yhteenvetomittarit valilehden ylaosaan."""
    all_events: list[dict] = []
    for evs in by_cat.values():
        all_events.extend(evs)

    total    = len(all_events)
    ending   = sum(1 for e in all_events if _event_state(e) == "ending")
    active   = sum(1 for e in all_events if _event_state(e) == "active")
    soon     = sum(1 for e in all_events if _event_state(e) == "soon")
    sold_out = sum(1 for e in all_events if e.get("sold_out"))
    large    = sum(1 for e in all_events if int(e.get("capacity") or 0) >= 5000)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Yhteensa", total)
    with c2:
        st.metric(
            "Kaynnissa", active,
            delta=f"+{soon} alkaa pian" if soon else None,
        )
    with c3:
        st.metric("Loppuu pian", ending)
    with c4:
        st.metric("Iso tapahtuma", large)
    with c5:
        st.metric("Loppuunmyyty", sold_out)


# ==============================================================
# DATAKERAYS -- EventsAgent-signaalit -> kategoriasanakirja
# ==============================================================

def _collect_events(
    agent_results: list[AgentResult],
) -> dict[str, list[dict]]:
    """
    Keraa tapahtumat EventsAgent-tuloksesta.
    Palauttaa dict[kategoria -> lista].
    """
    events_result = next(
        (r for r in agent_results if r.agent_name == "EventsAgent"),
        None,
    )
    if not events_result or events_result.status == "error":
        return {"kulttuuri": [], "urheilu": [], "politiikka": []}

    result: dict[str, list[dict]] = {
        "kulttuuri": [],
        "urheilu":   [],
        "politiikka": [],
    }

    for sig in getattr(events_result, "signals", []):
        extra = getattr(sig, "extra", {}) or {}
        sport = extra.get("sport", "")
        cat   = "urheilu" if sport else "kulttuuri"

        reason    = getattr(sig, "reason", "")
        fill_rate = extra.get("fill_rate")

        # Parsitaan title ja venue reason-tekstista
        # Muoto: "Tapahtuman nimi | Venue -- paiva [STATUS]"
        parts = str(reason).split(" | ", 1)
        title = parts[0].strip()[:80] if parts else str(reason)[:80]
        venue = parts[1].strip()[:50] if len(parts) > 1 else ""
        # Poistetaan pvm-osa venueta
        if " -- " in venue:
            venue = venue.split(" -- ")[0].strip()

        ev = {
            "title":      title,
            "venue":      venue or str(extra.get("venue", ""))[:50],
            "area":       getattr(sig, "area", ""),
            "capacity":   extra.get("capacity") or 0,
            "sold_out":   fill_rate is not None and fill_rate >= 1.0,
            "source_url": getattr(sig, "source_url", ""),
            "starts_at":  extra.get("start_date"),
            "ends_at":    None,
            "_cat":       cat,
        }
        result[cat].append(ev)

    return result


def _sort_events(events: list[dict]) -> list[dict]:
    """Jarjesta tapahtumat: ensin kaynnissa/loppuu pian, sitten aikajärjestys."""
    def sort_key(ev):
        state = _event_state(ev)
        starts = _parse_dt(ev.get("starts_at"))
        now    = datetime.now(timezone.utc)

        priority = {
            "ending": 0, "active": 1, "soon": 2,
            "upcoming": 3, "future": 4, "past": 99, "unknown": 50,
        }.get(state, 50)

        secs = (starts - now).total_seconds() if starts else 99999
        return (priority, secs)

    return sorted(events, key=sort_key)


# ==============================================================
# PAAFUNKTIO
# ==============================================================

def render_events_tab(agent_results: list[AgentResult]) -> None:
    """
    Tapahtumat-valilehden paafunktio.
    Kutsutaan app.py:sta kun valilehti = "Tapahtumat".
    """
    # CSS injektoitaan kerran -- st.markdown toimii CSS-tyyleille
    st.markdown(EVENTS_TAB_CSS, unsafe_allow_html=True)

    # == Keraa data ==========================================
    by_cat = _collect_events(agent_results)
    all_events: list[dict] = []
    for cat, evs in by_cat.items():
        for ev in evs:
            ev["_cat"] = cat
        all_events.extend(evs)

    # == Yhteenvetomittarit ==================================
    render_events_summary(by_cat)

    st.markdown(
        "<div style='height:8px'></div>", unsafe_allow_html=True
    )

    # == Hakukenttas ==========================================
    _raw_search = st.text_input(
        "Haku",
        placeholder="Hae tapahtumaa, paikkaa tai aluetta...",
        label_visibility="collapsed",
        key="events_search",
    )
    search = str(_raw_search) if _raw_search and not callable(_raw_search) else ""

    st.markdown(
        "<div style='height:4px'></div>", unsafe_allow_html=True
    )

    # == Kategoriatabs =======================================
    kulttuuri_n  = len([
        e for e in by_cat.get("kulttuuri", [])
        if _event_state(e) != "past"
    ])
    urheilu_n    = len([
        e for e in by_cat.get("urheilu", [])
        if _event_state(e) != "past"
    ])
    politiikka_n = len([
        e for e in by_cat.get("politiikka", [])
        if _event_state(e) != "past"
    ])
    kaikki_n = kulttuuri_n + urheilu_n + politiikka_n

    tab1, tab2, tab3, tab4 = st.tabs([
        f"Kulttuuri ({kulttuuri_n})",
        f"Urheilu ({urheilu_n})",
        f"Politiikka ({politiikka_n})",
        f"Kaikki ({kaikki_n})",
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
        render_category_view(
            list(all_events),
            "Kaikki tapahtumat",
            "",
            search,
        )

    # == Paivitysajankohta ===================================
    events_result = next(
        (r for r in agent_results if r.agent_name == "EventsAgent"),
        None,
    )
    if events_result and events_result.fetched_at:
        try:
            local = _to_local(events_result.fetched_at)
            errors = events_result.raw_data.get("errors", [])
            status_color = COLOR_MUTED if not errors else COLOR_RED
            status_txt = f"Paivitetty {local.strftime('%H:%M')}"
            if errors:
                status_txt += f"   {len(errors)} virhetta"
            st.markdown(
                f'<div style="font-size:0.72rem;color:{status_color};'
                f'margin-top:16px;text-align:right">'
                f'{status_txt}</div>',
                unsafe_allow_html=True,
            )
        except Exception:
            pass
