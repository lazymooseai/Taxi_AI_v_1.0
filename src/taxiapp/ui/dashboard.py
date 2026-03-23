"""
dashboard.py — Helsinki Taxi AI
Kojelauta-välilehti v2.0

Arkkitehtuuri:
  - Kaikki 3 hotspot-korttia renderöidään yhdeksi HTML-komponentiksi
  - CSS scroll-snap → natiivi swipe mobiilissa ja desktopilla
  - Animoitu sääwidget header-alueessa
  - Dynaaminen sijainti-älykkyys: jokainen kortti tietää etäisyytesi
  - Apple Smart Stack -inspiraatio: kortit elävät tilanteen mukaan
  - Fontit: Barlow Condensed (otsikot) + Jost (teksti) + Share Tech Mono (data)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

logger = logging.getLogger("taxiapp.dashboard")


# ══════════════════════════════════════════════════════════════════════════════
# SIJAINTILOGIIKKA — dynaaminen, toimii joka paikassa
# ══════════════════════════════════════════════════════════════════════════════

def _get_location() -> Optional[tuple[float, float]]:
    """Hae sijainti session_statesta. Tukee molempia location-moduuleja."""
    try:
        from src.taxiapp.location import get_driver_location
        loc = get_driver_location()
        if loc:
            return loc
    except Exception:
        pass
    try:
        lat = st.session_state.get("driver_lat")
        lon = st.session_state.get("driver_lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    except Exception:
        pass
    return None


def _nearest_area_info(location: Optional[tuple[float, float]]) -> dict:
    """
    Laske lähin alue ja etäisyys kaikista AREAS-alueista.
    Palauttaa dict jossa name, distance_km, direction_hint.
    """
    if location is None:
        return {}
    try:
        from src.taxiapp.location import nearest_areas_ranked, get_direction_hint
        ranked = nearest_areas_ranked(location, top_n=3)
        hint   = get_direction_hint()
        if not ranked:
            return {}
        name, km = ranked[0]
        direction_map = {
            "toward_city": "→ keskusta",
            "from_city":   "← lähiöt",
            "stationary":  "⏸ paikallaan",
        }
        return {
            "nearest_name": name,
            "nearest_km":   round(km, 1),
            "direction":    direction_map.get(hint or "", ""),
            "top3":         ranked,
        }
    except Exception:
        return {}


def _area_distance_km(
    location: Optional[tuple[float, float]],
    area_name: str,
) -> Optional[float]:
    """Laske etäisyys tiettyyn alueeseen."""
    if location is None:
        return None
    try:
        from src.taxiapp.location import haversine_km
        from src.taxiapp.areas import AREAS
        area = AREAS.get(area_name)
        if area is None:
            return None
        return round(haversine_km(location[0], location[1], area.lat, area.lon), 1)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SÄÄLOGIIKKA — animaation tyyppi ja data
# ══════════════════════════════════════════════════════════════════════════════

def _extract_weather(agent_results: list) -> dict:
    """
    Pura WeatherAgentin tiedot:
      weather_type: "rain"|"snow"|"thunder"|"wind"|"sun"|"cloud"|"frost"
      description:  "☀️ +15.2C, tuuli 4.0 m/s"
    """
    try:
        for r in (agent_results or []):
            if getattr(r, "agent_name", "") != "WeatherAgent":
                continue
            if not getattr(r, "ok", False):
                continue
            sigs = getattr(r, "signals", [])
            if not sigs:
                continue
            reason = getattr(sigs[0], "reason", "")
            raw    = getattr(r, "raw_data", {}) or {}
            temp   = raw.get("temperature")

            # Päättele tyyppi reason-tekstistä
            r_low = reason.lower()
            if "ukkonen" in r_low or "thunder" in r_low or "⛈" in reason:
                wtype = "thunder"
            elif "lumimyrsky" in r_low or "lumi" in r_low or "❄" in reason or "snow" in r_low:
                wtype = "snow"
            elif "rankkasade" in r_low or "sade" in r_low or "🌧" in reason or "🌦" in reason:
                wtype = "rain"
            elif "myrskytuuli" in r_low or "kova tuuli" in r_low or "🌪" in reason or "💨" in reason:
                wtype = "wind"
            elif "pakkanen" in r_low or "frost" in r_low or "🥶" in reason:
                wtype = "frost"
            elif "pilvi" in r_low or "☁" in reason:
                wtype = "cloud"
            else:
                wtype = "sun"

            # Siisti näyttöteksti
            desc = reason
            # Poista emoji-prefix jos on muodossa "🌧️ RANKKASADE: ..."
            import re
            desc = re.sub(r"^[\U00010000-\U0010ffff\u2600-\u27ff\ufe00-\ufe0f]+\s*", "", desc)
            desc = desc.strip()
            if temp is not None:
                temp_str = f"{temp:+.1f}°C"
            else:
                temp_str = ""

            return {
                "weather_type": wtype,
                "description":  desc[:60],
                "temp":         temp_str,
            }
    except Exception:
        pass
    return {"weather_type": "sun", "description": "", "temp": ""}


# ══════════════════════════════════════════════════════════════════════════════
# HÄIRIÖBANNERI
# ══════════════════════════════════════════════════════════════════════════════

def _extract_disruptions(agent_results: list) -> list[str]:
    """Palauta lista kriittisistä häiriöistä (urgency >= 7)."""
    msgs = []
    try:
        for r in (agent_results or []):
            if getattr(r, "agent_name", "") != "DisruptionAgent":
                continue
            for sig in getattr(r, "signals", []):
                if getattr(sig, "urgency", 0) >= 7:
                    msgs.append(getattr(sig, "reason", "")[:80])
    except Exception:
        pass
    return msgs[:2]


# ══════════════════════════════════════════════════════════════════════════════
# KORTIN DATA-EXTRAKTIO
# ══════════════════════════════════════════════════════════════════════════════

def _card_data(
    hotspot,
    location: Optional[tuple[float, float]],
    idx: int,
) -> dict:
    """
    Muunna Hotspot-olio serialisoitavaksi dict:iksi HTML-renderöintiä varten.
    Rikastetaan sijaintitiedolla.
    """
    area      = getattr(hotspot, "area", "")
    score     = getattr(hotspot, "score", 0.0)
    urgency   = getattr(hotspot, "urgency", 1)
    reasons   = getattr(hotspot, "reasons", [])
    signals   = getattr(hotspot, "signals", [])
    color     = getattr(hotspot, "card_color", ["red","gold","blue"][idx])
    predictive = getattr(hotspot, "predictive", idx == 2)

    # Badge-teksti
    if urgency >= 9:
        badge = "⚡ OVERRIDE"
    elif predictive:
        badge = "🔵 ENNAKOIVA"
    elif urgency >= 7:
        badge = "🔴 KRIITTINEN"
    elif urgency >= 5:
        badge = "🟡 KORKEA"
    else:
        badge = "🟢 NORMAALI"

    # Top-3 syytä — prefer reasons list
    display_reasons = []
    if reasons:
        for r in reasons[:3]:
            display_reasons.append({"text": str(r)[:90], "url": None})
    else:
        for sig in signals[:3]:
            display_reasons.append({
                "text": getattr(sig, "reason", "")[:90],
                "url":  getattr(sig, "source_url", None),
            })

    # Linkit — uniikit URLt signaaleista
    seen_urls: set[str] = set()
    links = []
    for sig in signals:
        url = getattr(sig, "source_url", None)
        if not url or not str(url).startswith("http") or url in seen_urls:
            continue
        seen_urls.add(url)
        reason_text = getattr(sig, "reason", "")[:35] or "Avaa"
        links.append({"label": reason_text, "url": url})
        if len(links) >= 3:
            break

    # Sijainti — etäisyys tähän alueeseen
    dist_km    = _area_distance_km(location, area)
    dist_label = f"📍 {dist_km} km" if dist_km is not None else ""

    # Lähin alue -merkintä
    is_nearest = False
    if location and dist_km is not None and dist_km < 3.0:
        is_nearest = True

    return {
        "area":        area,
        "area_pretty": area.replace("_", " "),
        "score":       round(score, 1),
        "urgency":     urgency,
        "badge":       badge,
        "color":       color,
        "reasons":     display_reasons,
        "links":       links,
        "dist_label":  dist_label,
        "dist_km":     dist_km,
        "is_nearest":  is_nearest,
        "predictive":  predictive,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HTML-RENDERER — koko dashboard yhdeksi HTML-merkkijonoksi
# ══════════════════════════════════════════════════════════════════════════════

def _build_html(
    cards:       list[dict],
    weather:     dict,
    loc_info:    dict,
    disruptions: list[str],
    now_str:     str,
    agent_dots:  list[dict],
) -> str:
    """
    Rakenna koko dashboard HTML-merkkijonona.
    Ei ulkoisia riippuvuuksia — kaikki inline.
    """
    cards_json = json.dumps(cards, ensure_ascii=False)
    wtype      = weather.get("weather_type", "sun")
    wdesc      = weather.get("description", "")
    wtemp      = weather.get("temp", "")

    # Sijainti-header
    nearest_name = loc_info.get("nearest_name", "")
    nearest_km   = loc_info.get("nearest_km", "")
    direction    = loc_info.get("direction", "")
    if nearest_name:
        loc_html = (
            f'<span class="loc-dot">📍</span>'
            f'<span class="loc-name">{nearest_name}</span>'
            f'<span class="loc-dist">{nearest_km} km</span>'
            f'<span class="loc-dir">{direction}</span>'
        )
    else:
        loc_html = '<span class="loc-dot" style="color:#555">⊙ GPS ei aktiivinen</span>'

    # Häiriöbanneri
    if disruptions:
        disrupt_html = "".join(
            f'<div class="disrupt-item">⚠️ {d}</div>'
            for d in disruptions
        )
        disrupt_block = f'<div class="disruption-bar">{disrupt_html}</div>'
    else:
        disrupt_block = ""

    # Agenttipisteet
    dots_html = "".join(
        f'<span class="adot adot-{"ok" if d["ok"] else "err"}" '
        f'title="{d["name"]}: {d["signals"]} signaalia"></span>'
        for d in agent_dots
    )

    # Korttien HTML
    card_divs = ""
    for i, c in enumerate(cards):
        color_cls = f"card-{c['color']}"

        # Syyt
        reasons_html = ""
        for r in c["reasons"]:
            text = r["text"]
            url  = r.get("url")
            if url:
                reasons_html += (
                    f'<a class="reason-link" href="{url}" target="_blank">'
                    f'{text}</a>'
                )
            else:
                reasons_html += f'<span class="reason-item">{text}</span>'

        # Linkkipainikkeet
        btns_html = ""
        for lnk in c["links"][:3]:
            btns_html += (
                f'<a class="card-btn" href="{lnk["url"]}" target="_blank">'
                f'{lnk["label"]}</a>'
            )

        # Lähellä-merkintä
        near_badge = (
            '<span class="near-badge">LÄHELLÄ SINUA</span>'
            if c["is_nearest"] else ""
        )

        dist_html = (
            f'<span class="dist-tag">{c["dist_label"]}</span>'
            if c["dist_label"] else ""
        )

        card_divs += f"""
