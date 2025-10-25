"""OSM helper tools for counting nearby outdoor activities.

Provides a function `count_outdoor_activities(location, radius_m)` which uses
osmnx to query OSM for common outdoor-activity tags near a point.

The module performs lazy-import of `osmnx` so importing this file doesn't
require osmnx to be installed until the function is called.
"""
from typing import Tuple, Union, Dict, Any, Optional


def _resolve_location(location: Union[str, Tuple[float, float]]):
    """Return (lat, lon) for a location string or tuple.

    If `location` is a tuple it's assumed to be (lat, lon). If it's a string
    we use osmnx geocoder to resolve it.
    """
    if isinstance(location, tuple) and len(location) == 2:
        return float(location[0]), float(location[1])

    # lazy import
    import osmnx as ox

    # ox.geocode may return a (lat, lng) tuple or a string -> coordinates
    try:
        point = ox.geocoder.geocode(location)
        # geocode returns (lat, lng)
        return float(point[0]), float(point[1])
    except Exception:
        # try geocode_to_gdf fallback
        gdf = ox.geocode_to_gdf(location)
        if not gdf.empty:
            geom = gdf.geometry.iloc[0]
            lat, lon = geom.y, geom.x
            return float(lat), float(lon)
        raise


def _geometries_from_point_compat(ox, point: Tuple[float, float], tags: Dict[str, Any], dist: int):
    """Compatibility wrapper: return a GeoDataFrame for a point using osmnx.

    osmnx exposes this functionality under different names across versions
    (eg. `geometries.geometries_from_point`, `geometries_from_point`,
    `features_from_point`). Try the common variants and return the first
    successful result. Raise RuntimeError with a helpful message otherwise.
    """
    candidates = []
    if hasattr(ox, "geometries") and hasattr(ox.geometries, "geometries_from_point"):
        candidates.append(("ox.geometries.geometries_from_point", lambda: ox.geometries.geometries_from_point(point, tags=tags, dist=dist)))
    if hasattr(ox, "geometries_from_point"):
        candidates.append(("ox.geometries_from_point", lambda: ox.geometries_from_point(point, tags=tags, dist=dist)))
    if hasattr(ox, "features_from_point"):
        candidates.append(("ox.features_from_point", lambda: ox.features_from_point(point, tags=tags, dist=dist)))

    tried = []
    for name, func in candidates:
        tried.append(name)
        try:
            gdf = func()
            return gdf
        except Exception:
            continue

    raise RuntimeError(
        "Could not retrieve geometries from osmnx. Tried: {}. "
        "Ensure osmnx is installed and is a compatible version.".format(
            ", ".join(tried) if tried else "no candidate functions found"
        )
    )


def count_outdoor_activities(
    location: Union[str, Tuple[float, float]],
    radius_m: int = 1000,
    tags: Optional[Dict[str, Any]] = None,
    breakdown: bool = False,
):
    """Count nearby OSM elements that represent outdoor activities.

    Args:
        location: place name (string) or (lat, lon) tuple.
        radius_m: search radius in meters.
        tags: optional custom tags dict for osmnx.geometries_from_point.
        breakdown: if True return a dict with breakdown counts by key.

    Returns:
        int or dict: count (int) when breakdown=False, else dict of counts.

    Notes:
        This function lazy-imports `osmnx` so calling it requires `osmnx`
        to be installed. The default tag set looks for common outdoor
        activity keys (leisure, sport, tourism, route, amenity).
    """
    # lazy import to keep module import cheap
    import osmnx as ox
    import pandas as pd

    lat, lon = _resolve_location(location)

    # sensible default tags that represent outdoor activities
    if tags is None:
        tags = {
            "leisure": [
                "park",
                "playground",
                "garden",
                "common",
                "sports_centre",
                "picnic_site",
            ],
            # request any element with a sport tag
            "sport": True,
            "tourism": ["viewpoint", "attraction"],
            # walking / hiking / cycling routes
            "route": ["hiking", "bicycle"],
            # pitches / fields
            "amenity": ["pitch"],
        }

    # Query OSM for geometries within distance using compatibility wrapper
    point = (lat, lon)
    gdf = _geometries_from_point_compat(ox, point, tags=tags, dist=radius_m)

    if gdf is None or gdf.empty:
        return {} if breakdown else 0

    # deduplicate by OSM id where possible
    if "osmid" in gdf.columns:
        unique_count = gdf["osmid"].nunique()
    else:
        unique_count = len(gdf)

    if not breakdown:
        return int(unique_count)

    # breakdown: counts per tag key/value
    breakdown_counts: Dict[str, int] = {}
    # For each interesting key present in the returned dataframe, count occurrences
    for col in [c for c in gdf.columns if c not in ("geometry",)]:
        # normalize series to string for grouping
        series = gdf[col].dropna()
        if series.empty:
            continue
        # Many OSM tags can be lists/sets; convert to string and count unique values
        # If values are lists, explode them
        if series.apply(lambda x: isinstance(x, (list, set, tuple))).any():
            # convert to list-like and explode
            exploded = series.apply(lambda x: list(x) if isinstance(x, (list, set, tuple)) else [x]).explode()
            value_counts = exploded.astype(str).value_counts().to_dict()
        else:
            value_counts = series.astype(str).value_counts().to_dict()
        breakdown_counts[col] = sum(value_counts.values())

    # add overall total
    breakdown_counts["__total__"] = int(unique_count)
    return breakdown_counts


