# stats_tab.py -- Tilastot-valilehti
# Helsinki Taxi AI
# Korjattu: render_learning_section accuracy_pct alustettu None:ksi

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import streamlit as st

from src.taxiapp.base_agent import AgentResult
from src.taxiapp.demand_model import get_demand_model, DemandFeatures


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

STATS_CSS = """
<style>
.stat-card {
    background: #1a1d27;
    border-radius: 14px;
    padding: 16px 20px;
    border: 1px solid #2a2d3d;
    margin-bottom: 12px;
}
.stat-title {
    font-size: 0.75rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #888899;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.bar-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 7px;
    font-size: 0.82rem;
}
.bar-label {
    min-width: 130px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: #CCCCDD;
}
.bar-track {
    flex: 1;
    background: #12151e;
    border-radius: 4px;
    height: 10px;
    overflow: hidden;
}
.bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.4s ease;
}
.bar-val {
    min-width: 36px;
    text-align: right;
    color: #888899;
    font-size: 0.78rem;
}
.ml-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
}
.ml-table th {
    color: #888899;
    font-weight: 600;
    padding: 4px 8px;
    text-align: left;
    border-bottom: 1px solid #2a2d3d;
}
.ml-table td {
    padding: 5px 8px;
    border-bottom: 1px solid #1a1d27;
    color: #CCCCDD;
}
.ml-soon    { color: #FF4B4B; font-weight: 700; }
.ml-landing { color: #FFD700; }
.ml-delayed { color: #FF8C00; }
.kpi-box {
    background: #12151e;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: center;
    border: 1px solid #2a2d3d;
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 1.6rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.kpi-label {
    font-size: 0.68rem;
    color: #888899;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 4px;
}
.heat-cell {
    display: inline-block;
    width: 22px;
    height: 22px;
    border-radius: 4px;
    margin: 2px;
    vertical-align: middle;
}
.heat-label {
    font-size: 0.72rem;
    color: #888899;
    min-width: 80px;
    display: inline-block;
}
.ride-heat-row {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 4px;
}
.status-pill {
    display: inline-block;
    font-size: 0.68rem;
    padding: 2px 8px;
    border-radius: 20px;
    font-weight: 600;
}
.status-ok       { background: #21C55D22; color: #21C55D; }
.status-cached   { background: #88889922; color: #888899; }
.status-error    { background: #FF4B4B22; color: #FF4B4B; }
.status-disabled { background: #33333322; color: #666677; }
.summary-stat {
    text-align: center;
    min-width: 70px;
}
.summary-stat .num {
    font-size: 1.8rem;
    font-weight: 700;
    line-height: 1;
}
.summary-stat .lbl {
    font-size: 0.68rem;
    color: #888899;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 2px;
}
</style>
"""


# ---------------------------------------------------------------------------
# APUFUNKTIOT
# ---------------------------------------------------------------------------

def _status_pill(status: str) -> str:
    cfg = {
        "ok":       ("status-ok",       "OK"),
        "cached":   ("status-cached",   "Valimuisti"),
        "error":    ("status-error",    "Virhe"),
        "disabled": ("status-disabled", "Pois"),
    }.get(status, ("status-disabled", status))
    return '<span class="status-pill ' + cfg[0] + '">' + cfg[1] + '</span>'


def _fmt_ms(ms: Optional[float]) -> str:
    if ms is None:
        return ""
    if ms < 1000:
        return str(int(ms)) + "ms"
    return "{:.1f}s".format(ms / 1000)


def _get_result(
    agent_results: list,
    agent_name: str,
) -> Optional[object]:
    return next(
        (r for r in agent_results if getattr(r, "agent_name", "") == agent_name),
        None,
    )


# ---------------------------------------------------------------------------
# AGENTTIOSIO
# ---------------------------------------------------------------------------

