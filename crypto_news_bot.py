"""
Silent Money — Crypto & Finance Daily Digest
Kanal: @silentmoney_feed | 5x täglich | Berlin-Zeit
"""

import os, json, time, hashlib, requests
from datetime import datetime, timedelta
from anthropic import Anthropic

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY", "")
NEWS_API_KEY        = os.environ.get("NEWS_API_KEY", "")
GIST_TOKEN          = os.environ.get("GIST_TOKEN", "")
GIST_ID             = os.environ.get("GIST_ID", "")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

DEDUP_HOURS = 72

SLOT_NAMES = {
    5: "🌅 Morgen", 9: "☀️ Mittag",
    12: "📊 Nachmittag", 15: "🌆 Abend", 18: "🌙 Nacht",
}

# ─── LOG via GitHub Gist (persistenter Speicher) ──────────────────────────────

def load_log() -> dict:
    """Lädt den Log aus GitHub Gist"""
    if GIST_TOKEN and GIST_ID:
        try:
            r = requests.get(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"token {GIST_TOKEN}"},
                timeout=15,
            )
            r.raise_for_status()
            content = r.json()["files"]["silent_money_log.json"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"[Gist] Ladefehler: {e}")
    # Fallback: lokale Datei
    try:
        if os.path.exists("sent_news_log.json"):
            with open("sent_news_log.json") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_log(log: dict) -> None:
    """Speichert den Log in GitHub Gist"""
    # Immer lokal speichern (für git commit als Backup)
    try:
        with open("sent_news_log.json", "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Log] Lokaler Speicherfehler: {e}")

    if GIST_TOKEN and GIST_ID:
        try:
            requests.patch(
                f"https://api.github.com/gists/{GIST_ID}",
                headers={"Authorization": f"token {GIST_TOKEN}"},
                json={"files": {"silent_money_log.json": {"content": json.dumps(log, ensure_ascii=False, indent=2)}}},
                timeout=15,
            )
            print("[Gist] Log gespeichert ✅")
        except Exception as e:
            print(f"[Gist] Speicherfehler: {e}")


def clean_log(log: dict) -> dict:
    cutoff = (datetime.utcnow() - timedelta(hours=DEDUP_HOURS)).isoformat()
    return {k: v for k, v in log.items() if k.startswith("__") or v >= cutoff}