def healthcare_layer(
    location: Union[str, Tuple[float, float]],
    radius_m: int = 1000,
    exclude_pharmacy: bool = True,
):
    """Return a GeoDataFrame of nearby healthcare-related OSM elements.

    This produces a GeoDataFrame with CRS=EPSG:4326 suitable for exporting to
    formats ArcGIS can consume (GeoJSON, GeoPackage, Shapefile).

    Args:
        location: place name or (lat, lon) tuple.
        radius_m: search radius in meters.
        exclude_pharmacy: if True, filter out features tagged as pharmacies.

    Returns:
        geopandas.GeoDataFrame (may be empty).
    """
    # lazy import to avoid requiring geopandas/osmnx until needed
    import osmnx as ox
    import geopandas as gpd

    lat, lon = _resolve_location(location)
    tags = {
        # healthcare-related amenities
        "amenity": ["hospital", "clinic", "doctors", "pharmacy", "dentist"],
        "healthcare": True,
    }

    gdf = _geometries_from_point_compat(ox, (lat, lon), tags=tags, dist=radius_m)
    if gdf is None:
        # return empty GeoDataFrame with geometry column
        return gpd.GeoDataFrame(columns=["geometry"]).set_geometry("geometry")
    if gdf.empty:
        return gdf

    # Optionally exclude pharmacies
    if exclude_pharmacy and any(col in gdf.columns for col in ("amenity", "healthcare")):
        def _is_pharmacy_value(v):
            if v is None:
                return False
            if isinstance(v, (list, set, tuple)):
                return any(str(x).lower() == "pharmacy" for x in v)
            return str(v).lower() == "pharmacy"

        def _row_is_pharmacy(row):
            for col in ("amenity", "healthcare"):
                if col in gdf.columns:
                    if _is_pharmacy_value(row.get(col)):
                        return True
            return False

        try:
            mask = gdf.apply(_row_is_pharmacy, axis=1)
            gdf = gdf.loc[~mask]
        except Exception:
            # if filtering fails, keep original gdf
            pass

    # Ensure we have a GeoDataFrame type and CRS is WGS84 for ArcGIS compatibility
    if not isinstance(gdf, gpd.GeoDataFrame):
        try:
            gdf = gpd.GeoDataFrame(gdf, geometry="geometry")
        except Exception:
            # fallback: construct minimal GeoDataFrame
            gdf = gpd.GeoDataFrame(gdf)

    try:
        # If CRS is missing, assume EPSG:4326 (osmnx standard)
        if getattr(gdf, "crs", None) is None:
            gdf = gdf.set_crs(epsg=4326, allow_override=True)
        else:
            # convert to 4326 if it's different
            gdf = gdf.to_crs(epsg=4326)
    except Exception:
        # best-effort: ignore CRS conversion errors
        pass

    return gdf


