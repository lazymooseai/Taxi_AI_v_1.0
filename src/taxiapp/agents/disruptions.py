"""
disruptions.py - HSL + Fintraffic häiriöagentti
Helsinki Taxi AI | KRIITTISIN agentti - päivittyy 2 min välein (ttl=120)
"""
from __future__ import annotations
import re, logging
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

# RSS-lähteet
SOURCES = [
    {"name": "HSL", "url": "https://www.hsl.fi/fi/rss/hairiot"},
    {"name": "Fintraffic", "url": "https://liikennetilanne.fintraffic.fi/rss"},
]

# Häiriösanakirja - avainsana -> (urgency, score_delta, label)
DISRUPTION_KEYWORDS = [
    (["lakko", "strike"], 10, 40.0, " LAKKO"),
    (["metro seisoo", "metro ei liikennöi"], 10, 35.0, " METRO POIKKI"),
    (["juna ei liikennöi", "junat seisovat"], 9, 35.0, " JUNAT POIKKI"),
    (["myöhässä yli 30", "delay over 30"], 8, 25.0, " JUNA >30MIN MYÖHÄSSÄ"),
    (["myrskyvaroitus", "myrsky"], 8, 22.0, " MYRSKYVAROITUS"),
    (["metro häiriö", "metro myöhästyy"], 7, 20.0, " METRO HÄIRIÖ"),
    (["raitiovaunu häiriö", "ratikka poikki"], 7, 18.0, " RAITIOVAUNU HÄIRIÖ"),
    (["bussikorvaus", "korvaava bussi"], 6, 15.0, " BUSSIKORVAUS"),
    (["juna myöhässä", "train delayed"], 5, 12.0, " JUNA MYÖHÄSSÄ"),
    (["vähäinen häiriö", "minor delay"], 4, 8.0, " LIEVÄ HÄIRIÖ"),
    (["häiriö", "disruption"], 3, 7.0, " HÄIRIÖ"),
]

AREA_KEYWORDS = {
    "Rautatieasema": ["rautatieasema", "helsingin asema", "hki asema"],
    "Pasila": ["pasila", "pasilan"],
    "Tikkurila": ["tikkurila", "dickursby"],
    "Lentokenttä": ["lentokenttä", "helsinki-vantaa", "vantaa"],
    "Kamppi": ["kamppi", "kampen"],
}

class _DisruptionItem:
    def __init__(self, title, summary, published, link, source):
        self.title = title or ""
        self.summary = summary or ""
        self.published = published or datetime.now(timezone.utc)
        self.link = link or ""
        self.source = source
        self._text = f"{self.title} {self.summary}".lower()

    def classify(self):
        best_urgency, best_score, best_reason = 1, 3.0, " Häiriöilmoitus"
        for keywords, urgency, score, label in DISRUPTION_KEYWORDS:
            for kw in keywords:
                if kw in self._text:
                    if urgency > best_urgency:
                        best_urgency = urgency
                        best_score = score
                        best_reason = f"{label}: {self.title[:60]}"
                    break
        return best_urgency, best_score, best_reason

    def affected_areas(self):
        found = []
        for area_name, keywords in AREA_KEYWORDS.items():
            for kw in keywords:
                if kw in self._text:
                    if area_name not in found:
                        found.append(area_name)
                    break
        return found if found else ["Rautatieasema"]

    def to_signals(self):
        urgency, score, reason = self.classify()
        areas = self.affected_areas()
        expires = datetime.now(timezone.utc) + timedelta(minutes=30)
        return [Signal(area=area, score_delta=score, reason=reason, 
                      urgency=urgency, expires_at=expires, 
                      source_url=self.link or self.source)
                for area in areas if area in AREAS]

def _parse_rss(xml_text, source_name):
    if HAS_FEEDPARSER:
        feed = feedparser.parse(xml_text)
        return [_DisruptionItem(e.get("title", ""), e.get("summary", ""),
                               None, e.get("link", ""), source_name)
                for e in feed.entries]

    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL):
        title = _re_tag(block, "title")
        summary = _re_tag(block, "description")
        link = _re_tag(block, "link")
        if title or summary:
            items.append(_DisruptionItem(title, summary, None, link, source_name))
    return items

def _re_tag(text, tag):
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    content = m.group(1)
    content = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", content, flags=re.DOTALL)
    content = re.sub(r"<[^>]+>", " ", content)
    return content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()

def _dedup_signals(signals):
    by_area = {}
    for sig in signals:
        if sig.area not in by_area:
            by_area[sig.area] = sig
        else:
            ex = by_area[sig.area]
            if sig.urgency >= ex.urgency:
                by_area[sig.area] = Signal(area=sig.area,
                    score_delta=ex.score_delta + sig.score_delta,
                    reason=sig.reason, urgency=sig.urgency,
                    expires_at=max(sig.expires_at, ex.expires_at),
                    source_url=sig.source_url)
    return list(by_area.values())

class DisruptionAgent(BaseAgent):
    name = "DisruptionAgent"
    ttl = 120

    async def fetch(self) -> AgentResult:
        all_items, errors = [], []
        raw = {"sources": []}

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0),
          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, follow_redirects=True) as client:

            for source in SOURCES:
                try:
                    resp = await client.get(source["url"])
                    resp.raise_for_status()
                    items = _parse_rss(resp.text, source["name"])
                    all_items.extend(items)
                    raw["sources"].append({"name": source["name"], "count": len(items)})
                except Exception as e:
                    errors.append(f"{source['name']}: {str(e)}")

        if not all_items:
            return self._error(f"Kaikki lähteet epäonnistuivat: {'; '.join(errors)}")

        fresh = [i for i in all_items 
                if (datetime.now(timezone.utc) - i.published).total_seconds() < 7200]
        signals = []
        for item in fresh:
            signals.extend(item.to_signals())

        signals = _dedup_signals(signals)
        signals.sort(key=lambda s: s.urgency, reverse=True)

        raw.update({"total_items": len(all_items), "fresh": len(fresh),
                   "signals": len(signals), "errors": errors})

        logger.info(f"DisruptionAgent: {len(fresh)} tuoretta -> {len(signals)} signaalia")
        return self._ok(signals, raw_data=raw)
