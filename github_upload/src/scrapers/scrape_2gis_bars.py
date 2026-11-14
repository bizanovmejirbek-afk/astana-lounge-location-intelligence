# -*- coding: utf-8 -*-
import csv
import json
import math
import random
import re
import sys
import time
from datetime import date, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

# ======================== БАПТАУЛАР ========================
QUERIES = ["лаундж-бар", "лаунж бар", "lounge bar"]
BASE = "https://2gis.kz/astana/search/"
MAX_PAGES = 40
SLEEP_MIN, SLEEP_MAX = 1.0, 2.0
HEADLESS = False
STRICT_FILTER = True
OUTPUT_FILE = f"astana_lounge_bars_{date.today().isoformat()}.csv"
NA = "data unavailable"
# ===========================================================

COLUMNS = [
    "id", "restaurant_name", "address", "latitude", "longitude",
    "restaurant_type", "comp_500m", "comp_1km", "comp_2km",
    "nearby_building_purpose", "district", "rating_2gis", "reviews_2gis",
    "price_level", "delivery_available", "delivery_platform", "status",
    "krisha_median_price_m2_nearby", "source", "date_collected",
]
DISTRICTS = [
    (("есил", "есіл", "esil", "yesil"), "Есіл"),
    (("алматы", "almaty"), "Алматы"),
    (("байконыр", "байқоңыр", "байконур", "baikonur"), "Байқоңыр"),
    (("нура", "нұра", "nura"), "Нұра"),
    (("сарыарка", "сарыарқа", "saryarka"), "Сарыарқа"),
    (("сарайшык", "сарайшық", "saraishyk"), "Сарайшық"),
]
KEYWORDS = ("lounge", "лаундж", "лаунж", "лаунд", "кальян")
BLOCK_MARKERS = ("captcha", "доступ ограничен", "подозрительн", "access denied")


def pause(extra=0.0):
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX) + extra)


def walk(obj, out):
    if isinstance(obj, dict):
        p = obj.get("point")
        if (obj.get("id") and obj.get("name") and isinstance(p, dict)
                and "lat" in p and "lon" in p):
            out[str(obj["id"])] = obj
        for v in obj.values():
            walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, out)


def is_blocked(page):
    try:
        text = (page.content() or "").lower()
    except Exception:
        return False
    return any(m in text for m in BLOCK_MARKERS)


def scrape_query(page, query, store):
    captured = {}

    def on_response(resp):
        try:
            if "application/json" in (resp.headers.get("content-type") or ""):
                if "2gis" in resp.url and "/items" in resp.url:
                    walk(resp.json(), captured)
        except Exception:
            pass

    page.on("response", on_response)
    try:
        for n in range(1, MAX_PAGES + 1):
            url = BASE + quote(query) + ("" if n == 1 else f"/page/{n}")
            print(f"[{query}] бет {n}: {url}")
            captured.clear()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            if is_blocked(page):
                print("!!! CAPTCHA / қолжетімділік шектелді - тоқтатылды.")
                return False

            try:
                state = page.evaluate("() => window.initialState || null")
                if state:
                    walk(state, captured)
            except Exception:
                pass

            for _ in range(3):
                page.mouse.wheel(0, 2500)
                time.sleep(0.5)

            new = [k for k in captured if k not in store]
            for k in new:
                store[k] = captured[k]
            print(f"   табылды: {len(captured)}, жаңа: {len(new)}, барлығы: {len(store)}")
            pause()
            if not new:
                break
    finally:
        page.remove_listener("response", on_response)
    return True


def looks_like_lounge(it):
    if not STRICT_FILTER:
        return True
    rubrics = " ".join(r.get("name", "") for r in (it.get("rubrics") or []) if isinstance(r, dict))
    text = f"{it.get('name', '')} {json.dumps(it.get('name_ex', ''), ensure_ascii=False)} {rubrics}".lower()
    if any(k in text for k in KEYWORDS):
        return True
    return "lounge" in json.dumps(it, ensure_ascii=False).lower()


def get_district(it):
    for d in it.get("adm_div") or []:
        if isinstance(d, dict) and d.get("type") == "district":
            n = d.get("name", "").lower()
            for keys, label in DISTRICTS:
                if any(k in n for k in keys):
                    return label
    blob = (it.get("address_name", "") or "").lower()
    for keys, label in DISTRICTS:
        if any(k in blob for k in keys):
            return label
    return NA


