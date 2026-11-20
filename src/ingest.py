"""
Role 1: Data Ingestion Lead (Bronze Layer)
------------------------------------------
Responsibilities:
- Download / verify JogjaPulse daily (500m grid) and hourly (kapanewon) CSVs from Zenodo.
- Extract unique 500m grid cells & compute buffered WGS84 bounding box for Overpass API.
- Query OpenStreetMap via Overpass API (historical snapshot 2021-12-01 + current fallback).
- Audit DIY landmark coverage (UGM, UNY, Ambarrukmo Plaza, Pakuwon Mall, RSUP Dr. Sardjito, Malioboro).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml
from pyproj import Transformer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "osm_tags.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"

DAILY_CSV_PATH = RAW_DIR / "presence_cell500m_daily.csv"
HOURLY_CSV_PATH = RAW_DIR / "presence_kapanewon_hourly.csv"
UNIQUE_CELLS_PARQUET = SILVER_DIR / "grid_cells_unique.parquet"
INGESTION_AUDIT_JSON = RAW_DIR / "jogjapulse_verification_summary.json"

OSM_HISTORICAL_JSON = RAW_DIR / "osm_facilities_20211201.json"
OSM_CURRENT_JSON = RAW_DIR / "osm_facilities_current.json"
OSM_METADATA_JSON = RAW_DIR / "osm_ingestion_metadata.json"
OSM_LANDMARK_AUDIT_JSON = RAW_DIR / "osm_landmark_audit.json"

OVERPASS_ENDPOINTS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

OVERPASS_ATTIC_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
]

EXPECTED_DAILY_COLUMNS = [
    "cell_id",
    "x_min_utm",
    "y_min_utm",
    "centroid_lon",
    "centroid_lat",
    "date",
    "n_maids",
]
EXPECTED_HOURLY_COLUMNS = [
    "kab_code",
    "kab_kota",
    "kapanewon_code",
    "kapanewon",
    "date",
    "hour",
    "n_maids",
    "n_pings",
]

DIY_LANDMARKS = {
    "UGM": {
        "expected_category": "education_campus",
        "existed_in_2021_2022": True,
        "historical_note": "Founded 1949; primary Sleman campus active throughout 2021-2022.",
        "patterns": [
            r"\buniversitas gadjah mada\b",
            r"\bugm\b",
        ],
    },
    "UNY": {
        "expected_category": "education_campus",
        "existed_in_2021_2022": True,
        "historical_note": "Founded 1964; Karangmalang & Wates campuses active throughout 2021-2022.",
        "patterns": [
            r"\buniversitas negeri yogyakarta\b",
            r"\buny\b",
        ],
    },
    "Ambarrukmo_Plaza": {
        "expected_category": "commercial_mall",
        "existed_in_2021_2022": True,
        "historical_note": "Opened 2006; major Sleman shopping mall active in 2021-2022.",
        "patterns": [
            r"ambarrukmo",
            r"amplaz",
        ],
    },
    "Pakuwon_Hartono_Mall": {
        "expected_category": "commercial_mall",
        "existed_in_2021_2022": True,
        "historical_note": "Opened 2015 as Hartono Mall Yogyakarta; rebranded to Pakuwon Mall Jogja after late-2020 acquisition. OSM uses 'Pakuwon Mall Jogja' (with 'Hartono Mall' in alt/old_name).",
        "patterns": [
            r"pakuwon mall",
            r"hartono mall",
        ],
    },
    "RSUP_Dr_Sardjito": {
        "expected_category": "healthcare_hospital",
        "existed_in_2021_2022": True,
        "historical_note": "Opened 1982; primary tertiary referral hospital in DIY active in 2021-2022.",
        "patterns": [
            r"sardjito",
        ],
    },
    "Malioboro": {
        "expected_category": "tourism_site / commercial_mall",
        "existed_in_2021_2022": True,
        "historical_note": "Historic central commercial & tourism corridor in Kota Yogyakarta ( includes Plaza Malioboro / Mall Malioboro, Teras Malioboro, and Jalan Malioboro).",
        "patterns": [
            r"malioboro",
        ],
    },
}


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load pipeline YAML configuration."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_grid_bbox_wgs84(
    cells_df: pd.DataFrame,
    grid_size_m: int = 500,
    buffer_m: float = 500.0,
    crs_utm: str = "EPSG:32749",
    crs_wgs84: str = "EPSG:4326",
) -> dict[str, float]:
    """
    Derive exact WGS84 bounding box from 500m UTM grid cell footprints plus a buffer
    (in meters), as specified in Step 1 of the Project Brief.
    """
    x_min = float(cells_df["x_min_utm"].min()) - buffer_m
    y_min = float(cells_df["y_min_utm"].min()) - buffer_m
    x_max = float(cells_df["x_min_utm"].max() + grid_size_m) + buffer_m
    y_max = float(cells_df["y_min_utm"].max() + grid_size_m) + buffer_m

    transformer = Transformer.from_crs(crs_utm, crs_wgs84, always_xy=True)
    corners_lon, corners_lat = transformer.transform(
        [x_min, x_max, x_min, x_max],
        [y_min, y_min, y_max, y_max],
    )

    return {
        "south": round(float(min(corners_lat)), 6),
        "west": round(float(min(corners_lon)), 6),
        "north": round(float(max(corners_lat)), 6),
        "east": round(float(max(corners_lon)), 6),
        "buffer_meters": buffer_m,
        "utm_bounds": {
            "x_min": x_min,
            "y_min": y_min,
            "x_max": x_max,
            "y_max": y_max,
        },
    }


def verify_jogjapulse_datasets(
    daily_path: Path = DAILY_CSV_PATH,
    hourly_path: Path = HOURLY_CSV_PATH,
    unique_cells_out: Path = UNIQUE_CELLS_PARQUET,
    audit_json_out: Path = INGESTION_AUDIT_JSON,
    buffer_m: float = 500.0,
) -> dict[str, Any]:
    """
    Task 1.3: Verify JogjaPulse daily & hourly CSVs, export unique 500m grid cells
    to Silver Layer for Role 2 (Nalen), and compute exact buffered WGS84 bbox for Overpass.
    """
    if not daily_path.exists():
        raise FileNotFoundError(f"Missing daily dataset: {daily_path}")
    if not hourly_path.exists():
        raise FileNotFoundError(f"Missing hourly dataset: {hourly_path}")

    cfg = load_config()
    grid_size = int(cfg["project"].get("grid_size_meters", 500))
    crs_utm = cfg["project"].get("crs_utm", "EPSG:32749")
    crs_wgs84 = cfg["project"].get("crs_wgs84", "EPSG:4326")

    # 1. Load & verify Daily 500m Grid dataset
    daily_df = pd.read_csv(daily_path)
    missing_daily_cols = set(EXPECTED_DAILY_COLUMNS) - set(daily_df.columns)
    if missing_daily_cols:
        raise ValueError(f"Daily CSV missing columns: {missing_daily_cols}")

    n_daily_rows = len(daily_df)
    n_unique_cells = daily_df["cell_id"].nunique()
    n_unique_dates = daily_df["date"].nunique()
    min_maid_daily = int(daily_df["n_maids"].min())
    max_maid_daily = int(daily_df["n_maids"].max())

    assert n_daily_rows == 183548, f"Expected 183,548 daily rows, got {n_daily_rows}"
    assert n_unique_cells == 5715, f"Expected 5,715 unique cells, got {n_unique_cells}"
    assert min_maid_daily >= 5, f"Privacy threshold k>=5 violated: min n_maids={min_maid_daily}"

    # Extract unique cells and verify 1-to-1 coordinate mapping per cell_id
    cells_df = (
        daily_df[["cell_id", "x_min_utm", "y_min_utm", "centroid_lon", "centroid_lat"]]
        .drop_duplicates()
        .sort_values("cell_id")
        .reset_index(drop=True)
    )
    if len(cells_df) != n_unique_cells:
        raise ValueError(
            f"Inconsistent coordinates per cell_id: {len(cells_df)} rows for {n_unique_cells} cell_ids"
        )

    cells_df["x_max_utm"] = cells_df["x_min_utm"] + grid_size
    cells_df["y_max_utm"] = cells_df["y_min_utm"] + grid_size

    unique_cells_out.parent.mkdir(parents=True, exist_ok=True)
    cells_df.to_parquet(unique_cells_out, index=False)

    derived_bbox = compute_grid_bbox_wgs84(
        cells_df,
        grid_size_m=grid_size,
        buffer_m=buffer_m,
        crs_utm=crs_utm,
        crs_wgs84=crs_wgs84,
    )

    # 2. Load & verify Hourly Kapanewon dataset
    hourly_df = pd.read_csv(hourly_path)
    missing_hourly_cols = set(EXPECTED_HOURLY_COLUMNS) - set(hourly_df.columns)
    if missing_hourly_cols:
        raise ValueError(f"Hourly CSV missing columns: {missing_hourly_cols}")

    n_hourly_rows = len(hourly_df)
    n_kapanewon = hourly_df["kapanewon_code"].nunique()
    n_kab_kota = hourly_df["kab_code"].nunique()
    min_maid_hourly = int(hourly_df["n_maids"].min())

    assert n_kapanewon == 78, f"Expected 78 kapanewon, got {n_kapanewon}"
    assert min_maid_hourly >= 5, f"Privacy threshold k>=5 violated in hourly: min={min_maid_hourly}"

    summary = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "daily_grid": {
            "file": str(daily_path.relative_to(PROJECT_ROOT)),
            "rows": n_daily_rows,
            "unique_cells": n_unique_cells,
            "unique_dates": n_unique_dates,
            "date_min": str(daily_df["date"].min()),
            "date_max": str(daily_df["date"].max()),
            "total_possible_cell_days": n_unique_cells * n_unique_dates,
            "observed_cell_day_fraction": round(n_daily_rows / (n_unique_cells * n_unique_dates), 4),
            "n_maids_min": min_maid_daily,
            "n_maids_max": max_maid_daily,
            "centroid_bounds_wgs84": {
                "south": round(float(cells_df["centroid_lat"].min()), 6),
                "west": round(float(cells_df["centroid_lon"].min()), 6),
                "north": round(float(cells_df["centroid_lat"].max()), 6),
                "east": round(float(cells_df["centroid_lon"].max()), 6),
            },
            "derived_overpass_bbox_wgs84": derived_bbox,
            "silver_unique_cells_parquet": str(unique_cells_out.relative_to(PROJECT_ROOT)),
        },
        "hourly_kapanewon": {
            "file": str(hourly_path.relative_to(PROJECT_ROOT)),
            "rows": n_hourly_rows,
            "unique_kab_kota": n_kab_kota,
            "unique_kapanewon": n_kapanewon,
            "unique_dates": int(hourly_df["date"].nunique()),
            "date_min": str(hourly_df["date"].min()),
            "date_max": str(hourly_df["date"].max()),
            "hour_min": int(hourly_df["hour"].min()),
            "hour_max": int(hourly_df["hour"].max()),
            "n_maids_min": min_maid_hourly,
            "n_maids_max": int(hourly_df["n_maids"].max()),
            "n_pings_min": int(hourly_df["n_pings"].min()),
            "n_pings_max": int(hourly_df["n_pings"].max()),
        },
    }

    audit_json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_json_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_overpass_query(
    facility_categories: dict[str, dict[str, list[str]]],
    bbox: dict[str, float],
    historical_date: str | None = None,
    timeout: int = 180,
) -> str:
    """
    Task 2.1: Build Overpass QL query from `configs/osm_tags.yaml` for nodes, ways, and relations
    with full geometry (`out body geom;`) across the derived WGS84 bounding box.
    """
    date_clause = f'[date:"{historical_date}"]' if historical_date else ""
    bbox_str = f"{bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']}"

    # Group tag values by OSM key to minimize redundant regex clauses
    key_values: dict[str, list[str]] = {}
    for _category, tag_dict in facility_categories.items():
        for osm_key, values in tag_dict.items():
            key_values.setdefault(osm_key, [])
            for v in values:
                if v not in key_values[osm_key]:
                    key_values[osm_key].append(v)

    clauses = []
    for osm_key, values in sorted(key_values.items()):
        for val in values:
            clauses.append(f'  nwr["{osm_key}"="{val}"]({bbox_str});')

    # Capture Jalan Malioboro corridor explicitly using tight central Yogyakarta bbox (-7.805,110.360,-7.785,110.372)
    clauses.append('  way["highway"]["name"~"Malioboro"](-7.805,110.360,-7.785,110.372);')

    query_lines = [
        f"[out:json][timeout:{timeout}]{date_clause};",
        "(",
        *clauses,
        ");",
        "out body geom;",
    ]
    return "\n".join(query_lines)


def fetch_overpass_snapshot(
    query: str,
    output_path: Path,
    endpoints: list[str] = OVERPASS_ENDPOINTS,
    force_refresh: bool = False,
    allow_unavailable: bool = False,
    request_timeout: int = 90,
) -> dict[str, Any]:
    """
    Execute Overpass QL query against public endpoints with retry/fallback, saving raw JSON.
    """
    if output_path.exists() and not force_refresh:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("elements") and "remark" not in data:
            return {
                "status": "cached",
                "endpoint_used": "local_cache",
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "output_file": str(output_path.relative_to(PROJECT_ROOT)),
                "data": data,
                "error": None,
            }

    headers = {
        "User-Agent": "UGM-HumanMobility-CityMagnets/1.0 (https://github.com/altafparves/Human-Mobility)"
    }
    last_error = None
    for endpoint in endpoints:
        for attempt in range(1, 3):
            try:
                print(f"Querying Overpass ({endpoint}, attempt {attempt})...")
                resp = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=headers,
                    timeout=request_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                if "elements" not in data:
                    raise ValueError(f"Overpass response missing 'elements': {list(data.keys())}")
                if "remark" in data and not data["elements"]:
                    raise RuntimeError(f"Overpass runtime error/remark: {data['remark']}")

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                return {
                    "status": "fetched",
                    "endpoint_used": endpoint,
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "output_file": str(output_path.relative_to(PROJECT_ROOT)),
                    "data": data,
                    "error": None,
                }
            except Exception as exc:
                last_error = exc
                print(f"Warning: Overpass attempt failed ({endpoint}): {exc}")
                time.sleep(2 * attempt)

    if allow_unavailable:
        return {
            "status": "unavailable_fallback_to_current",
            "endpoint_used": None,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "output_file": None,
            "data": {"elements": []},
            "error": str(last_error),
        }

    raise RuntimeError(f"All Overpass endpoints failed. Last error: {last_error}")


def classify_element_categories(
    tags: dict[str, str],
    facility_categories: dict[str, dict[str, list[str]]],
) -> list[str]:
    """Map an OSM element's tags to our 6 project facility categories."""
    matched_cats: list[str] = []
    for category, tag_rules in facility_categories.items():
        for osm_key, allowed_values in tag_rules.items():
            if tags.get(osm_key) in allowed_values:
                matched_cats.append(category)
                break
    return matched_cats


