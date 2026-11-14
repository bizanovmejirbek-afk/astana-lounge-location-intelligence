"""
Шаг 1. Признаки для модели А (уровень бара).

Вход:  data/raw/bars_2gis.csv, bars_attributes_2gis.csv, osm_poi.csv,
       krisha_listings.csv, krisha_geocoded.csv
Выход: data/processed/bars_features.csv, osm_clean.csv, krisha_clean.csv
"""
import numpy as np
import pandas as pd

from common import CENTER, LEFT_BANK, NOT_LOUNGE, PROC, RAW, haversine

PROC.mkdir(parents=True, exist_ok=True)


def clean_osm():
    """Удаляем дубли «точка + полигон» одного объекта и не-ТРЦ из категории mall."""
    o = pd.read_csv(RAW / "osm_poi.csv")
    o = o[~o["name"].fillna("").isin(["KFC", "Flowerhub"])]
    keep = []
    for cat, g in o.groupby("category"):
        g = g.reset_index(drop=True)
        used = np.zeros(len(g), bool)
        names = g["name"].fillna("")
        for i in range(len(g)):
            if used[i]:
                continue
            keep.append(g.iloc[i])
            d = haversine(g.lat[i], g.lon[i], g.lat.values, g.lon.values)
            # в радиусе 100 м: тот же объект, если совпадает название (для ТРЦ — любое)
            used |= ((d < 0.1) & ((names == names[i]) | (cat == "mall"))).values
    return pd.DataFrame(keep).reset_index(drop=True)


def clean_krisha():
    """Объявления с координатами: 15–300 м², ₸/м² в пределах 1–99 перцентиля."""
    t = pd.read_csv(RAW / "krisha_listings.csv").drop_duplicates("id")
    g = pd.read_csv(RAW / "krisha_geocoded.csv").dropna(subset=["lat"])
    t["addr_key"] = t["address"].str.split(" — ").str[0].str.strip()
    k = t.merge(g, left_on="addr_key", right_on="address", suffixes=("", "_geo"))
    k = k[k["area_m2"].between(15, 300)].copy()
    k["price_m2"] = k["price"] / k["area_m2"]
    lo, hi = k["price_m2"].quantile([0.01, 0.99])
    return k[k["price_m2"].between(lo, hi)].reset_index(drop=True)


def count_within(lat, lon, pts, r):
    return [int((haversine(a, b, pts.lat.values, pts.lon.values) <= r).sum()) for a, b in zip(lat, lon)]


def median_within(lat, lon, pts, r, min_n=5):
    out = []
    for a, b in zip(lat, lon):
        m = haversine(a, b, pts.lat.values, pts.lon.values) <= r
        out.append(np.median(pts.price_m2.values[m]) if m.sum() >= min_n else np.nan)
    return out


def main():
    osm, kr = clean_osm(), clean_krisha()
    osm.to_csv(PROC / "osm_clean.csv", index=False, encoding="utf-8-sig")
    kr.to_csv(PROC / "krisha_clean.csv", index=False, encoding="utf-8-sig")

    b = pd.read_csv(RAW / "bars_2gis.csv")
    at = pd.read_csv(RAW / "bars_attributes_2gis.csv")
    attrs = at["attributes_raw"].fillna("")
    at["vip"] = ((at["has_vip"] == 1) | attrs.str.contains("Кабинки")).astype(int)
    at["panorama"] = attrs.str.contains("Панорамный").astype(int)
    b = b.merge(at[["id", "found", "branches", "has_kitchen", "vip", "live_music", "sport_tv",
                    "terrace", "banquets", "board_games", "panorama"]], on="id", how="left")

    lat, lon = b.lat, b.lon
    P = lambda c: osm[osm.category == c]
    f = pd.DataFrame({"id": b.id, "name": b["name"], "district": b.district, "lat": lat, "lon": lon})
    f["Y_avg_check"] = b.avg_check
    f["X1_rent_2km"] = median_within(lat, lon, kr, 2)
    f["X2_competitors_1km"] = b.comp_1km
    f["X3_rating"] = b.rating_2gis
    f["X4_ln_reviews"] = np.log(b.reviews_2gis)
    f["X5_malls_1km"] = count_within(lat, lon, P("mall"), 1)
    f["X6_offices_1km"] = count_within(lat, lon, P("office"), 1)
    f["X7_food_1km"] = count_within(lat, lon, P("food"), 1)
    f["X8_bus_stops_500m"] = count_within(lat, lon, P("bus_stop"), 0.5)
    f["X9_hotels_1km"] = count_within(lat, lon, P("hotel"), 1)
    f["X10_dist_center_km"] = haversine(*CENTER, lat, lon)
    f["X11_left_bank"] = b.district.isin(LEFT_BANK).astype(int)
    f["X12_branches"] = b.branches
    for i, c in enumerate(["has_kitchen", "vip", "live_music", "sport_tv", "terrace", "banquets", "board_games", "panorama"], 13):
        f[f"X{i}_{c}"] = b[c]
    f["is_lounge"] = (~b.id.isin(NOT_LOUNGE)).astype(int)
    f["in_model_a"] = ((f.is_lounge == 1) & (b.found == 1)).astype(int)
    f.to_csv(PROC / "bars_features.csv", index=False, encoding="utf-8-sig")
    print(f"bars_features.csv: {len(f)} баров, в модели А: {f.in_model_a.sum()}")
    print(f"osm_clean.csv: {len(osm)} объектов · krisha_clean.csv: {len(kr)} квартир")


if __name__ == "__main__":
    main()
