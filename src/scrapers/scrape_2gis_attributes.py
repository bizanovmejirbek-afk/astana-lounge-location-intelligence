"""
Сбор признаков лаунж-баров со страниц 2GIS (кухня, VIP, живая музыка, веранда,
режим работы, число филиалов и т.д.).

Каждая страница 2GIS содержит JSON `initialState`. Скрипт открывает страницы
в настоящем браузере (Selenium): на простые HTTP-запросы 2GIS отвечает
страницей «Ваш браузер устарел».

Запуск:   python src/scrapers/scrape_2gis_attributes.py
Вход:      data/raw/bars_2gis.csv
Результат: data/raw/bars_attributes_2gis.csv
Сначала запустите с TEST = True (3 бара).
"""
import json
import math
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from selenium import webdriver

TEST = True
RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
BARS = RAW / "bars_2gis.csv"
OUT = RAW / "bars_attributes_2gis.csv"
DEBUG = Path("debug")
MAX_MATCH_M = 300  # если ближайший результат 2GIS дальше — считаем, что это другой бар


# ---------- разбор initialState ----------
def initial_state(html):
    m = re.search(r"var initialState = JSON\.parse\('(.*?)'\);", html, re.S)
    if not m:
        return None
    raw = m.group(1)
    try:
        txt = raw.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")
    except UnicodeError:
        txt = raw
    return json.loads(txt)


def branches(state):
    prof = state.get("data", {}).get("entity", {}).get("profile", {})
    return [v["data"] for v in prof.values()
            if (v.get("data") or {}).get("type") == "branch" and v["data"].get("point")]


