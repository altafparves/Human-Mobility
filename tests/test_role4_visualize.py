"""Contract and guardrail tests for Role 4 visualizations (src/visualize.py)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.visualize import (
    BREAK,
    COLORS,
    DEFAULT_MAP_PERIOD,
    LABELS,
    PERIOD_NAMES,
    PRIMARY_PERIODS,
    ROOT,
    build,
    diurnal,
    gold,
    holiday,
    pull,
    read,
    rhythm,
    spatial_map,
)

EXPECTED_PRODUCTS = (
    "city_magnets_map.html",
    "weekday_weekend_ratio.png",
    "nataru_timeseries.png",
    "kapanewon_diurnal_heatmap.png",
    "facility_pull.png",
)

AUDIT_LANDMARKS = (
    "Universitas Gadjah Mada",
    "Universitas Negeri Yogyakarta",
    "RSUP Dr. Sardjito",
    "Pakuwon Mall Yogyakarta",
    "Plaza Ambarrukmo",
    "Malioboro Mall",
    "Prambanan Temple Compounds",
    "Stasiun Wates",
    "RSUD Wonosari",
)


def test_build_generates_all_five_outputs(tmp_path: Path) -> None:
    """build() must render the HTML map and all four PNG figures atomically."""
    outputs = build(period="2021_Dec", output=tmp_path, map_period=DEFAULT_MAP_PERIOD)
    names = [p.name for p in outputs]
    assert tuple(names) == EXPECTED_PRODUCTS
    for p in outputs:
        assert p.exists(), f"Missing output {p}"
        assert p.stat().st_size > 10_000, f"Output {p.name} is unexpectedly small"
        if p.suffix == ".png":
            assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        elif p.suffix == ".html":
            text = p.read_text(encoding="utf-8")
            assert "<!DOCTYPE html>" in text or "<html" in text


def test_committed_figures_exist_and_non_empty() -> None:
    """All five committed deliverables in figures/ must exist and be non-empty."""
    figures_dir = ROOT / "figures"
    for filename in EXPECTED_PRODUCTS:
        path = figures_dir / filename
        assert path.exists(), f"Missing committed figure {path}"
        assert path.stat().st_size > 10_000, f"Committed figure {filename} is too small"


def test_map_embeds_offline_leaflet_and_boundaries() -> None:
    """The exported map HTML must work offline with embedded Leaflet and district boundaries."""
    html_text = (ROOT / "figures" / "city_magnets_map.html").read_text(encoding="utf-8")
    assert "Leaflet" in html_text
    assert ".leaflet-container { background: #f4f2eb; }" in html_text
    assert "City and regency boundaries" in html_text
    assert "Major roads" in html_text
    assert "Street basemap (online)" in html_text
    assert 'id="map-metric"' in html_text
    assert 'id="cell-panel"' in html_text
    assert 'id="period-summary"' in html_text


def test_map_includes_all_primary_periods_and_audit_landmarks() -> None:
    """The interactive map must include layers for all primary periods and all 9 landmarks."""
    html_text = (ROOT / "figures" / "city_magnets_map.html").read_text(encoding="utf-8")
    for period in PRIMARY_PERIODS:
        title = PERIOD_NAMES[period]
        # Check either raw or unicode-escaped title in HTML/JS
        escaped = json.dumps(f"Ratio · {title}")[1:-1]
        assert (f"Ratio · {title}" in html_text) or (escaped in html_text), (
            f"Missing period layer for {period} ({title})"
        )
    assert "Facility categories" in html_text
    assert "Mapped sites" in html_text
    for landmark in AUDIT_LANDMARKS:
        assert landmark in html_text, f"Missing landmark label: {landmark}"


def test_guardrail_no_pooling_across_sampling_periods() -> None:
    """Role 3 guardrail #3: category_summary and facility_pull must stay separated by period."""
    cat_df = gold(
        "category_summary",
        "sampling_period category median_ratio ci_low ci_high cells_with_ratio clusters evidence",
    )
    pull_df = gold(
        "facility_pull",
        "sampling_period category cells clusters median_share_weekday_pct ci_low ci_high median_share_weekend_pct evidence",
    )
    assert set(PRIMARY_PERIODS) <= set(cat_df["sampling_period"])
    assert set(PRIMARY_PERIODS) <= set(pull_df["sampling_period"])
    # Ensure no pooled 'all_periods' row exists in either summary table
    assert "all_periods" not in set(cat_df["sampling_period"])
    assert "all_periods" not in set(pull_df["sampling_period"])


def test_guardrail_jan1_sample_break_withheld_in_nataru() -> None:
    """Role 3 guardrail #1 & #2: 2022-01-01 is a sample break and must be withheld (NaN)."""
    event = gold(
        "event_window",
        "date category sampling_period median_relative_presence cells_with_support evidence",
    )
    jan1 = event[pd.to_datetime(event["date"]) == BREAK]
    assert not jan1.empty, "Expected 2022-01-01 rows in event_window"
    assert jan1["median_relative_presence"].isna().all(), (
        "2022-01-01 must have NaN relative presence"
    )
    assert jan1["evidence"].str.startswith("withheld").all(), (
        "2022-01-01 must carry a withheld evidence label"
    )


def test_guardrail_withheld_rows_handled_gracefully(tmp_path: Path) -> None:
    """Role 3 guardrail #1: withheld estimates must render without plotting a zero bar."""
    real_cat = gold(
        "category_summary",
        "sampling_period category median_ratio ci_low ci_high cells_with_ratio clusters evidence",
    ).copy()
    real_sens = gold(
        "mixed_use_sensitivity",
        "sampling_period category subset median_ratio evidence",
    ).copy()
    mask = (real_cat["sampling_period"] == "2021_Dec") & (
        real_cat["category"] == "commercial_mall"
    )
    real_cat.loc[mask, ["median_ratio", "ci_low", "ci_high"]] = np.nan
    real_cat.loc[mask, "evidence"] = "withheld: fewer than 5 site clusters"

    def fake_gold(name: str, columns: str) -> pd.DataFrame:
        if name == "category_summary":
            return real_cat
        if name == "mixed_use_sensitivity":
            return real_sens
        return gold(name, columns)

    out_png = tmp_path / "withheld_rhythm.png"
    with patch("src.visualize.gold", side_effect=fake_gold):
        rhythm(out_png)
    assert out_png.exists() and out_png.stat().st_size > 10_000


def test_missing_table_or_column_raises_actionable_error() -> None:
    """read() must tell the user which pipeline command to run when a table or column is missing."""
    with pytest.raises(FileNotFoundError, match="src.metrics"):
        read("gold", "nonexistent_table_xyz", "col_a")
    with pytest.raises(ValueError, match="missing columns"):
        read("gold", "category_summary", "sampling_period nonexistent_col_xyz")
