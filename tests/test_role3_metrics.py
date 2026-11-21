"""
Role 3 data-contract tests for the Gold layer.
----------------------------------------------
Written in the same spirit as `tests/test_role1_pipeline.py`: these do not
check that the numbers are *right* — no test can do that — they check that the
rules the analysis depends on were actually enforced, so a future change
cannot quietly break one.

    python -m src.metrics            # produce data/gold/ first
    pytest -q tests/test_role3_metrics.py

The rules under test:

  * every ratio lives inside one sampling period, never across a break
  * a withheld estimate carries no value, only its counts
  * the 1 January sample break is withheld in the event window, always
  * no table sums `n_maids`
  * sites never outnumber the cells they group
  * each kapanewon has exactly one peak hour per period and day type
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLD_DIR = PROJECT_ROOT / "data" / "gold"
SUMMARY_JSON = GOLD_DIR / "gold_metrics_summary.json"

KNOWN_PERIODS = {
    "2021_Dec", "2022_Jan", "2022_Feb_P1", "2022_Feb_P2",
    "2022_Mar_Apr_Exploratory",
}
PRIMARY_PERIODS = {"2021_Dec", "2022_Jan", "2022_Feb_P1", "2022_Feb_P2"}

EXPECTED_TABLES = [
    "facility_pull",
    "cell_metrics",
    "category_summary",
    "coverage_sensitivity",
    "mixed_use_sensitivity",
    "matched_comparison",
    "event_window",
    "kapanewon_hourly_profile",
]


def load(name: str) -> pd.DataFrame:
    path = GOLD_DIR / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{path.relative_to(PROJECT_ROOT)} is missing — "
                    "run `python -m src.metrics` first.")
    return pd.read_parquet(path)


def test_every_gold_table_exists_and_is_non_empty():
    for name in EXPECTED_TABLES:
        frame = load(name)
        assert not frame.empty, f"{name}.parquet is empty"


def test_summary_json_records_the_guardrails():
    if not SUMMARY_JSON.exists():
        pytest.skip("gold_metrics_summary.json is missing — run src.metrics.")
    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))

    assert summary["bootstrap"]["cluster_unit"].startswith("cluster_id"), (
        "Intervals must come from a bootstrap over site clusters, not rows."
    )
    assert summary["bootstrap"]["samples"] == 1000
    assert summary["bootstrap"]["multi_cell_clusters"] >= 1, (
        "Role 2 reports multi-cell sites (UGM spans 15 cells), so at least "
        "one cluster must group more than one cell — otherwise the clustering "
        "is doing nothing and the intervals are too narrow."
    )
    assert summary["event_window"]["single_holiday_uplift_value_produced"] is False, (
        "A single holiday-uplift value cannot be produced: the Nataru window "
        "crosses the 1 January sample break."
    )
    assert summary["coverage_threshold_primary_pct"] == 90
    assert set(summary["coverage_thresholds_sensitivity_pct"]) == {80, 90, 95}
    assert len(summary["interpretation_guardrails"]) >= 5


def test_no_metric_crosses_a_sampling_period():
    """Every row is labelled with exactly one known period."""
    for name in ("cell_metrics", "category_summary", "facility_pull",
                 "matched_comparison", "event_window"):
        frame = load(name)
        unknown = set(frame["sampling_period"].unique()) - KNOWN_PERIODS
        assert not unknown, f"{name} carries unknown periods: {unknown}"

    # A cell-period row must not be duplicated, or a ratio would be averaged
    # across two periods somewhere downstream.
    cells = load("cell_metrics")
    duplicated = cells.duplicated(subset=["cell_id", "sampling_period"]).sum()
    assert duplicated == 0, f"{duplicated} duplicated cell-period rows"


def test_ratio_uses_only_ordinary_days_within_the_period():
    """Observed day counts can never exceed the period's ordinary days.

    Nataru dates and 2022-03-08 are excluded by Role 1's `is_ordinary_*`
    flags. The longest primary period is December at 31 days, so a cell
    claiming more weekday or weekend days than that would mean the filter
    leaked.
    """
    cells = load("cell_metrics")
    primary = cells[cells["sampling_period"].isin(PRIMARY_PERIODS)]
    assert primary["days_weekday"].max() <= 31
    assert primary["days_weekend"].max() <= 31
    # February P2 runs 16-28, so at most 13 days of either kind.
    feb_p2 = cells[cells["sampling_period"] == "2022_Feb_P2"]
    if not feb_p2.empty:
        assert feb_p2["days_weekday"].max() <= 13
        assert feb_p2["days_weekend"].max() <= 13


def test_withheld_estimates_carry_no_value():
    """A row that was withheld must be NaN, not zero and not a stale number."""
    summary = load("category_summary")
    withheld = summary[summary["evidence"] != "reported"]
    for column in ("median_ratio", "ci_low", "ci_high"):
        assert withheld[column].isna().all(), (
            f"category_summary.{column} has a value on a withheld row"
        )
    # And the counts behind the decision are kept, so the reader can see why.
    assert withheld["cells"].notna().all()

    matched = load("matched_comparison")
    thin = matched[matched["evidence"] != "observational"]
    for column in ("median_difference", "ci_low", "ci_high",
                   "smd_coverage_after", "smd_activity_after"):
        assert thin[column].isna().all(), (
            f"matched_comparison.{column} has a value on a withheld row"
        )
    assert thin["matched_pairs"].notna().all()


def test_january_first_is_always_withheld_in_the_event_window():
    """The sample break can never carry a relative-presence value."""
    event = load("event_window")
    breaks = event[event["is_sample_break"].astype(bool)]
    assert not breaks.empty, (
        "The Nataru window includes 2022-01-01, so the break must appear."
    )
    assert (breaks["evidence"] == "withheld: 1 January sampling break").all()
    assert breaks["median_relative_presence"].isna().all(), (
        "1 January carries a value; a holiday effect cannot be separated from "
        "the change in sample composition on that date."
    )


def test_event_window_is_labelled_exploratory_only():
    event = load("event_window")
    allowed = {"exploratory"}
    reported = set(event.loc[event["median_relative_presence"].notna(),
                             "evidence"].unique())
    assert reported <= allowed, (
        f"event_window reports values under {reported - allowed}; the whole "
        "analysis is exploratory."
    )


def test_no_table_sums_n_maids():
    """`n_maids` is a distinct count; a sum of distinct counts means nothing."""
    for name in EXPECTED_TABLES:
        frame = load(name)
        offenders = [
            column for column in frame.columns
            if "n_maids" in column and ("sum" in column or "total" in column)
        ]
        assert not offenders, f"{name} appears to sum n_maids: {offenders}"


def test_clusters_never_outnumber_cells():
    """A cluster groups one or more cells, so it is never the larger count."""
    summary = load("category_summary")
    assert (summary["clusters"] <= summary["cells"]).all()
    assert (summary["clusters_with_ratio"] <= summary["clusters"]).all()

    pull = load("facility_pull")
    assert (pull["clusters"] <= pull["cells"]).all()
    assert (pull["clusters_with_value"] <= pull["clusters"]).all()


def test_multi_cell_sites_are_actually_clustered():
    """Cells of one complex must share a cluster id.

    Role 2 reports UGM across 15 cells. If every cell were its own cluster the
    bootstrap would treat one place as fifteen independent observations, and
    the intervals would come out too narrow.
    """
    cells = load("cell_metrics")
    sizes = cells.groupby("cluster_id")["cell_id"].nunique()
    assert (sizes > 1).any(), (
        "No cluster groups more than one cell; site clustering is not working."
    )


def test_category_membership_uses_role2_flags():
    """Grouping must use has_<category>, not the display-only label."""
    cells = load("cell_metrics")
    has_columns = [column for column in cells.columns
                   if column.startswith("has_")]
    assert len(has_columns) >= 6, (
        f"Expected Role 2's six has_<category> flags, found {has_columns}"
    )
    summary = load("category_summary")
    categories = set(summary["category"].unique()) - {"baseline_candidate"}
    flags = {column[len("has_"):] for column in has_columns}
    assert categories <= flags, (
        f"category_summary reports categories with no has_ flag: "
        f"{categories - flags}"
    )


def test_matched_pairs_are_bounded_by_the_treated_cells():
    matched = load("matched_comparison")
    assert (matched["matched_pairs"] <= matched["treated_cells"]).all()
    assert (matched["outside_common_support"] <= matched["treated_cells"]).all()
    assert (matched["matched_pairs"] >= 0).all()


def test_confidence_intervals_bracket_their_estimate():
    for name, estimate in (("category_summary", "median_ratio"),
                           ("facility_pull", "median_share_weekday_pct"),
                           ("matched_comparison", "median_difference")):
        frame = load(name)
        usable = frame[frame[["ci_low", "ci_high", estimate]].notna().all(axis=1)]
        if usable.empty:
            continue
        assert (usable["ci_low"] <= usable["ci_high"]).all(), (
            f"{name} has an inverted interval"
        )
        # A percentile interval around a median of the same sample should
        # contain it; a violation means the bootstrap resampled the wrong set.
        inside = (
            (usable[estimate] >= usable["ci_low"] - 1e-9)
            & (usable[estimate] <= usable["ci_high"] + 1e-9)
        )
        assert inside.all(), (
            f"{name}: {int((~inside).sum())} estimates fall outside their own "
            "interval"
        )


def test_shares_are_percentages():
    pull = load("facility_pull")
    values = pull["median_share_weekday_pct"].dropna()
    assert (values > 0).all() and (values <= 100).all()

    cells = load("cell_metrics")
    for column in ("restricted_share_weekday", "restricted_share_weekend",
                   "published_share_weekday", "published_share_weekend"):
        series = cells[column].dropna()
        assert (series >= 0).all() and (series <= 100).all(), (
            f"cell_metrics.{column} is not a percentage"
        )


def test_each_kapanewon_has_exactly_one_peak_hour():
    profile = load("kapanewon_hourly_profile")
    assert profile["hour_wib"].between(0, 23).all()
    peaks = (
        profile.groupby(["sampling_period", "kapanewon_code", "day_type"])
        ["is_peak_hour"].sum()
    )
    assert (peaks == 1).all(), (
        "Every kapanewon needs exactly one peak hour per period and day type"
    )


def test_pings_per_maid_is_at_least_one():
    """It is a ratio of pings to devices, so it cannot fall below one."""
    profile = load("kapanewon_hourly_profile")
    values = profile["median_pings_per_maid"].dropna()
    assert (values >= 1.0).all()


def test_coverage_sensitivity_covers_all_three_thresholds():
    sensitivity = load("coverage_sensitivity")
    assert set(sensitivity["coverage_threshold"].unique()) == {80, 90, 95}


def test_mixed_use_sensitivity_has_both_subsets():
    mixed = load("mixed_use_sensitivity")
    assert set(mixed["subset"].unique()) == {"all cells", "single-category only"}


def test_control_cells_are_not_called_residential():
    """The no-facility label must stay agnostic about what is actually there.

    A cell with no mapped facility may hold housing, farmland, roads, water,
    or an amenity nobody has mapped. Calling it "residential" would assert
    something the data does not support.
    """
    cells = load("cell_metrics")
    classes = {str(label).lower() for label in cells["cell_class"].unique()}
    assert "residential" not in classes
    assert "no_selected_facility" in classes, (
        "Role 2's comparison class must be present and explicitly labelled"
    )

    summary = load("category_summary")
    labels = {str(label).lower() for label in summary["category"].unique()}
    assert "residential" not in labels
    assert "baseline_candidate" in labels, (
        "The matched comparison group must appear as its own row"
    )


def test_matched_comparison_reports_its_imbalance():
    """Balance diagnostics must be present, whatever they say."""
    matched = load("matched_comparison")
    reported = matched[matched["evidence"] == "observational"]
    if reported.empty:
        pytest.skip("every comparison was withheld in this run")
    for column in ("smd_coverage_before", "smd_coverage_after",
                   "smd_activity_before", "smd_activity_after"):
        assert reported[column].notna().all(), (
            f"{column} is missing on a reported comparison; residual "
            "imbalance has to be reported, not assumed away"
        )
