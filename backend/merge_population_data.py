#!/usr/bin/env python3
"""
Spojenie geometrií zo ZSJ CSV s populačnými dátami
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

def merge_and_convert(geometry_csv: str, population_csv: str, output_geojson: str = None,
                      geom_column: str = 'geom', source_epsg: int = 5514):
    """
    Spojí geometrie s populačnými dátami a vytvorí GeoJSON
    
    Args:
        geometry_csv: CSV s geometriami (obsahuje stĺpce: geom, kod_zsj)
        population_csv: CSV s populáciou (obsahuje: Základná sídelná jednotka - kód, atď.)
        output_geojson: Výstupný GeoJSON súbor
        geom_column: Názov stĺpca s geometriou
        source_epsg: Zdrojový EPSG kód (5514 = S-JTSK)
    """
    print("=" * 80)
    print("MERGE GEOMETRIES + POPULATION DATA")
    print("=" * 80)
    
    # 1. Načítaj geometrie
    print(f"\n📂 Načítavam geometrie: {geometry_csv}")
    try:
        df_geom = pd.read_csv(geometry_csv, encoding='utf-8', low_memory=False)
    except Exception as e:
        print(f"✗ CHYBA: {e}")
        sys.exit(1)
    
    print(f"✓ Načítaných {len(df_geom)} geometrií")
    
    # 2. Načítaj populačné dáta
    print(f"\n📊 Načítavam populačné dáta: {population_csv}")
    try:
        df_pop = pd.read_csv(population_csv, encoding='utf-8')
    except Exception as e:
        print(f"✗ CHYBA: {e}")
        sys.exit(1)
    
    print(f"✓ Načítaných {len(df_pop)} záznamov")
    
    # 3. Identifikuj stĺpce s kódmi ZSJ
    geom_code_col = None
    for col in ['kod_zsj', 'ic_zsj', 'zsj_kod', 'code']:
        if col in df_geom.columns:
            geom_code_col = col
            break
    
    if not geom_code_col:
        print("✗ CHYBA: Nenašiel sa stĺpec s kódom ZSJ v geometriách!")
        print(f"Dostupné stĺpce: {', '.join(df_geom.columns[:20])}")
        sys.exit(1)
    
    pop_code_col = 'Základná sídelná jednotka - kód'
    if pop_code_col not in df_pop.columns:
        print(f"✗ CHYBA: Nenašiel sa stĺpec '{pop_code_col}' v populačných dátach!")
        sys.exit(1)
    
    print(f"\n🔗 Spájam podľa:")
    print(f"   Geometrie: {geom_code_col}")
    print(f"   Populácia: {pop_code_col}")
    
    # 4. Premenuj stĺpce v populačných dátach na kratšie názvy
    pop_rename = {
        'Kraj - kód': 'kraj_kod',
        'Kraj - názov': 'kraj_nazov',
        'Okres - kód': 'okres_kod',
        'Okres - názov': 'okres_nazov',
        'Obec - kód': 'obec_kod',
        'Obec - názov': 'obec_nazov',
        'Základná sídelná jednotka - kód': 'zsj_kod',
        'Základná sídelná jednotka - názov': 'zsj_nazov',
        'Miesto trvalého pobytu alebo obvyklého bydliska - zhodné s trvalým pobytom': 'pop_trvaly_pobyt',
        'Miesto trvalého pobytu alebo obvyklého bydliska - inde v SR': 'pop_inde_sr',
        'Miesto trvalého pobytu alebo obvyklého bydliska - v zahraničí': 'pop_zahranicie',
        'Spolu': 'pop_total'
    }
    df_pop = df_pop.rename(columns=pop_rename)
    
    # 5. Konvertuj kódy na string (pre istotu)
    df_geom[geom_code_col] = df_geom[geom_code_col].astype(str).str.strip()
    df_pop['zsj_kod'] = df_pop['zsj_kod'].astype(str).str.strip()
    
    # Extrahuj posledných 7 číslic z geometrických kódov (napr. SK01012045520 -> 2045520)
    df_geom['zsj_kod_short'] = df_geom[geom_code_col].str[-7:]
    
    print(f"\n   Príklady kódov:")
    print(f"   Geometrie (pôvodné): {df_geom[geom_code_col].head(3).tolist()}")
    print(f"   Geometrie (extrahované): {df_geom['zsj_kod_short'].head(3).tolist()}")
    print(f"   Populácia: {df_pop['zsj_kod'].head(3).tolist()}")
    
    # 6. Spoj dataframes
    print(f"\n🔄 Spájam dáta...")
    df_merged = df_geom.merge(
        df_pop,
        left_on='zsj_kod_short',
        right_on='zsj_kod',
        how='left'
    )
    
    matched = df_merged['pop_total'].notna().sum()
    print(f"✓ Spojených: {matched} / {len(df_geom)} geometrií")
    
    if matched == 0:
        print("\n⚠ VAROVANIE: Žiadne záznamy neboli spojené!")
        print("\nPríklady kódov z geometrií (pôvodné):")
        print(df_geom[geom_code_col].head(5).tolist())
        print("\nPríklady kódov z geometrií (extrahované):")
        print(df_geom['zsj_kod_short'].head(5).tolist())
        print("\nPríklady kódov z populácie:")
        print(df_pop['zsj_kod'].head(5).tolist())
        sys.exit(1)
    
    # 7. Nastav transformáciu súradníc
    print(f"\n🌍 Transformujem súradnice z S-JTSK do WGS84...")
    transformer = pyproj.Transformer.from_crs(
        f"EPSG:{source_epsg}",
        "EPSG:4326",
        always_xy=True
    )
    
    # 8. Vytvor GeoJSON features
    print(f"\n🗺️  Vytváram GeoJSON features...")
    features = []
    errors = 0
    no_geom = 0
    
    for idx, row in df_merged.iterrows():
        try:
            # Parsuj WKT geometriu
            geom_wkt = row[geom_column]
            if pd.isna(geom_wkt) or geom_wkt == '':
                no_geom += 1
                continue
            
            geometry = wkt.loads(geom_wkt)
            
            # Transformuj do WGS84
            geometry_wgs84 = transform(transformer.transform, geometry)
            
            # Vytvor properties - iba dôležité
            properties = {
                'zsj_kod': str(row.get('zsj_kod')) if pd.notna(row.get('zsj_kod')) else None,
                'zsj_nazov': str(row.get('zsj_nazov')) if pd.notna(row.get('zsj_nazov')) else None,
                'okres_nazov': str(row.get('okres_nazov')) if pd.notna(row.get('okres_nazov')) else None,
                'obec_nazov': str(row.get('obec_nazov')) if pd.notna(row.get('obec_nazov')) else None,
                'pop_trvaly_pobyt': int(row['pop_trvaly_pobyt']) if pd.notna(row.get('pop_trvaly_pobyt')) else 0,
                'pop_inde_sr': int(row['pop_inde_sr']) if pd.notna(row.get('pop_inde_sr')) else 0,
                'pop_zahranicie': int(row['pop_zahranicie']) if pd.notna(row.get('pop_zahranicie')) else 0,
                'pop_total': int(row['pop_total']) if pd.notna(row.get('pop_total')) else 0
            }
            
            # Pridaj z geometrií ak nie je v populačných dátach
            if pd.isna(properties['zsj_nazov']) and 'nazov_zsj' in row:
                properties['zsj_nazov'] = row['nazov_zsj']
            if pd.isna(properties['okres_nazov']) and 'nazov_okre' in row:
                properties['okres_nazov'] = row['nazov_okre']
            
            # Vytvor GeoJSON feature
            feature = {
                "type": "Feature",
                "geometry": mapping(geometry_wgs84),
                "properties": properties
            }
            features.append(feature)
            
            if (idx + 1) % 100 == 0:
                print(f"  Spracovaných {idx + 1}/{len(df_merged)} riadkov...")
                
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  ⚠ Chyba na riadku {idx + 1}: {str(e)[:100]}")
    
    print(f"\n✓ Úspešne vytvorených: {len(features)} features")
    if no_geom > 0:
        print(f"  ⚠ Bez geometrie: {no_geom}")
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
        
        # Ukážka prvého feature
        sample = features[0]['properties']
        print(f"\n📋 Ukážka dát prvej ZSJ:")
        print(f"   Názov: {sample['zsj_nazov']}")
        print(f"   Okres: {sample['okres_nazov']}")
        print(f"   Populácia spolu: {sample['pop_total']}")
        print(f"   - Trvalý pobyt: {sample['pop_trvaly_pobyt']}")
        print(f"   - Inde v SR: {sample['pop_inde_sr']}")
        print(f"   - Zahraničí: {sample['pop_zahranicie']}")
    
    # 9. Vytvor GeoJSON
    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:EPSG::4326"
            }
        },
        "features": features
    }
    
    # 10. Ulož GeoJSON
    if output_geojson is None:
        output_geojson = geometry_csv.replace('.csv', '_with_population.geojson')
    
    print(f"\n💾 Ukladám GeoJSON...")
    
    # Konvertuj NaN na None pre validný JSON
    geojson_str = json.dumps(geojson, ensure_ascii=False, indent=2, allow_nan=False)
    
    with open(output_geojson, 'w', encoding='utf-8') as f:
        f.write(geojson_str)
    
    file_size = len(json.dumps(geojson)) / 1024 / 1024
    print(f"✓ Uložené do: {output_geojson}")
    print(f"✓ Veľkosť súboru: {file_size:.2f} MB")
    
    # 11. Štatistiky
    total_pop = sum(f['properties']['pop_total'] for f in features)
    print(f"\n📊 ŠTATISTIKY:")
    print(f"   Celková populácia: {total_pop:,} obyvateľov")
    print(f"   Počet ZSJ: {len(features)}")
    print(f"   Priemerná populácia na ZSJ: {total_pop//len(features) if features else 0}")
    
    print("\n" + "=" * 80)
    print("HOTOVO!")
    print("=" * 80)
    print(f"\nVizualizuj na:")
    print(f"  • https://geojson.io")
    print(f"  • QGIS")
    print(f"  • Mapbox Studio")
    
    return output_geojson

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Spoj geometrie ZSJ s populačnými dátami a vytvor GeoJSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Príklady použitia:
  python merge.py geometries.csv population.csv
  python merge.py geometries.csv population.csv -o bratislava.geojson
  python merge.py filtered_geom.csv bratislava_data.csv

Vstupné súbory:
  1. CSV s geometriami (musí obsahovať: geom, kod_zsj/ic_zsj)
  2. CSV s populáciou (musí obsahovať: Základná sídelná jednotka - kód, Spolu, atď.)
        """
    )
    parser.add_argument('geometry_csv', help='CSV súbor s geometriami')
    parser.add_argument('population_csv', help='CSV súbor s populačnými dátami')
    parser.add_argument('-o', '--output', help='Výstupný GeoJSON súbor (voliteľné)')
    parser.add_argument('--geom-column', default='geom',
                       help='Názov stĺpca s geometriou (default: geom)')
    parser.add_argument('--source-epsg', type=int, default=5514,
                       help='Zdrojový EPSG kód (default: 5514 = S-JTSK)')
    
    args = parser.parse_args()
    
    merge_and_convert(
        args.geometry_csv,
        args.population_csv,
        args.output,
        args.geom_column,
        args.source_epsg
    )

if __name__ == "__main__":
    main()