def summarize_osm_elements(
    elements: list[dict[str, Any]],
    facility_categories: dict[str, dict[str, list[str]]],
) -> dict[str, Any]:
    """Summarize OSM element counts by geometry type and project facility category."""
    type_counts = {"node": 0, "way": 0, "relation": 0}
    category_counts = {cat: 0 for cat in facility_categories}
    category_by_type = {cat: {"node": 0, "way": 0, "relation": 0} for cat in facility_categories}
    named_count = 0

    for el in elements:
        el_type = el.get("type", "unknown")
        if el_type in type_counts:
            type_counts[el_type] += 1
        tags = el.get("tags") or {}
        if "name" in tags or "name:id" in tags or "name:en" in tags:
            named_count += 1
        cats = classify_element_categories(tags, facility_categories)
        for c in cats:
            category_counts[c] += 1
            if el_type in category_by_type[c]:
                category_by_type[c][el_type] += 1

    return {
        "total_elements": len(elements),
        "named_elements": named_count,
        "by_osm_type": type_counts,
        "by_facility_category": category_counts,
        "by_category_and_osm_type": category_by_type,
    }


def audit_diy_landmarks(
    elements: list[dict[str, Any]],
    facility_categories: dict[str, dict[str, list[str]]],
) -> dict[str, Any]:
    """
    Task 2.3: Audit DIY landmark coverage (UGM, UNY, Ambarrukmo Plaza, Pakuwon/Hartono Mall,
    RSUP Dr. Sardjito, Malioboro) in an OSM snapshot.
    """
    landmark_results: dict[str, Any] = {}

    for landmark_key, spec in DIY_LANDMARKS.items():
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in spec["patterns"]]
        matches = []

        for el in elements:
            tags = el.get("tags") or {}
            searchable_names = " | ".join(
                str(tags.get(k, ""))
                for k in ("name", "name:id", "name:en", "short_name", "alt_name", "official_name", "operator")
                if tags.get(k)
            )
            if not searchable_names:
                continue

            if any(pat.search(searchable_names) for pat in compiled_patterns):
                cats = classify_element_categories(tags, facility_categories)
                matches.append(
                    {
                        "osm_id": f"{el.get('type')}/{el.get('id')}",
                        "osm_type": el.get("type"),
                        "name": tags.get("name") or tags.get("short_name") or searchable_names,
                        "alt_names": {
                            k: tags[k]
                            for k in ("short_name", "alt_name", "official_name", "old_name")
                            if k in tags
                        },
                        "matched_categories": cats,
                        "key_tags": {
                            k: tags[k]
                            for k in ("amenity", "healthcare", "shop", "tourism", "historic", "highway", "public_transport", "railway", "building")
                            if k in tags
                        },
                    }
                )

        # Prioritize ways/relations and category-matching elements for summary preview
        category_matched = [m for m in matches if m["matched_categories"]]
        by_type = {"node": 0, "way": 0, "relation": 0}
        for m in matches:
            t = m["osm_type"]
            if t in by_type:
                by_type[t] += 1

        distinct_names = sorted({m["name"] for m in matches if m.get("name")})

        landmark_results[landmark_key] = {
            "expected_category": spec["expected_category"],
            "existed_in_2021_2022": spec["existed_in_2021_2022"],
            "historical_note": spec["historical_note"],
            "is_captured": len(matches) > 0,
            "is_captured_in_study_categories": len(category_matched) > 0,
            "total_matching_elements": len(matches),
            "category_matching_elements": len(category_matched),
            "counts_by_osm_type": by_type,
            "distinct_names_sample": distinct_names[:15],
            "top_category_matches": category_matched[:10],
        }

    return landmark_results


