"""
Шаг 2. Сетка 500×500 м для модели Б (уровень ячейки).

Ячейка считается городской, если в радиусе 1 км не меньше 5 объявлений об аренде.
Выход: data/processed/grid_cells.csv
"""
import numpy as np
import pandas as pd

from common import CENTER, LEFT_BANK, PROC, haversine

LAT0, LAT1, LON0, LON1 = 51.03, 51.25, 71.24, 71.65
DLAT = 0.5 / 111.32
DLON = 0.5 / (111.32 * np.cos(np.radians(51.13)))
KR_DISTRICT = {"Есильский р-н": "Есиль", "Нура р-н": "Нура", "Алматы р-н": "Алматы",
               "Сарайшык р-н": "Сарайшык", "Сарыарка р-н": "Сарыарка", "р-н Байконур": "Байконур"}


def cell_id(lat, lon):
    return ((lat - LAT0) // DLAT).astype(int).astype(str) + "_" + ((lon - LON0) // DLON).astype(int).astype(str)


def main():
    kr = pd.read_csv(PROC / "krisha_clean.csv")
    osm = pd.read_csv(PROC / "osm_clean.csv")
    bars = pd.read_csv(PROC / "bars_features.csv")
    bars = bars[bars.is_lounge == 1]

    la = np.arange(LAT0, LAT1, DLAT) + DLAT / 2
    lo = np.arange(LON0, LON1, DLON) + DLON / 2
    G = pd.DataFrame([(f"{i}_{j}", a, b) for i, a in enumerate(la) for j, b in enumerate(lo)], columns=["cell", "lat", "lon"])
    count = lambda df: G.cell.map(cell_id(df.lat, df.lon).value_counts()).fillna(0).astype(int)

    G["Y_bars"] = count(bars)
    G["X2_listings"] = count(kr)
    G["X3_food"] = count(osm[osm.category == "food"])
    G["X4_offices"] = count(osm[osm.category == "office"])
    G["X5_bus_stops"] = count(osm[osm.category == "bus_stop"])
    G["X6_hotels"] = count(osm[osm.category == "hotel"])

    malls, unis = osm[osm.category == "mall"], osm[osm.category == "university"]
    dist_kr = kr["district"].map(KR_DISTRICT)
    rent, n1, m1, u1, left = [], [], [], [], []
    for a, b in zip(G.lat, G.lon):
        near = haversine(a, b, kr.lat.values, kr.lon.values) <= 1
        n1.append(near.sum())
        rent.append(np.median(kr.price_m2.values[near]) if near.sum() >= 5 else np.nan)
        m1.append(int((haversine(a, b, malls.lat.values, malls.lon.values) <= 1).sum()))
        u1.append(int((haversine(a, b, unis.lat.values, unis.lon.values) <= 1).sum()))
        d = dist_kr[near].dropna()
        left.append(int(d.mode()[0] in LEFT_BANK) if len(d) else np.nan)
    G["X1_rent_1km"], G["X7_malls_1km"], G["X8_universities_1km"], G["X9_left_bank"] = rent, m1, u1, left
    G["X10_dist_center_km"] = haversine(*CENTER, G.lat, G.lon)
    G["listings_1km"] = n1

    urban = G.dropna(subset=["X1_rent_1km", "X9_left_bank"]).reset_index(drop=True)
    urban["X9_left_bank"] = urban["X9_left_bank"].astype(int)
    cols = ["cell", "lat", "lon", "Y_bars", "X1_rent_1km", "X2_listings", "X3_food", "X4_offices", "X5_bus_stops",
            "X6_hotels", "X7_malls_1km", "X8_universities_1km", "X9_left_bank", "X10_dist_center_km", "listings_1km"]
    urban[cols].to_csv(PROC / "grid_cells.csv", index=False, encoding="utf-8-sig")
    print(f"Ячеек всего: {len(G)}, городских: {len(urban)}, баров в них: {urban.Y_bars.sum()} из {len(bars)}")


if __name__ == "__main__":
    main()
