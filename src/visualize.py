"""Build the City Magnets map and three figures from the Silver and Gold tables."""

import argparse
import html
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from branca.element import Element, MacroElement, Template

from .metrics import PRIMARY_PERIODS
from .spatial_join import build_grid_polygons

ROOT = Path(__file__).resolve().parents[1]
COLORS = {
    "education_campus": "#0072B2",
    "healthcare_hospital": "#CC6677",
    "commercial_mall": "#AA4499",
    "traditional_market": "#B57700",
    "tourism_site": "#00896B",
    "transit_hub": "#674EA7",
    "baseline_candidate": "#647482",
    "mixed_use": "#503E35",
    "no_selected_facility": "#CBD2D4",
}
LABELS = {
    "education_campus": "Campuses",
    "healthcare_hospital": "Hospitals",
    "commercial_mall": "Malls",
    "traditional_market": "Markets",
    "tourism_site": "Tourism",
    "transit_hub": "Transit",
    "baseline_candidate": "Baseline candidates",
    "mixed_use": "Mixed use",
    "no_selected_facility": "No selected facility mapped",
}
MISSING = "#d9dfe2"
BREAK = pd.Timestamp("2022-01-01")


def read(layer, name, columns):
    path = ROOT / "data" / layer / (name + ".parquet")
    stage = (
        "src.metrics"
        if layer == "gold"
        else (
            "src.clean_temporal"
            if name
            in {"daily_coverage_summary", "mobility_daily_clean", "cell_coverage_audit"}
            else "src.spatial_join"
        )
    )
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Generate it with python -m {stage}.")
    frame = pd.read_parquet(path)
    missing = set(columns.split()) - set(frame)
    if missing:
        raise ValueError(
            f"{name} is missing columns {sorted(missing)}. Regenerate with {stage}."
        )
    return frame


def gold(name, columns):
    return read("gold", name, columns)


PERIOD_NAMES = {
    "2021_Dec": "December 2021",
    "2022_Jan": "January 2022",
    "2022_Feb_P1": "February 1–15",
    "2022_Feb_P2": "February 16–28",
    "2022_Mar_Apr_Exploratory": "March–April (exploratory)",
}


def heading(fig, title, description):
    fig.suptitle(
        title + "\n" + description,
        x=0.025,
        ha="left",
        fontsize=16,
        color="#163c45",
        fontweight="medium",
    )


