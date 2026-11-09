"""
Prep script -- NOT part of the class. Run once to build waterways.csv from the
OS Open Rivers GeoPackage; students just read the CSV.

Selects the navigable waterways (canals, plus the major named river systems and
their tidal reaches), flattens the line geometries into plain easting/northing
columns, and writes a CSV that plots with ax.plot() and nothing else.

    python3 make_waterways.py

Needs: geopandas, shapely, scipy, pandas.
"""
import geopandas as gpd
import pandas as pd
import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

SOURCE = "oprvrs_gb.gpkg"
OUTPUT = "waterways.csv"
MIN_SYSTEM_LENGTH = 60_000   # metres; a named river system must be this long to count
SIMPLIFY = 100               # metres; drops detail invisible at national scale

rivers = gpd.read_file(SOURCE, layer="watercourse_link")
print(f"read {len(rivers):,} segments from {SOURCE}")

# --- split the network into connected systems -------------------------------
# Names alone aren't enough: dozens of unrelated streams are called "Black Burn",
# and there are several "River Avon". Joining segments through their shared
# start/end nodes separates them into genuinely connected watercourses.
nodes = pd.Index(pd.unique(pd.concat([rivers.start_node, rivers.end_node])))
start = nodes.get_indexer(rivers.start_node)
end = nodes.get_indexer(rivers.end_node)
graph = coo_matrix((np.ones(len(start)), (start, end)), shape=(len(nodes),) * 2)
_, component = connected_components(graph, directed=False)
rivers["component"] = component[start]

system_length = rivers.groupby(["watercourse_name", "component"]).length.transform("sum")

# --- pick the navigable network ---------------------------------------------
# Canals are navigable by definition. For rivers we use a proxy: a named system
# long enough to be a trunk river, which keeps estuaries like the Thames and
# Humber but drops unnamed coastal creeks and Scottish sea lochs.
is_canal = rivers.form == "canal"
is_major = (rivers.watercourse_name.notna()
            & (system_length > MIN_SYSTEM_LENGTH)
            & (rivers.form != "lake"))

waterways = rivers[is_canal | is_major].copy()
waterways["geometry"] = waterways.geometry.simplify(SIMPLIFY)
waterways = waterways.sort_values(["watercourse_name", "component"])
print(f"kept {len(waterways):,} segments "
      f"({waterways.watercourse_name.nunique()} named waterways)")

# --- flatten the shapes into easting/northing columns -----------------------
# Each segment is a list of points. A row of NaN between segments tells
# matplotlib to lift the pen instead of drawing a line to the next one.
coords = shapely.get_coordinates(waterways.geometry)
counts = shapely.get_num_coordinates(waterways.geometry)
breaks = np.cumsum(counts)[:-1]

coords = np.insert(coords, breaks, np.nan, axis=0)
label = np.repeat(waterways.watercourse_name.values, counts)
label = np.insert(label, breaks, waterways.watercourse_name.values[:-1])
kind = np.repeat(waterways.form.values, counts)
kind = np.insert(kind, breaks, waterways.form.values[:-1])

out = pd.DataFrame({
    "easting": np.round(coords[:, 0]),      # whole metres is plenty
    "northing": np.round(coords[:, 1]),
    "name": label,
    "type": pd.Series(kind).map({"inlandRiver": "river", "tidalRiver": "tidal",
                                 "canal": "canal"}).values,
})
out.to_csv(OUTPUT, index=False)
print(f"wrote {OUTPUT}: {len(out):,} rows")
