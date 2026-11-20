"""
Unit & Integration Tests for Role 1 (Data Ingestion & Temporal Cleaning)
------------------------------------------------------------------------
Verifies Bronze & Silver layer contracts for Role 2 (Nalen) and Role 3 (Rafi).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"


def test_bronze_verification_and_osm_outputs_exist() -> None:
    """Verify Bronze layer files and audit JSONs exist and are populated."""
    assert (RAW_DIR / "presence_cell500m_daily.csv").exists()
    assert (RAW_DIR / "presence_kapanewon_hourly.csv").exists()
    assert (RAW_DIR / "jogjapulse_verification_summary.json").exists()
    assert (RAW_DIR / "osm_facilities_current.json").exists()
    assert (RAW_DIR / "osm_ingestion_metadata.json").exists()
    assert (RAW_DIR / "osm_landmark_audit.json").exists()

    with open(RAW_DIR / "osm_landmark_audit.json", "r", encoding="utf-8") as f:
        audit = json.load(f)

    landmarks = audit["landmark_comparison_summary"]
    expected_landmarks = {
        "UGM",
        "UNY",
        "Ambarrukmo_Plaza",
        "Pakuwon_Hartono_Mall",
        "RSUP_Dr_Sardjito",
        "Malioboro",
    }
    assert set(landmarks.keys()) == expected_landmarks
    for lm_name, lm_info in landmarks.items():
        assert lm_info["current_captured"] is True, f"Landmark {lm_name} not captured!"
        assert lm_info["current_category_elements"] > 0, f"Landmark {lm_name} has 0 category elements!"


def test_silver_unique_grid_cells_for_role2() -> None:
    """Verify `grid_cells_unique.parquet` contract for Role 2 (Nalen)."""
    cells_path = SILVER_DIR / "grid_cells_unique.parquet"
    assert cells_path.exists()
    df = pd.read_parquet(cells_path)

    assert len(df) == 5715
    assert df["cell_id"].nunique() == 5715
    required_cols = {
        "cell_id",
        "x_min_utm",
        "y_min_utm",
        "x_max_utm",
        "y_max_utm",
        "centroid_lon",
        "centroid_lat",
    }
    assert required_cols.issubset(df.columns)
    assert ((df["x_max_utm"] - df["x_min_utm"]) == 500).all()
    assert ((df["y_max_utm"] - df["y_min_utm"]) == 500).all()


def test_silver_daily_mobility_clean_for_role3() -> None:
    """Verify `mobility_daily_clean.parquet` contract for Role 3 (Rafi)."""
    path = SILVER_DIR / "mobility_daily_clean.parquet"
    assert path.exists()
    df = pd.read_parquet(path)

    assert len(df) == 183548
    assert (df["n_maids"] >= 5).all(), "k=5 privacy threshold violated"

    required_cols = {
        "cell_id",
        "date",
        "date_wib",
        "n_maids",
        "day_of_week",
        "is_weekend",
        "is_nataru_window",
        "is_anomalous_date",
        "is_sample_break",
        "sampling_period",
        "is_primary_window",
        "is_ordinary_weekday",
        "is_ordinary_weekend",
        "pass_80_in_period",
        "pass_90_in_period",
        "pass_95_in_period",
        "pass_80_primary_window",
        "pass_90_primary_window",
        "pass_95_primary_window",
        "pass_90_every_primary_period",
        "published_presence_share_pct",
        "published_presence_share_common90_pct",
    }
    assert required_cols.issubset(df.columns)

    # Daily published presence shares across all published cells on each date must sum to 100%
    daily_share_sums = df.groupby("date")["published_presence_share_pct"].sum()
    assert np.allclose(daily_share_sums.values, 100.0, atol=1e-5)

    # Check anomalous date flag (2022-03-08) and sample breaks (2022-01-01, 2022-02-16)
    anom_dates = set(df.loc[df["is_anomalous_date"], "date"].unique())
    assert anom_dates == {"2022-03-08"}

    break_dates = set(df.loc[df["is_sample_break"], "date"].unique())
    assert break_dates == {"2022-01-01", "2022-02-16"}


def test_silver_cell_coverage_audit() -> None:
    """Verify `cell_coverage_audit.parquet` completeness and threshold nesting (95 <= 90 <= 80)."""
    path = SILVER_DIR / "cell_coverage_audit.parquet"
    assert path.exists()
    cov = pd.read_parquet(path)

    expected_periods = {
        "2021_Dec",
        "2022_Jan",
        "2022_Feb_P1",
        "2022_Feb_P2",
        "2022_Mar_Apr_Exploratory",
        "Primary_Dec2021_Feb2022",
        "Full_150d_Excl_Anomaly",
    }
    assert set(cov["period"].unique()) == expected_periods
    assert len(cov) == 5715 * len(expected_periods)

    # Monotonicity of coverage thresholds: pass_95 => pass_90 => pass_80
    assert (cov["pass_95_ordinary"] <= cov["pass_90_ordinary"]).all()
    assert (cov["pass_90_ordinary"] <= cov["pass_80_ordinary"]).all()
    assert (cov["pass_95_all_days"] <= cov["pass_90_all_days"]).all()
    assert (cov["pass_90_all_days"] <= cov["pass_80_all_days"]).all()


def test_silver_hourly_kapanewon_clean_and_audit() -> None:
    """Verify `kapanewon_hourly_clean.parquet` and `kapanewon_coverage_audit.parquet`."""
    hr_path = SILVER_DIR / "kapanewon_hourly_clean.parquet"
    audit_path = SILVER_DIR / "kapanewon_coverage_audit.parquet"
    assert hr_path.exists()
    assert audit_path.exists()

    hr = pd.read_parquet(hr_path)
    assert len(hr) == 230418
    assert hr["kapanewon_code"].nunique() == 78
    assert (hr["n_maids"] >= 5).all()
    assert (hr["hour_wib"].between(0, 23)).all()
    assert (hr["pings_per_maid"] >= 1.0).all()
    assert str(hr["timestamp_wib"].dt.tz) == "Asia/Jakarta"

    audit = pd.read_parquet(audit_path)
    assert audit["kapanewon_code"].nunique() == 78
    assert (audit["pass_95_hourly"] <= audit["pass_90_hourly"]).all()
    assert (audit["pass_90_hourly"] <= audit["pass_80_hourly"]).all()

