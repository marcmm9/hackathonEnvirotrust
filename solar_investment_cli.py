import os
import sys
import json
import joblib
import pandas as pd
import numpy as np

# Reconfigure stdout to use UTF-8 (prevent cp1252 encoding crashes on Windows)
sys.stdout.reconfigure(encoding='utf-8')

# Load the trained model and dataset
MODEL_PATH = "solar_capacity_model.pkl"
DATA_PATH = "parks_data_sorted.json"

if not os.path.exists(MODEL_PATH) or not os.path.exists(DATA_PATH):
    print("Fehler: Modell oder Datensatz nicht gefunden. Bitte trainiere zuerst das Modell.")
    exit(1)

model = joblib.load(MODEL_PATH)
with open(DATA_PATH, "r", encoding="utf-8") as f:
    parks = json.load(f)

# Sort parks by area for display
parks = sorted(parks, key=lambda x: x['area_ha'], reverse=True)

def print_header(title):
    print("\n" + "=" * 60)
    print(title.center(60))
    print("=" * 60)

def display_parks(page=0, page_size=15):
    start = page * page_size
    end = start + page_size
    total_pages = int(np.ceil(len(parks) / page_size))
    print_header(f"Verfügbare Solarparks (Seite {page+1} von {total_pages})")
    for i in range(start, min(end, len(parks))):
        p = parks[i]
        city_str = p.get('city', 'Unbekannt')
        postal_str = p.get('postal', '')
        loc = f"{city_str} ({postal_str})" if postal_str else city_str
        print(f"[{i+1}] Solarpark in {loc} - Fläche: {p['area_ha']:.2f} ha - Baujahr: {p['year']} - Leistung (MaStR): {p['mastr_mw']:.2f} MW")
    print("-" * 60)
    print("[N] Nächste Seite | [P] Vorherige Seite | [Nummer] Park auswählen | [C] Eigener Park | [Q] Beenden")

