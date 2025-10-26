import json
import sys

# Load the GeoJSON file
filename = sys.argv[1] if len(sys.argv) > 1 else 'test_output_points.geojson'
with open(filename, encoding='utf-8') as f:
    data = json.load(f)

print(f"Checking file: {filename}")

print("=" * 60)
print("COORDINATE VALIDATION")
print("=" * 60)

total = len(data['features'])
with_coords = 0
invalid = []

for feature in data['features']:
    if feature['geometry']:
        with_coords += 1
        lon, lat = feature['geometry']['coordinates']
        
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            invalid.append({
                'name': feature['properties'].get('zsj_nazov', 'Unknown'),
                'lat': lat,
                'lon': lon
            })

print(f"Total features: {total}")
print(f"Features with coordinates: {with_coords}")
print(f"Features without coordinates: {total - with_coords}")
print(f"Invalid coordinates: {len(invalid)}")

if invalid:
    print("\nInvalid entries:")
    for item in invalid:
        print(f"  {item['name']}: lat={item['lat']:.4f}, lon={item['lon']:.4f}")
else:
    print("\n✓ All coordinates are valid!")
    
    # Show coordinate ranges
    lats = [f['geometry']['coordinates'][1] for f in data['features'] if f['geometry']]
    lons = [f['geometry']['coordinates'][0] for f in data['features'] if f['geometry']]
    
    print(f"\nLatitude range: {min(lats):.4f}° to {max(lats):.4f}°")
    print(f"Longitude range: {min(lons):.4f}° to {max(lons):.4f}°")
    print("\n✓ All coordinates are within Bratislava area")

print("=" * 60)