def save(fig, path):
    fig.savefig(path, dpi=155, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def rhythm(path):
    table = gold(
        "category_summary",
        "sampling_period category median_ratio ci_low ci_high cells_with_ratio clusters evidence",
    )
    sensitivity = gold(
        "mixed_use_sensitivity", "sampling_period category subset median_ratio evidence"
    )
    periods = [p for p in PRIMARY_PERIODS if p in set(table.sampling_period)] + sorted(
        set(table.sampling_period) - set(PRIMARY_PERIODS)
    )
    cats = [c for c in LABELS if c in set(table.category)]
    fig, axes = plt.subplots(
        (len(periods) + 1) // 2,
        2,
        figsize=(16, 3.8 * ((len(periods) + 1) // 2)),
        layout="constrained",
        squeeze=False,
    )
    for ax, period in zip(axes.flat, periods):
        rows = (
            table[table.sampling_period.eq(period)].set_index("category").reindex(cats)
        )
        overlay = sensitivity[
            (sensitivity.sampling_period == period)
            & (sensitivity.subset == "single-category only")
            & (sensitivity.evidence == "reported")
        ].set_index("category")
        for i, (cat, row) in enumerate(rows.iterrows()):
            if row.evidence == "reported":
                ax.barh(i, row.median_ratio - 1, left=1, color=COLORS[cat], height=0.48)
                ax.plot([row.ci_low, row.ci_high], [i, i], color="#14242b", lw=2.5)
            if cat in overlay.index:
                ax.scatter(
                    overlay.at[cat, "median_ratio"],
                    i,
                    marker="D",
                    s=28,
                    color="white",
                    edgecolor="#182933",
                    zorder=4,
                )
            counts = (
                "no eligible cells"
                if pd.isna(row.cells_with_ratio)
                else f"{int(row.cells_with_ratio):,} / {int(row.clusters):,}"
            )
            ax.text(
                1.02,
                i,
                ("withheld   " if str(row.evidence).startswith("withheld") else "")
                + counts,
                transform=ax.get_yaxis_transform(),
                va="center",
                fontsize=8,
            )
        ax.set_yticks(range(len(cats)), [LABELS[c] for c in cats])
        ax.invert_yaxis()
        ax.axvline(1, color="#52616a", ls="--", lw=1)
        ax.set_title(
            PERIOD_NAMES.get(period, period), loc="left", fontweight="bold", pad=18
        )
        ax.text(1.02, 1.02, "Cells / clusters", transform=ax.transAxes, fontsize=8)
        ax.grid(axis="x", alpha=0.14)
        ax.set_axisbelow(True)
        ax.set_xlabel("Weekday / weekend share")
    bounds = pd.concat([table.ci_low, table.ci_high, sensitivity.median_ratio]).dropna()
    for ax in list(axes.flat)[: len(periods)]:
        ax.set_xlim(min(1, bounds.min()) - 0.05, max(1, bounds.max()) + 0.05)
    for ax in list(axes.flat)[len(periods) :]:
        ax.set_visible(False)
    campus = table[
        (table.category == "education_campus") & (table.evidence == "reported")
    ]
    above = campus.median_ratio.gt(1).sum()
    result = (
        f"Campus cells leaned weekday in {above} of {len(campus)} periods with an estimate."
        if len(campus)
        else "The data did not support a campus comparison."
    )
    heading(
        fig,
        "Weekday and weekend presence by facility",
        "What we built: Bars compare weekday and weekend shares. 1.0 means equal shares.\n"
        "Lines show the range of uncertainty. Diamonds show cells with a single facility category.\n"
        f"What we found: {result}",
    )
    save(fig, path)


def holiday(path):
    event = gold(
        "event_window",
        "date category sampling_period median_relative_presence evidence",
    )
    cov = read(
        "silver", "daily_coverage_summary", "date daily_cell_coverage_pct"
    ).copy()
    cov.index = pd.to_datetime(cov.date)
    dates = pd.date_range("2021-12-24", "2022-01-02")
    cats = [c for c in LABELS if c in set(event.category)]
    rows = (len(cats) + 1) // 2
    fig = plt.figure(figsize=(13, 2.05 * rows + 2.5), layout="constrained")
    layout = fig.add_gridspec(rows + 1, 2, height_ratios=[1] * rows + [0.95])
    usable = event.loc[
        event.evidence.eq("exploratory"), "median_relative_presence"
    ].dropna()
    limits = (min(1, usable.min()) - 0.05, max(1, usable.max()) + 0.05)
    for i, cat in enumerate(cats):
        ax = fig.add_subplot(layout[i // 2, i % 2])
        for _, group in event[event.category.eq(cat)].groupby("sampling_period"):
            y = group.set_index(pd.to_datetime(group.date))
            series = y.median_relative_presence.where(
                y.evidence.eq("exploratory")
            ).reindex(dates)
            series.loc[BREAK] = np.nan
            ax.plot(dates, series, color=COLORS[cat], marker="o", markersize=4, lw=2)
        ax.axhline(1, color="#778b92", ls=":", lw=1)
        ax.axvspan(
            BREAK - pd.Timedelta(hours=8),
            BREAK + pd.Timedelta(hours=8),
            color="#f3dfce",
        )
        ax.set(
            ylim=limits,
            xticks=dates[[0, 4, 8, 9]],
            xticklabels=["24 Dec", "28 Dec", "1 Jan", "2 Jan"],
        )
        ax.set_title(
            LABELS[cat], loc="left", color=COLORS[cat], fontweight="bold", fontsize=12
        )
        ax.spines[["top", "right"]].set_visible(False)
    bottom = fig.add_subplot(layout[-1, :])
    bottom.bar(
        dates, cov.daily_cell_coverage_pct.reindex(dates), color="#43828a", width=0.68
    )
    bottom.set(
        xticks=dates, xticklabels=dates.strftime("%d %b"), ylabel="Grid published (%)"
    )
    bottom.set_title(
        "Daily publication coverage", loc="left", fontsize=12, fontweight="bold"
    )
    tourism = event[
        event.category.eq("tourism_site") & event.evidence.eq("exploratory")
    ]
    tourism = tourism.set_index(pd.to_datetime(tourism.date)).median_relative_presence
    christmas = tourism.get(pd.Timestamp("2021-12-25"), np.nan)
    later = tourism.get(pd.Timestamp("2021-12-29"), np.nan)
    result = "January 1 is skipped because the sample changed."
    if pd.notna(christmas) and pd.notna(later):

        def describe(ratio):
            return f"{abs(ratio - 1):.0%} {'above' if ratio >= 1 else 'below'} normal"

        result = (
            f"Tourism cells were {describe(christmas)} on Dec 25 and "
            f"{describe(later)} on Dec 29.\n" + result
        )
    heading(
        fig,
        "Christmas and New Year in Yogyakarta",
        "What we built: Lines compare each holiday date with the same day of the week outside the holiday.\n"
        "The bottom bars show how much of the map had published data.\n"
        f"What we found: {result}",
    )
    save(fig, path)


def diurnal(path, period):
    data = gold(
        "kapanewon_hourly_profile",
        "sampling_period kapanewon_code kapanewon hour_wib day_type median_n_maids median_pings_per_maid is_peak_hour",
    )
    data = data[data.sampling_period.eq(period)]
    if data.empty:
        raise ValueError(f"No hourly profile for {period}")
    order = (
        data.groupby("kapanewon_code")
        .median_n_maids.median()
        .dropna()
        .sort_values(ascending=False, kind="stable")
        .head(10)
        .index
    )
    names = data.drop_duplicates("kapanewon_code").set_index("kapanewon_code").kapanewon
    fig, axes = plt.subplots(2, 2, figsize=(15, 8), layout="constrained")
    for j, (metric, title) in enumerate(
        [
            ("median_n_maids", "Median observed devices"),
            ("median_pings_per_maid", "Median pings per device"),
        ]
    ):
        grids = [
            data[data.day_type.eq(day)]
            .pivot(index="kapanewon_code", columns="hour_wib", values=metric)
            .reindex(index=order, columns=range(24))
            for day in ("weekday", "weekend")
        ]
        palette = plt.get_cmap(("YlGnBu", "magma")[j]).copy()
        palette.set_bad(MISSING)
        for ax, grid, day in zip(axes[:, j], grids, ("weekday", "weekend")):
            im = ax.imshow(
                grid,
                aspect="auto",
                vmin=0,
                vmax=np.nanmax(np.asarray(grids)),
                cmap=palette,
            )
            ax.set(
                yticks=range(len(order)),
                yticklabels=names.loc[order].str.title(),
                xticks=range(0, 24, 2),
                xlabel="Hour (WIB)",
                title=f"{day.title()}  |  {title}",
            )
            if j == 0:
                for row in data[
                    data.day_type.eq(day)
                    & data.is_peak_hour
                    & data.kapanewon_code.isin(order)
                ].itertuples():
                    ax.plot(
                        row.hour_wib,
                        order.get_loc(row.kapanewon_code),
                        "wo",
                        ms=5,
                        mec="black",
                    )
        fig.colorbar(
            im,
            ax=axes[:, j].tolist(),
            orientation="horizontal",
            shrink=0.8,
            pad=0.06,
            label=title,
        )
    peaks = data[
        data.is_peak_hour
        & data.day_type.eq("weekday")
        & data.kapanewon_code.isin(order)
    ].dropna(subset=["median_n_maids"])
    result = "Weekday peak hours are unavailable."
    if not peaks.empty:
        peak = peaks.loc[peaks.median_n_maids.idxmax()]
        result = (
            f"{peak.kapanewon.title()} had the highest weekday device count shown, "
            f"peaking at {int(peak.hour_wib):02d}:00 WIB."
        )
    heading(
        fig,
        f"Hourly rhythms across ten kapanewon  |  {PERIOD_NAMES.get(period, period)}",
        "What we built: The left shows devices by hour. The right shows how often they reported.\n"
        "Circles mark the busiest hour. Gray means data is missing.\n"
        f"What we found: {result}",
    )
    save(fig, path)


def spatial_map(path, period):
    grid = read(
        "silver",
        "grid_facilities",
        "cell_id x_min_utm y_min_utm x_max_utm y_max_utm primary_category cell_class facility_names has_transit_hub",
    )
    cells = build_grid_polygons(grid).to_crs(4326)
    values = gold(
        "cell_metrics",
        "cell_id sampling_period wd_we_ratio_restricted min_period_coverage restricted_share_weekday",
    )
    daily = read(
        "silver",
        "mobility_daily_clean",
        "cell_id sampling_period published_presence_share_pct",
    )
    medians = daily.groupby(
        ["sampling_period", "cell_id"]
    ).published_presence_share_pct.median()
    audit = read(
        "silver",
        "cell_coverage_audit",
        "period cell_id ord_wd_coverage ord_we_coverage",
    )
    coverage = audit.set_index(["period", "cell_id"])[
        ["ord_wd_coverage", "ord_we_coverage"]
    ].min(axis=1)
    m = folium.Map(
        location=[-7.82, 110.4],
        zoom_start=11,
        control_scale=True,
        prefer_canvas=True,
        tiles=None,
    )
    # Embed Leaflet so the exported file can open directly from disk.
    m.default_js = []
    m.default_css = []
    assets = Path(__file__).parent / "assets" / "leaflet"
    license_text = (assets / "LICENSE").read_text(encoding="utf-8")
    leaflet = (assets / "leaflet.js").read_text(encoding="utf-8")
    styles = (assets / "leaflet.css").read_text(encoding="utf-8")
    header = m.get_root().header
    header.add_child(Element(f"<script>/* {license_text} */\n{leaflet}</script>"))
    header.add_child(
        Element(
            f"<style>{styles}\n.leaflet-container {{ background: #f4f2eb; }}</style>"
        )
    )
    context = assets.parent / "yogyakarta"
    for filename, label, style in [
        (
            "districts.geojson",
            "City and regency boundaries",
            {
                "color": "#526c72",
                "weight": 1.5,
                "fillColor": "#d9e2d7",
                "fillOpacity": 0.33,
            },
        ),
        (
            "roads.geojson",
            "Major roads",
            {"color": "#957a57", "weight": 1.25, "opacity": 0.75},
        ),
    ]:
        source = context / filename
        if source.exists():
            folium.GeoJson(
                json.loads(source.read_text(encoding="utf-8")),
                name=label,
                style_function=lambda _, style=style: style,
                interactive=False,
            ).add_to(m)
    cells["Facility class"] = cells.primary_category.fillna("no_selected_facility")
    cells.loc[cells.cell_class.eq("mixed_use"), "Facility class"] = "mixed_use"
    cells.loc[
        cells.primary_category.isna() & cells.has_transit_hub, "Facility class"
    ] = "transit_hub"
    cells["Facility class"] = cells["Facility class"].map(LABELS)
    cells["Sites"] = cells.facility_names.map(
        lambda x: (
            html.escape(", ".join(x)) if x is not None and len(x) else "None mapped"
        )
    )
    cols = ["cell_id", "Facility class", "Sites", "geometry"]
    base = cells[cols].copy()
    layercolors = {LABELS[k]: v for k, v in COLORS.items()}

    def add(frame, name, field, shown):
        return folium.GeoJson(
            frame,
            name=name,
            overlay=False,
            show=shown,
            style_function=lambda f: {
                "fillColor": f["properties"]["shade"],
                "color": "#5f6870",
                "weight": 0.35,
                "fillOpacity": 0.64,
            },
            tooltip=folium.GeoJsonTooltip(fields=field),
            highlight_function=lambda _: {
                "weight": 2,
                "color": "#153c45",
                "fillOpacity": 0.85,
            },
        ).add_to(m)

    base["shade"] = base["Facility class"].map(layercolors).fillna(MISSING)
    facility_layer = add(
        base,
        "Facility categories",
        cols[:-1],
        period not in set(values.sampling_period),
    )
    bins = [0.8, 0.95, 1.05, 1.25]
    shades = ["#a65316", "#edba76", "#f1eed9", "#88c8c1", "#197a79"]
    summaries = {}
    layers = {}
    for name, period_title in PERIOD_NAMES.items():
        group = values[values.sampling_period.eq(name)]
        if group.empty:
            continue
        view = cells[cols].merge(
            group[
                [
                    "cell_id",
                    "wd_we_ratio_restricted",
                    "min_period_coverage",
                    "restricted_share_weekday",
                    "restricted_share_weekend",
                ]
            ],
            on="cell_id",
            how="left",
            validate="one_to_one",
        )
        view["median_share"] = view.cell_id.map(medians.loc[name])
        view["min_period_coverage"] = view.cell_id.map(coverage.loc[name])
        for key, title in [
            ("ord_wd_coverage", "Weekday coverage"),
            ("ord_we_coverage", "Weekend coverage"),
        ]:
            coverage_by_cell = audit.loc[audit.period.eq(name)].set_index("cell_id")[
                key
            ]
            view[title] = view.cell_id.map(coverage_by_cell).map(
                lambda x: f"{x:.1%}" if pd.notna(x) else "Unavailable"
            )
        ratio = view.wd_we_ratio_restricted
        label = f"Ratio · {period_title}"
        summaries[label] = (
            f"{ratio.count():,} of {len(view):,} squares have enough data to compare. "
            f"{ratio.ge(1.05).sum():,} had a higher weekday share · "
            f"{ratio.lt(0.95).sum():,} had a higher weekend share · "
            f"{ratio.between(0.95, 1.05, inclusive='left').sum():,} had similar shares."
        )
        view["Reading"] = ratio.map(
            lambda x: (
                "No comparable estimate"
                if pd.isna(x)
                else f"{abs(x - 1):.0%} {'higher' if x >= 1 else 'lower'} share on weekdays"
            )
        )
        view["shade"] = np.where(
            ratio.isna(),
            MISSING,
            np.array(shades)[np.searchsorted(bins, ratio, side="right")],
        )
        for key, field_label, fmt in [
            ("wd_we_ratio_restricted", "Weekday / weekend", ".3f"),
            ("min_period_coverage", "Minimum coverage", ".1%"),
            ("restricted_share_weekday", "Mean restricted weekday share (%)", ".4f"),
            ("restricted_share_weekend", "Mean restricted weekend share (%)", ".4f"),
            ("median_share", "Median daily published share (%)", ".4f"),
        ]:
            view[field_label] = view.pop(key).map(
                lambda x, fmt=fmt: format(x, fmt) if pd.notna(x) else "Unavailable"
            )
        layers[label] = add(
            view,
            label,
            [k for k in view if k not in ("geometry", "shade")],
            name == period,
        ).get_name()
    sites = gpd.read_parquet(ROOT / "data/silver/facilities_dedup.parquet").to_crs(4326)
    folium.GeoJson(
        sites[["geometry"]],
        name="Mapped sites",
        show=False,
        marker=folium.CircleMarker(radius=2),
        style_function=lambda _: {
            "color": "#433931",
            "weight": 1.4,
            "fillOpacity": 0.12,
        },
    ).add_to(m)
    landmarks = folium.FeatureGroup(name="Landmark labels").add_to(m)
    for name in [
        "Universitas Gadjah Mada",
        "Prambanan Temple Compounds",
        "Stasiun Wates",
        "RSUD Wonosari",
    ]:
        match = sites.loc[sites.name.eq(name), "geometry"]
        if not match.empty:
            point = match.iloc[0].representative_point()
            folium.CircleMarker(
                [point.y, point.x],
                radius=3,
                color="#163c45",
                fill=True,
                tooltip=folium.Tooltip(
                    name,
                    permanent=True,
                    direction="left" if name == "Universitas Gadjah Mada" else "right",
                ),
            ).add_to(landmarks)
    folium.LayerControl(collapsed=False).add_to(m)

    def legend(keys, colors):
        return " &nbsp; ".join(
            f'<span style="color:{color}">■</span> {key}'
            for key, color in zip(keys, colors)
        )

    metadata = json.loads(
        (ROOT / "data/raw/osm_ingestion_metadata.json").read_text(encoding="utf-8")
    )
    m.get_root().html.add_child(
        Element(
            '<div style="position:absolute;bottom:32px;left:12px;z-index:950;background:white;border-left:5px solid #28595d;border-radius:5px;box-shadow:0 2px 14px #0002;padding:14px;max-width:min(400px,65vw);font:13px/1.55 Arial"><b>Yogyakarta | Device presence by 500 m cell</b><br><span id="ratio-key">Click a square to compare weekday and weekend shares.<br><b>Teal</b> had a higher weekday share · <b>Orange</b> weekend-leaning<br>'
            + legend(
                [
                    "&lt;0.80",
                    "0.80–&lt;0.95",
                    "0.95–&lt;1.05",
                    "1.05–&lt;1.25",
                    "≥1.25",
                    "Unavailable",
                ],
                shades + [MISSING],
            )
            + "</span><br>"
            + legend(
                [LABELS[c] for c in COLORS if c != "baseline_candidate"],
                [v for c, v in COLORS.items() if c != "baseline_candidate"],
            )
            + "<br>JogjaPulse · Boundaries: geoBoundaries (CC BY 3.0 IGO) · © OpenStreetMap contributors · facility extract "
            + metadata["generated_at_utc"][:10]
            + "</div>"
        )
    )
    m.get_root().html.add_child(
        Element(
            '<div style="position:absolute;top:12px;left:54px;z-index:950;background:white;padding:10px 14px;border-radius:6px;max-width:min(460px,54vw);font:14px Arial;color:#153c45"><strong>Yogyakarta mobility explorer</strong><br><p><b>What we built</b><br>Each square is a 500 m area. Choose a period and click a square.</p><label>Color by <select id="map-metric"><option value="">Weekday / weekend ratio</option><option>Weekday coverage</option><option>Weekend coverage</option></select></label><br><span id="coverage-key"></span><br><b>What we found</b><br><span id="period-summary" aria-live="polite"></span></div>'
        )
    )
    m.get_root().html.add_child(
        Element(
            '<aside id="cell-panel" aria-live="polite" style="position:absolute;right:10px;bottom:28px;z-index:960;background:white;border-radius:8px;box-shadow:0 2px 14px #0003;padding:14px;width:min(270px,38vw);max-height:42vh;overflow:auto;font:13px/1.45 Arial;color:#153c45"><strong>Cell details</strong><p>Click a grid square to compare shares and publication coverage.</p></aside>'
        )
    )
    summary = MacroElement()
    summary._template = Template("""
        {% macro script(this, kwargs) %}
        const map = {{ this._parent.get_name() }};
        const summary = document.getElementById("period-summary");
        const panel = document.getElementById("cell-panel");
        const metric = document.getElementById("map-metric");
        const coverageKey = document.getElementById("coverage-key");
        const ratioKey = document.getElementById("ratio-key");
        const periodSummaries = {{ this.summaries | tojson }};
        const layers = { {% for label, name in this.layers.items() %} {{ label | tojson }}: {{ name }}, {% endfor %} };
        const facility = {{ this.facility }};
        let active = {{ this.initial | tojson }};
        let selected = null;
        const indexes = new Map();
        const coverageColors = ["#e4f1f1", "#a9d6d2", "#559a99", "#13646a"];
        const fields = [
            "Facility class", "Sites", "Reading", "Weekday / weekend",
            "Mean restricted weekday share (%)", "Mean restricted weekend share (%)",
            "Weekday coverage", "Weekend coverage"
        ];
        function refreshPanel() {
            if (!selected) return;
            const layer = indexes.get(active)?.get(selected);
            panel.replaceChildren();
            const title = document.createElement("strong");
            title.textContent = selected + " · " + active.replace("Ratio · ", "");
            panel.append(title);
            const details = document.createElement("dl");
            for (const field of fields) {
                const value = layer?.feature.properties[field];
                if (value === undefined) continue;
                const term = document.createElement("dt");
                term.textContent = field;
                const description = document.createElement("dd");
                const decoder = document.createElement("textarea");
                decoder.innerHTML = String(value);
                description.textContent = decoder.value;
                description.style.margin = "0 0 6px";
                details.append(term, description);
            }
            panel.append(details);
        }
        function refreshColors() {
            const index = indexes.get(active);
            const coverage = metric.value && active in layers;
            metric.disabled = !(active in layers);
            coverageKey.textContent = coverage ? "Publication coverage · pale <50%, medium 50–<80% / 80–<90%, darkest ≥90%, gray unavailable" : "";
            ratioKey.hidden = Boolean(coverage);
            for (const [id, layer] of index || []) {
                const properties = layer.feature.properties;
                const percent = parseFloat(properties[metric.value]);
                let color = properties.shade;
                if (coverage) {
                    color = Number.isNaN(percent) ? "#d9dfe2" :
                        coverageColors[Number(percent >= 50) + Number(percent >= 80) + Number(percent >= 90)];
                }
                layer.setStyle({fillColor: color, color: id === selected ? "#153c45" : "#5f6870", weight: id === selected ? 2.6 : .35});
                if (id === selected) layer.bringToFront();
            }
        }
        function refreshView() {
            summary.textContent = periodSummaries[active] || "Colors show mapped facility classes.";
            refreshColors();
            refreshPanel();
        }
        for (const [name, layer] of Object.entries({...layers, "Facility categories": facility})) {
            const index = new Map();
            layer.eachLayer(cell => {
                const id = cell.feature.properties.cell_id;
                index.set(id, cell);
                cell.on("click", () => {
                    selected = id;
                    refreshColors();
                    refreshPanel();
                });
            });
            indexes.set(name, index);
        }
        map.on("baselayerchange", event => {
            active = event.name;
            refreshView();
        });
        metric.addEventListener("change", refreshColors);
        refreshView();
        {% endmacro %}
    """)
    # Leaflet layer variables are already declared when this script runs.
    summary.layers = layers
    summary.facility = facility_layer.get_name()
    summary.summaries = summaries
    summary.initial = f"Ratio · {PERIOD_NAMES.get(period, period)}"
    summary.add_to(m)
    m.save(str(path))


def build(period=PRIMARY_PERIODS[0], output=None):
    output = Path(output or ROOT / "figures")
    output.mkdir(parents=True, exist_ok=True)
    products = {
        "city_magnets_map.html": lambda p: spatial_map(p, period),
        "weekday_weekend_ratio.png": rhythm,
        "nataru_timeseries.png": holiday,
        "kapanewon_diurnal_heatmap.png": lambda p: diurnal(p, period),
    }
    with (
        TemporaryDirectory(dir=output) as temp,
        plt.rc_context(
            {
                "axes.spines.top": False,
                "axes.spines.right": False,
                "axes.titlecolor": "#224853",
            }
        ),
    ):
        for filename, render in products.items():
            render(Path(temp) / filename)
        for filename in products:
            (Path(temp) / filename).replace(output / filename)
    return [output / name for name in products]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--period",
        default=PRIMARY_PERIODS[0],
        help="Initial map layer and heatmap sampling period",
    )
    for product in build(parser.parse_args().period):
        print(product)
