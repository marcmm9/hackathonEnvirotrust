import os
import urllib.request
import geopandas as gpd
import fiona

# URL to the Microsoft Global Renewables Watch Solar PV dataset (2024 Q2)
URL = "https://github.com/microsoft/global-renewables-watch/releases/download/v1.0/solar_all_2024q2_v1.gpkg"
FILENAME = "global_renewables_watch.gpkg"

def download_file(url, filename):
    if os.path.exists(filename):
        print(f"Datei '{filename}' existiert bereits. Download wird übersprungen.")
        return
        
    print(f"Lade Datensatz herunter von: {url}")
    print("Dies kann einen Moment dauern (ca. 395 MB)...")
    
    # Download mit einfacher Fortschrittsanzeige
    def report_hook(block_num, block_size, total_size):
        read_so_far = block_num * block_size
        if total_size > 0:
            percent = min(100, (read_so_far * 100) / total_size)
            # Nur alle 10% aktualisieren, um die Log-Ausgabe sauber zu halten
            if block_num % 1000 == 0:
                print(f"Download: {percent:.1f}% ({read_so_far / (1024*1024):.1f} MB von {total_size / (1024*1024):.1f} MB)")
        else:
            if block_num % 1000 == 0:
                print(f"Download: {read_so_far / (1024*1024):.1f} MB")

    urllib.request.urlretrieve(url, filename, reporthook=report_hook)
    print("Download erfolgreich abgeschlossen!")

def read_solar_data(filename):
    print(f"\nLese {filename}...")
    
    # 1. Layer auflisten
    layers = fiona.listlayers(filename)
    print("Verfügbare Layer im GPKG:", layers)
    
    # 2. Den ersten Layer auslesen (über pyogrio)
    print("Lade Geometriedaten (Engine: pyogrio)...")
    df = gpd.read_file(filename, layer=layers[0], engine="pyogrio")
    
    # 3. Erste Zeilen anzeigen
    print("\nErste 5 Zeilen der Daten:")
    print(df.head())
    
    # 4. Zusammenfassung / Info
    print(f"\nAnzahl der Einträge: {len(df)}")
    print("\nSpaltennamen:")
    print(df.columns.tolist())
    
    # 5. Ein paar Statistiken (z.B. Baujahre, falls vorhanden)
    if 'construction_year' in df.columns:
        print("\nVerteilung der Baujahre:")
        print(df['construction_year'].value_counts().sort_index())
    
    return df

if __name__ == "__main__":
    download_file(URL, FILENAME)
    df = read_solar_data(FILENAME)
