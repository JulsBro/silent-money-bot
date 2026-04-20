"""
Silent Money — Crypto & Finance Daily Digest Bot
Quellen: EN + RU + EU | Ausgabe: Deutsch | Kanal: @silentmoney_feed
5x täglich: 07:00 / 11:00 / 14:30 / 17:00 / 20:00 MSK
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from anthropic import Anthropic

# ─── KONFIGURATION ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY", "")
NEWS_API_KEY        = os.environ.get("NEWS_API_KEY", "")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

SLOT_NAMES = {
    4:  "🌅 Morgen",
    8:  "☀️ Mittag",
    11: "📊 Nachmittag",
    14: "🌆 Abend",
    17: "🌙 Nacht",
}

# ─── MARKTPREISE ──────────────────────────────────────────────────────────────

def fetch_market_snapshot() -> str:
    """BTC, ETH, SOL + Gold + Gesamt-Marktkapitalisierung"""
    try:
        # Krypto-Preise
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "bitcoin,ethereum,solana,pax-gold",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_market_cap": "true",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        # Globale Marktdaten
        g = requests.get("https://api.coingecko.com/api/v3/global", timeout=15).json()
        gdata = g.get("data", {})
        total_mcap = gdata.get("total_market_cap", {}).get("usd", 0)
        btc_dom    = gdata.get("market_cap_percentage", {}).get("btc", 0)

        def fmt(coin, key="usd"):
            p = data.get(coin, {}).get(key, 0)
            c = data.get(coin, {}).get("usd_24h_change", 0)
            arrow = "▲" if c >= 0 else "▼"
            sign  = "+" if c >= 0 else ""
            if p > 1000:
                return f"${p:,.0f}  {arrow}{sign}{c:.1f}%"
            return f"${p:,.2f}  {arrow}{sign}{c:.1f}%"

        mcap_str = f"${total_mcap/1e12:.2f}T" if total_mcap > 1e12 else f"${total_mcap/1e9:.0f}B"

        now_berlin = datetime.utcnow() + timedelta(hours=2)  # CEST (Sommer); Winter: +1
        slot_hour = min(SLOT_NAMES.keys(), key=lambda h: abs(h - now_berlin.hour))
        slot_name = SLOT_NAMES.get(slot_hour, "📊 Update")

        msg = (
            f"💼 <b>SILENT MONEY</b> — {slot_name}\n"
            f"{now_berlin.strftime('%d.%m.%Y  %H:%M')} Berlin\n"
            f"{'─'*30}\n"
            f"₿  <b>BTC</b>    {fmt('bitcoin')}\n"
            f"Ξ  <b>ETH</b>    {fmt('ethereum')}\n"
            f"◎  <b>SOL</b>    {fmt('solana')}\n"
            f"🥇 <b>Gold</b>   {fmt('pax-gold')}\n"
            f"{'─'*30}\n"
            f"🌍 Krypto-Markt:  <b>{mcap_str}</b>\n"
            f"👑 BTC Dominanz: <b>{btc_dom:.1f}%</b>\n"
            f"{'─'*30}\n"
            f"Nachrichten folgen 👇"
        )
        return msg
    except Exception as e:
        print(f"[MarktDaten] Fehler: {e}")
        return "📊 <b>Marktdaten momentan nicht verfügbar</b>\n\nNachrichten folgen 👇"


# ─── NACHRICHTENQUELLEN ───────────────────────────────────────────────────────

RSS_FEEDS = [
    # 🇺🇸 Krypto
    ("https://www.coindesk.com/arc/outboundfeeds/rss/",         "CoinDesk",          "crypto",  "en"),
    ("https://cointelegraph.com/rss",                            "Cointelegraph",     "crypto",  "en"),
    ("https://decrypt.co/feed",                                  "Decrypt",           "crypto",  "en"),
    ("https://bitcoinmagazine.com/.rss/full/",                   "Bitcoin Magazine",  "crypto",  "en"),
    ("https://theblock.co/rss.xml",                              "The Block",         "crypto",  "en"),
    # 🇺🇸 Finanzen & Märkte
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml",           "WSJ Markets",       "finance", "en"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html",    "CNBC Finance",      "finance", "en"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml",          "BBC Business",      "finance", "en"),
    ("https://www.ft.com/rss/home/uk",                          "Financial Times",   "finance", "en"),
    ("https://fortune.com/feed/",                               "Fortune",           "finance", "en"),
    # 🇺🇸 Makro & Politik
    ("https://feeds.a.dj.com/rss/RSSWorldNews.xml",             "WSJ World",         "macro",   "en"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml",             "BBC World",         "macro",   "en"),
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html",   "CNBC Economy",      "macro",   "en"),
    # 🇩🇪🇪🇺 Europäisch
    ("https://www.handelsblatt.com/contentexport/feed/finanzen", "Handelsblatt",      "finance", "de"),
    ("https://www.faz.net/rss/aktuell/finanzen/",               "FAZ Finanzen",      "finance", "de"),
    ("https://www.btc-echo.de/feed/",                           "BTC-Echo",          "crypto",  "de"),
    ("https://www.crypto-news-flash.com/de/feed/",              "Crypto News Flash", "crypto",  "de"),
    # 🇷🇺 Russisch
    ("https://forklog.com/feed/",                               "Forklog",           "crypto",  "ru"),
    ("https://coinpost.ru/?feed=rss2",                          "CoinPost RU",       "crypto",  "ru"),
]

NEWSAPI_QUERIES = [
    ("crypto regulation SEC CFTC Congress law",        "en"),
    ("Bitcoin Ethereum ETF Federal Reserve rates",     "en"),
    ("MiCA Europe crypto ECB regulation",              "en"),
    ("Trump crypto executive order sanctions",         "en"),
    ("Nvidia Apple Microsoft earnings stock market",   "en"),
    ("Fed interest rate inflation recession",          "en"),
    ("Krypto Regulierung BaFin EZB Deutschland",       "de"),
]


def fetch_rss(feed_url, source, category, lang):
    import xml.etree.ElementTree as ET
    try:
        r = requests.get(feed_url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0 (SilentMoneyBot/1.0)"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        results = []
        for item in root.findall(".//item")[:12]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            desc  = (item.findtext("description") or "")[:300]
            if title and link:
                results.append({"title": title, "url": link, "source": source,
                                 "description": desc, "category": category, "lang": lang})
        return results
    except Exception as e:
        print(f"[RSS] {source}: {e}")
        return []


def fetch_cryptopanic():
    if not CRYPTOPANIC_API_KEY:
        return []
    try:
        r = requests.get(
            "https://cryptopanic.com/api/v1/posts/",
            params={"auth_token": CRYPTOPANIC_API_KEY, "filter": "important",
                    "public": "true", "kind": "news"},
            timeout=15,
        )
        r.raise_for_status()
        return [{"title": i.get("title", ""), "url": i.get("url", ""),
                 "source": i.get("source", {}).get("title", "CryptoPanic"),
                 "description": "", "category": "crypto", "lang": "en"}
                for i in r.json().get("results", [])[:30]]
    except Exception as e:
        print(f"[CryptoPanic]: {e}")
        return []


def fetch_newsapi(query, lang):
    if not NEWS_API_KEY:
        return []
    since = (datetime.utcnow() - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"apiKey": NEWS_API_KEY, "q": query, "from": since,
                    "language": lang, "sortBy": "publishedAt", "pageSize": 10},
            timeout=15,
        )
        r.raise_for_status()
        return [{"title": a.get("title", ""), "url": a.get("url", ""),
                 "source": a.get("source", {}).get("name", "NewsAPI"),
                 "description": (a.get("description") or "")[:300],
                 "category": "finance", "lang": lang}
                for a in r.json().get("articles", [])
                if a.get("title") and a.get("url")]
    except Exception as e:
        print(f"[NewsAPI] '{query}': {e}")
        return []


def fetch_all_news():
    print("📡 Nachrichten werden gesammelt...")
    all_news = []
    all_news.extend(fetch_cryptopanic())
    for q, lang in NEWSAPI_QUERIES:
        all_news.extend(fetch_newsapi(q, lang))
    for args in RSS_FEEDS:
        all_news.extend(fetch_rss(*args))

    seen, unique = set(), []
    for item in all_news:
        key = item["title"][:80].lower()
        if key not in seen and item["title"] and item["url"]:
            seen.add(key)
            unique.append(item)
    print(f"✅ Gesammelt: {len(unique)} einzigartige Nachrichten")
    return unique


# ─── CLAUDE-VERARBEITUNG ──────────────────────────────────────────────────────

def select_and_summarize(raw_news: list) -> list:
    now = datetime.utcnow().strftime("%d. %B %Y, %H:%M UTC")
    news_json = json.dumps(
        [{"i": i, "title": n["title"], "source": n["source"],
          "url": n["url"], "lang": n.get("lang", "en"),
          "desc": n.get("description", "")[:200]}
         for i, n in enumerate(raw_news)],
        ensure_ascii=False,
    )

    prompt = f"""
