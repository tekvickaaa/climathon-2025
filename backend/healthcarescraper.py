"""Scraper pre zdravotnícke zariadenia Bratislavského samosprávneho kraja.

Extrahuje dáta zo stránky https://www.e-vuc.sk/bsk/zdravotnictvo/
a exportuje ich do formátov kompatibilných s ArcGIS (GeoJSON, GeoPackage, Shapefile).
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from typing import List, Dict, Optional
import re
import time
from urllib.parse import urljoin


# URL pre jednotlivé okresy Bratislavy
BRATISLAVA_URLS = {
    'Bratislava I': {
        'ambulantne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ambulantne-zdravotnicke-zariadenia/bratislava-i.html?page_id=61870',
        'ustavne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ustavne-zdravotnicke-zariadenia/bratislava-i.html?page_id=61713'
    },
    'Bratislava II': {
        'ambulantne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ambulantne-zdravotnicke-zariadenia/bratislava-ii.html?page_id=61869',
        'ustavne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ustavne-zdravotnicke-zariadenia/bratislava-ii.html?page_id=61712'
    },
    'Bratislava III': {
        'ambulantne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ambulantne-zdravotnicke-zariadenia/bratislava-iii.html?page_id=60143',
        'ustavne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ustavne-zdravotnicke-zariadenia/bratislava-iii.html?page_id=61711'
    },
    'Bratislava IV': {
        'ambulantne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ambulantne-zdravotnicke-zariadenia/bratislava-iv.html?page_id=60144',
        'ustavne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ustavne-zdravotnicke-zariadenia/bratislava-iv.html?page_id=61710'
    },
    'Bratislava V': {
        'ambulantne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ambulantne-zdravotnicke-zariadenia/bratislava-v.html?page_id=60152',
        'ustavne': 'https://www.e-vuc.sk/bsk/zdravotnictvo/ustavne-zdravotnicke-zariadenia/bratislava-v.html?page_id=61709'
    }
}


def geocode_address(address: str, city: str = "Bratislava") -> Optional[tuple]:
    """Geokóduje adresu pomocou Nominatim API."""
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError
        
        geolocator = Nominatim(user_agent="bsk_health_scraper")
        full_address = f"{address}, {city}, Slovakia"
        
        time.sleep(1)  # rate limiting
        location = geolocator.geocode(full_address, timeout=10)
        
        if location:
            return (location.latitude, location.longitude)
        return None
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        print(f"  [!] Chyba pri geokódovaní '{address}': {e}")
        return None
    except ImportError:
        print("  [!] Pre geokódovanie inštaluj: pip install geopy")
        return None


def parse_facility_from_link(link_elem, base_url: str, okres: str, typ_zariadenia: str) -> Optional[Dict]:
    """Parsuje zariadenie z linku na zoznamovej stránke."""
    try:
        facility = {}
        
        # Názov zariadenia je text linku
        nazov = link_elem.get_text(strip=True)
        if not nazov or len(nazov) < 3:
            return None
        
        facility['nazov'] = nazov
        facility['okres'] = okres
        facility['typ_zariadenia'] = typ_zariadenia
        
        # URL detail stránky
        href = link_elem.get('href')
        if href:
            facility['detail_url'] = urljoin(base_url, href)
        
        # Extrakcia typu ambulancie/služby z názvu
        if 'ambulancia' in nazov.lower():
            facility['kategoria'] = 'Ambulancia'
        elif 'poliklinika' in nazov.lower():
            facility['kategoria'] = 'Poliklinika'
        elif 'nemocnica' in nazov.lower():
            facility['kategoria'] = 'Nemocnica'
        elif 'zdravotné stredisko' in nazov.lower():
            facility['kategoria'] = 'Zdravotné stredisko'
        elif 'jednodňová' in nazov.lower():
            facility['kategoria'] = 'Jednodňová starostlivosť'
        elif 'svalz' in nazov.lower():
            facility['kategoria'] = 'SVaLZ'
        else:
            facility['kategoria'] = 'Iné'
        
        # Hľadáme operátora v zátvorkách
        operator_match = re.search(r'\(([^)]+)\)\s*$', nazov)
        if operator_match:
            facility['operator'] = operator_match.group(1).strip()
        
        # Text okolo linku môže obsahovať dodatočné info
        parent = link_elem.parent
        if parent:
            text = parent.get_text(separator=' ', strip=True)
            
            # Kód zariadenia (formát: XX-XXXXXXXX-AXXXX)
            kod_match = re.search(r'\b(\d{2}-\d{8}-A\d{4,5})\b', text)
            if kod_match:
                facility['kod'] = kod_match.group(1)
        
        return facility
    except Exception as e:
        print(f"  [!] Chyba pri parsovaní: {e}")
        return None


def fetch_facility_details(url: str, facility: Dict) -> Dict:
    """Získa detaily zariadenia z jeho detail stránky."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Celý text stránky
        text = soup.get_text(separator='\n', strip=True)
        
        # Adresa - hľadáme ulicu a PSČ
        # Formát: Ulica číslo, PSČ Mesto alebo len PSČ Mesto
        address_patterns = [
            r'([A-ZÁČĎÉÍĽŇÓÔŔŠŤÚÝŽ][\w\s\.-]+\d+[a-zA-Z]?)\s*,?\s*(\d{3}\s*\d{2})\s+([A-ZÁČĎÉÍĽŇÓÔŔŠŤÚÝŽ][\w\s-]+)',
            r'(\d{3}\s*\d{2})\s+([A-ZÁČĎÉÍĽŇÓÔŔŠŤÚÝŽ][\w\s-]+)',
        ]
        
        for pattern in address_patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 3:
                    facility['ulica'] = match.group(1).strip()
                    facility['psc'] = match.group(2).replace(' ', '')
                    facility['mesto'] = match.group(3).strip()
                elif len(match.groups()) == 2:
                    facility['psc'] = match.group(1).replace(' ', '')
                    facility['mesto'] = match.group(2).strip()
                break
        
        # Telefón
        tel_patterns = [
            r'Tel\.:?\s*([\d\s/+-]+)',
            r'Telefón:?\s*([\d\s/+-]+)',
            r'T:?\s*(\+?\d{3,4}[\s/]?\d{3,4}[\s/]?\d{3,4})',
        ]
        for pattern in tel_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tel = match.group(1).strip()
                if len(tel) >= 9:  # minimálna dĺžka telefónneho čísla
                    facility['telefon'] = tel
                    break
        
        # Email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        if email_match:
            facility['email'] = email_match.group(0)
        
        # Web
        web_patterns = [
            r'(www\.[\w\.-]+\.\w+)',
            r'(https?://[\w\.-]+\.\w+)',
        ]
        for pattern in web_patterns:
            match = re.search(pattern, text)
            if match:
                facility['web'] = match.group(1)
                break
        
        # Špecializácie (v zátvorkách po názve)
        spec_match = re.search(r'\(([^)]+)\)\s*\d{2}-\d{8}', text)
        if spec_match:
            facility['specializacie'] = spec_match.group(1).strip()
        
    except Exception as e:
        print(f"  [!] Chyba pri získavaní detailov z {url}: {e}")
    
    return facility


