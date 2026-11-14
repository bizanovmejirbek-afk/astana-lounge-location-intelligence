"""
Шаг 3. Множественная регрессия (МНК) по методике:
корреляция → отбор X (|r| ≥ 0,2, без пар с |r| > 0,7) → регрессия →
пошаговое исключение X с наибольшим P > 0,05.

Модель А: Y = средний чек бара.        Модель Б: Y = число лаунж-баров в ячейке.
Выход: results/model_a.md, results/model_b.md, data/processed/niches.csv,
       data/processed/grid_cells.csv (+ прогноз)
"""
import json

import numpy as np
import pandas as pd
from scipy import stats

from common import PROC, RESULTS, haversine

RESULTS.mkdir(exist_ok=True)


def ols(y, X):
    Xc = np.column_stack([np.ones(len(y)), X]).astype(float)
    y = np.asarray(y, float)
    b, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    e = y - Xc @ b
    n, k = Xc.shape
    se = np.sqrt(np.diag(e @ e / (n - k) * np.linalg.inv(Xc.T @ Xc)))
    p = 2 * stats.t.sf(np.abs(b / se), n - k)
    r2 = 1 - e @ e / ((y - y.mean()) @ (y - y.mean()))
    F = (r2 / (k - 1)) / ((1 - r2) / (n - k))
    return {"b": b, "p": p, "r2": r2, "adj": 1 - (1 - r2) * (n - 1) / (n - k),
            "F_p": stats.f.sf(F, k - 1, n - k), "pred": Xc @ b, "resid": e}


def select(df, y, xs):
    r = df[[y] + xs].corr()[y][xs]
    cand = [x for x in xs if abs(r[x]) >= 0.2]
    c = df[cand].corr()
    dropped = []
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            if abs(c.loc[a, b]) > 0.7:
                dropped.append(min(a, b, key=lambda v: abs(r[v])))
    return r, [x for x in cand if x not in dropped], sorted(set(dropped))


def stepwise(df, y, xs):
    rounds, cur = [], list(xs)
    while True:
        m = ols(df[y], df[cur].values)
        p = dict(zip(cur, m["p"][1:]))
        worst = max(p, key=p.get)
        rounds.append({"X": list(cur), "R2": m["r2"], "adjR2": m["adj"], "F_p": m["F_p"], "max_p": p[worst], "worst": worst})
        if p[worst] < 0.05:
            return m, cur, rounds
        cur.remove(worst)


