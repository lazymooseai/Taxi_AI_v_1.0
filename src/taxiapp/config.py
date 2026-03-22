# config.py - Ymparistomuuttujien hallinta Helsinki Taxi AI

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Konfiguraatio Helsinki Taxi AI -sovellukselle."""

    # ===================== Supabase =====================
    supabase_url: Optional[str] = field(
        default_factory=lambda: os.environ.get("SUPABASE_URL")
    )
    supabase_anon_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("SUPABASE_ANON_KEY")
    )
    supabase_service_role_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )

    # ===================== API Keys =====================
    openai_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY")
    )
    finavia_app_id: Optional[str] = field(
        default_factory=lambda: os.environ.get("FINAVIA_APP_ID")
    )
    finavia_app_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("FINAVIA_APP_KEY")
    )

    # ===================== Admin & App =====================
    admin_password: str = field(
        default_factory=lambda: os.environ.get("ADMIN_PASSWORD", "changeme123")
    )
    app_title: str = field(
        default_factory=lambda: os.environ.get("APP_TITLE", "Helsinki Taxi AI")
    )
    debug: bool = field(
        default_factory=lambda: os.environ.get("DEBUG", "false").lower() == "true"
    )
    log_level: str = field(
        default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO").upper()
    )

    # ===================== Rate Limiting =====================
    rate_limit_seconds: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_SECONDS", "5"))
    )

    # ===================== TTL (Cache) =====================
    ttl_disruptions: int = field(
        default_factory=lambda: int(os.environ.get("TTL_DISRUPTIONS", "120"))
    )
    ttl_trains: int = field(
        default_factory=lambda: int(os.environ.get("TTL_TRAINS", "120"))
    )
    ttl_flights: int = field(
        default_factory=lambda: int(os.environ.get("TTL_FLIGHTS", "300"))
    )
    ttl_weather: int = field(
        default_factory=lambda: int(os.environ.get("TTL_WEATHER", "600"))
    )
    ttl_ferries: int = field(
        default_factory=lambda: int(os.environ.get("TTL_FERRIES", "480"))
    )
    ttl_social_media_rss: int = field(
        default_factory=lambda: int(os.environ.get("TTL_SOCIAL_MEDIA_RSS", "300"))
    )
    ttl_social_media_x: int = field(
        default_factory=lambda: int(os.environ.get("TTL_SOCIAL_MEDIA_X", "900"))
    )
    ttl_events: int = field(
        default_factory=lambda: int(os.environ.get("TTL_EVENTS", "1800"))
    )
    ttl_restaurants: int = field(
        default_factory=lambda: int(os.environ.get("TTL_RESTAURANTS", "1800"))
    )

    # ===================== API URLs =====================
    fmi_api_url: str = field(
        default_factory=lambda: os.environ.get(
            "FMI_API_URL", "https://opendata.fmi.fi/wfs"
        )
    )
    digitraffic_rest_url: str = field(
        default_factory=lambda: os.environ.get(
            "DIGITRAFFIC_REST_URL", "https://rata.digitraffic.fi/api/v1"
        )
    )
    finavia_api_url: str = field(
        default_factory=lambda: os.environ.get(
            "FINAVIA_API_URL", "https://api.finavia.fi/flights/public/v0"
        )
    )
    hsl_rss_url: str = field(
        default_factory=lambda: os.environ.get(
            "HSL_RSS_URL", "https://www.hsl.fi/fi/rss/hairiot"
        )
    )
    fintraffic_rss_url: str = field(
        default_factory=lambda: os.environ.get(
            "FINTRAFFIC_RSS_URL", "https://liikennetilanne.fintraffic.fi/rss"
        )
    )
    averio_url: str = field(
        default_factory=lambda: os.environ.get(
            "AVERIO_URL", "https://www.averio.fi"
        )
    )

    # ===================== Locale =====================
    timezone: str = field(
        default_factory=lambda: os.environ.get("TZ", "Europe/Helsinki")
    )

    # ===================== Properties =====================
    @property
    def has_supabase(self) -> bool:
        """Tarkista onko Supabase-konfiguraatio käytettävissä."""
        return bool(self.supabase_url and self.supabase_anon_key)


# Globaali instanssi
config = Config()