<div class="card {color_cls}" data-idx="{i}">
  <div class="card-inner">
    <div class="card-top">
      <div class="card-badge-row">
        <span class="badge">{c['badge']}</span>
        {near_badge}
        {dist_html}
      </div>
      <div class="card-area">{c['area_pretty']}</div>
      <div class="card-score">
        Pisteet <span class="score-num">{c['score']}</span>
      </div>
    </div>
    <div class="card-body">
      <div class="reasons">{reasons_html}</div>
    </div>
    <div class="card-footer">
      <div class="card-links">{btns_html}</div>
    </div>
  </div>
</div>"""

    # Dot-indikaattorit
    indicator_dots = "".join(
        f'<span class="idot{"  idot-active" if i == 0 else ""}" data-target="{i}"></span>'
        for i in range(len(cards))
    )

    # Sää-CSS animaatio
    weather_anim_css = _weather_animation_css(wtype)

    return f"""<!DOCTYPE html>
<html lang="fi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=Jost:wght@300;400;500;600&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
/* ── RESET & BASE ───────────────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:       #080a0f;
  --bg2:      #0d1018;
  --bg3:      #141720;
  --border:   #1e2235;
  --text:     #e8eaf0;
  --text2:    #8b90a8;
  --text3:    #555a70;
  --red:      #FF4040;
  --red-dim:  rgba(255,64,64,0.12);
  --gold:     #FFB800;
  --gold-dim: rgba(255,184,0,0.12);
  --blue:     #00C8FF;
  --blue-dim: rgba(0,200,255,0.12);
  --green:    #00E676;
  --radius:   18px;
}}

html, body {{
  background: var(--bg);
  color: var(--text);
  font-family: 'Jost', sans-serif;
  font-size: 16px;
  overscroll-behavior: none;
  -webkit-font-smoothing: antialiased;
}}

/* ── HEADER ─────────────────────────────────────────────────── */
.header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 14px 16px 10px;
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  position: relative;
  overflow: hidden;
}}

