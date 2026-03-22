# disruptions.py — KORJAUKSET
# =====================================================
# KOHTA #4: HSL RSS 403 Forbidden (molemmat URLt rikki)
# HSL on sulkenut julkiset RSS-syötteet vuonna 2025
# =====================================================

SOURCES = [
    # ❌ VANHA (403 Forbidden):
    # {
    #     "name": "HSL",
    #     "url": "https://www.hsl.fi/fi/rss/hairiot",
    #     "fallback_url": "https://www.hsl.fi/rss",
    # },
    # KORJAUS: Poista HSL-kohta tai aseta enabled=False
    # Digitransit (308 redirect) toimii automaattisesti ✓
    
    {
        "name": "Fintraffic",
        "url": "https://liikennetilanne.fintraffic.fi/rss",
        "fallback_url": "https://liikennetilanne.fintraffic.fi/rss",  # 308 -> toimii ✓
    },
]

# TULEVAISUUS: Jos haluat HSL-häiriöitä, integro Digitransit GraphQL API:
# URL: https://api.digitransit.fi/routing/v1/routers/hsl/index/graphql
# Vaatii: digitransit-subscription-1-api-key header (rekisteröidy: digitransit.fi)