def scrape_okres_page(url: str, okres: str, typ_zariadenia: str, 
                      fetch_details: bool = False) -> List[Dict]:
    """Scrapuje jednu stránku okresu."""
    facilities = []
    
    print(f"  Spracovávam: {okres} - {typ_zariadenia}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except requests.RequestException as e:
        print(f"  [!] Chyba pri sťahovaní {url}: {e}")
        return []
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Linky na zariadenia
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link.get('href', '')
        
        # Filtrujeme len relevantné linky na zariadenia
        if 'zdravotnictvo/ambulantne' in href or 'zdravotnictvo/ustavne' in href:
            # Preskočíme linky na okresy
            if any(x in href.lower() for x in ['bratislava-i.html', 'bratislava-ii.html', 
                                                 'bratislava-iii.html', 'bratislava-iv.html', 
                                                 'bratislava-v.html']):
                continue
            
            facility = parse_facility_from_link(link, url, okres, typ_zariadenia)
            
            if facility and facility.get('nazov'):
                # Získanie detailov zo samostatnej stránky
                if fetch_details and 'detail_url' in facility:
                    time.sleep(0.5)  # rate limiting
                    facility = fetch_facility_details(facility['detail_url'], facility)
                
                facilities.append(facility)
    
    print(f"    → Nájdených {len(facilities)} zariadení")
    return facilities


def scrape_bsk_health_facilities(geocode: bool = False, 
                                  fetch_details: bool = True,
                                  okresy: Optional[List[str]] = None) -> List[Dict]:
    """Scrapuje všetky zdravotnícke zariadenia z BSK.
    
    Args:
        geocode: Ak True, pokúsi sa geokódovať adresy
        fetch_details: Ak True, načíta detaily z každej podstránky (pomalšie)
        okresy: Zoznam okresov na scrapovanie, None = všetky
    
    Returns:
        List[Dict]: Zoznam zariadení
    """
    all_facilities = []
    
    # Ak nie sú špecifikované okresy, použijeme všetky
    if okresy is None:
        okresy = list(BRATISLAVA_URLS.keys())
    
    print("="*80)
    print("SCRAPOVANIE ZDRAVOTNÍCKYCH ZARIADENÍ BSK")
    print("="*80)
    
    for okres in okresy:
        if okres not in BRATISLAVA_URLS:
            print(f"[!] Neznámy okres: {okres}")
            continue
        
        urls = BRATISLAVA_URLS[okres]
        
        # Ambulantné zariadenia
        facilities = scrape_okres_page(
            urls['ambulantne'], 
            okres, 
            'Ambulantné',
            fetch_details=fetch_details
        )
        all_facilities.extend(facilities)
        
        time.sleep(1)  # rate limiting medzi requestami
        
        # Ústavné zariadenia
        facilities = scrape_okres_page(
            urls['ustavne'], 
            okres, 
            'Ústavné',
            fetch_details=fetch_details
        )
        all_facilities.extend(facilities)
        
        time.sleep(1)
    
    # Odstránenie duplicít podľa kódu alebo názvu
    unique_facilities = []
    seen_codes = set()
    seen_names = set()
    
    for fac in all_facilities:
        kod = fac.get('kod', '')
        nazov = fac.get('nazov', '')
        
        # Preferujeme identifikáciu podľa kódu
        if kod and kod not in seen_codes:
            seen_codes.add(kod)
            unique_facilities.append(fac)
        elif not kod and nazov and nazov not in seen_names:
            seen_names.add(nazov)
            unique_facilities.append(fac)
    
    print("\n" + "="*80)
    print(f"CELKOM: {len(unique_facilities)} unikátnych zariadení")
    print("="*80)
    
    # Geokódovanie
    if geocode and unique_facilities:
        print("\nGeokódujem adresy...")
        for i, fac in enumerate(unique_facilities, 1):
            if 'ulica' in fac and 'mesto' in fac:
                address = fac['ulica']
                city = fac['mesto']
                coords = geocode_address(address, city)
                if coords:
                    fac['lat'] = coords[0]
                    fac['lon'] = coords[1]
                    print(f"  [{i}/{len(unique_facilities)}] {fac['nazov'][:50]} ✓")
                else:
                    print(f"  [{i}/{len(unique_facilities)}] {fac['nazov'][:50]} ✗")
    
    return unique_facilities


def export_to_geodata(facilities: List[Dict], 
                      output_path: str,
                      driver: Optional[str] = None):
    """Exportuje zariadenia do geo formátu (GeoJSON/GPKG/Shapefile)."""
    if not facilities:
        print("[!] Žiadne dáta na export")
        return
    
    # DataFrame
    df = pd.DataFrame(facilities)
    
    # Ak máme súradnice, vytvoríme GeoDataFrame
    if 'lat' in df.columns and 'lon' in df.columns:
        df_with_coords = df.dropna(subset=['lat', 'lon'])
        
        if df_with_coords.empty:
            print("[!] Žiadne zariadenia s geokódovanými súradnicami")
            csv_path = output_path.rsplit('.', 1)[0] + '.csv'
            df.to_csv(csv_path, index=False, encoding='utf-8')
            print(f"✓ Exportované do CSV: {csv_path}")
            return
        
        # Geometria
        geometry = [Point(xy) for xy in zip(df_with_coords['lon'], df_with_coords['lat'])]
        gdf = gpd.GeoDataFrame(df_with_coords, geometry=geometry, crs='EPSG:4326')
        
        # Infer driver
        if driver is None:
            import os
            ext = os.path.splitext(output_path)[1].lower()
            if ext in ['.geojson', '.json']:
                driver = 'GeoJSON'
            elif ext == '.gpkg':
                driver = 'GPKG'
            elif ext == '.shp':
                driver = 'ESRI Shapefile'
            else:
                driver = 'GeoJSON'
        
        # Shapefile ma limity
        if driver == 'ESRI Shapefile':
            # Skrátenie názvov stĺpcov
            col_map = {
                'nazov': 'nazov',
                'ulica': 'ulica',
                'psc': 'psc',
                'mesto': 'mesto',
                'okres': 'okres',
                'telefon': 'tel',
                'email': 'email',
                'web': 'web',
                'kategoria': 'kategoria',
                'typ_zariadenia': 'typ_zar',
                'operator': 'operator',
                'kod': 'kod',
                'specializacie': 'spec'
            }
            gdf = gdf.rename(columns={k: v for k, v in col_map.items() if k in gdf.columns})
            
            # Skrátenie textov
            for col in gdf.columns:
                if col != 'geometry' and gdf[col].dtype == 'object':
                    gdf[col] = gdf[col].astype(str).str[:254]
        
        gdf.to_file(output_path, driver=driver)
        print(f"✓ Exportovaných {len(gdf)} zariadení s GPS do: {output_path}")
        
        # Export zariadení bez súradníc
        df_without = df[~df.index.isin(df_with_coords.index)]
        if not df_without.empty:
            csv_path = output_path.rsplit('.', 1)[0] + '_bez_GPS.csv'
            df_without.to_csv(csv_path, index=False, encoding='utf-8')
            print(f"✓ {len(df_without)} zariadení bez GPS exportovaných do: {csv_path}")
    else:
        # Bez súradníc - len CSV
        csv_path = output_path.rsplit('.', 1)[0] + '.csv'
        df.to_csv(csv_path, index=False, encoding='utf-8')
        print(f"✓ Exportované do CSV: {csv_path}")


def main():
    """Hlavná funkcia scrapera."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Scraper zdravotníckych zariadení BSK (Bratislava I-V)'
    )
    parser.add_argument(
        '--output', '-o',
        default='bsk_zdravotnictvo.geojson',
        help='Výstupný súbor (.geojson, .gpkg, .shp, .csv)'
    )
    parser.add_argument(
        '--geocode', '-g',
        action='store_true',
        help='Geokódovať adresy (vyžaduje geopy, pomalé)'
    )
    parser.add_argument(
        '--no-details',
        action='store_true',
        help='Nečítať detail stránky (rýchlejšie, menej dát)'
    )
    parser.add_argument(
        '--okresy',
        nargs='+',
        choices=['Bratislava I', 'Bratislava II', 'Bratislava III', 
                 'Bratislava IV', 'Bratislava V'],
        help='Konkrétne okresy na scrapovanie'
    )
    parser.add_argument(
        '--no-export',
        action='store_true',
        help='Len vypísať dáta bez exportu'
    )
    
    args = parser.parse_args()
    
    # Scraping
    facilities = scrape_bsk_health_facilities(
        geocode=args.geocode,
        fetch_details=not args.no_details,
        okresy=args.okresy
    )
    
    if not facilities:
        print("\n[!] Nenašli sa žiadne zariadenia")
        return
    
    # Výpis
    print("\n" + "="*80)
    print("UKÁŽKA DÁT (prvých 10 zariadení)")
    print("="*80)
    for i, fac in enumerate(facilities[:10], 1):
        print(f"\n{i}. {fac.get('nazov', 'N/A')}")
        if 'ulica' in fac:
            print(f"   {fac['ulica']}, {fac.get('psc', '')}, {fac.get('mesto', '')}")
        if 'okres' in fac:
            print(f"   Okres: {fac['okres']}")
        if 'kategoria' in fac:
            print(f"   Kategória: {fac['kategoria']}")
        if 'operator' in fac:
            print(f"   Operátor: {fac['operator']}")
        if 'telefon' in fac:
            print(f"   Tel: {fac['telefon']}")
        if 'email' in fac:
            print(f"   Email: {fac['email']}")
        if 'lat' in fac and 'lon' in fac:
            print(f"   GPS: {fac['lat']:.6f}, {fac['lon']:.6f}")
    
    if len(facilities) > 10:
        print(f"\n... a ďalších {len(facilities) - 10} zariadení")
    
    # Export
    if not args.no_export:
        print("\n" + "="*80)
        export_to_geodata(facilities, args.output)


if __name__ == '__main__':
    main()