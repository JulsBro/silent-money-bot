"""
Silent Money — Wohnungssuche Bot
Berlin-Schöneweide | bis 200.000 € | ab 40 m² | ab 2 Zimmer
"""

import os
import json
import time
import logging
import requests
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
APARTMENT_CHANNEL_ID = os.environ["APARTMENT_CHANNEL_ID"]

SEEN_FILE = "seen_apartments.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


# ─── PERSISTENZ ───────────────────────────────────────────────────────────────

def load_seen() -> dict:
    try:
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE) as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"[Seen] Ladefehler: {e}")
    return {}


def save_seen(seen: dict) -> None:
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(seen, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"[Seen] Speicherfehler: {e}")


# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def send(text: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": APARTMENT_CHANNEL_ID, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Telegram Fehler: {e}")
        return False


# ─── SCRAPER: ImmoScout24 ───────────────────────────────────────────────────────

def scrape_immoscout() -> list:
    results = []
    url = (
        "https://www.immobilienscout24.de/Suche/de/berlin/berlin/"
        "wohnung-kaufen?price=-200000&livingspace=40.0-&numberofrooms=2.0-"
        "&geocodes=1276004007286&pagenumber=1"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select("li[id^='result-']"):
            try:
                lid = "is24_" + item.get("id", "")
                title = (item.select_one(".result-list-entry__brand-title-container")
                         or item.select_one("h5") or item.select_one("h3"))
                title = title.get_text(strip=True) if title else "Wohnung"
                price = item.select_one("dd.result-list-entry__primary-criterion")
                price = price.get_text(strip=True) if price else "?"
                link_el = item.select_one("a[href*='/expose/']")
                link = f"https://www.immobilienscout24.de{link_el['href']}" if link_el else ""
                results.append({"id": lid, "title": title, "price": price, "link": link, "source": "ImmoScout24"})
            except Exception:
                continue
    except Exception as e:
        logging.error(f"ImmoScout24: {e}")
    return results


# ─── SCRAPER: Kleinanzeigen ─────────────────────────────────────────────────────

def scrape_kleinanzeigen() -> list:
    results = []
    url = (
        "https://www.kleinanzeigen.de/s-wohnung-kaufen/berlin/"
        "schoeneweide/preis:-200000/c196l3331+wohnung_kaufen.qm_d:40,"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select("article.aditem"):
            try:
                lid = "ka_" + item.get("data-adid", "")
                title_el = item.select_one(".ellipsis")
                title = title_el.get_text(strip=True) if title_el else "Wohnung"
                price_el = item.select_one(".aditem-main--middle--price-shipping--price")
                price = price_el.get_text(strip=True) if price_el else "?"
                link_el = item.select_one("a.ellipsis")
                link = f"https://www.kleinanzeigen.de{link_el['href']}" if link_el else ""
                results.append({"id": lid, "title": title, "price": price, "link": link, "source": "Kleinanzeigen"})
            except Exception:
                continue
    except Exception as e:
        logging.error(f"Kleinanzeigen: {e}")
    return results


# ─── SCRAPER: Immowelt ──────────────────────────────────────────────────────────

def scrape_immowelt() -> list:
    results = []
    url = (
        "https://www.immowelt.de/liste/berlin-schoeneweide/wohnungen/kaufen"
        "?cyp=200000&rms=2&wfl=40"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select("div[data-testid='serp-core-classified-card-testid']"):
            try:
                link_el = item.select_one("a[href]")
                lid = "iw_" + (link_el["href"].split("/")[-2] if link_el else str(time.time()))
                title_el = item.select_one("h2")
                title = title_el.get_text(strip=True) if title_el else "Wohnung"
                price_el = item.select_one("[data-testid='price']")
                price = price_el.get_text(strip=True) if price_el else "?"
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.immowelt.de" + link
                results.append({"id": lid, "title": title, "price": price, "link": link, "source": "Immowelt"})
            except Exception:
                continue
    except Exception as e:
        logging.error(f"Immowelt: {e}")
    return results


# ─── SCRAPER: Immonet ───────────────────────────────────────────────────────────

def scrape_immonet() -> list:
    results = []
    url = (
        "https://www.immonet.de/immobiliensuche/sel.do?sortby=19&such=1"
        "&objecttype=1&dealtype=1&parentcat=1&locality=110433"
        "&priceto=200000&areaFrom=40&numRooms=2"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select("div[id^='selObject_']"):
            try:
                lid = "in_" + item.get("id", "")
                title_el = item.select_one(".ellipsis-title") or item.select_one("h3")
                title = title_el.get_text(strip=True) if title_el else "Wohnung"
                price_el = item.select_one(".text-700")
                price = price_el.get_text(strip=True) if price_el else "?"
                link_el = item.select_one("a[href]")
                link = f"https://www.immonet.de{link_el['href']}" if link_el else ""
                results.append({"id": lid, "title": title, "price": price, "link": link, "source": "Immonet"})
            except Exception:
                continue
    except Exception as e:
        logging.error(f"Immonet: {e}")
    return results


def fetch_all() -> list:
    results = []
    results += scrape_immoscout()
    results += scrape_kleinanzeigen()
    results += scrape_immowelt()
    results += scrape_immonet()
    return results


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    logging.info("🔍 Suche läuft...")
    seen = load_seen()

    neu = 0
    for item in fetch_all():
        lid = item["id"]
        if not lid or lid in seen:
            continue
        seen[lid] = {"title": item["title"], "url": item["link"]}
        msg = (
            f"🏠 <b>{item['title']}</b>\n"
            f"💰 {item['price']}\n"
            f"📡 {item['source']}\n"
            f"🔗 {item['link']}"
        )
        if send(msg):
            neu += 1
        time.sleep(1)

    save_seen(seen)
    logging.info(f"✅ {neu} neue Angebote")


if __name__ == "__main__":
    main()
