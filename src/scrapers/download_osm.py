"""
Загрузка объектов OpenStreetMap по Астане через Overpass API:
ТРЦ, офисные здания, общепит, бары, остановки, гостиницы, вузы.

Запуск:   python src/scrapers/download_osm.py
Результат: data/raw/osm_poi.csv  (category, name, lat, lon, osm_id)

Каждая категория сохраняется сразу после загрузки; при повторном запуске
скачиваются только недостающие категории.
"""
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).resolve().parents[2] / "data" / "raw" / "osm_poi.csv"
BBOX = "51.00,71.20,51.30,71.70"  # юг, запад, север, восток
SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
HEADERS = {"User-Agent": "astana-lounge-research/1.0 (python-requests)"}  # без него Overpass отвечает 406

CATEGORIES = {
    "mall": ['["shop"="mall"]'],
    "office": ['["office"]', '["building"="office"]', '["building"="commercial"]'],
    "food": ['["amenity"="restaurant"]', '["amenity"="cafe"]', '["amenity"="fast_food"]'],
    "bar": ['["amenity"="bar"]', '["amenity"="pub"]', '["amenity"="nightclub"]'],
    "bus_stop": ['["highway"="bus_stop"]'],
    "hotel": ['["tourism"="hotel"]'],
    "university": ['["amenity"="university"]'],
}


def query(filters):
    parts = "".join(f"nwr{f}({BBOX});" for f in filters)
    return f"[out:json][timeout:120];({parts});out center tags;"


def fetch(category, filters):
    for url in SERVERS:
        try:
            r = requests.post(url, data={"data": query(filters)}, headers=HEADERS, timeout=180)
            if r.status_code == 200:
                break
            print(f"  {url} -> {r.status_code}, пробую следующий сервер")
        except requests.RequestException as e:
            print(f"  {url} -> {e.__class__.__name__}, пробую следующий сервер")
        time.sleep(3)
    else:
        return None
    rows = []
    for el in r.json()["elements"]:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        rows.append({"category": category,
                     "name": tags.get("name:kk") or tags.get("name") or tags.get("name:ru") or "",
                     "lat": lat, "lon": lon, "osm_id": f'{el["type"]}/{el["id"]}'})
    return rows


def main():
    df = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=["category", "name", "lat", "lon", "osm_id"])
    done = set(df["category"])
    failed = []
    for category, filters in CATEGORIES.items():
        if category in done:
            continue
        rows = fetch(category, filters)
        if rows is None:
            print(f"{category}: не загружено")
            failed.append(category)
            continue
        print(f"{category}: {len(rows)} объектов")
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True).drop_duplicates(["category", "osm_id"])
        df.to_csv(OUT, index=False, encoding="utf-8-sig")
        time.sleep(5)
    print(f"\n{OUT.name}: {len(df)} строк")
    if failed:
        print("Не загружены:", ", ".join(failed), "— запустите скрипт ещё раз через несколько минут.")


if __name__ == "__main__":
    main()
