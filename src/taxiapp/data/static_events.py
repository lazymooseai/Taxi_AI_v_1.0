"""
static_events.py - Staattinen tapahtumatietopankki
Helsinki Taxi AI v2.0

Lahde: Tapahtumat_2026_2.pdf
Sisaltaa operatiiviset URL-lahteet ja kapasiteettitiedot
koko vuoden tapahtumapaikoille.

EventsAgent kayttaa tata fallback-tietona kun live-data ei saatavilla.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Venue:
    """Tapahtumapaikka ja sen metatiedot."""
    name: str
    url: str
    area: str
    capacity: Optional[int] = None
    category: str = "culture"
    dispatch_station: Optional[int] = None
    notes: str = ""


# ==============================================================
# MERILIIKENNE
# ==============================================================

SEA_VENUES: list[Venue] = [
    Venue(
        name="Averio laivaliikenteen tilannekuva",
        url="https://www.averio.fi/laivat",
        area="Etelaesatama",
        category="ferries",
        notes="Datahairio: klo 00:30 saapuva alus naytetaan vaarin",
    ),
    Venue(
        name="Helsingin Satama matkustajalaivat",
        url=(
            "https://www.portofhelsinki.fi/matkustajille"
            "/matkustajatietoa/lahtevat-ja-saapuvat-matkustajalaivat/"
        ),
        area="Etelaesatama",
        category="ferries",
    ),
    Venue(
        name="Vuosaari rahtisatama",
        url=(
            "https://www.portofhelsinki.fi/en/professionals"
            "/information-for-port-users/vuosaaritoday/"
        ),
        area="Hansaterminaali",
        category="ferries",
        notes="Kayta vain rahtisataman keikassa",
    ),
]

# ==============================================================
# RAIDE- JA LENTOLIIKENNE
# ==============================================================

TRANSPORT_VENUES: list[Venue] = [
    Venue(
        name="VR Poikkeustilanteet",
        url="https://www.vr.fi/radalla/poikkeustilanteet",
        area="Rautatieasema",
        category="trains",
        notes="Tarkista aina poikkeuksellisella saalla",
    ),
    Venue(
        name="VR Helsinki saapuvat kaukojunat",
        url=(
            "https://www.vr.fi/radalla"
            "?station=HKI&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22"
            "%3A%22Long-distance%22%7D"
        ),
        area="Rautatieasema",
        category="trains",
        dispatch_station=14,
    ),
    Venue(
        name="VR Pasila saapuvat kaukojunat",
        url=(
            "https://www.vr.fi/radalla"
            "?station=PSL&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22"
            "%3A%22Long-distance%22%7D"
        ),
        area="Pasila",
        category="trains",
        dispatch_station=29,
    ),
    Venue(
        name="VR Tikkurila saapuvat kaukojunat",
        url=(
            "https://www.vr.fi/radalla"
            "?station=TKL&direction=ARRIVAL"
            "&stationFilters=%7B%22trainCategory%22"
            "%3A%22Long-distance%22%7D"
        ),
        area="Tikkurila",
        category="trains",
        dispatch_station=422,
    ),
    Venue(
        name="Helsinki-Vantaa saapuvat lennot",
        url=(
            "https://www.finavia.fi/fi/lentoasemat"
            "/helsinki-vantaa/lennot?tab=arr"
        ),
        area="Lentokentta",
        category="airport",
        dispatch_station=440,
    ),
    Venue(
        name="HSL Hairiotiedotteet",
        url="https://www.hsl.fi/aikataulut-ja-reitit/hairiot",
        area="Rautatieasema",
        category="disruptions",
        notes="Metro, raitiovaunu, bussit",
    ),
]

# ==============================================================
# TAPAHTUMALOGISTIIKKA
# ==============================================================

EVENT_VENUES: list[Venue] = [
    Venue(
        name="Messukeskus",
        url="https://www.messukeskus.com/kavijalle/tapahtumat/tapahtumakalenteri/",
        area="Pasila",
        capacity=15000,
        category="culture",
        dispatch_station=29,
        notes="Tarkista paattymisajat - ihmiset lahtevat ovien sulkeutuessa",
    ),
    Venue(
        name="Olympiastadion",
        url="https://www.olympiastadion.fi/tapahtumat/",
        area="Olympiastadion",
        capacity=36000,
        category="sports",
        dispatch_station=52,
    ),
    Venue(
        name="Finlandia-talo",
        url="https://www.finlandiatalo.fi/tapahtumakalenteri/",
        area="Rautatieasema",
        capacity=1700,
        category="culture",
        dispatch_station=39,
    ),
    Venue(
        name="Kaapelitehdas",
        url="https://www.kaapelitehdas.fi/tapahtumat",
        area="Laensisatama",
        capacity=3000,
        category="culture",
    ),
    Venue(
        name="Stadissa.fi tilannekuva",
        url="https://stadissa.fi/",
        area="Kamppi",
        category="culture",
    ),
]

# ==============================================================
# KULTTUURI & VIP
# ==============================================================

CULTURE_VENUES: list[Venue] = [
    Venue(
        name="Helsingin Suomalainen Klubi",
        url="https://tapahtumat.klubi.fi/tapahtumat/",
        area="Kamppi",
        capacity=300,
        category="culture",
        notes="Kansakoulukuja 3, Kamppi. Yritysjohto.",
    ),
    Venue(
        name="Svenska Klubben",
        url="https://klubben.fi/start/program/",
        area="Katajanokka",
        capacity=200,
        category="culture",
        notes="Maurinkatu 6, Kruununhaka. Korkeaprofiilinen.",
    ),
    Venue(
        name="Kaupunginteatteri",
        url="https://hkt.fi/kalenteri/",
        area="Rautatieasema",
        capacity=900,
        category="culture",
    ),
    Venue(
        name="Kansallisooppera",
        url="https://oopperabaletti.fi/ohjelmisto-ja-liput/",
        area="Rautatieasema",
        capacity=1340,
        category="culture",
    ),
    Venue(
        name="Musiikkitalo",
        url="https://www.musiikkitalo.fi/tapahtumat/",
        area="Rautatieasema",
        capacity=1700,
        category="culture",
        dispatch_station=39,
    ),
    Venue(
        name="Kansallisteatteri",
        url="https://kansallisteatteri.fi/esityskalenteri/",
        area="Rautatieasema",
        capacity=700,
        category="culture",
    ),
    Venue(
        name="Tavastia",
        url="https://tavastiaklubi.fi/fi_FI/ohjelma",
        area="Kamppi",
        capacity=900,
        category="concerts",
    ),
]

# ==============================================================
# URHEILU
# ==============================================================

SPORTS_VENUES: list[Venue] = [
    Venue(
        name="HIFK kotiottelut (Liiga/Nordis)",
        url=(
            "https://liiga.fi/fi/ohjelma"
            "?kausi=2025-2026&sarja=runkosarja"
            "&joukkue=hifk&kotiVieras=koti"
        ),
        area="Rautatieasema",
        capacity=13500,
        category="sports",
        notes="Nordis. Poistuma-aika 2,5h kiekon putoamisesta.",
    ),
    Venue(
        name="Kiekko-Espoo (Metro Areena)",
        url=(
            "https://liiga.fi/fi/ohjelma"
            "?kausi=2025-2026&sarja=runkosarja"
            "&joukkue=k-espoo&kotiVieras=koti"
        ),
        area="Kamppi",
        capacity=8000,
        category="sports",
    ),
    Venue(
        name="Jokerit (Mestis)",
        url="https://jokerit.fi/ottelut",
        area="Rautatieasema",
        capacity=13500,
        category="sports",
    ),
    Venue(
        name="Veikkausliiga jalkapallo",
        url="https://veikkausliiga.com/tilastot/2025/veikkausliiga/ottelut/",
        area="Olympiastadion",
        capacity=10770,
        category="sports",
        dispatch_station=52,
    ),
]

# ==============================================================
# SAA & INFRA LINKIT
# ==============================================================

WEATHER_LINKS: list[Venue] = [
    Venue(
        name="FMI Sadetutka Etela-Suomi",
        url=(
            "https://www.ilmatieteenlaitos.fi"
            "/sade-ja-pilvialueet?area=etela-suomi"
        ),
        area="Rautatieasema",
        category="weather",
    ),
    Venue(
        name="FMI Paikallissaa Helsinki",
        url="https://www.ilmatieteenlaitos.fi/paikallissaa/helsinki",
        area="Rautatieasema",
        category="weather",
    ),
    Venue(
        name="Fintraffic Liikennetilanne",
        url=(
            "https://liikennetilanne.fintraffic.fi"
            "/?x=385557.5&y=6672322.0&z=10"
        ),
        area="Rautatieasema",
        category="disruptions",
    ),
]


# ==============================================================
# KOOTTU LISTA
# ==============================================================

ALL_VENUES: list[Venue] = (
    SEA_VENUES
    + TRANSPORT_VENUES
    + EVENT_VENUES
    + CULTURE_VENUES
    + SPORTS_VENUES
    + WEATHER_LINKS
)


def venues_by_category(category: str) -> list[Venue]:
    """Hae kaikki paikat kategorian mukaan."""
    return [v for v in ALL_VENUES if v.category == category]


def venues_by_area(area: str) -> list[Venue]:
    """Hae kaikki paikat alueen mukaan."""
    return [v for v in ALL_VENUES if v.area == area]
