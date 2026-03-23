# settings_tab.py -- Asetukset-valilehti
# Helsinki Taxi AI
# Korjattu: _load_weights ei koskaan palauta None

from __future__ import annotations

from typing import Optional

import streamlit as st


# ---------------------------------------------------------------------------
# VAKIOT
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "weight_trains":    1.0,
    "weight_flights":   1.0,
    "weight_ferries":   1.0,
    "weight_events":    1.0,
    "weight_weather":   1.0,
    "weight_nightlife": 1.0,
    "weight_sports":    1.0,
    "weight_business":  1.0,
}

WEIGHT_DEFS: list[dict] = [
    {
        "key":   "weight_trains",
        "label": "Junat",
        "desc":  "HKI / PSL / TKL -- saapuvat kaukojunat",
        "color": "#60A5FA",
        "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.0,
    },
    {
        "key":   "weight_flights",
        "label": "Lennot",
        "desc":  "Helsinki-Vantaa -- saapuvat lennot",
        "color": "#34D399",
        "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.0,
    },
    {
        "key":   "weight_ferries",
        "label": "Lautat",
        "desc":  "Lansisatama P1/P2/P3 -- laiva-saapumiset",
        "color": "#22D3EE",
        "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.0,
    },
    {
        "key":   "weight_events",
        "label": "Tapahtumat",
        "desc":  "Konsertit, messut, urheilu, teatteri",
        "color": "#F59E0B",
        "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.0,
    },
    {
        "key":   "weight_weather",
        "label": "Saa ja uutiset",
        "desc":  "FMI saa + RSS-uutiset -- liikennevaikutukset",
        "color": "#89CFF0",
        "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.0,
    },
    {
        "key":   "weight_nightlife",
        "label": "Yoelama",
        "desc":  "Kamppi / Kallio / Hakaniemi -- ravintolat, baarit",
        "color": "#F472B6",
        "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.0,
    },
    {
        "key":   "weight_sports",
        "label": "Urheilu",
        "desc":  "Pasila / Olympiastadion / Messukeskus -- ottelut",
        "color": "#FB923C",
        "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.0,
    },
    {
        "key":   "weight_business",
        "label": "Business",
        "desc":  "Katajanokka / Erottaja -- liikematkustajat",
        "color": "#34D399",
        "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.0,
    },
]

PRESETS: dict[str, dict[str, float]] = {
    "Tasapaino (oletus)": {k: 1.0 for k in DEFAULT_WEIGHTS},
    "Junapainotus": {
        "weight_trains": 2.5, "weight_flights": 0.8,
        "weight_ferries": 0.8, "weight_events": 1.0,
        "weight_weather": 1.0, "weight_nightlife": 0.6,
        "weight_sports": 0.8, "weight_business": 1.0,
    },
    "Lentokenttapainotus": {
        "weight_trains": 1.0, "weight_flights": 2.5,
        "weight_ferries": 0.5, "weight_events": 0.8,
        "weight_weather": 1.2, "weight_nightlife": 0.5,
        "weight_sports": 0.7, "weight_business": 1.5,
    },
    "Tapahtumat ja yoelama": {
        "weight_trains": 0.8, "weight_flights": 0.5,
        "weight_ferries": 0.5, "weight_events": 2.5,
        "weight_weather": 0.8, "weight_nightlife": 2.0,
        "weight_sports": 1.5, "weight_business": 0.5,
    },
    "Business ja satama": {
        "weight_trains": 1.2, "weight_flights": 1.5,
        "weight_ferries": 2.0, "weight_events": 0.6,
        "weight_weather": 1.0, "weight_nightlife": 0.3,
        "weight_sports": 0.5, "weight_business": 2.5,
    },
}

VOICE_OPTIONS: dict[str, str] = {
    "off":    "Pois paalta",
    "web":    "Web Speech API (ilmainen)",
    "openai": "OpenAI TTS (laadukkaampi)",
}

