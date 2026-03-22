# config.py — KORJAUKSET
# =====================================================
# KOHTA #2: Supabase API-avaimen validaatio
# KOHTA #5: Digitransit API-avaimen lisäys
# =====================================================

import os
from typing import Optional

class Config:
    """Helsinki Taxi AI -konfiguraatio."""
    
    # == Supabase (Database) =============================
    SUPABASE_URL: str = os.getenv(
        "SUPABASE_URL", 
        "https://himfghlvyvndfpdodzoe.supabase.co"
    )
    
    # KORJAUS #2: Tarkista Streamlit Cloud Secrets-asetukset!
    # Streamlit Cloud -> Settings -> Secrets:
    # SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5..."  ← Korvaa OIKEALLA avaimella
    SUPABASE_KEY: Optional[str] = os.getenv("SUPABASE_KEY", None)
    SUPABASE_SERVICE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_KEY", None)
    
    # DB-operaatioissa käytetään SUPABASE_KEY (anon-avain riittää read/write)
    # Jos pelkät luku-operaatiot: service_role-avain tarpeeton
    
    @classmethod
    def validate_supabase(cls) -> tuple[bool, str]:
        """Validoi Supabase-asetukset ennen käyttöä."""
        if not cls.SUPABASE_URL:
            return False, "SUPABASE_URL puuttuu (config.py tai os.getenv)"
        if not cls.SUPABASE_KEY:
            return False, (
                "SUPABASE_KEY puuttuu. "
                "Lisää Streamlit Cloud Secrets-asetuksiin:\n"
                "  SUPABASE_KEY = 'eyJhbGciOi...'\n"
                "  (Hae https://app.supabase.com/project/[project-id]/settings/api)"
            )
        return True, "Supabase OK"
    
    # == Finavia API ====================================
    FINAVIA_APP_ID: Optional[str] = os.getenv("FINAVIA_APP_ID", None)
    FINAVIA_APP_KEY: Optional[str] = os.getenv("FINAVIA_APP_KEY", None)
    
    # == Digitransit API ================================
    # KORJAUS #5: Lisää Digitransit subscription-avain
    # Rekisteröidy: https://digitransit.fi/en/developers/
    DIGITRANSIT_KEY: Optional[str] = os.getenv("DIGITRANSIT_KEY", None)
    
    @classmethod
    def validate_digitransit(cls) -> tuple[bool, str]:
        """Validoi Digitransit-asetukset (Suomenlinna-lautta, HSL)."""
        if not cls.DIGITRANSIT_KEY:
            return False, (
                "DIGITRANSIT_KEY puuttuu. "
                "Suomenlinna-lauta ja HSL-häiriöt eivät toimu.\n"
                "Rekisteröidy: https://digitransit.fi/en/developers/\n"
                "Lisää Streamlit Secrets:\n"
                "  DIGITRANSIT_KEY = 'your_subscription_key_here'"
            )
        return True, "Digitransit OK"
    
    # == FMI API ========================================
    FMI_API_KEY: Optional[str] = os.getenv("FMI_API_KEY", None)
    
    # == Muut agenttit ==================================
    OPENWEATHER_KEY: Optional[str] = os.getenv("OPENWEATHER_KEY", None)
    
    # == Streamlit settings ==============================
    STREAMLIT_PAGE_CONFIG = {
        "page_title": "Helsinki Taxi AI",
        "page_icon": "🚕",
        "layout": "wide",
        "initial_sidebar_state": "expanded",
    }
    
    DEFAULT_REFRESH_INTERVAL = 30  # sekuntia
    DEFAULT_ALERT_THRESHOLD = 5.0  # score_delta
    
    # == Lokitus =========================================
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# Globaali config-instanssi
config = Config()


if __name__ == "__main__":
    # Validointiajo
    print("=" * 60)
    print("HELSINKI TAXI AI — KONFIGURAATION VALIDOINTI")
    print("=" * 60)
    
    ok_sb, msg_sb = Config.validate_supabase()
    print(f"Supabase:    {'✓' if ok_sb else '✗'} {msg_sb}")
    
    ok_dt, msg_dt = Config.validate_digitransit()
    print(f"Digitransit: {'✓' if ok_dt else '✗'} {msg_dt}")
    
    print("=" * 60)
    if not (ok_sb and ok_dt):
        print("⚠️  KONFIGURAATIO EPÄKOMPLETTI")
        print("    Lisää puuttuvat avaimet Streamlit Cloud Secrets-asetuksiin")
    else:
        print("✓ Kaikki asetukset OK")
