# social_media.py — KORJAUKSET
# =====================================================
# KOHTA #3: 3 rikkinäistä RSS-URLia
# =====================================================

# KORJAUS 1: YLE_HELSINKI publisherId epäkelvollinen
NEWSSOURCES = [
    {
        "name": "Yle Helsinki",
        "url": "https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_HELSINKI",
        "weight": 1.2,
        "enabled": False,  # ← KORJAUS: Disable (410 Bad Request)
    },
    {
        "name": "Yle Uutiset",
        "url": "https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_UUTISET",
        "weight": 1.0,
        "enabled": True,  # Tämä toimii ✓
    },
    {
        "name": "MTV Uutiset",
        "url": "https://www.mtvuutiset.fi/rss/uutiset.rss",
        "weight": 0.9,
        "enabled": True,
    },
    {
        "name": "Ilta-Sanomat",
        "url": "https://www.is.fi/rss/tuoreimmat/",  # ← KORJAUS: Trailing slash
        "weight": 0.8,
        "enabled": True,
    },
    {
        "name": "Iltalehti",
        "url": "https://www.iltalehti.fi/rss/",  # ← KORJAUS: Hakemiston juuri
        "weight": 0.8,
        "enabled": True,
    },
]