def dist_m(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 6371000 * 2 * math.asin(math.sqrt(a))


def closing_hour(schedule):
    """Час закрытия в пятницу: 02:00 -> 26, круглосуточно -> 30."""
    if not schedule:
        return None
    if schedule.get("is_24x7"):
        return 30
    fri = schedule.get("Fri", {}).get("working_hours", [])
    if not fri:
        return None
    fr, to = fri[-1]["from"], fri[-1]["to"]
    if to == "24:00":
        return 24
    h_to = int(to[:2]) + int(to[3:5]) / 60
    return round(h_to + 24 if h_to <= int(fr[:2]) else h_to, 1)


def number(text):
    m = re.search(r"(\d[\d\s]*)", text or "")
    return int(re.sub(r"\s", "", m.group(1))) if m else None


def features(d):
    attrs = [(a.get("name", ""), a.get("tag", ""), g.get("name", ""))
             for g in d.get("attribute_groups", []) for a in g.get("attributes", [])]
    tags = {t for _, t, _ in attrs}
    names = " | ".join(n for n, _, _ in attrs).lower()
    menu = [n for n, _, g in attrs if g == "Меню"]
    created = (d.get("dates") or {}).get("created_at", "")
    return {
        "firm_id": d.get("id", "").split("_")[0],
        "name_2gis": d.get("name", ""),
        "avg_check_2gis": number(next((n for n, t, _ in attrs if t == "food_service_avg_price"), "")),
        "has_kitchen": int(bool(menu) or any(t.startswith("food_service_food_") for t in tags)
                           or "food_service_business_lunch" in tags),
        "menu_items": len(menu),
        "has_vip": int("food_service_infrastructure_vip_hall" in tags or "vip" in names),
        "has_karaoke": int("караоке" in names),
        "live_music": int("food_service_details_food_live_music" in tags),
        "sport_tv": int("food_service_details_food_sport_on_tv" in tags),
        "terrace": int("food_service_infrastructure_patio" in tags),
        "banquets": int("food_service_infrastructure_banquet" in tags),
        "board_games": int("food_service_infrastructure_table_games" in tags),
        "capacity": next((n for n, t, _ in attrs if t == "food_service_capacity"), ""),
        "closing_hour_fri": closing_hour(d.get("schedule")),
        "open_24h": int(bool((d.get("schedule") or {}).get("is_24x7"))),
        "year_added": int(created[:4]) if created[:4].isdigit() else None,
        "branches": (d.get("org") or {}).get("branch_count"),
        "rating": (d.get("reviews") or {}).get("general_rating"),
        "reviews": (d.get("reviews") or {}).get("general_review_count"),
        "attributes_raw": " | ".join(n for n, _, _ in attrs),
    }


# ---------- браузер ----------
def open_browser():
    try:
        return webdriver.Chrome()
    except Exception:
        return webdriver.Edge()  # на Windows Edge есть всегда


def load(driver, url, tag):
    driver.get(url)
    for _ in range(30):
        time.sleep(0.5)
        if "initialState" in driver.page_source:
            break
    html = driver.page_source
    if "acceptRiskButton" in html and "initialState" not in html:  # «Ваш браузер устарел»
        try:
            driver.find_element("id", "acceptRiskButton").click()
            time.sleep(4)
            html = driver.page_source
        except Exception:
            pass
    state = initial_state(html)
    if state is None:
        DEBUG.mkdir(exist_ok=True)
        (DEBUG / f"{tag}.html").write_text(html, encoding="utf-8")
    return state, html


def firm(driver, fid, tag):
    state, _ = load(driver, f"https://2gis.kz/astana/firm/{fid}", tag)
    found = [p for p in branches(state)] if state else []
    return next((p for p in found if p["id"].split("_")[0] == fid), None)


def find_bar(driver, row):
    name = row["name"].split(",")[0].strip()
    state, html = load(driver, f"https://2gis.kz/astana/search/{quote(name + ' ' + row['address'])}", f"search_{row['id']}")
    cands = branches(state) if state else []
    if not cands:  # в выдаче нет профилей — пробуем ссылки /firm/...
        for i, fid in enumerate(list(dict.fromkeys(re.findall(r"/firm/(\d{10,})", html)))[:3]):
            time.sleep(random.uniform(2, 4))
            p = firm(driver, fid, f"firm_{row['id']}_{i}")
            if p:
                cands.append(p)
    if not cands:
        return None, "нет результатов поиска"
    for c in cands:
        c["_dist"] = dist_m(row["lat"], row["lon"], c["point"]["lat"], c["point"]["lon"])
    best = min(cands, key=lambda c: c["_dist"])
    if best["_dist"] > MAX_MATCH_M:
        return None, f"ближайший результат в {best['_dist']:.0f} м: {best.get('name')}"
    if not best.get("attribute_groups"):  # в поиске атрибутов нет — открываем страницу бара
        dist = best["_dist"]
        time.sleep(random.uniform(2, 4))
        full = firm(driver, best["id"].split("_")[0], f"firm_{row['id']}")
        if full:
            best, best["_dist"] = full, dist
    return best, ""


def main():
    bars = pd.read_csv(BARS)
    if TEST:
        bars = bars.head(3)
    done = set()
    if OUT.exists():
        old = pd.read_csv(OUT)
        done = set(old.loc[old["found"] == 1, "id"])
    driver = open_browser()
    rows = []
    try:
        for _, row in bars.iterrows():
            if row["id"] in done:
                continue
            try:
                d, err = find_bar(driver, row)
            except Exception as e:
                d, err = None, f"{e.__class__.__name__}: {str(e)[:80]}"
            if d is None:
                rows.append({"id": row["id"], "found": 0, "note": err})
                print(f'{row["id"]:>4} {row["name"][:32]:<32} -> ОШИБКА: {err}')
            else:
                rows.append({"id": row["id"], "found": 1, "match_distance_m": round(d["_dist"]), **features(d), "note": ""})
                print(f'{row["id"]:>4} {row["name"][:32]:<32} -> {d.get("name", "")[:28]}')
            old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=["id", "found"])
            (pd.concat([old[old["found"] == 1], pd.DataFrame(rows)], ignore_index=True)
               .drop_duplicates("id", keep="last").to_csv(OUT, index=False, encoding="utf-8-sig"))
            time.sleep(random.uniform(3, 6))
    finally:
        driver.quit()
    df = pd.read_csv(OUT)
    print(f"\n{OUT.name}: найдено {int(df['found'].sum())} из {len(df)}")


if __name__ == "__main__":
    main()
