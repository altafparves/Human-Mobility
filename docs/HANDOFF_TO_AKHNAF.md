# 📌 Handoff Back to Akhnaf — Role 4 Completion & Finalization (`role4/visualization` → `main`)

**From:** Altaf (PM / Role 1)  
**To:** Akhnaf (Role 4 — Geospatial Visualization & Interactive Map Lead)  
**Branches:** `main` & `role4/visualization` (fully synced)  
**Status:** ✅ **Role 4 100% Complete & Merged to `main`** (`40/40 pytest passed`)

---

## 1. TL;DR

To help with your token limits, we stepped in to finish the remaining items in [`docs/HANDOFF_ROLE4_PM.md`](HANDOFF_ROLE4_PM.md) and added the **RQ1 Facility Pull** chart requested by [`docs/HANDOFF_ROLE3.md`](HANDOFF_ROLE3.md) (§5).

Your work remains the core of Role 4 (`src/visualize.py`, `figures/`, and the standalone Colab notebooks). Everything has now been polished, covered by unit tests, re-executed against the real Gold/Silver tables, and merged into `main`.

---

## 2. How to Sync Your Local Repository (`git pull`)

Before opening or editing any files locally, run:

```bash
git fetch --all
git checkout main
git pull origin main

# Or if you prefer staying on the role4/visualization branch:
git checkout role4/visualization
git pull origin role4/visualization
```

*(Both `main` and `role4/visualization` point to the exact same latest commit).*

---

## 3. What Was Completed on Top of Your Work

### A. PM Review Checklist Items ([`docs/HANDOFF_ROLE4_PM.md`](HANDOFF_ROLE4_PM.md))

| Item in `HANDOFF_ROLE4_PM.md` | Previous Gap | What We Implemented | Affected Files |
| :--- | :--- | :--- | :--- |
| **1. Offline Major Roads on Interactive Map** | Major road geometry was unavailable offline, limiting spatial orientation when zoomed in. | Extracted and simplified DIY trunk & primary highways from OpenStreetMap (ODbL, 62 KB) into `src/assets/yogyakarta/roads.geojson` (embedded **offline** inside the HTML), plus added an optional toggleable **Street basemap (online)** layer (CARTO Positron). | [`src/assets/yogyakarta/roads.geojson`](../src/assets/yogyakarta/roads.geojson)<br>[`figures/city_magnets_map.html`](../figures/city_magnets_map.html) |
| **2. Landmark Labels on Map** | Only 4 landmarks were labeled (`UGM`, `Prambanan`, `Stasiun Wates`, `RSUD Wonosari`). | Expanded to **9 landmarks** covering all 6 *Week 1 DIY Audit* landmarks (**UGM, UNY, RSUP Dr. Sardjito, Pakuwon Mall, Plaza Ambarrukmo, Malioboro Mall**) plus 3 regional anchors, with non-overlapping tooltip directions (`top`/`bottom`/`left`/`right`). | [`src/visualize.py`](../src/visualize.py)<br>[`figures/city_magnets_map.html`](../figures/city_magnets_map.html) |
| **3. Weekday vs. Weekend Ratio Chart (RQ2)** | Dense at slide size; needed stronger emphasis on campuses, clarity on the `1.0` parity line, and a legend for uncertainty bars & diamonds. | Highlighted **Campuses** in bold blue on the y-axis across all four period panels, and added a bottom legend box explaining the **Colored Bar** (`All eligible cells ≥90%`), **Black Line** (`95% site-cluster bootstrap CI`), **White Diamond** (`Single-category cells only`), and **Dashed Line** (`1.0 = Equal weekday & weekend share`). | [`figures/weekday_weekend_ratio.png`](../figures/weekday_weekend_ratio.png)<br>[`notebooks/weekday_weekend_ratio.ipynb`](../notebooks/weekday_weekend_ratio.ipynb) |
| **4. Christmas & New Year Time-Series (RQ3)** | Wording *"normal"* needed to be replaced with matched same-weekday baseline wording; Jan 1 break needed a direct visual callout. | Replaced *"normal"* with ***"matched same-weekday baseline"***, added a direct **`1 Jan break (withheld)`** text annotation on the Jan 1 shaded band, displayed `cells_with_support` ranges in each category subplot title (e.g., `Campuses (69–75 cells)`), and placed a *How to read this chart (exploratory RQ3)* legend box in the bottom-right panel slot. | [`figures/nataru_timeseries.png`](../figures/nataru_timeseries.png)<br>[`notebooks/nataru_timeseries.ipynb`](../notebooks/nataru_timeseries.ipynb) |
| **5. Kapanewon Diurnal Heatmap (RQ4)** | Left panels (`Median observed devices`) needed more horizontal room on slides than right panels (`Median pings per device`). | Set `gridspec_kw={"width_ratios": [1.3, 1.0]}` to widen the left panels, labeled `○ = peak hour` in the left panel titles, and explicitly labeled the right panels `(reporting intensity)`. | [`figures/kapanewon_diurnal_heatmap.png`](../figures/kapanewon_diurnal_heatmap.png)<br>[`notebooks/kapanewon_diurnal_heatmap.ipynb`](../notebooks/kapanewon_diurnal_heatmap.ipynb) |