.header-left {{
  display: flex;
  flex-direction: column;
  gap: 2px;
}}

.clock {{
  font-family: 'Share Tech Mono', monospace;
  font-size: 2.8rem;
  font-weight: 400;
  color: var(--text);
  letter-spacing: 0.02em;
  line-height: 1;
}}

.location-row {{
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  flex-wrap: wrap;
}}

.loc-dot {{ font-size: 0.85rem; }}
.loc-name {{ font-size: 0.9rem; font-weight: 600; color: var(--blue); }}
.loc-dist {{ font-size: 0.78rem; color: var(--text2); }}
.loc-dir  {{ font-size: 0.75rem; color: var(--text3); }}

.header-right {{
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
}}

.weather-widget {{
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}}

.weather-icon {{
  font-size: 2.2rem;
  line-height: 1;
}}

.weather-temp {{
  font-family: 'Share Tech Mono', monospace;
  font-size: 1.4rem;
  color: var(--text);
  font-weight: 400;
}}

.weather-desc {{
  font-size: 0.72rem;
  color: var(--text2);
  max-width: 160px;
  text-align: right;
}}

/* ── HÄIRIÖBANNERI ──────────────────────────────────────────── */
.disruption-bar {{
  background: linear-gradient(90deg, #1a0505, #120303);
  border-bottom: 1px solid rgba(255,64,64,0.4);
  padding: 8px 16px;
}}

.disrupt-item {{
  font-size: 0.83rem;
  color: #FF7070;
  padding: 2px 0;
  font-family: 'Jost', sans-serif;
  font-weight: 500;
}}

/* ── SWIPE STACK ────────────────────────────────────────────── */
.stack-wrapper {{
  position: relative;
  padding: 12px 0 0;
}}

.card-stack {{
  display: flex;
  overflow-x: scroll;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  gap: 0;
}}

.card-stack::-webkit-scrollbar {{ display: none; }}

/* ── KORTTI ─────────────────────────────────────────────────── */
.card {{
  min-width: 100%;
  max-width: 100%;
  scroll-snap-align: start;
  padding: 0 14px 8px;
  flex-shrink: 0;
}}

.card-inner {{
  border-radius: var(--radius);
  padding: 20px 20px 16px;
  min-height: 340px;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border);
  transition: transform 0.2s ease;
}}