def prices_shown_today(log: dict) -> bool:
    today = (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%d")
    return log.get("__prices_date__") == today


def mark_prices(log: dict) -> dict:
    log["__prices_date__"] = (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%d")
    return log


def news_key(title: str) -> str:
    return hashlib.md5(title.lower().strip()[:120].encode()).hexdigest()


def url_key(url: str) -> str:
    return hashlib.md5(url.lower().strip().encode()).hexdigest()


def filter_sent(news: list, log: dict) -> list:
    filtered = [n for n in news
                if news_key(n["title"]) not in log
                and url_key(n["url"]) not in log]
    print(f"🔁 Gefiltert: {len(news)-len(filtered)} bereits gesendet → {len(filtered)} neu")
    return filtered


def mark_sent(items: list, log: dict) -> dict:
    now = datetime.utcnow().isoformat()
    for item in items:
        title = item.get("headline") or item.get("title", "")
        url   = item.get("url", "")
        if title:
            log[news_key(title)] = now
        if url:
            log[url_key(url)] = now
    return log


# ─── MARKTPREISE ──────────────────────────────────────────────────────────────

def fetch_market_snapshot() -> str:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin,ethereum,solana,pax-gold",
                    "vs_currencies": "usd", "include_24hr_change": "true"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        g    = requests.get("https://api.coingecko.com/api/v3/global", timeout=15).json()
        gd   = g.get("data", {})
        mcap = gd.get("total_market_cap", {}).get("usd", 0)
        dom  = gd.get("market_cap_percentage", {}).get("btc", 0)

        def fmt(coin):
            p = data.get(coin, {}).get("usd", 0)
            c = data.get(coin, {}).get("usd_24h_change", 0)
            a = "▲" if c >= 0 else "▼"
            s = "+" if c >= 0 else ""
            return f"${p:,.0f}  {a}{s}{c:.1f}%" if p > 1000 else f"${p:,.2f}  {a}{s}{c:.1f}%"

        mcap_s    = f"${mcap/1e12:.2f}T" if mcap > 1e12 else f"${mcap/1e9:.0f}B"
        now_b     = datetime.utcnow() + timedelta(hours=2)
        slot_name = SLOT_NAMES.get(min(SLOT_NAMES, key=lambda h: abs(h - now_b.hour)), "📊")

        return (
            f"💼 <b>SILENT MONEY</b> — {slot_name}\n"
            f"{now_b.strftime('%d.%m.%Y  %H:%M')} Berlin\n"
            f"{'─'*30}\n"
            f"₿  <b>BTC</b>    {fmt('bitcoin')}\n"
            f"Ξ  <b>ETH</b>    {fmt('ethereum')}\n"
            f"◎  <b>SOL</b>    {fmt('solana')}\n"
            f"🥇 <b>Gold</b>   {fmt('pax-gold')}\n"
            f"{'─'*30}\n"
            f"🌍 Krypto-Markt:  <b>{mcap_s}</b>\n"
            f"👑 BTC Dominanz: <b>{dom:.1f}%</b>\n"
            f"{'─'*30}\n"
            f"Nachrichten folgen 👇"
        )
    except Exception as e:
        print(f"[Markt] {e}")
        return "📊 <b>Marktdaten nicht verfügbar</b>\n\nNachrichten folgen 👇"


# ─── QUELLEN ──────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    # 🇺🇸 Krypto
    ("https://www.coindesk.com/arc/outboundfeeds/rss/",         "CoinDesk",         "crypto",  "en"),
    ("https://cointelegraph.com/rss",                            "Cointelegraph",    "crypto",  "en"),
    ("https://decrypt.co/feed",                                  "Decrypt",          "crypto",  "en"),
    ("https://bitcoinmagazine.com/.rss/full/",                   "Bitcoin Magazine", "crypto",  "en"),
    ("https://theblock.co/rss.xml",                              "The Block",        "crypto",  "en"),
    ("https://blockworks.co/feed",                               "Blockworks",       "crypto",  "en"),
    # 🇺🇸 Finanzen & Märkte
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml",           "WSJ Markets",      "finance", "en"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html",    "CNBC Finance",     "finance", "en"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml",          "BBC Business",     "finance", "en"),
    ("https://www.ft.com/rss/home/uk",                          "Financial Times",  "finance", "en"),
    ("https://fortune.com/feed/",                               "Fortune",          "finance", "en"),
    # 🇺🇸 Makro & Politik
    ("https://feeds.a.dj.com/rss/RSSWorldNews.xml",             "WSJ World",        "macro",   "en"),
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html",   "CNBC Economy",     "macro",   "en"),
    # 🤖 AI & Technologie
    ("https://techcrunch.com/feed/",                            "TechCrunch",       "ai",      "en"),
    ("https://www.theverge.com/rss/index.xml",                  "The Verge",        "ai",      "en"),
    ("https://venturebeat.com/feed/",                           "VentureBeat",      "ai",      "en"),
    ("https://www.wired.com/feed/rss",                          "Wired",            "ai",      "en"),
    # 🌏 Global
    ("https://asia.nikkei.com/rss/feed/nar",                    "Nikkei Asia",      "finance", "en"),
    # 🇩🇪🇪🇺 Europäisch
    ("https://www.handelsblatt.com/contentexport/feed/finanzen", "Handelsblatt",     "finance", "de"),
    ("https://www.faz.net/rss/aktuell/finanzen/",               "FAZ Finanzen",     "finance", "de"),
    ("https://www.btc-echo.de/feed/",                           "BTC-Echo",         "crypto",  "de"),
    ("https://www.crypto-news-flash.com/de/feed/",              "Crypto News Flash","crypto",  "de"),
    # 🇷🇺 Russisch
    ("https://forklog.com/feed/",                               "Forklog",          "crypto",  "ru"),
    ("https://coinpost.ru/?feed=rss2",                          "CoinPost RU",      "crypto",  "ru"),
]

# Twitter/X via Nitter RSS (kostenlos, keine API nötig)
NITTER_ACCOUNTS = [
    ("elonmusk",        "Elon Musk",              "twitter"),
    ("vitalikbuterin",  "Vitalik Buterin",        "twitter"),
    ("durov",           "Pavel Durov",            "twitter"),
    ("cz_binance",      "CZ Binance",             "twitter"),
    ("brian_armstrong", "Brian Armstrong",        "twitter"),
    ("realDonaldTrump", "Donald Trump",           "twitter"),
    ("ethereum",        "Ethereum",               "twitter"),
    ("binance",         "Binance",                "twitter"),
    ("coinbase",        "Coinbase",               "twitter"),
    ("federalreserve",  "Federal Reserve",        "twitter"),
    ("ECB",             "EZB",                    "twitter"),
    ("michael_saylor",  "Michael Saylor",         "twitter"),
    ("SBF_FTX",         "Sam Bankman-Fried",      "twitter"),
]

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]


