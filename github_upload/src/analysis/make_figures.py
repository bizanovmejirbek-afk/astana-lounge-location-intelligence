"""Шаг 5. Статичные иллюстрации для README: docs/img/*.png"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

from build_grid import DLAT, DLON
from common import PROC, ROOT

IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "Inter", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#8a8984", "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e"})
SEQ = ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#104281"]
SEG = {"Эконом (< 6 000 ₸)": "#1baf7a", "Средний (6 000–8 999 ₸)": "#eda100", "Премиум (≥ 9 000 ₸)": "#e34948"}
KX = np.cos(np.radians(51.13))


def fig_map():
    G = pd.read_csv(PROC / "grid_cells.csv")
    B = pd.read_csv(PROC / "bars_features.csv")
    B = B[B.is_lounge == 1]
    N = pd.read_csv(PROC / "niches.csv")
    fig, ax = plt.subplots(figsize=(9, 8.2), dpi=150)
    cuts = [40, 60, 80, 90]
    for r in G.itertuples():
        k = next((i for i, t in enumerate(cuts) if r.score_0_100 < t), 4)
        ax.add_patch(Rectangle(((r.lon - DLON / 2) * KX, r.lat - DLAT / 2), DLON * KX, DLAT, facecolor=SEQ[k], edgecolor="white", lw=0.4))
    for lbl, col in SEG.items():
        lo, hi = {"Э": (0, 6000), "С": (6000, 9000), "П": (9000, 1e9)}[lbl[0]]
        s = B[(B.Y_avg_check >= lo) & (B.Y_avg_check < hi)]
        ax.scatter(s.lon * KX, s.lat, s=18 + (s.Y_avg_check - 3000) / 12000 * 50, c=col, edgecolors="white", linewidths=1, zorder=3, label=lbl)
    for r in N.itertuples():
        ax.scatter(r.lon * KX, r.lat, s=260, c="#0b0b0b", edgecolors="white", linewidths=1.5, zorder=4)
        ax.text(r.lon * KX, r.lat, str(r.rank), color="white", ha="center", va="center", fontsize=8, fontweight="bold", zorder=5)
    ax.scatter([], [], s=200, c="#0b0b0b", label="Свободная ниша (топ-10)")
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_xlim((G.lon.min() - 0.01) * KX, (G.lon.max() + 0.01) * KX); ax.set_ylim(G.lat.min() - 0.01, G.lat.max() + 0.01)
    ax.legend(loc="lower left", frameon=True, framealpha=0.95, edgecolor="#e3e2dd", fontsize=8.5, title="Лаунж-бары по среднему чеку", title_fontsize=8.5)
    cax = fig.add_axes([0.62, 0.11, 0.25, 0.018])
    for i, c in enumerate(SEQ):
        cax.add_patch(Rectangle((i, 0), 1, 1, color=c))
    cax.set_xlim(0, 5); cax.set_ylim(0, 1); cax.set_yticks([]); cax.set_xticks([0, 2.5, 5]); cax.set_xticklabels(["0", "оценка места", "100"], fontsize=8)
    for s in cax.spines.values(): s.set_visible(False)
    ax.set_title("Астана: оценка мест для лаунж-бара (сетка 500 м) и свободные ниши", loc="left", fontsize=12, fontweight="bold", color="#0b0b0b")
    fig.savefig(IMG / "map_preview.png", bbox_inches="tight", facecolor="white"); plt.close(fig)


def fig_model_a():
    B = pd.read_csv(PROC / "bars_features.csv")
    A = B[B.in_model_a == 1]
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8), dpi=150)
    m = A.groupby("X11_left_bank").Y_avg_check.mean()
    axs[0].bar(["Правый берег", "Левый берег"], [m[0], m[1]], color=["#86b6ef", "#256abf"], width=0.55)
    for i, v in enumerate([m[0], m[1]]):
        axs[0].text(i, v + 150, f"{v:,.0f} ₸".replace(",", " "), ha="center", fontsize=10, fontweight="bold")
    axs[0].set_title("Средний чек: левый берег дороже", loc="left", fontweight="bold"); axs[0].set_ylabel("Средний чек, ₸")
    axs[0].set_ylim(0, max(m) * 1.2)
    grp = pd.cut(A.X12_branches, [-1, 1, 3, 100], labels=["1", "2–3", "4 и более"])
    g = A.groupby(grp, observed=True).Y_avg_check.agg(["mean", "count"])
    axs[1].bar(range(len(g)), g["mean"], color=["#86b6ef", "#3987e5", "#184f95"], width=0.55)
    for i, (v, n) in enumerate(zip(g["mean"], g["count"])):
        axs[1].text(i, v + 150, f"{v:,.0f} ₸".replace(",", " "), ha="center", fontsize=10, fontweight="bold")
        axs[1].text(i, 300, f"n = {n}", ha="center", fontsize=8, color="white")
    axs[1].set_xticks(range(len(g))); axs[1].set_xticklabels(g.index); axs[1].set_ylim(0, g["mean"].max() * 1.2)
    axs[1].set_title("Чем больше филиалов, тем выше чек", loc="left", fontweight="bold")
    axs[1].set_xlabel("Филиалов у бренда"); axs[1].set_ylabel("Средний чек, ₸"); 
    fig.tight_layout(); fig.savefig(IMG / "model_a.png", facecolor="white"); plt.close(fig)


if __name__ == "__main__":
    fig_map(); fig_model_a(); print("docs/img: map_preview.png, model_a.png")