/* Värivariantit */
.card-red  .card-inner {{
  background: linear-gradient(160deg, #150808 0%, #0d0404 60%, #0a0606 100%);
  border-color: rgba(255,64,64,0.25);
}}
.card-gold .card-inner {{
  background: linear-gradient(160deg, #141005 0%, #0c0a04 60%, #090806 100%);
  border-color: rgba(255,184,0,0.25);
}}
.card-blue .card-inner {{
  background: linear-gradient(160deg, #050d14 0%, #040b10 60%, #030810 100%);
  border-color: rgba(0,200,255,0.25);
}}

/* Väriaksentin viiva vasemmalla */
.card-inner::before {{
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  border-radius: var(--radius) 0 0 var(--radius);
}}
.card-red  .card-inner::before {{ background: var(--red); }}
.card-gold .card-inner::before {{ background: var(--gold); }}
.card-blue .card-inner::before {{ background: var(--blue); }}

/* Hehkuefekti kortille */
.card-red  .card-inner::after {{
  content: '';
  position: absolute;
  top: -60px; right: -60px;
  width: 180px; height: 180px;
  background: radial-gradient(circle, rgba(255,64,64,0.08) 0%, transparent 70%);
  pointer-events: none;
}}
.card-gold .card-inner::after {{
  content: '';
  position: absolute;
  top: -60px; right: -60px;
  width: 180px; height: 180px;
  background: radial-gradient(circle, rgba(255,184,0,0.07) 0%, transparent 70%);
  pointer-events: none;
}}
.card-blue .card-inner::after {{
  content: '';
  position: absolute;
  top: -60px; right: -60px;
  width: 180px; height: 180px;
  background: radial-gradient(circle, rgba(0,200,255,0.07) 0%, transparent 70%);
  pointer-events: none;
}}

/* ── KORTIN SISÄLTÖ ─────────────────────────────────────────── */
.card-top {{ margin-bottom: 14px; }}

.card-badge-row {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}}

.badge {{
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: 20px;
}}

.card-red  .badge {{ background: var(--red-dim);  color: var(--red);  border: 1px solid rgba(255,64,64,0.3); }}
.card-gold .badge {{ background: var(--gold-dim); color: var(--gold); border: 1px solid rgba(255,184,0,0.3); }}
.card-blue .badge {{ background: var(--blue-dim); color: var(--blue); border: 1px solid rgba(0,200,255,0.3); }}

.near-badge {{
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 2px 8px;
  border-radius: 20px;
  background: rgba(0,230,118,0.15);
  color: var(--green);
  border: 1px solid rgba(0,230,118,0.3);
  text-transform: uppercase;
}}

.dist-tag {{
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.75rem;
  color: var(--text2);
  padding: 2px 8px;
  background: rgba(255,255,255,0.04);
  border-radius: 12px;
  border: 1px solid var(--border);
}}

.card-area {{
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 2.6rem;
  font-weight: 800;
  line-height: 1.0;
  color: var(--text);
  letter-spacing: -0.01em;
  margin-bottom: 4px;
}}

.card-score {{
  font-family: 'Jost', sans-serif;
  font-size: 0.8rem;
  color: var(--text3);
  font-weight: 400;
}}

.score-num {{
  font-family: 'Share Tech Mono', monospace;
  color: var(--text2);
}}

/* ── SYYT ───────────────────────────────────────────────────── */
.card-body {{ flex: 1; }}

.reasons {{
  display: flex;
  flex-direction: column;
  gap: 6px;
}}

.reason-item, .reason-link {{
  display: block;
  font-size: 0.92rem;
  color: #c8cadc;
  line-height: 1.4;
  font-weight: 400;
  padding: 6px 10px;
  background: rgba(255,255,255,0.03);
  border-radius: 8px;
  border-left: 2px solid var(--border);
  text-decoration: none;
  transition: background 0.15s;
}}

.reason-link:hover {{
  background: rgba(255,255,255,0.07);
  color: var(--blue);
  border-left-color: var(--blue);
}}

.card-red  .reason-item  {{ border-left-color: rgba(255,64,64,0.3); }}
.card-gold .reason-item  {{ border-left-color: rgba(255,184,0,0.3); }}
.card-blue .reason-item  {{ border-left-color: rgba(0,200,255,0.3); }}
.card-red  .reason-link  {{ border-left-color: rgba(255,64,64,0.4); }}
.card-gold .reason-link  {{ border-left-color: rgba(255,184,0,0.4); }}
.card-blue .reason-link  {{ border-left-color: rgba(0,200,255,0.4); }}

/* ── LINKIT ─────────────────────────────────────────────────── */
.card-footer {{ margin-top: 14px; }}

.card-links {{
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}}

.card-btn {{
  font-family: 'Jost', sans-serif;
  font-size: 0.78rem;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: 10px;
  text-decoration: none;
  background: rgba(255,255,255,0.05);
  color: var(--text2);
  border: 1px solid var(--border);
  transition: all 0.15s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}}

.card-btn:hover {{
  background: rgba(255,255,255,0.1);
  color: var(--text);
  border-color: rgba(255,255,255,0.2);
}}

.card-red  .card-btn:hover {{ border-color: var(--red);  color: var(--red); }}
.card-gold .card-btn:hover {{ border-color: var(--gold); color: var(--gold); }}
.card-blue .card-btn:hover {{ border-color: var(--blue); color: var(--blue); }}

/* ── SWIPE INDIKAATTORIT ────────────────────────────────────── */
.indicators {{
  display: flex;
  justify-content: center;
  gap: 8px;
  padding: 10px 0 6px;
}}

.idot {{
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--border);
  transition: all 0.3s ease;
  cursor: pointer;
}}

.idot-active {{
  width: 20px;
  border-radius: 3px;
  background: var(--blue);
}}

/* ── AGENTTIPISTEET ─────────────────────────────────────────── */
.agent-status {{
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 16px 12px;
  flex-wrap: wrap;
}}

.agent-label {{
  font-size: 0.68rem;
  color: var(--text3);
  font-family: 'Share Tech Mono', monospace;
  margin-right: 4px;
}}

.adot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}}

