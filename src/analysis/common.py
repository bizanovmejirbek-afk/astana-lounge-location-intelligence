"""Общие пути и функции."""
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
CENTER = (51.1283, 71.4305)          # монумент Байтерек
LEFT_BANK = {"Есиль", "Нура"}         # условное деление на левый/правый берег
NOT_LOUNGE = {79, 84}                 # бильярд-клуб и кибер-лаунж


def haversine(lat1, lon1, lat2, lon2):
    """Расстояние по прямой, км (работает с массивами numpy)."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))
