"""
Overlay georeferenced rasters (GeoTIFFs) on the 60x60 km grid (clipped to Delhi-NCR).

Behavior:
- Search for GeoTIFFs inside "rgb/".
- If none found, try "worldcover_bbox_delhi_ncr_2021.tif" at project root.
- Build 60x60 km grid (UTM 32644), clip to region.
- For each raster, create a footprint polygon from bounds and compute its center.
- Report which rasters' centers fall outside the clipped grid.
- Produce:
    - static matplotlib plot (grid, region, footprints, centers)
    - interactive Folium map (Esri.WorldImagery base) with toggleable layers
Outputs saved into `overlay_output/`:
    - footprints.geojson (all raster footprints)
    - inside_rasters.csv, outside_rasters.csv
"""

import os, sys
from pathlib import Path
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Polygon, Point, mapping

try:
    import rasterio
except Exception:
    print("Install rasterio: pip install rasterio")
    raise

import folium
from folium.plugins import Fullscreen

# --------- CONFIG ----------
PROJECT_ROOT = Path(r"D:\IITG project dataset\Delhi-NCR Map")
REGION_GEOJSON = PROJECT_ROOT / "delhi_ncr_region.geojson"
RASTER_FOLDER = PROJECT_ROOT / "rgb"
FALLBACK_RASTER = PROJECT_ROOT / "worldcover_bbox_delhi_ncr_2021.tif"
OUTPUT_FOLDER = PROJECT_ROOT / "overlay_output"
GRID_SIZE_METERS = 60000
UTM_EPSG = 32644
# --------------------------

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 0) sanity checks
if not REGION_GEOJSON.exists():
    print(f"[ERR] Region file not found: {REGION_GEOJSON}")
    sys.exit(1)

# 1) Build clipped grid (re-usable)
region_gdf = gpd.read_file(str(REGION_GEOJSON))
if region_gdf.crs is None:
    region_gdf.set_crs(epsg=4326, inplace=True)
# project to UTM
if region_gdf.crs.is_geographic:
    region_utm = region_gdf.to_crs(epsg=UTM_EPSG)
else:
    region_utm = region_gdf.to_crs(epsg=UTM_EPSG)

minx, miny, maxx, maxy = region_utm.total_bounds
xs = np.arange(minx, maxx + 1, GRID_SIZE_METERS)
ys = np.arange(miny, maxy + 1, GRID_SIZE_METERS)

polys = []
cell_ids = []
cid = 0
for x in xs[:-1]:
    for y in ys[:-1]:
        polys.append(Polygon([(x, y), (x+GRID_SIZE_METERS, y), (x+GRID_SIZE_METERS, y+GRID_SIZE_METERS), (x, y+GRID_SIZE_METERS)]))
        cell_ids.append(cid); cid += 1
grid_gdf = gpd.GeoDataFrame({"cell_id": cell_ids, "geometry": polys}, crs=region_utm.crs)

# clip to region
try:
    region_union = region_utm.geometry.union_all()
except Exception:
    region_union = region_utm.unary_union
grid_gdf = grid_gdf[grid_gdf.intersects(region_union)].reset_index(drop=True)
print(f"[OK] Built grid with {len(grid_gdf)} cells (clipped).")

# 2) find rasters (GeoTIFFs)
tif_list = [f for f in sorted(os.listdir(RASTER_FOLDER)) if f.lower().endswith(('.tif','.tiff'))] if RASTER_FOLDER.exists() else []
if len(tif_list) == 0 and FALLBACK_RASTER.exists():
    print("[INFO] No GeoTIFFs in rgb/ — using fallback raster:", FALLBACK_RASTER.name)
    tif_list = [FALLBACK_RASTER.name]
    raster_base_folder = str(FALLBACK_RASTER.parent)
else:
    raster_base_folder = str(RASTER_FOLDER)

if len(tif_list) == 0:
    print("[WARN] No georeferenced rasters found and no fallback raster present. Aborting overlay step.")
    sys.exit(0)

