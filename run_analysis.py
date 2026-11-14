"""Полный пересчёт анализа: признаки → сетка → модели → карта → рисунки."""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "src" / "analysis"
sys.path.insert(0, str(HERE))
for step in ["build_features", "build_grid", "run_models", "build_map", "make_figures"]:
    print(f"\n=== {step} ===")
    runpy.run_path(str(HERE / f"{step}.py"), run_name="__main__")
