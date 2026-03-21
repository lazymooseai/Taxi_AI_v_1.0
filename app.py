from __future__ import annotations

import logging
import time
from importlib import import_module
from typing import Any, Optional

import streamlit as st

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# SIVUMODUULIEN TUONTI ROBUSTILLA FALLBACKILLA
# ============================================================

def _import_ui_modules() -> dict[str, Any]:
    candidates = [
        {
            "dashboard": "dashboard",
            "events": "events_tab",
            "links": "links_tab",
            "stats": "stats_tab",
            "settings": "settings_tab",
            "admin": "admin_tab",
        },
        {
            "dashboard": "src.taxiapp.dashboard",
            "events": "src.taxiapp.events_tab",
            "links": "src.taxiapp.links_tab",
            "stats": "src.taxiapp.stats_tab",
            "settings": "src.taxiapp.settings_tab",
            "admin": "src.taxiapp.admin_tab",
        },
        {
            "dashboard": "src.taxiapp.ui.dashboard",
            "events": "src.taxiapp.ui.events_tab",
            "links": "src.taxiapp.ui.links_tab",
            "stats": "src.taxiapp.ui.stats_tab",
            "settings": "src.taxiapp.ui.settings_tab",
            "admin": "src.taxiapp.ui.admin_tab",
        },
    ]

    last_error: Optional[Exception] = None

    for paths in candidates:
        try:
            dashboard_mod = import_module(paths["dashboard"])
            events_mod = import_module(paths["events"])
            links_mod = import_module(paths["links"])
            stats_mod = import_module(paths["stats"])
            settings_mod = import_module(paths["settings"])
            admin_mod = import_module(paths["admin"])

            return {
                "render_dashboard": getattr(dashboard_mod, "render_dashboard"),
                "fetch_hotspots": getattr(dashboard_mod, "fetch_hotspots", None),
                "render_events_tab": getattr(events_mod, "render_events_tab"),
                "render_links_tab": getattr(links_mod, "render_links_tab"),
                "render_stats_tab": getattr(stats_mod, "render_stats_tab"),
                "render_settings_tab": getattr(settings_mod, "render_settings_tab"),
                "render_admin_tab": getattr(admin_mod, "render_admin_tab"),
            }
        except Exception as e:
            last_error = e

    raise RuntimeError(f"UI-moduulien tuonti epäonnistui: {last_error}")


UI = _import_ui_modules()

render_dashboard = UI["render_dashboard"]
fetch_hotspots = UI["fetch_hotspots"]
render_events_tab = UI["render_events_tab"]
render_links_tab = UI["render_links_tab"]
render_stats_tab = UI["render_stats_tab"]
render_settings_tab = UI["render_settings_tab"]
render_admin_tab = UI["render_admin_tab"]


# ============================================================
# TIETOKANTA / DRIVER-REPO FALLBACKILLA
# ============================================================

def _import_driver_repo():
    for mod_path in (
        "src.taxiapp.repository.database",
        "repository.database",
        "database",
    ):
        try:
            mod = import_module(mod_path)
            return getattr(mod, "DriverRepo", None)
        except Exception:
            continue
    return None


DriverRepo = _import_driver_repo()


# ============================================================
# ASETUKSET JA SESSION STATE
# ============================================================

APP_TITLE = "Helsinki Taxi AI"
APP_ICON = "🚕"

DEFAULT_APP_SETTINGS = {
    "voice_provider": "web",
    "voice_enabled": True,
    "alert_threshold": 7,
    "refresh_seconds": 30,
    "dark_mode": True,
    "show_map": False,
    "auto_read_cards": False,
    "language": "fi",
}


def _init_page() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )


def _init_state() -> None:
    st.session_state.setdefault("driver_id", None)
    st.session_state.setdefault("active_page", "Kojelauta")
    st.session_state.setdefault("shared_agent_results", [])
    st.session_state.setdefault("shared_agent_results_ts", 0.0)

    if "app_settings" not in st.session_state:
        st.session_state["app_settings"] = DEFAULT_APP_SETTINGS.copy()


# ============================================================
# APUTOIMINNOT
# ============================================================

def _app_settings() -> dict:
    settings = st.session_state.get("app_settings", {})
    return {**DEFAULT_APP_SETTINGS, **settings}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clear_runtime_cache() -> None:
    for key in (
        "hotspot_cache",
        "hotspot_ts",
        "shared_agent_results",
        "shared_agent_results_ts",
    ):
        st.session_state.pop(key, None)

    try:
        st.cache_data.clear()
    except Exception:
        pass

    try:
        st.cache_resource.clear()
    except Exception:
        pass


def _load_active_drivers() -> list[dict]:
    if DriverRepo is None:
        return []

    try:
        drivers = DriverRepo.get_all_active()
        return drivers or []
    except Exception as e:
        logger.warning("Kuljettajien haku epäonnistui: %s", e)
        return []


def _current_driver_label(drivers: list[dict], driver_id: Optional[str]) -> str:
    if not driver_id:
        return "Ei valittu"

    for d in drivers:
        if d.get("id") == driver_id:
            name = d.get("name", "Tuntematon")
            car = d.get("car_model") or "ei autoa"
            return f"{name} · {car}"

    return "Ei valittu"