def save_layer(gdf, filepath: str, driver: Optional[str] = None):
    """Save a GeoDataFrame to disk in a format ArcGIS can read.

    Driver is inferred from the file extension if not provided. Supported
    extensions: .geojson/.json -> GeoJSON, .gpkg -> GPKG, .shp -> ESRI Shapefile.

    This function will coerce non-scalar columns to strings when writing a
    Shapefile (which has field type limitations).
    """
    import geopandas as gpd
    import os

    if gdf is None:
        raise ValueError("gdf is None")

    # infer driver from extension if not provided
    if driver is None:
        ext = os.path.splitext(filepath)[1].lower().lstrip('.')
        if ext in ("geojson", "json"):
            driver = "GeoJSON"
        elif ext in ("gpkg", "gpk"):
            driver = "GPKG"
        elif ext in ("shp",):
            driver = "ESRI Shapefile"
        else:
            driver = "GeoJSON"

    gdf_to_write = gdf.copy()

    if driver == "ESRI Shapefile":
        # Shapefile has strict limitations: field names (<=10 chars) and types.
        # Convert list-like and complex values to strings and shorten field names.
        def make_scalar(x):
            if x is None:
                return None
            if isinstance(x, (list, set, tuple, dict)):
                return str(x)
            if isinstance(x, (str, int, float)):
                return x
            return str(x)

        for col in list(gdf_to_write.columns):
            if col == gdf_to_write.geometry.name:
                continue
            try:
                gdf_to_write[col] = gdf_to_write[col].apply(make_scalar)
            except Exception:
                # fallback - convert entire column to string
                try:
                    gdf_to_write[col] = gdf_to_write[col].astype(str)
                except Exception:
                    pass

        # shorten column names to 10 chars if needed
        rename_map = {}
        used = set()
        for col in gdf_to_write.columns:
            if col == gdf_to_write.geometry.name:
                continue
            short = col[:10]
            i = 1
            while short in used:
                # create a new unique short name
                base = col[:max(1, 10 - len(str(i)))]
                short = f"{base}{i}"
                i += 1
            if short != col:
                rename_map[col] = short
            used.add(short)

        if rename_map:
            gdf_to_write = gdf_to_write.rename(columns=rename_map)

    # Now write using geopandas
    try:
        gdf_to_write.to_file(filepath, driver=driver)
    except Exception as e:
        # Provide a helpful error message if writing fails
        raise RuntimeError(f"Failed to write file '{filepath}' with driver '{driver}': {e}")

    return filepath


