# 📌 Role 4 Handoff — Geospatial Visualization & Interactive Map (Akhnaf & Team)

**From:** Akhnaf (Role 4 — Geospatial Visualization & Interactive Map Lead, completed with Team support)  
**To:** Altaf (Role 1), Nalen (Role 2), Rafi Busthami (Role 3) — Shared Presentation & 5-Minute eLOK Video Team  
**Status:** ✅ **Role 4 complete** — the Serve & Visual Analytics layer (`src/visualize.py`, `figures/`, `notebooks/`, and `tests/test_role4_visualize.py`) is built, verified against real Gold & Silver outputs, and ready for the live presentation and 5-minute eLOK video.

---

## 1. TL;DR

* `src/visualize.py` renders **5 core visual deliverables** directly from the merged Silver (`data/silver/`) and Gold (`data/gold/`) tables into `figures/`:
  1. **`figures/city_magnets_map.html`** — Standalone offline-capable interactive $500\text{ m} \times 500\text{ m}$ spatial map (embedded Leaflet JS/CSS + DIY ADM2 regency boundaries + optional online CARTO Positron street basemap, multi-period ratio layers, weekday/weekend publication coverage switcher, deduplicated facility footprints, all 9 audited DIY landmarks, and a click-to-inspect cell details side panel).
  2. **`figures/facility_pull.png`** — **RQ1 Facility Pull** 4-period horizontal bar & interval chart showing median weekday presence share (%), 95% site-cluster bootstrap CIs, weekend median share markers, and the unmapped baseline candidate reference line.
  3. **`figures/weekday_weekend_ratio.png`** — **RQ2 Weekly Rhythm (H1–H3)** 4-period horizontal bar chart extending from parity ($1.0$), with 95% site-cluster bootstrap CIs, single-category sensitivity diamonds (`mixed_use_sensitivity`), and `Cells / clusters` sample sizes.
  4. **`figures/nataru_timeseries.png`** — **RQ3 Holiday Shockwave** small-multiple relative presence time-series (24 Dec 2021 – 2 Jan 2022) paired with a bottom daily grid publication coverage panel and an explicit **1 January 2022 sampling break** callout (`withheld`).
  5. **`figures/kapanewon_diurnal_heatmap.png`** — **RQ4 Diurnal Pulse** 2×2 shared-scale 24-hour WIB heatmap comparing weekday vs. weekend device presence (`median_n_maids`, with peak-hour markers $\circ$) and reporting intensity (`median_pings_per_maid`) across the 10 busiest well-covered *kapanewon*.
* **All four statistical guardrails from Role 3 (`docs/HANDOFF_ROLE3.md` §5) are enforced in code and verified by unit tests.**
* **Interactive & Colab Notebooks:** `notebooks/visuals.ipynb` (repo walkthrough with saved outputs) plus 4 self-contained Google Colab notebooks (`notebooks/facility_pull.ipynb`, `notebooks/weekday_weekend_ratio.ipynb`, `notebooks/nataru_timeseries.ipynb`, `notebooks/kapanewon_diurnal_heatmap.ipynb`).
* **Contract Tests:** `pytest -q tests/` → **40 passed** (Role 1: 5, Role 2: 7, Role 3: 20, Role 4: 8).

---

## 2. Why Role 4 Can Be Considered Done

Checked against [`project_brief_city_magnets_yogyakarta_refined.md`](../project_brief_city_magnets_yogyakarta_refined.md) (§6 Planned Visualizations, §8.C Role 4) and [`docs/HANDOFF_ROLE3.md`](HANDOFF_ROLE3.md) (§5 *"What to Plot, and What Not To"*):