SETTINGS_CSS = """
<style>
.settings-section {
    background: #1a1d27;
    border-radius: 16px;
    padding: 20px 22px;
    margin-bottom: 16px;
    border: 1px solid #2a2d3d;
}
.settings-section-title {
    font-size: 0.78rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #888899;
    margin-bottom: 14px;
}
.weight-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2px;
}
.weight-name  { font-size: 0.85rem; font-weight: 500; }
.weight-value { font-size: 0.85rem; font-weight: 700; }
.weight-desc  { font-size: 0.72rem; color: #888899; margin-bottom: 4px; }
.weight-preview {
    height: 4px;
    border-radius: 2px;
    margin-top: 2px;
    margin-bottom: 8px;
    min-width: 4px;
}
.toggle-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid #2a2d3d;
}
.toggle-row:last-child { border-bottom: none; }
.toggle-label { font-size: 0.9rem; }
.toggle-desc  { font-size: 0.74rem; color: #888899; margin-top: 2px; }
</style>
"""


# ---------------------------------------------------------------------------
# APUFUNKTIOT
# ---------------------------------------------------------------------------

def _load_weights(driver_id: Optional[str] = None) -> dict[str, float]:
    """Lataa painot. Palauttaa AINA dictin, ei koskaan None."""
    try:
        saved = st.session_state.get("driver_weights")
        if saved and isinstance(saved, dict) and len(saved) > 0:
            return {**DEFAULT_WEIGHTS, **saved}
    except Exception:
        pass

    if driver_id:
        try:
            from src.taxiapp.repository.database import PreferencesRepo
            prefs = PreferencesRepo.get(driver_id)
            if prefs and isinstance(prefs, dict) and len(prefs) > 0:
                return {**DEFAULT_WEIGHTS, **prefs}
        except Exception:
            pass

    return dict(DEFAULT_WEIGHTS)


def _save_weights(weights: dict[str, float], driver_id: Optional[str]) -> bool:
    try:
        st.session_state["driver_weights"] = weights
        for k in ("hotspot_cache", "hotspot_ts"):
            st.session_state.pop(k, None)
        if driver_id:
            try:
                from src.taxiapp.repository.database import PreferencesRepo
                return PreferencesRepo.upsert(driver_id, weights)
            except Exception:
                pass
        return True
    except Exception:
        return False


def _load_settings() -> dict:
    return st.session_state.get("app_settings", {
        "voice_provider":  "web",
        "voice_enabled":   True,
        "alert_threshold": 7,
        "refresh_seconds": 30,
        "dark_mode":       True,
        "show_map":        False,
        "auto_read_cards": False,
        "language":        "fi",
    })


def _save_settings(settings: dict) -> None:
    st.session_state["app_settings"] = settings


# ---------------------------------------------------------------------------
# KOMPONENTIT
# ---------------------------------------------------------------------------

