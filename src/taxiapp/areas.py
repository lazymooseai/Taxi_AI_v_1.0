"""
areas.py - Helsinki-alueet ja kategoriat
Helsinki Taxi AI v2.0

AREAS-sanakirja on koko jarjestelman maantieteellinen pohja.
CEO kayttaa tata pisteiden laskemiseen ja korttien luomiseen.

v2.0: Lisatty Hansaterminaali, Suomenlinna, politiikka-kategoria
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ==============================================================
# KATEGORIAT
# ==============================================================

CATEGORIES: dict[str, str] = {
    "trains":      "Junat",
    "airport":     "Lentoasema",
    "ferries":     "Satamat",
    "nightlife":   "Yoelama",
    "concerts":    "Konsertit",
    "sports":      "Urheilu",
    "culture":     "Kulttuuri",
    "business":    "Business",
    "politics":    "Politiikka",
    "disruptions": "Hairiot",
}


# ==============================================================
# AREA - yksittainen alue
# ==============================================================

@dataclass(frozen=True)
class Area:
    name: str
    lat: float
    lon: float
    categories: tuple[str, ...]
    base_score: float = 0.0
    dispatch_stations: tuple[int, ...] = ()  # Valitysaseman numerot

    def has_category(self, category: str) -> bool:
        return category in self.categories

    def distance_km(self, lat: float, lon: float) -> float:
        """Haversine-approksimaatio kilometreissa."""
        import math
        R = 6371.0
        dlat = math.radians(lat - self.lat)
        dlon = math.radians(lon - self.lon)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(self.lat))
             * math.cos(math.radians(lat))
             * math.sin(dlon / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def __str__(self) -> str:
        cats = ", ".join(self.categories)
        return f"{self.name} ({cats})"


# ==============================================================
# AREAS - paasanakirja
# ==============================================================

AREAS: dict[str, Area] = {

    # == Rautatiet =============================================
    "Rautatieasema": Area(
        name="Rautatieasema",
        lat=60.1718, lon=24.9414,
        categories=("trains",),
        base_score=10.0,
        dispatch_stations=(14, 39),
    ),
    "Pasila": Area(
        name="Pasila",
        lat=60.1990, lon=24.9338,
        categories=("trains", "concerts", "sports"),
        base_score=8.0,
        dispatch_stations=(29, 51, 77),
    ),
    "Tikkurila": Area(
        name="Tikkurila",
        lat=60.2924, lon=25.0439,
        categories=("trains", "airport"),
        base_score=6.0,
        dispatch_stations=(422,),
    ),

    # == Lentoasema ===========================================
    "Lentokentta": Area(
        name="Lentokentta",
        lat=60.3172, lon=24.9633,
        categories=("airport",),
        base_score=12.0,
        dispatch_stations=(440, 444, 449, 450),
    ),

    # == Satamat ===============================================
    "Etelaesatama": Area(
        name="Etelaesatama",
        lat=60.1628, lon=24.9522,
        categories=("ferries", "business", "culture"),
        base_score=8.0,
        dispatch_stations=(0, 2, 10),
    ),
    "Laensisatama": Area(
        name="Laensisatama",
        lat=60.1551, lon=24.9196,
        categories=("ferries",),
        base_score=7.0,
        dispatch_stations=(7, 11),
    ),
    "Katajanokka": Area(
        name="Katajanokka",
        lat=60.1648, lon=24.9651,
        categories=("business", "ferries"),
        base_score=7.0,
        dispatch_stations=(8, 9),
    ),
    "Hansaterminaali": Area(
        name="Hansaterminaali",
        lat=60.2085, lon=25.1961,
        categories=("ferries",),
        base_score=4.0,
        dispatch_stations=(98,),
    ),
    "Kauppatori": Area(
        name="Kauppatori",
        lat=60.1674, lon=24.9522,
        categories=("ferries", "business"),
        base_score=9.0,
        dispatch_stations=(6, 12),
    ),
    "Suomenlinna": Area(
        name="Suomenlinna",
        lat=60.1454, lon=24.9881,
        categories=("ferries", "culture"),
        base_score=3.0,
        dispatch_stations=(),
    ),

    # == Yoelama ===============================================
    "Kamppi": Area(
        name="Kamppi",
        lat=60.1685, lon=24.9320,
        categories=("nightlife", "culture", "concerts"),
        base_score=11.0,
        dispatch_stations=(59, 96),
    ),
    "Kallio": Area(
        name="Kallio",
        lat=60.1841, lon=24.9497,
        categories=("nightlife", "concerts"),
        base_score=9.0,
        dispatch_stations=(20, 24, 25),
    ),
    "Hakaniemi": Area(
        name="Hakaniemi",
        lat=60.1791, lon=24.9497,
        categories=("nightlife",),
        base_score=7.0,
        dispatch_stations=(22,),
    ),
    "Erottaja": Area(
        name="Erottaja",
        lat=60.1659, lon=24.9401,
        categories=("business", "nightlife"),
        base_score=8.0,
        dispatch_stations=(21, 23),
    ),

    # == Tapahtumat / urheilu ===================================
    "Messukeskus": Area(
        name="Messukeskus",
        lat=60.2034, lon=24.9396,
        categories=("concerts", "sports"),
        base_score=6.0,
        dispatch_stations=(29, 51),
    ),
    "Olympiastadion": Area(
        name="Olympiastadion",
        lat=60.1878, lon=24.9260,
        categories=("concerts", "sports", "culture"),
        base_score=7.0,
        dispatch_stations=(52,),
    ),

    # == Politiikka ============================================
    "Eduskunta": Area(
        name="Eduskunta",
        lat=60.1726, lon=24.9327,
        categories=("politics", "business"),
        base_score=3.0,
        dispatch_stations=(41,),
    ),

    # == Sairaalat =============================================
    "Meilahti": Area(
        name="Meilahti",
        lat=60.1899, lon=24.9062,
        categories=("business",),
        base_score=5.0,
        dispatch_stations=(53, 55),
    ),
}


# ==============================================================
# ASEMA -> ALUE -KARTOITUS (Tolpat_ja_ruudut_.txt)
# ==============================================================

STATION_TO_AREA: dict[int, str] = {}


def _build_station_map() -> None:
    """Rakenna valitysasema -> AREAS-alue -kartoitus."""
    for area_name, area in AREAS.items():
        for station_id in area.dispatch_stations:
            STATION_TO_AREA[station_id] = area_name


_build_station_map()


def station_to_area(station_id: int) -> Optional[str]:
    """Palauta alueen nimi valitysaseman numeron perusteella."""
    return STATION_TO_AREA.get(station_id)


# ==============================================================
# APUFUNKTIOT
# ==============================================================

def get_area(name: str) -> Optional[Area]:
    """Palauta alue nimella, tai None jos ei loydy."""
    return AREAS.get(name)


def areas_by_category(category: str) -> list[Area]:
    """Kaikki alueet joilla on tietty kategoria."""
    return [a for a in AREAS.values() if a.has_category(category)]


def nearest_area(lat: float, lon: float) -> Area:
    """Lahin alue koordinaateille."""
    return min(AREAS.values(), key=lambda a: a.distance_km(lat, lon))


def areas_within_km(lat: float, lon: float, radius_km: float) -> list[Area]:
    """Kaikki alueet tietyn sateen sisalla."""
    return [
        a for a in AREAS.values()
        if a.distance_km(lat, lon) <= radius_km
    ]


def validate_area_name(name: str) -> bool:
    """Onko aluenimi AREAS-sanakirjassa?"""
    return name in AREAS


def all_area_names() -> list[str]:
    """Kaikki aluenimet listana."""
    return sorted(AREAS.keys())