.adot-ok  {{ background: var(--green); }}
.adot-err {{ background: var(--red); opacity: 0.7; }}

/* ── SÄÄANIMAATIOT ──────────────────────────────────────────── */
{weather_anim_css}

/* ── SWIPE HINT (näkyy kerran) ──────────────────────────────── */
.swipe-hint {{
  text-align: center;
  font-size: 0.7rem;
  color: var(--text3);
  padding: 2px 0 4px;
  font-family: 'Share Tech Mono', monospace;
  letter-spacing: 0.05em;
}}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="header-left">
    <div class="clock">{now_str}</div>
    <div class="location-row">{loc_html}</div>
  </div>
  <div class="header-right">
    <div class="weather-widget">
      <div class="weather-icon {wtype}-icon">{_weather_emoji(wtype)}</div>
      <div class="weather-temp">{wtemp}</div>
      <div class="weather-desc">{wdesc}</div>
    </div>
  </div>
</div>

<!-- HÄIRIÖBANNERI -->
{disrupt_block}

<!-- SWIPE HINT -->
<div class="swipe-hint">← pyyhkäise →</div>

<!-- KORTTIPINO -->
<div class="stack-wrapper">
  <div class="card-stack" id="cardStack">
    {card_divs}
  </div>
  <div class="indicators" id="indicators">
    {indicator_dots}
  </div>
