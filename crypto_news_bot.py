"""
Silent Money — Crypto, Finanz & Makro Digest
Kanal: @silentmoney_feed | 5x täglich | Berlin-Zeit

v3 (2026-10-19):
- Event-basierte Deduplizierung (event_key + 72h) statt nur Hash/Headline
- Relevanz-Score mit Mindestschwelle: lieber 2 starke als 5 schwache Posts
- Geopolitik max. 3 Posts/Tag (Zähler im Log)
- Regionen-Abdeckung: USA, Europa, Asien, Afrika, Russland
- Alle Nachrichten erreichen Claude (kein Abschneiden nach Feed-Reihenfolge)
- Post-Format: FAKT / KONTEXT / WARUM ES WICHTIG IST / QUELLE
"""

import os, json, time, hashlib, random, requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from anthropic import Anthropic

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY", "")
NEWS_API_KEY        = os.environ.get("NEWS_API_KEY", "")
GIST_TOKEN          = os.environ.get("GIST_TOKEN", "")
GIST_ID             = os.environ.get("GIST_ID", "")
CLAUDE_MODEL        = os.environ.get("CLAUDE_MODEL") or "claude-haiku-4-5-20251001"

client = Anthropic(api_key=ANTHROPIC_API_KEY)

BERLIN          = ZoneInfo("Europe/Berlin")
DEDUP_HOURS     = 72        # kein Event doppelt innerhalb 72h (ohne neue Entwicklung)
SENT_KEEP_DAYS  = 7         # Sendehistorie für Wochenrückblick
MAX_PER_SLOT    = 5         # Obergrenze pro Run
MIN_SCORE       = 7         # Relevanz-Schwelle (1–10)
GEO_MAX_PER_DAY = 3         # Geopolitik-Posts pro Tag
NEWS_CHAR_CAP   = 48000     # Zeichenbudget für die Kandidatenliste (~12k Tokens)

SLOT_NAMES = {
    7: "🌅 Morgen", 11: "☀️ Mittag",
    14: "📊 Nachmittag", 17: "🌆 Abend", 20: "🌙 Nacht",
}

CATEGORIES = ["zentralbank", "regulierung", "staat", "geopolitik",
              "institutionell", "unternehmen", "krypto", "makro"]
