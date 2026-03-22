# events.py — KORJAUKSET
# =====================================================
# KOHTA #6: 2 hel.fi RSS-URLia 404 Not Found
# =====================================================

EVENT_SOURCES = [
    # ❌ VANHA (404 Not Found):
    # {
    #     "name": "Helsinki tapahtumat",
    #     "url": "https://www.hel.fi/fi/rss/tapahtumat",
    # },
    # KORJAUS: Aseta enabled=False (MyHelsinki + Liput.fi toimivat)
    
    {
        "name": "Helsinki tapahtumat (yleinen)",
        "url": "https://www.hel.fi/fi/uutiset/rss",  # ← KORJAUS
        "enabled": True,  # VALINNAINEN: jos haluat hel.fi-uutisia
    },
    
    {
        "name": "MyHelsinki events",
        "url": "https://www.myhelsinki.fi/en/events",  # 301->302->200 ✓
        "enabled": True,
    },
    
    {
        "name": "Liput.fi events",
        "url": "https://www.liput.fi/",
        "enabled": True,
    },
    
    # ❌ VANHA (404 Not Found):
    # {
    #     "name": "Helsinki urheilu",
    #     "url": "https://www.hel.fi/fi/rss/urheilu",
    # },
    # KORJAUS: Poista tai aseta enabled=False
    
    {
        "name": "Eduskunta events",  # Kokoukset, istunnot
        "url": "https://www.eduskunta.fi/EN/RSS",
        "enabled": False,  # Vain mikäli halutaan poliittiset tapahtumat
    },
]

# YHTEENVETO:
# ✓ MyHelsinki (301->302->200) toimii
# ✓ Liput.fi (200) toimii
# ✗ hel.fi/rss/tapahtumat (404)
# ✗ hel.fi/rss/urheilu (404)
# ✓ Eduskunta (200, mutta erikoistunut)