</div>

<!-- AGENTTISTATUS -->
<div class="agent-status">
  <span class="agent-label">AGENTIT</span>
  {dots_html}
</div>

<script>
(function() {{
  var stack  = document.getElementById('cardStack');
  var dots   = document.querySelectorAll('.idot');
  var cards  = document.querySelectorAll('.card');
  var active = 0;

  // Päivitä aktiivinen dot scroll-tapahtumassa
  function updateDots() {{
    var idx = Math.round(stack.scrollLeft / (stack.offsetWidth || 1));
    if (idx !== active) {{
      dots[active] && dots[active].classList.remove('idot-active');
      dots[idx]    && dots[idx].classList.add('idot-active');
      active = idx;
    }}
  }}

  stack.addEventListener('scroll', updateDots, {{ passive: true }});

  // Klikkaamalla dotia -> siirry korttiin
  dots.forEach(function(dot, i) {{
    dot.addEventListener('click', function() {{
      stack.scrollTo({{ left: i * stack.offsetWidth, behavior: 'smooth' }});
    }});
  }});

  // Piilota swipe-hint ensimmäisen pyyhkäisyn jälkeen
  var hint = document.querySelector('.swipe-hint');
  stack.addEventListener('scroll', function() {{
    if (hint) {{ hint.style.opacity = '0'; hint.style.transition = 'opacity 0.5s'; }}
  }}, {{ once: true, passive: true }});

  // Ilmoita korkeus Streamlitille
  function resize() {{
    if (window.parent !== window) {{
      try {{
        window.parent.postMessage({{
          type: 'streamlit:setFrameHeight',
          height: document.body.scrollHeight + 20
        }}, '*');
      }} catch(e) {{}}
    }}
  }}
  setTimeout(resize, 200);
  window.addEventListener('resize', resize);
}})();
</script>
</body>
</html>"""


def _weather_emoji(wtype: str) -> str:
    return {
        "rain":    "🌧️",
        "snow":    "❄️",
        "thunder": "⛈️",
        "wind":    "💨",
        "frost":   "🥶",
        "cloud":   "☁️",
        "sun":     "☀️",
    }.get(wtype, "☀️")


def _weather_animation_css(wtype: str) -> str:
    """Sää-animaatio oikeanlaiselle säätilalle."""
    base = ""
    if wtype == "rain":
        base = """
@keyframes rainDrop {
  0%   { transform: translateY(-8px); opacity: 0; }
  20%  { opacity: 0.7; }
  100% { transform: translateY(6px);  opacity: 0; }
}
.rain-icon {
  display: inline-block;
  animation: rainDrop 1.2s ease-in infinite;
}"""
    elif wtype == "snow":
        base = """
@keyframes snowFall {
  0%   { transform: translateY(-5px) rotate(0deg); opacity: 0; }
  20%  { opacity: 1; }
  100% { transform: translateY(8px) rotate(180deg); opacity: 0; }
}
.snow-icon {
  display: inline-block;
  animation: snowFall 2s ease-in-out infinite;
}"""
    elif wtype == "thunder":
        base = """
@keyframes flash {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.4; }
}
.thunder-icon {
  display: inline-block;
  animation: flash 1.8s ease-in-out infinite;
}"""
    elif wtype == "wind":
        base = """