# 3) build footprints (header-only)
records = []
for fname in tif_list:
    path = os.path.join(raster_base_folder, fname)
    try:
        with rasterio.open(path) as src:
            b = src.bounds  # left, bottom, right, top (in src.crs)
            src_crs = src.crs
            # footprint polygon in src.crs
            poly = Polygon([(b.left, b.bottom), (b.right, b.bottom), (b.right, b.top), (b.left, b.top)])
            # center in src.crs
            cx = (b.left + b.right) / 2.0
            cy = (b.bottom + b.top) / 2.0
            records.append({
                "filename": fname,
                "path": path,
                "src_crs": src_crs.to_string() if src_crs else None,
                "cx": cx,
                "cy": cy,
                "geometry": poly
            })
    except Exception as e:
        print(f"[WARN] Could not open {path}: {e}")

if len(records) == 0:
    print("[ERR] No readable raster headers. Exiting.")
    sys.exit(1)

footprints_gdf = gpd.GeoDataFrame(records, geometry='geometry', crs=records[0]['src_crs'])
# ensure geometry column is set
footprints_gdf = footprints_gdf.set_geometry('geometry')

# 4) reproject footprints and centers to grid CRS (UTM)
if footprints_gdf.crs is None:
    print("[WARN] footprint CRS is None — assuming EPSG:4326")
    footprints_gdf.set_crs(epsg=4326, inplace=True)

footprints_utm = footprints_gdf.to_crs(grid_gdf.crs)
# add center point geometry in UTM
footprints_utm['center_geom'] = footprints_utm.apply(lambda r: Point(r.cx, r.cy), axis=1)
# if cx/cy were in src_crs, after to_crs they remain but points need to transform: better recompute center from polygon bounds in utm
footprints_utm['center_geom'] = footprints_utm.geometry.centroid
footprints_utm = footprints_utm.set_geometry('geometry')  # keep footprint as geometry col

# 5) spatial join: which raster centers fall within grid cells?
centers_gdf = gpd.GeoDataFrame(footprints_utm[['filename']], geometry=footprints_utm['center_geom'], crs=footprints_utm.crs)
joined = gpd.sjoin(centers_gdf, grid_gdf[['cell_id','geometry']], how='left', predicate='within')
inside = joined[~joined['cell_id'].isna()].copy().reset_index(drop=True)
outside = joined[joined['cell_id'].isna()].copy().reset_index(drop=True)

print(f"[RESULT] Total rasters checked: {len(footprints_utm)}")
print(f"[RESULT] Raster centers inside grid: {len(inside)}")
print(f"[RESULT] Raster centers outside grid: {len(outside)}")

# Save footprints (reprojected to WGS84 for sharing)
# Keep only the footprint geometry before export
export_gdf = footprints_utm.copy()

# Drop the center geometry column so only one geometry remains
if "center_geom" in export_gdf.columns:
    export_gdf = export_gdf.drop(columns=["center_geom"])

# Ensure active geometry is the polygon footprint
export_gdf = export_gdf.set_geometry("geometry")

# Reproject for GeoJSON
export_wgs = export_gdf.to_crs(epsg=4326)

# Export cleanly
footprints_out = OUTPUT_FOLDER / "footprints.geojson"
export_wgs.to_file(footprints_out, driver="GeoJSON")

print("[OUT] Saved raster footprints ->", footprints_out)


# Save inside/outside lists
inside[['filename','cell_id']].to_csv(os.path.join(OUTPUT_FOLDER, "inside_rasters.csv"), index=False)
outside[['filename']].to_csv(os.path.join(OUTPUT_FOLDER, "outside_rasters.csv"), index=False)
print("[OUT] Saved inside/outside CSVs into", OUTPUT_FOLDER)

