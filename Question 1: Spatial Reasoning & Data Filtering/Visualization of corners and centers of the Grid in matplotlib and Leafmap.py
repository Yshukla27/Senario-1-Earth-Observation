# Task 3: Mark four corners + center of each 60x60 km grid cell
import os
import numpy as np
import geopandas as gpd
from shapely.geometry import Polygon, Point
import matplotlib.pyplot as plt
import folium

# -----------------------
# CONFIG - update path
# -----------------------
folder = r"D:\IITG project dataset\Delhi-NCR Map"    # <-- update this to your folder
file = "delhi_ncr_region.geojson"

# -----------------------
# 1) LOAD boundary
# -----------------------
gdf = gpd.read_file(os.path.join(folder, file))

# ensure projected to meters for correct grid sizing
if gdf.crs.is_geographic:
    gdf = gdf.to_crs(epsg=32644)  # UTM zone 44N

# -----------------------
# 2) MAKE 60x60 km GRID
# -----------------------
grid_size = 60000  # meters
minx, miny, maxx, maxy = gdf.total_bounds

polygons = []
cell_ids = []
cid = 0
for x in np.arange(minx, maxx, grid_size):
    for y in np.arange(miny, maxy, grid_size):
        polygons.append(Polygon([
            (x, y),
            (x + grid_size, y),
            (x + grid_size, y + grid_size),
            (x, y + grid_size)
        ]))
        cell_ids.append(cid)
        cid += 1

grid_gdf = gpd.GeoDataFrame({"cell_id": cell_ids, "geometry": polygons}, crs=gdf.crs)

# OPTIONAL: clip grid to region if you want only cells overlapping region
# grid_gdf = gpd.overlay(grid_gdf, gdf, how="intersection")

# -----------------------
# 3) EXTRACT CORNERS & CENTERS
# -----------------------
corner_points = []   # list of (Point, cell_id, corner_label)
center_points = []   # list of (Point, cell_id)

for idx, row in grid_gdf.iterrows():
    cid = row["cell_id"]
    poly = row.geometry
    # bounds: minx, miny, maxx, maxy
    bminx, bminy, bmaxx, bmaxy = poly.bounds
    # corners: SW, SE, NE, NW (choose any order, we'll label them)
    corners = {
        "SW": Point(bminx, bminy),
        "SE": Point(bmaxx, bminy),
        "NE": Point(bmaxx, bmaxy),
        "NW": Point(bminx, bmaxy),
    }
    for label, pt in corners.items():
        corner_points.append({"cell_id": cid, "corner": label, "geometry": pt})
    center_points.append({"cell_id": cid, "geometry": poly.centroid})

corners_gdf = gpd.GeoDataFrame(corner_points, crs=grid_gdf.crs)
centers_gdf = gpd.GeoDataFrame(center_points, crs=grid_gdf.crs)

# -----------------------
# 4) Prepare layers in WGS84 for web map
# -----------------------
gdf_4326 = gdf.to_crs(epsg=4326)
grid_4326 = grid_gdf.to_crs(epsg=4326)
corners_4326 = corners_gdf.to_crs(epsg=4326)
centers_4326 = centers_gdf.to_crs(epsg=4326)

# -----------------------
# 5) QUICK MATPLOTLIB PLOT (static check)
# -----------------------
fig, ax = plt.subplots(figsize=(9,9))
gdf_4326.boundary.plot(ax=ax, color="black", linewidth=1.4)
grid_4326.boundary.plot(ax=ax, color="red", linewidth=0.4, alpha=0.6)

# plot corners and centers
corners_4326.plot(ax=ax, marker="o", markersize=8, color="black", label="corners", alpha=0.9)
centers_4326.plot(ax=ax, marker="*", markersize=40, color="blue", label="centers", alpha=0.9)

plt.title("Delhi-NCR: Grid cells with corners (black) and centers (blue stars)")
plt.legend()
plt.show()

# -----------------------
# 6) INTERACTIVE FOLIUM MAP (satellite + markers)
# -----------------------
# center map on Delhi roughly; you can compute centroid of gdf_4326 if needed
map_center = [gdf_4326.geometry.centroid.y.values[0], gdf_4326.geometry.centroid.x.values[0]]
m = folium.Map(location=map_center, zoom_start=9, tiles=None)
# add Esri Satellite tiles
folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                 attr='Esri', name='Esri.WorldImagery', overlay=False, control=True).add_to(m)

# add grid boundary layer
folium.GeoJson(grid_4326.__geo_interface__, name="60x60 km grid", 
               style_function=lambda feat: {"color": "red", "weight": 1, "fill": False}
              ).add_to(m)

# add region boundary
folium.GeoJson(gdf_4326.__geo_interface__, name="Delhi-NCR boundary",
               style_function=lambda feat: {"color": "yellow", "weight": 2, "fill": False}
              ).add_to(m)

# add corners (small black circles) and centers (blue stars)
corner_fg = folium.FeatureGroup(name="Corners (4 per cell)", show=False)
for _, r in corners_4326.iterrows():
    lat = r.geometry.y
    lon = r.geometry.x
    popup = f"cell:{r.cell_id} corner:{r.corner}"
    folium.CircleMarker(location=[lat, lon], radius=3, color="black", fill=True, fill_opacity=1, popup=popup).add_to(corner_fg)
corner_fg.add_to(m)

center_fg = folium.FeatureGroup(name="Centers", show=True)
for _, r in centers_4326.iterrows():
    lat = r.geometry.y
    lon = r.geometry.x
    popup = f"cell:{r.cell_id} center"
    # use a slightly larger marker for center
    folium.CircleMarker(location=[lat, lon], radius=6, color="blue", fill=True, fill_opacity=0.9, popup=popup).add_to(center_fg)
center_fg.add_to(m)

folium.LayerControl().add_to(m)

# show map (in notebooks this will render)
m
