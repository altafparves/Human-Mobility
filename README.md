# City Magnets: What Draws the Crowds in Yogyakarta?

**Course:** Data Engineering / Human Mobility Group Project — Universitas Gadjah Mada (UGM)  
**Lecturer:** Dr. Widyawan (`widyawan@ugm.ac.id`)  
**Full Project Specification:** [`project_brief_city_magnets_yogyakarta_refined.md`](project_brief_city_magnets_yogyakarta_refined.md)

---

## 1. Project Overview

Using anonymized mobile device presence data (**JogjaPulse**) and **OpenStreetMap (OSM)** spatial features, this project investigates how observed mobile device activity across the Special Region of Yogyakarta (DIY) differs between $500\text{ m} \times 500\text{ m}$ grid cells containing **university campuses, hospitals, shopping malls, traditional markets, tourism sites, and transit stops**, and how those activity rhythms shift across weekdays, weekends, and the Christmas & New Year (*Nataru*) holiday period.

### Core Research Questions
1. **Facility Pull (RQ1):** Which mapped facility categories are associated with higher relative device presence after accounting for geography, mixed land uses, and publication coverage?
2. **Weekly Rhythm (RQ2):** How does the weekday-to-weekend presence ratio differ by facility category (**H1: Education**, **H2: Commercial & Tourism**, **H3: Healthcare**)?
3. **Holiday Shockwave (RQ3):** How does the Christmas & New Year period (24 Dec 2021 – 2 Jan 2022) coincide with changes in relative device presence, and which apparent shifts remain credible after accounting for the **1 January 2022 sample discontinuity**?
4. **Diurnal Pulse (RQ4):** At what hours of the day ($0\text{–}23\text{ WIB}$) do the busiest *kapanewon* (sub-districts) peak in device presence (`n_maids`) and ping intensity (`n_pings / n_maids`)?

---

## 2. Data Sources

