"""
events_tab.py — Tapahtumat-välilehti
Helsinki Taxi AI

Näyttää tapahtumat neljässä kategoriavälilehdessä:
   🎭 Kulttuuri   — konsertit, teatterit, ooppera, festivaalit
   ⚽ Urheilu     — jääkiekko, jalkapallo, yleisurheilu
   📋 Kaikki      — kaikki signaalit aikajärjestyksessä

Korjaus v1.1:
  _collect_events() lukee nyt suoraan EventsAgentin Signal-listasta.
  Vanha versio luki raw_data["by_category"]-rakennetta jota EventsAgent
  ei koskaan tuottanut → koko välilehti oli tyhjä.

  Signal-kenttäkartta → event-dict:
    Signal.area        → event["area"] + event["venue"]
    Signal.reason      → event["title"] (jäsennetty)
    Signal.expires_at  → event["starts_at"] (approx: expires - 30min)
    Signal.source_url  → event["source_url"]
    Signal.urgency     → event["capacity"] (approx), event["sold_out"]
"""

from __future__ import annotations

import re
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st

from src.taxiapp.base_agent import AgentResult, Signal


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
.evt-sold-out { background: #FF4B4B22; color: #FF4B4B; }
.evt-large    { background: #21C55D22; color: #21C55D; }
.evt-soon     { background: #FFD70022; color: #FFD700; }
.evt-ending   { background: #FF4B4B22; color: #FF4B4B; }
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
# SIGNAALIN MUUNTAMINEN TAPAHTUMA-DICTIKSI
# ==============================================================

# Urheilu-avainsanat reason-tekstissä tai lähteen nimessä
_SPORTS_KEYWORDS: frozenset[str] = frozenset({
    "⚽", "jääkiekko", "jalkapallo", "hifk", "jokerit", "kiekko",
    "veikkausliiga", "nordis", "nokia arena", "bolt arena", "metro areena",
    "liiga", "mestis", "ottelut", "ottelu", "urheilu",
})

# Kulttuuri-avainsanat
_CULTURE_KEYWORDS: frozenset[str] = frozenset({
    "🎭", "🎵", "konsertti", "teatteri", "ooppera", "baletti", "näytelmä",
    "musiikki", "festivaali", "tanssi", "elokuva", "galleria",
    "finlandia", "musiikkitalo", "tavastia", "kaupunginteatteri",
    "kansallisteatteri", "kansallisooppera",
})

# Area → venue-nimi
_AREA_VENUE: dict[str, str] = {
    "Messukeskus":    "Messukeskus",
    "Olympiastadion": "Olympiastadion",
    "Pasila":         "Pasila (Nordis / Messukeskus)",
    "Kamppi":         "Kamppi",
    "Rautatieasema":  "Helsingin keskusta",
    "Kallio":         "Kallio",
    "Kauppatori":     "Kauppatori",
    "Eteläsatama":    "Eteläsatama",
}


def _categorize(signal: Signal) -> str:
    """
    Luokittele signaali kategoriaan reason-tekstin ja alueen perusteella.

    Returns:
        "urheilu" | "kulttuuri"
    """
    text = (signal.reason or "").lower()
    area = (signal.area or "").lower()

    # Urheilu ensin — selkeämmät tunnisteet
    if any(kw in text or kw in area for kw in _SPORTS_KEYWORDS):
        return "urheilu"

    # Kulttuuri
    if any(kw in text for kw in _CULTURE_KEYWORDS):
        return "kulttuuri"

    # Alue-pohjainen päättely
    if signal.area in ("Olympiastadion", "Pasila"):
        return "urheilu"

    return "kulttuuri"  # Oletus: kulttuuri


def _parse_reason(reason: str) -> tuple[str, str, Optional[int], bool]:
    """
    Jäsennä Signal.reason → (title, venue, capacity, sold_out).

    Tuetut formaatit (events.py tuottama):
      "🎭 Venue — DD.MM HH:MM (15000 katsojaa): EventName"
      "🎭 Venue — DD.MM HH:MM [LOPPUUNMYYTY]: EventName"
      "🎭 Venue — DD.MM HH:MM [Viimeiset liput]: EventName"
      "⚽ SportName — VenueName (13500 paikkaa)"
      "📅 Venue — tarkista tapahtumakalenteri"

    Returns:
        (title, venue, capacity_or_None, is_sold_out)
    """
    if not reason:
        return "Tapahtuma", "Tuntematon", None, False

    # Poista emoji-prefix
    clean = re.sub(r"^[\U00010000-\U0010ffff\u2600-\u27ff\ufe00-\ufe0f🎭⚽📅🎵]+\s*", "", reason).strip()

    sold_out = "[LOPPUUNMYYTY]" in reason or "SoldOut" in reason

    # Kapasiteetti: "(15000 katsojaa)" tai "(13500 paikkaa)"
    cap_match = re.search(r"\((\d[\d\s]*)\s*(?:katsojaa|paikkaa|hlö)\)", clean)
    capacity: Optional[int] = None
    if cap_match:
        try:
            capacity = int(cap_match.group(1).replace(" ", ""))
        except ValueError:
            pass

    # Jaa venue ja otsikko " — " -erottimella
    parts = clean.split(" — ", 1)
    venue = parts[0].strip()[:60]

    if len(parts) < 2:
        # Ei erotinta → koko teksti on otsikko
        return clean[:80], venue, capacity, sold_out

    rest = parts[1].strip()

    # Otsikko on ":" jälkeen (jos on)
    if ": " in rest:
        title_part = rest.split(": ", 1)[1].strip()[:80]
    else:
        # Poista päivämäärä- ja kapasiteettiosat
        title_part = re.sub(
            r"\d{1,2}\.\d{1,2}(?:\s+\d{2}:\d{2})?"   # DD.MM HH:MM
            r"|\[.*?\]"                                  # [LOPPUUNMYYTY]
            r"|\(.*?\)",                                 # (kapasiteetti)
            "",
            rest,
        ).strip()[:80]

    title = title_part or venue
    return title, venue, capacity, sold_out


def _extract_start_time(signal: Signal, reason: str) -> Optional[str]:
    """
    Yritä johtaa alkamisaika Signal-datasta.

    Strategia 1: Jäsennä "DD.MM HH:MM" reason-tekstistä.
    Strategia 2: expires_at - 30min (events.py asettaa expires = start + 30min).

    Returns:
        ISO 8601 -merkkijono tai None
    """
    # Strategia 1: Jäsennä päivämäärä reason-tekstistä
    date_match = re.search(
        r"(\d{1,2})\.(\d{1,2})(?:\s+(\d{2}):(\d{2}))?",
        reason or "",
    )
    if date_match:
        try:
            day   = int(date_match.group(1))
            month = int(date_match.group(2))
            hour  = int(date_match.group(3)) if date_match.group(3) else 0
            minute = int(date_match.group(4)) if date_match.group(4) else 0
            now   = datetime.now(timezone.utc)
            year  = now.year
            # Jos kuukausi on jo mennyt, käytä ensi vuotta
            if month < now.month or (month == now.month and day < now.day):
                year += 1
            dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            # Muunna Helsingin aikavyöhykkeeltä UTC:ksi (EEST = UTC+3)
            offset = 3 if _time.daylight else 2
            dt_utc = dt - timedelta(hours=offset)
            return dt_utc.isoformat()
        except (ValueError, TypeError):
            pass

    # Strategia 2: expires_at - 30 minuuttia
    if signal.expires_at:
        try:
            start_dt = signal.expires_at - timedelta(minutes=30)
            return start_dt.isoformat()
        except Exception:
            pass

    return None


def _signal_to_event_dict(signal: Signal, category: str) -> dict:
    """
    Muunna Signal-olio events_tab:n render_event_card()-funktion
    odottamaksi dict-muodoksi.

    Returns:
        dict jossa avaimet: title, venue, area, capacity, sold_out,
              source_url, starts_at, ends_at, _cat, _urgency
    """
    title, venue, capacity, sold_out = _parse_reason(signal.reason or "")

    # Venue: käytä ensin AREA_VENUE-mappingia, sitten jäsennettyä venue-nimeä
    display_venue = _AREA_VENUE.get(signal.area, venue or signal.area or "?")

    # Lippustatuksen rikastaminen urgency-arvosta
    if signal.urgency >= 8:
        sold_out = True
    elif signal.urgency >= 7 and not sold_out:
        sold_out = False  # Lähes loppuunmyyty mutta ei vielä

    starts_at = _extract_start_time(signal, signal.reason or "")

    # ends_at: tapahtuma loppuu noin 2h alun jälkeen (approksimaatio)
    ends_at: Optional[str] = None
    if starts_at:
        try:
            start_dt = datetime.fromisoformat(starts_at)
            ends_at  = (start_dt + timedelta(hours=2)).isoformat()
        except (ValueError, TypeError):
            pass

    return {
        "title":      title or "Tapahtuma",
        "venue":      display_venue,
        "area":       signal.area or "",
        "capacity":   capacity or 0,
        "sold_out":   sold_out,
        "source_url": signal.source_url or "#",
        "starts_at":  starts_at,
        "ends_at":    ends_at,
        "_cat":       category,
        "_urgency":   signal.urgency,
        "_score":     signal.score_delta,
    }


# ==============================================================
# PÄÄKERÄÄJÄ — lukee suoraan signals-listasta
# ==============================================================

def _collect_events(
    agent_results: list[AgentResult],
) -> dict[str, list[dict]]:
    """
    Kerää tapahtumat EventsAgentin Signal-listasta.

    Korjaus: Vanha versio luki raw_data["by_category"]-rakennetta
    jota EventsAgent ei koskaan tuottanut. Tämä versio lukee
    suoraan signals-listasta ja luokittelee signaalit itse.

    Returns:
        {"kulttuuri": [...], "urheilu": [...]}
        Jokainen alkio on render_event_card()-yhteensopiva dict.
    """
    result: dict[str, list[dict]] = {
        "kulttuuri":  [],
        "urheilu":    [],
    }

    # Etsi EventsAgent
    events_result = next(
        (r for r in (agent_results or []) if r.agent_name == "EventsAgent"),
        None,
    )

    if not events_result:
        return result

    # Salli myös "cached"-tila — välimuistista palautettu data on käyttökelpoista
    if events_result.status not in ("ok", "cached"):
        return result

    # Muunna jokainen signaali event-dictiksi
    for signal in events_result.valid_signals:
        try:
            category   = _categorize(signal)
            event_dict = _signal_to_event_dict(signal, category)
            result[category].append(event_dict)
        except Exception:
            # Yhden signaalin jäsennysvirhe ei kaada muita
            continue

    # Järjestä kumpikin kategoria urgency-laskevaan järjestykseen
    for cat in result:
        result[cat].sort(key=lambda e: e.get("_urgency", 0), reverse=True)

    return result


# ==============================================================
# APUFUNKTIOT — aikakäsittely
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
    return _to_local(dt).strftime("%H:%M")


def _format_datetime(dt: Optional[datetime]) -> str:
    if dt is None:
        return "-"
    local     = _to_local(dt)
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
      'ending'  — loppuu alle 30min
      'active'  — käynnissä
      'soon'    — alkaa alle 30min
      'upcoming'— alkaa 30min–3h
      'future'  — myöhemmin tänään
      'past'    — jo ohitse
    """
    starts     = _parse_dt(ev.get("starts_at"))
    ends       = _parse_dt(ev.get("ends_at"))

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
    """(css_class, chip_color, state_label)"""
    return {
        "ending":   ("ending-soon",    COLOR_RED,   "⏰ Loppuu pian"),
        "active":   ("large-event",    COLOR_GREEN, "🟢 Käynnissä"),
        "soon":     ("starting-soon",  COLOR_GOLD,  "⚡ Alkaa pian"),
        "upcoming": ("",               COLOR_BLUE,  ""),
        "future":   ("",               COLOR_MUTED, ""),
        "past":     ("",               COLOR_MUTED, ""),
        "unknown":  ("",               COLOR_MUTED, ""),
    }.get(state, ("", COLOR_MUTED, ""))


def _capacity_str(cap: int) -> str:
    if cap <= 0:
        return ""
    if cap >= 1000:
        return f"~{cap // 1000}k hlö"
    return f"~{cap} hlö"


# ==============================================================
# TAPAHTUMA-KORTTI
# ==============================================================

def render_event_card(ev: dict) -> None:
    """Renderöi yksi tapahtumakortti."""
    title    = str(ev.get("title",    "Nimetön"))[:80]
    venue    = str(ev.get("venue",    ""))[:50]
    area     = str(ev.get("area",     ""))
    capacity = int(ev.get("capacity", 0) or 0)
    sold_out = bool(ev.get("sold_out", False))
    url      = str(ev.get("source_url", "#"))
    cat      = str(ev.get("_cat",      ""))

    starts = _parse_dt(ev.get("starts_at"))
    ends   = _parse_dt(ev.get("ends_at"))

    state                            = _event_state(ev)
    css_class, chip_color, state_lbl = _state_config(state)

    start_str  = _format_datetime(starts)
    end_str    = _format_time(ends) if ends else None
    time_range = start_str + (f" – {end_str}" if end_str else "")

    cap_str    = _capacity_str(capacity)
    cat_icon   = {"kulttuuri": "🎭", "urheilu": "⚽"}.get(cat, "📅")
    dot_color  = chip_color if state in ("ending", "active", "soon") else "#2a2d3d"

    # Badges
    badges_html = ""
    if sold_out:
        badges_html += '<span class="evt-badge evt-sold-out">🔴 Loppuunmyyty</span>'
    if capacity >= 5000:
        badges_html += f'<span class="evt-badge evt-large">🏟 {cap_str}</span>'
    elif cap_str:
        badges_html += (
            f'<span class="evt-badge" style="background:#2a2d3d22;color:{COLOR_MUTED}">'
            f'{cap_str}</span>'
        )
    if state_lbl:
        state_css = "evt-ending" if state == "ending" else "evt-soon"
        badges_html += f'<span class="evt-badge {state_css}">{state_lbl}</span>'

    # Aikachip
    mins = _minutes_to(ends if state in ("ending", "active") else starts)
    if mins is not None and state in ("ending", "soon") and abs(mins) <= 90:
        mins_abs   = abs(int(mins))
        chip_label = (
            f"Loppuu {mins_abs} min"
            if state == "ending"
            else f"Alkaa {mins_abs} min"
        )
    elif state == "active":
        chip_label = "🟢 Käynnissä"
    else:
        chip_label = time_range

    link_html = (
        f'<a class="evt-link" href="{url}" target="_blank">→ avaa</a>'
        if url and url != "#"
        else ""
    )

    # Area näytetään vain jos eri kuin venue
    area_html = (
        f'<span>📍 {area}</span>'
        if area and area != venue
        else ""
    )

    st.markdown(f"""
    <div class="evt-card {css_class}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
            <div style="flex:1;min-width:0">
                <div class="evt-title">
                    <span class="timeline-dot" style="background:{dot_color}"></span>
                    {cat_icon} {title}
                </div>
                <div class="evt-meta">
                    <span>🏛 {venue}</span>
                    {area_html}
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

def _sort_events(events: list[dict]) -> list[dict]:
    """Järjestä: ensin aktiiviset/loppuvat, sitten aikajärjestys."""
    priority_map = {
        "ending": 0, "active": 1, "soon": 2,
        "upcoming": 3, "future": 4, "past": 99, "unknown": 50,
    }
    now = datetime.now(timezone.utc)

    def sort_key(ev):
        state    = _event_state(ev)
        priority = priority_map.get(state, 50)
        starts   = _parse_dt(ev.get("starts_at"))
        secs     = (starts - now).total_seconds() if starts else 99999
        return (priority, secs)

    return sorted(events, key=sort_key)


def render_category_view(
    events:         list[dict],
    category_label: str,
    emoji:          str,
    search_query:   str = "",
) -> None:
    """Renderöi yhden kategorian tapahtumalista."""
    if search_query:
        q      = search_query.lower()
        events = [
            ev for ev in events
            if q in ev.get("title", "").lower()
            or q in ev.get("venue", "").lower()
            or q in ev.get("area",  "").lower()
        ]

    # Suodata menneet
    events = [ev for ev in events if _event_state(ev) != "past"]
    events = _sort_events(events)

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
            f'<div style="font-size:0.75rem;margin-top:4px">'
            f'Tiedot päivittyvät 30 min välein</div>'
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
    """Yhteenvetomittarit välilehden yläosaan."""
    all_events = [ev for evs in by_cat.values() for ev in evs]

    total    = len(all_events)
    ending   = sum(1 for e in all_events if _event_state(e) == "ending")
    active   = sum(1 for e in all_events if _event_state(e) == "active")
    soon     = sum(1 for e in all_events if _event_state(e) == "soon")
    sold_out = sum(1 for e in all_events if e.get("sold_out"))
    large    = sum(1 for e in all_events if e.get("capacity", 0) >= 5000)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("📅 Yhteensä", total)
    with c2:
        st.metric("🟢 Käynnissä", active, delta=f"+{soon} alkaa pian" if soon else None)
    with c3:
        st.metric("⏰ Loppuu pian", ending)
    with c4:
        st.metric("🏟 Iso tapahtuma", large)
    with c5:
        st.metric("🔴 Loppuunmyyty", sold_out)


# ==============================================================
# PÄÄFUNKTIO
# ==============================================================

def render_events_tab(agent_results: list[AgentResult]) -> None:
    """
    Tapahtumat-välilehden pääfunktio.
    Kutsutaan app.py:stä välilehden ollessa aktiivinen.
    """
    st.markdown(EVENTS_TAB_CSS, unsafe_allow_html=True)

    # Kerää ja luokittele data
    by_cat     = _collect_events(agent_results)
    all_events = [ev for evs in by_cat.values() for ev in evs]
    for cat, evs in by_cat.items():
        for ev in evs:
            ev.setdefault("_cat", cat)

    # Yhteenvetomittarit
    render_events_summary(by_cat)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Hakukenttä
    _raw_search = st.text_input(
        "Haku",
        placeholder="🔍 Hae tapahtumaa, paikkaa tai aluetta...",
        label_visibility="collapsed",
        key="events_search",
    )
    search = str(_raw_search) if _raw_search and not callable(_raw_search) else ""
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # Lasketaan kappaleet ennakkoon tab-otsikkoa varten
    kulttuuri_n = len([
        e for e in by_cat.get("kulttuuri", [])
        if _event_state(e) != "past"
    ])
    urheilu_n = len([
        e for e in by_cat.get("urheilu", [])
        if _event_state(e) != "past"
    ])
    kaikki_n = kulttuuri_n + urheilu_n

    tab1, tab2, tab3 = st.tabs([
        f"🎭 Kulttuuri ({kulttuuri_n})",
        f"⚽ Urheilu ({urheilu_n})",
        f"📋 Kaikki ({kaikki_n})",
    ])

    with tab1:
        render_category_view(
            list(by_cat.get("kulttuuri", [])),
            "Kulttuuri & viihde",
            "🎭",
            search,
        )

    with tab2:
        render_category_view(
            list(by_cat.get("urheilu", [])),
            "Urheilu",
            "⚽",
            search,
        )

    with tab3:
        render_category_view(
            list(all_events),
            "Kaikki tapahtumat",
            "📋",
            search,
        )

    # Päivitysajankohta
    events_result = next(
        (r for r in (agent_results or []) if r.agent_name == "EventsAgent"),
        None,
    )
    if events_result and events_result.fetched_at:
        local      = _to_local(events_result.fetched_at)
        errors     = (events_result.raw_data or {}).get("errors", [])
        stat_color = COLOR_MUTED if not errors else COLOR_RED
        stat_txt   = (
            f"Päivitetty {local.strftime('%H:%M')}"
            + (f"  ⚠️ {len(errors)} virhettä" if errors else "")
        )
        st.markdown(
            f'<div style="font-size:0.72rem;color:{stat_color};'
            f'margin-top:16px;text-align:right">'
            f'{stat_txt}</div>',
            unsafe_allow_html=True,
        )
