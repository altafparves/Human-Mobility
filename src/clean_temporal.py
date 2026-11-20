"""
Role 1: Temporal Cleaning & Coverage Audit Lead (Bronze -> Silver Layer)
------------------------------------------------------------------------
Responsibilities:
- Parse dates and standardize timestamps to WIB (UTC+7).
- Flag anomalous dates (2022-03-08), sample breaks (2022-01-01, 2022-02-16), and Nataru window.
- Define sampling periods (2021_Dec, 2022_Jan, 2022_Feb_P1, 2022_Feb_P2, 2022_Mar_Apr_Exploratory).
- Build full expected cell-date calendar and calculate weekday/weekend publication coverage.
- Apply >= 90% coverage filter (with 80% and 95% sensitivity flags) and export Silver Parquet tables.
- Clean hourly kapanewon dataset (WIB timestamps, pings_per_maid, hourly coverage audit).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "osm_tags.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"

DAILY_CSV_PATH = RAW_DIR / "presence_cell500m_daily.csv"
HOURLY_CSV_PATH = RAW_DIR / "presence_kapanewon_hourly.csv"
UNIQUE_CELLS_PARQUET = SILVER_DIR / "grid_cells_unique.parquet"

MOBILITY_DAILY_CLEAN_PARQUET = SILVER_DIR / "mobility_daily_clean.parquet"
CELL_COVERAGE_AUDIT_PARQUET = SILVER_DIR / "cell_coverage_audit.parquet"
DAILY_COVERAGE_SUMMARY_PARQUET = SILVER_DIR / "daily_coverage_summary.parquet"
KAPANEWON_HOURLY_CLEAN_PARQUET = SILVER_DIR / "kapanewon_hourly_clean.parquet"
KAPANEWON_COVERAGE_AUDIT_PARQUET = SILVER_DIR / "kapanewon_coverage_audit.parquet"
TEMPORAL_SUMMARY_JSON = SILVER_DIR / "temporal_cleaning_summary.json"


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load pipeline YAML configuration."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def assign_sampling_period(dt: pd.Timestamp) -> str:
    """
    Assign each date to its sampling period per Step 2 of the Project Brief:
    - 2021_Dec: 2021-12-01 to 2021-12-31
    - 2022_Jan: 2022-01-01 to 2022-01-31
    - 2022_Feb_P1: 2022-02-01 to 2022-02-15 (pre-16 Feb break)
    - 2022_Feb_P2: 2022-02-16 to 2022-02-28 (post-16 Feb break)
    - 2022_Mar_Apr_Exploratory: 2022-03-01 to 2022-04-30
    """
    if dt.year == 2021 and dt.month == 12:
        return "2021_Dec"
    if dt.year == 2022 and dt.month == 1:
        return "2022_Jan"
    if dt.year == 2022 and dt.month == 2:
        return "2022_Feb_P1" if dt.day <= 15 else "2022_Feb_P2"
    return "2022_Mar_Apr_Exploratory"


def build_master_calendar(
    start_date: str = "2021-12-01",
    end_date: str = "2022-04-30",
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Task 3.1 & 3.2: Build master 151-day calendar in WIB (UTC+7) with all temporal flags.
    """
    if cfg is None:
        cfg = load_config()

    analysis_cfg = cfg["analysis"]
    primary_start = pd.Timestamp(analysis_cfg["primary_start"])
    primary_end = pd.Timestamp(analysis_cfg["primary_end"])
    nataru_start = pd.Timestamp(analysis_cfg["nataru_window"]["start"])
    nataru_end = pd.Timestamp(analysis_cfg["nataru_window"]["end"])
    anomalous_dates = {pd.Timestamp(d) for d in analysis_cfg.get("anomalous_dates", [])}
    sample_breaks = {pd.Timestamp(d) for d in analysis_cfg.get("sample_breaks", [])}

    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    cal = pd.DataFrame({"date_dt": dates})
    cal["date"] = cal["date_dt"].dt.strftime("%Y-%m-%d")
    cal["date_wib"] = cal["date_dt"].dt.tz_localize("Asia/Jakarta")
    cal["year"] = cal["date_dt"].dt.year
    cal["month"] = cal["date_dt"].dt.month
    cal["day_of_week"] = cal["date_dt"].dt.day_of_week  # 0=Mon .. 6=Sun
    cal["day_name"] = cal["date_dt"].dt.day_name()
    cal["is_weekend"] = cal["day_of_week"].isin([5, 6])

    cal["is_nataru_window"] = (cal["date_dt"] >= nataru_start) & (cal["date_dt"] <= nataru_end)
    cal["is_anomalous_date"] = cal["date_dt"].isin(anomalous_dates)
    cal["is_sample_break"] = cal["date_dt"].isin(sample_breaks)

    cal["sampling_period"] = cal["date_dt"].apply(assign_sampling_period)
    cal["is_primary_window"] = (cal["date_dt"] >= primary_start) & (cal["date_dt"] <= primary_end)

    # Ordinary weekday/weekend flags exclude both the Nataru event window and anomalous dates
    cal["is_ordinary_day"] = (~cal["is_nataru_window"]) & (~cal["is_anomalous_date"])
    cal["is_ordinary_weekday"] = (~cal["is_weekend"]) & cal["is_ordinary_day"]
    cal["is_ordinary_weekend"] = cal["is_weekend"] & cal["is_ordinary_day"]

    return cal