@keyframes sway {
  0%,100% { transform: rotate(-5deg); }
  50%     { transform: rotate(5deg); }
}
.wind-icon {
  display: inline-block;
  animation: sway 1.5s ease-in-out infinite;
}"""
    elif wtype == "sun":
        base = """
@keyframes pulse {
  0%,100% { transform: scale(1);    opacity: 1; }
  50%     { transform: scale(1.12); opacity: 0.85; }
}
.sun-icon {
  display: inline-block;
  animation: pulse 3s ease-in-out infinite;
}"""
    elif wtype == "frost":
        base = """
@keyframes shimmer {
  0%,100% { opacity: 1; }
  50%     { opacity: 0.6; }
}
.frost-icon {
  display: inline-block;
  animation: shimmer 2.5s ease-in-out infinite;
}"""
    return base


# ══════════════════════════════════════════════════════════════════════════════
# PÄÄFUNKTIO
# ══════════════════════════════════════════════════════════════════════════════

def render_dashboard(
    hotspots:      list | None = None,
    agent_results: list | None = None,
    refresh_callback=None,
) -> None:
    """
    Renderoi kojelauta full-HTML-komponenttina.

    Yhteensopiva app.py-kutsutavan kanssa:
      render_dashboard()
      render_dashboard(hotspots, agent_results)
    """
    # ── Hae data ─────────────────────────────────────────────────────────────
    if hotspots is None or agent_results is None:
        cache = st.session_state.get("hotspot_cache")
        if cache and isinstance(cache, (tuple, list)) and len(cache) >= 2:
            if hotspots is None:
                hotspots = cache[0]
            if agent_results is None:
                agent_results = cache[1]
        hotspots      = hotspots or []
        agent_results = agent_results or []

    # ── GPS-komponentti (injektoi kerran) ────────────────────────────────────
    try:
        from src.taxiapp.location import inject_gps_component
        inject_gps_component()
    except Exception:
        pass

    # ── Kellonaika (Helsinki) ────────────────────────────────────────────────
    import time as _t
    offset  = 3 if _t.daylight else 2
    now_hki = datetime.now(timezone.utc) + timedelta(hours=offset)
    now_str = now_hki.strftime("%H:%M")

    # ── Sijainti ─────────────────────────────────────────────────────────────
    location = _get_location()
    loc_info = _nearest_area_info(location)

    # ── Sää ──────────────────────────────────────────────────────────────────
    weather = _extract_weather(agent_results)

    # ── Häiriöt ───────────────────────────────────────────────────────────────
    disruptions = _extract_disruptions(agent_results)

    # ── Agenttipisteet ───────────────────────────────────────────────────────
    agent_dots = []
    for r in (agent_results or []):
        name    = getattr(r, "agent_name", "?")
        ok      = getattr(r, "status", "") in ("ok", "cached")
        signals = len(getattr(r, "signals", []))
        agent_dots.append({"name": name, "ok": ok, "signals": signals})

    # ── Jos ei hotspotteja ───────────────────────────────────────────────────
    if not hotspots:
        components.html(
            f"""<html><body style="background:#080a0f;color:#555a70;
            font-family:'Jost',sans-serif;display:flex;align-items:center;
            justify-content:center;height:200px;font-size:1rem;">
            ⏳ Ladataan agentteja...</body></html>""",
            height=200,
        )
        _, c, _ = st.columns([1, 2, 1])
        with c:
            if st.button("🔄 Päivitä", use_container_width=True, key="dash_refresh_empty"):
                st.cache_resource.clear()
                st.rerun()
        return

    # ── Rakenna korttidata ────────────────────────────────────────────────────
    st.session_state["ceo_hotspots"] = hotspots
    cards = [
        _card_data(h, location, i)
        for i, h in enumerate(hotspots[:3])
    ]

    # ── Renderöi HTML ─────────────────────────────────────────────────────────
    html = _build_html(
        cards=cards,
        weather=weather,
        loc_info=loc_info,
        disruptions=disruptions,
        now_str=now_str,
        agent_dots=agent_dots,
    )
    components.html(html, height=660, scrolling=False)

    # ── Päivitä-nappi Streamlit-kerroksessa ──────────────────────────────────
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        if st.button("🔄 Päivitä nyt", use_container_width=True, key="dash_refresh"):
            if refresh_callback:
                refresh_callback()
            else:
                for k in ("hotspot_cache", "hotspot_ts"):
                    st.session_state.pop(k, None)
                st.rerun()
