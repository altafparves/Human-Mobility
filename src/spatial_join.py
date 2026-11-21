"""
Role 2: Geospatial Engineering & Facility Deduplication Lead (Silver -> Gold Spatial)
-------------------------------------------------------------------------------------
Responsibilities:
- Reconstruct 500m x 500m grid polygons in UTM Zone 49S (EPSG:32749).
- Reproject OSM geometries (EPSG:4326 -> EPSG:32749) and apply tag taxonomy from configs/osm_tags.yaml.
- Deduplicate overlapping OSM representations (point nodes vs. campus/hospital polygons).
- Execute spatial join (gpd.sjoin / overlay) and classify single-category, mixed-use, and matched baseline cells.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from src.ingest import classify_element_categories, load_config

ROOT = Path(__file__).resolve().parents[1]
GRID_CELLS_PATH = ROOT / "data" / "silver" / "grid_cells_unique.parquet"
OSM_RAW_PATH = ROOT / "data" / "raw" / "osm_facilities_current.json"
OSM_PARSED_PATH = ROOT / "data" / "silver" / "osm_facilities_parsed.parquet"
FACILITIES_DEDUP_PATH = ROOT / "data" / "silver" / "facilities_dedup.parquet"
DEDUP_LOG_PATH = ROOT / "data" / "silver" / "facilities_dedup_log.json"
CELL_FACILITY_LINKS_PATH = ROOT / "data" / "silver" / "cell_facility_links.parquet"
GRID_FACILITIES_PATH = ROOT / "data" / "silver" / "grid_facilities.parquet"
SUMMARY_PATH = ROOT / "data" / "silver" / "spatial_join_summary.json"

# Tags kept as columns; the full tag dict is kept as JSON for later dedup decisions.
KEY_TAGS = ["name", "operator", "amenity", "healthcare", "shop", "tourism", "historic",
            "highway", "public_transport", "railway", "start_date", "opening_date"]
OUTER_ROLES = {"outer", ""}  # OSM treats an empty multipolygon role as outer


def build_grid_polygons(cells: pd.DataFrame, crs_utm: str = "EPSG:32749") -> gpd.GeoDataFrame:
    """One 500 m square per cell from its UTM bounds."""
    geom = shapely.box(cells["x_min_utm"], cells["y_min_utm"], cells["x_max_utm"], cells["y_max_utm"])
    return gpd.GeoDataFrame(cells.copy(), geometry=geom, crs=crs_utm)


def _coords(geometry: list[dict[str, float]]) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in geometry]


def _relation_geometry(members: list[dict[str, Any]]):
    """Stitch outer/inner member ways into a (multi)polygon; split rings are merged by polygonize."""
    def rings(roles):
        lines = [LineString(_coords(m["geometry"])) for m in members
                 if m["type"] == "way" and m.get("role", "") in roles and len(m.get("geometry", [])) >= 2]
        return unary_union(list(polygonize(unary_union(lines)))) if lines else None

    outer = rings(OUTER_ROLES)
    if outer is None or outer.is_empty:
        return None
    inner = rings({"inner"})  # other roles (e.g. "balcony") are ignored
    return outer.difference(inner) if inner is not None and not inner.is_empty else outer


def element_to_geometry(el: dict[str, Any]):
    """node -> Point, closed way -> Polygon, open way -> LineString, relation -> (Multi)Polygon."""
    if el["type"] == "node":
        return Point(el["lon"], el["lat"])
    if el["type"] == "way":
        pts = _coords(el.get("geometry", []))
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        return LineString(pts) if len(pts) >= 2 else None
    if el["type"] == "relation":
        return _relation_geometry(el.get("members", []))
    return None


def parse_osm_facilities(
    elements: list[dict[str, Any]],
    facility_categories: dict[str, dict[str, list[str]]],
    crs_wgs84: str = "EPSG:4326",
    crs_utm: str = "EPSG:32749",
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]]]:
    """Overpass elements -> categorized GeoDataFrame in UTM, plus a log of dropped elements."""
    rows, dropped = [], []
    for el in elements:
        tags = el.get("tags", {})
        cats = classify_element_categories(tags, facility_categories)
        osm_key = f"{el['type']}/{el['id']}"
        if not cats:
            dropped.append({"osm_key": osm_key, "name": tags.get("name"), "reason": "no study category"})
            continue
        geom = element_to_geometry(el)
        if geom is None or geom.is_empty:
            dropped.append({"osm_key": osm_key, "name": tags.get("name"), "reason": "no usable geometry"})
            continue
        rows.append({
            "osm_key": osm_key, "osm_type": el["type"], "osm_id": el["id"],
            "categories": cats, "n_categories": len(cats),
            **{k: tags.get(k) for k in KEY_TAGS},
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "geometry": shapely.make_valid(geom),
        })
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs_wgs84).to_crs(crs_utm)
    gdf["geom_kind"] = gdf.geom_type.map({"Point": "point", "LineString": "line", "MultiLineString": "line"}).fillna("polygon")
    gdf["area_m2"] = gdf.area.where(gdf["geom_kind"] == "polygon", 0.0)
    return gdf, dropped


def flag_in_grid(facilities: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Mark facilities touching at least one published cell (the bbox carries a 500 m buffer)."""
    hits = gpd.sjoin(facilities[["geometry"]], grid[["geometry"]], predicate="intersects").index.unique()
    return facilities.assign(in_grid=facilities.index.isin(hits))