---

### B. Additional Deliverables from [`docs/HANDOFF_ROLE3.md`](HANDOFF_ROLE3.md) & Team Standards

1. **New RQ1 Facility Pull Chart & Colab Notebook (`facility_pull.png` & `facility_pull.ipynb`):**
   * Added `pull()` in [`src/visualize.py`](../src/visualize.py) to plot `data/gold/facility_pull.parquet` (median ordinary-weekday restricted presence share `%` across the 4 primary periods, 95% site-cluster bootstrap CIs, weekend median share markers, and the unmapped `baseline_candidate` reference line).
   * Created a matching standalone Google Colab notebook [`notebooks/facility_pull.ipynb`](../notebooks/facility_pull.ipynb) with an embedded compressed table snapshot.
2. **Executed [`notebooks/visuals.ipynb`](../notebooks/visuals.ipynb) End-to-End:**
   * Previously, code cells in `visuals.ipynb` had empty outputs (`execution_count: null`). It is now fully executed against the real Silver & Gold tables with all 5 visuals and diagnostic tables (`matched_comparison`, `coverage_sensitivity`, `event_window`) saved in the notebook so it renders directly on GitHub.
3. **Automated Contract & Guardrail Tests ([`tests/test_role4_visualize.py`](../tests/test_role4_visualize.py)):**
   * Added **8 unit tests** for Role 4 verifying atomic generation of all 5 outputs, offline Leaflet + boundary + major road embedding, presence of all 9 landmarks, and strict adherence to Role 3's 4 statistical guardrails (withheld rows never plotted as zero, Jan 1 isolated as `NaN`, no pooling across `sampling_period`).
   * Full repository test suite: **`python -m pytest -q tests/` $\rightarrow$ 40 passed, 0 warnings** (Role 1: 5, Role 2: 7, Role 3: 20, Role 4: 8).
4. **Expanded [`docs/HANDOFF_ROLE4.md`](HANDOFF_ROLE4.md) & [`README.md`](../README.md):**
   * Upgraded `HANDOFF_ROLE4.md` to match the format of Roles 1–3 (requirement-by-requirement verification table, visual reading guide, and verified headline numbers for RQ1–RQ4).
   * Marked **`Role 4 status: ✅ Complete`** and added Section 7 (**Key Findings & Visual Deliverables RQ1–RQ4**) with an embedded visual gallery to the front page of `README.md`.

---

## 4. Your Talking Points & Verified Numbers (Role 4 Segment — 5-Minute eLOK Video & Slides)

When presenting the **Visual Analytics & Headline Findings** segment (~1.25 minutes in the 5-minute video and during the live Q&A), use these verified numbers:

1. **Interactive 500 m Spatial Map (`figures/city_magnets_map.html`):**
   * Out of **5,715 grid cells ($500\text{ m} \times 500\text{ m}$)** across DIY, **1,628 cells ($28.5\%$)** clear the $\ge 90\%$ ordinary weekday *and* weekend publication coverage rule in **February 1–15, 2022 (`2022_Feb_P1`)** (compared to 700 in Dec 2021, 705 in Jan 2022, and 407 in Feb 16–28).
   * Among those 1,628 comparable cells: **829 ($\ge 1.05$, teal)** are weekday-leaning, **498 ($< 0.95$, orange)** are weekend-leaning, and **301 ($0.95\text{–}<1.05$, cream)** sit near parity.