def run_osm_ingestion_and_audit(
    verification_summary: dict[str, Any],
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Task 2.1, 2.2, 2.3: Build Overpass queries, extract historical (2021-12-01) and
    current snapshots, log ingestion metadata, and execute the DIY landmark coverage audit.
    """
    cfg = load_config()
    facility_categories = cfg["facility_categories"]
    historical_date = cfg["overpass"].get("historical_date", "2021-12-01T00:00:00Z")
    derived_bbox = verification_summary["daily_grid"]["derived_overpass_bbox_wgs84"]

    # 1. Build queries
    hist_query = build_overpass_query(
        facility_categories=facility_categories,
        bbox=derived_bbox,
        historical_date=historical_date,
        timeout=60,
    )
    curr_query = build_overpass_query(
        facility_categories=facility_categories,
        bbox=derived_bbox,
        historical_date=None,
        timeout=120,
    )

    # 2. Fetch snapshots (Current extract via available mirror + Historical attic attempt with documented fallback)
    curr_res = fetch_overpass_snapshot(
        query=curr_query,
        output_path=OSM_CURRENT_JSON,
        endpoints=OVERPASS_ENDPOINTS,
        force_refresh=force_refresh,
        allow_unavailable=False,
        request_timeout=120,
    )
    hist_res = fetch_overpass_snapshot(
        query=hist_query,
        output_path=OSM_HISTORICAL_JSON,
        endpoints=OVERPASS_ATTIC_ENDPOINTS,
        force_refresh=force_refresh,
        allow_unavailable=True,
        request_timeout=30,
    )

    hist_elements = hist_res["data"].get("elements", [])
    curr_elements = curr_res["data"].get("elements", [])

    hist_summary = summarize_osm_elements(hist_elements, facility_categories)
    curr_summary = summarize_osm_elements(curr_elements, facility_categories)

    primary_snapshot_used = (
        "historical_2021-12-01"
        if hist_res["status"] in ("fetched", "cached") and len(hist_elements) > 0
        else "current_snapshot_verified_2021_2022_existence"
    )

    # 3. Save OSM Ingestion Metadata
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "crs_source": "EPSG:4326",
        "primary_snapshot_selected": primary_snapshot_used,
        "derived_bbox_wgs84": derived_bbox,
        "historical_snapshot": {
            "requested_date": historical_date,
            "status": hist_res["status"],
            "endpoint_used": hist_res["endpoint_used"],
            "fetched_at_utc": hist_res["fetched_at_utc"],
            "osm3s_timestamp_base": hist_res["data"].get("osm3s", {}).get("timestamp_osm_base"),
            "output_file": hist_res["output_file"],
            "error": hist_res.get("error"),
            "query": hist_query,
            "summary": hist_summary,
        },
        "current_snapshot": {
            "requested_date": "current",
            "status": curr_res["status"],
            "endpoint_used": curr_res["endpoint_used"],
            "fetched_at_utc": curr_res["fetched_at_utc"],
            "osm3s_timestamp_base": curr_res["data"].get("osm3s", {}).get("timestamp_osm_base"),
            "output_file": curr_res["output_file"],
            "error": curr_res.get("error"),
            "query": curr_query,
            "summary": curr_summary,
        },
    }
    with open(OSM_METADATA_JSON, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # 4. Run Landmark Audit on both snapshots and compare discrepancies
    hist_landmarks = audit_diy_landmarks(hist_elements, facility_categories)
    curr_landmarks = audit_diy_landmarks(curr_elements, facility_categories)

    comparison: dict[str, Any] = {}
    for lm_key in DIY_LANDMARKS:
        h = hist_landmarks[lm_key]
        c = curr_landmarks[lm_key]
        comparison[lm_key] = {
            "expected_category": h["expected_category"],
            "existed_in_2021_2022": c["existed_in_2021_2022"],
            "historical_note": c["historical_note"],
            "historical_2021_status": hist_res["status"],
            "historical_2021_captured": h["is_captured"],
            "historical_2021_category_elements": h["category_matching_elements"],
            "current_captured": c["is_captured"],
            "current_category_elements": c["category_matching_elements"],
            "current_total_elements": c["total_matching_elements"],
            "current_counts_by_osm_type": c["counts_by_osm_type"],
            "current_names_sample": c["distinct_names_sample"][:6],
        }

    landmark_audit_report = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "historical_date": historical_date,
        "category_count_comparison": {
            cat: {
                "historical_2021": hist_summary["by_facility_category"][cat],
                "current": curr_summary["by_facility_category"][cat],
                "delta": curr_summary["by_facility_category"][cat] - hist_summary["by_facility_category"][cat],
            }
            for cat in facility_categories
        },
        "landmark_comparison_summary": comparison,
        "historical_2021_details": hist_landmarks,
        "current_details": curr_landmarks,
    }
    with open(OSM_LANDMARK_AUDIT_JSON, "w", encoding="utf-8") as f:
        json.dump(landmark_audit_report, f, indent=2)

    return {
        "metadata": metadata,
        "landmark_audit": landmark_audit_report,
    }


if __name__ == "__main__":
    jp_report = verify_jogjapulse_datasets()
    print("=== JogjaPulse Verification Complete (Task 1.3) ===")
    print(f"Verified {jp_report['daily_grid']['rows']} daily rows across {jp_report['daily_grid']['unique_cells']} cells.")

    osm_report = run_osm_ingestion_and_audit(jp_report)
    print("\n=== OSM Overpass Extraction & Landmark Audit Complete (Batch 2) ===")
    print("Category Counts (Historical 2021-12-01 vs Current):")
    print(json.dumps(osm_report["landmark_audit"]["category_count_comparison"], indent=2))
    print("\nDIY Landmark Audit Summary:")
    print(json.dumps(osm_report["landmark_audit"]["landmark_comparison_summary"], indent=2))