def report(name, title, df, y, xs, note=""):
    r, cand, dropped = select(df, y, xs)
    m, final, rounds = stepwise(df, y, cand)
    eq = f"{y} = {m['b'][0]:,.4f} " + " ".join(f"{'+' if c >= 0 else '−'} {abs(c):,.4f}·{x}" for c, x in zip(m["b"][1:], final))
    L = [f"# {title}", "", f"Наблюдений: {len(df)}", "", "## Корреляция с Y", "", "| X | r |", "|---|---|"]
    L += [f"| {x} | {r[x]:+.3f} |" for x in sorted(xs, key=lambda v: -abs(r[v]))]
    L += ["", f"Отобрано (|r| ≥ 0,2): {', '.join(cand)}", f"Исключены из-за мультиколлинеарности (|r| > 0,7): {', '.join(dropped) or '—'}", "",
          "## Пошаговое исключение", "", "| Раунд | Число X | R² | Норм. R² | Значимость F | Наибольшее P | X |", "|---|---|---|---|---|---|---|"]
    L += [f"| {i} | {len(rd['X'])} | {rd['R2']:.3f} | {rd['adjR2']:.3f} | {rd['F_p']:.1e} | {rd['max_p']:.3f} | {rd['worst'] if rd['max_p'] >= 0.05 else '—'} |"
          for i, rd in enumerate(rounds, 1)]
    L += ["", "## Итоговая модель", "", "| | Коэффициент | P |", "|---|---|---|", f"| Пересечение | {m['b'][0]:.4f} | {m['p'][0]:.4f} |"]
    L += [f"| {x} | {c:.4f} | {p:.6f} |" for x, c, p in zip(final, m["b"][1:], m["p"][1:])]
    L += ["", f"**{eq}**", "", f"R² = {m['r2']:.3f} · нормированный R² = {m['adj']:.3f} · значимость F = {m['F_p']:.1e}", note]
    (RESULTS / f"{name}.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[-4:-1]))
    return m, final


def main():
    bars = pd.read_csv(PROC / "bars_features.csv")
    A = bars[bars.in_model_a == 1].reset_index(drop=True)
    xa = [c for c in A.columns if c.startswith("X")]
    mA, fa = report("model_a", "Модель А: средний чек лаунж-бара", A, "Y_avg_check", xa)
    err = np.abs(mA["resid"]) / A["Y_avg_check"]
    with open(RESULTS / "model_a.md", "a", encoding="utf-8") as f:
        f.write(f"\n\nСредняя относительная ошибка: {err.mean():.1%}, медианная: {err.median():.1%}, наибольшая: {err.max():.0%}.\n")

    G = pd.read_csv(PROC / "grid_cells.csv")
    xb = [c for c in G.columns if c.startswith("X")]
    mB, fb = report("model_b", "Модель Б: число лаунж-баров в ячейке 500×500 м", G, "Y_bars", xb)
    mae, base = np.abs(mB["resid"]).mean(), np.abs(G.Y_bars - G.Y_bars.mean()).mean()
    with open(RESULTS / "model_b.md", "a", encoding="utf-8") as f:
        f.write(f"\n\nMAE = {mae:.3f} бара (простой прогноз средним: {base:.3f}, модель точнее на {1 - mae / base:.0%}).\n"
                "Y — счётные данные (89% нулей); линейная регрессия использована как базовый метод.\n")

    # свободные ниши: в ячейке нет баров, в радиусе 1 км ≤ 2 бара, ниши не ближе 1 км друг к другу
    lounge = bars[bars.is_lounge == 1]
    G["predicted_bars"] = mB["pred"]
    pct = G["predicted_bars"].rank(pct=True, method="min")
    G["score_0_100"] = ((pct - pct.min()) / (pct.max() - pct.min()) * 100).round().astype(int)
    G["bars_1km"] = [int((haversine(a, b, lounge.lat.values, lounge.lon.values) <= 1).sum()) for a, b in zip(G.lat, G.lon)]
    G.to_csv(PROC / "grid_cells.csv", index=False, encoding="utf-8-sig")
    cand = G[(G.Y_bars == 0) & (G.bars_1km <= 2)].sort_values("predicted_bars", ascending=False)
    top = []
    for _, c in cand.iterrows():
        if all(haversine(c.lat, c.lon, t.lat, t.lon) > 1 for t in top):
            top.append(c)
        if len(top) == 10:
            break
    top = pd.DataFrame(top).reset_index(drop=True)
    a0, coefs = mA["b"][0], dict(zip(fa, mA["b"][1:]))
    top["recommended_check"] = (a0 + coefs.get("X12_branches", 0) * 1 + coefs.get("X11_left_bank", 0) * top.X9_left_bank).round(-2)
    kr, osm = pd.read_csv(PROC / "krisha_clean.csv"), pd.read_csv(PROC / "osm_clean.csv")
    malls = osm[osm.category == "mall"]
    streets, mall_txt = [], []
    for a, b in zip(top.lat, top.lon):
        d = haversine(a, b, kr.lat.values, kr.lon.values)
        near = kr["address"][d <= 0.35] if (d <= 0.35).any() else kr["address"].iloc[[d.argmin()]]
        streets.append(near.str.replace(r"\s*\d.*$", "", regex=True).value_counts().index[0])
        dm = haversine(a, b, malls.lat.values, malls.lon.values)
        nm = malls["name"].iloc[dm.argmin()]
        mall_txt.append(f"{nm if isinstance(nm, str) and nm else 'ТРЦ'} ({dm.min():.1f} км)")
    top["street"], top["nearest_mall"] = streets, mall_txt
    top.insert(0, "rank", range(1, len(top) + 1))
    top.to_csv(PROC / "niches.csv", index=False, encoding="utf-8-sig")
    json.dump({"model_a": {"intercept": a0, **coefs, "r2": mA["r2"]},
               "model_b": {"intercept": mB["b"][0], **dict(zip(fb, mB["b"][1:])), "r2": mB["r2"]}},
              open(RESULTS / "coefficients.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nniches.csv: {len(top)} ниш")


if __name__ == "__main__":
    main()