def fetch_nitter(account: str, name: str) -> list[dict]:
    """Holt Tweets via Nitter RSS"""
    import xml.etree.ElementTree as ET
    for instance in NITTER_INSTANCES:
        try:
            url = f"{instance}/{account}/rss"
            r   = requests.get(url, timeout=10,
                               headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            results = []
            for item in root.findall(".//item")[:5]:
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                desc  = (item.findtext("description") or "")[:400]
                if title and link and len(title) > 20:
                    results.append({
                        "title": f"[{name}] {title}",
                        "url": link.replace(instance, "https://twitter.com"),
                        "source": f"X/@{account}",
                        "description": desc,
                        "category": "twitter",
                        "lang": "en",
                    })
            if results:
                return results
        except Exception:
            continue
    return []

NEWSAPI_QUERIES = [
    ("crypto regulation SEC CFTC Congress",        "en"),
    ("Bitcoin ETF Federal Reserve interest rates", "en"),
    ("MiCA Europe ECB crypto regulation",          "en"),
    ("Trump sanctions tariffs crypto",             "en"),
    ("Nvidia Apple earnings stock market",         "en"),
    ("Fed inflation recession macro",              "en"),
    ("Japan UAE Singapore crypto law",             "en"),
    ("whale bitcoin institutional BlackRock",      "en"),
    ("AI regulation artificial intelligence law",  "en"),
    ("OpenAI Anthropic Google AI policy",          "en"),
    ("Krypto BaFin EZB Regulierung",               "de"),
    ("KI Regulierung Europa Deutschland",          "de"),
]


def fetch_rss(url, source, cat, lang):
    import xml.etree.ElementTree as ET
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out  = []
        for item in root.findall(".//item")[:12]:
            t = (item.findtext("title") or "").strip()
            l = (item.findtext("link")  or "").strip()
            d = (item.findtext("description") or "")[:300]
            if t and l:
                out.append({"title": t, "url": l, "source": source,
                             "description": d, "category": cat, "lang": lang})
        return out
    except Exception as e:
        print(f"[RSS] {source}: {e}")
        return []


def fetch_cryptopanic():
    if not CRYPTOPANIC_API_KEY:
        return []
    try:
        r = requests.get("https://cryptopanic.com/api/v1/posts/",
                         params={"auth_token": CRYPTOPANIC_API_KEY, "filter": "important",
                                 "public": "true", "kind": "news"}, timeout=15)
        r.raise_for_status()
        return [{"title": i.get("title",""), "url": i.get("url",""),
                 "source": i.get("source",{}).get("title","CryptoPanic"),
                 "description": "", "category": "crypto", "lang": "en"}
                for i in r.json().get("results",[])[:30]]
    except Exception as e:
        print(f"[CryptoPanic]: {e}"); return []


def fetch_newsapi(query, lang):
    if not NEWS_API_KEY:
        return []
    since = (datetime.utcnow() - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        r = requests.get("https://newsapi.org/v2/everything",
                         params={"apiKey": NEWS_API_KEY, "q": query, "from": since,
                                 "language": lang, "sortBy": "publishedAt", "pageSize": 10},
                         timeout=15)
        r.raise_for_status()
        return [{"title": a.get("title",""), "url": a.get("url",""),
                 "source": a.get("source",{}).get("name","NewsAPI"),
                 "description": (a.get("description") or "")[:300],
                 "category": "finance", "lang": lang}
                for a in r.json().get("articles",[]) if a.get("title") and a.get("url")]
    except Exception as e:
        print(f"[NewsAPI] {query}: {e}"); return []


def fetch_all() -> list:
    print("📡 Sammle Nachrichten...")
    all_n = []
    all_n.extend(fetch_cryptopanic())
    for q, l in NEWSAPI_QUERIES:
        all_n.extend(fetch_newsapi(q, l))
    for args in RSS_FEEDS:
        all_n.extend(fetch_rss(*args))

    # Twitter via Nitter
    print("🐦 Sammle Tweets...")
    for account, name, _ in NITTER_ACCOUNTS:
        tweets = fetch_nitter(account, name)
        all_n.extend(tweets)
        if tweets:
            print(f"  ✅ @{account}: {len(tweets)} Tweets")

    seen, unique = set(), []
    for n in all_n:
        k = n["title"][:80].lower()
        if k not in seen and n["title"] and n["url"]:
            seen.add(k); unique.append(n)
    print(f"✅ {len(unique)} einzigartige Nachrichten gesammelt")
    return unique


# ─── CLAUDE ───────────────────────────────────────────────────────────────────

def summarize(news: list, recent_headlines: list, is_weekly: bool = False) -> list:
    count = 7 if is_weekly else 5
    now   = datetime.utcnow().strftime("%d. %B %Y, %H:%M UTC")

    news_json = json.dumps(
        [{"i": i, "title": n["title"], "source": n["source"], "url": n["url"],
          "lang": n.get("lang","en"), "desc": n.get("description","")[:150]}
         for i, n in enumerate(news)],
        ensure_ascii=False)

    recent_str = "\n".join(f"- {h}" for h in recent_headlines[-40:]) if recent_headlines else "keine"

    now_b     = datetime.utcnow() + timedelta(hours=2)
    is_sunday = now_b.weekday() == 6

    prompt = f"""
Jetzt: {now}. Redakteur von "Silent Money" — Krypto/Finanz Telegram-Kanal.
Philosophie: Fakten. Regulatorische Entscheidungen. Unternehmenshandlungen. Ereignisse die Märkte bewegen.
Kein Lärm. Keine Meinungen. Keine Prognosen.

BEREITS IN DEN LETZTEN 72H GESENDET (diese Themen NICHT wiederholen):
{recent_str}

AUFGABE: Wähle GENAU {count} Nachrichten.

TÄGLICH PRÜFEN:
→ Krypto-Regulierung: SEC, CFTC, MiCA, BaFin, Kongress, Kreml, Japan, UAE
→ Zentralbanken: Fed, EZB, Zinsentscheidungen
→ Politik mit Marktauswirkung: Trump, Sanktionen, Handelskrieg
→ Unternehmen: Earnings, Übernahmen (Nvidia, Apple, Tesla, BlackRock, Coinbase)
→ Krypto-Institutionell: ETF, große Käufe, Hacks, Protokoll-Updates
→ Stille Bewegungen: Whales, staatliche BTC-Käufe, große OTC-Deals
→ AI-Regulierung: OpenAI, Anthropic, Google AI, EU AI Act, US AI Policy
→ Twitter/X: Nur wenn eine relevante Persönlichkeit (Musk, Vitalik, CZ, Trump, Powell) etwas KONKRETES und MARKTRELEVANTES gepostet hat — keine Meinungen, nur Fakten oder Ankündigungen

{"HEUTE SONNTAG — ZUSÄTZLICH PRÜFEN:" if is_sunday else ""}
{"→ Rohstoffe: Öl (WTI/Brent), Gas, Kupfer, Lithium — wichtige Preisbewegungen oder OPEC-Entscheidungen" if is_sunday else ""}
{"→ Währungen: Dollar-Index (DXY), EUR/USD, USD/JPY, Yuan — wichtige Bewegungen" if is_sunday else ""}
{"→ Makro: CPI, PMI, Arbeitsmarkt — neue Daten der Woche" if is_sunday else ""}
{"→ Energie: OPEC-Entscheidungen, Gaspreise Europa" if is_sunday else ""}

TWITTER-FILTER (sehr streng):
✓ Nur aufnehmen wenn: konkrete Ankündigung, Gesetzesvorhaben, Unternehmungsentscheidung
✗ Nicht aufnehmen: Meinungen, Witze, Retweets ohne neue Info, allgemeine Kommentare

STRENGE DEDUPLIZIERUNG:
- Bereits gesendete Themen: NICHT nochmal senden
- Pro Ereignis NUR EINE Quelle
- Gleicher Inhalt mit anderer Überschrift = Duplikat = weglassen

FORMAT pro Post (Deutsch):
Emoji + fette Schlagzeile (max 10 Wörter, reiner Fakt)
2-3 Sätze: Was passiert ist → Was es für Märkte bedeutet
Bei Twitter-Posts: Wer hat was gesagt/angekündigt → Marktbedeutung
Ton: Reuters, nicht Krypto-Blog

JSON-Array (keine Codeblöcke):
[{{"emoji":"🏛","headline":"...","body":"...","source_name":"...","url":"..."}}]

NACHRICHTEN:
{news_json[:13000]}
"""

    print("🤖 Claude analysiert...")
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"): text = text[4:]
    text = text.strip().rstrip("```").strip()

    try:
        result = json.loads(text)
        print(f"✅ {len(result)} ausgewählt")
        return result[:count]
    except Exception as e:
        print(f"❌ JSON: {e}\n{text[:300]}")
        return []


def self_check_duplicates(selected: list, recent_titles: list) -> list:
    """Claude prüft seine eigene Auswahl nochmal auf inhaltliche Duplikate"""
    if not recent_titles or not selected:
        return selected

    selected_json  = json.dumps([{"i": i, "h": s.get("headline","")} for i, s in enumerate(selected)], ensure_ascii=False)
    recent_str     = "\n".join(f"- {t}" for t in recent_titles[-50:])

    prompt = f"""Du hast diese Nachrichten ausgewählt:
{selected_json}

Bereits in den letzten 72h gesendet:
{recent_str}

Prüfe: Welche der ausgewählten Nachrichten sind inhaltlich GLEICH oder SEHR ÄHNLICH zu bereits gesendeten?
Gleich = dasselbe Ereignis, auch wenn anders formuliert.

Antworte NUR mit JSON-Array der Indizes die BEHALTEN werden sollen (nicht die Duplikate):
[0, 1, 2, 3, 4]

Wenn alle ok: alle Indizes zurückgeben. Wenn ein Duplikat: diesen Index weglassen."""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        keep = json.loads(text)
        result = [selected[i] for i in keep if i < len(selected)]
        removed = len(selected) - len(result)
        if removed > 0:
            print(f"🔍 Selbstprüfung: {removed} Duplikat(e) entfernt")
        return result
    except Exception as e:
        print(f"[Selbstprüfung] Fehler: {e}")
        return selected




def send(text: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=15)
        r.raise_for_status(); return True
    except Exception as e:
        print(f"[TG] {e}"); return False


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    now_b     = datetime.utcnow() + timedelta(hours=2)
    is_weekly = now_b.weekday() == 6 and now_b.hour >= 18

    print(f"\n{'─'*50}")
    print(f"🤫💰 SILENT MONEY | {now_b.strftime('%Y-%m-%d %H:%M')} Berlin")
    print(f"{'─'*50}\n")

    # 1. Log laden
    log = load_log()
    log = clean_log(log)
    print(f"📋 Log: {len([k for k in log if not k.startswith('__')])} Einträge")

    # 2. Nachrichten holen
    raw = fetch_all()
    if not raw:
        print("❌ Keine Nachrichten"); return

    # 3. Bereits gesendete filtern (nach Hash)
    filtered = filter_sent(raw, log)
    if len(filtered) < 5:
        print("⚠️ Zu wenige neue Nachrichten — nehme alle")
        filtered = raw  # Fallback: alle nehmen, Claude dedupliziert nach Thema

    # 4. Bereits gesendete Headlines für Claude (semantische Deduplizierung)
    recent_headlines = [v for k, v in log.items() if not k.startswith("__")]
    # Wir speichern Headlines separat
    recent_titles = log.get("__recent_titles__", [])

    # 5. Claude wählt aus
    selected = summarize(filtered, recent_titles, is_weekly)
    if not selected:
        print("❌ Nichts von Claude"); return

    # 5b. Selbstprüfung — Claude checkt nochmal auf Duplikate
    selected = self_check_duplicates(selected, recent_titles)

    # 6. Senden
    if is_weekly:
        send(f"📅 <b>SILENT MONEY — Wochenrückblick</b>\n"
             f"{now_b.strftime('%d.%m.%Y')} · Die 7 wichtigsten Ereignisse\n\nWas wirklich zählte 👇")
        time.sleep(3)
    elif not prices_shown_today(log):
        send(fetch_market_snapshot())
        log = mark_prices(log)
        time.sleep(3)

    new_titles = list(recent_titles)
    for i, item in enumerate(selected, 1):
        msg = (f"{item.get('emoji','📌')} <b>{item.get('headline','')}</b>\n\n"
               f"{item.get('body','')}\n\n"
               f"📰 <a href=\"{item.get('url','')}\">{ item.get('source_name','')}</a>")
        ok = send(msg)
        print(f"{'✅' if ok else '❌'} [{i}] {item.get('headline','')[:55]}")
        new_titles.append(item.get("headline",""))
        time.sleep(3)

    # 7. Log speichern — recent_titles dedupliziert
    log = mark_sent(selected, log)
    seen_t, deduped = set(), []
    for t in new_titles:
        if t and t not in seen_t:
            seen_t.add(t); deduped.append(t)
    log["__recent_titles__"] = deduped[-60:]
    save_log(log)
    print(f"\n✅ Fertig! Log: {len([k for k in log if not k.startswith('__')])} Einträge")


if __name__ == "__main__":
    main()
