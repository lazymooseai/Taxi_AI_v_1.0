# location_service.py -- Reaaliaikainen sijaintipalvelu
# Helsinki Taxi AI
#
# Kayttaa streamlit-geolocation-komponenttia GPS-koordinaattien hakemiseen.
# Laskee haversine-etaisyyden kaikkiin tunnettuihin alueisiin.
#
# Asennus: pip install streamlit-geolocation==0.0.7

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

import streamlit as st

logger = logging.getLogger("taxiapp.location")


# ---------------------------------------------------------------------------
# ALUEET
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Area:
    id: str
    name: str
    lat: float
    lon: float
    radius_km: float = 3.0
    vr_url: str = ""
    priority: int = 1


KNOWN_AREAS: list[Area] = [
    Area(
        id="helsinki_central",
        name="Rautatieasema",
        lat=60.1719, lon=24.9414,
        radius_km=2.5,
        vr_url=(
            "https://www.vr.fi/radalla"
            "?station=HKI&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
        priority=3,
    ),
    Area(
        id="pasila",
        name="Pasila",
        lat=60.1989, lon=24.9340,
        radius_km=2.0,
        vr_url=(
            "https://www.vr.fi/radalla"
            "?station=PSL&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
        priority=2,
    ),
    Area(
        id="tikkurila",
        name="Tikkurila",
        lat=60.2925, lon=25.0440,
        radius_km=3.0,
        vr_url=(
            "https://www.vr.fi/radalla"
            "?station=TKL&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22%3A%22Long-distance%22%7D"
        ),
        priority=2,
    ),
    Area(
        id="airport",
        name="Helsinki-Vantaa",
        lat=60.3172, lon=24.9633,
        radius_km=4.0,
        vr_url="https://www.finavia.fi/fi/lentokentat/helsinki-vantaa/lennot?tab=arr",
        priority=3,
    ),
    Area(id="itakeskus",   name="Itakeskus",    lat=60.2093, lon=25.0793, radius_km=3.0),
    Area(id="espoo_center",name="Espoon keskus", lat=60.2052, lon=24.6557, radius_km=3.0),
    Area(id="myyrmaki",    name="Myyrmaki",      lat=60.2636, lon=24.8577, radius_km=2.5),
    Area(id="korso",       name="Korso",          lat=60.3611, lon=25.0765, radius_km=2.5),
    Area(id="kerava",      name="Kerava",         lat=60.4032, lon=25.1066, radius_km=3.0),
]

AREA_BY_ID: dict[str, Area] = {a.id: a for a in KNOWN_AREAS}


# ---------------------------------------------------------------------------
# HAVERSINE
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# TULOSTYYPIT
# ---------------------------------------------------------------------------

@dataclass
class LocationResult:
    lat: float
    lon: float
    accuracy_m: float
    nearest_area: Optional[Area] = None
    nearest_distance_km: float = 999.0
    areas_by_distance: list[tuple[float, Area]] = field(default_factory=list)


def get_nearest_areas(lat: float, lon: float, top_n: int = 3) -> LocationResult:
    distances: list[tuple[float, Area]] = sorted(
        [(haversine_km(lat, lon, a.lat, a.lon), a) for a in KNOWN_AREAS],
        key=lambda x: x[0],
    )
    result = LocationResult(lat=lat, lon=lon, accuracy_m=0.0, areas_by_distance=distances[:top_n])
    if distances:
        result.nearest_distance_km = distances[0][0]
        result.nearest_area = distances[0][1]
    return result


# ---------------------------------------------------------------------------
# STREAMLIT-KOMPONENTTI
# ---------------------------------------------------------------------------

def render_location_widget(
    ceo_hotspots: list | None = None,
    on_location_change=None,
) -> Optional[LocationResult]:
    try:
        from streamlit_geolocation import streamlit_geolocation  # type: ignore
    except ImportError:
        st.caption("Sijaintipalvelu: pip install streamlit-geolocation")
        return None

    location = streamlit_geolocation()

    # KORJAUS: streamlit_geolocation voi palauttaa str tai None -- hyvaksytaan vain dict
    if not location or not isinstance(location, dict):
        return None

    lat = location.get("latitude")
    lon = location.get("longitude")
    accuracy = location.get("accuracy", 0.0)

    if lat is None or lon is None:
        return None

    try:
        lat = float(lat)
        lon = float(lon)
        accuracy = float(accuracy) if accuracy else 0.0
    except (TypeError, ValueError):
        return None

    full_result = get_nearest_areas(lat, lon)

    loc_result = LocationResult(
        lat=lat,
        lon=lon,
        accuracy_m=accuracy,
        nearest_area=full_result.nearest_area,
        nearest_distance_km=full_result.nearest_distance_km,
        areas_by_distance=full_result.areas_by_distance,
    )

    st.session_state["driver_lat"] = lat
    st.session_state["driver_lon"] = lon
    st.session_state["driver_accuracy_m"] = accuracy
    st.session_state["driver_nearest_area"] = (
        full_result.nearest_area.id if full_result.nearest_area else None
    )

    if on_location_change:
        on_location_change(loc_result)

    if loc_result.nearest_area:
        st.caption(
            "Sijainti: " + loc_result.nearest_area.name
            + " (" + "{:.1f}".format(loc_result.nearest_distance_km) + " km)"
        )

    return loc_result


def get_location_from_session() -> Optional[LocationResult]:
    lat = st.session_state.get("driver_lat")
    lon = st.session_state.get("driver_lon")
    if lat is None or lon is None:
        return None
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None
    accuracy = float(st.session_state.get("driver_accuracy_m", 0.0))
    full_result = get_nearest_areas(lat, lon)
    return LocationResult(
        lat=lat, lon=lon, accuracy_m=accuracy,
        nearest_area=full_result.nearest_area,
        nearest_distance_km=full_result.nearest_distance_km,
        areas_by_distance=full_result.areas_by_distance,
    )


# ---------------------------------------------------------------------------
# CEO-INTEGRAATIO
# ---------------------------------------------------------------------------

def apply_location_boost(
    hotspots: list,
    driver_lat: float,
    driver_lon: float,
    boost_factor: float = 1.5,
    nearby_km: float = 5.0,
) -> list:
    if not hotspots:
        return hotspots
    boosted = []
    for hotspot in hotspots:
        area_id = getattr(hotspot, "area", None)
        area = AREA_BY_ID.get(area_id) if area_id else None
        if area:
            dist_km = haversine_km(driver_lat, driver_lon, area.lat, area.lon)
            if dist_km <= nearby_km:
                proximity_bonus = max(0.0, (nearby_km - dist_km) / nearby_km)
                new_score = hotspot.score * (1 + (boost_factor - 1) * proximity_bonus)
                import dataclasses
                try:
                    hotspot = dataclasses.replace(hotspot, score=new_score)
                except Exception:
                    pass
        boosted.append(hotspot)
    boosted.sort(key=lambda h: getattr(h, "score", 0), reverse=True)
    return boosted


def get_smart_recommendation_text(
    driver_lat: float,
    driver_lon: float,
    active_hotspots: list,
) -> str:
    loc = get_nearest_areas(driver_lat, driver_lon)
    nearest_name = loc.nearest_area.name if loc.nearest_area else "tuntematon"
    dist_str = "{:.1f} km".format(loc.nearest_distance_km)

    if not active_hotspots:
        return "Sijainti: " + nearest_name + " (" + dist_str + ")"

    hotspot_distances: list[tuple[float, str]] = []
    for hs in active_hotspots[:3]:
        hs_area_id = getattr(hs, "area", None)
        hs_area = AREA_BY_ID.get(hs_area_id) if hs_area_id else None
        if hs_area:
            dist = haversine_km(driver_lat, driver_lon, hs_area.lat, hs_area.lon)
            hotspot_distances.append((dist, hs_area.name))

    hotspot_distances.sort(key=lambda x: x[0])

    if hotspot_distances:
        suggestions = " -> ".join(
            name + " (" + "{:.0f}".format(d) + " km)"
            for d, name in hotspot_distances[:2]
        )
        return "Sijainti: " + nearest_name + " -> " + suggestions

    return "Sijainti: " + nearest_name + " (" + dist_str + ")"
