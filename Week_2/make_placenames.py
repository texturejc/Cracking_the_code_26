"""
Prep script -- NOT part of the class. Run once to build placenames.json from the
OS Open Names CSVs; students just read the JSON.

Keeps the populated places (cities, towns, villages, hamlets, suburban areas) and
writes them keyed on the place name, each holding a list of locations, because
place names repeat: there are 90 Newtowns.

    python3 make_placenames.py

Source: OS Open Names, Ordnance Survey, Open Government Licence v3.
        Contains OS data (c) Crown copyright and database right 2025.
Coordinates are eastings/northings on the British National Grid (EPSG:27700),
the same grid as the Week 1 pub data, so the two overlay directly.
"""
import csv
import glob
import json
import os

SRC = "Data"
HEADER = os.path.join(SRC, "OS_Open_Names_Header.csv")
OUTPUT = "placenames.json"          # one place per name, for the dictionaries class
OUTPUT_ALL = "placenames_all.json"  # every location, kept so nothing is lost

# How "large" a place is. OS ranks its own names by the zoom level at which they
# stay on the map (LEAST_DETAIL_VIEW_RES): City 9,000,000 down to Hamlet 25,000.
# That leaves Suburban Area, Other Settlement and Hamlet tied, so median bounding
# box area splits them: 0.66, 0.64 and 0.27 square km respectively.
SIZE_ORDER = ["City", "Town", "Village", "Suburban Area", "Other Settlement", "Hamlet"]

# The header lives in its own file; the 819 data files have no header row.
with open(HEADER, encoding="utf-8-sig") as fh:
    columns = next(csv.reader(fh))
idx = {name: i for i, name in enumerate(columns)}


def field(row, name):
    return row[idx[name]].strip()


places = {}
rows = kept = 0

for path in sorted(glob.glob(os.path.join(SRC, "*.csv"))):
    if path == HEADER:
        continue
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if len(row) < len(columns):
                continue
            rows += 1
            if field(row, "TYPE") != "populatedPlace":
                continue

            name = field(row, "NAME1")
            entry = {
                "easting": int(float(field(row, "GEOMETRY_X"))),
                "northing": int(float(field(row, "GEOMETRY_Y"))),
                "type": field(row, "LOCAL_TYPE"),
                "county": field(row, "COUNTY_UNITARY") or None,
                # Metropolitan boroughs (Leeds, Gateshead, Birmingham...) carry no
                # county in OS Open Names; the district is where their name lives.
                "district": field(row, "DISTRICT_BOROUGH") or None,
                "region": field(row, "REGION"),
                "country": field(row, "COUNTRY"),
            }
            # A handful of Welsh and Gaelic places carry the name in both languages
            if field(row, "NAME2"):
                entry["name_alt"] = field(row, "NAME2")
                entry["name_alt_lang"] = field(row, "NAME2_LANG") or None

            width = float(field(row, "MBR_XMAX")) - float(field(row, "MBR_XMIN"))
            height = float(field(row, "MBR_YMAX")) - float(field(row, "MBR_YMIN"))
            entry["_area"] = round(width * height / 1e6, 4)   # km2, dropped below

            places.setdefault(name, []).append(entry)
            kept += 1

# Drop exact repeats of the same place, then sort for a stable, browsable file
for name, entries in places.items():
    seen, unique = set(), []
    for e in entries:
        key = (e["easting"], e["northing"], e["type"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda e: (e["northing"], e["easting"]))
    places[name] = unique

places = {k: places[k] for k in sorted(places)}
locations = sum(len(v) for v in places.values())

# --- the full picture, one name -> every location ---------------------------
with open(OUTPUT_ALL, "w", encoding="utf-8") as fh:
    json.dump({k: [{kk: vv for kk, vv in e.items() if kk != "_area"} for e in v]
               for k, v in places.items()}, fh, ensure_ascii=False, indent=1)

# --- one place per name, so every key is unique -----------------------------
# A dictionary can only hold one value per key, so where a name repeats we keep
# the largest place and record how many others there were.
def rank(entry):
    order = SIZE_ORDER.index(entry["type"]) if entry["type"] in SIZE_ORDER else len(SIZE_ORDER)
    return (order, -entry["_area"])

single = {}
for name, entries in places.items():
    best = min(entries, key=rank)
    flat = {k: v for k, v in best.items() if k != "_area"}
    if len(entries) > 1:
        flat["other_locations"] = len(entries) - 1
    single[name] = flat

with open(OUTPUT, "w", encoding="utf-8") as fh:
    json.dump(single, fh, ensure_ascii=False, indent=1)

dropped = locations - len(single)
print(f"read {rows:,} rows, kept {kept:,} populated places")
print(f"wrote {OUTPUT_ALL}: {len(places):,} names, {locations:,} locations")
print(f"wrote {OUTPUT}: {len(single):,} names, one each "
      f"({dropped:,} further locations set aside)")
