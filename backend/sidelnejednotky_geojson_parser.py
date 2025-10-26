#!/usr/bin/env python3
"""
CSV to GeoJSON converter
Konvertuje CSV s WKT geometriami na GeoJSON
"""

import sys
import json

try:
    import pandas as pd
    from shapely import wkt
    from shapely.geometry import mapping
    from shapely.ops import transform
    import pyproj
except ImportError as e:
    print("✗ CHYBA: Potrebuješ nainštalovať potrebné knižnice")
    print("  Spusti: pip install pandas shapely pyproj")
    sys.exit(1)

def csv_to_geojson(input_csv: str, output_geojson: str = None, geom_column: str = 'geom',
                   source_epsg: int = 5514, target_epsg: int = 4326):
    """
    Konvertuje CSV s WKT geometriami na GeoJSON
    
    Args:
        input_csv: Vstupný CSV súbor
        output_geojson: Výstupný GeoJSON súbor
        geom_column: Názov stĺpca s geometriou
        source_epsg: Zdrojový EPSG kód (5514 = S-JTSK, slovenský systém)
        target_epsg: Cieľový EPSG kód (4326 = WGS84, GPS súradnice)
    """
    print("=" * 80)
    print("CSV TO GEOJSON CONVERTER")
    print("=" * 80)
    
    # Načítaj CSV
    print(f"\n📂 Načítavam: {input_csv}")
    try:
        df = pd.read_csv(input_csv, encoding='utf-8', low_memory=False)
    except FileNotFoundError:
        print(f"✗ CHYBA: Súbor {input_csv} neexistuje!")
        sys.exit(1)
    except Exception as e:
        print(f"✗ CHYBA pri čítaní CSV: {e}")
        sys.exit(1)
    
    print(f"✓ Načítaných {len(df)} riadkov")
    
    # Skontroluj či existuje stĺpec s geometriou
    if geom_column not in df.columns:
        print(f"\n✗ CHYBA: Stĺpec '{geom_column}' neexistuje!")
        print(f"\nDostupné stĺpce:")
        for col in df.columns:
            print(f"  - {col}")
        sys.exit(1)
    
    # Nastav transformáciu súradníc
    print(f"\n🌍 Transformujem súradnice:")
    print(f"   Zo: EPSG:{source_epsg} (S-JTSK)")
    print(f"   Do: EPSG:{target_epsg} (WGS84 - GPS)")
    
    transformer = pyproj.Transformer.from_crs(
        f"EPSG:{source_epsg}",
        f"EPSG:{target_epsg}",
        always_xy=True
    )
    
    # Vytvor GeoJSON features
    print(f"\n🔄 Konvertujem geometrie...")
    features = []
    errors = 0
    
    for idx, row in df.iterrows():
        try:
            # Parsuj WKT geometriu
            geom_wkt = row[geom_column]
            if pd.isna(geom_wkt) or geom_wkt == '':
                errors += 1
                continue
            
            geometry = wkt.loads(geom_wkt)
            
            # Transformuj do WGS84
            geometry_wgs84 = transform(transformer.transform, geometry)
            
            # Vytvor properties (všetky stĺpce okrem geometrie)
            properties = {}
            for col in df.columns:
                if col != geom_column:
                    val = row[col]
                    # Konvertuj pandas typy na Python typy
                    if pd.isna(val):
                        properties[col] = None
                    elif isinstance(val, (pd.Timestamp, pd.Timedelta)):
                        properties[col] = str(val)
                    else:
                        properties[col] = val
            
            # Vytvor GeoJSON feature
            feature = {
                "type": "Feature",
                "geometry": mapping(geometry_wgs84),
                "properties": properties
            }
            features.append(feature)
            
            if (idx + 1) % 100 == 0:
                print(f"  Spracovaných {idx + 1}/{len(df)} riadkov...")
                
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  ⚠ Chyba na riadku {idx + 1}: {str(e)[:100]}")
    
    print(f"✓ Úspešne konvertovaných: {len(features)} features")
    if errors > 0:
        print(f"  ⚠ Chýb pri konverzii: {errors}")
    
    # Zobraz ukážku súradníc
    if len(features) > 0:
        first_coords = features[0]['geometry']['coordinates']
        if features[0]['geometry']['type'] == 'MultiPolygon':
            sample_coord = first_coords[0][0][0]
        elif features[0]['geometry']['type'] == 'Polygon':
            sample_coord = first_coords[0][0]
        else:
            sample_coord = first_coords[0] if isinstance(first_coords[0], list) else first_coords
        
        print(f"\n✓ Ukážka transformovaných súradníc:")
        print(f"   Longitude: {sample_coord[0]:.6f}°")
        print(f"   Latitude: {sample_coord[1]:.6f}°")
    
    # Vytvor GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": f"urn:ogc:def:crs:EPSG::{target_epsg}"
            }
        },
        "features": features
    }
    
    # Vytvor názov výstupného súboru
    if output_geojson is None:
        if input_csv.endswith('.csv'):
            output_geojson = input_csv.replace('.csv', '.geojson')
        else:
            output_geojson = f"{input_csv}.geojson"
    
    # Ulož GeoJSON
    print(f"\n💾 Ukladám GeoJSON...")
    with open(output_geojson, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    
    file_size = len(json.dumps(geojson)) / 1024 / 1024
    print(f"✓ Uložené do: {output_geojson}")
    print(f"✓ Veľkosť súboru: {file_size:.2f} MB")
    
    print("\n" + "=" * 80)
    print("HOTOVO!")
    print("=" * 80)
    print(f"\nVizualizuj na:")
    print(f"  • https://geojson.io (ak je súbor < 10MB)")
    print(f"  • QGIS (pre väčšie súbory)")
    print(f"  • Mapbox Studio")
    print(f"  • Leaflet / OpenLayers")
    
    return output_geojson

def create_simplified_geojson(input_csv: str, output_geojson: str = None, 
                              keep_columns: list = None):
    """
    Vytvorí zjednodušený GeoJSON s len vybranými stĺpcami
    """
    print("\n📦 Vytváram zjednodušený GeoJSON...")
    
    df = pd.read_csv(input_csv, encoding='utf-8', low_memory=False)
    
    # Default stĺpce ak nie sú špecifikované
    if keep_columns is None:
        keep_columns = ['nazov_zsj', 'nazov_okre', 'kod_zsj', 'nazov_co', 'nazov_utj']
    
    # Filter len existujúce stĺpce
    keep_columns = [col for col in keep_columns if col in df.columns]
    keep_columns.append('geom')  # Vždy zahrnúť geometriu
    
    print(f"  Ponechávam stĺpce: {', '.join([c for c in keep_columns if c != 'geom'])}")
    
    # Vytvor zjednodušený DataFrame
    df_simple = df[keep_columns].copy()
    
    # Vytvor dočasný CSV
    temp_csv = input_csv.replace('.csv', '_temp_simple.csv')
    df_simple.to_csv(temp_csv, index=False, encoding='utf-8')
    
    # Konvertuj na GeoJSON
    if output_geojson is None:
        output_geojson = input_csv.replace('.csv', '_simple.geojson')
    
    result = csv_to_geojson(temp_csv, output_geojson)
    
    # Vymaž dočasný súbor
    import os
    os.remove(temp_csv)
    
    return result

def show_preview(input_csv: str, n_rows: int = 5):
    """
    Zobraz náhľad prvých N riadkov
    """
    df = pd.read_csv(input_csv, encoding='utf-8', low_memory=False, nrows=n_rows)
    
    print("\n" + "=" * 80)
    print(f"NÁHĽAD PRVÝCH {n_rows} RIADKOV")
    print("=" * 80)
    
    # Zobraz bez geometrie (je príliš dlhá)
    cols_to_show = [col for col in df.columns if col != 'geom']
    print(df[cols_to_show].to_string())
    
    if 'geom' in df.columns:
        print(f"\n(Stĺpec 'geom' obsahuje geometrie - nezobrazený)")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Konvertor CSV s WKT geometriami na GeoJSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Príklady použitia:
  python csv_to_geojson.py data.csv
  python csv_to_geojson.py data.csv -o output.geojson
  python csv_to_geojson.py data.csv --simple
  python csv_to_geojson.py data.csv --preview
  python csv_to_geojson.py data.csv --columns nazov_zsj,nazov_okre,kod_zsj
        """
    )
    parser.add_argument('input', help='Vstupný CSV súbor')
    parser.add_argument('-o', '--output', help='Výstupný GeoJSON súbor (voliteľné)')
    parser.add_argument('--geom-column', default='geom', 
                       help='Názov stĺpca s geometriou (default: geom)')
    parser.add_argument('--source-epsg', type=int, default=5514,
                       help='Zdrojový EPSG kód (default: 5514 = S-JTSK)')
    parser.add_argument('--target-epsg', type=int, default=4326,
                       help='Cieľový EPSG kód (default: 4326 = WGS84)')
    parser.add_argument('--simple', action='store_true',
                       help='Vytvor zjednodušený GeoJSON s len základnými stĺpcami')
    parser.add_argument('--columns', 
                       help='Stĺpce na ponechanie (oddelené čiarkou, použiť s --simple)')
    parser.add_argument('--preview', action='store_true',
                       help='Zobraz len náhľad dát bez konverzie')
    
    args = parser.parse_args()
    
    # Ak chce len náhľad
    if args.preview:
        show_preview(args.input)
        return
    
    # Ak chce zjednodušený GeoJSON
    if args.simple:
        keep_cols = None
        if args.columns:
            keep_cols = [c.strip() for c in args.columns.split(',')]
        create_simplified_geojson(args.input, args.output, keep_cols)
    else:
        # Štandardná konverzia
        csv_to_geojson(args.input, args.output, args.geom_column, 
                      args.source_epsg, args.target_epsg)

if __name__ == "__main__":
    main()