from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import json
from datetime import datetime

print("=" * 80)
print("BRATISLAVA OPEN DATA SCRAPER - GeoJSON EXPORT")
print("=" * 80)
print(f"Spustené: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# URL datasetu
url = "https://data.bratislava.sk/datasets/44975438b830498396bdfd3658574eab_0/explore"

print(f"URL: {url}\n")
print("Inicializujem prehliadač (Chrome)...")

# Nastavenie Chrome
chrome_options = Options()
chrome_options.add_argument('--headless')  # Bez GUI
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1920,1080')
chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

try:
    # Pokus o spustenie Chrome
    driver = webdriver.Chrome(options=chrome_options)
except Exception as e:
    print(f"✗ Chyba pri spustení Chrome: {e}")
    print("\nInštaluj ChromeDriver:")
    print("  pip install webdriver-manager")
    print("  alebo stiahni z: https://chromedriver.chromium.org/\n")
    
    # Skúsime s webdriver-manager
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("✓ Chrome spustený s webdriver-manager")
    except ImportError:
        print("✗ webdriver-manager nie je nainštalovaný")
        print("  Inštaluj: pip install selenium webdriver-manager")
        exit(1)

print("✓ Prehliadač spustený")
print(f"\nNačítavam stránku: {url}")

def parse_coordinates(coord_string):
    """Parsuje súradnice z rôznych formátov."""
    if not coord_string or coord_string.strip() == '':
        return None, None
    
    try:
        # Odstráň medzery a skús rôzne formáty
        coord_string = coord_string.strip()
        
        # Formát: "lat, lon" alebo "lat,lon"
        if ',' in coord_string:
            parts = coord_string.split(',')
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return lon, lat  # GeoJSON používa [lon, lat]
        
        # Formát: "lat lon"
        elif ' ' in coord_string:
            parts = coord_string.split()
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return lon, lat
        
        return None, None
    except (ValueError, IndexError):
        return None, None

def create_geojson(data):
    """Vytvorí GeoJSON z extrahovaných dát."""
    geojson = {
        "type": "FeatureCollection",
        "features": []
    }
    
    # Hľadaj stĺpce so súradnicami
    coord_columns = []
    lat_column = None
    lon_column = None
    
    if data:
        first_row = data[0]
        keys_lower = {k.lower(): k for k in first_row.keys()}
        
        # Hľadaj lat/lon stĺpce
        for key_lower, key_original in keys_lower.items():
            if 'lat' in key_lower or 'sirka' in key_lower:
                lat_column = key_original
            if 'lon' in key_lower or 'dlzka' in key_lower or 'lng' in key_lower:
                lon_column = key_original
            if 'coord' in key_lower or 'gps' in key_lower or 'poloha' in key_lower:
                coord_columns.append(key_original)
    
    print(f"\nDetekované stĺpce so súradnicami:")
    if lat_column:
        print(f"  Latitude: {lat_column}")
    if lon_column:
        print(f"  Longitude: {lon_column}")
    if coord_columns:
        print(f"  Kombinované: {', '.join(coord_columns)}")
    
    skipped = 0
    
    for i, row in enumerate(data):
        lon, lat = None, None
        
        # Pokus 1: Použiť lat/lon stĺpce
        if lat_column and lon_column:
            try:
                lat = float(row.get(lat_column, '').replace(',', '.'))
                lon = float(row.get(lon_column, '').replace(',', '.'))
            except (ValueError, AttributeError):
                pass
        
        # Pokus 2: Použiť kombinovaný stĺpec
        if (lon is None or lat is None) and coord_columns:
            for coord_col in coord_columns:
                coord_string = row.get(coord_col, '')
                lon, lat = parse_coordinates(coord_string)
                if lon is not None and lat is not None:
                    break
        
        # Ak máme platné súradnice, pridaj feature
        if lon is not None and lat is not None:
            # Vytvor properties bez súradníc
            properties = {k: v for k, v in row.items()}
            
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                },
                "properties": properties
            }
            geojson["features"].append(feature)
        else:
            skipped += 1
    
    print(f"\nVytvorených features: {len(geojson['features'])}")
    print(f"Preskočených (bez súradníc): {skipped}")
    
    return geojson