2. **RQ1 — Facility Pull (`figures/facility_pull.png`):**
   * Facility-associated cells draw higher median weekday presence shares than unmapped baseline candidate cells across all 4 primary periods.
   * **Malls** ($0.103\%\text{–}0.316\%$) and **Campuses** ($0.067\%\text{–}0.191\%$) rank highest in every period compared against baseline candidates ($0.023\%\text{–}0.119\%$). Because 1:1 matching leaves residual activity imbalance ($\text{SMD up to } 0.57$), we report these as **observational spatial associations**, not causal effects.
3. **RQ2 — Weekly Rhythm & Hypotheses H1–H3 (`figures/weekday_weekend_ratio.png`):**
   * **H1 (Campuses):** **Supported across all 4 primary periods** ($> 1.0$) — **$1.291$** in Dec 2021 (95% CI $[1.206, 1.404]$), **$1.152$** in Feb 1–15 (CI $[1.127, 1.196]$), and **$1.138$** in Feb 16–28 (CI $[1.096, 1.216]$), compressing near parity (**$1.022$**) during the **January 2022** academic break. This holds across single-category diamonds ($\diamond$) and $80\% / 90\% / 95\%$ coverage thresholds.
   * **H2 (Malls, Markets, Tourism):** Evaluated separately, they show distinct seasonal regimes — shifting below $1.0$ (weekend-leaning) in **January 2022** (**Malls $0.893$**, **Tourism $0.964$**, **Markets $0.969$**). For **Markets**, single-category cells ($\diamond$) sit much closer to parity ($0.98\text{–}1.04$) than mixed-use cells.
   * **H3 (Hospitals):** Weekday-leaning ($1.012\text{–}1.290$) reflecting weekday outpatient clinic schedules and urban co-location, sitting below campuses in February.
4. **RQ3 — Holiday Shockwave / Nataru (`figures/nataru_timeseries.png`):**
   * Relative to matched non-event weekdays in Dec 2021, **Tourism** cells rose **$+29\%$ ($1.29\times$)** on Christmas Day (`2021-12-25`) before dipping **$-36\%$ ($0.64\times$)** mid-week on `2021-12-29` and recovering on New Year's Eve.
   * **1 January 2022** is shaded and withheld (`NaN`) because daily grid publication coverage steps down from $27.5\%$ to $23.9\%$ due to an upstream sample break — preventing an observation panel change from being misread as holiday travel.
5. **RQ4 — Diurnal Pulse Across Kapanewon (`figures/kapanewon_diurnal_heatmap.png`):**
   * In December 2021, urban/campus hubs peak around midday on weekdays (**Gamping** at `12:00 WIB` $\rightarrow$ `11:00 WIB` on weekends; **Depok** at `13:00 WIB`).
   * Residential commuter rings peak in the evening on weekdays and shift earlier on weekends (**Banguntapan** from `19:00 WIB` $\rightarrow$ `14:00 WIB`; **Kasihan** steady at `20:00 WIB`).
   * The right panels (`median_pings_per_maid`) serve strictly as a reporting-intensity diagnostic (higher background ping rates in **Seyegan** and **Pakem**, and a synchronous `08:00–10:00 WIB` dip across urban districts) rather than crowd size.

---

## 5. Final Light Checklist for You (No Coding Needed)

- [ ] Run `git pull` on your local machine to get the latest `main`.
- [ ] Open [`figures/city_magnets_map.html`](../figures/city_magnets_map.html) offline in the browser on our presentation laptop (test clicking a 500 m square, switching period layers, toggling *Major roads*, and changing the *Color by* dropdown).
- [ ] Open the 4 standalone notebooks in Google Colab (`facility_pull.ipynb`, `weekday_weekend_ratio.ipynb`, `nataru_timeseries.ipynb`, `kapanewon_diurnal_heatmap.ipynb`) and verify **Runtime → Run all**.
