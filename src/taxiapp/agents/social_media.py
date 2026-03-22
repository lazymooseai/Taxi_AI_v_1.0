"""
social_media.py - Uutis-agentti (Yle, HS, MTV, IS)
Helsinki Taxi AI | Päivittyy 5 min välein (ttl=300)
"""
from __future__ import annotations
import logging, re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

from src.taxiapp.base_agent import BaseAgent, AgentResult, Signal
from src.taxiapp.areas import AREAS

logger = logging.getLogger(__name__)

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

NEWS_SOURCES = [
    {"name": "Yle", "url": "https://feeds.yle.fi/uutiset/v1/recent.rss?publisherIds=YLE_UUTISET", "weight": 1.2},
    {"name": "MTV", "url": "https://www.mtvuutiset.fi/rss/uutiset.rss", "weight": 0.9},
    {"name": "IS", "url": "https://www.is.fi/rss/tuoreimmat.xml", "weight": 0.8},
]

NEWS_SIGNALS = [
    (["lakko", "strike"], 9, 35.0, None),
    (["onnettomuus", "accident"], 9, 30.0, None),
    (["mielenosoitus", "protesti"], 7, 20.0, "Rautatieasema"),
    (["metro", "juna myöhässä"], 7, 22.0, None),
    (["myrsky", "rankkasade"], 5, 14.0, None),
    (["konsertti", "tapahtuma"], 5, 12.0, None),
    (["helsingissä", "helsinki"], 3, 6.0, None),
]

@dataclass
class NewsItem:
    headline: str
    source: str
    source_url: str
    published_at: datetime
    weight: float = 1.0

    @property
    def age_minutes(self):
        return (datetime.now(timezone.utc) - self.published_at).total_seconds() / 60

    @property
    def is_fresh(self):
        return self.age_minutes <= 120

    def classify(self):
        text = self.headline.lower()
        best_urgency, best_score, best_area = 1, 2.0, None
        for keywords, urgency, score, area in NEWS_SIGNALS:
            for kw in keywords:
                if kw in text:
                    if urgency > best_urgency:
                        best_urgency = urgency
                        best_score = score * self.weight
                        best_area = area
                    break
        return best_urgency, round(best_score, 1), best_area

    def affected_area(self):
        _, _, area = self.classify()
        return area if area and area in AREAS else "Rautatieasema"

def _parse_news_rss(xml, source_name, weight):
    items = []
    if HAS_FEEDPARSER:
        feed = feedparser.parse(xml)
        for entry in feed.entries[:20]:
            items.append(NewsItem(
                headline=entry.get("title", ""),
                source=source_name,
                source_url=entry.get("link", ""),
                published_at=datetime.now(timezone.utc),
                weight=weight))
    else:
        for block in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL):
            title = _re_tag(block, "title")
            link = _re_tag(block, "link")
            if title:
                items.append(NewsItem(headline=title, source=source_name,
                                     source_url=link, published_at=datetime.now(timezone.utc),
                                     weight=weight))
    return items

def _re_tag(text, tag):
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    content = re.sub(r"<[^>]+>", "", m.group(1))
    return content.replace("&amp;", "&").strip()

class SocialMediaAgent(BaseAgent):
    name = "SocialMediaAgent"
    ttl = 300

    async def fetch(self) -> AgentResult:
        all_items = []
        errors = []

    
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, follow_redirects=True) as client:

            for source in NEWS_SOURCES:
                try:
                    resp = await client.get(source["url"])
                    resp.raise_for_status()
                    items = _parse_news_rss(resp.text, source["name"], source.get("weight", 1.0))
                    all_items.extend(items)
                except Exception as e:
                    errors.append(f"{source['name']}: {str(e)}")

        fresh = [i for i in all_items if i.is_fresh]
        fresh.sort(key=lambda i: -i.age_minutes)
        top_items = fresh[:5]

        signals = []
        for item in top_items:
            urgency, score, _ = item.classify()
            area = item.affected_area()
            age_factor = max(0.3, 1.0 - (item.age_minutes / 120.0))
            final_score = round(score * age_factor, 1)

            reason = f" {item.source}: {item.headline[:60]}"
            signals.append(Signal(area=area, score_delta=final_score,
                                 reason=reason, urgency=urgency,
                                 expires_at=item.published_at + timedelta(hours=2),
                                 source_url=item.source_url))

        signals.sort(key=lambda s: s.urgency, reverse=True)
        raw = {"total": len(fresh), "shown": len(top_items), "signals": len(signals), "errors": errors}

        logger.info(f"SocialMediaAgent: {len(fresh)} uutista -> {len(signals)} signaalia")
        return self._ok(signals, raw_data=raw)