def _load_shared_agent_results(force: bool = False) -> list:
    cached = st.session_state.get("shared_agent_results", [])
    cached_ts = float(st.session_state.get("shared_agent_results_ts", 0.0))
    refresh_seconds = _safe_int(_app_settings().get("refresh_seconds", 30), 30)
    ttl = max(10, min(refresh_seconds, 120))

    if force:
        st.session_state["shared_agent_results"] = []
        st.session_state["shared_agent_results_ts"] = 0.0
        cached = []
        cached_ts = 0.0

    now = time.monotonic()

    if cached and (now - cached_ts) < ttl:
        return cached

    if fetch_hotspots is None:
        return cached

    try:
        _, agent_results = fetch_hotspots()
        st.session_state["shared_agent_results"] = agent_results or []
        st.session_state["shared_agent_results_ts"] = now
        return st.session_state["shared_agent_results"]
    except Exception as e:
        logger.exception("Agenttidatan haku epäonnistui: %s", e)
        return cached or []


# ============================================================
# ULKOASU
# ============================================================

APP_CSS = """
<style>
.block-container {
    padding-top: 1.0rem;
    padding-bottom: 1.5rem;
    max-width: 1320px;
}
.app-shell {
    background: linear-gradient(135deg, #0e1117 0%, #151925 100%);
    border: 1px solid #2a2d3d;
    border-radius: 18px;
    padding: 18px 22px;
    margin-bottom: 14px;
}
.app-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #FAFAFA;
    margin-bottom: 2px;
}
.app-sub {
    font-size: 0.82rem;
    color: #888899;
}
.app-kpis {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 12px;
}
.app-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 999px;
    background: #1a1d27;
    border: 1px solid #2a2d3d;
    font-size: 0.78rem;
    color: #CCCCDD;
}
section[data-testid="stSidebar"] .block-container {
    padding-top: 1rem;
}
</style>
"""


def _render_app_header(agent_results: list) -> None:
    drivers = _load_active_drivers()
    driver_label = _current_driver_label(drivers, st.session_state.get("driver_id"))
    refresh_seconds = _safe_int(_app_settings().get("refresh_seconds", 30), 30)
    cached_at = float(st.session_state.get("shared_agent_results_ts", 0.0))
    cache_age = max(0, int(time.monotonic() - cached_at)) if cached_at else None

    st.markdown(APP_CSS, unsafe_allow_html=True)

    pills = [
        f'<span class="app-pill">📍 Kuljettaja: {driver_label}</span>',
        f'<span class="app-pill">⏱️ Päivitysväli: {refresh_seconds}s</span>',
    ]

    if agent_results:
        pills.append(f'<span class="app-pill">📡 Agenttitulosjoukko: {len(agent_results)}</span>')
    if cache_age is not None:
        pills.append(f'<span class="app-pill">🕒 Välimuisti-ikä: {cache_age}s</span>')

    st.markdown(
        f"""
        <div class="app-shell">
            <div class="app-title">🚕 Helsinki Taxi AI</div>
            <div class="app-sub">Operatiivinen sovellus: kojelauta, tapahtumat, linkit, tilastot, asetukset ja ylläpito.</div>
            <div class="app-kpis">{''.join(pills)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🚕 Helsinki Taxi AI")
        st.caption("Tuotanto-appi välilehtimoduuleille")

        drivers = _load_active_drivers()
        driver_options = [None] + [d.get("id") for d in drivers if d.get("id")]
        current_driver_id = st.session_state.get("driver_id")

        if current_driver_id not in driver_options:
            current_driver_id = None

        label_map = {None: "— Ei valittu —"}
        for d in drivers:
            did = d.get("id")
            if did:
                name = d.get("name", "Tuntematon")
                car = d.get("car_model") or "ei autoa"
                label_map[did] = f"{name} · {car}"

        selected_driver = st.selectbox(
            "Kuljettaja",
            options=driver_options,
            index=driver_options.index(current_driver_id),
            format_func=lambda x: label_map.get(x, str(x)),
        )
        st.session_state["driver_id"] = selected_driver

        st.markdown("---")

        pages = [
            "Kojelauta",
            "Tapahtumat",
            "Linkit",
            "Tilastot",
            "Asetukset",
            "Ylläpito",
        ]
        current_page = st.session_state.get("active_page", "Kojelauta")
        if current_page not in pages:
            current_page = "Kojelauta"

        selected_page = st.radio(
            "Sivu",
            options=pages,
            index=pages.index(current_page),
            label_visibility="collapsed",
        )
        st.session_state["active_page"] = selected_page

        st.markdown("---")

        if st.button("🔄 Pakota päivitys", use_container_width=True):
            _clear_runtime_cache()
            st.rerun()

        settings = _app_settings()
        st.caption(
            f"Ääni: {settings.get('voice_provider', 'web')} · "
            f"Ilmoituskynnys: {settings.get('alert_threshold', 7)}"
        )


# ============================================================
# SIVURENDERÖINTI
# ============================================================

def _render_selected_page() -> None:
    page = st.session_state.get("active_page", "Kojelauta")
    driver_id = st.session_state.get("driver_id")

    if page == "Kojelauta":
        render_dashboard()
        return

    agent_results = _load_shared_agent_results()
    _render_app_header(agent_results)

    if page == "Tapahtumat":
        render_events_tab(agent_results)
    elif page == "Linkit":
        render_links_tab(agent_results)
    elif page == "Tilastot":
        render_stats_tab(agent_results, driver_id)
    elif page == "Asetukset":
        render_settings_tab(driver_id)
    elif page == "Ylläpito":
        render_admin_tab(driver_id)
    else:
        st.warning("Tuntematon sivuvalinta.")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    _init_page()
    _init_state()
    _render_sidebar()
    _render_selected_page()


if __name__ == "__main__":
    main()
