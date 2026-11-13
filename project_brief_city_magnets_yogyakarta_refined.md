# Project Brief: “City Magnets” – What Draws the Crowds in Yogyakarta?

**Course:** Data Engineering / Human Mobility Group Project (UGM)  
**Lecturer:** Pak Widyawan (`widyawan@ugm.ac.id`)  
**Target Deadlines:**  
* **Before Week 13:** Submit 5-minute video to eLOK UGM & push final code to GitHub  
* **Weeks 13–14:** Live class presentation  

---

## 1. One-Line Pitch
Using mobile device presence data and OpenStreetMap (OSM), we examine how observed device activity differs between areas containing campuses, hospitals, malls, markets, tourism sites, and transit stops, and how those differences vary between weekdays, weekends, and the New Year period.

## 2. The Idea in Plain Terms
The **JogjaPulse** dataset tells us *how many* mobile devices were present in each $500\text{ m} \times 500\text{ m}$ grid cell each day, as well as hourly counts per sub-district (*kapanewon*). However, it does not tell us *what* is inside each cell. **OpenStreetMap (OSM)** fills that gap by mapping where universities, malls, hospitals, tourist sites, and bus stops are located. By spatially joining the two datasets, we compare the activity rhythms of facility-associated areas. Measurements refer to all observed devices within each cell, including residents, passersby, and visitors to other facilities.

---

## 3. Research Questions & Hypotheses

### Research Questions
1. **Facility Pull:** Which mapped facility categories are associated with higher relative device presence after accounting for geography, mixed uses, and publication coverage?
2. **Weekly Rhythm:** How does the weekday-to-weekend presence ratio differ by facility type?
3. **Holiday Shockwave:** How does the Christmas & New Year holiday period (late December 2021 to early January 2022) coincide with changes in relative device presence, and which apparent changes remain credible after inspecting the sample discontinuity on 1 January 2022?
4. **Diurnal Pulse (Context):** At what hours of the day do the busiest *kapanewon* peak in device presence and app activity? *(Used for sub-district context only; see Section 8).*

### Hypotheses to Test
* **H1 (Education):** Cells containing campuses have higher relative presence on weekdays than weekends. Their late-December pattern is an exploratory comparison requiring verification of local academic schedules.
* **H2 (Commercial & Tourism):** Mall, market, and tourism cells have distinct weekly and holiday profiles. Analyze these categories separately because markets can follow different operating schedules from malls or tourism sites.
* **H3 (Healthcare):** Hospital-associated cells show smaller weekday-weekend differences than some other categories. This remains a testable hypothesis because outpatient schedules and surrounding land uses may influence the pattern.

---

## 4. Data Sources