Jetzt ist {now}. Du bist Redakteur von "Silent Money" — einem Telegram-Kanal mit dieser Philosophie:

REDAKTIONELLE LINIE:
Kein Informationslärm. Keine Meinungen. Keine Prognosen. Keine Kauf-/Verkaufssignale.
Nur: Fakten — regulatorische Entscheidungen — Unternehmenshandlungen — Ereignisse die Märkte wirklich bewegen.
Format jedes Posts: Ereignis → Auswirkung → Quelle

AUFGABE: Wähle GENAU 5 Nachrichten aus. Nur solche die wirklich Bedeutung haben.

AUSWAHLKRITERIEN — Märkte bewegende Ereignisse:
→ Regulierung & Gesetze: SEC, CFTC, MiCA, BaFin, Kongress, Kreml
→ Zentralbanken: Fed, EZB, Zinsentscheidungen, Inflation
→ Politik mit Marktauswirkung: Trump-Dekrete, Sanktionen, Handelskrieg
→ Unternehmen: Earnings-Überraschungen, Übernahmen, Krisen (Nvidia, Apple, Coinbase, Tesla, BlackRock)
→ Krypto-Institutionelles: ETF-Entscheidungen, große Käufe/Verkäufe, Protokoll-Hacks
→ Makro-Schocks: Rezessionszeichen, Bankenkrisen, systemische Ereignisse