def count_healthcare_nearby(
    location: Union[str, Tuple[float, float]],
    radius_m: int = 1000,
    breakdown: bool = False,
    details: bool = False,
):
    """Count nearby healthcare-related OSM elements.

    This searches for common healthcare amenities (hospitals, clinics,
    doctors, pharmacies) within the given radius.
    """
    import osmnx as ox

    lat, lon = _resolve_location(location)
    tags = {
        # healthcare-related amenities
        "amenity": ["hospital", "clinic", "doctors", "pharmacy", "dentist"],
        # some contributors use a dedicated healthcare tag
        "healthcare": True,
    }

    gdf = _geometries_from_point_compat(ox, (lat, lon), tags=tags, dist=radius_m)
    if gdf is None or gdf.empty:
        if details:
            return []
        return {} if breakdown else 0

    # Exclude pharmacies explicitly (some healthcare/amenity values may be 'pharmacy')
    def _is_pharmacy_value(v):
        if v is None:
            return False
        if isinstance(v, (list, set, tuple)):
            return any(str(x).lower() == "pharmacy" for x in v)
        return str(v).lower() == "pharmacy"

    if any(col in gdf.columns for col in ("amenity", "healthcare")):
        def _row_is_pharmacy(row):
            for col in ("amenity", "healthcare"):
                if col in gdf.columns:
                    if _is_pharmacy_value(row.get(col)):
                        return True
            return False

        try:
            mask = gdf.apply(_row_is_pharmacy, axis=1)
            # keep rows that are NOT pharmacies
            gdf = gdf.loc[~mask]
        except Exception:
            # if anything goes wrong with the check, fall back to original gdf
            pass

    if details:
        # produce a list of detail dicts with name, osmid, tags and distance (m)
        def _row_centroid_coords(row):
            try:
                geom = row.geometry
                c = geom.centroid
                return float(c.y), float(c.x)
            except Exception:
                return None, None

        def _haversine_m(lat1, lon1, lat2, lon2):
            # approximate distance in meters between two lat/lon points
            from math import radians, sin, cos, asin, sqrt

            if None in (lat1, lon1, lat2, lon2):
                return None
            R = 6371000.0
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
            c = 2 * asin(min(1, sqrt(a)))
            return R * c

        details_list = []
        for _, row in gdf.iterrows():
            lat2, lon2 = _row_centroid_coords(row)
            dist_m = _haversine_m(lat, lon, lat2, lon2) if lat2 is not None else None
            name = None
            for col in ("name", "operator", "ref"):
                if col in row.index and row[col] not in (None, ""):
                    name = row[col]
                    break
            # collect relevant tags present in the row
            tags_present = {}
            for col in row.index:
                if col in ("geometry",):
                    continue
                val = row[col]
                if val is None:
                    continue
                # include simple scalar or list-like values
                if isinstance(val, (str, int, float)) or isinstance(val, (list, tuple, set)):
                    tags_present[col] = val

            details_list.append({
                "osmid": row.get("osmid"),
                "name": name,
                "distance_m": None if dist_m is None else int(dist_m),
                "tags": tags_present,
            })

        return details_list

    if "osmid" in gdf.columns:
        unique_count = gdf["osmid"].nunique()
    else:
        unique_count = len(gdf)

    if not breakdown:
        return int(unique_count)

    # reuse the same breakdown logic as count_outdoor_activities
    breakdown_counts: Dict[str, int] = {}
    for col in [c for c in gdf.columns if c not in ("geometry",)]:
        series = gdf[col].dropna()
        if series.empty:
            continue
        if series.apply(lambda x: isinstance(x, (list, set, tuple))).any():
            exploded = series.apply(lambda x: list(x) if isinstance(x, (list, set, tuple)) else [x]).explode()
            value_counts = exploded.astype(str).value_counts().to_dict()
        else:
            value_counts = series.astype(str).value_counts().to_dict()
        breakdown_counts[col] = sum(value_counts.values())

    breakdown_counts["__total__"] = int(unique_count)
    return breakdown_counts


if __name__ == "__main__":
    # simple CLI for quick experiments
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Count outdoor activities near a location using OSM (osmnx).")
    parser.add_argument("--location", "-l", required=True, help="Place name or 'lat,lon' tuple")
    parser.add_argument("--radius", "-r", type=int, default=1000, help="Search radius in meters")
    parser.add_argument("--breakdown", action="store_true", help="Return a breakdown of counts per tag")
    parser.add_argument("--check-healthcare", action="store_true", help="Check for nearby healthcare facilities (hospital/clinic/pharmacy)")
    parser.add_argument("--export-file", "-o", help="Optional path to export a healthcare layer (GeoJSON/GPKG/Shapefile).")
    args = parser.parse_args()

    # parse lat,lon input
    loc = args.location
    if "," in loc:
        try:
            parts = [p.strip() for p in loc.split(",")]
            loc = (float(parts[0]), float(parts[1]))
        except Exception:
            pass

    if args.check_healthcare:
        # when exporting, prefer to return the GeoDataFrame via healthcare_layer
        if args.export_file:
            gdf = healthcare_layer(loc, radius_m=args.radius, exclude_pharmacy=True)
            try:
                save_layer(gdf, args.export_file)
                print(f"Exported healthcare layer to {args.export_file}")
            except Exception as e:
                print(json.dumps({"error": str(e)}))
        else:
            res = count_healthcare_nearby(loc, radius_m=args.radius, breakdown=args.breakdown)
            if isinstance(res, dict):
                print(json.dumps(res, indent=2))
            else:
                print(res)
    else:
        # outdoor activities path (no export implemented for this layer)
        res = count_outdoor_activities(loc, radius_m=args.radius, breakdown=args.breakdown)
        if isinstance(res, dict):
            print(json.dumps(res, indent=2))
        else:
            print(res)
