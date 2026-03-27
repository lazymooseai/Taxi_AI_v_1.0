"""
stations.py - Valitysasemien data
Helsinki Taxi AI v2.0

Lahde: Tolpat_ja_ruudut_.txt
Kayttaa OCRDispatchAgent asemien tunnistamiseen.

Sarakkeet valitysnaytossa:
  K+   = Historiadata: Kavelykyydit viikko sitten (seuraava 30min)
  T+   = Historiadata: Tilaukset viikko sitten (seuraava 30min)
  K-30 = Reaalidata: Toteutuneet kavelykyydit alle 30min sisalla
  T-30 = Reaalidata: Toteutuneet tilaukset alle 30min sisalla
  Autoja = Reaaliaikainen kalustovahvuus

HUOM: K+ ja T+ ovat historiallista vertailudataa (urgency = 4, ei 6)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Station:
    """Yksittainen valitysasema tai alue."""
    number: int
    name: str
    station_type: str = "alue"  # "alue" tai "tolppa"
    group: str = ""             # Ryhmakoodi (a, c, s, v)


# Kaikki asemat Tolpat_ja_ruudut_ -tiedostosta
STATIONS: dict[int, Station] = {
    0:   Station(0,   "HERNESAARI",        "tolppa"),
    1:   Station(1,   "KAPTEENINKATU",     "tolppa"),
    2:   Station(2,   "ETELARANTA",        "tolppa"),
    3:   Station(3,   "VIISKULMA",         "tolppa"),
    4:   Station(4,   "KAMP",              "tolppa"),
    5:   Station(5,   "UUDENMAANKATU",     "tolppa"),
    6:   Station(6,   "SENAATINTORI",      "tolppa"),
    7:   Station(7,   "HIETALAHTI",        "tolppa"),
    8:   Station(8,   "GRAND MARINA",      "tolppa"),
    9:   Station(9,   "H KATAJANOKKA",     "tolppa"),
    10:  Station(10,  "KAIVOPUISTO",       "tolppa"),
    11:  Station(11,  "RUOHOLAHTI",        "tolppa"),
    12:  Station(12,  "KRUUNUNHAKA",       "tolppa"),
    13:  Station(13,  "KAISANIEMI",        "tolppa"),
    14:  Station(14,  "RAUTATIENTORI",     "tolppa"),
    15:  Station(15,  "LAUTTASAARI P",     "tolppa"),
    19:  Station(19,  "SEASIDE",           "tolppa"),
    20:  Station(20,  "KARHUPUISTO",       "tolppa"),
    21:  Station(21,  "EROTTAJA",          "tolppa"),
    22:  Station(22,  "BRAHENKENTTA",      "tolppa"),
    23:  Station(23,  "MARSKI",            "tolppa"),
    24:  Station(24,  "SORNAINEN",         "tolppa"),
    25:  Station(25,  "KALASATAMA",        "tolppa"),
    26:  Station(26,  "ALPPILA",           "tolppa"),
    27:  Station(27,  "LINNANMAKI",        "tolppa"),
    28:  Station(28,  "VALLILA",           "tolppa"),
    29:  Station(29,  "MESSUKESKUS",       "tolppa"),
    32:  Station(32,  "MAUNULA",           "tolppa"),
    33:  Station(33,  "METSALA",           "tolppa"),
    34:  Station(34,  "KAPYLA",            "tolppa"),
    35:  Station(35,  "LASIPALATSI",       "tolppa"),
    36:  Station(36,  "OULUNKYLA",         "tolppa"),
    38:  Station(38,  "TOUKOLA",           "tolppa"),
    39:  Station(39,  "ELIELINAUKIO",      "tolppa"),
    40:  Station(40,  "PIHLAJAMAKI",       "tolppa"),
    41:  Station(41,  "MUSEOKATU",         "tolppa"),
    42:  Station(42,  "PUKINMAKI",         "tolppa"),
    43:  Station(43,  "MEHILAINEN",        "tolppa"),
    44:  Station(44,  "ALA-MALMI",         "tolppa"),
    45:  Station(45,  "TOOLONTORI",        "tolppa"),
    46:  Station(46,  "YLA-MALMI",         "tolppa"),
    47:  Station(47,  "CROWNE PLAZA",      "tolppa"),
    48:  Station(48,  "SILTAMAKI",         "tolppa"),
    49:  Station(49,  "SCANDIC PARK",      "tolppa"),
    50:  Station(50,  "PUISTOLA",          "tolppa"),
    51:  Station(51,  "MESSUKESKUS",       "tolppa"),
    52:  Station(52,  "TOIVONKATU",        "tolppa"),
    53:  Station(53,  "MEILAHTI",          "tolppa"),
    54:  Station(54,  "KULOSAARI",         "tolppa"),
    55:  Station(55,  "SAIRAALAT",         "tolppa"),
    56:  Station(56,  "HERTTONIEMI",       "tolppa"),
    57:  Station(57,  "RUSKEASUO",         "tolppa"),
    58:  Station(58,  "HERTTON. SAIRAALA", "tolppa"),
    59:  Station(59,  "KAMPPI",            "tolppa"),
    60:  Station(60,  "ROIHUVUORI",        "tolppa"),
    61:  Station(61,  "KRUUNUVUORI",       "tolppa"),
    62:  Station(62,  "LAAJASALO",         "tolppa"),
    63:  Station(63,  "JOLLAS",            "tolppa"),
    64:  Station(64,  "ITAKESKUS",         "tolppa"),
    65:  Station(65,  "MUNKKINIEMI",       "tolppa"),
    66:  Station(66,  "MYLLYPURO",         "tolppa"),
    67:  Station(67,  "MUNKKIVUORI",       "tolppa"),
    68:  Station(68,  "KONTULA",           "tolppa"),
    70:  Station(70,  "MELLUNMAKI",        "tolppa"),
    71:  Station(71,  "PITAJANMAKI",       "tolppa"),
    72:  Station(72,  "VARTIOKYLA",        "tolppa"),
    73:  Station(73,  "KONALA",            "tolppa"),
    74:  Station(74,  "VUOSAARI",          "tolppa"),
    75:  Station(75,  "MAISTRAATINPORTTI", "tolppa"),
    77:  Station(77,  "ILMALA",            "tolppa"),
    79:  Station(79,  "VEIKKAUS AREENA",   "tolppa"),
    80:  Station(80,  "PALOHEINA SAHKO",   "tolppa"),
    81:  Station(81,  "ETELA-HAAGA",       "tolppa"),
    85:  Station(85,  "LASSILA",           "tolppa"),
    86:  Station(86,  "ITA-PAKILA",        "tolppa"),
    87:  Station(87,  "KANNELMAKI",        "tolppa"),
    88:  Station(88,  "MALMINKARTANO",     "tolppa"),
    96:  Station(96,  "SIMONKENTTA",       "tolppa"),
    98:  Station(98,  "HANSATERMINAALI",   "tolppa"),
    99:  Station(99,  "OSTERSUNDOM",       "tolppa"),
    212: Station(212, "OTANIEMI",          "tolppa"),
    214: Station(214, "TAPIOLA",           "tolppa"),
    216: Station(216, "WESTEND",           "tolppa"),
    218: Station(218, "KEILANIEMI",        "tolppa"),
    222: Station(222, "HAUKILAHTI",        "tolppa"),
    224: Station(224, "OLARINLUOMA",       "tolppa"),
    226: Station(226, "MANKKAA",           "tolppa"),
    228: Station(228, "TAPIOLA P",         "tolppa"),
    230: Station(230, "NIITTYKUMPU",       "tolppa"),
    232: Station(232, "MATINKYLA",         "tolppa"),
    236: Station(236, "OLARI",             "tolppa"),
    238: Station(238, "SUOMENOJA",         "tolppa"),
    242: Station(242, "SOUKKA",            "tolppa"),
    244: Station(244, "ESPOONLAHTI",       "tolppa"),
    246: Station(246, "KIVENLAHTI",        "tolppa"),
    248: Station(248, "LATOKASKI",         "tolppa"),
    251: Station(251, "KALASATAMA SAHKO",  "tolppa"),
    252: Station(252, "SELLO",             "tolppa"),
    254: Station(254, "LAKKITORI",         "tolppa"),
    258: Station(258, "LAAJALAHTI",        "tolppa"),
    262: Station(262, "KILO",              "tolppa"),
    264: Station(264, "KAUNIAINEN",        "tolppa"),
    268: Station(268, "KARAPORTTI",        "tolppa"),
    274: Station(274, "ESPOONTORI",        "tolppa"),
    276: Station(276, "ESPOON KESKUS",     "tolppa"),
    278: Station(278, "KAUKLAHTI",         "tolppa"),
    282: Station(282, "JORVIN SAIR",       "tolppa"),
    284: Station(284, "JARVENRERA",        "tolppa"),
    292: Station(292, "JUVANMALMI",        "tolppa"),
    422: Station(422, "TIKKURILA",         "tolppa"),
    424: Station(424, "SIMONKYLA",         "tolppa"),
    428: Station(428, "VIERTOLA",          "tolppa"),
    432: Station(432, "KOIVUKYLA",         "tolppa"),
    434: Station(434, "KORSO",             "tolppa"),
    436: Station(436, "LEINELA",           "tolppa"),
    440: Station(440, "KERAILY LENTOAS.",  "tolppa"),
    444: Station(444, "VEROMIES",          "tolppa"),
    448: Station(448, "JUMBO",             "tolppa"),
    449: Station(449, "YLASTO",            "tolppa"),
    450: Station(450, "AVIAPOLIS",         "tolppa"),
    451: Station(451, "KAIVOKSELA",        "tolppa"),
    452: Station(452, "MYYRMAKI",          "tolppa"),
    454: Station(454, "MARTINLAAKSO",      "tolppa"),
    456: Station(456, "PAHKINARINNE",      "tolppa"),
    458: Station(458, "PETIKKO",           "tolppa"),
    462: Station(462, "VIINIKKALA",        "tolppa"),
    466: Station(466, "KIVISTO",           "tolppa"),
}


def get_station(number: int) -> Optional[Station]:
    """Palauta asema numeron perusteella."""
    return STATIONS.get(number)


def find_station_by_name(name: str) -> Optional[Station]:
    """Etsi asema nimella (case-insensitive osuma)."""
    name_up = name.upper().strip()
    for station in STATIONS.values():
        if station.name == name_up or name_up in station.name:
            return station
    return None
