# Location Tagging Improvements

## What Was Fixed

The `sidelnejednotky_geojson_parser.py` script has been significantly improved to include better location tagging and coordinate generation.

## New Features

### 1. **Approximate Coordinate Generation**
- Added mapping for all Bratislava city districts (mestské časti)
- Generates unique Point coordinates for each ZSJ (Základná sídelná jednotka)
- Uses hash-based offset to ensure different ZSJs within the same district have distinct coordinates

### 2. **Enhanced Location Properties**
Each feature now includes:
- `location`: Short form (e.g., "Hradný svah, Bratislava - Staré Mesto")
- `full_address`: Complete address with district (e.g., "Hradný svah, Bratislava - Staré Mesto, Bratislava I")
- `coord_source`: Indicates how coordinates were generated ("approximate" or "geocoded")

### 3. **Optional Geocoding Support**
- Use `--geocode` flag to fetch real coordinates from OpenStreetMap Nominatim API
- Respects rate limiting (1 second delay between requests)
- Falls back to approximate coordinates if geocoding fails

### 4. **Bratislava District Coverage**
The script now has built-in coordinates for all major Bratislava districts:
- Staré Mesto
- Ružinov
- Petržalka
- Nové Mesto
- Karlova Ves
- Rača
- Vajnory
- Devín
- Devínska Nová Ves
- Dúbravka
- Lamač
- Podunajské Biskupice
- Vrakuňa
- Čunovo
- Jarovce
- Rusovce
- Záhorská Bystrica

## Usage

### Generate with approximate coordinates (fast):
```bash
python sidelnejednotky_geojson_parser.py --points
```

### Generate with geocoding (slower, more accurate):
```bash
python sidelnejednotky_geojson_parser.py --points --geocode
```

### Merge with existing boundary polygons:
```bash
python sidelnejednotky_geojson_parser.py --merge zsj_hranice.geojson
```

## Output Files

The script generates 5 GeoJSON files with Point geometries:
1. `bratislava_population_points.geojson` - All data
2. `bratislava_population_total_points.geojson` - Total population
3. `bratislava_population_trvalý_pobyt_points.geojson` - Permanent residents
4. `bratislava_population_inde_sr_points.geojson` - Residing elsewhere in Slovakia
5. `bratislava_population_zahraničí_points.geojson` - Residing abroad

## Example Feature

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [17.1056, 48.1483]
  },
  "properties": {
    "kraj_nazov": "Bratislavský kraj",
    "okres_nazov": "Bratislava I",
    "obec_nazov": "Bratislava - Staré Mesto",
    "zsj_kod": "2040640",
    "zsj_nazov": "Hradný svah",
    "pop_trvalý_pobyt": 192,
    "pop_inde_sr": 4,
    "pop_zahraničí": 12,
    "pop_total": 208,
    "location": "Hradný svah, Bratislava - Staré Mesto",
    "full_address": "Hradný svah, Bratislava - Staré Mesto, Bratislava I",
    "coord_source": "approximate"
  }
}
```

## Benefits

1. **Better Visualization**: All features now have coordinates and can be displayed on a map
2. **More Context**: Location strings make features easier to understand
3. **Flexible**: Can use approximate coordinates, real geocoding, or merge with polygon boundaries
4. **No External Dependencies**: Approximate coordinates work without internet connection
5. **Unique Coordinates**: Each ZSJ has distinct coordinates even within the same district

## Validation

View the generated GeoJSON files at: https://geojson.io
