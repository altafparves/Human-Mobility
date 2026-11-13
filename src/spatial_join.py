"""
Role 2: Geospatial Engineering & Facility Deduplication Lead (Silver -> Gold Spatial)
-------------------------------------------------------------------------------------
Responsibilities:
- Reconstruct 500m x 500m grid polygons in UTM Zone 49S (EPSG:32749).
- Reproject OSM geometries (EPSG:4326 -> EPSG:32749) and apply tag taxonomy from configs/osm_tags.yaml.
- Deduplicate overlapping OSM representations (point nodes vs. campus/hospital polygons).
- Execute spatial join (gpd.sjoin / overlay) and classify single-category, mixed-use, and matched baseline cells.
"""

