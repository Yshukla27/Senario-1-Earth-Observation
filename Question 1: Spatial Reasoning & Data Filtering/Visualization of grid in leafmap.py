import geopandas as gpd
import leafmap.foliumap as leafmap
import os

# -------------------------------------
# 1) Load GeoJSON
# -------------------------------------
folder = r"D:\IITG project dataset\Delhi-NCR Map"  # <-- update this
file = "delhi_ncr_region.geojson"

gdf = gpd.read_file(os.path.join(folder, file))

# Ensure projected to UTM (meters)
if gdf.crs.is_geographic:
    gdf = gdf.to_crs(epsg=32644)

# -------------------------------------
# 2) Create 60×60 km Grid
# -------------------------------------
from shapely.geometry import Polygon
import numpy as np

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

# Convert both to WGS84 for web basemaps
gdf_4326 = gdf.to_crs(epsg=4326)
grid_4326 = grid_gdf.to_crs(epsg=4326)

# -------------------------------------
# 3) Create the Map
# -------------------------------------
m = leafmap.Map(center=[28.6, 77.2], zoom=8)

# Add satellite basemap (Esri World Imagery)
m.add_basemap("Esri.WorldImagery")

# Overlay Delhi-NCR boundary
m.add_gdf(gdf_4326, layer_name="Delhi-NCR Boundary", style={"color": "yellow", "weight": 3})

# Overlay 60×60 km grid
m.add_gdf(grid_4326, layer_name="60x60 km Grid", style={"color": "red", "weight": 1})

# Show map
m
