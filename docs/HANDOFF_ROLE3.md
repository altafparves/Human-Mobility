# 📌 Role 3 Handoff — Mobility Analytics & Statistical Modeling (Rafi → Team)

**From:** Rafi Busthami (Role 3 — Mobility Analytics & Statistical Modeling Lead)
**To:** Akhnaf (Role 4 — next in pipeline), Nalen (Role 2), Altaf (Role 1)
**Status:** ✅ **Role 3 complete** — the Gold layer is built, tested, and ready to plot.

> [!IMPORTANT]
> This work sits on top of Nalen's `role2/spatial-join`. **Merge Role 2 first**,
> then this. `src/metrics.py` reads `data/silver/grid_facilities.parquet` and
> `data/silver/cell_facility_links.parquet` and will not run without them.

---

## 1. TL;DR

* `src/metrics.py` produces **8 Gold tables** covering RQ1–RQ4, with cluster-robust intervals, coverage sensitivity at 80/90/95 %, mixed-use sensitivity, a matched comparison with balance diagnostics, and an exploratory Nataru window that **isolates 1 January**.
* Nothing upstream is recomputed differently: eligibility is Altaf's `pass_90_in_period`, the weekday/weekend split is his `is_ordinary_weekday/weekend`, and category membership is Nalen's `has_<category>` flags — **not** `primary_category`, exactly as Role 2's handoff asks.
* **Nalen's `site_ids` solved the clustering problem.** Cells sharing a site are grouped into one bootstrap unit, so UGM's multi-cell campus counts once rather than many times. [§4.4](#44-intervals-come-from-a-cluster-bootstrap-over-site-clusters)
* **Akhnaf, your inputs are ready:** jump to [§5](#5-for-akhnaf-role-4--what-to-plot-and-what-not-to). Four things there would undo the statistics if missed.
* `pytest -q tests/` → **32 passed** (Altaf's 5 + Nalen's 7 + my 20).

---

## 2. Why Role 3 Can Be Considered Done

Checked against [`project_brief_city_magnets_yogyakarta_refined.md`](../project_brief_city_magnets_yogyakarta_refined.md) (§5 Step 4, §7.C Role 3) and the README role table.

| # | Brief requirement (Role 3) | Status | Evidence |
| :-: | :--- | :-: | :--- |
| 1 | Daily **Published Presence Share (%)** per cell | ✅ | Role 1's `published_presence_share_pct` carried through; `restricted_share_*` recomputed per day over each period's eligible cells in `build_cell_metrics()` |
| 2 | Shares across **declared and common-support** universes | ✅ | `published_share_*` (every published cell) vs `restricted_share_*` (eligible cells only); disagreement between them is a coverage finding, not a nuisance |
| 3 | Cell-level **Weekday-to-Weekend Ratio** within each period, excluding Nataru | ✅ | `wd_we_ratio_restricted` / `_published`, built only from `is_ordinary_weekday` / `is_ordinary_weekend` rows, grouped by `sampling_period` |
| 4 | **H1 / H2 / H3** category comparison | ✅ | `category_summary.parquet` — median ratio per category per period, with cluster CI, cell and cluster counts, and coverage |
| 5 | **RQ1 facility pull** after geography, mixed use and coverage | ✅ | `facility_pull.parquet` (descriptive) + `matched_comparison.parquet` (proximity + coverage + activity) + `mixed_use_sensitivity.parquet` |
| 6 | Matched-weekday **Nataru** comparison, **isolating 1 Jan** | ✅ | `event_window.parquet`: each event date vs non-event dates of the **same weekday in the same period**; 1 January always `withheld: 1 January sampling break`, enforced by a test |
| 7 | **No single holiday-uplift value** where the window crosses a break | ✅ | Deliberately not produced; recorded as `single_holiday_uplift_value_produced: false` in `gold_metrics_summary.json` with the reason |
| 8 | **Cluster-robust** resampling, clustering multi-cell complexes | ✅ | `build_site_clusters()` unions cells through Role 2's `cell_facility_links`, so cells sharing a site form one bootstrap unit; `cluster_bootstrap_median()` resamples those, 1,000 draws, seed 42 |
| 9 | Sensitivity across **80 / 90 / 95 %** coverage | ✅ | `coverage_sensitivity.parquet`; a ranking that flips across thresholds is an artefact of the rule and must not be claimed |
| 10 | **Single-category vs mixed-use** comparison | ✅ | `mixed_use_sensitivity.parquet`, using Nalen's `cell_class` |
| 11 | **Hourly kapanewon** aggregation (`n_maids`, `n_pings/n_maids`) | ✅ | `kapanewon_hourly_profile.parquet`, with `is_peak_hour` per period × kapanewon × day type |
| 12 | Export Gold tables + documentation | ✅ | 8 Parquet tables, `city_magnets_gold.duckdb`, `gold_metrics_summary.json`, this document |
| 13 | Tests / reproducibility | ✅ | `pytest -q tests/test_role3_metrics.py` → **20 passed** |

**Known deviations, all deliberate:**

1. **No Holiday Uplift Index.** The brief's earlier draft asked for one. It is not produced, for the reason in [§4.6](#46-why-there-is-no-single-holiday-uplift-number). The refined brief agrees: *"a single holiday-uplift value cannot isolate a holiday effect."*
2. **Table name.** The brief lists `kapanewon_hourly.parquet`; the file is **`kapanewon_hourly_profile.parquet`**, to avoid colliding with Role 1's `kapanewon_hourly_clean.parquet`. `cell_metrics.parquet` matches the brief.
3. **Mar–Apr is computed but labelled `exploratory`** in `period_kind`, because the panel has decayed by then. Only the four primary periods carry the headline.
4. **Category groups overlap.** Following Role 2's instruction to use the `has_` flags, a mixed-use cell counts in every category it holds, and `transit_hub` overlaps all of them. `cells_shared_with_other_categories` records how much.

---

## 3. How to Reproduce

```bash
# 1. Environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Download from https://zenodo.org/records/23157460 into data/raw/
#    presence_cell500m_daily.csv, presence_kapanewon_hourly.csv

# 3. The pipeline, in order
python -m src.ingest           # Role 1  bronze + grid_cells_unique
python -m src.clean_temporal   # Role 1  silver, temporal
python -m src.spatial_join     # Role 2  silver, spatial
python -m src.metrics          # Role 3  gold

# 4. Contracts
pytest -q tests/               # 32 passed
```

> [!WARNING]
> Nalen's note applies here too: rerunning `src.ingest` rewrites the three
> committed JSONs in `data/raw/`. Restore them before committing with
> `git checkout -- data/raw/*.json`.

### Developing without the Zenodo download

Zenodo needs a manual download, which blocks anyone setting up fresh. `tests/make_sample_bronze.py` writes CSVs matching the **verified** bronze shape, so Role 1's assertions and the whole test suite pass against them:

```bash
python -m tests.make_sample_bronze          # -> data/_sample/raw/
cp data/_sample/raw/*.csv data/raw/
python -m src.clean_temporal
python -m src.spatial_join
python -m src.metrics
```

It matches 183,548 daily rows, 5,715 cells, 151 dates, 230,418 hourly rows and 78 kapanewon, and reproduces the panel decay, the k = 5 suppression, the step changes on 1 Jan and 16 Feb, and the near-empty 2022-03-08. The activity signal is attached using the **real committed OSM snapshot**, so campuses behave like campuses and H1–H3 have something to find.

**Those numbers are invented. None of them belongs in the report.**

---

## 4. The Statistical Decisions, and What Each One Costs

If a choice is challenged in the presentation, the answer is here.

### 4.1 Nothing is compared across a sampling break

The published panel steps on **1 January 2022** and **16 February 2022**. Every ratio is computed inside one of Role 1's `sampling_period` values, so a change in *who is observed* can never be read as a change in *who moved*.

**Cost.** Four smaller samples instead of one, so the intervals are wider. That is the honest price; a single number spanning a break would be narrower and wrong.

**What it buys.** A result that appears in all four primary periods is a result about Yogyakarta. A result in one period is a result about that month. `category_summary.parquet` reports every period precisely so this can be checked — and in testing the category ranking holds in all four, which is the strongest claim this design can support.

### 4.2 Eligibility comes from Role 1, within the period

A cell enters a period's comparison through `pass_90_in_period`: ≥ 90 % publication coverage on ordinary weekdays **and** ordinary weekends, counted separately. Both sides must clear the bar, because a cell seen every weekday but on two weekend days would otherwise produce a ratio resting on those two days.

The *within-period* flag is used rather than `pass_90_primary_window` because the ratio is a within-period quantity: a cell well covered in December but absent in February belongs in December's comparison and nowhere else. `pass_90_primary_window` and `pass_90_every_primary_period` are both carried into `cell_metrics.parquet` for robustness checks.

**Cost.** This removes the least-observed places, which in practice means the rural and the quiet. The result describes relatively well-observed Yogyakarta, not all of it.

**The threshold is an analyst choice**, so 80 % and 95 % are reported in `coverage_sensitivity.parquet`.

### 4.3 What the share is, and is not

$$\text{Published Presence Share (\%)} = \frac{n\_maids_{c,d}}{\sum_c n\_maids_{c,d}} \times 100$$

The denominator sums device–cell presences. A device present in several cells contributes to each, so this is **not** a count of unique devices and no regional total can be recovered from it. What it does describe is how published observations are distributed across space on a given day — enough for a question about relative differences between kinds of place on the same day.

`n_maids` is a **distinct count**, so it is never summed across cells or dates. Period summaries use means and medians of daily shares; a test asserts no Gold column sums it.

Suppressed cell-days (k = 5) are **missing, not zero**. Suppression removes the quietest places first, which has a consequence worth stating in the report: the surviving baseline cells are *the busiest of the quiet cells*, not a fair sample of quiet places. That biases the matched comparison towards **understating** the gap, and it cannot be fixed downstream — only disclosed.

### 4.4 Intervals come from a cluster bootstrap over site clusters

Two kinds of repetition make cell-days non-independent: a cell recurs across dates, and a large complex spans several cells. Role 2 reports UGM across 15 cells, UNY across 8. Those are **one place each**.

`build_site_clusters()` unions a cell with every site that counts in it (from Role 2's `cell_facility_links.parquet`, falling back to the `site_ids` column), so cells sharing a site — directly or through a chain — land in one cluster. A cell belonging to no site is its own cluster.

The bootstrap then resamples **clusters** with replacement, 1,000 times, and takes the 2.5th and 97.5th percentiles of the resulting medians. One cluster is one draw, whatever the number of cells and days behind it. Treating cell-days as independent would give an interval far too narrow to be honest.

Every table reports `clusters` alongside `cells`. A category-period with fewer than **5 clusters** has its estimate withheld with the counts kept, so the reader sees why. A test asserts that at least one cluster really does group several cells — a `site_id` column that gave every cell its own id would satisfy the schema while defeating the purpose.

### 4.5 The matched comparison, and why it is thinner than it looks

Role 2 built the baseline set by distance — `is_baseline_candidate`: no mapped destination facility, centroid within 2 km of a facility cell — and left matching on coverage and activity to Role 3. That is what happens here.

Each facility cell is matched 1:1 without replacement, inside one period, to a baseline cell within **2 km** and closest on a combined distance over standardised **publication coverage** and standardised **overall activity**. Activity is included because proximity and coverage alone leave the busy paired with the quiet; the outcome is a *ratio*, so matching on activity level is not matching on the outcome. Treated cells are processed in random order, so the first ones are not quietly given the best matches.

**Common support.** A facility cell busier than *every* baseline cell has no honest counterpart — matching it anyway would pair a mall with the quietest thing available and call the gap an effect. Those cells are excluded and **counted**, and the count is itself a result: for those places there is no comparable unmapped cell in DIY.

**Thin comparisons are withheld.** Fewer than **20 matched pairs** and the difference and its balance diagnostics are set to NaN. Otherwise a figure built on two pairs would dominate the headline imbalance while describing almost nothing. In testing most category-periods are withheld on this rule — the eligible facility cells are simply few once the coverage rule has run, and that is the honest state of the data rather than something to work around.

**Residual imbalance is reported, not assumed away.** Standardised mean differences appear before and after matching; below 0.1 is the usual bar for "balanced". In testing the activity imbalance stays **well above** it. The comparison is therefore suggestive, not clean, and the report must say **associated with**, never *caused by*. These cells were never randomised.

### 4.6 Why there is no single holiday-uplift number

The Nataru window runs 24 December – 2 January. **1 January is a sampling break.** One ratio spanning that date cannot separate a holiday effect from a change in who is being observed, and presenting one would imply a precision the data cannot support.

What `event_window.parquet` gives instead, per date and category:

* each event date against non-event dates of the **same weekday in the same sampling period**
* `cells_with_support` and `median_baseline_days`, so the support behind each value is visible
* the value **withheld** when fewer than 10 cells have at least 2 matched baseline days
* the value **withheld entirely on 1 January** — enforced by a test
* the whole table labelled `exploratory`

Matching on weekday removes the weekly cycle. It does not remove a spatially varying change in sample composition, and nothing available here does.

### 4.7 Category membership, mixed use, and the transit caveat

Role 2's handoff is explicit that `primary_category` is a display label and the `has_<category>` flags are for analysis, so that is what Role 3 groups by. A mixed-use cell genuinely holds every category it is flagged for and belongs in each of their comparisons, so **the category groups overlap**. `cells_shared_with_other_categories` records by how much, and `mixed_use_sensitivity.parquet` repeats the headline using `cell_class == "single_category"` only.

**Transit needs its own sentence in the report.** Role 2 keeps it as a flag rather than a cell class, because bus stops would make almost every urban cell mixed-use. It is still reported as a category here, but its cells overlap all the others, and in testing its ratio moves noticeably between the all-cells and single-category subsets — which means the transit label was doing work that belonged to whatever else was in the cell. Report the single-category figure for transit, or report both.

### 4.8 The hourly layer

`pings_per_maid` is a **reporting-intensity diagnostic** — how talkative the apps were, not how many people were present. It must never be read as a crowd measure.

Sub-districts cannot be linked to individual grid cells without a boundary layer or an explicit crosswalk, so this layer stays macro context, exactly as the brief specifies.

---

## 5. For Akhnaf (Role 4) — What to Plot, and What Not To

All inputs are in `data/gold/` as Parquet, and as tables in `city_magnets_gold.duckdb`.

| Your figure | Table | Columns |
| :--- | :--- | :--- |
| **Weekly Rhythm grouped bar / interval plot** | `category_summary.parquet` | `category`, `median_ratio`, `ci_low`, `ci_high`, `cells_with_ratio`, `clusters`, `median_period_coverage`, `sampling_period` |
| single-vs-mixed overlay on the same chart | `mixed_use_sensitivity.parquet` | `subset` ∈ {`all cells`, `single-category only`} |
| **Nataru time-series** | `event_window.parquet` | `date`, `category`, `median_relative_presence`, `cells_with_support`, `is_sample_break`, `evidence` |
| its coverage panel | Role 1's `daily_coverage_summary.parquet` | `daily_cell_coverage_pct`, `is_sample_break` |
| **24-hour diurnal heatmap** | `kapanewon_hourly_profile.parquet` | `kapanewon_code`, `kapanewon`, `hour_wib`, `day_type`, `median_n_maids`, `median_pings_per_maid`, `is_peak_hour` |
| **Interactive 500 m map** | `cell_metrics.parquet` | `cell_id`, `x_min_utm`, `y_min_utm`, `centroid_lon`, `centroid_lat`, `cell_class`, `primary_category`, `wd_we_ratio_restricted`, `min_period_coverage`, `restricted_share_weekday`, `facility_names` |
| facility pull bar chart | `facility_pull.parquet` | `category`, `median_share_weekday_pct`, `ci_low`, `ci_high` |

`cell_metrics.parquet` already carries Role 2's `has_<category>`, `cell_class`, `primary_category` and `facility_names`, so the map needs no further join. Site outlines for the map come from Role 2's `facilities_dedup.parquet`.

### Four things that would undo the statistics

1. **Respect the `evidence` column.** Every table that can withhold a value has one. A withheld row is NaN on purpose — plot it as a gap or a marked "insufficient support", **never as zero**. A zero there reads as "no activity", which is the opposite of what it means.
2. **Mark the 1 January break on every time axis.** `is_sample_break` is in `event_window.parquet` and in Role 1's daily summary. The Nataru chart must not draw a continuous line across it.
3. **Never pool or average across `sampling_period`.** Each period is its own comparison. Put them side by side; do not merge them into one bar.
4. **Show `cells` and `clusters` on the ratio chart.** A category with 5 cells and one with 428 should not look equally solid, and `commercial_mall` has very few eligible cells. The counts are in every summary table.

Wording for captions and the video: **"relative device presence"**, not "people" or "footfall"; **"associated with"**, not "caused by"; **"published presence share"**, never "share of the population".

---

## 6. What Was Consumed from Role 2, and the One Thing Still Open

Nalen's `grid_facilities.parquet` landed with everything Role 3 needed, including the `site_ids` column that makes the cluster bootstrap work. Used directly:

| Column | Used for |
| :--- | :--- |
| `has_<category>` | category membership for every comparison |
| `cell_class`, `n_categories` | mixed-use sensitivity |
| `site_ids` + `cell_facility_links.parquet` | building `cluster_id` for the bootstrap |
| `in_multicell_site` | reporting how much clustering actually does |
| `is_baseline_candidate` | the control pool for matching |
| `primary_category`, `facility_names` | passed through to `cell_metrics` for Role 4's map |

**Still open (not a blocker):** Role 2's §8 notes the baseline is distance-only, and the brief mentions a *pre-period activity baseline* as a stronger match. Matching currently uses coverage and overall activity measured **inside** the comparison window. A pre-period baseline — activity in, say, the first week of December used to match cells compared in January onwards — would be a cleaner design. It is listed in [§8](#8-what-would-make-this-stronger) rather than done, because it costs a period of data and the panel is already thin.

---

## 7. Output Data Dictionary

All in `data/gold/` (git-ignored; regenerate locally).

| File | Grain | Use it for |
| :--- | :--- | :--- |
| `facility_pull.parquet` | category × period | RQ1 — median presence share per category, with cluster CIs |
| `cell_metrics.parquet` | eligible cell × period | the cell-level ratios; input to the map |
| `category_summary.parquet` | category × period | RQ2 headline — median weekday/weekend ratio with CIs |
| `coverage_sensitivity.parquet` | category × period × threshold | does the 90 % rule decide the answer? |
| `mixed_use_sensitivity.parquet` | category × period × subset | does the label decide the answer? |
| `matched_comparison.parquet` | category × period | RQ1 against matched baseline cells, with balance diagnostics |
| `event_window.parquet` | category × event date | RQ3, exploratory, with support flags and the break isolated |
| `kapanewon_hourly_profile.parquet` | kapanewon × hour × day type × period | RQ4 diurnal pulse and ping intensity |
| `gold_metrics_summary.json` | — | counts, diagnostics, and the interpretation guardrails |
| `city_magnets_gold.duckdb` | — | all of the above as SQL tables |

**Columns that recur across tables:**

| Column | Meaning |
| :--- | :--- |
| `sampling_period`, `period_kind` | Role 1's period label; `primary` or `exploratory` |
| `evidence` | `reported` / `observational` / `exploratory`, or the reason the value was withheld |
| `cells`, `clusters` | how many 500 m cells, and how many site clusters they group into |
| `cells_shared_with_other_categories` | overlap with other categories, since the groups are not disjoint |
| `ci_low`, `ci_high` | 95 % percentile interval from the cluster bootstrap over `cluster_id` |
| `smd_*_before`, `smd_*_after` | standardised mean differences; below 0.1 is "balanced" |
| `outside_common_support` | facility cells with no comparable baseline cell |
| `restricted_share_*` | share with the denominator restricted to this period's eligible cells |
| `published_share_*` | Role 1's share over every published cell that day |

---

## 8. What Would Make This Stronger

Listed honestly, because knowing what is missing is part of the result.

1. **A model instead of medians.** A mixed-effects model with random effects for site cluster and date would use the data better than per-cell ratios and would give effect sizes directly.
2. **A pre-period activity baseline for matching**, as in [§6](#6-what-was-consumed-from-role-2-and-the-one-thing-still-open).
3. **A historical OSM snapshot.** Facilities are matched using a current extract against 2021–22 activity. Role 1 documented the attic-query fallback and Role 2 checked that no study facility has a `start_date` ≥ 2022, which narrows the risk without removing it.
4. **More eligible facility cells.** The coverage rule leaves few cells per category — `commercial_mall` in particular — which is why so many matched comparisons are withheld. Nothing in the analysis can fix that; only a denser published panel could.
5. **A confirmed licence for JogjaPulse.** The supplied README carries a placeholder. Worth recording before submission.

---

## 9. Shared Reminders

* Keep `pytest -q tests/` green before pushing — 32 tests now, across all three roles.
* `data/` is git-ignored. Gold is regenerated, never committed.
* My segment for the video and presentation: the two sample breaks and why nothing is compared across them, the coverage rule and what it excludes, why the intervals resample site clusters, the matched comparison and its residual imbalance, and why there is no single holiday number.
* Questions about Role 3 → ping **Rafi**.