| # | Brief & Role 3 Handoff Requirement (Role 4) | Status | Evidence |
| :-: | :--- | :-: | :--- |
| 1 | Unified visual design system & colorblind-safe palette across static and interactive outputs | ✅ | `COLORS` & `LABELS` in `src/visualize.py` (Okabe-Ito / Paul Tol palette, unified typography, consistent category ordering) |
| 2 | **Interactive 500 m Spatial Map** colored by facility category and weekday/weekend ratio with coverage & site tooltips | ✅ | `spatial_map()` → `figures/city_magnets_map.html` (5,715 cells, period layer switcher, `Color by` dropdown for ratio / weekday coverage / weekend coverage, persistent side panel on cell click) |
| 3 | Include all **6 Week 1 DIY Audit Landmarks** + regional anchors and deduplicated site geometries on the map | ✅ | `facilities_dedup.parquet` overlay + 9 permanent landmark labels (*UGM, UNY, RSUP Dr. Sardjito, Pakuwon Mall, Plaza Ambarrukmo, Malioboro Mall, Prambanan, Stasiun Wates, RSUD Wonosari*) |
| 4 | **RQ1 Facility Pull Chart** (`facility_pull.parquet`) with cluster CIs and baseline comparison | ✅ | `pull()` → `figures/facility_pull.png` + `notebooks/facility_pull.ipynb` |
| 5 | **RQ2 Weekly Rhythm Chart** (`category_summary.parquet` + `mixed_use_sensitivity.parquet`) with cluster CIs, single-category overlay, and cell/cluster counts | ✅ | `rhythm()` → `figures/weekday_weekend_ratio.png` + `notebooks/weekday_weekend_ratio.ipynb` |
| 6 | **RQ3 Nataru Holiday Time-Series** (`event_window.parquet` + `daily_coverage_summary.parquet`) with bottom coverage panel and 1 Jan sample break isolated | ✅ | `holiday()` → `figures/nataru_timeseries.png` + `notebooks/nataru_timeseries.ipynb` |
| 7 | **RQ4 24-Hour Kapanewon Diurnal Heatmap** (`kapanewon_hourly_profile.parquet`) showing device peaks (`n_maids`) and ping intensity (`n_pings / n_maids`) in WIB | ✅ | `diurnal()` → `figures/kapanewon_diurnal_heatmap.png` + `notebooks/kapanewon_diurnal_heatmap.ipynb` |
| 8 | **Role 3 Statistical Guardrail #1:** Respect `evidence` column; never plot withheld rows as zero | ✅ | Withheld rows render as `NaN` gaps or text callouts (`withheld`), tested in `test_guardrail_withheld_rows_handled_gracefully` |
| 9 | **Role 3 Statistical Guardrail #2:** Mark 1 January break on every time axis; never draw a continuous line across it | ✅ | `series.loc[BREAK] = np.nan` + shaded vertical band (`#f3dfce`) + `"1 Jan break (withheld)"` label in `holiday()` |
| 10 | **Role 3 Statistical Guardrail #3:** Never pool or average across `sampling_period` | ✅ | `pull()` and `rhythm()` plot each `sampling_period` in its own panel; interactive map separates each period into its own layer |
| 11 | **Role 3 Statistical Guardrail #4:** Show `cells` and `clusters` on category comparison charts | ✅ | Every row in `facility_pull.png` and `weekday_weekend_ratio.png` displays `Cells / clusters` (e.g., `72 / 53` for Dec 2021 campuses, `12 / 12` for malls), and `nataru_timeseries.png` titles display supported cell ranges |
| 12 | Executed notebooks & automated contract tests | ✅ | `notebooks/visuals.ipynb` + 4 Colab notebooks executed with saved outputs; `pytest -q tests/test_role4_visualize.py` → **8 passed** (total suite: **40 passed**) |

---

## 3. How to Reproduce

Run these commands from the repository root after generating the Silver and Gold layers (see `README.md` Quickstart):

```bash
# 1. Generate all 5 visual deliverables (default: heatmap=2021_Dec, initial map layer=2022_Feb_P1)
python -m src.visualize

# 2. Optional: set a specific sampling period for both the heatmap and initial map layer
python -m src.visualize --period 2022_Feb_P1

# 3. Optional: customize heatmap period and initial map period independently
python -m src.visualize --period 2021_Dec --map-period 2022_Feb_P1

# 4. Run the full 4-role test suite (40 contract tests)
python -m pytest -q tests/
```

* **Default period choice:** By default, `python -m src.visualize` opens the interactive map on **February 1–15, 2022 (`2022_Feb_P1`)** — the primary period with the broadest spatial coverage (1,628 eligible cells clearing $\ge 90\%$ weekday and weekend coverage) — while rendering the diurnal heatmap for **December 2021 (`2021_Dec`)**. All four primary periods (`2021_Dec`, `2022_Jan`, `2022_Feb_P1`, `2022_Feb_P2`) and the exploratory March–April layer remain selectable inside the interactive map's layer control.

---

## 4. Reading the Outputs & Visual Design Decisions