def compute_period_coverage_for_cells(
    all_cells: pd.Series,
    daily_obs: pd.DataFrame,
    calendar_df: pd.DataFrame,
    period_name: str,
    period_mask: pd.Series,
) -> pd.DataFrame:
    """
    Task 4.1 & 4.2: Compute per-cell weekday and weekend publication coverage
    (published days / expected days) for a given calendar slice, both for:
      1. All non-anomalous days in the slice (`all_weekday_*`, `all_weekend_*`)
      2. Ordinary non-event days excluding Nataru (`ord_weekday_*`, `ord_weekend_*`)
    And evaluate 80%, 90%, and 95% eligibility thresholds.
    """
    sub_cal = calendar_df.loc[period_mask & (~calendar_df["is_anomalous_date"])].copy()
    sub_dates = set(sub_cal["date"])

    # Expected day counts in this period
    exp_total = len(sub_cal)
    exp_all_wd = int((~sub_cal["is_weekend"]).sum())
    exp_all_we = int(sub_cal["is_weekend"].sum())
    exp_ord_wd = int(sub_cal["is_ordinary_weekday"].sum())
    exp_ord_we = int(sub_cal["is_ordinary_weekend"].sum())

    # Filter observed rows to this period's valid dates
    sub_obs = daily_obs.loc[daily_obs["date"].isin(sub_dates), ["cell_id", "date", "n_maids"]].merge(
        sub_cal[["date", "is_weekend", "is_ordinary_weekday", "is_ordinary_weekend"]],
        on="date",
        how="inner",
    )

    # Aggregate published day counts per cell
    grp = sub_obs.groupby("cell_id", as_index=False).agg(
        pub_total_days=("date", "count"),
        pub_all_wd_days=("is_weekend", lambda s: int((~s).sum())),
        pub_all_we_days=("is_weekend", lambda s: int(s.sum())),
        pub_ord_wd_days=("is_ordinary_weekday", "sum"),
        pub_ord_we_days=("is_ordinary_weekend", "sum"),
        mean_n_maids_published=("n_maids", "mean"),
        median_n_maids_published=("n_maids", "median"),
    )

    # Left-join onto the complete 5,715 cell universe so cells with 0 published days in the period are preserved
    base = pd.DataFrame({"cell_id": all_cells}).merge(grp, on="cell_id", how="left")
    count_cols = [
        "pub_total_days",
        "pub_all_wd_days",
        "pub_all_we_days",
        "pub_ord_wd_days",
        "pub_ord_we_days",
    ]
    for col in count_cols:
        base[col] = base[col].fillna(0).astype(int)

    base["period"] = period_name
    base["exp_total_days"] = exp_total
    base["exp_all_wd_days"] = exp_all_wd
    base["exp_all_we_days"] = exp_all_we
    base["exp_ord_wd_days"] = exp_ord_wd
    base["exp_ord_we_days"] = exp_ord_we

    # Compute coverage ratios
    base["total_coverage"] = base["pub_total_days"] / max(exp_total, 1)
    base["all_wd_coverage"] = base["pub_all_wd_days"] / max(exp_all_wd, 1)
    base["all_we_coverage"] = base["pub_all_we_days"] / max(exp_all_we, 1)
    base["ord_wd_coverage"] = base["pub_ord_wd_days"] / max(exp_ord_wd, 1)
    base["ord_we_coverage"] = base["pub_ord_we_days"] / max(exp_ord_we, 1)

    # Eligibility flags (requiring >= threshold separately on weekdays AND weekends)
    for pct, thresh in [(80, 0.80), (90, 0.90), (95, 0.95)]:
        base[f"pass_{pct}_ordinary"] = (
            (base["ord_wd_coverage"] >= thresh - 1e-9)
            & (base["ord_we_coverage"] >= thresh - 1e-9)
        )
        base[f"pass_{pct}_all_days"] = (
            (base["all_wd_coverage"] >= thresh - 1e-9)
            & (base["all_we_coverage"] >= thresh - 1e-9)
        )

    return base