# 6) Static plot (matplotlib) — quick sanity check
try:
    import matplotlib.pyplot as plt
    grid_wgs = grid_gdf.to_crs(epsg=4326)
    region_wgs = region_utm.to_crs(epsg=4326)
    footprints_plot = footprints_wgs.copy()
    centers_plot = gpd.GeoDataFrame(joined.copy()).to_crs(epsg=4326)

    fig, ax = plt.subplots(1,1,figsize=(10,10))
    region_wgs.boundary.plot(ax=ax, color='black', linewidth=1)
    grid_wgs.boundary.plot(ax=ax, color='red', linewidth=0.6)
    footprints_plot.boundary.plot(ax=ax, color='orange', linewidth=1, alpha=0.6)
    # plot centers: inside green, outside black X
    if len(inside)>0:
        inside_wgs = inside.to_crs(epsg=4326)
        inside_wgs.plot(ax=ax, marker='o', color='green', markersize=8, label='inside centers')
    if len(outside)>0:
        outside_wgs = outside.to_crs(epsg=4326)
        outside_wgs.plot(ax=ax, marker='x', color='black', markersize=60, label='outside centers')
    ax.set_title("Raster footprints & centers vs 60x60 km grid")
    ax.legend()
    plt.show()
except Exception as e:
    print("[WARN] Static plot failed:", e)

# 7) Interactive Folium map (footprints as GeoJSON layer + centers)
try:
    # base map center from region centroid in WGS84
    region_centroid = region_gdf.to_crs(epsg=4326).geometry.centroid.iloc[0]
    m = folium.Map(location=[region_centroid.y, region_centroid.x], zoom_start=9)
    Fullscreen().add_to(m)

    # add satellite basemap
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                     attr='Esri', name='Esri.WorldImagery', control=True).add_to(m)

    # add region boundary
    folium.GeoJson(region_gdf.to_crs(epsg=4326).__geo_interface__, name='Delhi-NCR boundary',
                   style_function=lambda feat: {'color':'yellow','weight':2,'fill':False}).add_to(m)

    # add grid (simplify geometry to speed)
    folium.GeoJson(grid_gdf.to_crs(epsg=4326).__geo_interface__, name='60x60 km grid',
                   style_function=lambda feat: {'color':'red','weight':0.6,'fill':False}).add_to(m)

    # add footprints layer
    folium.GeoJson(footprints_wgs.__geo_interface__, name='Raster footprints',
                   style_function=lambda feat: {'color':'orange','weight':1,'fill':False},
                   tooltip=folium.GeoJsonTooltip(fields=['filename'], aliases=['file'])
                  ).add_to(m)

    # centers: inside vs outside markers
    for idx, row in inside.to_crs(epsg=4326).iterrows():
        folium.CircleMarker(location=[row.geometry.y, row.geometry.x], radius=5, color='green',
                            fill=True, fill_opacity=0.9, popup=f"{row.filename} | cell:{int(row.cell_id)}").add_to(m)
    for idx, row in outside.to_crs(epsg=4326).iterrows():
        folium.CircleMarker(location=[row.geometry.y, row.geometry.x], radius=6, color='black',
                            fill=True, fill_opacity=1, popup=f"{row.filename} | outside").add_to(m)

    folium.LayerControl().add_to(m)
    out_html = os.path.join(OUTPUT_FOLDER, "raster_overlay_map.html")
    m.save(out_html)
    print("[OUT] Saved interactive map ->", out_html)
except Exception as e:
    print("[WARN] Could not create interactive map:", e)

print("\nDONE — check the CSVs and HTML in", OUTPUT_FOLDER)



import os
import re
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

# folder setup
RGB_FOLDER = r"D:\IITG project dataset\Delhi-NCR Map\rgb"
REGION_GEOJSON = "D:\IITG project dataset\Delhi-NCR Map\delhi_ncr_region.geojson"
UTM_EPSG = 32644

# STEP 1 — Build grid again (fast, minimal)
region = gpd.read_file(REGION_GEOJSON)
if region.crs is None:
    region = region.set_crs("EPSG:4326")

region_utm = region.to_crs(UTM_EPSG)
minx, miny, maxx, maxy = region_utm.total_bounds

GRID_SIZE = 60000  # 60 km

import numpy as np
from shapely.geometry import Polygon

