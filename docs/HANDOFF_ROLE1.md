# 📌 Role 1 Handoff — Data Ingestion & Temporal Cleaning (Altaf → Team)

**From:** Altaf (Role 1 — Data Ingestion & Temporal Cleaning Lead)
**To:** Nalen (Role 2 — next in pipeline), Rafi Busthami (Role 3), Akhnaf (Role 4)
**Status:** ✅ **Role 1 complete** — Bronze & Silver (Temporal) layers are built, tested, and ready to consume.

---

## 1. TL;DR

* The raw JogjaPulse CSVs are **verified**, the OSM facilities are **extracted** (2,358 elements, nodes + ways + relations with full geometry), and the **6 DIY landmarks are audited**.
* The daily grid and hourly kapanewon data are **cleaned** into Silver Parquet tables with WIB timestamps, calendar flags (weekend, Nataru, sample breaks, anomalous date, sampling period), and **80 / 90 / 95 % publication-coverage flags** for every cell and period.
* **Bonus for Role 3:** `published_presence_share_pct` (all cells and common-90 % cells) is already precomputed.
* **Nalen, your inputs are ready:** `data/silver/grid_cells_unique.parquet` + `data/raw/osm_facilities_current.json`. Jump to [§6](#6-for-nalen-role-2--what-you-need-to-do).

---

## 2. Why Role 1 Can Be Considered Done

Checked against the Role 1 objective in [`project_brief_city_magnets_yogyakarta_refined.md`](../project_brief_city_magnets_yogyakarta_refined.md) (§4 Week 1 Verification Task, §5 Step 1–2, §7.C Role 1):

| # | Brief requirement (Role 1) | Status | Evidence |
| :-: | :--- | :-: | :--- |
| 1 | Load & verify JogjaPulse daily + hourly CSVs into `data/raw/` | ✅ | `ingest.verify_jogjapulse_datasets()` asserts 183,548 rows, 5,715 cells, 78 kapanewon, privacy floor `n_maids ≥ 5` → `jogjapulse_verification_summary.json` |
| 2 | Derive the Overpass extent from **grid polygons + buffer** (not the draft bbox) | ✅ | `compute_grid_bbox_wgs84()`: UTM cell footprints + 500 m buffer → WGS84 |
| 3 | Retrieve `node` / `way` / `relation` incl. full geometry; log endpoint, query, time | ✅ | `out body geom;` → `osm_facilities_current.json`; endpoint, query, and timestamps in `osm_ingestion_metadata.json` |
| 4 | Historical snapshot (2021-12-01) with fallback comparison to current extract | ⚠️ Accepted fallback | Attic query timed out on all public endpoints; the fallback is **documented** in metadata (`primary_snapshot_selected = current_snapshot_verified_2021_2022_existence`). The brief explicitly permits this: *"If only a current extract is usable, label its date and verify major facilities existed during 2021–22"*, and we did both (snapshot base `2026-11-15T04:15:17Z`, `existed_in_2021_2022` + historical note per landmark). |
| 5 | Week 1 landmark audit (UGM, UNY, Ambarrukmo Plaza, Pakuwon Mall, RSUP Dr. Sardjito, Malioboro); log alternate names | ✅ | All 6 captured in study categories → `osm_landmark_audit.json` (e.g. *Hartono Mall* → *Pakuwon Mall Jogja*) |
| 6 | Parse dates; standardize timestamps to WIB (UTC+7) | ✅ | `date_wib`, `timestamp_wib` (`Asia/Jakarta`), `hour_wib` |
| 7 | Calendar flags: `day_of_week`, `is_weekend`, `is_nataru_window` (24 Dec–2 Jan), `sampling_period` | ✅ | `build_master_calendar()`; plus `is_ordinary_weekday/weekend` (Nataru and anomaly excluded) |
| 8 | Flag `2022-03-08`; mark sample breaks 1 Jan & 16 Feb | ✅ | `is_anomalous_date`, `is_sample_break` |
| 9 | Expected calendar per cell; coverage = published / expected days, **separately weekday & weekend**, per period (Dec, Jan, 1–15 Feb, 16–28 Feb) | ✅ | `cell_coverage_audit.parquet` (5,715 cells × 7 periods; absent days retained as missing) |
| 10 | ≥ 90 % coverage filter + 80 % / 95 % sensitivity flags | ✅ | `pass_{80,90,95}_*` flags. Primary window: **772 / 470 / 341** cells pass 80 / 90 / 95 % |
| 11 | Export cleaned tables to `data/silver/` (Parquet) | ✅ | 6 Parquet tables + `temporal_cleaning_summary.json` |
| 12 | Tests / reproducibility | ✅ | `pytest tests/test_role1_pipeline.py` → **5 passed** |

**Known minor deviations (not blockers):**
1. **OSM snapshot date:** we use the current extract (see row 4). Facilities opened after 2022 could appear; Role 2 can filter them with `start_date` / `opening_date` tags if needed.
2. **File name:** the brief lists `data/silver/mobility_clean.parquet`, but the actual file is **`data/silver/mobility_daily_clean.parquet`**.
3. **JogjaPulse download:** `ingest.py` *verifies* the CSVs, but they have to be downloaded manually from Zenodo (one-time step, see §3).

---

## 3. How to Reproduce Role 1 Outputs

> [!IMPORTANT]
> `data/` is git-ignored (large files). The **frozen OSM snapshot** and its audit JSONs *are* committed, so everyone uses the exact same OSM data. You only need to download the two JogjaPulse CSVs and regenerate Silver locally.

```bash
# 1. Environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Download from https://zenodo.org/records/23157460 into data/raw/
#    - presence_cell500m_daily.csv
#    - presence_kapanewon_hourly.csv

# 3. Bronze: verify CSVs, export unique grid cells, OSM extract (uses cached JSON) + landmark audit
python -m src.ingest

# 4. Silver: calendar, coverage audit, cleaned daily + hourly tables
python -m src.clean_temporal

# 5. Check the data contracts
pytest -q tests/test_role1_pipeline.py
```

* `src.ingest` **re-uses** `data/raw/osm_facilities_current.json` if it exists (no network call). Only pass `force_refresh=True` to `run_osm_ingestion_and_audit()` if the team agrees to re-snapshot OSM.
* The historical attic query is retried every run (≈ 1–2 min of timeouts) and then falls back gracefully. This is expected.

---

## 4. Code Walkthrough

### `configs/osm_tags.yaml` — single source of truth
| Block | Controls |
| :--- | :--- |
| `project` | CRS (`EPSG:4326` → `EPSG:32749`), `grid_size_meters: 500` |
| `overpass` | Default endpoint, `historical_date`, draft bbox (the real bbox is derived from the grid) |
| `analysis` | Primary window (2021-12-01 → 2022-02-28), anomalous dates, Nataru window, sample breaks, coverage thresholds |
| `facility_categories` | OSM tag → 6 study categories (`education_campus`, `healthcare_hospital`, `commercial_mall`, `traditional_market`, `tourism_site`, `transit_hub`) |

### `src/ingest.py` — Bronze layer
| Function | What it does | Output |
| :--- | :--- | :--- |
| `load_config()` | Reads the YAML above | dict |
| `verify_jogjapulse_datasets()` | Schema + row/cell/kapanewon assertions, k ≥ 5 check, 1-to-1 cell→coordinate check, adds `x_max_utm` / `y_max_utm` | `data/silver/grid_cells_unique.parquet`, `data/raw/jogjapulse_verification_summary.json` |
| `compute_grid_bbox_wgs84()` | UTM grid extent + buffer → WGS84 bbox for Overpass | dict |
| `build_overpass_query()` | Builds Overpass QL from `facility_categories` (`nwr[...]` + `out body geom;`), plus the Jalan Malioboro corridor | query string |
| `fetch_overpass_snapshot()` | POST with endpoint fallback & retries; caches to disk | raw Overpass JSON |
| `classify_element_categories()` | Tags → list of matching study categories (**reuse this in Role 2**) | `list[str]` |
| `summarize_osm_elements()` | Counts by OSM type & category | dict |
| `audit_diy_landmarks()` | Regex name search over `name`, `alt_name`, `short_name`, `official_name`, `operator`… | dict |
| `run_osm_ingestion_and_audit()` | Orchestrates historical + current fetch, metadata, landmark audit | `osm_ingestion_metadata.json`, `osm_landmark_audit.json` |

### `src/clean_temporal.py` — Silver (temporal) layer
| Function | What it does |
| :--- | :--- |
| `assign_sampling_period()` | Date → `2021_Dec`, `2022_Jan`, `2022_Feb_P1` (1–15), `2022_Feb_P2` (16–28), `2022_Mar_Apr_Exploratory` |
| `build_master_calendar()` | 151-day calendar with WIB date + all flags |
| `compute_period_coverage_for_cells()` | Per cell, per period: published vs expected weekday/weekend days for **all days** and **ordinary days** (Nataru + anomaly excluded); 80/90/95 % pass flags |
| `compute_hourly_kapanewon_cleaning()` | Hourly WIB timestamps, `pings_per_maid`, per-kapanewon hourly coverage audit (incl. min coverage across the 24 hours) |
| `run_daily_temporal_cleaning()` | Orchestrates everything, adds strict "passes in every primary sub-period" flags, daily denominators, presence share, writes all Silver files + JSON summary |

### `tests/test_role1_pipeline.py`
Data-contract tests: Bronze files exist and all landmarks are captured; `grid_cells_unique` has 5,715 unique cells with UTM bounds; the daily clean table has the expected flags/columns; the coverage audit and hourly tables are consistent. **If you change Role 1 outputs, these must stay green.**

### `notebooks/role1_playground.ipynb`
A visual explainer: **(1)** raw-data pitfalls (sample breaks, suppression), **(2)** what Role 1 produced (OSM counts, landmark audit, schema before/after, presence share stabilizing the breaks, cells passing 80/90/95 %), **(3)** a *rough prototype* of Roles 2–4 (naive spatial join, weekday/weekend ratio, diurnal heatmap, Folium map). Section 3 is **only a sketch**: no deduplication and no rigorous stats. Use it for inspiration, not as final logic.

---

## 5. Output Data Dictionary

### Bronze — `data/raw/`
| File | Committed? | Content |
| :--- | :-: | :--- |
| `presence_cell500m_daily.csv` | ❌ (Zenodo) | 183,548 rows · `cell_id, x_min_utm, y_min_utm, centroid_lon, centroid_lat, date, n_maids` |
| `presence_kapanewon_hourly.csv` | ❌ (Zenodo) | 230,418 rows · 78 kapanewon · `date, hour, n_maids, n_pings` |
| `osm_facilities_current.json` | ✅ frozen | Overpass JSON, 2,358 elements (1,401 nodes / 932 ways / 25 relations) |
| `osm_ingestion_metadata.json` | ✅ | Endpoint, exact queries, timestamps, counts per category × OSM type |
| `osm_landmark_audit.json` | ✅ | Per-landmark matches, alternate names, historical note |
| `jogjapulse_verification_summary.json` | ✅ | Row/cell/date stats + derived Overpass bbox |

### Silver — `data/silver/` (regenerate locally)
| File | Shape | Grain | Use it for |
| :--- | :--- | :--- | :--- |
| `grid_cells_unique.parquet` | 5,715 × 7 | cell | **Role 2:** grid polygons (`x_min_utm`, `y_min_utm`, `x_max_utm`, `y_max_utm`, EPSG:32749) |
| `mobility_daily_clean.parquet` | 183,548 × 50 | cell × day | **Role 3:** main analysis table (flags, coverage, presence share) |
| `cell_coverage_audit.parquet` | 40,005 × 31 | cell × period (7) | Coverage reporting; choose eligible cells per period |
| `daily_coverage_summary.parquet` | 151 × 23 | day | Coverage panel under the Nataru chart (Role 4); daily totals |
| `kapanewon_hourly_clean.parquet` | 230,418 × 33 | kapanewon × hour | RQ4 diurnal pulse |
| `kapanewon_coverage_audit.parquet` | 546 × 27 | kapanewon × period (7) | Hourly coverage + busiest kapanewon |
| `temporal_cleaning_summary.json` | — | — | Human-readable counts (cells passing, key-date diagnostics) |

**Key columns in `mobility_daily_clean.parquet`:**
| Column(s) | Meaning |
| :--- | :--- |
| `is_weekend`, `is_nataru_window`, `is_sample_break`, `is_anomalous_date` | Raw calendar flags (they can overlap) |
| `is_ordinary_weekday`, `is_ordinary_weekend` | Use for weekday/weekend ratios (Nataru + 2022-03-08 excluded) |
| `sampling_period`, `is_primary_window` | Compare *within* a period, never across the Jan 1 / Feb 16 breaks |
| `pass_{80,90,95}_in_period` | Cell passes coverage in *this row's* sampling period |
| `pass_{80,90,95}_primary_window` | Cell passes across Dec 2021–Feb 2022 as a whole (**main 90 % rule → 470 cells**) |
| `pass_{80,90,95}_every_primary_period` | Strictest: passes in **each** of Dec / Jan / Feb P1 / Feb P2 (264 cells at 90 %) |
| `*_all_days_*` variants | Same rule but counting Nataru days too (sensitivity) |
| `published_presence_share_pct` | `n_maids / Σ n_maids (all published cells that day) × 100` |
| `published_presence_share_common90_pct` | Same, but the denominator uses only `pass_90_primary_window` cells (NaN otherwise) |

---

## 6. For Nalen (Role 2) — What You Need to Do

**Goal:** turn the grid + OSM data into a per-cell facility table that Rafi can join on `cell_id`. Build it in `src/spatial_join.py` (currently a stub).

### Inputs ready for you
* `data/silver/grid_cells_unique.parquet`: 5,715 cells with UTM bounds.
* `data/raw/osm_facilities_current.json`: Overpass JSON. Element shapes:
  * `node` → `lat`, `lon`, `tags`
  * `way` → `geometry: [{lat, lon}, ...]` (closed ring = polygon), `tags`
  * `relation` → `members: [{type, ref, role, geometry}]` (assemble `outer`/`inner` rings into multipolygons), `tags`
* `configs/osm_tags.yaml` → `facility_categories`; and `from src.ingest import classify_element_categories, load_config` to categorize the same way the audit did.

### Suggested steps (general)
1. **Grid polygons:** `shapely.box(x_min_utm, y_min_utm, x_max_utm, y_max_utm)` → GeoDataFrame in `EPSG:32749`.
2. **Parse OSM → GeoDataFrame** (`EPSG:4326`): Point / Polygon (or LineString for open ways) / MultiPolygon; keep `osm_id`, `osm_type`, `name`, key tags, `categories`. Then `.to_crs("EPSG:32749")`.
3. **Categorize:** use `classify_element_categories`; decide how to handle the **2 elements that match 2 categories** and drop the 1 uncategorized element (*Jalan Malioboro* highway, which was fetched only for the landmark audit).
4. **Deduplicate** (the hard part 🔥): e.g. drop nodes that fall inside a polygon of the same category; merge features sharing a name / `operator` within a distance; group large complexes (UGM: 39 nodes + 9 ways) into one *site*. **Log every decision and ambiguous case** (the brief requires this).
5. **Spatial join:** `gpd.sjoin(grid, facilities, predicate="intersects")`; for polygons also compute overlap area / share of the cell.
6. **Classify cells:** `single_category`, `mixed_use`, `no_selected_facility`, then build the **spatially matched baseline** set (e.g. nearby no-facility cells).
7. **Report** (brief §4): number of distinct facilities and grid cells after deduplication, per category.

### Suggested output contract → `data/silver/grid_facilities.parquet`
One row per `cell_id` (all 5,715): `cell_id`, `geometry` (or keep the UTM bounds), `n_<category>` counts, `has_<category>` booleans, `n_categories`, `cell_class` (`single_category` / `mixed_use` / `no_selected_facility`), `primary_category`, `is_baseline_candidate`, `facility_names`. Optionally a long table `facilities_dedup.parquet` (one row per deduplicated site). Agree on the final columns with Rafi.

### Gotchas I noticed
* **Transit dominates the counts** (1,039 elements, mostly `bus_stop` nodes) → nearly every urban cell will "have transit". Consider treating it separately or thresholding it.
* **Large campuses / hospitals span several cells.** Decide whether a polygon counts for every cell it touches or only above an overlap threshold.
* **Current snapshot (2026)**: some facilities may postdate 2022. Check the `start_date` tags for the big ones if you have time.
* Use only `grid_cells_unique.parquet` cells as the universe; facilities outside the grid should be filtered out (the bbox includes a 500 m buffer).

---

## 7. Notes for Rafi (Role 3) & Akhnaf (Role 4)

**Rafi:**
* Start from `mobility_daily_clean.parquet`; join Nalen's `grid_facilities.parquet` on `cell_id`.
* Main eligibility: `pass_90_primary_window`; sensitivity: the 80 / 95 variants; strict robustness: `pass_90_every_primary_period`.
* Weekday/weekend ratios: use `is_ordinary_weekday/weekend` **within** each `sampling_period`.
* Nataru: compare against the same weekday in the same period; **always isolate 2022-01-01** (`is_sample_break`). Exclude 2022-03-08 if you use Mar–Apr.
* Shares are already computed; summarize with means/medians, not sums.
* RQ4: `kapanewon_hourly_clean.parquet` (`hour_wib`, `n_maids`, `pings_per_maid`) + `pass_90_hourly_primary_window`.

**Akhnaf:**
* The Nataru chart coverage panel → `daily_coverage_summary.parquet` (`daily_cell_coverage_pct`, `is_sample_break`).
* Diurnal heatmap → `kapanewon_hourly_clean.parquet`; busiest kapanewon list → `temporal_cleaning_summary.json → hourly_kapanewon_summary.top_10_busiest_kapanewon_primary_window`.
* The Folium prototype in `notebooks/role1_playground.ipynb` §3 is a starting template.

---

## 8. Shared Reminders

* Don't edit files in `data/raw/`, since they are the immutable Bronze layer. If OSM must be re-snapshotted, agree as a team first and update `osm_ingestion_metadata.json`.
* Keep `pytest` green before pushing.
* For the video/presentation, my segment covers: data sources, the k = 5 suppression, the Jan 1 / Feb 16 breaks, the coverage rule, and the landmark audit.
* Questions about Role 1 → ping **Altaf**.

