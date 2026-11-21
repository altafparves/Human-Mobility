"""
Synthetic Bronze stand-in for the two JogjaPulse CSVs.
------------------------------------------------------
Role 3 development aid. Zenodo requires a manual download, so this writes CSVs
shaped exactly like the real ones — same columns, same row counts, same cell
and kapanewon universe — into a scratch directory. Role 1's own
`src.clean_temporal` is then run against them, which means Role 3 is developed
against the *real* Silver schema rather than a guess at it.

    python -m tests.make_sample_bronze --out data/_sample/raw

Targets taken from `data/raw/jogjapulse_verification_summary.json`, so the
output satisfies every assertion in `src.ingest.verify_jogjapulse_datasets()`:

    daily   183,548 rows · 5,715 cells · 151 dates · n_maids 5–10,971
    hourly  230,418 rows · 78 kapanewon · 5 kab/kota · n_maids 5–2,506

The documented pathologies are reproduced on purpose, because code that only
works on tidy data has not been tested:

  * panel decay across the window (the sample shrinks sharply by April)
  * k = 5 suppression, so quiet cell-days are ABSENT, never zero
  * 2022-03-08 present but almost empty (the delivery failure)
  * step changes in the published sample on 1 January and 16 February

EVERY NUMBER HERE IS INVENTED. It exists to prove the pipeline runs. None of
it may appear in the report, the slides or the video.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERIFICATION_JSON = PROJECT_ROOT / "data" / "raw" / "jogjapulse_verification_summary.json"
OSM_JSON = PROJECT_ROOT / "data" / "raw" / "osm_facilities_current.json"

RNG = np.random.default_rng(20261121)

CELL_SIZE_M = 500
CRS_UTM, CRS_WGS84 = "EPSG:32749", "EPSG:4326"

# Real targets, read from the verification summary when it is available.
TARGET_DAILY_ROWS = 183_548
TARGET_CELLS = 5_715
TARGET_HOURLY_ROWS = 230_418
TARGET_KAPANEWON = 78
DATE_START, DATE_END = "2021-12-01", "2022-04-30"

ANOMALOUS_DATE = "2022-03-08"
SAMPLE_BREAKS = ("2022-01-01", "2022-02-16")
NATARU = ("2021-12-24", "2022-01-02")

# Panel size at the start and end of the window: the sample decays hard.
PANEL_START, PANEL_END = 87_000, 9_000
# Multiplicative step applied from each sample break onwards.
BREAK_STEPS = {"2022-01-01": 0.72, "2022-02-16": 1.18}

# Six study categories from configs/osm_tags.yaml, with the behaviour that
# gives H1, H2 and H3 something to find.
# (pull, weekend multiplier, Nataru multiplier)
CATEGORY_BEHAVIOUR = {
    "education_campus":    (6.0, 0.35, 0.25),
    "commercial_mall":     (5.0, 1.45, 1.80),
    "traditional_market":  (3.5, 1.15, 1.20),
    "tourism_site":        (3.0, 1.60, 2.10),
    "transit_hub":         (2.5, 0.90, 1.30),
    "healthcare_hospital": (2.8, 0.95, 1.00),
}

HOUR_SHAPE = np.array(
    [0.22, 0.18, 0.16, 0.16, 0.20, 0.34, 0.58, 0.84, 0.97, 1.00, 1.00, 0.96,
     0.90, 0.93, 0.96, 0.99, 1.00, 0.94, 0.78, 0.63, 0.49, 0.40, 0.33, 0.27]
)

KAB_KOTA = {
    "3401": ("KULON PROGO", 12),
    "3402": ("BANTUL", 17),
    "3403": ("GUNUNGKIDUL", 18),
    "3404": ("SLEMAN", 17),
    "3471": ("KOTA YOGYAKARTA", 14),
}


def read_targets() -> dict:
    """Prefer the committed verification summary over the constants above."""
    targets = {
        "daily_rows": TARGET_DAILY_ROWS,
        "cells": TARGET_CELLS,
        "hourly_rows": TARGET_HOURLY_ROWS,
        "kapanewon": TARGET_KAPANEWON,
        "maids_max_daily": 10_971,
        "utm": {"x_min": 393_000, "y_min": 9_096_000,
                "x_max": 480_000, "y_max": 9_162_500},
    }
    if not VERIFICATION_JSON.exists():
        return targets
    summary = json.loads(VERIFICATION_JSON.read_text(encoding="utf-8"))
    daily, hourly = summary["daily_grid"], summary["hourly_kapanewon"]
    bounds = daily["derived_overpass_bbox_wgs84"]["utm_bounds"]
    targets.update({
        "daily_rows": daily["rows"],
        "cells": daily["unique_cells"],
        "hourly_rows": hourly["rows"],
        "kapanewon": hourly["unique_kapanewon"],
        "maids_max_daily": daily["n_maids_max"],
        # The committed bounds include Role 1's 500 m Overpass buffer, so step
        # inside it to keep every generated cell within the real extent.
        "utm": {
            "x_min": bounds["x_min"] + CELL_SIZE_M,
            "y_min": bounds["y_min"] + CELL_SIZE_M,
            "x_max": bounds["x_max"] - CELL_SIZE_M,
            "y_max": bounds["y_max"] - CELL_SIZE_M,
        },
    })
    return targets


# The real cell universe is whatever appeared in the CSV at least once, so a
# pool larger than the target is simulated and the quietest cells never make
# it in — exactly how k = 5 suppression decides the published universe.
POOL_MULTIPLIER = 1.6


def build_cell_universe(targets: dict) -> pd.DataFrame:
    """A candidate pool; the published universe is selected after simulation."""
    utm = targets["utm"]
    xs = np.arange(utm["x_min"], utm["x_max"], CELL_SIZE_M)
    ys = np.arange(utm["y_min"], utm["y_max"], CELL_SIZE_M)
    mesh_x, mesh_y = np.meshgrid(xs, ys)
    grid = pd.DataFrame({
        "x_min_utm": mesh_x.ravel().astype(int),
        "y_min_utm": mesh_y.ravel().astype(int),
    })
    pool_size = min(len(grid), int(targets["cells"] * POOL_MULTIPLIER))
    if pool_size < targets["cells"]:
        raise RuntimeError(
            f"The UTM extent only yields {len(grid):,} cells, fewer than the "
            f"{targets['cells']:,} required."
        )

    # Bias towards the middle so the synthetic region is a city, not a slab.
    centre_x, centre_y = grid.x_min_utm.mean(), grid.y_min_utm.mean()
    radius = np.hypot(grid.x_min_utm - centre_x, grid.y_min_utm - centre_y)
    weight = np.exp(-radius / radius.std())
    picked = RNG.choice(len(grid), size=pool_size, replace=False,
                        p=weight / weight.sum())
    cells = grid.iloc[np.sort(picked)].reset_index(drop=True)

    to_wgs = Transformer.from_crs(CRS_UTM, CRS_WGS84, always_xy=True)
    lon, lat = to_wgs.transform(
        cells.x_min_utm + CELL_SIZE_M / 2, cells.y_min_utm + CELL_SIZE_M / 2
    )
    cells["centroid_lon"] = np.round(lon, 6)
    cells["centroid_lat"] = np.round(lat, 6)
    cells["cell_id"] = (
        "C" + cells.x_min_utm.astype(str) + "_" + cells.y_min_utm.astype(str)
    )

    # Heavy-tailed baseline busyness: a few cells dominate, as in a real city.
    cells["base"] = RNG.lognormal(2.0, 1.15, len(cells))

    # Behaviour is attached using the REAL OSM snapshot, so a cell that
    # genuinely holds a campus behaves like a campus. Without this the
    # synthetic data would have no association for H1–H3 to find, and the
    # smoke test would exercise the arithmetic without exercising the result.
    facility_map = osm_cell_categories()
    keys = list(zip(cells.x_min_utm.astype(int), cells.y_min_utm.astype(int)))
    cells["behaviour"] = [facility_map.get(key, "") for key in keys]
    matched = int((cells["behaviour"] != "").sum())
    if matched == 0:
        raise RuntimeError(
            "No synthetic cell lined up with an OSM facility — check that the "
            "UTM extent matches the committed snapshot."
        )

    # The pull factor itself is applied per day in build_daily(), so nothing
    # further is needed here.
    cells.attrs["facility_cells"] = matched
    return cells


def osm_cell_categories() -> dict[tuple[int, int], str]:
    """Map 500 m cell origins to a study category, from the frozen snapshot.

    One representative point per element is enough here: the real polygon
    treatment, deduplication and site grouping are Role 2's work, and this
    only needs to put the signal in roughly the right places.
    """
    if not OSM_JSON.exists():
        raise RuntimeError(f"{OSM_JSON} is missing; it should be committed.")

    from src.ingest import classify_element_categories, load_config

    categories = load_config()["facility_categories"]
    priority = {name: index for index, name in enumerate(categories)}
    to_utm = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True)

    best: dict[tuple[int, int], str] = {}
    payload = json.loads(OSM_JSON.read_text(encoding="utf-8"))
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        matched = classify_element_categories(tags, categories)
        if not matched:
            continue
        point = representative_lonlat(element)
        if point is None:
            continue
        x, y = to_utm.transform(*point)
        key = (int(np.floor(x / CELL_SIZE_M) * CELL_SIZE_M),
               int(np.floor(y / CELL_SIZE_M) * CELL_SIZE_M))
        category = min(matched, key=lambda name: priority[name])
        if key not in best or priority[category] < priority[best[key]]:
            best[key] = category
    return best


def representative_lonlat(element: dict) -> tuple[float, float] | None:
    if element.get("type") == "node":
        if element.get("lon") is None:
            return None
        return float(element["lon"]), float(element["lat"])

    points = [p for p in element.get("geometry", []) or []
              if p and p.get("lon") is not None]
    if not points:
        for member in element.get("members", []) or []:
            points = [p for p in member.get("geometry", []) or []
                      if p and p.get("lon") is not None]
            if points:
                break
    if not points:
        return None
    return (float(np.mean([p["lon"] for p in points])),
            float(np.mean([p["lat"] for p in points])))


def daily_panel(dates: pd.DatetimeIndex) -> np.ndarray:
    """Panel size per day: smooth decay plus a step at each sample break."""
    panel = np.linspace(PANEL_START, PANEL_END, len(dates)).astype(float)
    for break_date, step in BREAK_STEPS.items():
        panel[dates >= pd.Timestamp(break_date)] *= step
    # The delivery failure: the day is published, but a fraction of normal.
    panel[dates == pd.Timestamp(ANOMALOUS_DATE)] *= 0.08
    return panel


def build_daily(cells: pd.DataFrame, targets: dict) -> pd.DataFrame:
    dates = pd.date_range(DATE_START, DATE_END, freq="D")
    panel = daily_panel(dates)
    nataru = pd.date_range(*NATARU)

    behaviour = cells["behaviour"].to_numpy()
    pull = np.array([CATEGORY_BEHAVIOUR.get(b, (1.0, 1.05, 1.0))[0] for b in behaviour])
    weekend = np.array([CATEGORY_BEHAVIOUR.get(b, (1.0, 1.05, 1.0))[1] for b in behaviour])
    holiday = np.array([CATEGORY_BEHAVIOUR.get(b, (1.0, 1.05, 1.0))[2] for b in behaviour])
    base = cells.base.to_numpy() * pull

    frames = []
    for day, day_panel in zip(dates, panel):
        factor = np.ones(len(cells))
        if day.day_of_week >= 5:
            factor = factor * weekend
        if day in nataru:
            factor = factor * holiday
        intensity = base * factor
        intensity = intensity / intensity.sum()
        counts = RNG.poisson(intensity * day_panel)

        keep = counts >= 5                      # k = 5: below this, no row
        if not keep.any():
            continue
        frames.append(pd.DataFrame({
            "cell_id": cells.cell_id.to_numpy()[keep],
            "x_min_utm": cells.x_min_utm.to_numpy()[keep],
            "y_min_utm": cells.y_min_utm.to_numpy()[keep],
            "centroid_lon": cells.centroid_lon.to_numpy()[keep],
            "centroid_lat": cells.centroid_lat.to_numpy()[keep],
            "date": day.strftime("%Y-%m-%d"),
            "n_maids": counts[keep],
        }))

    daily = pd.concat(frames, ignore_index=True)
    daily["n_maids"] = daily["n_maids"].clip(upper=targets["maids_max_daily"])
    return trim_to_target(select_published_universe(daily, targets), targets)


def select_published_universe(daily: pd.DataFrame, targets: dict) -> pd.DataFrame:
    """Keep the cells that were published most often, and only those.

    In the real data the 5,715-cell universe is not chosen in advance: it is
    whatever survived suppression. Selecting the best-covered cells from a
    larger pool reproduces that, and it is why the control group in the
    analysis is the *busiest of the quiet cells* rather than a fair sample of
    quiet places — a bias Role 3 has to report rather than remove.
    """
    published_days = daily.groupby("cell_id").size().sort_values(ascending=False)
    if len(published_days) < targets["cells"]:
        raise RuntimeError(
            f"Only {len(published_days):,} cells were ever published, fewer "
            f"than the {targets['cells']:,} required. Raise POOL_MULTIPLIER "
            "or PANEL_START."
        )
    keep = set(published_days.index[: targets["cells"]])
    return daily[daily["cell_id"].isin(keep)].reset_index(drop=True)


def trim_to_target(daily: pd.DataFrame, targets: dict) -> pd.DataFrame:
    """Hit the exact published row count without losing a cell or a date.

    Role 1 asserts 183,548 rows and 5,715 cells, so the synthetic file has to
    match both. Rows are dropped from the quietest end, which is also where
    real suppression bites, while one row per cell and per date is protected.
    """
    target = targets["daily_rows"]
    if len(daily) < target:
        raise RuntimeError(
            f"Generated only {len(daily):,} rows, fewer than the required "
            f"{target:,}. Raise PANEL_START and regenerate."
        )

    # Protect the row that keeps each cell, and each date, present.
    daily = daily.sort_values(["n_maids"], ascending=False).reset_index(drop=True)
    protected = pd.concat([
        daily.drop_duplicates("cell_id", keep="first"),
        daily.drop_duplicates("date", keep="first"),
    ]).index.unique()

    surplus = len(daily) - target
    droppable = daily.index.difference(protected)
    if surplus > len(droppable):
        raise RuntimeError(
            f"Cannot drop {surplus:,} rows while keeping every cell and date: "
            f"only {len(droppable):,} rows are unprotected."
        )
    # Drop from the quiet tail, where k = 5 suppression acts in the real data.
    drop = droppable[-surplus:] if surplus else droppable[:0]
    daily = daily.drop(index=drop)

    if daily["cell_id"].nunique() != targets["cells"]:
        raise RuntimeError(
            f"Cell universe is {daily['cell_id'].nunique():,}, expected "
            f"{targets['cells']:,}."
        )
    return daily.sort_values(["date", "cell_id"]).reset_index(drop=True)


def build_hourly(targets: dict) -> pd.DataFrame:
    names = []
    for kab_code, (kab_name, count) in KAB_KOTA.items():
        for index in range(1, count + 1):
            names.append({
                "kab_code": kab_code,
                "kab_kota": kab_name,
                "kapanewon_code": f"{kab_code}{index:02d}",
                "kapanewon": f"{kab_name.title().split()[-1]} {index:02d}",
            })
    kapanewon = pd.DataFrame(names)
    if len(kapanewon) != targets["kapanewon"]:
        raise RuntimeError(
            f"Built {len(kapanewon)} kapanewon, expected {targets['kapanewon']}."
        )

    base = RNG.lognormal(4.1, 0.60, len(kapanewon))
    dates = pd.date_range(DATE_START, DATE_END, freq="D")
    panel = daily_panel(dates)
    # A kapanewon aggregates thousands of devices, so panel decay pushes far
    # fewer of its hours below the k = 5 floor than it does a 500 m cell.
    scale = np.sqrt(panel / PANEL_START)

    frames = []
    for day, day_scale in zip(dates, scale):
        weekend = 0.86 if day.day_of_week >= 5 else 1.0
        for hour in range(24):
            level = base * HOUR_SHAPE[hour] * weekend * day_scale
            maids = RNG.poisson(np.maximum(level, 0))
            keep = maids >= 5
            if not keep.any():
                continue
            kept = maids[keep]
            frames.append(pd.DataFrame({
                "kab_code": kapanewon.kab_code.to_numpy()[keep],
                "kab_kota": kapanewon.kab_kota.to_numpy()[keep],
                "kapanewon_code": kapanewon.kapanewon_code.to_numpy()[keep],
                "kapanewon": kapanewon.kapanewon.to_numpy()[keep],
                "date": day.strftime("%Y-%m-%d"),
                "hour": hour,
                "n_maids": kept,
                "n_pings": np.maximum(kept * RNG.integers(3, 12, kept.size), 5),
            }))

    hourly = pd.concat(frames, ignore_index=True)
    if hourly["kapanewon_code"].nunique() != targets["kapanewon"]:
        raise RuntimeError("A kapanewon vanished entirely; raise the base level.")
    hourly = trim_hourly_to_target(hourly, targets)
    return hourly.sort_values(["date", "hour", "kapanewon_code"]).reset_index(drop=True)


def trim_hourly_to_target(hourly: pd.DataFrame, targets: dict) -> pd.DataFrame:
    """Hit the published hourly row count, keeping every kapanewon and slot.

    Role 1's test suite asserts 230,418 hourly rows, so the synthetic file has
    to match it for `pytest tests/` to stay green on sample data.
    """
    target = targets["hourly_rows"]
    if len(hourly) <= target:
        return hourly

    hourly = hourly.sort_values("n_maids", ascending=False).reset_index(drop=True)
    protected = pd.concat([
        hourly.drop_duplicates("kapanewon_code", keep="first"),
        hourly.drop_duplicates("date", keep="first"),
        hourly.drop_duplicates("hour", keep="first"),
    ]).index.unique()

    surplus = len(hourly) - target
    droppable = hourly.index.difference(protected)
    if surplus > len(droppable):
        raise RuntimeError(
            f"Cannot drop {surplus:,} hourly rows while keeping every "
            f"kapanewon, date and hour: only {len(droppable):,} are free."
        )
    # Drop from the quiet tail, where the k = 5 floor bites in the real data.
    return hourly.drop(index=droppable[-surplus:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", default="data/_sample/raw",
        help="where to write the synthetic CSVs (default: data/_sample/raw)",
    )
    args = parser.parse_args()
    out = (PROJECT_ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    targets = read_targets()
    cells = build_cell_universe(targets)
    daily = build_daily(cells, targets)
    hourly = build_hourly(targets)

    daily_path = out / "presence_cell500m_daily.csv"
    hourly_path = out / "presence_kapanewon_hourly.csv"
    daily.to_csv(daily_path, index=False)
    hourly.to_csv(hourly_path, index=False)

    possible = targets["cells"] * daily["date"].nunique()
    anomaly_rows = int((daily["date"] == ANOMALOUS_DATE).sum())
    typical = daily.groupby("date").size().median()

    print(f"cells  : {cells.attrs.get('facility_cells', 0):,} of "
          f"{len(cells):,} pooled cells line up with a real OSM facility, so "
          "the synthetic signal sits where the facilities actually are")
    print(f"daily  : {len(daily):,} rows (target {targets['daily_rows']:,}), "
          f"{daily['cell_id'].nunique():,} cells, "
          f"{daily['date'].nunique()} dates, "
          f"n_maids {daily['n_maids'].min()}–{daily['n_maids'].max()}")
    print(f"         {1 - len(daily) / possible:.1%} of cell-days absent "
          "(k = 5 suppression)")
    print(f"         {ANOMALOUS_DATE}: {anomaly_rows:,} rows vs a typical day's "
          f"{int(typical):,} — the delivery failure")
    print(f"hourly : {len(hourly):,} rows (target {targets['hourly_rows']:,}), "
          f"{hourly['kapanewon_code'].nunique()} kapanewon, "
          f"n_maids {hourly['n_maids'].min()}–{hourly['n_maids'].max()}")
    print(f"\nWritten to {out}")
    print("\nThese numbers are invented. Never put them in the report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