xs = np.arange(minx, maxx + GRID_SIZE, GRID_SIZE)
ys = np.arange(miny, maxy + GRID_SIZE, GRID_SIZE)

polys = []
ids = []
cid = 0
for x in xs[:-1]:
    for y in ys[:-1]:
        polys.append(Polygon([
            (x, y),
            (x + GRID_SIZE, y),
            (x + GRID_SIZE, y + GRID_SIZE),
            (x, y + GRID_SIZE)
        ]))
        ids.append(cid)
        cid += 1

grid = gpd.GeoDataFrame({"cell_id": ids, "geometry": polys}, crs=UTM_EPSG)
grid = grid[grid.intersects(region_utm.unary_union)].reset_index(drop=True)

print("Grid cells:", len(grid))

# STEP 2 — Parse filenames into coordinates
latlons = []
pattern = re.compile(r"([0-9]+\.[0-9]+)_([0-9]+\.[0-9]+)\.png$")

for fname in os.listdir(RGB_FOLDER):
    m = pattern.search(fname)
    if m:
        lat = float(m.group(1))
        lon = float(m.group(2))
        latlons.append({
            "filename": fname,
            "lat": lat,
            "lon": lon,
            "geometry": Point(lon, lat)
        })

points = gpd.GeoDataFrame(latlons, crs="EPSG:4326")
points_utm = points.to_crs(UTM_EPSG)

print("Total images detected:", len(points_utm))

# STEP 3 — Spatial join: image → grid cell
joined = gpd.sjoin(points_utm, grid, how="left", predicate="within")

inside = joined[joined["cell_id"].notna()].copy()
outside = joined[joined["cell_id"].isna()].copy()

print("Inside grid:", len(inside))
print("Outside grid:", len(outside))

# STEP 4 — Save dataset
inside[["filename", "lat", "lon", "cell_id"]].to_csv("images_inside_grid.csv", index=False)
outside[["filename", "lat", "lon"]].to_csv("images_outside_grid.csv", index=False)

print("Saved: images_inside_grid.csv and images_outside_grid.csv")
import folium
from folium.plugins import MarkerCluster, Fullscreen
import geopandas as gpd
import pandas as pd

# Load region and grid
region = gpd.read_file("D:\IITG project dataset\Delhi-NCR Map\delhi_ncr_region.geojson").to_crs(epsg=4326)
grid = gpd.read_file("grid.geojson") if False else None  # skip unless you export grid

# Load inside-only dataset (main dataset)
df = pd.read_csv("images_inside_grid.csv")

# Create a GeoDataFrame of image points
gdf = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df.lon, df.lat),
    crs="EPSG:4326"
)

print("Points to visualize:", len(gdf))

# Map centered on NCR
center = region.geometry.unary_union.centroid
m = folium.Map(location=[center.y, center.x], zoom_start=10, tiles="CartoDB positron")

Fullscreen().add_to(m)

# Add region boundary
folium.GeoJson(
    region,
    name="Delhi NCR Boundary",
    style_function=lambda x: {"color": "yellow", "weight": 2, "fill": False},
).add_to(m)

# Add grid overlay (optional)
# NOTE: Only add if you exported your grid to a geojson
# folium.GeoJson(grid, name="60x60km Grid",
#                 style_function=lambda x: {"color":"red","weight":1,"fill":False}).add_to(m)

# Add points with clustering
cluster = MarkerCluster(name="Image Chips").add_to(m)

for _, row in gdf.iterrows():
    popup = f"""
    <b>Filename:</b> {row['filename']}<br>
    <b>Lat:</b> {row['lat']}<br>
    <b>Lon:</b> {row['lon']}<br>
    <b>Cell:</b> {row['cell_id']}
    """
    folium.CircleMarker(
        location=[row['lat'], row['lon']],
        radius=4,
        color="blue",
        fill=True,
        fill_opacity=0.8,
        popup=popup
    ).add_to(cluster)

folium.LayerControl().add_to(m)

# Save output
m.save("image_chip_map.html")
print("Saved interactive map -> image_chip_map.html")

        
        
