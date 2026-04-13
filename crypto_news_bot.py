"""
Silent Money — Crypto & Finance Daily Digest Bot
Quellen: EN + RU + EU | Ausgabe: Deutsch | Kanal: @SilentMoney
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

# ─── RSS-QUELLEN ──────────────────────────────────────────────────────────────
#  (feed_url, Quellenname, Kategorie, Sprache)
RSS_FEEDS = [
    # 🇺🇸 Englisch — Krypto
    ("https://www.coindesk.com/arc/outboundfeeds/rss/",         "CoinDesk",          "crypto",  "en"),
    ("https://cointelegraph.com/rss",                            "Cointelegraph",     "crypto",  "en"),
    ("https://decrypt.co/feed",                                  "Decrypt",           "crypto",  "en"),
    ("https://bitcoinmagazine.com/.rss/full/",                   "Bitcoin Magazine",  "crypto",  "en"),
    ("https://theblock.co/rss.xml",                              "The Block",         "crypto",  "en"),

    # 🇺🇸 Englisch — Finanzen
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml",           "WSJ Markets",       "finance", "en"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html",    "CNBC Finance",      "finance", "en"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml",          "BBC Business",      "finance", "en"),
    ("https://www.ft.com/rss/home/uk",                          "Financial Times",   "finance", "en"),
    ("https://fortune.com/feed/",                               "Fortune",           "finance", "en"),

    # 🇩🇪🇪🇺 Deutsch / Europäisch
    ("https://www.handelsblatt.com/contentexport/feed/finanzen", "Handelsblatt",      "finance", "de"),
    ("https://www.faz.net/rss/aktuell/finanzen/",               "FAZ Finanzen",      "finance", "de"),
    ("https://www.boerse.de/rss/nachrichten.htm",               "Boerse.de",         "finance", "de"),
    ("https://www.btc-echo.de/feed/",                           "BTC-Echo",          "crypto",  "de"),
    ("https://www.crypto-news-flash.com/de/feed/",              "Crypto News Flash", "crypto",  "de"),

    # 🇷🇺 Russisch — Krypto & Finanzen
    ("https://bits.media/rss/news/",                            "Bits.media",        "crypto",  "ru"),
    ("https://forklog.com/feed/",                               "Forklog",           "crypto",  "ru"),
    ("https://www.rbc.ru/crypto/rss/",                          "RBC Crypto",        "crypto",  "ru"),
    ("https://coinpost.ru/?feed=rss2",                          "CoinPost RU",       "crypto",  "ru"),
]

NEWSAPI_QUERIES = [
    ("crypto regulation SEC CFTC law",        "en"),
    ("Bitcoin Ethereum Federal Reserve rates", "en"),
    ("MiCA Europe crypto ECB regulation",      "en"),
    ("crypto token unlock liquidation DeFi",   "en"),
    ("Binance Coinbase BlackRock crypto ETF",  "en"),
    ("Krypto Regulierung BaFin Deutschland",   "de"),
    ("Bitcoin Zinsen EZB Inflation",           "de"),
]


# ─── QUELLEN ABRUFEN ─────────────────────────────────────────────────────────

def fetch_rss(feed_url: str, source: str, category: str, lang: str) -> list[dict]:
    import xml.etree.ElementTree as ET
    try:
        r = requests.get(
            feed_url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (SilentMoneyBot/1.0)"}
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        results = []
        for item in root.findall(".//item")[:15]:
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


def fetch_cryptopanic() -> list[dict]:
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
                for i in r.json().get("results", [])[:40]]
    except Exception as e:
        print(f"[CryptoPanic]: {e}")
        return []


def fetch_newsapi(query: str, lang: str) -> list[dict]:
    if not NEWS_API_KEY:
        return []
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"apiKey": NEWS_API_KEY, "q": query, "from": yesterday,
                    "language": lang, "sortBy": "relevancy", "pageSize": 15},
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


def fetch_all_news() -> list[dict]:
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

def select_and_summarize(raw_news: list[dict]) -> list[dict]:
    today = datetime.utcnow().strftime("%d. %B %Y")
    news_json = json.dumps(
        [{"i": i, "title": n["title"], "source": n["source"],
          "url": n["url"], "lang": n.get("lang", "en"),
          "desc": n.get("description", "")[:200]}
         for i, n in enumerate(raw_news)],
        ensure_ascii=False,
    )

    prompt = f"""