REGIONS    = ["USA", "Europa", "Asien", "Afrika", "Russland", "Global"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_berlin() -> datetime:
    return datetime.now(BERLIN)


# ─── LOG via GitHub Gist (persistenter Speicher) ──────────────────────────────

def load_log() -> dict:
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
    try:
        if os.path.exists("sent_news_log.json"):
            with open("sent_news_log.json") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_log(log: dict) -> None:
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
    """Hashes älter als 72h raus; Sendehistorie älter als 7 Tage raus."""
    cutoff_hash = (now_utc() - timedelta(hours=DEDUP_HOURS)).replace(tzinfo=None).isoformat()
    cutoff_sent = (now_utc() - timedelta(days=SENT_KEEP_DAYS)).isoformat()
    out = {k: v for k, v in log.items()
           if k.startswith("__") or (isinstance(v, str) and v >= cutoff_hash)}
    out["__sent__"] = [s for s in log.get("__sent__", []) if s.get("ts", "") >= cutoff_sent]
    out.pop("__recent_titles__", None)   # altes Format
    return out


def prices_shown_today(log: dict) -> bool:
    return log.get("__prices_date__") == now_berlin().strftime("%Y-%m-%d")


def mark_prices(log: dict) -> dict:
    log["__prices_date__"] = now_berlin().strftime("%Y-%m-%d")
    return log


def news_key(title: str) -> str:
    return hashlib.md5(title.lower().strip()[:120].encode()).hexdigest()


def url_key(url: str) -> str:
    return hashlib.md5(url.lower().strip().encode()).hexdigest()


def filter_sent(news: list, log: dict) -> list:
    filtered = [n for n in news
                if news_key(n["title"]) not in log
                and url_key(n["url"]) not in log]
    print(f"🔁 Hash-Filter: {len(news)-len(filtered)} bereits gesendet → {len(filtered)} neu")
    return filtered


def sent_within(log: dict, hours: int) -> list:
    cutoff = (now_utc() - timedelta(hours=hours)).isoformat()
    return [s for s in log.get("__sent__", []) if s.get("ts", "") >= cutoff]


def geo_sent_today(log: dict) -> int:
    today = now_berlin().strftime("%Y-%m-%d")
    return sum(1 for s in log.get("__sent__", [])
               if s.get("category") == "geopolitik" and s.get("date_berlin") == today)


def mark_sent(items: list, log: dict) -> dict:
    ts   = now_utc().isoformat()
    ts_h = now_utc().replace(tzinfo=None).isoformat()
    today = now_berlin().strftime("%Y-%m-%d")
    sent = log.setdefault("__sent__", [])
    for item in items:
        for t in (item.get("headline"), item.get("_raw_title")):
            if t:
                log[news_key(t)] = ts_h
        for u in (item.get("url"), item.get("_raw_url")):
            if u:
                log[url_key(u)] = ts_h
        sent.append({
            "ts": ts,
            "date_berlin": today,
            "event_key": item.get("event_key", ""),
            "headline": item.get("headline", ""),
            "fakt": item.get("fakt", "")[:200],
            "category": item.get("category", ""),
            "region": item.get("region", ""),
            "score": item.get("score", 0),
            "url": item.get("url", ""),
            "source_name": item.get("source_name", ""),
        })
    log["__sent__"] = sent[-400:]
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
        nb        = now_berlin()
        slot_name = SLOT_NAMES.get(min(SLOT_NAMES, key=lambda h: abs(h - nb.hour)), "📊")

        return (
            f"💼 <b>SILENT MONEY</b> — {slot_name}\n"
            f"{nb.strftime('%d.%m.%Y  %H:%M')} Berlin\n"
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
# (url, name, category, lang, region)

RSS_FEEDS = [
    # Krypto
    ("https://www.coindesk.com/arc/outboundfeeds/rss/",         "CoinDesk",         "crypto",  "en", "USA"),
    ("https://cointelegraph.com/rss",                            "Cointelegraph",    "crypto",  "en", "Global"),
    ("https://decrypt.co/feed",                                  "Decrypt",          "crypto",  "en", "USA"),
    ("https://theblock.co/rss.xml",                              "The Block",        "crypto",  "en", "USA"),
    ("https://blockworks.co/feed",                               "Blockworks",       "crypto",  "en", "USA"),
    ("https://bitcoinmagazine.com/.rss/full/",                   "Bitcoin Magazine", "crypto",  "en", "USA"),
    # Finanzen & Märkte USA
    ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml",           "WSJ Markets",      "finance", "en", "USA"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html",    "CNBC Finance",     "finance", "en", "USA"),
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html",   "CNBC Economy",     "macro",   "en", "USA"),
    ("https://fortune.com/feed/",                               "Fortune",          "finance", "en", "USA"),
    ("https://www.federalreserve.gov/feeds/press_all.xml",      "Federal Reserve",  "macro",   "en", "USA"),
    # Geopolitik / Welt
    ("https://feeds.a.dj.com/rss/RSSWorldNews.xml",             "WSJ World",        "geo",     "en", "Global"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml",             "BBC World",        "geo",     "en", "Global"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml",          "BBC Business",     "finance", "en", "Europa"),
    ("https://www.aljazeera.com/xml/rss/all.xml",               "Al Jazeera",       "geo",     "en", "Global"),
    # Europa
    ("https://www.ft.com/rss/home/uk",                          "Financial Times",  "finance", "en", "Europa"),
    ("https://www.ecb.europa.eu/rss/press.html",                "EZB",              "macro",   "en", "Europa"),
    ("https://www.handelsblatt.com/contentexport/feed/finanzen", "Handelsblatt",     "finance", "de", "Europa"),
    ("https://www.faz.net/rss/aktuell/finanzen/",               "FAZ Finanzen",     "finance", "de", "Europa"),
    ("https://www.btc-echo.de/feed/",                           "BTC-Echo",         "crypto",  "de", "Europa"),
    ("https://www.crypto-news-flash.com/de/feed/",              "Crypto News Flash","crypto",  "de", "Europa"),
    # Asien
    ("https://asia.nikkei.com/rss/feed/nar",                    "Nikkei Asia",      "finance", "en", "Asien"),
    ("https://www.scmp.com/rss/92/feed",                        "SCMP Business",    "finance", "en", "Asien"),
    # Afrika
    ("https://african.business/feed",                           "African Business", "finance", "en", "Afrika"),
    ("https://www.theafricareport.com/feed/",                   "The Africa Report","finance", "en", "Afrika"),
    # Russland
    ("https://forklog.com/feed/",                               "Forklog",          "crypto",  "ru", "Russland"),
    ("https://coinpost.ru/?feed=rss2",                          "CoinPost RU",      "crypto",  "ru", "Russland"),
    ("https://www.interfax.ru/rss.asp",                         "Interfax",         "finance", "ru", "Russland"),
    ("https://tass.com/rss/v2.xml",                             "TASS",             "finance", "en", "Russland"),
    # AI (nur Regulierung / Kapitalflüsse relevant)
    ("https://techcrunch.com/feed/",                            "TechCrunch",       "ai",      "en", "USA"),
    ("https://venturebeat.com/feed/",                           "VentureBeat",      "ai",      "en", "USA"),
]

# Twitter/X via Nitter RSS
NITTER_ACCOUNTS = [
    ("elonmusk",        "Elon Musk"),
    ("vitalikbuterin",  "Vitalik Buterin"),
    ("durov",           "Pavel Durov"),
    ("cz_binance",      "CZ Binance"),
    ("brian_armstrong", "Brian Armstrong"),
    ("realDonaldTrump", "Donald Trump"),
    ("federalreserve",  "Federal Reserve"),
    ("ECB",             "EZB"),
    ("michael_saylor",  "Michael Saylor"),
]

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]