| Deliverable | File | Upstream Inputs | How to Read & Interpret |
| :--- | :--- | :--- | :--- |
| **Interactive 500 m Spatial Map** | `figures/city_magnets_map.html` | Gold `cell_metrics`; Silver `grid_facilities`, `facilities_dedup`, `mobility_daily_clean`, `cell_coverage_audit` | • **Ratio layers:** A ratio of `1.30` means the cell's ordinary-weekday relative presence share is 30% higher than its ordinary-weekend share (**Teal** $\ge 1.05$ = weekday-leaning; **Cream** $0.95\text{–}<1.05$ = near parity; **Orange** $< 0.95$ = weekend-leaning; **Grey** = insufficient coverage).<br>• **Color by dropdown:** Switch any period layer between *Weekday/weekend ratio*, *Weekday coverage (%)*, and *Weekend coverage (%)*.<br>• **Click a square:** Pins the cell to the bottom-right *Cell details* panel and keeps it selected as you switch across periods. |
| **RQ1 Facility Pull** | `figures/facility_pull.png` | Gold `facility_pull` | • Horizontal bars show median ordinary-weekday restricted presence share (%) per category within each primary period.<br>• Black lines show 95% site-cluster bootstrap confidence intervals; white circles ($\circ$) show median ordinary-weekend share; the vertical dashed line marks the unmapped `baseline_candidate` weekday median. |
| **RQ2 Weekly Rhythm** | `figures/weekday_weekend_ratio.png` | Gold `category_summary`, `mixed_use_sensitivity` | • Bars extend left or right from parity at $1.0$ (dashed line).<br>• Black lines show 95% site-cluster bootstrap intervals (clustering multi-cell complexes such as UGM's 15 cells into a single bootstrap draw).<br>• White diamonds ($\diamond$) show the `single-category only` sensitivity estimate (`cell_class == "single_category"`).<br>• `Cells / clusters` counts appear to the right of every bar. |
| **RQ3 Nataru Holiday Window** | `figures/nataru_timeseries.png` | Gold `event_window`; Silver `daily_coverage_summary` | • Each point compares an event date (24 Dec 2021 – 2 Jan 2022) against non-event dates of the **same weekday within the same sampling period** ($1.0$ = matched weekday baseline).<br>• **1 January 2022** is shaded and withheld (`NaN`) so the upstream sample break is never interpolated as human movement.<br>• The bottom bar chart shows daily grid publication coverage (% of 5,715 cells). |
| **RQ4 Kapanewon Diurnal Heatmap** | `figures/kapanewon_diurnal_heatmap.png` | Gold `kapanewon_hourly_profile` | • Rows show the 10 busiest well-covered *kapanewon* ($\ge 90\%$ hourly coverage); columns show hours $0\text{–}23\text{ WIB}$.<br>• Left panels share a color scale for `median_n_maids` with white circles ($\circ$) marking each district's peak hour.<br>• Right panels share a color scale for `median_pings_per_maid` (reporting-intensity diagnostic). |

---

## 5. Headline Visual Findings for the 5-Minute eLOK Video & Presentation

Use these verified numbers when narrating the charts and map:

1. **Spatial Coverage & Map Context (`city_magnets_map.html`):**
   * In February 1–15, 2022 (`2022_Feb_P1`), **1,628 of 5,715** grid cells ($28.5\%$) clear the $\ge 90\%$ ordinary weekday and weekend publication coverage threshold.
   * Among those 1,628 comparable cells, **829 ($\ge 1.05$)** are weekday-leaning, **498 ($< 0.95$)** are weekend-leaning, and **301 ($0.95\text{–}<1.05$)** sit near parity.
2. **RQ1 — Facility Pull (`facility_pull.png`):**
   * Facility-associated cells consistently attract higher median weekday presence shares than unmapped baseline candidate cells across all 4 primary periods.
   * **Malls** (`commercial_mall`, $12\text{–}20$ cells) and **Campuses** (`education_campus`, $72\text{–}110$ cells across $53\text{–}82$ site clusters) rank at the top of median weekday presence share in every primary period (e.g., Dec 2021: Malls $0.103\%$, Campuses $0.067\%$, Markets $0.066\%$ vs. Baseline candidates $0.054\%$; Feb 1–15: Malls $0.134\%$, Campuses $0.082\%$ vs. Baseline candidates $0.023\%$).
   * As documented by Role 3, 1:1 proximity-coverage-activity matching leaves residual activity imbalance ($\text{SMD up to } 0.57 > 0.10$), so all findings are framed as **observational spatial associations**, never causal effects.
3. **RQ2 — Weekly Rhythm & Hypotheses H1–H3 (`weekday_weekend_ratio.png`):**
   * **H1 (Education — Campuses):** **Supported across all 4 primary periods** and robust across single-category diamonds and $80\% / 90\% / 95\%$ coverage rules. Campus cells lean strongly toward weekdays in **Dec 2021 ($1.291$, 95% CI $[1.206, 1.404]$)**, **Feb 1–15 ($1.152$, CI $[1.127, 1.196]$)**, and **Feb 16–28 ($1.138$, CI $[1.096, 1.216]$)**, while compressing toward parity in **Jan 2022 ($1.022$, CI $[0.965, 1.045]$)** during the inter-semester break.
   * **H2 (Commercial, Markets & Tourism):** Analyzed separately as required by the brief, these categories show distinct seasonal regimes rather than a uniform weekend effect: in Dec 2021 and Feb 1–15, urban mixed activity keeps weekday ratios above $1.0$, whereas in **Jan 2022** Malls ($0.893$, CI $[0.841, 0.945]$; single-category diamond $0.85$), Tourism ($0.964$, CI $[0.929, 0.994]$), and Markets ($0.969$) shift below $1.0$ (weekend-leaning). Moreover, single-category market cells ($\diamond$) sit much closer to parity ($0.98\text{–}1.04$) than mixed-use market cells, showing why separating single-category vs. mixed-use cells matters.
   * **H3 (Healthcare — Hospitals):** Hospital-associated cells ($39\text{–}88$ clusters) exhibit weekday-leaning activity driven by weekday outpatient schedules and urban co-location ($1.290$ in Dec 2021, $1.012$ in Jan 2022, $1.085$ in Feb 1–15, $1.070$ in Feb 16–28), sitting below campuses in February and slightly tighter when isolated to single-category hospital cells ($\diamond$).
4. **RQ3 — Holiday Shockwave (`nataru_timeseries.png`):**
   * Compared against matched non-event weekdays in December 2021, **Tourism** cells rose to **$1.29$ ($+29\%$ above normal Saturday baseline)** on Christmas Day (`2021-12-25`) and **Malls** peaked on `2021-12-26` ($1.29$), followed by a mid-week dip across all categories on `2021-12-29` (Tourism $0.64$, $-36\%$ below normal Wednesday baseline) and recovery by New Year's Eve (`2021-12-31`).
   * On **1 January 2022**, grid publication coverage drops from $27.5\%$ ($1,573$ cells) to $23.9\%$ ($1,364$ cells) and total observed devices step down sharply (`is_sample_break = True`). Isolating and withholding Jan 1 prevents mistaking an upstream panel change for a New Year mobility drop.
5. **RQ4 — Diurnal Pulse (`kapanewon_diurnal_heatmap.png`):**
   * Across the 10 busiest *kapanewon* in December 2021, core urban/campus districts peak around midday on weekdays (**Gamping** at `12:00 WIB`, shifting to `11:00 WIB` on weekends; **Depok** at `13:00 WIB` on both weekdays and weekends).
   * Surrounding commuter sub-districts peak in the evening on weekdays and shift earlier on weekends (**Banguntapan** shifts from `19:00 WIB` on weekdays to `14:00 WIB` on weekends; **Kasihan** holds steady at `20:00 WIB`).
   * The right-hand heatmap (`median_pings_per_maid`) reveals a sharp synchronous dip in reporting intensity around `08:00–10:00 WIB` across urban districts and higher background ping rates ($3\text{–}5$ pings/device) in **Seyegan** and **Pakem** — confirming that ping volume reflects app/SDK reporting behavior rather than crowd size.

---

## 6. Sources, Offline Assets & Licensing

* **Mobility Observations:** JogjaPulse dataset ([Zenodo Record 23157460](https://zenodo.org/records/23157460)).
* **Facility, Landmark & Major Road Geometry (`src/assets/yogyakarta/roads.geojson`):** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors under the Open Database License (ODbL).
* **Administrative Boundaries (`src/assets/yogyakarta/districts.geojson`):** [geoBoundaries Indonesia ADM2](https://www.geoboundaries.org/api/current/gbOpen/IDN/ADM2/) under CC BY 3.0 IGO (Statistics Indonesia / BPS, WFP, and OCHA ROAP).
* **Embedded Map Runtime (`src/assets/leaflet/`):** Leaflet JS & CSS embedded inline for offline execution under the BSD-2-Clause license in `src/assets/leaflet/LICENSE`, paired with an optional online CARTO Positron basemap tile layer.

For presentation priorities and signoff checklist, see the [PM handoff](HANDOFF_ROLE4_PM.md).