AUSSCHLUSSKRITERIEN:
✗ Preisbewegungen ohne klaren Nachrichtengrund
✗ Altcoin-Projekte ohne systemische Relevanz
✗ PR-Artikel, Spekulationen, Meinungsstücke

SCHREIBSTIL — Silent Money Format:
• Emoji passend zum Thema
• Schlagzeile: Fakt in max. 10 Wörtern (fett) — kein Clickbait
• Text: 2–3 Sätze. Erst das Ereignis (was genau passiert ist). Dann die Auswirkung (was das konkret bedeutet — für Markt, Regulierung, Investoren). Keine weichen Formulierungen, keine Meinungen, keine Prognosen.
• Ton: sachlich, präzise, direkt. Wie Reuters — nicht wie ein Krypto-Blog.

Antworte NUR mit validen JSON-Array (keine Codeblöcke):
[
  {{
    "emoji": "🔥",
    "headline": "Schlagzeile auf Deutsch",
    "body": "Post-Text, 3–4 Sätze auf Deutsch.",
    "source_name": "Quellenname",
    "url": "https://..."
  }}
]

NACHRICHTEN:
{news_json[:13000]}
"""

    print("🤖 Claude analysiert...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip().rstrip("```").strip()

    try:
        result = json.loads(text)
        print(f"✅ {len(result)} Nachrichten ausgewählt")
        return result
    except json.JSONDecodeError as e:
        print(f"❌ JSON-Fehler: {e}\n{text[:400]}")
        return []


# ─── TELEGRAM-VERSAND ─────────────────────────────────────────────────────────

def send_message(text: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[Telegram] Fehler: {e}")
        return False


def send_digest(items: list) -> None:
    # 1. Marktpreise
    market_msg = fetch_market_snapshot()
    send_message(market_msg)
    time.sleep(3)

    # 2. Nachrichten einzeln
    for i, item in enumerate(items, 1):
        msg = (
            f"{item.get('emoji','📌')} <b>{item.get('headline','')}</b>\n\n"
            f"{item.get('body','')}\n\n"
            f"📰 <a href=\"{item.get('url','')}\">{ item.get('source_name','Quelle')}</a>"
        )
        ok = send_message(msg)
        print(f"{'✅' if ok else '❌'} [{i}/5] {item.get('headline','')[:60]}")
        time.sleep(3)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    now_utc = datetime.utcnow()
    print(f"\n{'─'*50}")
    print(f"🤫💰 SILENT MONEY | {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'─'*50}\n")

    raw = fetch_all_news()
    if not raw:
        print("❌ Keine Nachrichten gefunden"); return

    selected = select_and_summarize(raw)
    if not selected:
        print("❌ Keine Nachrichten von Claude"); return

    send_digest(selected)
    print("\n✅ Digest erfolgreich gesendet!")


if __name__ == "__main__":
    main()