def render_agent_section(agent_name: str, result: Optional[object]) -> None:
    if result is None:
        st.markdown(
            '<div class="stat-card"><div class="stat-title">' +
            agent_name + ' -- ei dataa</div></div>',
            unsafe_allow_html=True,
        )
        return

    status = getattr(result, "status", "error" if not getattr(result, "ok", False) else "ok")
    signals = getattr(result, "signals", [])
    elapsed = getattr(result, "elapsed_ms", None)

    header = (
        '<div class="stat-card">'
        '<div class="stat-title">'
        + agent_name + " "
        + _status_pill(status)
        + '<span style="color:#888899;font-size:0.72rem">'
        + str(len(signals)) + " signaalia"
        + (" | " + _fmt_ms(elapsed) if elapsed else "")
        + "</span></div>"
    )

    rows_html = ""
    for sig in signals[:8]:
        desc = getattr(sig, "description", "")
        urgency = getattr(sig, "urgency", 1)
        score = getattr(sig, "score", 0.0)
        color = "#FF4B4B" if urgency >= 7 else "#FFD700" if urgency >= 5 else "#00B4D8"
        rows_html += (
            '<div class="bar-row">'
            '<span class="bar-label">' + str(desc)[:60] + "</span>"
            '<div class="bar-track">'
            '<div class="bar-fill" style="width:' + str(min(int(score * 10), 100)) + '%;background:' + color + '"></div>'
            "</div>"
            '<span class="bar-val">' + str(round(score, 1)) + "</span>"
            "</div>"
        )

    st.markdown(header + rows_html + "</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# JUNA-OSIO
# ---------------------------------------------------------------------------

def render_train_section(agent_results: list) -> None:
    result = _get_result(agent_results, "TrainAgent")
    if not result:
        return

    signals = getattr(result, "signals", [])
    if not signals:
        return

    rows = ""
    for sig in signals[:10]:
        extra = getattr(sig, "extra", {}) or {}
        station = extra.get("station_name", "")
        origin = extra.get("origin", "")
        arrival = extra.get("actual_arrival", "")[:16].replace("T", " ") if extra.get("actual_arrival") else ""
        delay = extra.get("delay_minutes", 0)
        train_type = extra.get("train_type", "")
        train_num = extra.get("train_number", "")

        delay_html = ""
        if delay >= 15:
            delay_html = '<span style="color:#FF4B4B">+' + str(delay) + "min</span>"
        elif delay >= 5:
            delay_html = '<span style="color:#FFD700">+' + str(delay) + "min</span>"

        rows += (
            "<tr>"
            "<td>" + str(train_type) + str(train_num) + "</td>"
            "<td>" + str(origin) + "</td>"
            "<td>" + str(station) + "</td>"
            "<td>" + str(arrival) + " " + delay_html + "</td>"
            "</tr>"
        )

    if rows:
        st.markdown(
            '<div class="stat-card">'
            '<div class="stat-title">Saapuvat kaukojunat</div>'
            '<table class="ml-table">'
            "<thead><tr><th>Juna</th><th>Lahto</th><th>Asema</th><th>Saapuu</th></tr></thead>"
            "<tbody>" + rows + "</tbody>"
            "</table></div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# OPPIMIS-OSIO (KORJATTU)
# ---------------------------------------------------------------------------

def _motivation_message(accuracy_pct: Optional[float]) -> tuple:
    if accuracy_pct is None:
        return "Malli oppii -- kirjaa ensimmainen kyyti!", "#888899"
    if accuracy_pct < 50:
        return "Malli oppii viela -- kirjaa lisaa kyyteja", "#888899"
    if accuracy_pct < 70:
        return "Kohtalainen tarkkuus -- jatka kirjaamista", "#FFD700"
    if accuracy_pct < 85:
        return "Hyva tarkkuus -- malli toimii hyvin!", "#21C55D"
    return "Erinomainen -- TaksiAI tuntee Helsingin!", "#00B4D8"


def render_learning_section(
    agent_results: list,
    driver_id: Optional[str] = None,
) -> None:
    try:
        model = get_demand_model()
    except Exception:
        st.caption("River-malli ei saatavilla")
        return

    history: list = []
    rolling_7d: Optional[float] = None
    try:
        from src.taxiapp.repository.database import ModelAccuracyRepo
        history = ModelAccuracyRepo.get_recent(driver_id, days=30)
        rolling_7d = ModelAccuracyRepo.get_rolling_hit_rate(driver_id, days=7)
    except Exception:
        pass

    # KRIITTINEN: accuracy_pct alustetaan AINA ensin
    accuracy_pct: Optional[float] = None
    if rolling_7d is not None:
        accuracy_pct = rolling_7d * 100
    elif getattr(model, "accuracy_pct", None) is not None:
        accuracy_pct = model.accuracy_pct

    msg, msg_color = _motivation_message(accuracy_pct)

    acc_str = "{:.1f}%".format(accuracy_pct) if accuracy_pct is not None else "-"
    trained = getattr(model, "trained_samples", 0)
    mae_val = getattr(model, "mae", None)
    mae_str = "{:.2f}".format(mae_val) if mae_val is not None else "-"

    c1, c2, c3, c4 = st.columns(4)
    for col, val, lbl, color in [
        (c1, acc_str,                   "Tarkkuus (7pv)",  "#00B4D8"),
        (c2, str(trained),              "Opetuskyyteja",   "#A78BFA"),
        (c3, mae_str,                   "MAE (virhe)",     "#FB923C"),
        (c4, str(len(history)) + "pv",  "Historiadata",   "#34D399"),
    ]:
        with col:
            st.markdown(
                '<div class="kpi-box">'
                '<div class="kpi-value" style="color:' + color + '">' + val + '</div>'
                '<div class="kpi-label">' + lbl + '</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div style="background:#1a1d27;border-radius:10px;padding:12px 16px;'
        'border-left:4px solid ' + msg_color + ';margin:10px 0;font-size:0.9rem">'
        + msg + "</div>",
        unsafe_allow_html=True,
    )

    if len(history) >= 2:
        import pandas as pd
        df = pd.DataFrame(
            {"Tarkkuus %": [(r.get("hit_rate") or 0) * 100 for r in reversed(history)]},
            index=[r.get("date", "") for r in reversed(history)],
        )
        st.line_chart(df, color="#00B4D8", height=160)

    with st.expander("Opeta mallia kasin", expanded=False):
        st.caption("Kirjaa todellinen kysynta -- malli oppii valittomasti.")
        col_a, col_b = st.columns(2)
        with col_a:
            actual = st.number_input(
                "Todellinen kysynta (0-10)",
                min_value=0.0, max_value=10.0, value=5.0, step=0.5,
                key="manual_teach_actual",
            )
        with col_b:
            st.text_input("Alue", value="Rautatieasema", key="manual_teach_area")
        if st.button("Tallenna opetus", key="btn_teach_model"):
            try:
                features = DemandFeatures()
                model.learn(features, float(actual))
                st.success("Tallennettu! Opetuskyyteja: " + str(model.trained_samples))
            except Exception as exc:
                st.error("Virhe: " + str(exc))

    st.divider()
    _render_ocr_learning(model, driver_id)


# ---------------------------------------------------------------------------
# OCR / KAMERA / TIEDOSTO - ML-opetus
# ---------------------------------------------------------------------------

def _run_ocr(image_bytes: bytes) -> str:
    """
    Aja OCR kuvatiedostoon. Kayttaa easyocr jos saatavilla,
    muuten palauttaa tyhjaa.
    """
    try:
        import easyocr
        import numpy as np
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)
        reader = easyocr.Reader(["fi", "en"], gpu=False, verbose=False)
        results = reader.readtext(arr, detail=0, paragraph=True)
        return "\n".join(results)
    except Exception as e:
        return f"OCR virhe: {e}"


def _parse_ocr_to_rows(text: str) -> list[dict]:
    """
    Jassenna OCR-teksti tolppa/alue-riveiksi.
    Etsii numeroa + nimen muotoja kuten:
      12  Rautatieasema  K+3  T+1
      Tolppa 5 Kamppi
    """
    import re
    rows = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        # Etsi: numero + teksti + mahdolliset K+N T+N luvut
        m = re.match(
            r'(\d{1,3})\s+([A-Za-zaaoOaA\s\-]{3,40})'
            r'(?:\s+K\+?(\d+))?(?:\s+T\+?(\d+))?',
            line, re.IGNORECASE
        )
        if m:
            rows.append({
                "numero":  m.group(1),
                "nimi":    m.group(2).strip(),
                "k_plus":  int(m.group(3)) if m.group(3) else 0,
                "t_plus":  int(m.group(4)) if m.group(4) else 0,
            })
    return rows


def _save_ocr_to_db(
    text: str,
    rows: list[dict],
    driver_id: Optional[str],
    source_name: str = "kamera",
) -> bool:
    """Tallenna OCR-tulos Supabaseen dispatch_snapshots-tauluun."""
    try:
        import json
        from src.taxiapp.repository.database import get_db
        get_db().table("dispatch_snapshots").insert({
            "driver_id":       driver_id,
            "source_type":     "image",
            "source_name":     source_name,
            "raw_ocr_text":    text[:8000],
            "parsed_stations": json.dumps(rows),
            "page_count":      1,
        }).execute()
        return True
    except Exception:
        return False


def _render_ocr_learning(model, driver_id: Optional[str] = None) -> None:
    """
    OCR-oppimisosio: kamera tai tiedostolataus.
    Tukee: kuva (jpg/png), tekstitiedosto (txt/csv).
    """
    st.markdown(
        '<div class="stat-title">LATAA DATA MALLILLE</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Ota kuva valitysnaytosta tai lataa txt-tiedosto. "
        "Malli lukee datan ja oppii siita."
    )

    tab_cam, tab_file = st.tabs(["Kamera", "Tiedosto"])

    # ── KAMERA ────────────────────────────────────────────────────────
    with tab_cam:
        st.caption("Ota kuva valitysnayton listanakymasta.")
        cam_img = st.camera_input(
            "Kuvaa nakytto",
            key="ocr_camera",
            label_visibility="collapsed",
        )
        if cam_img is not None:
            image_bytes = cam_img.getvalue()
            with st.spinner("Luetaan kuvaa..."):
                text = _run_ocr(image_bytes)

            if text and not text.startswith("OCR virhe"):
                rows = _parse_ocr_to_rows(text)
                if rows:
                    import pandas as pd
                    st.success(f"Tunnistettu {len(rows)} riviä")
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )
                    if st.button("Tallenna malliin", key="btn_save_cam_ocr"):
                        saved = _save_ocr_to_db(
                            text, rows, driver_id, source_name="kamera"
                        )
                        if saved:
                            st.success("Tallennettu tietokantaan!")
                        # Opeta myos River-malli riveista
                        try:
                            for row in rows:
                                features = DemandFeatures()
                                demand = float(row.get("k_plus", 0) + row.get("t_plus", 0))
                                if demand > 0:
                                    model.learn(features, demand)
                            st.info(f"River-malli paivitetty. Opetusnaytelma: {model.trained_samples}")
                        except Exception:
                            pass
                else:
                    st.warning("Tekstia tunnistettu mutta ei rivirakennetta. Raaka teksti:")
                    st.text_area("OCR-tulos", text[:1000], height=150, key="ocr_raw_cam")
            elif text.startswith("OCR virhe"):
                st.error(text)
            else:
                st.warning("Kuvasta ei tunnistettu tekstia.")

    # ── TIEDOSTO ──────────────────────────────────────────────────────
    with tab_file:
        st.caption("Lataa kuva (jpg/png) tai tekstitiedosto (txt/csv).")
        uploaded = st.file_uploader(
            "Valitse tiedosto",
            type=["jpg", "jpeg", "png", "txt", "csv"],
            key="ocr_file_upload",
            label_visibility="collapsed",
        )
        if uploaded is not None:
            file_bytes = uploaded.read()
            fname      = uploaded.name.lower()

            if fname.endswith((".jpg", ".jpeg", ".png")):
                # Kuvatiedosto -> OCR
                with st.spinner("Luetaan kuvaa..."):
                    text = _run_ocr(file_bytes)
                source_type = "image"
            else:
                # Tekstitiedosto -> suora luku
                try:
                    text = file_bytes.decode("utf-8", errors="replace")
                except Exception:
                    text = ""
                source_type = "txt"

            if text:
                rows = _parse_ocr_to_rows(text)
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Riveja tunnistettu", len(rows))
                with col2:
                    st.metric("Merkkia", len(text))

                if rows:
                    import pandas as pd
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )

                with st.expander("Nayta raaka teksti", expanded=False):
                    st.text_area(
                        "Tunnistettu teksti",
                        text[:2000],
                        height=200,
                        key="ocr_raw_file",
                    )

                if st.button("Tallenna malliin", key="btn_save_file_ocr"):
                    saved = _save_ocr_to_db(
                        text, rows, driver_id, source_name=uploaded.name
                    )
                    if saved:
                        st.success("Tallennettu tietokantaan!")
                    try:
                        for row in rows:
                            features = DemandFeatures()
                            demand = float(row.get("k_plus", 0) + row.get("t_plus", 0))
                            if demand > 0:
                                model.learn(features, demand)
                        st.info(f"River-malli paivitetty. Opetusnaytelma: {model.trained_samples}")
                    except Exception:
                        pass
            else:
                st.warning("Tiedostosta ei saatu tekstia.")


# ---------------------------------------------------------------------------
# PAARUNKTIO
# ---------------------------------------------------------------------------

def render_stats_tab(
    agent_results: list,
    driver_id: Optional[str] = None,
) -> None:
    st.markdown(STATS_CSS, unsafe_allow_html=True)

    if not agent_results:
        st.info("Ei agenttidata saatavilla.")
        return

    # Junat
    render_train_section(agent_results)

    # Agenttiosiot
    for agent_name in [
        "WeatherAgent", "FerryAgent", "DisruptionAgent",
        "SocialMediaAgent", "EventsAgent", "FlightAgent",
    ]:
        result = _get_result(agent_results, agent_name)
        if result and len(getattr(result, "signals", [])) > 0:
            render_agent_section(agent_name, result)

    # Oppimisosio
    st.divider()
    render_learning_section(agent_results, driver_id)