try:
    driver.get(url)
    print("✓ Stránka načítaná, čakám na tabuľku...")
    
    # Počkaj na načítanie tabuľky
    wait = WebDriverWait(driver, 30)
    
    # Hľadáme tabuľku
    possible_selectors = [
        "table",
        "[role='table']",
        ".table",
        "[class*='table']",
        "[class*='grid']",
        ".data-table",
        "[data-testid='table']"
    ]
    
    table = None
    for selector in possible_selectors:
        try:
            table = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            print(f"✓ Tabuľka nájdená: {selector}")
            break
        except:
            continue
    
    if not table:
        print("✗ Tabuľka sa nenašla, skúšam hľadať riadky priamo...")
    
    time.sleep(3)
    
    # Scrollovanie
    print("\nScrollujem aby sa načítali všetky dáta...")
    
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_pause = 2
    scroll_count = 0
    max_scrolls = 50
    
    while scroll_count < max_scrolls:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause)
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        scroll_count += 1
        print(f"  Scroll {scroll_count}: Výška stránky = {new_height}px")
        
        if new_height == last_height:
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(1)
            final_height = driver.execute_script("return document.body.scrollHeight")
            if final_height == new_height:
                print("  ✓ Koniec dát (žiadne ďalšie načítavanie)")
                break
        
        last_height = new_height
    
    print("\n✓ Scrollovanie dokončené")
    print("\nExtrahujem dáta z tabuľky...")
    
    data = []
    
    # Metóda 1: Klasická HTML tabuľka
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        if rows:
            print(f"  Metóda 1 (tbody tr): Našiel som {len(rows)} riadkov")
            
            headers = []
            header_elements = driver.find_elements(By.CSS_SELECTOR, "table thead th")
            if not header_elements:
                header_elements = driver.find_elements(By.CSS_SELECTOR, "table tr:first-child th")
            
            for th in header_elements:
                headers.append(th.text.strip())
            
            if not headers:
                first_row_cells = rows[0].find_elements(By.TAG_NAME, "td")
                headers = [f"Column_{i+1}" for i in range(len(first_row_cells))]
            
            print(f"  Stĺpce: {', '.join(headers)}")
            
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if cells:
                    row_data = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            row_data[headers[i]] = cell.text.strip()
                    if row_data:
                        data.append(row_data)
    except Exception as e:
        print(f"  Metóda 1 zlyhala: {e}")
    
    # Metóda 2: Div-based table (ArcGIS style)
    if not data:
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, "[role='row']")
            if rows and len(rows) > 1:
                print(f"  Metóda 2 (role='row'): Našiel som {len(rows)} riadkov")
                
                header_cells = rows[0].find_elements(By.CSS_SELECTOR, "[role='columnheader']")
                if not header_cells:
                    header_cells = rows[0].find_elements(By.CSS_SELECTOR, "[role='cell']")
                
                headers = [cell.text.strip() for cell in header_cells]
                print(f"  Stĺpce: {', '.join(headers)}")
                
                for row in rows[1:]:
                    cells = row.find_elements(By.CSS_SELECTOR, "[role='cell']")
                    if cells:
                        row_data = {}
                        for i, cell in enumerate(cells):
                            if i < len(headers):
                                row_data[headers[i]] = cell.text.strip()
                        if row_data:
                            data.append(row_data)
        except Exception as e:
            print(f"  Metóda 2 zlyhala: {e}")
    
    print(f"\n{'=' * 80}")
    print(f"CELKOM: {len(data)} záznamov extrahovaných")
    print(f"{'=' * 80}\n")
    
    if not data:
        print("✗ Nepodarilo sa extrahovať žiadne dáta")
        print("\nUložím screenshot pre diagnostiku...")
        driver.save_screenshot("debug_screenshot.png")
        print("✓ Screenshot uložený: debug_screenshot.png")
        
        print("\nUložím HTML zdrojový kód...")
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("✓ HTML uložený: debug_page.html")
        
    else:
        # Ukážka prvých záznamov
        print("Ukážka prvých 3 záznamov:")
        for i, row in enumerate(data[:3], 1):
            print(f"\n{i}. záznam:")
            for k, v in row.items():
                print(f"   {k}: {v}")
        
        # Vytvor GeoJSON
        print("\n" + "=" * 80)
        print("VYTVÁRAM GeoJSON...")
        print("=" * 80)
        
        geojson = create_geojson(data)
        
        # Uloženie do GeoJSON
        output_file = 'bratislava_data.geojson'
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(geojson, f, ensure_ascii=False, indent=2)
            
            print(f"\n✓ Úspešne uložené do: {output_file}")
            print(f"  Počet features: {len(geojson['features'])}")
            if geojson['features']:
                print(f"  Počet properties: {len(geojson['features'][0]['properties'])}")
        except Exception as e:
            print(f"\n✗ Chyba pri ukladaní GeoJSON: {e}")
        
        # Uloženie aj backup JSON
        output_json = 'bratislava_data_raw.json'
        try:
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✓ Raw dáta uložené do: {output_json}")
        except Exception as e:
            print(f"✗ Chyba pri ukladaní JSON: {e}")

finally:
    print("\nZatvárám prehliadač...")
    driver.quit()
    print("✓ Hotovo")

print("\n" + "=" * 80)
print("DOKONČENÉ!")
print("=" * 80)