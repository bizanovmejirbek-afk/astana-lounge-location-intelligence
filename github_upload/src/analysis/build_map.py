"""
Шаг 4. Интерактивная карта для GitHub Pages: docs/index.html
Вход: data/processed/grid_cells.csv, bars_features.csv, niches.csv
"""
import json

import pandas as pd

from common import PROC, ROOT

HERE = ROOT / "src" / "analysis"


def main():
    G = pd.read_csv(PROC / "grid_cells.csv")
    B = pd.read_csv(PROC / "bars_features.csv")
    B = B[B.is_lounge == 1]
    N = pd.read_csv(PROC / "niches.csv")
    data = {
        # [lat, lon, аренда 1 км, прогноз модели Б, баров, объявлений, общепит, левый берег]
        "cells": [[round(r.lat, 5), round(r.lon, 5), int(round(r.X1_rent_1km)), round(r.predicted_bars, 3), int(r.Y_bars),
                   int(r.X2_listings), int(r.X3_food), int(r.X9_left_bank)] for r in G.itertuples()],
        # [название, lat, lon, чек, район, филиалы, отзывы]
        "bars": [[r.name.replace(", лаундж-бар", ""), round(r.lat, 5), round(r.lon, 5), int(r.Y_avg_check), r.district,
                  None if pd.isna(r.X12_branches) else int(r.X12_branches), int(round(__import__("math").exp(r.X4_ln_reviews)))]
                 for r in B.itertuples()],
        # [номер, lat, lon, улица, ближайший ТРЦ]
        "niches": [[int(r.rank), round(r.lat, 5), round(r.lon, 5), r.street, r.nearest_mall] for r in N.itertuples()],
    }
    html = (HERE / "map_template.html").read_text(encoding="utf-8")
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":"))), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: {len(data['cells'])} ячеек, {len(data['bars'])} баров, {len(data['niches'])} ниш")


if __name__ == "__main__":
    main()