def fetch_nitter(account: str, name: str) -> list[dict]:
    import xml.etree.ElementTree as ET
    for instance in NITTER_INSTANCES:
        try:
            url = f"{instance}/{account}/rss"
            r   = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
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
                        "region": "Global",
                    })
            if results:
                return results
        except Exception:
            continue
    return []


NEWSAPI_QUERIES = [
    ("crypto regulation SEC CFTC Congress",            "en", "USA"),
    ("Federal Reserve interest rates decision",        "en", "USA"),
    ("ECB MiCA regulation eurozone",                   "en", "Europa"),
    ("sanctions tariffs trade war export controls",    "en", "Global"),
    ("China PBOC yuan capital controls",               "en", "Asien"),
    ("Japan BOJ yen intervention",                     "en", "Asien"),
    ("Russia ruble central bank sanctions oil",        "en", "Russland"),
    ("Africa central bank IMF debt Nigeria Kenya",     "en", "Afrika"),
    ("OPEC oil output decision",                       "en", "Global"),
    ("Bitcoin reserve government central bank gold",   "en", "Global"),
    ("BlackRock ETF institutional inflows",            "en", "USA"),
    ("AI regulation law EU AI Act",                    "en", "Europa"),
    ("Krypto BaFin EZB Regulierung",                   "de", "Europa"),
    ("Sanktionen Zölle Bundesbank Zinsen",             "de", "Europa"),
]


def fetch_rss(url, source, cat, lang, region="Global"):
    import xml.etree.ElementTree as ET
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out  = []
        for item in root.findall(".//item")[:15]:
            t = (item.findtext("title") or "").strip()
            l = (item.findtext("link")  or "").strip()
            d = (item.findtext("description") or "")[:300]
            if t and l:
                out.append({"title": t, "url": l, "source": source,
                            "description": d, "category": cat, "lang": lang,
                            "region": region})
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
                 "description": "", "category": "crypto", "lang": "en", "region": "Global"}
                for i in r.json().get("results",[])[:30]]
    except Exception as e:
        print(f"[CryptoPanic]: {e}"); return []