def compute_hourly_kapanewon_cleaning(
    hourly_csv_path: Path = HOURLY_CSV_PATH,
    calendar_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """
    Task 5.1 (Batch 5): Standardize `presence_kapanewon_hourly.csv` timestamps to WIB (UTC+7),
    compute `pings_per_maid` (`n_pings / n_maids`), build hourly publication coverage audit
    across 78 kapanewon and sampling periods, and export Silver Parquet tables.
    """
    raw_hr = pd.read_csv(hourly_csv_path)
    if calendar_df is None:
        calendar_df = build_master_calendar(
            start_date=str(raw_hr["date"].min()),
            end_date=str(raw_hr["date"].max()),
        )

    # Rename/keep explicit hour_wib (0-23) and construct localized timestamp_wib (UTC+7)
    raw_hr["hour_wib"] = raw_hr["hour"].astype(int)
    base_dt = pd.to_datetime(raw_hr["date"], format="%Y-%m-%d") + pd.to_timedelta(
        raw_hr["hour_wib"], unit="h"
    )
    raw_hr["timestamp_wib"] = base_dt.dt.tz_localize("Asia/Jakarta")

    # Compute reporting-intensity diagnostic (pings_per_maid)
    raw_hr["pings_per_maid"] = raw_hr["n_pings"] / raw_hr["n_maids"]

    # Attach calendar attributes
    hr_clean = raw_hr.merge(
        calendar_df.drop(columns=["date_dt"]),
        on="date",
        how="left",
    )

    # Unique 78 kapanewon universe
    kapanewon_universe = (
        raw_hr[["kab_code", "kab_kota", "kapanewon_code", "kapanewon"]]
        .drop_duplicates()
        .sort_values("kapanewon_code")
        .reset_index(drop=True)
    )
    n_kapanewon = len(kapanewon_universe)

    period_definitions = [
        ("2021_Dec", calendar_df["sampling_period"] == "2021_Dec"),
        ("2022_Jan", calendar_df["sampling_period"] == "2022_Jan"),
        ("2022_Feb_P1", calendar_df["sampling_period"] == "2022_Feb_P1"),
        ("2022_Feb_P2", calendar_df["sampling_period"] == "2022_Feb_P2"),
        ("2022_Mar_Apr_Exploratory", calendar_df["sampling_period"] == "2022_Mar_Apr_Exploratory"),
        ("Primary_Dec2021_Feb2022", calendar_df["is_primary_window"]),
        ("Full_150d_Excl_Anomaly", ~calendar_df["is_anomalous_date"]),
    ]

    cov_frames = []
    for period_name, mask in period_definitions:
        sub_cal = calendar_df.loc[mask & (~calendar_df["is_anomalous_date"])]
        sub_dates = set(sub_cal["date"])

        exp_days = len(sub_cal)
        exp_hours_total = exp_days * 24
        exp_wd_hours = int((~sub_cal["is_weekend"]).sum()) * 24
        exp_we_hours = int(sub_cal["is_weekend"].sum()) * 24

        sub_hr = hr_clean.loc[hr_clean["date"].isin(sub_dates)]

        grp = sub_hr.groupby("kapanewon_code", as_index=False).agg(
            pub_hours_total=("hour_wib", "count"),
            pub_wd_hours=("is_weekend", lambda s: int((~s).sum())),
            pub_we_hours=("is_weekend", lambda s: int(s.sum())),
            distinct_hours_of_day_observed=("hour_wib", "nunique"),
            mean_n_maids=("n_maids", "mean"),
            median_n_maids=("n_maids", "median"),
            mean_n_pings=("n_pings", "mean"),
            mean_pings_per_maid=("pings_per_maid", "mean"),
            median_pings_per_maid=("pings_per_maid", "median"),
        )

        # Also check min coverage across the 24 diurnal hours (0..23) for each kapanewon
        diurnal_counts = (
            sub_hr.groupby(["kapanewon_code", "hour_wib"], as_index=False)
            .agg(pub_days_at_hour=("date", "count"))
        )
        full_diurnal_grid = kapanewon_universe[["kapanewon_code"]].merge(
            pd.DataFrame({"hour_wib": range(24)}), how="cross"
        ).merge(diurnal_counts, on=["kapanewon_code", "hour_wib"], how="left")
        full_diurnal_grid["pub_days_at_hour"] = full_diurnal_grid["pub_days_at_hour"].fillna(0)
        full_diurnal_grid["hour_coverage"] = full_diurnal_grid["pub_days_at_hour"] / max(exp_days, 1)

        diurnal_summary = full_diurnal_grid.groupby("kapanewon_code", as_index=False).agg(
            min_hour_of_day_coverage=("hour_coverage", "min"),
            hours_passing_80pct=("hour_coverage", lambda s: int((s >= 0.80 - 1e-9).sum())),
            hours_passing_90pct=("hour_coverage", lambda s: int((s >= 0.90 - 1e-9).sum())),
        )

        k_cov = (
            kapanewon_universe.merge(grp, on="kapanewon_code", how="left")
            .merge(diurnal_summary, on="kapanewon_code", how="left")
        )
        for col in ["pub_hours_total", "pub_wd_hours", "pub_we_hours", "distinct_hours_of_day_observed"]:
            k_cov[col] = k_cov[col].fillna(0).astype(int)

        k_cov["period"] = period_name
        k_cov["exp_days"] = exp_days
        k_cov["exp_hours_total"] = exp_hours_total
        k_cov["exp_wd_hours"] = exp_wd_hours
        k_cov["exp_we_hours"] = exp_we_hours

        k_cov["hourly_total_coverage"] = k_cov["pub_hours_total"] / max(exp_hours_total, 1)
        k_cov["hourly_wd_coverage"] = k_cov["pub_wd_hours"] / max(exp_wd_hours, 1)
        k_cov["hourly_we_coverage"] = k_cov["pub_we_hours"] / max(exp_we_hours, 1)

        for pct, thresh in [(80, 0.80), (90, 0.90), (95, 0.95)]:
            k_cov[f"pass_{pct}_hourly"] = (
                (k_cov["hourly_wd_coverage"] >= thresh - 1e-9)
                & (k_cov["hourly_we_coverage"] >= thresh - 1e-9)
            )

        cov_frames.append(k_cov)

    kapanewon_coverage_audit = pd.concat(cov_frames, ignore_index=True)

    # Attach primary window and within-period hourly eligibility flags to hr_clean
    primary_kap_flags = kapanewon_coverage_audit[
        kapanewon_coverage_audit["period"] == "Primary_Dec2021_Feb2022"
    ][
        [
            "kapanewon_code",
            "hourly_total_coverage",
            "pass_80_hourly",
            "pass_90_hourly",
            "pass_95_hourly",
        ]
    ].rename(
        columns={
            "hourly_total_coverage": "primary_hourly_coverage",
            "pass_80_hourly": "pass_80_hourly_primary_window",
            "pass_90_hourly": "pass_90_hourly_primary_window",
            "pass_95_hourly": "pass_95_hourly_primary_window",
        }
    )

    period_kap_flags = kapanewon_coverage_audit[
        kapanewon_coverage_audit["period"].isin(
            ["2021_Dec", "2022_Jan", "2022_Feb_P1", "2022_Feb_P2", "2022_Mar_Apr_Exploratory"]
        )
    ][
        [
            "kapanewon_code",
            "period",
            "hourly_total_coverage",
            "pass_80_hourly",
            "pass_90_hourly",
            "pass_95_hourly",
        ]
    ].rename(
        columns={
            "period": "sampling_period",
            "hourly_total_coverage": "period_hourly_coverage",
            "pass_80_hourly": "pass_80_hourly_in_period",
            "pass_90_hourly": "pass_90_hourly_in_period",
            "pass_95_hourly": "pass_95_hourly_in_period",
        }
    )

    hr_clean = hr_clean.merge(
        period_kap_flags, on=["kapanewon_code", "sampling_period"], how="left"
    ).merge(
        primary_kap_flags, on="kapanewon_code", how="left"
    )

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    hr_clean.to_parquet(KAPANEWON_HOURLY_CLEAN_PARQUET, index=False)
    kapanewon_coverage_audit.to_parquet(KAPANEWON_COVERAGE_AUDIT_PARQUET, index=False)

    # Summarize hourly coverage across periods
    hourly_period_summary: dict[str, Any] = {}
    for period_name, _ in period_definitions:
        sub = kapanewon_coverage_audit[kapanewon_coverage_audit["period"] == period_name]
        hourly_period_summary[period_name] = {
            "expected_hours_per_kapanewon": int(sub["exp_hours_total"].iloc[0]),
            "kapanewon_with_any_publication": int((sub["pub_hours_total"] > 0).sum()),
            "pass_80_hourly": int(sub["pass_80_hourly"].sum()),
            "pass_90_hourly": int(sub["pass_90_hourly"].sum()),
            "pass_95_hourly": int(sub["pass_95_hourly"].sum()),
            "mean_hourly_coverage_pct": round(float(sub["hourly_total_coverage"].mean() * 100), 2),
        }

    prim_top = (
        kapanewon_coverage_audit[kapanewon_coverage_audit["period"] == "Primary_Dec2021_Feb2022"]
        .sort_values("mean_n_maids", ascending=False)
        .head(10)[
            [
                "kapanewon_code",
                "kab_kota",
                "kapanewon",
                "hourly_total_coverage",
                "mean_n_maids",
                "mean_pings_per_maid",
                "pass_90_hourly",
            ]
        ]
        .to_dict(orient="records")
    )

    hourly_summary = {
        "total_kapanewon": n_kapanewon,
        "total_observed_hourly_rows": len(hr_clean),
        "total_expected_kapanewon_hours_151d": n_kapanewon * len(calendar_df) * 24,
        "overall_observed_fraction_151d": round(
            len(hr_clean) / (n_kapanewon * len(calendar_df) * 24), 4
        ),
        "pings_per_maid_min": round(float(hr_clean["pings_per_maid"].min()), 4),
        "pings_per_maid_median": round(float(hr_clean["pings_per_maid"].median()), 4),
        "pings_per_maid_mean": round(float(hr_clean["pings_per_maid"].mean()), 4),
        "pings_per_maid_max": round(float(hr_clean["pings_per_maid"].max()), 4),
        "period_eligibility_summary": hourly_period_summary,
        "top_10_busiest_kapanewon_primary_window": prim_top,
    }

    return hr_clean, kapanewon_coverage_audit, hourly_summary


def run_daily_temporal_cleaning(
    daily_csv_path: Path = DAILY_CSV_PATH,
    hourly_csv_path: Path = HOURLY_CSV_PATH,
) -> dict[str, Any]:
    """
    Execute Batch 3, Batch 4, and Batch 5:
    - Build master calendar & clean daily mobility table.
    - Compute daily coverage summary across the 5,715-cell universe.
    - Compute per-cell, per-period weekday/weekend coverage audit and 80/90/95% eligibility flags.
    - Clean hourly kapanewon table in WIB (UTC+7), compute `pings_per_maid` and hourly coverage audit.
    - Export all Silver Parquet tables and JSON audit summary.
    """
    cfg = load_config()
    raw_df = pd.read_csv(daily_csv_path)

    if UNIQUE_CELLS_PARQUET.exists():
        cells_df = pd.read_parquet(UNIQUE_CELLS_PARQUET)
    else:
        cells_df = (
            raw_df[["cell_id", "x_min_utm", "y_min_utm", "centroid_lon", "centroid_lat"]]
            .drop_duplicates()
            .sort_values("cell_id")
            .reset_index(drop=True)
        )

    all_cells = cells_df["cell_id"].sort_values().reset_index(drop=True)
    n_total_cells = len(all_cells)

    # 1. Build Master Calendar (Batch 3)
    calendar_df = build_master_calendar(
        start_date=str(raw_df["date"].min()),
        end_date=str(raw_df["date"].max()),
        cfg=cfg,
    )

    # 2. Compute per-cell coverage audit across each sampling period + aggregate windows (Batch 4)
    period_definitions = [
        ("2021_Dec", calendar_df["sampling_period"] == "2021_Dec"),
        ("2022_Jan", calendar_df["sampling_period"] == "2022_Jan"),
        ("2022_Feb_P1", calendar_df["sampling_period"] == "2022_Feb_P1"),
        ("2022_Feb_P2", calendar_df["sampling_period"] == "2022_Feb_P2"),
        ("2022_Mar_Apr_Exploratory", calendar_df["sampling_period"] == "2022_Mar_Apr_Exploratory"),
        ("Primary_Dec2021_Feb2022", calendar_df["is_primary_window"]),
        ("Full_150d_Excl_Anomaly", ~calendar_df["is_anomalous_date"]),
    ]

    coverage_tables = []
    for period_name, mask in period_definitions:
        cov_df = compute_period_coverage_for_cells(
            all_cells=all_cells,
            daily_obs=raw_df,
            calendar_df=calendar_df,
            period_name=period_name,
            period_mask=mask,
        )
        coverage_tables.append(cov_df)

    cell_coverage_audit = pd.concat(coverage_tables, ignore_index=True)

    # Also compute strict "All 4 Primary Periods" common-support flags per cell
    primary_subperiods = ["2021_Dec", "2022_Jan", "2022_Feb_P1", "2022_Feb_P2"]
    sub_cov = cell_coverage_audit[cell_coverage_audit["period"].isin(primary_subperiods)]
    strict_every_period = (
        sub_cov.groupby("cell_id", as_index=False)
        .agg(
            pass_80_every_primary_period=("pass_80_ordinary", "all"),
            pass_90_every_primary_period=("pass_90_ordinary", "all"),
            pass_95_every_primary_period=("pass_95_ordinary", "all"),
            pass_80_all_days_every_primary_period=("pass_80_all_days", "all"),
            pass_90_all_days_every_primary_period=("pass_90_all_days", "all"),
            pass_95_all_days_every_primary_period=("pass_95_all_days", "all"),
        )
    )

    primary_window_cov = (
        cell_coverage_audit[cell_coverage_audit["period"] == "Primary_Dec2021_Feb2022"][
            [
                "cell_id",
                "total_coverage",
                "ord_wd_coverage",
                "ord_we_coverage",
                "pass_80_ordinary",
                "pass_90_ordinary",
                "pass_95_ordinary",
                "pass_80_all_days",
                "pass_90_all_days",
                "pass_95_all_days",
            ]
        ]
        .rename(
            columns={
                "total_coverage": "primary_total_coverage",
                "ord_wd_coverage": "primary_ord_wd_coverage",
                "ord_we_coverage": "primary_ord_we_coverage",
                "pass_80_ordinary": "pass_80_primary_window",
                "pass_90_ordinary": "pass_90_primary_window",
                "pass_95_ordinary": "pass_95_primary_window",
                "pass_80_all_days": "pass_80_all_days_primary_window",
                "pass_90_all_days": "pass_90_all_days_primary_window",
                "pass_95_all_days": "pass_95_all_days_primary_window",
            }
        )
        .merge(strict_every_period, on="cell_id", how="left")
    )

    cell_coverage_audit = cell_coverage_audit.merge(
        strict_every_period, on="cell_id", how="left"
    )

    # 3. Enrich daily mobility table with calendar attributes, within-period coverage flags, and daily denominators
    mobility_clean = raw_df.merge(
        calendar_df.drop(columns=["date_dt"]),
        on="date",
        how="left",
    )

    period_flags_lookup = cell_coverage_audit[
        cell_coverage_audit["period"].isin(
            ["2021_Dec", "2022_Jan", "2022_Feb_P1", "2022_Feb_P2", "2022_Mar_Apr_Exploratory"]
        )
    ][
        [
            "cell_id",
            "period",
            "ord_wd_coverage",
            "ord_we_coverage",
            "pass_80_ordinary",
            "pass_90_ordinary",
            "pass_95_ordinary",
            "pass_80_all_days",
            "pass_90_all_days",
            "pass_95_all_days",
        ]
    ].rename(
        columns={
            "period": "sampling_period",
            "ord_wd_coverage": "period_ord_wd_coverage",
            "ord_we_coverage": "period_ord_we_coverage",
            "pass_80_ordinary": "pass_80_in_period",
            "pass_90_ordinary": "pass_90_in_period",
            "pass_95_ordinary": "pass_95_in_period",
            "pass_80_all_days": "pass_80_all_days_in_period",
            "pass_90_all_days": "pass_90_all_days_in_period",
            "pass_95_all_days": "pass_95_all_days_in_period",
        }
    )

    mobility_clean = mobility_clean.merge(
        period_flags_lookup,
        on=["cell_id", "sampling_period"],
        how="left",
    ).merge(
        primary_window_cov,
        on="cell_id",
        how="left",
    )

    # Precompute daily total published device-cell presences (full universe & common-support 90% cells)
    daily_totals = (
        mobility_clean.groupby("date", as_index=False)
        .agg(
            daily_published_cells=("cell_id", "count"),
            daily_total_maids_all_cells=("n_maids", "sum"),
        )
    )
    common90_totals = (
        mobility_clean[mobility_clean["pass_90_primary_window"]]
        .groupby("date", as_index=False)
        .agg(
            daily_published_cells_common90=("cell_id", "count"),
            daily_total_maids_common90=("n_maids", "sum"),
        )
    )
    strict90_totals = (
        mobility_clean[mobility_clean["pass_90_every_primary_period"]]
        .groupby("date", as_index=False)
        .agg(
            daily_published_cells_strict90=("cell_id", "count"),
            daily_total_maids_strict90=("n_maids", "sum"),
        )
    )

    daily_summary = (
        calendar_df.drop(columns=["date_dt"])
        .merge(daily_totals, on="date", how="left")
        .merge(common90_totals, on="date", how="left")
        .merge(strict90_totals, on="date", how="left")
    )
    daily_summary["expected_cells_universe"] = n_total_cells
    daily_summary["daily_cell_coverage_pct"] = (
        daily_summary["daily_published_cells"] / n_total_cells * 100.0
    )

    # Attach daily denominators to mobility_clean so Published Presence Share (%) is ready
    mobility_clean = mobility_clean.merge(
        daily_summary[
            [
                "date",
                "daily_published_cells",
                "daily_total_maids_all_cells",
                "daily_total_maids_common90",
                "daily_total_maids_strict90",
            ]
        ],
        on="date",
        how="left",
    )
    mobility_clean["published_presence_share_pct"] = (
        mobility_clean["n_maids"] / mobility_clean["daily_total_maids_all_cells"] * 100.0
    )
    mobility_clean["published_presence_share_common90_pct"] = np.where(
        mobility_clean["pass_90_primary_window"] & (mobility_clean["daily_total_maids_common90"] > 0),
        mobility_clean["n_maids"] / mobility_clean["daily_total_maids_common90"] * 100.0,
        np.nan,
    )

    # 4. Save Daily Silver Parquet outputs
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    mobility_clean.to_parquet(MOBILITY_DAILY_CLEAN_PARQUET, index=False)
    cell_coverage_audit.to_parquet(CELL_COVERAGE_AUDIT_PARQUET, index=False)
    daily_summary.to_parquet(DAILY_COVERAGE_SUMMARY_PARQUET, index=False)

    # 5. Execute Batch 5: Hourly Kapanewon Cleaning & Coverage Audit
    _, _, hourly_summary = compute_hourly_kapanewon_cleaning(
        hourly_csv_path=hourly_csv_path,
        calendar_df=calendar_df,
    )

    # 6. Build human-readable audit summary JSON
    period_eligibility_summary: dict[str, Any] = {}
    for period_name, _ in period_definitions:
        p_df = cell_coverage_audit[cell_coverage_audit["period"] == period_name]
        period_eligibility_summary[period_name] = {
            "expected_total_days": int(p_df["exp_total_days"].iloc[0]),
            "expected_ordinary_weekdays": int(p_df["exp_ord_wd_days"].iloc[0]),
            "expected_ordinary_weekends": int(p_df["exp_ord_we_days"].iloc[0]),
            "cells_with_any_publication": int((p_df["pub_total_days"] > 0).sum()),
            "ordinary_weekday_weekend_rule": {
                "pass_80": int(p_df["pass_80_ordinary"].sum()),
                "pass_90": int(p_df["pass_90_ordinary"].sum()),
                "pass_95": int(p_df["pass_95_ordinary"].sum()),
                "pass_90_pct_of_universe": round(float(p_df["pass_90_ordinary"].mean() * 100), 2),
            },
            "all_days_weekday_weekend_rule": {
                "pass_80": int(p_df["pass_80_all_days"].sum()),
                "pass_90": int(p_df["pass_90_all_days"].sum()),
                "pass_95": int(p_df["pass_95_all_days"].sum()),
            },
        }

    key_dates_diag = {}
    for d_str in ["2021-12-31", "2022-01-01", "2022-02-15", "2022-02-16", "2022-03-07", "2022-03-08", "2022-03-09"]:
        row = daily_summary[daily_summary["date"] == d_str]
        if not row.empty:
            r = row.iloc[0]
            key_dates_diag[d_str] = {
                "sampling_period": str(r["sampling_period"]),
                "published_cells": int(r["daily_published_cells"]),
                "cell_coverage_pct": round(float(r["daily_cell_coverage_pct"]), 2),
                "total_n_maids": int(r["daily_total_maids_all_cells"]),
                "is_sample_break": bool(r["is_sample_break"]),
                "is_anomalous_date": bool(r["is_anomalous_date"]),
            }

    summary_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_cells_universe": n_total_cells,
        "total_calendar_days": len(calendar_df),
        "primary_window_days": int(calendar_df["is_primary_window"].sum()),
        "nataru_window_days": int(calendar_df["is_nataru_window"].sum()),
        "strict_every_primary_subperiod_counts": {
            "ordinary_rule": {
                "pass_80_every_primary_period": int(strict_every_period["pass_80_every_primary_period"].sum()),
                "pass_90_every_primary_period": int(strict_every_period["pass_90_every_primary_period"].sum()),
                "pass_95_every_primary_period": int(strict_every_period["pass_95_every_primary_period"].sum()),
            },
            "all_days_rule": {
                "pass_80_every_primary_period": int(strict_every_period["pass_80_all_days_every_primary_period"].sum()),
                "pass_90_every_primary_period": int(strict_every_period["pass_90_all_days_every_primary_period"].sum()),
                "pass_95_every_primary_period": int(strict_every_period["pass_95_all_days_every_primary_period"].sum()),
            },
        },
        "period_eligibility_summary": period_eligibility_summary,
        "key_dates_diagnostics": key_dates_diag,
        "hourly_kapanewon_summary": hourly_summary,
        "silver_outputs": {
            "mobility_daily_clean": str(MOBILITY_DAILY_CLEAN_PARQUET.relative_to(PROJECT_ROOT)),
            "cell_coverage_audit": str(CELL_COVERAGE_AUDIT_PARQUET.relative_to(PROJECT_ROOT)),
            "daily_coverage_summary": str(DAILY_COVERAGE_SUMMARY_PARQUET.relative_to(PROJECT_ROOT)),
            "kapanewon_hourly_clean": str(KAPANEWON_HOURLY_CLEAN_PARQUET.relative_to(PROJECT_ROOT)),
            "kapanewon_coverage_audit": str(KAPANEWON_COVERAGE_AUDIT_PARQUET.relative_to(PROJECT_ROOT)),
        },
    }

    with open(TEMPORAL_SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    return summary_payload


if __name__ == "__main__":
    report = run_daily_temporal_cleaning()
    print("=== Temporal Cleaning & Coverage Audit Complete (Batches 3, 4 & 5) ===")
    print(json.dumps(report["hourly_kapanewon_summary"], indent=2))
