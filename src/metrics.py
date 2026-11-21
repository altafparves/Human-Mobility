"""
Role 3: Mobility Analytics & Statistical Modeling Lead (Gold Layer)
-------------------------------------------------------------------
Responsibilities:
- Compute daily Published Presence Share (%) per cell across declared and common-support cell universes.
- Calculate cell-level Weekday-to-Weekend Ratios within each sampling period (excluding Nataru dates).
- Conduct matched-weekday Nataru holiday shockwave comparisons while isolating the Jan 1 sample break.
- Compute cluster-robust confidence intervals and hourly kapanewon diurnal summaries (n_maids, n_pings/n_maids).

Run from the repository root, after Role 1 and Role 2:

    python -m src.ingest             # Role 1 -> data/raw/, grid_cells_unique
    python -m src.clean_temporal     # Role 1 -> data/silver/ temporal tables
    python -m src.spatial_join       # Role 2 -> data/silver/grid_facilities.parquet
    python -m src.metrics            # Role 3 -> data/gold/

Reads
    configs/osm_tags.yaml                      thresholds, periods, categories
    data/silver/mobility_daily_clean.parquet   Role 1: cell x day, flags, coverage, share
    data/silver/kapanewon_hourly_clean.parquet Role 1: kapanewon x hour
    data/silver/grid_facilities.parquet        Role 2: cell -> categories, sites, baseline
    data/silver/cell_facility_links.parquet    Role 2: cell x site (optional, for clusters)

Writes to data/gold/ (Parquet, plus a JSON summary and a DuckDB file):
    facility_pull.parquet            RQ1  relative presence by category
    cell_metrics.parquet             RQ2  per eligible cell per period
    category_summary.parquet         RQ2  headline ratios with cluster-robust CIs
    coverage_sensitivity.parquet     RQ2  the same at 80 / 90 / 95 % coverage
    mixed_use_sensitivity.parquet    RQ2  all cells vs single-category cells
    matched_comparison.parquet       RQ1  against matched baseline cells
    event_window.parquet             RQ3  Nataru, exploratory, 1 January isolated
    kapanewon_hourly_profile.parquet RQ4  diurnal pulse and ping intensity
    gold_metrics_summary.json             counts, diagnostics, guardrails

Role 1 and Role 2 own their decisions and this module does not second-guess
them: eligibility is Role 1's `pass_<t>_in_period`, the weekday/weekend split
is Role 1's `is_ordinary_weekday/weekend`, and category membership is Role 2's
`has_<category>` flags rather than the display-only `primary_category`, as
Role 2's handoff asks.

Four rules are enforced in code rather than left to the analyst to remember,
because each is a way this dataset can produce a confident wrong answer:

1. Never compare across a sampling break. The published panel steps on
   1 January and 16 February 2022, so every ratio is computed *within* one
   `sampling_period` and a change in who is observed can never read as a
   change in who moved.
2. Earn your way into a comparison. A cell enters a period only through
   Role 1's coverage rule: >= 90 % publication coverage on ordinary weekdays
   *and* ordinary weekends, counted separately. 80 % and 95 % are reported
   alongside.
3. A share is a share of *published observations*. It describes how
   observations are distributed across space on a day. It is not a count of
   people, it cannot recover a regional total, and `n_maids` is a distinct
   count that is never summed across cells or dates.
4. Cell-days are not independent. A cell recurs across dates and a complex
   such as UGM spans 15 cells, so intervals come from a bootstrap that
   resamples *site clusters*, never rows.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import duckdb
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "osm_tags.yaml"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"

MOBILITY_DAILY_CLEAN = SILVER_DIR / "mobility_daily_clean.parquet"
KAPANEWON_HOURLY_CLEAN = SILVER_DIR / "kapanewon_hourly_clean.parquet"
GRID_FACILITIES = SILVER_DIR / "grid_facilities.parquet"
CELL_FACILITY_LINKS = SILVER_DIR / "cell_facility_links.parquet"

GOLD_SUMMARY_JSON = GOLD_DIR / "gold_metrics_summary.json"
GOLD_DUCKDB = GOLD_DIR / "city_magnets_gold.duckdb"

# Role 1's period labels. The four primary ones are bounded by the documented
# sample breaks; Mar-Apr is exploratory because the panel has decayed by then.
PRIMARY_PERIODS = ["2021_Dec", "2022_Jan", "2022_Feb_P1", "2022_Feb_P2"]

# Role 2 keeps transit as a flag rather than a cell class, because bus stops
# would make almost every urban cell mixed-use. It is still reported as a
# category here, with its overlap against the others made explicit.
TRANSIT_CATEGORY = "transit_hub"
# Role 2's label for cells with no mapped destination facility. Not
# "residential": such a cell may hold housing, farmland, roads, water, or an
# amenity nobody has mapped yet.
CONTROL_LABEL = "no_selected_facility"
BASELINE_LABEL = "baseline_candidate"

BOOTSTRAP_SAMPLES = 1_000
BOOTSTRAP_SEED = 42
# Below these counts an estimate describes almost nothing, so the row is
# written with its counts kept and the estimate withheld.
MIN_CLUSTERS_FOR_ESTIMATE = 5
MIN_MATCHED_PAIRS = 20
MIN_BASELINE_DAYS = 2
MIN_CELLS_FOR_EVENT = 10
MATCH_RADIUS_M = 2_000
COMMON_SUPPORT_PERCENTILES = (2.5, 97.5)
BALANCED_SMD = 0.10

RNG = np.random.default_rng(BOOTSTRAP_SEED)


# --------------------------------------------------------------------------
# configuration and inputs
# --------------------------------------------------------------------------
def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load the shared pipeline YAML. Role 3 adds no parameters of its own."""
    with open(config_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def read_silver_inputs() -> dict[str, pd.DataFrame]:
    """Load Role 1's temporal tables and Role 2's spatial tables.

    A missing table is an upstream question, not a crash to debug, so the
    error names the file and the command that produces it.
    """
    required = [
        ("daily", MOBILITY_DAILY_CLEAN, "python -m src.clean_temporal", "Role 1"),
        ("hourly", KAPANEWON_HOURLY_CLEAN, "python -m src.clean_temporal", "Role 1"),
        ("facilities", GRID_FACILITIES, "python -m src.spatial_join", "Role 2"),
    ]
    frames: dict[str, pd.DataFrame] = {}
    for key, path, command, owner in required:
        if not path.exists():
            raise FileNotFoundError(
                f"{path.relative_to(PROJECT_ROOT)} is missing. Run "
                f"`{command}` first ({owner})."
            )
        frames[key] = pd.read_parquet(path)

    # Optional: the cell x site long table gives exact site membership. Without
    # it, membership is read from the `site_ids` list column instead.
    frames["links"] = (
        pd.read_parquet(CELL_FACILITY_LINKS)
        if CELL_FACILITY_LINKS.exists() else pd.DataFrame()
    )
    return frames


def build_site_clusters(facilities: pd.DataFrame,
                        links: pd.DataFrame) -> pd.Series:
    """One cluster id per cell, so cells sharing a site share a cluster.

    This is what makes the bootstrap honest. UGM spans 15 cells; those cells
    share a place, its surroundings and its OSM mapping, so they are one unit
    of evidence rather than fifteen. Cells linked through a chain of shared
    sites join the same cluster, and a cell belonging to no site is its own.

    Role 2's `cell_facility_links.parquet` is used when present because it is
    the authoritative cell-site table; otherwise the `site_ids` list column
    carries the same information.
    """
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:            # path compression
            parent[node], node = root, parent[node]
        return root

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for cell_id in facilities["cell_id"]:
        parent.setdefault(str(cell_id), str(cell_id))

    if not links.empty and {"cell_id", "site_id", "counts_for_cell"} <= set(links.columns):
        pairs = links.loc[links["counts_for_cell"], ["cell_id", "site_id"]]
        membership = zip(pairs["cell_id"].astype(str), pairs["site_id"].astype(str))
    else:
        membership = (
            (str(row.cell_id), str(site))
            for row in facilities.itertuples()
            for site in (row.site_ids if row.site_ids is not None else [])
        )

    for cell_id, site_id in membership:
        site_key = f"site::{site_id}"
        parent.setdefault(cell_id, cell_id)
        parent.setdefault(site_key, site_key)
        union(cell_id, site_key)

    return pd.Series(
        {str(cell_id): find(str(cell_id)) for cell_id in facilities["cell_id"]},
        name="cluster_id",
    )


def prepare_facilities(facilities: pd.DataFrame, links: pd.DataFrame,
                       categories: list[str]) -> pd.DataFrame:
    """Normalise Role 2's table to what Role 3 joins on, and add cluster ids."""
    required = ["cell_id", "cell_class", "n_categories", "is_baseline_candidate"]
    missing = [column for column in required if column not in facilities.columns]
    if missing:
        raise KeyError(
            f"grid_facilities.parquet is missing {missing}. Columns present: "
            f"{sorted(facilities.columns)}. See docs/HANDOFF_ROLE3.md §6."
        )
    has_columns = [f"has_{category}" for category in categories]
    missing = [column for column in has_columns if column not in facilities.columns]
    if missing:
        raise KeyError(
            f"grid_facilities.parquet is missing {missing}; Role 3 groups by "
            "the has_<category> flags, not primary_category."
        )

    frame = facilities.copy()
    frame["cell_id"] = frame["cell_id"].astype(str)
    for column in has_columns:
        frame[column] = frame[column].fillna(False).astype(bool)
    frame["is_baseline_candidate"] = (
        frame["is_baseline_candidate"].fillna(False).astype(bool))
    frame["in_multicell_site"] = (
        frame.get("in_multicell_site", pd.Series(False, index=frame.index))
        .fillna(False).astype(bool))
    frame["n_categories"] = frame["n_categories"].fillna(0).astype(int)
    frame["cell_class"] = frame["cell_class"].fillna(CONTROL_LABEL)

    clusters = build_site_clusters(frame, links)
    frame["cluster_id"] = frame["cell_id"].map(clusters)

    keep = required + has_columns + [
        "cluster_id", "in_multicell_site", "primary_category",
    ]
    for optional in ("dist_to_facility_cell_m", "facility_names",
                     *[f"n_{category}" for category in categories]):
        if optional in frame.columns:
            keep.append(optional)
    keep = [column for column in dict.fromkeys(keep) if column in frame.columns]

    out = frame[keep].copy()
    multi = frame.loc[frame["in_multicell_site"], "cluster_id"]
    out.attrs["multi_cell_clusters"] = int(multi.nunique())
    sizes = frame.groupby("cluster_id")["cell_id"].nunique()
    out.attrs["largest_cluster_cells"] = int(sizes.max()) if len(sizes) else 0
    return out


# --------------------------------------------------------------------------
# uncertainty: cluster bootstrap over site clusters
# --------------------------------------------------------------------------
def cluster_bootstrap_median(frame: pd.DataFrame, value_column: str,
                             cluster_column: str = "cluster_id",
                             samples: int = BOOTSTRAP_SAMPLES
                             ) -> tuple[float, float, int]:
    """Percentile interval for a median, resampling whole clusters.

    One cluster is one draw, whatever the number of cells and days behind it.
    Resampling rows instead would treat correlated observations as independent
    and give an interval far too narrow to be honest.

    Returns (ci_low, ci_high, n_clusters).
    """
    usable = frame.loc[:, [value_column, cluster_column]].dropna()
    usable = usable[np.isfinite(usable[value_column].to_numpy(dtype=float))]
    if usable.empty:
        return (np.nan, np.nan, 0)

    groups = [part[value_column].to_numpy(dtype=float)
              for _, part in usable.groupby(cluster_column, sort=False)]
    n_clusters = len(groups)
    if n_clusters < MIN_CLUSTERS_FOR_ESTIMATE:
        return (np.nan, np.nan, n_clusters)

    medians = np.empty(samples, dtype=float)
    for index in range(samples):
        picks = RNG.integers(0, n_clusters, size=n_clusters)
        medians[index] = np.median(np.concatenate([groups[pick] for pick in picks]))
    low, high = np.percentile(medians, [2.5, 97.5])
    return (float(low), float(high), n_clusters)


def standardised_difference(treated: np.ndarray, control: np.ndarray) -> float:
    """Standardised mean difference, the usual covariate-balance diagnostic.

    Below about 0.1 is conventionally called balanced.
    """
    treated = treated[np.isfinite(treated)]
    control = control[np.isfinite(control)]
    if len(treated) < 2 or len(control) < 2:
        return np.nan
    pooled = np.sqrt((treated.var(ddof=1) + control.var(ddof=1)) / 2)
    if pooled == 0:
        # Neither group varies — every cell at 100 % coverage, say. There is
        # nothing to standardise against, so report exact agreement or none.
        return 0.0 if np.isclose(treated.mean(), control.mean()) else np.inf
    return float((treated.mean() - control.mean()) / pooled)


def standardise(values) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    spread = np.nanstd(array)
    return (array - np.nanmean(array)) / (spread if spread else 1.0)


# --------------------------------------------------------------------------
# RQ2: per-cell shares and the weekday-to-weekend ratio
# --------------------------------------------------------------------------
def build_cell_metrics(daily: pd.DataFrame, facilities: pd.DataFrame,
                       threshold: int) -> pd.DataFrame:
    """Per eligible cell per sampling period: mean shares and their ratio.

    Eligibility uses Role 1's *within-period* flag, because the ratio is a
    within-period quantity: a cell well covered in December but absent in
    February belongs in December's comparison and nowhere else.

    Two shares are carried through:

      published_share   denominator is every published cell that day
                        (Role 1's `published_presence_share_pct`)
      restricted_share  denominator is only the cells eligible in this period,
                        recomputed per day, so it stops moving as other cells
                        drop in and out

    If the two disagree, that disagreement is a finding about coverage and
    belongs in the report rather than being resolved quietly.
    """
    eligibility = f"pass_{threshold}_in_period"
    needed = [eligibility, "is_ordinary_weekday", "is_ordinary_weekend",
              "published_presence_share_pct", "sampling_period", "cell_id",
              "date", "n_maids", "x_min_utm", "y_min_utm",
              "centroid_lon", "centroid_lat", "period_ord_wd_coverage",
              "period_ord_we_coverage", f"pass_{threshold}_primary_window",
              f"pass_{threshold}_every_primary_period"]
    missing = [column for column in needed if column not in daily.columns]
    if missing:
        raise KeyError(
            f"mobility_daily_clean.parquet is missing {missing}. Columns "
            f"present: {sorted(daily.columns)}"
        )

    ordinary = daily[
        daily[eligibility].fillna(False)
        & (daily["is_ordinary_weekday"] | daily["is_ordinary_weekend"])
    ].copy()
    if ordinary.empty:
        return pd.DataFrame()

    # Restricted denominator: this period's eligible cells only, per day.
    day_total = ordinary.groupby(["sampling_period", "date"])["n_maids"].transform("sum")
    ordinary["restricted_share_pct"] = ordinary["n_maids"] / day_total * 100.0
    ordinary["day_type"] = np.where(
        ordinary["is_ordinary_weekend"], "weekend", "weekday")

    aggregated = (
        ordinary.groupby(["cell_id", "sampling_period", "day_type"], as_index=False)
        .agg(
            published_share=("published_presence_share_pct", "mean"),
            restricted_share=("restricted_share_pct", "mean"),
            mean_n_maids=("n_maids", "mean"),
            median_n_maids=("n_maids", "median"),
            days=("date", "nunique"),
        )
    )
    wide = aggregated.pivot_table(
        index=["cell_id", "sampling_period"], columns="day_type",
        values=["published_share", "restricted_share", "mean_n_maids",
                "median_n_maids", "days"],
    )
    wide.columns = [f"{measure}_{side}" for measure, side in wide.columns]
    wide = wide.reset_index()

    for measure in ("published_share", "restricted_share", "mean_n_maids",
                    "median_n_maids", "days"):
        for side in ("weekday", "weekend"):
            column = f"{measure}_{side}"
            if column not in wide.columns:
                wide[column] = np.nan

    wide["wd_we_ratio_published"] = (
        wide["published_share_weekday"] / wide["published_share_weekend"])
    wide["wd_we_ratio_restricted"] = (
        wide["restricted_share_weekday"] / wide["restricted_share_weekend"])
    # A ratio needs both sides. Role 1's rule makes this rare, but a cell with
    # no ordinary weekend observation is reported, not silently dropped.
    wide["ratio_defined"] = np.isfinite(
        wide["wd_we_ratio_restricted"].to_numpy(dtype=float))

    cell_attributes = (
        daily[["cell_id", "sampling_period", "x_min_utm", "y_min_utm",
               "centroid_lon", "centroid_lat", "period_ord_wd_coverage",
               "period_ord_we_coverage", f"pass_{threshold}_primary_window",
               f"pass_{threshold}_every_primary_period"]]
        .drop_duplicates(subset=["cell_id", "sampling_period"])
    )
    wide["cell_id"] = wide["cell_id"].astype(str)

    out = (
        wide.merge(cell_attributes, on=["cell_id", "sampling_period"], how="left")
        .merge(facilities, on="cell_id", how="left")
    )
    out["cell_class"] = out["cell_class"].fillna(CONTROL_LABEL)
    out["cluster_id"] = out["cluster_id"].fillna(out["cell_id"])
    out["is_baseline_candidate"] = out["is_baseline_candidate"].fillna(False).astype(bool)
    out["n_categories"] = out["n_categories"].fillna(0).astype(int)
    out["coverage_threshold"] = threshold
    out["min_period_coverage"] = out[
        ["period_ord_wd_coverage", "period_ord_we_coverage"]].min(axis=1)
    out["period_kind"] = np.where(
        out["sampling_period"].isin(PRIMARY_PERIODS), "primary", "exploratory")
    return out


def category_subsets(cell_metrics: pd.DataFrame, categories: list[str],
                     single_only: bool = False
                     ) -> Iterator[tuple[str, pd.DataFrame]]:
    """Yield (label, cells) per category, plus the baseline comparison group.

    Membership comes from Role 2's `has_<category>` flags, as Role 2's handoff
    instructs: `primary_category` is a display label, and a mixed-use cell
    genuinely holds every category it is flagged for, so it belongs in each of
    their comparisons. The groups therefore overlap, and `cells_shared_with_
    other_categories` records by how much.
    """
    for category in categories:
        part = cell_metrics[cell_metrics[f"has_{category}"]]
        if single_only:
            part = part[part["cell_class"] == "single_category"]
        yield category, part

    baseline = cell_metrics[cell_metrics["is_baseline_candidate"]]
    yield BASELINE_LABEL, baseline


def summarise_categories(cell_metrics: pd.DataFrame, categories: list[str],
                         ratio_column: str = "wd_we_ratio_restricted",
                         subset_label: str = "all cells",
                         single_only: bool = False) -> pd.DataFrame:
    """Median weekday/weekend ratio per category per period, with a cluster CI."""
    rows = []
    for period, period_cells in cell_metrics.groupby("sampling_period"):
        for category, part in category_subsets(period_cells, categories,
                                               single_only=single_only):
            if part.empty:
                continue
            values = part[ratio_column].to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            low, high, n_clusters = cluster_bootstrap_median(part, ratio_column)
            shared = (
                int((part["n_categories"] > 1).sum())
                if category not in (BASELINE_LABEL, TRANSIT_CATEGORY)
                else int((part["n_categories"] > 0).sum())
                if category == TRANSIT_CATEGORY else 0
            )
            rows.append({
                "sampling_period": period,
                "period_kind": "primary" if period in PRIMARY_PERIODS
                               else "exploratory",
                "category": category,
                "subset": subset_label,
                "cells": int(len(part)),
                "clusters": int(part["cluster_id"].nunique()),
                "clusters_with_ratio": int(n_clusters),
                "cells_with_ratio": int(len(finite)),
                "ratio_undefined": int(len(part) - len(finite)),
                "cells_shared_with_other_categories": shared,
                "median_ratio": float(np.median(finite)) if len(finite) else np.nan,
                "ci_low": low,
                "ci_high": high,
                "median_restricted_share_weekday": float(
                    part["restricted_share_weekday"].median()),
                "median_restricted_share_weekend": float(
                    part["restricted_share_weekend"].median()),
                "median_period_coverage": float(part["min_period_coverage"].median()),
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["evidence"] = np.where(
        out["clusters_with_ratio"] >= MIN_CLUSTERS_FOR_ESTIMATE,
        "reported",
        f"withheld: fewer than {MIN_CLUSTERS_FOR_ESTIMATE} site clusters",
    )
    thin = out["evidence"] != "reported"
    out.loc[thin, ["median_ratio", "ci_low", "ci_high"]] = np.nan
    return out.sort_values(
        ["sampling_period", "median_ratio"], ascending=[True, False]
    ).reset_index(drop=True)


# --------------------------------------------------------------------------
# RQ1: relative presence by category
# --------------------------------------------------------------------------
def build_facility_pull(cell_metrics: pd.DataFrame,
                        categories: list[str]) -> pd.DataFrame:
    """Median published presence share by category, per sampling period.

    This answers RQ1 descriptively. It is a share of published observations,
    so it says how observations are distributed across kinds of place — not
    how many people were anywhere. The matched comparison that follows is what
    makes the contrast with baseline cells defensible.
    """
    rows = []
    for period, period_cells in cell_metrics.groupby("sampling_period"):
        for category, part in category_subsets(period_cells, categories):
            if part.empty:
                continue
            low, high, n_clusters = cluster_bootstrap_median(
                part, "restricted_share_weekday")
            rows.append({
                "sampling_period": period,
                "period_kind": "primary" if period in PRIMARY_PERIODS
                               else "exploratory",
                "category": category,
                "cells": int(len(part)),
                "clusters": int(part["cluster_id"].nunique()),
                "clusters_with_value": int(n_clusters),
                "median_share_weekday_pct": float(
                    part["restricted_share_weekday"].median()),
                "ci_low": low,
                "ci_high": high,
                "median_share_weekend_pct": float(
                    part["restricted_share_weekend"].median()),
                "median_mean_n_maids_weekday": float(
                    part["mean_n_maids_weekday"].median()),
                "median_period_coverage": float(
                    part["min_period_coverage"].median()),
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["evidence"] = np.where(
        out["clusters_with_value"] >= MIN_CLUSTERS_FOR_ESTIMATE,
        "reported",
        f"withheld: fewer than {MIN_CLUSTERS_FOR_ESTIMATE} site clusters",
    )
    thin = out["evidence"] != "reported"
    out.loc[thin, ["median_share_weekday_pct", "median_share_weekend_pct",
                   "ci_low", "ci_high"]] = np.nan
    return out.sort_values(
        ["sampling_period", "median_share_weekday_pct"], ascending=[True, False]
    ).reset_index(drop=True)


# --------------------------------------------------------------------------
# RQ1: matched comparison against baseline cells
# --------------------------------------------------------------------------
def build_matched_comparison(cell_metrics: pd.DataFrame,
                             categories: list[str]) -> pd.DataFrame:
    """Match each facility cell to a nearby baseline cell and compare.

    Role 2 built the baseline set by distance (`is_baseline_candidate`: no
    mapped destination facility, centroid within 2 km of a facility cell) and
    left matching on coverage and activity to Role 3, which is what happens
    here: 1:1 without replacement, inside one sampling period, closest on a
    combined distance over standardised publication coverage and standardised
    overall activity. Activity is included because proximity and coverage
    alone leave the busy paired with the quiet; the outcome is a *ratio*, so
    matching on the activity level is not matching on the outcome.

    The comparison is observational and is reported with its residual
    imbalance. These cells were never randomised.
    """
    rows = []
    for period, part in cell_metrics.groupby("sampling_period"):
        pool = part.copy()
        pool["z_coverage"] = standardise(pool["min_period_coverage"])
        pool["z_activity"] = standardise(
            np.log10(pool["restricted_share_weekday"].clip(lower=1e-9)))

        controls = pool[pool["is_baseline_candidate"]]
        if controls.empty:
            continue
        control_xy = controls[["x_min_utm", "y_min_utm"]].to_numpy(dtype=float)
        control_z = controls[["z_coverage", "z_activity"]].to_numpy(dtype=float)
        control_ratio = controls["wd_we_ratio_restricted"].to_numpy(dtype=float)
        control_coverage = controls["min_period_coverage"].to_numpy(dtype=float)

        # Common support: a facility cell busier than every baseline cell has
        # no honest counterpart, and matching it anyway would pair a mall with
        # the quietest thing available and call the gap an effect.
        low_support, high_support = np.nanpercentile(
            controls["z_activity"].to_numpy(dtype=float),
            COMMON_SUPPORT_PERCENTILES)

        used = np.zeros(len(controls), dtype=bool)
        for category in categories:
            treated = pool[pool[f"has_{category}"]]
            if treated.empty:
                continue
            in_support = treated["z_activity"].between(low_support, high_support)
            outside_support = int((~in_support).sum())
            candidates = treated[in_support]
            if candidates.empty:
                rows.append(empty_match_row(period, category, outside_support,
                                            len(treated)))
                continue

            # Random order, so the cells processed first are not quietly given
            # the best available matches.
            candidates = candidates.sample(frac=1.0, random_state=BOOTSTRAP_SEED)
            pairs = []
            for cell in candidates.itertuples():
                distance = np.hypot(control_xy[:, 0] - cell.x_min_utm,
                                    control_xy[:, 1] - cell.y_min_utm)
                near = (distance <= MATCH_RADIUS_M) & ~used
                if not near.any():
                    continue
                penalty = np.hypot(control_z[:, 0] - cell.z_coverage,
                                   control_z[:, 1] - cell.z_activity)
                penalty = np.where(near, penalty, np.inf)
                pick = int(np.argmin(penalty))
                if not np.isfinite(penalty[pick]):
                    continue
                used[pick] = True
                pairs.append((cell, pick))

            if not pairs:
                rows.append(empty_match_row(period, category, outside_support,
                                            len(treated)))
                continue

            picks = [pick for _, pick in pairs]
            treated_ratio = np.array(
                [cell.wd_we_ratio_restricted for cell, _ in pairs], dtype=float)
            matched_ratio = control_ratio[picks]
            treated_coverage = np.array(
                [cell.min_period_coverage for cell, _ in pairs], dtype=float)
            treated_activity = np.array(
                [cell.z_activity for cell, _ in pairs], dtype=float)

            # The difference is paired, so the cluster is the treated site.
            paired = pd.DataFrame({
                "difference": treated_ratio - matched_ratio,
                "cluster_id": [cell.cluster_id for cell, _ in pairs],
            })
            low, high, n_clusters = cluster_bootstrap_median(paired, "difference")

            rows.append({
                "sampling_period": period,
                "period_kind": "primary" if period in PRIMARY_PERIODS
                               else "exploratory",
                "category": category,
                "treated_cells": int(len(treated)),
                "matched_pairs": int(len(pairs)),
                "unmatched_treated": int(len(candidates) - len(pairs)),
                "outside_common_support": outside_support,
                "treated_clusters": int(n_clusters),
                "median_ratio_treated": float(np.nanmedian(treated_ratio)),
                "median_ratio_control": float(np.nanmedian(matched_ratio)),
                "median_difference": float(
                    np.nanmedian(treated_ratio - matched_ratio)),
                "ci_low": low,
                "ci_high": high,
                "smd_coverage_before": standardised_difference(
                    treated_coverage, control_coverage),
                "smd_coverage_after": standardised_difference(
                    treated_coverage, control_coverage[picks]),
                "smd_activity_before": standardised_difference(
                    treated_activity, control_z[:, 1]),
                "smd_activity_after": standardised_difference(
                    treated_activity, control_z[picks, 1]),
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    # Withhold the thin comparisons. The panel decays hard after February, so
    # late periods otherwise produce a difference built on one or two pairs,
    # whose balance diagnostic would dominate the headline while describing
    # almost nothing.
    out["evidence"] = np.where(
        out["matched_pairs"] >= MIN_MATCHED_PAIRS,
        "observational",
        f"withheld: fewer than {MIN_MATCHED_PAIRS} matched pairs",
    )
    thin = out["evidence"] != "observational"
    out.loc[thin, ["median_ratio_treated", "median_ratio_control",
                   "median_difference", "ci_low", "ci_high",
                   "smd_coverage_after", "smd_activity_after"]] = np.nan

    reported = out[out["evidence"] == "observational"]
    worst = (
        pd.concat([reported["smd_coverage_after"].abs(),
                   reported["smd_activity_after"].abs()])
        .replace(np.inf, np.nan).max()
        if not reported.empty else np.nan
    )
    out.attrs["worst_residual_smd"] = float(worst) if pd.notna(worst) else np.nan
    return out.sort_values(["sampling_period", "category"]).reset_index(drop=True)


def empty_match_row(period: str, category: str, outside_support: int,
                    treated_cells: int) -> dict[str, Any]:
    return {
        "sampling_period": period,
        "period_kind": "primary" if period in PRIMARY_PERIODS else "exploratory",
        "category": category,
        "treated_cells": treated_cells,
        "matched_pairs": 0,
        "unmatched_treated": 0,
        "outside_common_support": outside_support,
        "treated_clusters": 0,
        "median_ratio_treated": np.nan,
        "median_ratio_control": np.nan,
        "median_difference": np.nan,
        "ci_low": np.nan,
        "ci_high": np.nan,
        "smd_coverage_before": np.nan,
        "smd_coverage_after": np.nan,
        "smd_activity_before": np.nan,
        "smd_activity_after": np.nan,
    }


# --------------------------------------------------------------------------
# RQ3: the Nataru event window, exploratory
# --------------------------------------------------------------------------
def build_event_window(daily: pd.DataFrame, facilities: pd.DataFrame,
                       categories: list[str], threshold: int) -> pd.DataFrame:
    """Each Nataru date against non-event dates of the same weekday.

    No single holiday-uplift number is produced, and the reason is specific:
    the window runs 24 December to 2 January and **1 January is a sampling
    break**. One ratio spanning that date cannot separate a holiday effect
    from a change in who is observed, so presenting one would imply a
    precision the data cannot support.

    What is produced instead is per-date, within one sampling period, matched
    on weekday, with the support behind each value recorded and the value
    withheld when that support is thin or the date is the break itself.

    Matching on weekday removes the weekly cycle. It does not remove a
    spatially varying change in sample composition, and nothing available here
    does, which is why the whole table is labelled exploratory.
    """
    eligibility = f"pass_{threshold}_in_period"
    columns = ["cell_id", "cluster_id", "is_baseline_candidate",
               *[f"has_{category}" for category in categories]]
    frame = (
        daily[daily[eligibility].fillna(False) & ~daily["is_anomalous_date"]]
        .assign(cell_id=lambda f: f["cell_id"].astype(str))
        .merge(facilities[columns], on="cell_id", how="left")
    )
    if frame.empty:
        return pd.DataFrame()

    baseline = (
        frame[~frame["is_nataru_window"]]
        .groupby(["cell_id", "sampling_period", "day_of_week"], as_index=False)
        .agg(baseline_share=("published_presence_share_pct", "mean"),
             baseline_days=("date", "nunique"))
    )
    event = frame[frame["is_nataru_window"]].merge(
        baseline, on=["cell_id", "sampling_period", "day_of_week"], how="left")
    if event.empty:
        return pd.DataFrame()

    event["has_support"] = event["baseline_days"].fillna(0) >= MIN_BASELINE_DAYS
    event["relative_presence"] = np.where(
        event["has_support"] & (event["baseline_share"] > 0),
        event["published_presence_share_pct"] / event["baseline_share"],
        np.nan,
    )

    rows = []
    for category in [*categories, BASELINE_LABEL]:
        column = ("is_baseline_candidate" if category == BASELINE_LABEL
                  else f"has_{category}")
        part = event[event[column].fillna(False)]
        if part.empty:
            continue
        grouped = (
            part.groupby(["sampling_period", "date"], as_index=False)
            .agg(cells=("cell_id", "nunique"),
                 clusters=("cluster_id", "nunique"),
                 cells_with_support=("has_support", "sum"),
                 median_relative_presence=("relative_presence", "median"),
                 day_of_week=("day_of_week", "first"),
                 is_sample_break=("is_sample_break", "max"),
                 median_baseline_days=("baseline_days", "median"))
        )
        grouped.insert(2, "category", category)
        rows.append(grouped)

    if not rows:
        return pd.DataFrame()
    summary = pd.concat(rows, ignore_index=True)
    summary["evidence"] = np.where(
        summary["cells_with_support"] >= MIN_CELLS_FOR_EVENT,
        "exploratory",
        f"withheld: fewer than {MIN_CELLS_FOR_EVENT} cells with baseline",
    )
    summary.loc[summary["is_sample_break"].astype(bool), "evidence"] = (
        "withheld: 1 January sampling break")
    summary.loc[summary["evidence"] != "exploratory",
                "median_relative_presence"] = np.nan
    return summary.sort_values(["date", "category"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# RQ4: the diurnal pulse
# --------------------------------------------------------------------------
def build_kapanewon_profile(hourly: pd.DataFrame, threshold: int) -> pd.DataFrame:
    """Hourly profile for sub-districts that clear Role 1's hourly coverage.

    `pings_per_maid` is a **reporting-intensity diagnostic**: how talkative
    the apps were, not how many people were present. It must never be read as
    a crowd measure.

    Sub-districts cannot be linked to individual grid cells without a boundary
    layer or an explicit crosswalk, so this layer stays macro context, exactly
    as the brief specifies.
    """
    eligibility = f"pass_{threshold}_hourly_in_period"
    if eligibility not in hourly.columns:
        raise KeyError(
            f"{eligibility} is missing from kapanewon_hourly_clean.parquet. "
            f"Columns present: {sorted(hourly.columns)}"
        )

    frame = hourly[hourly[eligibility].fillna(False) & ~hourly["is_anomalous_date"]]
    if frame.empty:
        return pd.DataFrame()

    frame = frame.assign(
        day_type=np.where(frame["is_weekend"], "weekend", "weekday"))
    profile = (
        frame.groupby(["sampling_period", "kab_code", "kab_kota",
                       "kapanewon_code", "kapanewon", "hour_wib", "day_type"],
                      as_index=False)
        .agg(median_n_maids=("n_maids", "median"),
             mean_n_maids=("n_maids", "mean"),
             median_pings_per_maid=("pings_per_maid", "median"),
             observed_days=("date", "nunique"),
             period_hourly_coverage=("period_hourly_coverage", "first"))
    )
    profile["period_kind"] = np.where(
        profile["sampling_period"].isin(PRIMARY_PERIODS), "primary", "exploratory")

    # Peak hour per kapanewon, per period, per day type — the answer to RQ4.
    profile["is_peak_hour"] = False
    peak_index = profile.groupby(
        ["sampling_period", "kapanewon_code", "day_type"])["median_n_maids"].idxmax()
    profile.loc[peak_index, "is_peak_hour"] = True
    return profile


# --------------------------------------------------------------------------
def write_gold(outputs: dict[str, pd.DataFrame]) -> list[str]:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    if GOLD_DUCKDB.exists():
        GOLD_DUCKDB.unlink()
    connection = duckdb.connect(str(GOLD_DUCKDB))
    written = []
    try:
        for name, frame in outputs.items():
            if frame is None or frame.empty:
                print(f"  {name}: empty, skipped")
                continue
            # List columns (Role 2's site_ids, facility_names) survive parquet
            # but not DuckDB's CREATE TABLE, so they are joined for SQL only.
            flat = frame.copy()
            for column in flat.columns:
                if flat[column].map(lambda v: isinstance(v, (list, np.ndarray))).any():
                    flat[column] = flat[column].map(
                        lambda v: "; ".join(map(str, v))
                        if isinstance(v, (list, np.ndarray)) else v)
            frame.to_parquet(GOLD_DIR / f"{name}.parquet", index=False)
            connection.register(f"{name}_df", flat)
            connection.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_df")
            print(f"  wrote {name}: {len(frame):,} rows x {frame.shape[1]} cols")
            written.append(name)
    finally:
        connection.close()
    return written


def run_gold_metrics() -> dict[str, Any]:
    """Build every Gold table and return a JSON-serialisable summary."""
    config = load_config()
    categories = list(config["facility_categories"])
    coverage_config = config["analysis"]["coverage_thresholds"]
    primary_threshold = int(round(coverage_config["primary"] * 100))
    sensitivity = [int(round(value * 100))
                   for value in coverage_config["sensitivity"]]

    print("Reading Silver inputs ...")
    frames = read_silver_inputs()
    daily, hourly = frames["daily"], frames["hourly"]
    facilities = prepare_facilities(
        frames["facilities"], frames["links"], categories)

    facility_cells = int((facilities["n_categories"] > 0).sum())
    print(f"  {len(daily):,} cell-days, {daily['cell_id'].nunique():,} cells, "
          f"{len(hourly):,} kapanewon-hours")
    print(f"  Role 2: {facility_cells:,} cells hold a destination facility, "
          f"{int(facilities['is_baseline_candidate'].sum()):,} are baseline "
          "candidates")
    print(f"  site clusters: {facilities.attrs['multi_cell_clusters']:,} span "
          f"more than one cell (largest: "
          f"{facilities.attrs['largest_cluster_cells']} cells)")
    if frames["links"].empty:
        print("  note: cell_facility_links.parquet absent; clusters built from "
              "the site_ids column instead")

    print(f"\n1. Cell metrics at the primary threshold ({primary_threshold}%) ...")
    cell_metrics = build_cell_metrics(daily, facilities, primary_threshold)
    if cell_metrics.empty:
        raise RuntimeError(
            f"No cell cleared pass_{primary_threshold}_in_period. Check "
            "Role 1's coverage audit before going further."
        )
    primary = cell_metrics[cell_metrics["period_kind"] == "primary"]
    print(f"  {len(cell_metrics):,} cell-periods "
          f"({len(primary):,} in the primary window) over "
          f"{cell_metrics['cluster_id'].nunique():,} site clusters")
    print("  " + primary["cell_class"].value_counts().to_string()
          .replace("\n", "\n  "))
    undefined = int((~cell_metrics["ratio_defined"]).sum())
    if undefined:
        print(f"  {undefined:,} ratios undefined (no ordinary weekend "
              "observation)")

    print("\n2. RQ1 facility pull — median presence share by category ...")
    facility_pull = build_facility_pull(primary, categories)
    show = facility_pull[facility_pull["evidence"] == "reported"]
    if not show.empty:
        print(show[["sampling_period", "category", "cells", "clusters",
                    "median_share_weekday_pct", "ci_low", "ci_high"]]
              .to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

    print("\n3. RQ2 weekday-to-weekend ratio by category ...")
    category_summary = summarise_categories(primary, categories)
    show = category_summary[category_summary["evidence"] == "reported"]
    if not show.empty:
        print(show[["sampling_period", "category", "cells_with_ratio",
                    "clusters", "median_ratio", "ci_low", "ci_high",
                    "median_period_coverage"]]
              .to_string(index=False, float_format=lambda v: f"{v:,.3f}"))

    print("\n4. Sensitivity to the coverage rule ...")
    sensitivity_frames = []
    for threshold in sensitivity:
        alternative = build_cell_metrics(daily, facilities, threshold)
        if alternative.empty:
            continue
        alternative = alternative[alternative["period_kind"] == "primary"]
        summary = summarise_categories(
            alternative, categories, subset_label=f"coverage {threshold}%")
        summary["coverage_threshold"] = threshold
        sensitivity_frames.append(summary)
    coverage_sensitivity = (
        pd.concat(sensitivity_frames, ignore_index=True)
        if sensitivity_frames else pd.DataFrame()
    )
    if not coverage_sensitivity.empty:
        pivot = coverage_sensitivity.pivot_table(
            index="category", columns="coverage_threshold",
            values="median_ratio", aggfunc="median")
        print(pivot.to_string(float_format=lambda v: f"{v:,.3f}",
                              na_rep="withheld"))
        print("  A ranking that flips across these columns was an artefact of "
              "the rule, not a finding.")

    print("\n5. Mixed-use sensitivity ...")
    mixed_use_sensitivity = pd.concat([
        summarise_categories(primary, categories, subset_label="all cells"),
        summarise_categories(primary, categories,
                             subset_label="single-category only",
                             single_only=True),
    ], ignore_index=True)
    comparison = mixed_use_sensitivity.pivot_table(
        index="category", columns="subset", values="median_ratio",
        aggfunc="median")
    print(comparison.to_string(float_format=lambda v: f"{v:,.3f}",
                               na_rep="withheld"))

    print("\n6. RQ1 matched comparison against baseline cells ...")
    matched = build_matched_comparison(primary, categories)
    worst_smd = np.nan
    if not matched.empty:
        print(matched[["sampling_period", "category", "matched_pairs",
                       "outside_common_support", "median_difference",
                       "ci_low", "ci_high", "smd_coverage_after",
                       "smd_activity_after"]]
              .to_string(index=False, float_format=lambda v: f"{v:,.3f}",
                         na_rep="withheld"))
        excluded = int(matched["outside_common_support"].sum())
        attempted = excluded + int(matched["matched_pairs"].sum())
        if attempted:
            print(f"\n  {excluded:,} of {attempted:,} facility cells sit "
                  "outside the activity range of ANY baseline cell and were "
                  "excluded. That is itself a result: for those places there "
                  "is no comparable unmapped cell in DIY.")
        withheld = int((matched["evidence"] != "observational").sum())
        if withheld:
            print(f"  {withheld} of {len(matched)} category-periods withheld: "
                  f"fewer than {MIN_MATCHED_PAIRS} matched pairs.")
        worst_smd = matched.attrs.get("worst_residual_smd", np.nan)
        if pd.notna(worst_smd):
            verdict = ("balanced" if worst_smd < BALANCED_SMD
                       else "acceptable" if worst_smd < 0.25
                       else "NOT balanced — say so in the report")
            print(f"\n  Largest residual imbalance among reported "
                  f"comparisons: {worst_smd:.3f} ({verdict}; below "
                  f"{BALANCED_SMD} is the usual bar)")
            print("  These cells were never randomised, so the wording is "
                  "'associated with', never 'caused by'.")

    print("\n7. RQ3 Nataru event window, exploratory ...")
    event_window = build_event_window(
        daily, facilities, categories, primary_threshold)
    if not event_window.empty:
        print("  " + event_window["evidence"].value_counts()
              .to_string().replace("\n", "\n  "))
        print("  No single holiday-uplift value is produced: the window "
              "crosses the 1 January sampling break.")

    print("\n8. RQ4 diurnal pulse ...")
    kapanewon_profile = build_kapanewon_profile(hourly, primary_threshold)
    if not kapanewon_profile.empty:
        eligible = kapanewon_profile["kapanewon_code"].nunique()
        peaks = kapanewon_profile[
            kapanewon_profile["is_peak_hour"]
            & (kapanewon_profile["period_kind"] == "primary")
            & (kapanewon_profile["day_type"] == "weekday")
        ]
        print(f"  {eligible} kapanewon clear {primary_threshold}% hourly "
              f"coverage; {len(kapanewon_profile):,} profile rows")
        if not peaks.empty:
            common = peaks["hour_wib"].value_counts().head(3)
            hours = ", ".join(f"{int(hour):02d}:00 ({count})"
                              for hour, count in common.items())
            print(f"  most common weekday peak hours (WIB): {hours}")

    outputs = {
        "facility_pull": facility_pull,
        "cell_metrics": cell_metrics,
        "category_summary": category_summary,
        "coverage_sensitivity": coverage_sensitivity,
        "mixed_use_sensitivity": mixed_use_sensitivity,
        "matched_comparison": matched,
        "event_window": event_window,
        "kapanewon_hourly_profile": kapanewon_profile,
    }
    print()
    written = write_gold(outputs)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage_threshold_primary_pct": primary_threshold,
        "coverage_thresholds_sensitivity_pct": sensitivity,
        "category_membership": "Role 2's has_<category> flags; "
                               "primary_category is a display label only",
        "transit_note": "transit_hub is Role 2's flag, excluded from "
                        "cell_class and n_categories, so its cells overlap "
                        "the destination categories",
        "bootstrap": {
            "samples": BOOTSTRAP_SAMPLES,
            "seed": BOOTSTRAP_SEED,
            "cluster_unit": "cluster_id (cells sharing a Role 2 site)",
            "multi_cell_clusters": facilities.attrs["multi_cell_clusters"],
            "largest_cluster_cells": facilities.attrs["largest_cluster_cells"],
        },
        "eligible_cell_periods": int(len(cell_metrics)),
        "eligible_cell_periods_primary": int(len(primary)),
        "eligible_cell_classes_primary": {
            str(key): int(value)
            for key, value in primary["cell_class"].value_counts().items()
        },
        "distinct_clusters": int(cell_metrics["cluster_id"].nunique()),
        "ratios_undefined": undefined,
        "matched_comparison": {
            "rows": int(len(matched)),
            "withheld_rows": int((matched["evidence"] != "observational").sum())
                             if not matched.empty else 0,
            "outside_common_support_cells": int(
                matched["outside_common_support"].sum())
                if not matched.empty else 0,
            "worst_residual_smd_after_matching":
                None if pd.isna(worst_smd) else round(float(worst_smd), 4),
            "balanced_threshold": BALANCED_SMD,
            "baseline_set": "Role 2's is_baseline_candidate, then matched on "
                            "proximity, coverage and activity",
        },
        "event_window": {
            "rows": int(len(event_window)),
            "evidence_counts": (
                {str(key): int(value) for key, value
                 in event_window["evidence"].value_counts().items()}
                if not event_window.empty else {}
            ),
            "single_holiday_uplift_value_produced": False,
            "reason": "The Nataru window crosses the 1 January sampling break, "
                      "so one value cannot separate a holiday effect from a "
                      "change in sample composition.",
        },
        "gold_tables_written": written,
        "interpretation_guardrails": [
            "n_maids is a distinct count and is never summed across cells or dates.",
            "Shares describe the spatial distribution of published observations, "
            "not population or pedestrian counts.",
            "Suppressed cell-days (k = 5) are missing, not zero; suppression "
            "removes the quietest places first, so the surviving baseline cells "
            "are the busiest of the quiet ones.",
            "Every ratio is computed within one sampling period, never across "
            "the 1 January or 16 February breaks.",
            "Category groups overlap: a mixed-use cell counts in each category "
            "it holds, and transit_hub overlaps all of them.",
            "Co-location in a 500 m cell is association, not causation.",
        ],
    }
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    with open(GOLD_SUMMARY_JSON, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print(f"\nGold layer written to {GOLD_DIR.relative_to(PROJECT_ROOT)}")
    return summary


def main() -> int:
    try:
        run_gold_metrics()
    except (FileNotFoundError, KeyError) as problem:
        # A missing table or column is an upstream contract question, not a
        # crash to debug. Say what is wrong and stop.
        message = problem.args[0] if problem.args else problem
        print(f"\n  {message}", file=sys.stderr)
        print("  See docs/HANDOFF_ROLE3.md for the input contract.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