def render_weight_sliders(current_weights: dict[str, float]) -> dict[str, float]:
    """Renderoi 8 liukusaadinta. Palauttaa paivitetyt painot."""
    # KORJAUS: varmista etta current_weights on aina dict
    if not isinstance(current_weights, dict):
        current_weights = dict(DEFAULT_WEIGHTS)

    new_weights: dict[str, float] = {}
    col_left, col_right = st.columns(2, gap="large")

    for i, wdef in enumerate(WEIGHT_DEFS):
        col = col_left if i < 4 else col_right
        with col:
            key   = wdef["key"]
            color = wdef["color"]
            val   = float(current_weights.get(key, wdef["default"]))

            st.markdown(
                '<div class="weight-label">'
                '<span class="weight-name" style="color:' + color + '">' + wdef["label"] + '</span>'
                '<span class="weight-value" style="color:' + color + '">' + "{:.1f}".format(val) + 'x</span>'
                '</div>'
                '<div class="weight-desc">' + wdef["desc"] + '</div>',
                unsafe_allow_html=True,
            )

            new_val = st.slider(
                label=wdef["label"],
                min_value=wdef["min"],
                max_value=wdef["max"],
                value=val,
                step=wdef["step"],
                label_visibility="collapsed",
                key="slider_" + key,
            )
            new_weights[key] = round(float(new_val), 1)

            pct = int(float(new_val) / wdef["max"] * 100)
            st.markdown(
                '<div class="weight-preview" style="width:' + str(pct) + '%;background:' + color + '22;border:1px solid ' + color + '44"></div>',
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    return new_weights


def render_presets() -> Optional[dict[str, float]]:
    st.markdown(
        '<div class="settings-section-title">Valmiit profiilit</div>',
        unsafe_allow_html=True,
    )
    selected: Optional[dict] = None
    cols = st.columns(len(PRESETS))
    for col, (label, weights) in zip(cols, PRESETS.items()):
        with col:
            if st.button(label, key="preset_" + label, use_container_width=True):
                selected = weights
                st.toast("Profiili ladattu: " + label)
    return selected


def render_voice_settings(current: dict) -> dict:
    st.markdown(
        '<div class="settings-section-title">Aaniasetukset</div>',
        unsafe_allow_html=True,
    )
    provider = st.selectbox(
        "Aani",
        options=list(VOICE_OPTIONS.keys()),
        format_func=lambda x: VOICE_OPTIONS[x],
        index=list(VOICE_OPTIONS.keys()).index(current.get("voice_provider", "web")),
        key="sel_voice_provider",
        label_visibility="collapsed",
    )
    enabled = st.toggle(
        "Aani kaytossa",
        value=current.get("voice_enabled", True),
        key="tog_voice_enabled",
    )
    return {**current, "voice_provider": provider, "voice_enabled": enabled}


def render_general_settings(current: dict) -> dict:
    st.markdown(
        '<div class="settings-section-title">Yleiset asetukset</div>',
        unsafe_allow_html=True,
    )
    refresh = st.slider(
        "Paivitysvaili (sekuntia)",
        min_value=10, max_value=300,
        value=int(current.get("refresh_seconds", 30)),
        step=10,
        key="sl_refresh",
    )
    threshold = st.select_slider(
        "Hairiohalsytys-kynnys",
        options=[5, 7, 9],
        value=int(current.get("alert_threshold", 7)),
        key="sl_threshold",
    )
    return {**current, "refresh_seconds": refresh, "alert_threshold": threshold}


def render_weight_visualizer(weights: dict[str, float]) -> None:
    total = sum(weights.values())
    if total == 0:
        return
    st.markdown(
        '<div class="settings-section-title">Painojen yhteenveto</div>',
        unsafe_allow_html=True,
    )
    bars_html = '<div style="display:flex;flex-direction:column;gap:6px">'
    for wdef in WEIGHT_DEFS:
        key   = wdef["key"]
        color = wdef["color"]
        val   = weights.get(key, 1.0)
        pct   = int(val / 3.0 * 100)
        bars_html += (
            '<div style="display:flex;align-items:center;gap:10px;font-size:0.82rem">'
            '<span style="min-width:130px;color:#CCCCDD">' + wdef["label"] + '</span>'
            '<div style="flex:1;background:#12151e;border-radius:4px;height:8px;overflow:hidden">'
            '<div style="width:' + str(pct) + '%;height:100%;background:' + color + ';border-radius:4px"></div>'
            '</div>'
            '<span style="min-width:32px;text-align:right;color:' + color + ';font-weight:700">' + "{:.1f}x".format(val) + '</span>'
            '</div>'
        )
    bars_html += '</div>'
    st.markdown(bars_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# PAARUNKTIO
# ---------------------------------------------------------------------------

def render_settings_tab(driver_id: Optional[str] = None) -> None:
    st.markdown(SETTINGS_CSS, unsafe_allow_html=True)

    current_weights = _load_weights(driver_id)
    # Varmistus -- ei koskaan None
    if not isinstance(current_weights, dict):
        current_weights = dict(DEFAULT_WEIGHTS)

    current_settings = _load_settings()

    st.markdown('<div class="settings-section">', unsafe_allow_html=True)
    preset_weights = render_presets()
    if preset_weights:
        current_weights = preset_weights
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="settings-section-title">Kategoriapainot</div>', unsafe_allow_html=True)
    new_weights = render_weight_sliders(current_weights)

    render_weight_visualizer(new_weights)

    new_settings = render_voice_settings(current_settings)
    new_settings = render_general_settings(new_settings)

    col_btn, col_status, col_reset = st.columns([2, 3, 2])
    with col_btn:
        save_clicked = st.button(
            "Tallenna asetukset",
            type="primary",
            use_container_width=True,
            key="btn_save_settings",
        )
    with col_reset:
        reset_clicked = st.button(
            "Palauta oletukset",
            use_container_width=True,
            key="btn_reset_settings",
        )

    if save_clicked:
        ok = _save_weights(new_weights, driver_id)
        _save_settings(new_settings)
        with col_status:
            if ok:
                st.success("Asetukset tallennettu!")
            else:
                st.warning("Tallennettu paikallisesti.")

    if reset_clicked:
        st.session_state.pop("driver_weights", None)
        st.session_state.pop("app_settings", None)
        st.rerun()