| Dataset | Granularity | Description | Source / Access |
| :--- | :--- | :--- | :--- |
| **JogjaPulse — Daily Grid** | $500\text{ m} \times 500\text{ m}$ cell $\times$ Day | Daily distinct mobile device counts (`n_maids`) across 5,715 cells (Dec 2021 – Apr 2022). | [Zenodo Record 23157460](https://zenodo.org/records/23157460) |
| **JogjaPulse — Hourly Sub-District** | *Kapanewon* $\times$ Hour | Hourly device counts (`n_maids`) and ping volume (`n_pings`) across 78 *kapanewon*. | [Zenodo Record 23157460](https://zenodo.org/records/23157460) |
| **OpenStreetMap (OSM)** | Point Nodes & Polygons (`way`/`relation`) | Real-world locations and footprints of urban facilities across DIY (`amenity`, `shop`, `tourism`, `healthcare`, `highway`, `railway`). | [Overpass API](https://overpass-turbo.eu/) / [Geofabrik Java](https://download.geofabrik.de/asia/indonesia/java.html) |

---

## 3. Data Engineering Architecture (Medallion Pipeline)

```text
[JogjaPulse CSVs] ──┐
                    ├──> (1. Bronze / Raw) ──> (2. Silver / Clean & Spatial) ──> (3. Gold / Metrics) ──> [Visuals & Interactive Map]
[OSM Overpass API] ─┘
```

1. **Bronze Layer (`data/raw/`):**
   * Immutable raw CSVs from JogjaPulse and GeoJSON/JSON extracts from the Overpass API (historical snapshot targeting `2021-12-01T00:00:00Z` + current validation extract).
2. **Silver Layer (`data/silver/`):**
   * **Temporal Cleaning:** Standardized `WIB (UTC+7)` timestamps, anomalous date flagging (`2022-03-08`), sampling period segmentation, and publication coverage filtering ($\ge 90\%$ primary threshold; $80\%$ and $95\%$ sensitivity checks).
   * **Geospatial Engineering:** Reconstructed $500\text{ m} \times 500\text{ m}$ grid polygons in `EPSG:32749` (UTM Zone 49S), deduplicated OSM facilities (merging overlapping point nodes and campus/building polygons), and spatial joins (`gpd.sjoin`) classifying single-category, mixed-use, and matched baseline cells.
3. **Gold Layer (`data/gold/`):**
   * Analytical Parquet tables containing daily **Published Presence Share (%)**, within-period **Weekday-to-Weekend Ratios**, matched-weekday **Nataru Event Comparisons**, cluster-robust uncertainty intervals, and hourly *kapanewon* diurnal profiles.

---

## 4. Repository Structure (Data Engineering Best Practice)

```text
Human-Mobility/
├── configs/
│   └── osm_tags.yaml                  # Pipeline parameters, CRS, date windows & OSM tag taxonomy
├── data/
│   ├── raw/                           # Bronze Layer: Immutable JogjaPulse CSVs & raw OSM GeoJSON (git-ignored)
│   ├── silver/                        # Silver Layer: Cleaned Parquet tables & deduplicated spatial joins (git-ignored)
│   └── gold/                          # Gold Layer: Final aggregated cell metrics & hourly summaries (git-ignored)
├── src/
│   ├── __init__.py
│   ├── ingest.py                      # Role 1: Zenodo verification & Overpass API extraction
│   ├── clean_temporal.py              # Role 1: Calendar grid, coverage audit & temporal cleaning
│   ├── spatial_join.py                # Role 2: EPSG:32749 grid reconstruction, OSM deduplication & spatial join
│   ├── metrics.py                     # Role 3: Presence share, weekday/weekend ratios & statistical tests
│   └── visualize.py                   # Role 4: Interactive Folium/Kepler map & static chart generators
├── notebooks/                         # Exploratory analysis & visualization notebooks (e.g., visuals.ipynb)
├── figures/                           # Exported static charts (.png/.svg) & interactive maps (.html)
├── tests/                             # Data quality & pipeline unit tests
├── project_brief_city_magnets_yogyakarta_refined.md   # Full methodological & technical project brief
├── requirements.txt                   # Python dependencies
└── README.md                          # Project documentation
```

---

## 5. Team Roles & Task Division (4 Members)

Each of the **4 team members** leads a core technical stage of the data engineering pipeline, while **Storytelling, Slide Deck Design, the 5-Minute eLOK Video, and Repository Documentation** are shared equally by the entire team.

### Technical Pipeline Roles

| Role | PIC | Pipeline Stage | Key Responsibilities & Deliverables |
| :--- | :--- | :--- | :--- |
| **Role 1: Data Ingestion & Temporal Cleaning Lead** | **Altaf** | Bronze $\rightarrow$ Silver (Temporal) | • Build `src/ingest.py` to load JogjaPulse CSVs and query OSM Overpass API (`node`/`way`/`relation`).<br>• Conduct Week 1 DIY landmark audit (UGM, UNY, Amplaz, Pakuwon, Sardjito, Malioboro).<br>• Build `src/clean_temporal.py` to standardize `UTC+7` timestamps, flag `2022-03-08`, compute weekday/weekend publication coverage per cell, and apply the $\ge 90\%$ coverage rule. |
| **Role 2: Geospatial Engineering & Facility Deduplication Lead** | **Akhnaf** | Silver $\rightarrow$ Gold (Spatial) | • Build `src/spatial_join.py` to reconstruct $500\text{ m} \times 500\text{ m}$ polygons in `EPSG:32749`.<br>• Map OSM tags (`configs/osm_tags.yaml`) into the 6 core facility categories.<br>• Deduplicate overlapping OSM features (point nodes vs. polygons/multi-cell campuses) and run `gpd.sjoin` to classify single-category, mixed-use, and matched baseline cells. |
| **Role 3: Mobility Analytics & Statistical Modeling Lead** | **Nalen** | Gold (Analytical Metrics) | • Build `src/metrics.py` to compute daily **Published Presence Share (%)** across declared and common-support cells.<br>• Compute cell-level **Weekday-to-Weekend Ratios** (H1–H3) and matched-weekday **Nataru Holiday Comparisons** (explicitly isolating the Jan 1 sample break).<br>• Run cluster-robust resampling/uncertainty intervals, sensitivity checks ($80\%/90\%/95\%$), and hourly *kapanewon* aggregations. |
| **Role 4: Geospatial Visualization & Interactive Map Lead** | **Rafi Busthami** | Serve & Visual Analytics | • Build `src/visualize.py` & `notebooks/visuals.ipynb` with a unified visual theme.<br>• Create the **Interactive 500m Spatial Map** (Folium/Kepler.gl), **Weekday/Weekend Ratio Bar Chart**, **Nataru Time-Series with Coverage Panel**, and **24-Hour Kapanewon Diurnal Heatmap** in `figures/`. |

### Shared Team Responsibilities (All 4 Members)
* **GitHub Documentation & Code Review:** Collaboratively maintain `README.md`, review Pull Requests, and verify end-to-end reproducibility.
* **Storytelling & Methodological Rigor:** Synthesize results for RQ1–RQ4 and clearly communicate dataset limitations ($k=5$ privacy suppression, Jan 1 & Feb 16 sample breaks, mixed-use $500\text{ m}$ cells, and association vs. causation).
* **5-Minute Video Presentation (eLOK UGM — Before Week 13):** Co-write the script, record presenter segments, and edit the final 5-minute video.
* **Live Class Presentation (Weeks 13–14):** Co-design the presentation deck and present together in class.

---

## 6. Quickstart & Setup

### 1. Clone the Repository & Create Environment
```bash
git clone https://github.com/altafparves/Human-Mobility.git
cd Human-Mobility
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Place Raw JogjaPulse Data
Download `presence_cell500m_daily.csv` and `presence_kapanewon_hourly.csv` from [Zenodo (Record 23157460)](https://zenodo.org/records/23157460) and place them inside `data/raw/`.

### 3. Run the Medallion Pipeline
```bash
# Step 1: Ingest OSM features & verify raw files (Bronze)
python -m src.ingest

# Step 2: Clean temporal coverage & standardize dates (Silver - Temporal)
python -m src.clean_temporal

# Step 3: Reconstruct 500m UTM grid, deduplicate OSM POIs & spatial join (Silver - Spatial)
python -m src.spatial_join

# Step 4: Compute Gold mobility metrics & statistical intervals (Gold)
python -m src.metrics

# Step 5: Generate static figures & interactive HTML map (Serve)
python -m src.visualize
```

---

## 7. License & Attribution
* **Mobility Data:** JogjaPulse dataset via Zenodo ([Record 23157460](https://zenodo.org/records/23157460)).
* **Spatial Facility Data:** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the Open Database License (ODbL).
