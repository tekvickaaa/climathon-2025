import requests
import json

# Overpass API endpoint
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Overpass Query Language (QL) dotaz pre Bratislavu
# Kategórie: zdravotnícke (amenity=dentist, doctor, hospital, clinic, pharmacy)
# + sociálne zariadenia (amenity=social_facility)
overpass_query = """
[out:json][timeout:60];
area["name"="Bratislava"]["admin_level"=8]->.searchArea;
(
  node["amenity"="dentist"](area.searchArea);
  node["amenity"="doctors"](area.searchArea);
  node["amenity"="hospital"](area.searchArea);
  node["amenity"="clinic"](area.searchArea);
  node["amenity"="pharmacy"](area.searchArea);
  node["amenity"="social_facility"](area.searchArea);
  node["healthcare"](area.searchArea);
  
  way["amenity"="dentist"](area.searchArea);
  way["amenity"="doctors"](area.searchArea);
  way["amenity"="hospital"](area.searchArea);
  way["amenity"="clinic"](area.searchArea);
  way["amenity"="pharmacy"](area.searchArea);
  way["amenity"="social_facility"](area.searchArea);
  way["healthcare"](area.searchArea);
);
out center;
>;
out skel qt;
"""

# Odoslanie dotazu na Overpass API
response = requests.post(OVERPASS_URL, data={"data": overpass_query})

if response.status_code == 200:
    data = response.json()
    
    # Príprava GeoJSON štruktúry podľa tvojho formátu
    geojson_output = {
        "type": "FeatureCollection",
        "name": "bratislava_healthcare_social_facilities",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features": []
    }
    
    # Spracovanie každého elementu z OSM
    for element in data.get("elements", []):
        # Zistenie súradníc (pre "node" priamo, pre "way" použije "center")
        if element["type"] == "node":
            lon, lat = element["lon"], element["lat"]
        elif element["type"] == "way" and "center" in element:
            lon, lat = element["center"]["lon"], element["center"]["lat"]
        else:
            continue  # Preskočiť, ak nie sú súradnice
        
        # Získanie tagov (atribútov)
        tags = element.get("tags", {})
        
        # Vytvorenie feature objektu podľa tvojho formátu
        feature = {
            "type": "Feature",
            "properties": {
                "element": element["type"],
                "id": element["id"],
                "amenity": tags.get("amenity"),
                "healthcare": tags.get("healthcare"),
                "healthcare:speciality": tags.get("healthcare:speciality"),
                "social_facility": tags.get("social_facility"),
                "social_facility:for": tags.get("social_facility:for"),
                "name": tags.get("name"),
                "opening_hours": tags.get("opening_hours"),
                "phone": tags.get("phone"),
                "website": tags.get("website"),
                "addr:street": tags.get("addr:street"),
                "addr:housenumber": tags.get("addr:housenumber"),
                "addr:city": tags.get("addr:city"),
                "addr:postcode": tags.get("addr:postcode"),
                "operator": tags.get("operator"),
                "wheelchair": tags.get("wheelchair"),
                "email": tags.get("email"),
                "capacity": tags.get("capacity"),
                "beds": tags.get("beds"),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            }
        }
        
        geojson_output["features"].append(feature)
    
    # Uloženie do súboru
    output_filename = "bratislava_healthcare_social_facilities.geojson"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(geojson_output, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Stiahnuté {len(geojson_output['features'])} zariadení")
    print(f"✅ Uložené do: {output_filename}")
    
    # Kategorizácia podľa typu (pre debugging/štatistiku)
    categories = {}
    for feature in geojson_output["features"]:
        amenity = feature["properties"]["amenity"]
        healthcare = feature["properties"]["healthcare"]
        category = amenity or healthcare or "unknown"
        categories[category] = categories.get(category, 0) + 1
    
    print("\n📊 Rozdelenie podľa kategórie:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

else:
    print(f"❌ Chyba pri sťahovaní: {response.status_code}")
    print(response.text)
