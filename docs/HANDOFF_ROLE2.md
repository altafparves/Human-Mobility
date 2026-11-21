# 📌 Role 2 Handoff: Geospatial Engineering & Facility Deduplication (Nalen → Team)

**From:** Nalen (Role 2, Geospatial Engineering & Facility Deduplication Lead)
**To:** Rafi Busthami (Role 3, next in pipeline), Akhnaf (Role 4), Altaf (Role 1)
**Status:** ✅ **Role 2 complete.** The spatial Silver layer is built, tested, and ready to consume.

---

## 1. TL;DR

* The OSM extract (2,357 categorized features) is parsed into points, polygons and multipolygons in `EPSG:32749`.
* Duplicate drawings of the same place are merged: **1,839 in-grid features → 1,276 real-world sites** (UGM: 18 features → 1 campus site).
* Every site is placed on the 500 m grid with exact overlap areas, and tiny border slivers are not counted.
* Every one of the 5,715 cells is labelled **single_category / mixed_use / no_selected_facility**, with transit kept as a separate flag and **baseline candidates** flagged.
* **Rafi, your input is ready:** `data/silver/grid_facilities.parquet` (one row per cell, join on `cell_id`). Jump to [§6](#6-for-rafi-role-3).
* Visual walkthrough: [`notebooks/role2_playground.ipynb`](../notebooks/role2_playground.ipynb) (outputs saved, readable on GitHub).

---

## 2. Why Role 2 Can Be Considered Done

Checked against the brief ([`project_brief_city_magnets_yogyakarta_refined.md`](../project_brief_city_magnets_yogyakarta_refined.md) §5 Step 3, §8.C Role 2):

| # | Brief requirement (Role 2) | Status | Evidence |
| :-: | :--- | :-: | :--- |
| 1 | Reconstruct 500 m polygons `[x_min, x_min+500) × [y_min, y_min+500)` in `EPSG:32749` | ✅ | `build_grid_polygons()`: 5,715 squares, all exactly 250,000 m² |
| 2 | Reproject OSM points and polygons `EPSG:4326 → EPSG:32749` | ✅ | `parse_osm_facilities()`: nodes → Point, closed ways → Polygon, relations → MultiPolygon (split rings stitched, holes cut) |
| 3 | Apply the tag dictionary to the 6 study categories | ✅ | Reuses `classify_element_categories` + `configs/osm_tags.yaml`. Only *Jalan Malioboro* dropped (no category) |
| 4 | Deduplicate node vs polygon and multi-building complexes; record decisions and ambiguous cases | ✅ | `dedup_facilities()` + `facilities_dedup_log.json` (rules, links per rule, 11 same-name groups kept apart) |
| 5 | Spatial join with category presence, unique facility counts, polygon overlap areas | ✅ | `join_sites_to_cells()` → `cell_facility_links.parquet`, aggregated in `grid_facilities.parquet` |
| 6 | Keep mixed-use cells explicit; single-category subset for sensitivity | ✅ | `cell_class`, `n_categories`, `has_<category>` |
| 7 | Label cells without facilities as *no selected facility mapped* | ✅ | `cell_class = "no_selected_facility"` |
| 8 | Build the spatially matched baseline set | ✅ (distance part) | `is_baseline_candidate`, `dist_to_facility_cell_m`. Matching on coverage and activity is Role 3 (needs mobility data) |
| 9 | Report distinct facilities and grid cells after dedup, per category | ✅ | `spatial_join_summary.json` and §5 below |
| 10 | Tests / reproducibility | ✅ | `pytest -q` → **12 passed** (7 Role 2 + 5 Role 1) |

---

## 3. How to Reproduce

```bash
# Role 1 first (needs the two JogjaPulse CSVs in data/raw/, see HANDOFF_ROLE1.md)
python -m src.ingest
python -m src.clean_temporal

# Role 2
python -m src.spatial_join        # ~10 s, prints a JSON summary
pytest -q                         # 12 passed
```

> [!WARNING]
> Rerunning `src.ingest` rewrites the three committed JSONs in `data/raw/` (fetch timestamps become `local_cache`). Restore them before committing:
> `git checkout -- data/raw/jogjapulse_verification_summary.json data/raw/osm_ingestion_metadata.json data/raw/osm_landmark_audit.json`

---

## 4. Decisions & Rules (all in `src/spatial_join.py`)

### Deduplication: two features of the **same category** become one site when any rule holds

| Rule | Condition | Example | Links |
| :--- | :--- | :--- | --: |
| `contained` | One feature's representative point lies inside the other's polygon | Faculty points inside the UGM campus | 191 |
| `same_name` | Same normalized name and distance ≤ **500 m** | 11 buildings of Pasar Rogobangsan, Tugu station platforms | 424 |
| `transit` | Both transit and distance ≤ **20 m** | One stop drawn as `bus_stop` + `stop_position` + `platform` | 318 |

Links chain (A–B and B–C ⇒ one site). Same-name groups farther than 500 m stay apart and are logged (e.g. two *Pasar Turi* 36 km apart).
**Multi-category:** features tagged both tourism and transit (*Stasiun Trem Gamplong*, *Eks Halte Mlati*) count as **tourism only**, because they draw visitors, not commuters.

### Counting a polygon in a cell
Points always count. A polygon counts in a cell if **any** holds:
1. it covers **≥ 5 % of the cell** (≥ 12,500 m²)
2. **≥ 50 % of the site** lies in that cell (small buildings)
3. it is the site's **home cell** (largest piece) and **≥ 50 % of the site** lies in published cells

182 sliver links (e.g. a 25 m² corner of RSUP Sardjito inside a UGM cell) are kept in the links table with `counts_for_cell = False`.

### Cell classes
* Classified on the **5 destination categories** only. **Transit is a separate flag** (`has_transit_hub`), because bus stops would make almost every urban cell "mixed".
* `primary_category` is a **display label** (most area, then most sites). Use the `has_` columns for analysis.
* **Baseline candidate:** no destination facility and cell centroid within **2 km** of a facility cell.

---

## 5. Results

| Category | Distinct facilities | Cells | Single-category cells |
| :--- | --: | --: | --: |
| tourism_site | 311 | 233 | 171 |
| traditional_market | 215 | 180 | 132 |
| healthcare_hospital | 118 | 115 | 87 |
| education_campus | 115 | 117 | 80 |
| commercial_mall | 24 | 21 | 11 |
| transit_hub *(flag only)* | 490 | 275 | n/a |

| Cell class | All cells | Pass 90 % coverage (`pass_90_primary_window`) |
| :--- | --: | --: |
| single_category | 481 | 135 |
| mixed_use | 82 | 60 |
| no_selected_facility | 5,152 | 275 |
| ↳ of which baseline candidates | 3,826 | 257 |

Multi-cell sites: UGM 15 cells, UNY 8, UII 6, Gembira Loka 6, Prambanan 5.

---

## 6. For Rafi (Role 3)

**Input:** `data/silver/grid_facilities.parquet` (5,715 × 33), join on `cell_id`:

```python
cells = pd.read_parquet("data/silver/grid_facilities.parquet")
daily = pd.read_parquet("data/silver/mobility_daily_clean.parquet").merge(cells, on="cell_id")
```

| Column(s) | Meaning |
| :--- | :--- |
| `n_<category>`, `has_<category>` | Distinct counted sites per category, and presence flag (6 categories) |
| `overlap_m2_<category>` | Counted polygon area of that category in the cell |
| `n_categories`, `cell_class` | Destination categories present; `single_category` / `mixed_use` / `no_selected_facility` |
| `primary_category` | Display label only |
| `site_ids`, `facility_names` | Which sites count in the cell |
| `in_multicell_site` | Cell shares a site with other cells (**cluster these for uncertainty**, e.g. UGM's 15 cells) |
| `dist_to_facility_cell_m`, `is_baseline_candidate` | Distance to nearest facility cell; 2 km baseline flag |

**Suggestions:**
* Main comparison: `cell_class == "single_category"` cells with `pass_90_primary_window`. Sensitivity: add `mixed_use`.
* Baseline: start from `is_baseline_candidate & pass_90_primary_window` (257 cells), then match on coverage and pre-period activity.
* For cluster-robust intervals, group cells that share a `site_id` (explode `site_ids`).

**Other Silver files:**

| File | Grain | Use |
| :--- | :--- | :--- |
| `facilities_dedup.parquet` | site (1,276) | Site geometry, name, category, `member_osm_keys` |
| `cell_facility_links.parquet` | cell × site (1,507) | Overlap m², shares, `counts_for_cell` |
| `osm_facilities_parsed.parquet` | OSM feature (2,357) | Parsed raw features + `in_grid` |
| `facilities_dedup_log.json` / `spatial_join_summary.json` | n/a | Decisions, ambiguous cases, counts |

## 7. For Akhnaf (Role 4)

* Cell polygons: `build_grid_polygons(cells)` from `src.spatial_join` (UTM bounds are in the table).
* Colour the map by `cell_class` or `primary_category`, and use `facility_names` for tooltips.
* Site outlines: `facilities_dedup.parquet` (EPSG:32749, `.to_crs("EPSG:4326")` for Folium).
* The Folium map in `notebooks/role2_playground.ipynb` §5 is a working template.

---

## 8. Known Limits

* **Current OSM snapshot** (historical query timed out in Role 1). No study facility has a `start_date` ≥ 2022.
* **Large tourism polygons** (e.g. Ratu Boko area) absorb attractions drawn inside them, so counts are conservative.
* **Plaza Malioboro** and **Malioboro Mall** are kept as two malls (manually checked: different owners and entrances).
* **Baseline is distance-only** at this stage.
* **Association, not causation:** a device in a campus cell did not necessarily visit the campus.

Questions about Role 2 → ping **Nalen**.