TRANSIT_MERGE_M = 20   # bus_stop / stop_position / platform drawings of one stop sit within ~7 m
NAME_MERGE_M = 500     # one cell width: catches station platforms, keeps far-apart namesakes apart


def _resolve_categories(cats: list[str]) -> list[str]:
    # Former/heritage stops (Gamplong tram, Eks Halte Mlati) draw visitors, not commuters.
    return ["tourism_site"] if {"tourism_site", "transit_hub"} <= set(cats) else cats


def _components(n: int, edges: list[tuple[int, int]]) -> list[int]:
    """Union-find: connected-component label for each of n nodes."""
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in edges:
        parent[find(a)] = find(b)
    return [find(i) for i in range(n)]


def dedup_facilities(
    facilities: gpd.GeoDataFrame,
    transit_merge_m: float = TRANSIT_MERGE_M,
    name_merge_m: float = NAME_MERGE_M,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Group OSM features of the same category that represent one real-world site.

    Two features of the same category are linked when any rule holds; linked features form one site:
      contained  - representative point lies inside the other feature's polygon (campus faculties, station platforms)
      same_name  - identical normalized name within `name_merge_m` (market buildings, station platforms)
      transit    - both transit and within `transit_merge_m` (one stop drawn as several objects)
    """
    f = facilities.copy()
    f["category"] = f["categories"].map(_resolve_categories)
    f = f.explode("category").reset_index(drop=True)
    f["name_norm"] = f["name"].str.lower().str.strip().str.replace(r"\s+", " ", regex=True)

    edges: dict[tuple[int, int], str] = {}

    pts = f[["category", "geometry"]].copy()
    pts["geometry"] = f.representative_point()
    polys = f.loc[f["geom_kind"] == "polygon", ["category", "geometry"]]
    inside = gpd.sjoin(pts, polys, predicate="within")
    for i, j in inside.loc[(inside["category_left"] == inside["category_right"]) & (inside.index != inside["index_right"]),
                           "index_right"].items():
        edges.setdefault((min(i, j), max(i, j)), "contained")

    near = gpd.sjoin(f[["category", "name_norm", "geom_kind", "geometry"]],
                     f[["category", "name_norm", "geometry"]], predicate="dwithin", distance=name_merge_m)
    near = near[(near["category_left"] == near["category_right"]) & (near.index < near["index_right"])]
    near["dist"] = f.geometry.loc[near.index].distance(f.geometry.loc[near["index_right"]], align=False).to_numpy()
    same_name = near["name_norm_left"].notna() & (near["name_norm_left"] == near["name_norm_right"])
    transit = (near["category_left"] == "transit_hub") & (near["dist"] <= transit_merge_m)
    for (i, row), sn, tr in zip(near.iterrows(), same_name, transit):
        if sn or tr:
            edges.setdefault((i, row["index_right"]), "same_name" if sn else "transit")

    f["site_root"] = _components(len(f), list(edges))
    f["site_id"] = f["category"] + "_" + f.groupby(["category", "site_root"]).ngroup().astype(str).str.zfill(4)

    def summarize(g: gpd.GeoDataFrame) -> pd.Series:
        lead = g.sort_values("area_m2", ascending=False)
        has_poly = bool((g["geom_kind"] == "polygon").any())
        geom = unary_union(list(g.loc[g["geom_kind"] == "polygon", "geometry"] if has_poly else g.geometry))
        return pd.Series({
            "category": g["category"].iloc[0],
            "name": lead["name"].dropna().iloc[0] if lead["name"].notna().any() else None,
            "n_osm_features": len(g),
            "member_osm_keys": g["osm_key"].tolist(),
            "has_polygon": has_poly,
            "area_m2": geom.area,
            "geometry": geom,
        })

    sites = gpd.GeoDataFrame(
        [summarize(g).rename(sid) for sid, g in f.groupby("site_id")], geometry="geometry", crs=f.crs
    ).rename_axis("site_id").reset_index()

    # Namesakes kept apart (same category + name, but > name_merge_m away): logged for manual review.
    split = f.dropna(subset=["name_norm"]).groupby(["category", "name_norm"])["site_id"].nunique()
    ambiguous = [{"category": c, "name": n, "n_sites": int(k)} for (c, n), k in split[split > 1].items()]

    log = {
        "rules": {"transit_merge_m": transit_merge_m, "name_merge_m": name_merge_m,
                  "multi_category": "tourism_site+transit_hub -> tourism_site (heritage/former stops)"},
        "feature_category_rows": len(f),
        "links_by_rule": pd.Series(list(edges.values())).value_counts().to_dict() if edges else {},
        "sites_by_category": sites["category"].value_counts().to_dict(),
        "features_by_category": f["category"].value_counts().to_dict(),
        "ambiguous_same_name_kept_apart": ambiguous,
    }
    return sites, log


def join_sites_to_cells(sites: gpd.GeoDataFrame, grid: gpd.GeoDataFrame, grid_size_m: int = 500) -> pd.DataFrame:
    """Long table: one row per (cell, site) the site physically reaches, with overlap measures.

    Polygon sites -> intersection area per cell (boundary-only touches dropped).
    Point sites   -> the cell containing each point, using the grid's half-open [x, x+500) rule,
                     so a point on a shared edge lands in exactly one cell.
    Line sites    -> cells the line passes through (positive length inside the cell).
    Only published cells (the grid universe) are kept.
    """
    cell_area = grid_size_m ** 2
    cols = ["site_id", "category", "geometry"]
    parts = sites[cols].explode(index_parts=False)
    kind = parts.geom_type.map({"Point": "point", "LineString": "line"}).fillna("polygon")

    poly = gpd.overlay(grid[["cell_id", "geometry"]], parts[kind == "polygon"], how="intersection", keep_geom_type=True)
    poly = poly.assign(link_kind="polygon", overlap_m2=poly.area)

    pts = parts[kind == "point"]
    pts = pd.DataFrame({
        "site_id": pts["site_id"], "category": pts["category"], "link_kind": "point", "overlap_m2": 0.0,
        "cell_id": "E" + (pts.geometry.x // grid_size_m).astype(int).astype(str)
                   + "_N" + (pts.geometry.y // grid_size_m).astype(int).astype(str),
    })

    lines = gpd.overlay(grid[["cell_id", "geometry"]], parts[kind == "line"], how="intersection", keep_geom_type=True)
    lines = lines[lines.length > 0].assign(link_kind="line", overlap_m2=0.0)

    links = pd.concat([pd.DataFrame(d.drop(columns="geometry", errors="ignore")) for d in (poly, pts, lines)])
    links = links[links["cell_id"].isin(grid["cell_id"]) & ((links["link_kind"] != "polygon") | (links["overlap_m2"] > 0))]
    links = (links.groupby(["cell_id", "site_id", "category", "link_kind"], as_index=False)
                  .agg(overlap_m2=("overlap_m2", "sum"), n_parts=("overlap_m2", "size")))

    site_area = sites.set_index("site_id")["area_m2"]
    links["overlap_share_of_cell"] = links["overlap_m2"] / cell_area
    links["overlap_share_of_site"] = (links["overlap_m2"] / links["site_id"].map(site_area)).where(links["link_kind"] == "polygon")
    links["n_cells_for_site"] = links.groupby("site_id")["cell_id"].transform("nunique")
    return links.sort_values(["cell_id", "category", "site_id"]).reset_index(drop=True)


MIN_SHARE_OF_CELL = 0.05   # a polygon must cover >= 5% of a cell (12,500 m2) to label it...
MIN_SHARE_OF_SITE = 0.50   # ...or have most of its own area there (keeps small buildings)
BASELINE_MAX_DIST_M = 2000
TRANSIT = "transit_hub"    # kept as a flag; too common to define single/mixed-use cells


def flag_counting_links(links: pd.DataFrame) -> pd.DataFrame:
    """Points/lines always count; polygons count above the sliver thresholds, or in their home cell.

    Home cell = the cell holding the site's largest piece; it counts when most of the site lies in
    published cells, so a site split into many small pieces is still counted once.
    """
    share = links["overlap_share_of_site"]
    by_site = share.groupby(links["site_id"])
    home = (share == by_site.transform("max")) & (by_site.transform("sum") >= MIN_SHARE_OF_SITE)
    counts = ((links["link_kind"] != "polygon")
              | (links["overlap_share_of_cell"] >= MIN_SHARE_OF_CELL)
              | (share >= MIN_SHARE_OF_SITE)
              | home)
    return links.assign(counts_for_cell=counts)


def build_grid_facilities(
    grid: gpd.GeoDataFrame, links: pd.DataFrame, sites: gpd.GeoDataFrame, categories: list[str]
) -> pd.DataFrame:
    """One row per published cell: facility counts/flags per category, cell class, baseline candidacy."""
    k = links[links["counts_for_cell"]].merge(sites[["site_id", "name"]], on="site_id")
    n = k.pivot_table(index="cell_id", columns="category", values="site_id", aggfunc="nunique", fill_value=0)
    area = k.pivot_table(index="cell_id", columns="category", values="overlap_m2", aggfunc="sum", fill_value=0.0)
    n, area = (t.reindex(index=grid["cell_id"], columns=categories, fill_value=0).fillna(0) for t in (n, area))

    out = grid.drop(columns="geometry").set_index("cell_id")
    for c in categories:
        out[f"n_{c}"] = n[c].astype(int)
        out[f"has_{c}"] = n[c] > 0
        out[f"overlap_m2_{c}"] = area[c]

    dest = [c for c in categories if c != TRANSIT]
    out["n_categories"] = (n[dest] > 0).sum(axis=1)
    out["cell_class"] = np.select([out["n_categories"] == 0, out["n_categories"] == 1],
                                  ["no_selected_facility", "single_category"], "mixed_use")
    # Display label only: the destination category with the most area, then most sites.
    rank = area[dest] * 1e6 + n[dest]
    out["primary_category"] = rank.idxmax(axis=1).where(out["n_categories"] > 0)

    per_cell = k.groupby("cell_id").agg(site_ids=("site_id", lambda s: sorted(set(s))),
                                        facility_names=("name", lambda s: sorted(set(s.dropna()))))
    out = out.join(per_cell)
    for col in ("site_ids", "facility_names"):
        out[col] = out[col].map(lambda v: v if isinstance(v, list) else [])
    multi = set(links.loc[links["n_cells_for_site"] > 1, "site_id"])
    out["in_multicell_site"] = out["site_ids"].map(lambda ids: any(s in multi for s in ids))

    centroids = grid.set_index("cell_id").centroid
    has_dest = out["n_categories"] > 0
    dist = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=centroids), gpd.GeoDataFrame(geometry=centroids[has_dest]),
                             distance_col="d")["d"]
    out["dist_to_facility_cell_m"] = dist.groupby(level=0).min().reindex(out.index)
    out["is_baseline_candidate"] = ~has_dest & (out["dist_to_facility_cell_m"] <= BASELINE_MAX_DIST_M)
    return out.reset_index()


def run_spatial_join() -> dict[str, Any]:
    cfg = load_config()
    crs_wgs84, crs_utm = cfg["project"]["crs_wgs84"], cfg["project"]["crs_utm"]

    grid = build_grid_polygons(pd.read_parquet(GRID_CELLS_PATH), crs_utm)
    with open(OSM_RAW_PATH, encoding="utf-8") as f:
        elements = json.load(f)["elements"]
    facilities, dropped = parse_osm_facilities(elements, cfg["facility_categories"], crs_wgs84, crs_utm)
    facilities = flag_in_grid(facilities, grid)
    facilities.to_parquet(OSM_PARSED_PATH)

    sites, dedup_log = dedup_facilities(facilities[facilities["in_grid"]])
    sites.to_parquet(FACILITIES_DEDUP_PATH)
    DEDUP_LOG_PATH.write_text(json.dumps(dedup_log, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    links = flag_counting_links(join_sites_to_cells(sites, grid, cfg["project"]["grid_size_meters"]))
    links.to_parquet(CELL_FACILITY_LINKS_PATH, index=False)

    categories = list(cfg["facility_categories"])
    cells = build_grid_facilities(grid, links, sites, categories)
    cells.to_parquet(GRID_FACILITIES_PATH, index=False)

    counted = links[links["counts_for_cell"]]
    summary = {
        "rules": {"min_share_of_cell": MIN_SHARE_OF_CELL, "min_share_of_site": MIN_SHARE_OF_SITE,
                  "transit_excluded_from_cell_class": True, "baseline_max_dist_m": BASELINE_MAX_DIST_M},
        "cells_total": len(cells),
        "cell_class": cells["cell_class"].value_counts().to_dict(),
        "baseline_candidates": int(cells["is_baseline_candidate"].sum()),
        "per_category": {c: {"distinct_facilities": int(counted.loc[counted["category"] == c, "site_id"].nunique()),
                             "cells": int(cells[f"has_{c}"].sum()),
                             # transit is outside cell_class, so its single-category count would be meaningless
                             "single_category_cells": None if c == TRANSIT else
                             int((cells[f"has_{c}"] & (cells["cell_class"] == "single_category")).sum())}
                         for c in categories},
        "sliver_links_not_counted": int((~links["counts_for_cell"]).sum()),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return {
        "grid_cells": len(grid),
        "osm_elements": len(elements),
        "parsed_facilities": len(facilities),
        "in_grid": int(facilities["in_grid"].sum()),
        "multi_category": facilities.loc[facilities["n_categories"] > 1, ["osm_key", "name", "categories"]]
                                    .to_dict("records"),
        "by_geom_kind": facilities["geom_kind"].value_counts().to_dict(),
        "by_category": facilities.explode("categories")["categories"].value_counts().to_dict(),
        "dropped": dropped,
        "dedup": {k: v for k, v in dedup_log.items() if k != "ambiguous_same_name_kept_apart"},
        "dedup_ambiguous_count": len(dedup_log["ambiguous_same_name_kept_apart"]),
        "join": {
            "links": len(links),
            "cells_with_any_site": int(links["cell_id"].nunique()),
            "sites_linked": int(links["site_id"].nunique()),
            "sites_not_in_published_cell": int(len(sites) - links["site_id"].nunique()),
            "links_by_kind": links["link_kind"].value_counts().to_dict(),
        },
        "cells": summary,
    }


if __name__ == "__main__":
    print(json.dumps(run_spatial_join(), indent=2, ensure_ascii=False, default=str))