def fetch_newsapi(query, lang, region):
    if not NEWS_API_KEY:
        return []
    since = (now_utc() - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        r = requests.get("https://newsapi.org/v2/everything",
                         params={"apiKey": NEWS_API_KEY, "q": query, "from": since,
                                 "language": lang, "sortBy": "publishedAt", "pageSize": 10},
                         timeout=15)
        r.raise_for_status()
        return [{"title": a.get("title",""), "url": a.get("url",""),
                 "source": a.get("source",{}).get("name","NewsAPI"),
                 "description": (a.get("description") or "")[:300],
                 "category": "finance", "lang": lang, "region": region}
                for a in r.json().get("articles",[]) if a.get("title") and a.get("url")]
    except Exception as e:
        print(f"[NewsAPI] {query}: {e}"); return []


def fetch_all() -> list:
    print("📡 Sammle Nachrichten...")
    all_n = []
    all_n.extend(fetch_cryptopanic())
    for q, l, reg in NEWSAPI_QUERIES:
        all_n.extend(fetch_newsapi(q, l, reg))
    for args in RSS_FEEDS:
        all_n.extend(fetch_rss(*args))

    print("🐦 Sammle Tweets...")
    for account, name in NITTER_ACCOUNTS:
        tweets = fetch_nitter(account, name)
        all_n.extend(tweets)
        if tweets:
            print(f"  ✅ @{account}: {len(tweets)} Tweets")

    seen, unique = set(), []
    for n in all_n:
        k = n["title"][:80].lower()
        if k not in seen and n["title"] and n["url"]:
            seen.add(k); unique.append(n)

    # Reihenfolge mischen: sonst entscheidet die Feed-Reihenfolge, was Claude sieht
    random.shuffle(unique)
    print(f"✅ {len(unique)} einzigartige Nachrichten gesammelt")
    return unique


# ─── CLAUDE ───────────────────────────────────────────────────────────────────

def build_candidates_json(news: list) -> str:
    """Kompakte Kandidatenliste; URL bleibt draußen (wird per Index zurückgemappt)."""
    items, size = [], 0
    for i, n in enumerate(news):
        it = {"i": i, "t": n["title"][:160], "s": n["source"],
              "r": n.get("region", "Global"), "d": n.get("description", "")[:120]}
        s = json.dumps(it, ensure_ascii=False)
        if size + len(s) > NEWS_CHAR_CAP:
            break
        items.append(it); size += len(s) + 1
    if len(items) < len(news):
        print(f"⚠️ Zeichenbudget: {len(items)} von {len(news)} Kandidaten an Claude")
    return json.dumps(items, ensure_ascii=False)


def sent_history_str(sent: list) -> str:
    if not sent:
        return "none"
    lines = []
    for s in sent[-120:]:
        d = s.get("ts", "")[:16].replace("T", " ")
        lines.append(f"- [{d} UTC] key={s.get('event_key','?')} | {s.get('headline','')} | {s.get('fakt','')[:100]}")
    return "\n".join(lines)


def call_claude(prompt: str, max_tokens: int) -> str:
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip().rstrip("```").strip()


def summarize(news: list, sent_72h: list, geo_budget: int) -> list:
    now = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    candidates = build_candidates_json(news)
    history    = sent_history_str(sent_72h)

    prompt = f"""You are the editor of "Silent Money", a German-language Telegram channel for financial, macro and geopolitical news. Current time: {now}.

ROLE
You are a precise information filter, not a journalist and not a trader. No recommendations, no opinions, no asset valuations, no predictions.

MISSION
Select only news with real impact on markets, capital flows, economic conditions or systemic/geopolitical stability. Everything else is ignored. Quality over quantity: selecting 0 is acceptable; selecting 5 weak items is a failure.

CORE TEST for every item: "Does this change markets, the economy, the financial system or capital flows?" If no → do not select.

STATE CHANGE vs. NORMAL STATE
Prefer B) a change of state (escalation, turning point, new phase, new measure, new decision) over A) a normal event within an existing state. A) only if clear economic impact exists.

TOPIC SCOPE (daily)
- Central banks, rates, inflation (Fed, ECB, BoJ, PBoC, CBR, SNB, BoE, African central banks)
- Regulation of finance, banks, crypto (SEC, CFTC, MiCA, BaFin, FCA, Japan FSA, UAE, Russia, Congress)
- Government actions: buying/selling Bitcoin, gold or other assets; capital controls; currency policy; strategic economic decisions — HIGH PRIORITY, always consider
- Geopolitics ONLY with economic transmission: energy (oil/gas), sanctions, supply chains, major economies involved, currency/capital-flow impact, military escalation with international reaction
- Institutional capital moves: ETF flows with cause, sovereign funds, large allocations, bank strategy shifts
- Major corporate decisions with market impact (earnings that move sectors, M&A, defaults)
- Crypto market structure: exchange failures, hacks above ~$50M, protocol-level changes, stablecoin regulation
- AI only when it concerns regulation, capital flows or market structure — not product launches
- Tweets only if a key figure announces something concrete and market-relevant

REGIONS
Cover USA, Europe, Asia, Africa and Russia. Do not let US sources crowd out the rest: if a comparably strong story exists from Asia, Africa, Russia or Europe, prefer it over a weaker US story.

NOT RELEVANT (never select)
- opinions, analyst views, "could", "may", "signals", "experts say"
- speculation without new facts, historical-pattern pieces, price moves without a cause
- social-media hype, product launches, personnel gossip, crime stories without systemic impact
- local events without wider effect
- conflict reports without economic consequences; political statements without concrete measures
- anything already covered in the last 72h (see below) unless it contains a genuinely new development

ALREADY SENT IN THE LAST 72H (event_key | headline | fact):
{history}

DEDUPLICATION RULES (strict)
- Assign every candidate an event_key: lowercase, 2-4 words, hyphenated, naming the ENTITY and the EVENT, stable across different wordings and outlets. Examples: "cysic-bridge-exploit", "fed-rate-decision-oct", "msci-bitcoin-index-exclusion". Two articles about the same event MUST get the same event_key, even if numbers or wording differ.
- If the event_key matches an already-sent item, select it ONLY if there is a genuinely new development (new official measure, court ruling, new confirmed figures changing the picture, new party acting). Then set "is_new_development": true and state in "what_is_new" one sentence naming exactly what is new. A second outlet reporting the same thing, a recap, a follow-up without new facts, or a restated number is NOT new.
- Among the candidates, one post per event. Keep the strongest source.

GEOPOLITICS BUDGET
Category "geopolitik" has a daily cap. Remaining budget today: {geo_budget}. Select at most {geo_budget} items with category "geopolitik". If the budget is 0, select none.

SCORING (score 1-10, be strict)
10 = central bank decision, sanctions regime, sovereign asset purchase, systemic failure
8-9 = new regulation in force, major capital-flow shift with cause, escalation with energy/currency effect
7 = confirmed decision by a major institution with clear but limited market effect
≤6 = everything weaker → do not select
Only items with score ≥ {MIN_SCORE} will be published. Select at most {MAX_PER_SLOT}.

OUTPUT (German, Reuters tone: factual, calm, no emotion, no hype, no recommendation)
Return ONLY a JSON array, no code fences, no commentary:
[{{"index": 3,
   "event_key": "fed-rate-decision-oct",
   "category": one of {CATEGORIES},
   "region": one of {REGIONS},
   "score": 9,
   "is_new_development": false,
   "what_is_new": "",
   "emoji": "🏛",
   "headline": "max 10 words, pure fact, no clickbait",
   "fakt": "1-2 sentences: what happened (who, what, numbers, date)",
   "kontext": "1-2 sentences: in which context this stands",
   "warum": "1-2 sentences: possible impact on markets, economy or capital — factual, no prediction language like 'could rally'",
   "source_name": "outlet name"}}]

"index" must be the "i" of the candidate. Facts must come from the candidate text; do not invent numbers.

CANDIDATES:
{candidates}
"""

    print(f"🤖 Claude wählt aus ({CLAUDE_MODEL})...")
    try:
        text = call_claude(prompt, max_tokens=5000)
        result = json.loads(text)
    except Exception as e:
        print(f"❌ JSON: {e}")
        return []

    out = []
    for item in result:
        idx = item.get("index")
        if not (isinstance(idx, int) and 0 <= idx < len(news)):
            continue
        item["_raw_title"] = news[idx]["title"]
        item["_raw_url"]   = news[idx]["url"]
        item["url"]        = news[idx]["url"]
        item.setdefault("source_name", news[idx]["source"])
        item["score"]      = int(item.get("score", 0) or 0)
        item["event_key"]  = (item.get("event_key") or "").strip().lower()
        out.append(item)
    print(f"✅ Claude: {len(out)} Vorschläge")
    return out


def enforce_rules(selected: list, sent_72h: list, geo_budget: int) -> list:
    """Harte Regeln im Code — unabhängig davon, was Claude behauptet."""
    sent_keys = {s.get("event_key") for s in sent_72h if s.get("event_key")}
    kept, seen_keys, geo_used = [], set(), 0
    for it in sorted(selected, key=lambda x: -x.get("score", 0)):
        hl = it.get("headline", "")[:55]
        if it["score"] < MIN_SCORE:
            print(f"  ✂️ Score {it['score']} < {MIN_SCORE}: {hl}"); continue
        if not it.get("headline") or not it.get("fakt"):
            print(f"  ✂️ Unvollständig: {hl}"); continue
        k = it.get("event_key")
        if k in seen_keys:
            print(f"  ✂️ Doppelt im Batch ({k}): {hl}"); continue
        if k in sent_keys and not (it.get("is_new_development") and it.get("what_is_new")):
            print(f"  ✂️ Bereits gesendet ({k}): {hl}"); continue
        if it.get("category") == "geopolitik":
            if geo_used >= geo_budget:
                print(f"  ✂️ Geo-Budget erschöpft: {hl}"); continue
            geo_used += 1
        seen_keys.add(k)
        kept.append(it)
        if len(kept) >= MAX_PER_SLOT:
            break
    return kept


def self_check_duplicates(selected: list, sent_72h: list) -> list:
    """Zweite Prüfung: dasselbe Ereignis trotz anderem event_key?"""
    if not selected:
        return selected

    sel_json = json.dumps(
        [{"i": i, "key": s.get("event_key"), "headline": s.get("headline"), "fakt": s.get("fakt", "")[:200]}
         for i, s in enumerate(selected)], ensure_ascii=False)
    history = sent_history_str(sent_72h)

    prompt = f"""Final duplicate check before publishing.

SELECTED (to be published now):
{sel_json}

ALREADY SENT IN THE LAST 72H:
{history}

RULE
Remove a selected item if it covers the same event as an already-sent item (same entity, same action — even with different wording, different source, different numbers or a different event_key) UNLESS it reports a genuinely new development: a new official measure, a ruling, a new acting party, or confirmed figures that change the picture. A second source, a recap, a reaction piece or a restated number is NOT new.
Also remove items that duplicate each other within SELECTED (keep the first).

Answer ONLY with a JSON array of the indices to KEEP, e.g. [0, 2]. An empty array [] is a valid answer."""

    try:
        text = call_claude(prompt, max_tokens=100)
        keep = json.loads(text)
        if not isinstance(keep, list):
            raise ValueError("no list")
        result = [selected[i] for i in keep if isinstance(i, int) and 0 <= i < len(selected)]
        removed = len(selected) - len(result)
        if removed:
            print(f"🔍 Selbstprüfung: {removed} Duplikat(e) entfernt")
        return result
    except Exception as e:
        print(f"[Selbstprüfung] Fehler: {e} — Auswahl bleibt")
        return selected


def weekly_recap(sent_week: list) -> list:
    """Sonntag 20:00: Top 7 der Woche aus der eigenen Sendehistorie."""
    if not sent_week:
        return []
    items = json.dumps(
        [{"i": i, "headline": s.get("headline"), "fakt": s.get("fakt"), "category": s.get("category"),
          "region": s.get("region"), "score": s.get("score"), "date": s.get("date_berlin")}
         for i, s in enumerate(sent_week)], ensure_ascii=False)
    prompt = f"""From the posts "Silent Money" published this week, choose the 7 events with the greatest impact on markets, the economy or the financial system. Prefer state changes over routine; avoid two items about the same story; keep regional balance where justified.

POSTS:
{items}

Return ONLY a JSON array (German, factual, Reuters tone), ordered by importance:
[{{"index": 3, "emoji": "🏛", "headline": "max 10 words", "fakt": "1 sentence what happened", "warum": "1 sentence why it mattered"}}]"""
    try:
        result = json.loads(call_claude(prompt, max_tokens=3000))
        out = []
        for it in result[:7]:
            idx = it.get("index")
            if isinstance(idx, int) and 0 <= idx < len(sent_week):
                it["url"] = sent_week[idx].get("url", "")
                it["source_name"] = sent_week[idx].get("source_name", "")
                out.append(it)
        return out
    except Exception as e:
        print(f"[Wochenrückblick] {e}")
        return []


# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send(text: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15)
        r.raise_for_status(); return True
    except Exception as e:
        print(f"[TG] {e}"); return False


def format_post(it: dict) -> str:
    new_line = f"\n🆕 <i>Neu: {esc(it['what_is_new'])}</i>\n" if it.get("is_new_development") and it.get("what_is_new") else ""
    return (
        f"{it.get('emoji','📌')} <b>{esc(it.get('headline',''))}</b>\n"
        f"{new_line}\n"
        f"<b>FAKT:</b> {esc(it.get('fakt',''))}\n\n"
        f"<b>KONTEXT:</b> {esc(it.get('kontext',''))}\n\n"
        f"<b>WARUM ES WICHTIG IST:</b> {esc(it.get('warum',''))}\n\n"
        f"📰 <a href=\"{it.get('url','')}\">{esc(it.get('source_name',''))}</a>"
    )


def format_weekly(it: dict, n: int) -> str:
    return (
        f"{n}. {it.get('emoji','📌')} <b>{esc(it.get('headline',''))}</b>\n"
        f"{esc(it.get('fakt',''))} {esc(it.get('warum',''))}"
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    nb        = now_berlin()
    is_weekly = nb.weekday() == 6 and nb.hour >= 19

    print(f"\n{'─'*50}")
    print(f"🤫💰 SILENT MONEY | {nb.strftime('%Y-%m-%d %H:%M')} Berlin | {CLAUDE_MODEL}")
    print(f"{'─'*50}\n")

    log = clean_log(load_log())
    sent_72h = sent_within(log, DEDUP_HOURS)
    print(f"📋 Log: {len([k for k in log if not k.startswith('__')])} Hashes, {len(sent_72h)} Events/72h")

    # ── Sonntag: Wochenrückblick aus eigener Historie ──
    if is_weekly:
        week = sent_within(log, 24 * 7)
        top  = weekly_recap(week)
        if not top:
            print("❌ Kein Wochenrückblick möglich"); return
        header = (f"📅 <b>SILENT MONEY — Wochenrückblick</b>\n"
                  f"{nb.strftime('%d.%m.%Y')} · Die 7 wichtigsten Ereignisse\n\n")
        body = "\n\n".join(format_weekly(it, i) for i, it in enumerate(top, 1))
        send(header + body)
        log["__weekly_date__"] = nb.strftime("%Y-%m-%d")
        save_log(log)
        print("✅ Wochenrückblick gesendet")
        return

    raw = fetch_all()
    if not raw:
        print("❌ Keine Nachrichten"); return

    filtered = filter_sent(raw, log)
    if not filtered:
        print("ℹ️ Nichts Neues — kein Post"); return

    geo_budget = max(0, GEO_MAX_PER_DAY - geo_sent_today(log))
    print(f"🌍 Geo-Budget heute: {geo_budget}")

    selected = summarize(filtered, sent_72h, geo_budget)
    selected = enforce_rules(selected, sent_72h, geo_budget)
    selected = self_check_duplicates(selected, sent_72h)

    if not selected:
        print("ℹ️ Nichts über der Schwelle — kein Post (das ist gewollt)")
        save_log(log)
        return

    if not prices_shown_today(log):
        send(fetch_market_snapshot())
        log = mark_prices(log)
        time.sleep(3)

    sent_ok = []
    for i, it in enumerate(selected, 1):
        ok = send(format_post(it))
        print(f"{'✅' if ok else '❌'} [{i}] {it.get('score')}/10 {it.get('category')}/{it.get('region')} · {it.get('headline','')[:55]}")
        if ok:
            sent_ok.append(it)
        time.sleep(3)

    log = mark_sent(sent_ok, log)
    save_log(log)
    print(f"\n✅ Fertig: {len(sent_ok)} Posts | Events/72h: {len(sent_within(log, DEDUP_HOURS))}")


if __name__ == "__main__":
    main()