| Source | File / Layer | Role in Project | Access / Link |
| :--- | :--- | :--- | :--- |
| **JogjaPulse — daily product** | `presence_cell500m_daily.csv` | Daily distinct device counts per $500\text{ m} \times 500\text{ m}$ grid cell (5,715 cells, 151 days). | [zenodo.org/records/23157460](https://zenodo.org/records/23157460) |
| **JogjaPulse — hourly product** | `presence_kapanewon_hourly.csv` | Hourly device presence (`n_maids`) and ping volume (`n_pings`) across 78 *kapanewon*. | [zenodo.org/records/23157460](https://zenodo.org/records/23157460) |
| **OpenStreetMap (External)** | POI Nodes & Polygons (`amenity`, `shop`, `tourism`, `highway`) | Real-world locations and categories of urban facilities across DIY. | [Overpass Turbo](https://overpass-turbo.eu/) / Overpass API / [Geofabrik Java](https://download.geofabrik.de/asia/indonesia/java.html) |

The project integrates **two independent sources, JogjaPulse and OpenStreetMap**. The two JogjaPulse CSVs are complementary products from one release. BPS data are outside the selected design. Use the supplied README and suppression summaries as supporting documentation. The supplied JogjaPulse README contains a placeholder license statement, so record the confirmed license when it is available. OSM uses ODbL and requires attribution. [OSM attribution and licensing](https://www.openstreetmap.org/copyright)

> **Week 1 Verification Task:** Public Overpass endpoints generally allow queries without an API key, subject to endpoint limits. Record the endpoint, query, extraction time, and requested historical date. During Week 1, the Ingestion Lead must verify DIY coverage by confirming that major landmarks (e.g., UGM, UNY, Ambarrukmo Plaza, Pakuwon Mall, RSUP Dr. Sardjito, Malioboro) are properly captured. Record missing sites, alternate names, category counts, and the number of distinct facilities and grid cells after deduplication. Actual OSM coverage remains unverified.

Use a historical OSM snapshot near the study period, initially 1 December 2021, through an endpoint supporting historical data. A historical snapshot reflects what contributors had mapped by that date. It can omit facilities that already existed. Compare landmark coverage with a current extract and document discrepancies. If only a current extract is usable, label its date and verify major facilities existed during 2021–22. [Historical Overpass queries](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL#Date)

---

## 5. Data Engineering Pipeline (Medallion Architecture)

```
[JogjaPulse CSVs] ──┐
                    ├──> (1. Raw/Bronze) ──> (2. Clean/Silver) ──> (3. Spatial Join & Metrics/Gold) ──> [Visuals & Dashboard]
[OSM Overpass API] ─┘
```

### Step 1: Ingest (Bronze Layer)
* Download the JogjaPulse CSV files and query OSM using a reproducible Python script covering the published mobility grid footprint. The draft extraction box (`lat: -8.21 to -7.54`, `lon: 110.00 to 110.84`) contains the observed cell centroids, but derive the final query extent from transformed grid polygons with a small retrieval buffer. Filter returned facilities against those grid polygons. Retrieve nodes, ways, and relations, including full multipolygon geometry.
* Store all raw data unchanged in `data/raw/`.

### Step 2: Clean & Normalize (Silver Layer)
* Parse dates (`YYYY-MM-DD`) and standardize timestamps to WIB (`UTC+7`).
* **Critical Data Rules from JogjaPulse README:**
  * **Analysis window:** Use December 2021–February 2022 for primary analysis. Treat December, January, 1–15 February, and 16–28 February as separate sampling periods when checking stability. March–April can support an explicitly exploratory extension.
  * **Anomalous date:** Flag `2022-03-08` and exclude it from primary metrics if the analysis is extended. Preserve it in raw data and the coverage audit.
  * **Publication coverage:** Build the expected date calendar per observed cell and retain absent records as missing. Report published days divided by expected days for every comparison group. As an initial analyst-selected criterion, require at least 90% coverage separately for weekdays and weekends within each compared month, with sensitivity checks at 80% and 95%. This restricts inference to relatively well-observed places and may exclude rural areas. Report how many cells and facilities remain.
  * **Relative presence:** Sample size changes sharply, including on 1 January and 16 February. Compute a descriptive share of published device–cell presences:
    $$\text{Published Presence Share (\%)} = \frac{n\_maids_{c, d}}{\sum_{c} n\_maids_{c, d}} \times 100$$
  * The denominator above sums device–cell presences. A device can contribute to multiple cells, so this quantity describes the spatial distribution of published observations. It cannot recover a regional unique-device total or remove changes in sample composition. Compute it over a declared cell universe and repeat the comparison using a common set of well-covered cells. Changes in publication coverage still affect both versions.
  * **Interpretation of counts:** Use means/medians of daily shares for period summaries. Retain raw counts and coverage alongside them for diagnostics. Summing counts across cells or dates does not yield unique people or visits.
* Store separate `day_of_week`, `is_weekend`, and `is_nataru_window` fields. Use 24 Dec 2021–2 Jan 2022 as an analyst-defined event window. Preserve overlapping weekend and event flags. For an ordinary weekday-weekend comparison, exclude the event window and report the remaining dates.
* **Holiday comparison:** Mark 1 January as a sampling discontinuity in every event chart. Compare event dates with non-event dates of the same weekday within the same sampling period where enough observations exist. Report date counts and withhold event ratios when baseline support is inadequate. The combined Nataru window crosses a known sample break, so a single holiday-uplift value cannot isolate a holiday effect. Neither within-day shares nor matched dates eliminate spatially varying sample changes.
* Save cleaned tables in **Parquet** or **DuckDB** format (`data/silver/`).

### Step 3: Geospatial Join (Silver $\rightarrow$ Gold Layer)
* Reconstruct $500\text{ m} \times 500\text{ m}$ grid polygons from `[x_min_utm, x_min_utm + 500) × [y_min_utm, y_min_utm + 500)` in UTM Zone 49S (`EPSG:32749`).
* Reproject OSM points and polygons from WGS84 (`EPSG:4326`) to `EPSG:32749` and run a GeoPandas spatial join (`gpd.sjoin`).
* Define and save a facility tag dictionary before comparing results. Include relevant `amenity`, `healthcare`, `shop`, `tourism`, `public_transport`, `highway`, and railway tags. Query categories explicitly rather than treating every tagged object as a comparable facility.
* Deduplicate multiple representations of the same facility using object identity, geometry, names, and campus or site membership. A node and a polygon can represent the same hospital or mall. Record decisions and ambiguous cases.
* For every cell retain a category-presence vector, unique facility counts, and polygon overlap areas where available. Keep mixed-use cells explicit. Present single-category subsets as a sensitivity analysis. A display label can simplify the map, while the analytical table preserves all categories.
* Label cells without selected mapped facilities as **no selected facility mapped**. Such cells can contain housing, farmland, roads, water, or unmapped amenities. If comparing them with facility-associated cells, match on geographic proximity, coverage, and a separately defined pre-comparison activity baseline where feasible. Describe the resulting comparison as observational and report residual imbalance.

### Step 4: Metrics & Serve (Gold Layer)
* Compute final analytical metrics per cell and facility category:
  * **Median Published Presence Share**, alongside raw-count summaries, cell counts, and publication coverage
  * **Weekday-to-Weekend Ratio:** Compute the ratio of mean weekday share to mean weekend share within each eligible cell and sampling period, using non-event days. Summarize the distribution of cell ratios by category. Report undefined ratios and coverage explicitly.
  * **Event-Period Relative Presence:** Compare event dates with matched non-event weekdays within the same sampling period, subject to baseline support. Show the January discontinuity and retain this analysis as exploratory.
  * **Comparison with Matched Cells** lacking selected mapped facilities, with the matching rule and imbalance diagnostics documented
  * **Uncertainty and sensitivity:** Cell-days repeat places and dates. Use resampling or models that account for repeated dates and spatial grouping, with large sites spanning multiple cells treated as a shared cluster where feasible. Report effect sizes and intervals, vary coverage rules, and compare single-category with mixed-use results. Avoid claiming independent samples for every cell-day.
  * **Hourly context:** Recompute hourly publication coverage directly from the hourly file. Use well-covered sub-districts, compare hours within sampling periods, and retain `n_pings / n_maids` as a reporting-intensity diagnostic. Linking individual grid cells to sub-districts requires a compatible boundary layer or an explicit spatial crosswalk.
* Export lightweight summary tables (`data/gold/`) to power charts and interactive maps, with full documentation in the GitHub `README.md`.

---

## 6. Planned Visualizations & Deliverables

### Key Visuals for the 5-Minute Video
1. **Interactive Spatial Map (Kepler.gl / Folium):** $500\text{ m} \times 500\text{ m}$ facility-rich cells across Yogyakarta colored by facility category or weekday/weekend ratio.
2. **Grouped Bar Chart:** Distributions of cell-level weekday/weekend ratios by facility category, showing uncertainty, number of cells, and coverage. Include matched comparison cells where justified.
3. **Time-Series Line Chart:** Daily published presence shares around the Christmas & New Year period, with a coverage panel, the 1 January sample break, and separate category series. Treat any holiday association as exploratory.
4. **24-Hour Heatmap:** Hour of day ($0\text{–}23\text{ WIB}$) $\times$ key *kapanewon*, showing diurnal peaks and ping intensity ($n\_pings / n\_maids$).

### Course Deliverables
* **GitHub Repository:** Modular Python code, environment file (`requirements.txt`), and a reproducible `README.md`.
* **5-Minute Video Presentation:** Uploaded to `elok.ugm.ac.id` before Week 13.
* **Live Presentation:** Slide deck presented in class during Weeks 13–14.

---

## 7. Known Limitations (To State Openly in Our Presentation)

Highlighting these limitations shows strong data literacy and familiarity with Pak Widyawan's dataset documentation:
* **Sample Bias:** Data originates from smartphones with location-enabled advertising SDKs, representing a tech-active subset rather than a random census sample.
* **Privacy Suppression ($k = 5$):** Cells with fewer than 5 distinct devices are suppressed (`NaN`, not `0`), removing 64.6% of pre-suppression cell-day rows and biasing visibility toward busier urban areas. This percentage uses the publisher’s input-row denominator, rather than all possible cells multiplied by dates. Published-only averages condition on passing the threshold.
* **Cell-Level vs. Building-Level Granularity:** A $500\text{ m} \times 500\text{ m}$ cell containing both a mall and a traditional market cannot be disaggregated; preserve multiple category indicators and show how results change when mixed-use cells are excluded.
* **Large Footprint Sites:** Major campuses (e.g., UGM) and hospital complexes span multiple grid cells. Where OSM provides polygons (`ways`/`relations`), we intersect full polygons rather than single centroid points to identify their spatial overlap. A campus spanning several cells remains one facility, and the cell counts can include the same devices. Report overlap and avoid interpreting their sum as unique campus visitors.
* **Association, Not Causation:** Co-location within a $500\text{ m}$ cell shows spatial correlation between facilities and crowds, not direct proof that every device visited that specific building.
* **Time window and historical context:** Findings describe the December 2021–April 2022 observation period. Sample breaks, holiday schedules, weather, and pandemic-related conditions can influence comparisons. Verify any specific contextual explanation before attributing observed changes to it.
* **Kapanewon Resolution:** Sub-district hourly data is too coarse to isolate individual buildings, so it is strictly used for macro hourly context.

---

## 8. Team Split & Detailed Action Plan (4 Members)

Our team consists of **4 members** (**Altaf**, **Akhnaf**, **Nalen**, and **Rafi Busthami**). Each member leads one dedicated technical pillar across the Medallion Data Engineering Pipeline, while **Storytelling, Slide Deck, Video Production, and Repository Documentation** are shared equally among all 4 members.

### A. 4-Person Technical Role Assignment Summary

| Role | PIC (Member) | Pipeline Stage | Primary Output / Modules |
| :--- | :--- | :--- | :--- |
| **Role 1: Data Ingestion & Temporal Cleaning Lead** | **Altaf** | Bronze $\rightarrow$ Silver (Temporal) | `src/ingest.py`, `src/clean_temporal.py`, `data/raw/`, `data/silver/mobility_clean.parquet` |
| **Role 2: Geospatial Engineering & Facility Deduplication Lead** | **Akhnaf** | Silver $\rightarrow$ Gold (Spatial) | `src/spatial_join.py`, `configs/osm_tags.yaml`, `data/silver/grid_facilities.parquet` |
| **Role 3: Mobility Analytics & Statistical Modeling Lead** | **Nalen** | Gold (Analytical Metrics) | `src/metrics.py`, `data/gold/cell_metrics.parquet`, `data/gold/kapanewon_hourly.parquet` |
| **Role 4: Geospatial Visualization & Dashboard Lead** | **Rafi Busthami** | Serve & Visual Analytics | `src/visualize.py`, `notebooks/visuals.ipynb`, `figures/`, Interactive Map (`figures/city_magnets_map.html`) |

---

### B. Detailed Responsibilities per Technical Role

#### Role 1: Data Ingestion & Temporal Cleaning Lead (Bronze $\rightarrow$ Silver) — **Altaf**
* **Data Acquisition & Reproducible Ingestion (`src/ingest.py`):**
  * Automate downloading/loading of JogjaPulse daily (`presence_cell500m_daily.csv`) and hourly (`presence_kapanewon_hourly.csv`) datasets into `data/raw/`.
  * Build the Overpass API query script (targeting historical snapshot `2021-12-01T00:00:00Z` with fallback comparison to current extract) covering the Yogyakarta mobility grid bounding box plus buffer.
  * Retrieve OSM `node`, `way`, and `relation` geometries (including full multipolygons) and store raw GeoJSON/JSON snapshots with metadata (endpoint URL, timestamp, query parameters).
* **Week 1 Landmark & Coverage Audit:**
  * Verify that major DIY landmarks (UGM, UNY, Ambarrukmo Plaza, Pakuwon Mall, RSUP Dr. Sardjito, Malioboro) are present in the OSM extract; log missing sites or alternate names.
* **Temporal Standardization & Coverage Filtering (`src/clean_temporal.py`):**
  * Parse dates (`YYYY-MM-DD`) and standardize hourly timestamps to `WIB (UTC+7)`.
  * Build the complete expected calendar grid per cell and compute publication coverage ($\text{published days} / \text{expected days}$) separately for weekdays and weekends within each sampling period (Dec 2021, Jan 2022, 1–15 Feb 2022, 16–28 Feb 2022).
  * Flag the anomalous date (`2022-03-08`) and implement the $\ge 90\%$ coverage filter (plus $80\%$ and $95\%$ flags for sensitivity checks).
  * Create temporal calendar flags (`day_of_week`, `is_weekend`, `is_nataru_window` for 24 Dec 2021–2 Jan 2022, and `sampling_period`) and export cleaned tables to `data/silver/`.

#### Role 2: Geospatial Engineering & Facility Deduplication Lead (Silver $\rightarrow$ Gold Spatial) — **Akhnaf**
* **Grid Polygon Reconstruction (`src/spatial_join.py`):**
  * Reconstruct exact $500\text{ m} \times 500\text{ m}$ vector grid polygons from `[x_min_utm, x_min_utm + 500) × [y_min_utm, y_min_utm + 500)` in UTM Zone 49S (`EPSG:32749`).
* **OSM Tag Taxonomy & Geometry Normalization (`configs/osm_tags.yaml`):**
  * Define explicit tag rules mapping OSM keys (`amenity`, `healthcare`, `shop`, `tourism`, `public_transport`, `highway`, `railway`) into target study categories: **Education (Campuses)**, **Healthcare (Hospitals)**, **Commercial (Malls)**, **Traditional Markets**, **Tourism Sites**, and **Transit Stops**.
  * Reproject all OSM points and polygons from WGS84 (`EPSG:4326`) to `EPSG:32749`.
* **Facility Deduplication & Spatial Join:**
  * Deduplicate overlapping OSM representations of the same real-world facility (e.g., a hospital or campus mapped as both a point node and a boundary polygon, or multi-building complexes like UGM) using spatial containment, name matching, and site membership.
  * Execute `gpd.sjoin` / polygon intersection between the $500\text{ m}$ grid cells and deduplicated facilities, computing facility counts, category-presence binary vectors, and polygon overlap areas per cell.
  * Explicitly label **single-category cells**, **mixed-use cells**, and **no selected facility mapped** cells, and construct the spatially matched baseline comparison cell set.

#### Role 3: Mobility Analytics & Statistical Modeling Lead (Gold Layer) — **Nalen**
* **Relative Presence Normalization (`src/metrics.py`):**
  * Compute daily **Published Presence Share (%)** per cell:
    $$\text{Published Presence Share (\%)} = \frac{n\_maids_{c, d}}{\sum_{c} n\_maids_{c, d}} \times 100$$
    across both the full declared cell universe and the common well-covered cell subset to control for sharp sample breaks (Jan 1 and Feb 16).
* **Core Hypothesis Testing & Metrics Computation:**
  * **RQ1 (Facility Pull):** Calculate median/mean published presence shares, raw count diagnostics, and matched baseline comparisons across facility categories.
  * **RQ2 (Weekly Rhythm — H1, H2, H3):** Compute cell-level **Weekday-to-Weekend Ratios** within each sampling period (excluding Nataru dates) and compare category distributions.
  * **RQ3 (Holiday Shockwave):** Perform matched-weekday comparisons for the Christmas & New Year window (24 Dec 2021–2 Jan 2022) while explicitly isolating the 1 January 2022 sample discontinuity.
  * **RQ4 (Diurnal Pulse):** Aggregate hourly *kapanewon* presence (`n_maids`) and reporting intensity (`n_pings / n_maids`) across 0–23 WIB for well-covered sub-districts.
* **Uncertainty & Sensitivity Analysis:**
  * Implement cluster-robust resampling/bootstrapping (clustering multi-cell complexes like UGM/Sardjito and repeated dates) to generate confidence intervals.
  * Run sensitivity comparisons across coverage thresholds ($80\%, 90\%, 95\%$) and **single-category vs. mixed-use** cells, exporting final Gold tables (`data/gold/`).

#### Role 4: Geospatial Visualization & Interactive Dashboard Lead (Serve Layer) — **Rafi Busthami**
* **Visual Design System & Chart Engineering (`src/visualize.py` & `notebooks/visuals.ipynb`):**
  * Establish a unified color palette and publication-grade typography across all static (`matplotlib`/`seaborn`/`plotly`) and interactive outputs.
* **Delivering the 4 Core Analytical Visuals (`figures/`):**
  1. **Interactive Spatial Map (Kepler.gl / Folium):** Render the $500\text{ m} \times 500\text{ m}$ Yogyakarta grid colored by facility category and weekday-to-weekend ratio, with tooltips showing cell coverage, facility names, and median share.
  2. **Weekly Rhythm Grouped Bar / Interval Plot:** Display cell-level weekday/weekend ratio distributions per category with confidence intervals, sample sizes ($n$ cells), and single-vs-mixed-use overlays.
  3. **Nataru Holiday Shockwave Time-Series:** Multi-panel line chart showing daily relative presence share by facility category alongside a bottom panel for daily publication coverage and a vertical callout for the **1 January 2022 sample break**.
  4. **24-Hour Kapanewon Diurnal Heatmap:** Hour-of-day ($0\text{–}23\text{ WIB}$) $\times$ top *kapanewon* heatmap illustrating morning commuter inflows, daytime campus/commercial peaks, and `n_pings / n_maids` reporting intensity.

---

### C. Shared Team Responsibilities (All 4 Members)

Because clear communication, reproducibility, and academic rigor are evaluated across the entire group, **all 4 members collaborate on Storytelling, Documentation, and Presentation**:

| Shared Deliverable | Collective Tasks (Altaf, Akhnaf, Nalen, Rafi Busthami) |
| :--- | :--- |
| **1. GitHub Repository & Documentation** | Maintain clean modular code (`src/`), document pipeline execution instructions and methodology in `README.md`, review Pull Requests, and ensure one-command reproducibility. |
| **2. Storytelling & Limitations Synthesis** | Synthesize findings for H1 (Education), H2 (Commercial/Tourism/Markets), and H3 (Healthcare), while transparently communicating the 7 methodological limitations ($k=5$ privacy suppression, Jan 1 sample break, ecological fallacy in $500\text{ m}$ cells). |
| **3. 5-Minute eLOK Video (Before Week 13)** | Co-write the 5-minute narrative script, record voiceovers/segments (approx. 1–1.25 minutes per member covering their pipeline stage and findings), and edit the final video for submission to `elok.ugm.ac.id`. |
| **4. Live Class Presentation (Weeks 13–14)** | Co-design the final presentation slide deck and present together during the Week 13–14 session, with each member defending their technical domain during Q&A. |

---

## 9. Review Status and Decisions to Verify

This revision retains the City Magnets narrative, the two analytical JogjaPulse CSVs, the OSM integration, and the original course deliverables. It replaces population or pedestrian interpretations with measures of observed device presence. The preferred historical OSM snapshot, primary analysis window, initial coverage threshold, and comparison strategy are methodological proposals to verify during implementation.

The local daily CSV contains 183,548 rows across 5,715 cells. The original extraction box contains its published cell centroids. Historical OSM extraction, facility coverage, deduplication, spatial joins, category rankings, statistical effects, and figures remain to be implemented. The supplied JogjaPulse license text remains a placeholder. The project’s exact course deadlines should be checked against the class schedule.

The core deliverable is an evidence-based answer to which facility-associated areas have different weekly rhythms, how robust those differences are, and how much of the New Year pattern remains ambiguous because of changing observation coverage.
