"""
Объявления об аренде квартир в Астане с Krisha.kz + геокодирование адресов.

Krisha закрывает страницы отдельных объявлений антибот-защитой, поэтому
скрипт читает только страницы списка (цена, площадь, комнаты, адрес),
а координаты получает по адресу через OpenStreetMap Nominatim.

Этап 1: страницы списка -> data/raw/krisha_listings.csv   (~15 мин)
Этап 2: геокодирование   -> data/raw/krisha_geocoded.csv  (~1–1,5 ч)

Запуск: python src/scrapers/scrape_krisha.py  (сначала TEST = True).
При остановке перезапустите — сбор продолжится с места остановки.
"""
import html as htmllib
import random
import re
import time
from pathlib import Path

import pandas as pd
import requests
from selenium import webdriver

TEST = True
MAX_PAGES = 261
URL = "https://krisha.kz/arenda/kvartiry/astana/?page={}"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
LISTINGS = RAW / "krisha_listings.csv"
GEO = RAW / "krisha_geocoded.csv"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "astana-lounge-research/1.0"}


def open_browser():
    try:
        return webdriver.Chrome()
    except Exception:
        return webdriver.Edge()


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).replace("\xa0", " ").strip()


def parse_cards(html):
    """Карточки объявлений на странице списка."""
    rows = []
    for block in re.split(r'(?=<div\s+data-id="\d+"\s+data-uuid=)', html)[1:]:
        lid = re.search(r'data-id="(\d+)"', block).group(1)
        t = re.search(r'class="a-card__title[^"]*"[^>]*>(.*?)</a>', block, re.S)
        p = re.search(r'class="a-card__price">(.*?)</div>', block, re.S)
        a = re.search(r'class="a-card__subtitle[^"]*">(.*?)</div>', block, re.S)
        if not (t and p and a):
            continue
        title, price_txt, addr = clean(t.group(1)), clean(p.group(1)), clean(a.group(1))
        area = re.search(r"([\d.]+)\s*м²", title)
        rooms = re.search(r"(\d+)-комнатная", title)
        price = re.sub(r"\D", "", price_txt.split("₸")[0])
        district, _, street = addr.partition(",")
        if "р-н" not in district:
            district, street = "", addr
        rows.append({"id": int(lid), "price": int(price) if price else None,
                     "area_m2": float(area.group(1)) if area else None,
                     "rooms": int(rooms.group(1)) if rooms else None,
                     "period": "month" if "за месяц" in price_txt else ("day" if "сутки" in price_txt else price_txt),
                     "district": district.strip(), "address": street.strip(), "title": title})
    return rows


def collect_listings():
    done = set(pd.read_csv(LISTINGS)["page"]) if LISTINGS.exists() else set()
    last = 2 if TEST else MAX_PAGES
    todo = [p for p in range(1, last + 1) if p not in done]
    if not todo:
        return
    driver = open_browser()
    try:
        for page in todo:
            driver.get(URL.format(page))
            rows = []
            for i in range(240):  # если появилась проверка — ждём до 2 минут
                time.sleep(0.5)
                rows = parse_cards(driver.page_source)
                if rows:
                    break
                if i == 10:
                    print("   ⚠ Страница не открывается. Если появился слайдер — передвиньте его один раз.")
            if not rows:
                print(f"Страница {page}: нет данных, останавливаюсь. Перезапустите позже.")
                break
            df = pd.DataFrame(rows)
            df["page"] = page
            df.to_csv(LISTINGS, mode="a", header=not LISTINGS.exists(), index=False, encoding="utf-8-sig")
            print(f"Страница {page}/{last}: {len(rows)} объявлений")
            time.sleep(random.uniform(2, 4))
    finally:
        driver.quit()


def normalize(a):
    """Упрощение адреса для Nominatim."""
    a = re.sub(r"^мкр\s+[^,]+,\s*", "", a)                       # «мкр Пригородный, ...»
    a = re.sub(r"^(ул\.|улица|пр\.|проспект)\s*", "", a, flags=re.I)
    a = re.sub(r"^[А-ЯӘІҢҒҮҰҚӨҺ]\.\s*", "", a)                     # «Ч.Айтматова» -> «Айтматова»
    return (a.split(",")[0] if re.search(r"\d.*,", a) else a).strip()  # «Толе би 25, 25А» -> «Толе би 25»


def geocode_one(q):
    r = requests.get(NOMINATIM, headers=UA, timeout=30, params={
        "q": f"{q}, Астана, Казахстан", "format": "json", "limit": 1,
        "viewbox": "71.20,51.30,71.70,51.00", "bounded": 1})
    time.sleep(1.5)  # правило Nominatim: не более 1 запроса в секунду
    if r.status_code != 200:
        raise PermissionError(f"Nominatim {r.status_code}")  # блокировка: результат не записываем
    if not r.json():
        return None
    j = r.json()[0]
    # если вернулся сам город или район — это не адрес
    if j.get("addresstype") in ("city", "state", "country", "city_district", "suburb") \
            or j.get("type") in ("city", "administrative"):
        return None
    house = j.get("addresstype") in ("building", "house") or j.get("class") == "building" \
        or j.get("type") in ("house", "apartments", "residential", "yes")
    return float(j["lat"]), float(j["lon"]), "house" if house else "street"


def geocode():
    df = pd.read_csv(LISTINGS).drop_duplicates("id")
    addr = df["address"].dropna().str.split(" — ").str[0].str.strip()
    unique = addr[addr.str.contains(r"\d")].value_counts().index.tolist()  # только с номером дома
    done = set(pd.read_csv(GEO)["address"]) if GEO.exists() else set()
    todo = [a for a in unique if a not in done][: 15 if TEST else None]
    print(f"\nЭтап 2: геокодирование {len(todo)} адресов")
    for n, a in enumerate(todo, 1):
        for attempt in range(3):
            try:
                res = geocode_one(a)
                if res is None and normalize(a) != a:
                    res = geocode_one(normalize(a))
                break
            except Exception as e:
                if attempt == 2:
                    print(f"\nNominatim не отвечает ({e}). Перезапустите через 30 минут.")
                    return
                print(f"   {a}: {e}. Жду 2 минуты...")
                time.sleep(120)
        lat, lon, prec = res if res else (None, None, "")
        pd.DataFrame([{"address": a, "lat": lat, "lon": lon, "precision": prec}]).to_csv(
            GEO, mode="a", header=not GEO.exists(), index=False, encoding="utf-8-sig")
        if n % 25 == 0 or TEST:
            print(f"{n}/{len(todo)}: {a} -> {lat}, {lon} {prec}")
    g = pd.read_csv(GEO)
    print(f"\nНайдены координаты: {g['lat'].notna().sum()} из {len(g)} адресов")


def main():
    collect_listings()
    if LISTINGS.exists():
        print(f"\nЭтап 1: {pd.read_csv(LISTINGS)['id'].nunique()} уникальных объявлений")
        geocode()


if __name__ == "__main__":
    main()
