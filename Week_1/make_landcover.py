"""
Prep script -- NOT part of the class. Run once to build landcover.csv;
students just read the CSV.

Takes ESA WorldCover 2021 (10 m global land cover), reduces it to the dominant
land cover class in each 1 km cell of the British National Grid, clips it to
Great Britain, and writes a CSV with the same easting/northing columns as the
pub and waterway data.

    python3 make_landcover.py

Downloads ~530 MB of source tiles into data_raw/ on first run and reuses them
afterwards. Needs: rasterio, geopandas, pandas, numpy.

Sources
  ESA WorldCover 2021 v200, CC BY 4.0
    https://esa-worldcover.org/   (credit: "(c) ESA WorldCover project 2021")
  Natural Earth 1:10m admin 0 map units, public domain -- used only to clip to GB
"""
import os
import urllib.request
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

RAW = os.environ.get("LANDCOVER_RAW", "data_raw")   # override to reuse tiles elsewhere
OUTPUT = "landcover.csv"
CELL = 1000                      # metres; grid resolution of the output
WIDTH, HEIGHT = 700, 1300        # cells; covers the whole British National Grid

# The 16 WorldCover tiles that between them cover Great Britain
TILES = ["N48W009", "N48W006", "N48W003", "N48E000",
         "N51W009", "N51W006", "N51W003", "N51E000",
         "N54W009", "N54W006", "N54W003",
         "N57W009", "N57W006", "N57W003",
         "N60W009", "N60W003"]
TILE_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
            "ESA_WorldCover_10m_2021_v200_{}_Map.tif")
NE_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_map_units.zip"

# WorldCover's numeric classes, renamed to words a reader will recognise
CLASSES = {10: "forest", 20: "shrub", 30: "grassland", 40: "arable",
           50: "urban", 60: "bare", 70: "snow", 80: "water",
           90: "wetland", 95: "mangrove", 100: "moss"}


def fetch(url, path):
    if not os.path.exists(path):
        print(f"  downloading {os.path.basename(path)} ...")
        urllib.request.urlretrieve(url, path)
    return path


os.makedirs(RAW, exist_ok=True)
transform = from_origin(0, HEIGHT * CELL, CELL, CELL)

# --- reduce each tile to the dominant class per 1 km cell -------------------
# Resampling.mode asks for the most common 10 m pixel in each 1 km cell, which
# is what "dominant land cover" means. Tiles don't overlap, so we can merge them
# by filling in wherever a tile has data and the grid so far doesn't.
print("building 1 km grid from WorldCover tiles")
grid = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)

for tile in TILES:
    path = fetch(TILE_URL.format(tile), os.path.join(RAW, f"wc_{tile}.tif"))
    patch = np.zeros_like(grid)
    with rasterio.open(path) as src:
        reproject(source=rasterio.band(src, 1), destination=patch,
                  dst_transform=transform, dst_crs="EPSG:27700",
                  src_nodata=0, dst_nodata=0, resampling=Resampling.mode)
    grid[patch > 0] = patch[patch > 0]
    print(f"  {tile}: {(patch > 0).sum():,} cells")

# --- clip to Great Britain --------------------------------------------------
# The tiles also cover Ireland, France and the Low Countries, and those fall
# inside the National Grid's numeric extent. Without this they'd appear on the
# map. Northern Ireland is excluded too: it uses the Irish Grid, not the BNG.
print("clipping to Great Britain")
zip_path = fetch(NE_URL, os.path.join(RAW, "ne_map_units.zip"))
with zipfile.ZipFile(zip_path) as z:
    z.extractall(os.path.join(RAW, "ne"))

units = gpd.read_file(os.path.join(RAW, "ne", "ne_10m_admin_0_map_units.shp"))
gb = units[units.GEOUNIT.isin(["England", "Scotland", "Wales"])].to_crs("EPSG:27700")


def gb_mask(buffer):
    shapes = [(shape, 1) for shape in gb.geometry.buffer(buffer)]
    return rasterize(shapes, out_shape=grid.shape, transform=transform, dtype=np.uint8)


# A small buffer stops the generalised coastline from shaving off coastal land...
grid[gb_mask(CELL) == 0] = 0
# ...but that buffer also catches a rim of sea, which would then show up as
# "water". Hold the water class to the coastline itself, so it means lakes,
# lochs and estuaries rather than an outline of the sea.
WATER = 80
grid[(grid == WATER) & (gb_mask(0) == 0)] = 0

# --- write out one row per cell --------------------------------------------
rows, cols = np.nonzero(grid)
easting = cols * CELL + CELL // 2        # centre of the cell, not its corner
northing = (HEIGHT - 1 - rows) * CELL + CELL // 2

land = pd.DataFrame({
    "easting": easting,
    "northing": northing,
    "type": pd.Series(grid[rows, cols]).map(CLASSES).values,
}).sort_values(["type", "easting", "northing"])

land = land[land.type.notna()]
land.to_csv(OUTPUT, index=False)

print(f"\nwrote {OUTPUT}: {len(land):,} rows")
print(land.type.value_counts().to_string())
