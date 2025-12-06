import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Polygon
import numpy as np
import os

# -----------------------------
# 1) LOAD GEOJSON SAFELY
# -----------------------------
folder = r"D:\IITG project dataset\Delhi-NCR Map"     # <-- UPDATE THIS
file = "delhi_ncr_region.geojson"

gdf = gpd.read_file(os.path.join(folder, file))

# Ensure CRS is in meters (UTM)
if gdf.crs.is_geographic:
    gdf = gdf.to_crs(epsg=32644)  # UTM Zone 44N

# -----------------------------
# 2) Build 60×60 km grid
# -----------------------------
grid_size = 60000  # meters

minx, miny, maxx, maxy = gdf.total_bounds

polygons = []
for x in np.arange(minx, maxx, grid_size):
    for y in np.arange(miny, maxy, grid_size):
        polygons.append(Polygon([
            (x, y),
            (x + grid_size, y),
            (x + grid_size, y + grid_size),
            (x, y + grid_size)
        ]))

grid_gdf = gpd.GeoDataFrame(geometry=polygons, crs=gdf.crs)

# -----------------------------
# 3) Plot
# -----------------------------
fig, ax = plt.subplots(figsize=(10, 10))

gdf.boundary.plot(ax=ax, color="black", linewidth=1.4)
grid_gdf.boundary.plot(ax=ax, color="red", linewidth=0.4)

plt.title("Delhi-NCR with 60×60 km Grid")
plt.show()
