# Role 4 visualization handoff

Role 4 renders the outputs of the merged Silver and Gold pipeline. Run these commands from the repository root after creating those tables using the README quickstart.

```sh
python -m src.visualize
python -m src.visualize --period 2022_Feb_P1
```

The CLI writes the interactive HTML and three PNGs to `figures/`. The default period is December 2021. The optional period sets the initial map layer and the heatmap period. The committed map opens on February 1–15, 2022, and the committed heatmap shows December 2021. Use `notebooks/visuals.ipynb` to regenerate and explore all four outputs against current local data. For a GitHub download, open the standalone HTML locally in a browser.

## Reading the outputs

| Output | Upstream inputs | Interpretation |
| --- | --- | --- |
| Interactive 500 m map | Gold `cell_metrics` and Silver `grid_facilities`, `facilities_dedup`, `mobility_daily_clean`, `cell_coverage_audit` | A ratio of 1.30 means the cell's relative weekday share is 30% higher than its weekend share. Grey indicates an unavailable ratio. Weekday and weekend coverage show the fraction of eligible days with published values. |
| Weekday/weekend ratio | Gold `category_summary` and `mixed_use_sensitivity` | Compare facility categories within a period. Bars extend from parity at 1.0. Intervals come from the site-cluster bootstrap. Diamonds show the single-category sensitivity estimate when available. |
| Nataru time series | Gold `event_window` and Silver `daily_coverage_summary` | A value of 1.0 equals the matched weekday baseline within the same sampling period. January 1 is a sampling break and its estimate is withheld. The lower panel shows publication coverage. |
| Kapanewon diurnal heatmap | Gold `kapanewon_hourly_profile` | Read the hours in WIB. The weekday and weekend panels share a scale for each metric. Pings per device measure reporting intensity. |

For February 1–15, 2022, 1,628 of 5,715 grid cells have a ratio. Of these, 829 are at least 1.05, 498 are below 0.95, and 301 are within the near-parity band from 0.95 to below 1.05. These counts describe cells with comparable data. Device presence is an observational measure and facilities are mapped associations.

## Sources and offline assets

JogjaPulse supplies device observations. Facility and landmark geometry is from OpenStreetMap contributors under the ODbL. City and regency boundaries are from [geoBoundaries Indonesia ADM2](https://www.geoboundaries.org/api/current/gbOpen/IDN/ADM2/) under CC BY 3.0 IGO and credited to Statistics Indonesia, WFP and OCHA ROAP. The HTML embeds Leaflet under the license in `src/assets/leaflet/LICENSE`. Detailed road geometry is unavailable in this export.

The standalone Colab notebooks embed a snapshot of the upstream summary tables. The repository CLI uses the current generated local tables. The raw JogjaPulse files and generated Silver and Gold tables are excluded from the commit.