def run_simulation(area_ha, lat, lon, year):
    # Predict capacity using the trained Random Forest model (AI)
    features = pd.DataFrame([[area_ha, lat, lon, year]], columns=['area_ha', 'lat', 'lon', 'year'])
    pred_mw = model.predict(features)[0]
    
    print_header("KI-Prognose und Finanzsimulation")
    print(f"Eingegebene Werte:")
    print(f"  Fläche: {area_ha:.2f} ha")
    print(f"  Standort: {lat:.6f}°N, {lon:.6f}°E")
    print(f"  Baujahr: {year}")
    print(f"\n-> Jährliche KI-prognostizierte Nennleistung: {pred_mw:.2f} MW")
    
    # Financial parameters from user
    try:
        years = int(input("\nSimulationszeitraum in Jahren [Standard: 20]: ") or 20)
        purchase_price_per_mw = float(input("Kaufpreis pro MW in EUR [Standard: 800000]: ") or 800000)
        elec_price = float(input("Strompreis pro kWh in EUR [Standard: 0.08]: ") or 0.08)
        degradation = float(input("Jährliche Degradation der Paneele in % [Standard: 0.5]: ") or 0.5) / 100.0
    except ValueError:
        print("Ungültige Eingabe. Verwende Standardwerte.")
        years = 20
        purchase_price_per_mw = 800000
        elec_price = 0.08
        degradation = 0.005

    # Specific Yield model based on Latitude (more sun in the south)
    # Latitude in Germany ranges from 47.3 to 55.0
    specific_yield = 1000.0 + 40.0 * (51.3 - lat)
    
    # Financial calculation
    total_cost = pred_mw * purchase_price_per_mw
    op_cost_per_mw = 18000.0  # Annual O&M costs per MW
    
    print(f"\n--- Kaufpreis-Kalkulation ---")
    print(f"Errechneter Kaufpreis: {total_cost:,.2f} EUR (bei {purchase_price_per_mw:,.2f} EUR/MW)")
    
    sim_data = []
    cum_net_profit = 0.0
    payback_year = None
    
    for y_idx in range(1, years + 1):
        # Calculate current capacity considering degradation
        current_deg = (1.0 - degradation) ** y_idx
        # Annual energy production in kWh
        # Capacity (kW) * specific yield * degradation factor
        production_kwh = (pred_mw * 1000.0) * specific_yield * current_deg
        
        revenue = production_kwh * elec_price
        op_cost = pred_mw * op_cost_per_mw
        net_profit = revenue - op_cost
        
        cum_net_profit += net_profit
        
        sim_data.append({
            "Jahr": y_idx,
            "Produktion (MWh)": production_kwh / 1000.0,
            "Einnahmen (EUR)": revenue,
            "Betriebskosten (EUR)": op_cost,
            "Reingewinn (EUR)": net_profit,
            "Kumuliert (EUR)": cum_net_profit - total_cost
        })
        
        if payback_year is None and cum_net_profit >= total_cost:
            payback_year = y_idx

    df_sim = pd.DataFrame(sim_data)
    
    print("\n--- Jährlicher Cashflow ---")
    print(df_sim.to_string(index=False, formatters={
        "Produktion (MWh)": "{:,.1f}".format,
        "Einnahmen (EUR)": "{:,.2f} EUR".format,
        "Betriebskosten (EUR)": "{:,.2f} EUR".format,
        "Reingewinn (EUR)": "{:,.2f} EUR".format,
        "Kumuliert (EUR)": "{:,.2f} EUR".format
    }))
    
    roi = (cum_net_profit / total_cost) * 100.0 if total_cost > 0 else 0.0
    
    print_header("Zusammenfassung der Investition")
    print(f"Kaufpreis:             {total_cost:,.2f} EUR")
    print(f"Gesamteinnahmen:       {df_sim['Einnahmen (EUR)'].sum():,.2f} EUR")
    print(f"Gesamtbetriebskosten:  {df_sim['Betriebskosten (EUR)'].sum():,.2f} EUR")
    print(f"Gesamter Reingewinn:   {cum_net_profit:,.2f} EUR")
    print(f"Reingewinn nach Kauf:  {(cum_net_profit - total_cost):,.2f} EUR")
    print(f"Return on Investment:  {roi:.2f} %")
    if payback_year:
        print(f"Amortisationszeit:     {payback_year} Jahre")
    else:
        print(f"Amortisationszeit:     Amortisiert sich nicht innerhalb von {years} Jahren.")
    print("=" * 60)
    input("\nDrücke Enter, um fortzufahren...")

def main():
    page = 0
    while True:
        display_parks(page)
        choice = input("\nDeine Auswahl: ").strip().lower()
        if choice == 'q':
            break
        elif choice == 'n':
            if (page + 1) * 15 < len(parks):
                page += 1
            else:
                print("Du bist bereits auf der letzten Seite.")
        elif choice == 'p':
            if page > 0:
                page -= 1
            else:
                print("Du bist bereits auf der ersten Seite.")
        elif choice == 'c':
            print_header("Eigener Solarpark")
            try:
                area = float(input("Fläche in Hektar: "))
                lat = float(input("Breitengrad (Lat, z.B. 49.0): "))
                lon = float(input("Längengrad (Lon, z.B. 11.5): "))
                year = int(input("Baujahr (z.B. 2023): "))
                run_simulation(area, lat, lon, year)
            except ValueError:
                print("Ungültige Eingaben. Bitte Zahlen eingeben.")
                input("\nDrücke Enter, um fortzufahren...")
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(parks):
                    p = parks[idx]
                    run_simulation(p['area_ha'], p['lat'], p['lon'], p['year'])
                else:
                    print("Ungültige Solarpark-Nummer.")
                    input("\nDrücke Enter, um fortzufahren...")
            except ValueError:
                print("Ungültige Eingabe.")
                input("\nDrücke Enter, um fortzufahren...")

if __name__ == "__main__":
    main()