def get_status(it):
    sch = it.get("schedule")
    if not isinstance(sch, dict) or not sch:
        return NA
    if sch.get("is_24x7"):
        return "ашық"
    now = datetime.now(ZoneInfo("Asia/Almaty"))
    day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][now.weekday()]
    hours = (sch.get(day) or {}).get("working_hours")
    if not hours:
        return "жабық"
    cur = now.strftime("%H:%M")
    for h in hours:
        a, b = h.get("from", "00:00"), h.get("to", "24:00")
        if (a <= b and a <= cur <= b) or (a > b and (cur >= a or cur <= b)):
            return "ашық"
    return "жабық"


def get_building(it):
    addr = it.get("address") or {}
    if isinstance(addr, dict) and addr.get("building_name"):
        return addr["building_name"]
    m = re.search(r"(ЖК|БЦ|ТРЦ|ТРК|ТД)\s*[«\"]?[\w\- ]+", it.get("address_name", "") or "")
    return m.group(0).strip() if m else NA


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def build_rows(items):
    today = date.today().isoformat()
    rows = []
    for i, it in enumerate(items, 1):
        pt = it.get("point") or {}
        rev = it.get("reviews") or {}
        blob = json.dumps(it, ensure_ascii=False).lower()
        platform = [p for p in ("wolt", "glovo") if p in blob]
        has_deliv = "достав" in blob or bool(platform)
        price = re.search(r"₸{1,3}", blob)
        rating = rev.get("general_rating", rev.get("org_rating"))
        count = rev.get("general_review_count", rev.get("org_review_count"))
        rows.append({
            "id": i,
            "restaurant_name": it.get("name") or NA,
            "address": it.get("address_name") or NA,
            "latitude": pt.get("lat", ""),
            "longitude": pt.get("lon", ""),
            "restaurant_type": "lounge_bar",
            "comp_500m": "", "comp_1km": "", "comp_2km": "",
            "nearby_building_purpose": get_building(it),
            "district": get_district(it),
            "rating_2gis": rating if rating is not None else NA,
            "reviews_2gis": count if count is not None else NA,
            "price_level": price.group(0) if price else NA,
            "delivery_available": "Иә" if has_deliv else "Жоқ",
            "delivery_platform": ", ".join(p.capitalize() for p in platform) if platform else NA,
            "status": get_status(it),
            "krisha_median_price_m2_nearby": NA,
            "source": "2GIS (web)",
            "date_collected": today,
        })
    return rows


def compute_density(rows):
    pts = [(r, r["latitude"], r["longitude"]) for r in rows if r["latitude"] != ""]
    for r, lat, lon in pts:
        c5 = c1 = c2 = 0
        for o, olat, olon in pts:
            if o is r:
                continue
            d = haversine(lat, lon, olat, olon)
            c5 += d <= 500
            c1 += d <= 1000
            c2 += d <= 2000
        r["comp_500m"], r["comp_1km"], r["comp_2km"] = c5, c1, c2


def save_csv(rows):
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def report(rows):
    print("\n=========== ТЕКСЕРУ ===========")
    print(f"1) Барлығы табылған лаундж-бар: {len(rows)}")
    print("2) 'data unavailable' жол саны:")
    for col in COLUMNS:
        n = sum(1 for r in rows if str(r[col]) == NA)
        if n:
            print(f"   {col}: {n}")
    print(f"3) comp_* есептелмеген жол: {sum(1 for r in rows if r['comp_500m'] == '')}")
    print(f"Файл: {OUTPUT_FILE}")


def main():
    store = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(
            locale="ru-RU", viewport={"width": 1366, "height": 800},
            timezone_id="Asia/Almaty",
        )
        page = ctx.new_page()
        ok = True
        for q in QUERIES:
            if not scrape_query(page, q, store):
                ok = False
                break
            pause()
        browser.close()

    items = [it for it in store.values() if looks_like_lounge(it)]
    if not items:
        sys.exit("Нәтиже жоқ. STRICT_FILTER=False қойып көріңіз.")
    rows = build_rows(items)
    compute_density(rows)
    save_csv(rows)
    report(rows)
    if not ok:
        print("Ескерту: блокталғандықтан тізім толық емес.")


if __name__ == "__main__":
    main()