Heute ist der {today}. Du bist Chefredakteur von "Silent Money" — einem professionellen 
Krypto- und Finanzkanal auf Telegram. Deine Leser: erfahrene Investoren aus dem 
deutschsprachigen Raum, die präzise, interpretierte Informationen schätzen.

AUFGABE:
1. Wähle MAXIMAL 25 der wichtigsten Nachrichten aus EN, DE, RU und EU Quellen.
   Priorität:
   → Regulierung (SEC, CFTC, MiCA, BaFin, Russland)
   → Zinsentscheidungen (Fed, EZB, russische Zentralbank)
   → Große Deals, ETF-Entscheidungen, institutionelle Bewegungen
   → Aussagen von Trump, Powell, Lagarde, Binance/Coinbase-CEOs, Vitalik
   → Token-Unlocks, Liquidierungen, Marktbewegungen
   → Regulatorische Neuheiten in Europa und USA

2. Schreibe jeden Beitrag AUF DEUTSCH im Stil von Silent Money:
   • Passendes Emoji (einzigartig pro Post)
   • Prägnante Schlagzeile (max. 12 Wörter, fett)
   • 3–5 Sätze: 80% Fakten + 20% Interpretation ("Was bedeutet das?")
   • Professioneller, aber zugänglicher Ton
   • Quellenlink am Ende

Antworte NUR mit einem validen JSON-Array (keine Codeblöcke, keine Erklärung):
[
  {{
    "emoji": "🔥",
    "headline": "Deutsche Schlagzeile",
    "body": "Post-Text auf Deutsch, 3–5 Sätze.",
    "source_name": "Quellenname",
    "url": "https://..."
  }}
]

NACHRICHTEN:
{news_json[:14000]}
"""

    print("🤖 Claude analysiert und übersetzt...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
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


def send_digest(items: list[dict]) -> None:
    today = datetime.utcnow().strftime("%d.%m.%Y")

    send_message(
        f"🤫💰 <b>SILENT MONEY — {today}</b>\n\n"
        f"Die {len(items)} wichtigsten Krypto- & Finanznachrichten des Tages.\n"
        f"Quellen: 🇺🇸 EN · 🇩🇪 DE · 🇪🇺 EU · 🇷🇺 RU\n\n"
        f"Jede Nachricht folgt einzeln 👇"
    )
    time.sleep(2)

    for i, item in enumerate(items, 1):
        msg = (
            f"{item.get('emoji','📌')} <b>{item.get('headline','')}</b>\n\n"
            f"{item.get('body','')}\n\n"
            f"📰 <a href=\"{item.get('url','')}\">{ item.get('source_name','Quelle')}</a>"
        )
        ok = send_message(msg)
        print(f"{'✅' if ok else '❌'} [{i}/{len(items)}] {item.get('headline','')[:60]}")
        time.sleep(3)

    send_message(f"✅ <b>Silent Money Digest {today} — vollständig.</b>\nBis morgen! 🤫💰")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'─'*55}")
    print(f"🤫💰 SILENT MONEY BOT | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'─'*55}\n")

    raw = fetch_all_news()
    if not raw:
        print("❌ Keine Nachrichten gefunden"); return

    selected = select_and_summarize(raw)
    if not selected:
        print("❌ Claude hat keine Nachrichten zurückgegeben"); return

    send_digest(selected)
    print("\n✅ Digest erfolgreich gesendet!")


if __name__ == "__main__":
    main()
