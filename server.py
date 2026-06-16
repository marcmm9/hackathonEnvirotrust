import os
import json
import joblib
import pandas as pd
import urllib.request
import urllib.parse
import math
from flask import Flask, jsonify, request, render_template

app = Flask(__name__, template_folder='templates', static_folder='static')

# --- CONFIGURATION ---
# Trage hier deinen API-Schlüssel ein, falls er nicht als System-Umgebungsvariable gesetzt ist:
ENVIROTRUST_API_KEY = "znsimzs12sfb5g21o339e2krhd6z38711"
# ---------------------

MODEL_PATH = "solar_capacity_model.pkl"
DATA_PATH = "parks_data_sorted.json"

# In-Memory Cache for hourly weather data by rounded coordinates
WEATHER_CACHE = {}

def check_wetter_ausfall(weather_code):
    # WMO Codes 71, 73, 75 stehen für leichten, mittleren und starken Schneefall.
    # 85, 86 stehen für Schneeschauer.
    return int(weather_code) in [71, 73, 75, 85, 86]

def berechne_zell_temperatur(lufttemperatur_c, strahlung_w_m2, wind_m_s):
    # k-Faktor für Solarmodule ist ca. 0.03 °C/(W/m²)
    # Wind kühlt die Module ab (ca. 0.2 °C pro m/s Windgeschwindigkeit)
    return lufttemperatur_c + (0.03 * strahlung_w_m2) - (0.2 * wind_m_s)

def berechne_hitze_wirkungsgrad(t_cell, wind_m_s=None):
    if t_cell > 25.0:
        # 0.004 entspricht dem Verlust von 0,4% pro Grad über 25°C
        verlust_faktor = 0.004 * (t_cell - 25.0)
        # Zusätzliche Überhitzung (Severe Thermal Derating) wenn wind < 2.0 m/s und t_cell > 55.0°C
        if wind_m_s is not None and t_cell > 55.0 and wind_m_s < 2.0:
            verlust_faktor += 0.015 * (t_cell - 55.0)
        return max(0.0, 1.0 - verlust_faktor)
    return 1.0

def get_hourly_weather(lat, lon):
    """
    Holt stündliche Wetterdaten für das Jahr 2023 von der Open-Meteo Archive API.
    Nutzt in-memory Cache. Wenn offline oder fehlerhaft, wird ein synthetisches Profil erzeugt.
    """
    # Runden auf 2 Nachkommastellen (ca. 1.1km Genauigkeit), um Cache-Treffer zu maximieren
    lat_key = round(lat, 2)
    lon_key = round(lon, 2)
    cache_key = (lat_key, lon_key)
    
    if cache_key in WEATHER_CACHE:
        print(f"[Wetter] Cache-Treffer für Koordinaten: {lat_key}, {lon_key}")
        return WEATHER_CACHE[cache_key]
        
    print(f"[Wetter] Cache-Miss. Frage Open-Meteo API für {lat_key}, {lon_key} ab...")
    
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat_key}&longitude={lon_key}&"
        f"start_date=2023-01-01&end_date=2023-12-31&"
        f"hourly=temperature_2m,wind_speed_10m,shortwave_radiation,weather_code&"
        f"wind_speed_unit=ms&timezone=Europe%2FBerlin"
    )
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'EnviroTrustSolarSimulator/1.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
        hourly = res_data.get('hourly', {})
        temps = hourly.get('temperature_2m', [])
        winds = hourly.get('wind_speed_10m', [])
        rads = hourly.get('shortwave_radiation', [])
        codes = hourly.get('weather_code', [])
        
        # Sicherstellen, dass Daten für alle 8760 Stunden des Jahres da sind
        if len(temps) >= 8760 and len(winds) >= 8760 and len(rads) >= 8760 and len(codes) >= 8760:
            profile = []
            for i in range(8760):
                profile.append({
                    'temp': float(temps[i] if temps[i] is not None else 10.0),
                    'wind': float(winds[i] if winds[i] is not None else 2.0),
                    'radiation': float(rads[i] if rads[i] is not None else 0.0),
                    'weather_code': int(codes[i] if codes[i] is not None else 0)
                })
            WEATHER_CACHE[cache_key] = (profile, "Open-Meteo API")
            print(f"[Wetter] API-Abfrage erfolgreich für {lat_key}, {lon_key}.")
            return WEATHER_CACHE[cache_key]
        else:
            print("[Wetter] API lieferte unvollständige Stunden. Verwende Fallback.")
    except Exception as e:
        print(f"[Wetter] API-Fehler ({str(e)}). Verwende Fallback.")
        
    # FALLBACK: Synthetisches Wetterprofil erzeugen
    profile = []
    # Mittlere Jahrestemperatur (Lat 47 -> 11°C, Lat 55 -> 7°C)
    base_temp = 15.0 - (0.5 * lat_key) 
    # Globalstrahlung Jahresleistung: ca. 1150 W/m² max im Süden, ca. 950 W/m² max im Norden
    base_rad_max = 1100.0 - 25.0 * (lat_key - 51.3)
    
    for h in range(8760):
        day = h // 24
        hour = h % 24
        
        # Jahreszeitlicher Verlauf (Peak um den 21. Juni, Tag 172)
        seasonal_factor = math.cos(2 * math.pi * (day - 172) / 365.25)
        
        # Täglicher Temperaturverlauf (Peak nachmittags)
        daily_temp_factor = math.sin(2 * math.pi * (hour - 6) / 24)
        
        temp = base_temp + (12.0 * seasonal_factor) + (4.0 * daily_temp_factor)
        
        # Windgeschwindigkeit: Im Norden windiger, leichtes Rauschen
        base_wind = 2.5 + 0.3 * (lat_key - 50.0)
        wind = max(0.2, base_wind + 1.5 * math.sin(2 * math.pi * h / 23) + (h % 5) * 0.3)
        
        # Strahlung (Sonne geht tagsüber auf, nachts 0)
        radiation = 0.0
        is_day = 6 <= hour <= 18
        if is_day:
            diurnal_rad = math.sin(math.pi * (hour - 6) / 12)
            cloud_noise = 0.4 + 0.6 * math.sin(h / 9)  # Wolkensimulation
            rad_max = base_rad_max * (0.65 + 0.35 * seasonal_factor)
            radiation = max(0.0, rad_max * diurnal_rad * cloud_noise)
            
        # Wettercode (simulierter Schneefall bei Kälte im Winter)
        weather_code = 0
        if temp < 1.0 and seasonal_factor < -0.8:
            if (h % 12) == 0:
                weather_code = 73  # Mittlerer Schneefall
                radiation = 0.0  # Schnee bedeckt die Paneele vollständig
                
        profile.append({
            'temp': float(temp),
            'wind': float(wind),
            'radiation': float(radiation),
            'weather_code': int(weather_code)
        })
        
    WEATHER_CACHE[cache_key] = (profile, "Synthetisches Modell (Fallback)")
    print(f"[Wetter] Synthetisches Profil generiert für {lat_key}, {lon_key}.")
    return WEATHER_CACHE[cache_key]

def get_climate_risk(lat, lon):
    """
    Fragt die Klimarisiko-Scores von api.envirotrust.eu ab.
    Bei Fehlern oder Offline-Status wird ein Fallback-Score generiert.
    """
    api_key = ENVIROTRUST_API_KEY or os.environ.get('ENVIROTRUST_API_KEY')
    url = f"https://api.envirotrust.eu/api/climate_risk/risk_score?latitude={lat}&longitude={lon}"
    
    headers = {'User-Agent': 'EnviroTrustSolarSimulator/1.0'}
    if api_key and api_key.strip() != "":
        headers['x-api-key'] = api_key.strip()
        
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
        scores = res_data.get('scores', {})
        if scores:
            return {
                'air_quality': float(scores.get('air_quality', 3.0)),
                'flood_risk': float(scores.get('flood_risk', 0.0)),
                'wildfire_risk': float(scores.get('wildfire_risk', 2.0)),
                'wind_risk': float(scores.get('wind_risk', 3.0)),
                'heat_risk': float(scores.get('heat_risk', 4.0)),
                'resilience_index': float(scores.get('resilience_index', 5.0)),
                'source': 'EnviroTrust Klimadaten-API'
            }
    except Exception as e:
        print(f"[Risiko] API-Fehler ({str(e)}). Generiere Fallback-Risiko.")
        
    # Robust Fallback basierend auf Geodaten
    seed = int(abs(lat * 100 + lon * 1000)) % 100
    air_quality = round(2.0 + (seed % 6) * 0.8, 1)
    flood_risk = 10.0 if (seed % 9) == 0 else 0.0
    wildfire_risk = round(1.0 + ((seed + 3) % 8) * 0.9, 1)
    wind_risk = round(2.0 + ((seed + 7) % 7) * 1.0, 1)
    heat_risk = round(3.0 + ((seed + 13) % 6) * 1.0, 1)
    resilience_index = round(4.0 + ((seed + 19) % 6) * 1.0, 1)
    
    return {
        'air_quality': air_quality,
        'flood_risk': flood_risk,
        'wildfire_risk': wildfire_risk,
        'wind_risk': wind_risk,
        'heat_risk': heat_risk,
        'resilience_index': resilience_index,
        'source': 'Risiko-Modell (Fallback)'
    }

def get_future_weather_projections(lat, lon):
    """
    Fragt die Heat Trend and Wind Damage Zukunfts-Szenariodaten (1970-2100) von api.envirotrust.eu ab.
    Bei Fehlern oder Offline-Status wird ein Fallback-Szenariodatensatz generiert.
    """
    api_key = ENVIROTRUST_API_KEY or os.environ.get('ENVIROTRUST_API_KEY')
    url = f"https://api.envirotrust.eu/api/heat-wind/timeseries?latitude={lat}&longitude={lon}"
    
    headers = {'User-Agent': 'EnviroTrustSolarSimulator/1.0'}
    if api_key and api_key.strip() != "":
        headers['x-api-key'] = api_key.strip()
        
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
        return res_data.get('heat_wind_timeseries_data', [])
    except Exception as e:
        print(f"[Zukunft] API-Fehler ({str(e)}). Generiere Fallback-Projektionen.")
        
    # Robust Fallback für Zukunftsdaten (1970 bis 2100) basierend auf Geodaten
    seed = int(abs(lat * 100 + lon * 1000)) % 100
    fallback_data = []
    for y in range(1970, 2101):
        # Steigender Trend bei Hitzewellen (RCP8.5 steigt stärker)
        base_h85 = max(0, int((y - 2020) * 0.3 + (seed % 4))) if y > 2020 else 0
        base_h45 = max(0, int((y - 2020) * 0.12 + (seed % 3))) if y > 2020 else 0
        
        # Windgeschwindigkeit: leichte Zunahme und stärkere Schwankung
        w85 = 3.2 + 0.003 * (y - 2020) + ((seed + y) % 7 - 3) * 0.1
        w45 = 3.2 + 0.001 * (y - 2020) + ((seed + y) % 7 - 3) * 0.1
        
        # Extreme Windtage
        ext_w85 = max(5.0, 8.0 + 0.08 * (y - 2020) + ((seed * y) % 5 - 2))
        ext_w45 = max(5.0, 8.0 + 0.02 * (y - 2020) + ((seed * y) % 5 - 2))
        
        fallback_data.append({
            "year": y,
            "heatwaves_rcp45": int(base_h45),
            "heatwaves_rcp85": int(base_h85),
            "consecutive_dry_days_rcp45": float(12 + (y % 8)),
            "consecutive_dry_days_rcp85": float(12 + (y % 8) * 1.4),
            "mean wind speed rcp45(m/s)": w45,
            "mean wind speed rcp85(m/s)": w85,
            "extreme_wind_speed_days_rcp45": ext_w45,
            "extreme_wind_speed_days_rcp85": ext_w85,
            "daily max temperature rcp45(K)": 298.0 + 0.02 * (y - 2020),
            "daily max temperature rcp85(K)": 298.0 + 0.06 * (y - 2020)
        })
    return fallback_data

# Load AI model and dataset
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
else:
    model = None

if os.path.exists(DATA_PATH):
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        parks = json.load(f)
        parks = sorted(parks, key=lambda x: x['area_ha'], reverse=True)
else:
    parks = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/parks', methods=['GET'])
def get_parks():
    return jsonify(parks)

@app.route('/api/simulate', methods=['POST'])
def simulate():
    if not model:
        return jsonify({"error": "KI-Modell nicht geladen. Bitte trainieren Sie das Modell zuerst."}), 500

    data = request.json or {}
    try:
        area_ha = float(data.get('area_ha', 10.0))
        lat = float(data.get('lat', 51.3))
        lon = float(data.get('lon', 10.4))
        year = int(data.get('year', 2023))
        
        years = int(data.get('years', 20))
        purchase_price_per_mw = float(data.get('purchase_price_per_mw', 800000))
        elec_price = float(data.get('elec_price', 0.08))
        degradation = float(data.get('degradation', 0.5)) / 100.0
        use_future_projections = bool(data.get('use_future_projections', False))
        
        op_cost_mode = data.get('op_cost_mode', 'standard')
        custom_op_cost_per_mw = float(data.get('custom_op_cost_per_mw', 18000.0))
        custom_op_cost_escalation = float(data.get('custom_op_cost_escalation', 0.0)) / 100.0
        inflation_rate = float(data.get('inflation_rate', 2.0)) / 100.0
        target_profit = float(data.get('target_profit', 0.0))
        rcp_scenario = data.get('rcp_scenario', 'rcp85')  # 'rcp45' oder 'rcp85'
        if rcp_scenario not in ('rcp45', 'rcp85'):
            rcp_scenario = 'rcp85'
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Ungültige Parameter: {str(e)}"}), 400

    # 1. KI-Prognose für Leistung (MW)
    features = pd.DataFrame([[area_ha, lat, lon, year]], columns=['area_ha', 'lat', 'lon', 'year'])
    pred_mw = float(model.predict(features)[0])

    # 2. Klimarisiken abfragen und in die Kalkulation einfließen lassen
    risk_profile = get_climate_risk(lat, lon)
    air_q = risk_profile['air_quality']
    flood_r = risk_profile['flood_risk']
    wildfire_r = risk_profile['wildfire_risk']
    wind_r = risk_profile['wind_risk']
    heat_r = risk_profile['heat_risk']
    resilience = risk_profile['resilience_index']
    
    # Risikobezogene Berechnungen:
    # - Luftverschmutzung (air_q) führt zu Verschmutzung (Soiling) -> mindert Ertrag (bis zu 3% bei max. Score 10)
    soiling_loss_factor = 1.0 - (0.003 * air_q)
    
    # - O&M-Multiplikator:
    #   * Luftqualität: +4% O&M pro Punkt (erhöhte Reinigungskosten)
    #   * Hochwasser: Flach +15% falls Zone (>= 5.0) für Versicherungsschutz
    #   * Waldbrand: +3% pro Punkt für Versicherungsschutz
    #   * Wind: +2% pro Punkt für mechanische Instandhaltung
    om_multiplier = 1.0 + (0.04 * air_q) + (0.15 if flood_r >= 5.0 else 0.0) + (0.03 * wildfire_r) + (0.02 * wind_r)
    
    # - Wind: Extreme Winde/Stürme erhöhen Verschleiß -> erhöht Degradationsrate
    adjusted_degradation = degradation + (0.0003 * wind_r)

    # 3. Spezifischer Solarertrag stündlich simulieren (Temperatur, Wind, Schnee, Abregelung, Soiling)
    hourly_weather, weather_source = get_hourly_weather(lat, lon)
    
    baseline_production_kwh = 0.0
    overheat_hours = 0
    total_overheat_loss_kwh = 0.0
    for hour_data in hourly_weather:
        w_code = hour_data['weather_code']
        rad = hour_data['radiation']
        temp = hour_data['temp']
        wind = hour_data['wind']
        
        # Check auf Totalausfall (Schnee oder keine Strahlung)
        if check_wetter_ausfall(w_code) or rad <= 0:
            continue
            
        # Zelltemperatur bestimmen
        t_cell = berechne_zell_temperatur(temp, rad, wind)
        
        # Hitzeminderung berechnen (standard vs. überhitzt)
        wirkungsgrad_std = berechne_hitze_wirkungsgrad(t_cell)
        wirkungsgrad_pen = berechne_hitze_wirkungsgrad(t_cell, wind)
        
        # Theoretische Rohleistung der Module (P_peak = pred_mw * 1000 kW) unter Einbeziehung des Soiling-Verlusts
        rohleistung_std = (pred_mw * 1000.0) * (rad / 1000.0) * wirkungsgrad_std * soiling_loss_factor
        rohleistung_pen = (pred_mw * 1000.0) * (rad / 1000.0) * wirkungsgrad_pen * soiling_loss_factor
        
        # Wechselrichter-Abregelung (Clipping) bei max 95% der Nennleistung
        output_std = min(rohleistung_std, pred_mw * 1000.0 * 0.95)
        output_pen = min(rohleistung_pen, pred_mw * 1000.0 * 0.95)
        
        # Überhitzung erfassen
        if t_cell > 55.0 and wind < 2.0:
            overheat_hours += 1
            loss_kwh = max(0.0, output_std - output_pen)
            total_overheat_loss_kwh += loss_kwh
            
        # Da stündlich, entspricht kW direkt kWh. Die tatsächliche Produktion berücksichtigt die Pönalisierung.
        baseline_production_kwh += output_pen
        
    # Spezifischer Solarertrag = Gesamtproduktion (kWh) / Kapazität (kWp)
    specific_yield = (baseline_production_kwh / (pred_mw * 1000.0)) if pred_mw > 0 else 0.0

    # 4. Investitionsrechnung
    total_cost = pred_mw * purchase_price_per_mw
    op_cost_per_mw = 18000.0 * om_multiplier  # Jährliche Betriebskosten pro MW in EUR (angepasst durch Risikofaktoren)
    
    # Bank covenants configurations
    capex_bank = pred_mw * 600000.0
    loan_bank = capex_bank * 0.75
    interest_rate = 0.04
    amortization_years = 20
    opex_annual_bank = pred_mw * 1000.0 * 12.0 # 12 EUR / kWp / year
    
    if loan_bank > 0:
        annuity_bank = loan_bank * (interest_rate * (1 + interest_rate)**amortization_years) / ((1 + interest_rate)**amortization_years - 1)
    else:
        annuity_bank = 0.0
    
    future_projs = get_future_weather_projections(lat, lon) if (use_future_projections or op_cost_mode == 'model') else []
    proj_by_year = {p['year']: p for p in future_projs}
    
    # Vorabberechnung des Amortisationszeitpunkts (Payback Year) bis maximal 100 Jahre
    payback_year = None
    temp_cum_profit = 0.0
    temp_capacity_multiplier = 1.0
    
    for y_idx in range(1, 101):
        sim_year = year + y_idx - 1
        
        # Jährliche Parameter initialisieren (Standard ohne Zukunftsprognosen)
        year_degradation = adjusted_degradation
        year_op_multiplier = 1.0
        year_yield_multiplier = 1.0
        
        if (use_future_projections or op_cost_mode == 'model') and sim_year in proj_by_year:
            proj = proj_by_year[sim_year]
            heatwaves = proj.get(f'heatwaves_{rcp_scenario}', 0)
            extreme_wind_days = proj.get(f'extreme_wind_speed_days_{rcp_scenario}', 10.0)
            mean_wind_speed = proj.get(f'mean wind speed {rcp_scenario}(m/s)', 3.5)
            
            if use_future_projections:
                year_yield_multiplier = max(0.5, 1.0 - (0.008 * heatwaves))
                wind_excess = max(0.0, extreme_wind_days - 10.0)
                year_degradation = adjusted_degradation + (0.0002 * wind_excess)
            
            year_op_multiplier = 1.0 + (0.015 * heatwaves) + (0.01 * max(0.0, mean_wind_speed - 3.0))
            
        temp_capacity_multiplier *= (1.0 - year_degradation)
        production_kwh = baseline_production_kwh * temp_capacity_multiplier * year_yield_multiplier
        revenue = production_kwh * elec_price
        
        if op_cost_mode == 'custom':
            op_cost = pred_mw * custom_op_cost_per_mw * ((1.0 + custom_op_cost_escalation) ** (y_idx - 1))
        elif op_cost_mode == 'model':
            op_cost = pred_mw * (18000.0 * om_multiplier) * year_op_multiplier * ((1.0 + inflation_rate) ** (y_idx - 1))
        else: # 'standard'
            op_cost = pred_mw * op_cost_per_mw * (year_op_multiplier if use_future_projections else 1.0)
            
        temp_cum_profit += (revenue - op_cost)
        
        if temp_cum_profit >= (total_cost + target_profit):
            payback_year = y_idx
            break

    # Der Simulationszeitraum wird vergrößert, falls die Amortisation länger dauert
    active_sim_years = years
    if payback_year is not None:
        active_sim_years = max(years, payback_year)
        
    sim_data = []
    cum_net_profit = 0.0
    capacity_multiplier = 1.0
    
    for y_idx in range(1, active_sim_years + 1):
        sim_year = year + y_idx - 1
        
        # Jährliche Parameter initialisieren (Standard ohne Zukunftsprognosen)
        year_degradation = adjusted_degradation
        year_op_multiplier = 1.0
        year_yield_multiplier = 1.0
        
        if (use_future_projections or op_cost_mode == 'model') and sim_year in proj_by_year:
            proj = proj_by_year[sim_year]
            heatwaves = proj.get(f'heatwaves_{rcp_scenario}', 0)
            extreme_wind_days = proj.get(f'extreme_wind_speed_days_{rcp_scenario}', 10.0)
            mean_wind_speed = proj.get(f'mean wind speed {rcp_scenario}(m/s)', 3.5)
            
            if use_future_projections:
                # 1. Hitzewellen-Ertragsminderung: Jede Hitzewelle reduziert den Ertrag in diesem Jahr um 0.8%
                year_yield_multiplier = max(0.5, 1.0 - (0.008 * heatwaves))
                
                # 2. Windschadens-Degradation: Mehr extreme Windtage erhöhen die mechanische Abnutzung
                wind_excess = max(0.0, extreme_wind_days - 10.0)
                year_degradation = adjusted_degradation + (0.0002 * wind_excess)
            
            # 3. O&M Multiplikator: Hitzewellen und höhere Windgeschwindigkeiten erhöhen die Betriebskosten
            year_op_multiplier = 1.0 + (0.015 * heatwaves) + (0.01 * max(0.0, mean_wind_speed - 3.0))
            
        capacity_multiplier *= (1.0 - year_degradation)
        production_kwh = baseline_production_kwh * capacity_multiplier * year_yield_multiplier
        
        revenue = production_kwh * elec_price
        
        # Jährliche Betriebskosten anhand der Berechnungsmethode bestimmen
        if op_cost_mode == 'custom':
            op_cost = pred_mw * custom_op_cost_per_mw * ((1.0 + custom_op_cost_escalation) ** (y_idx - 1))
        elif op_cost_mode == 'model':
            # Klimabewertetes Risiko (om_multiplier) * Klimawandel (year_op_multiplier) * Inflation
            op_cost = pred_mw * (18000.0 * om_multiplier) * year_op_multiplier * ((1.0 + inflation_rate) ** (y_idx - 1))
        else: # 'standard'
            op_cost = pred_mw * op_cost_per_mw * (year_op_multiplier if use_future_projections else 1.0)
            
        net_profit = revenue - op_cost
        cum_net_profit += net_profit
        
        # DSCR calculation
        annuity = annuity_bank if y_idx <= 20 else 0.0
        cfads = revenue - opex_annual_bank
        dscr = cfads / annuity if annuity > 0 else 99.99
        covenant_breached = bool(annuity > 0 and dscr < 1.20)
        
        sim_data.append({
            "year": y_idx,
            "production_mwh": float(production_kwh / 1000.0),
            "revenue": float(revenue),
            "op_cost": float(op_cost),
            "net_profit": float(net_profit),
            "cum_profit": float(cum_net_profit - total_cost),
            "dscr": float(dscr),
            "annuity": float(annuity),
            "opex_bank": float(opex_annual_bank),
            "covenant_breached": covenant_breached
        })
        
    roi = (cum_net_profit / total_cost) * 100.0 if total_cost > 0 else 0.0

    # Falls Zukunftsprognosen aktiv sind, passen wir das angezeigte Hitze- und Windrisiko
    # im Scoreboard basierend auf den Zukunftsprognosen an
    if use_future_projections and future_projs:
        relevant_projs = [proj_by_year[y] for y in range(year, year + years) if y in proj_by_year]
        if relevant_projs:
            avg_heatwaves = sum(p.get(f'heatwaves_{rcp_scenario}', 0) for p in relevant_projs) / len(relevant_projs)
            avg_ext_wind = sum(p.get(f'extreme_wind_speed_days_{rcp_scenario}', 0.0) for p in relevant_projs) / len(relevant_projs)
            
            # Das Hitzerisiko und Windrisiko steigen basierend auf den durchschnittlichen Projektionen
            heat_r = min(10.0, heat_r + avg_heatwaves * 0.4)
            wind_r = min(10.0, wind_r + max(0.0, avg_ext_wind - 10.0) * 0.3)
            
            rcp_label = 'RCP 4.5' if rcp_scenario == 'rcp45' else 'RCP 8.5'
            risk_profile['heat_risk'] = round(heat_r, 1)
            risk_profile['wind_risk'] = round(wind_r, 1)
            risk_profile['source'] = f'EnviroTrust API (mit Zukunfts-Szenario {rcp_label})'

    # Berechne Gesamtrisiko (0-10) neu mit den (eventuell angepassten) Risikofaktoren
    raw_avg = (air_q + flood_r + wildfire_r + wind_r + heat_r) / 5.0
    resilience_effect = 1.0 - 0.03 * (resilience - 5.0)
    overall_risk = min(10.0, max(0.0, raw_avg * resilience_effect))
    
    # Nun inverte die Scores für die Rückgabe (hohe Scores sind gut/Sicherheit/Qualität):
    inverted_risk_profile = {
        'air_quality': round(10.0 - air_q, 1),
        'flood_risk': round(10.0 - flood_r, 1),
        'wildfire_risk': round(10.0 - wildfire_r, 1),
        'wind_risk': round(10.0 - wind_r, 1),
        'heat_risk': round(10.0 - heat_r, 1),
        'resilience_index': resilience,
        'overall_risk': round(10.0 - overall_risk, 1),
        'source': risk_profile.get('source', 'Klimarisiko-Modell')
    }

    # Überhitzungsinformationen berechnen
    annual_loss_eur = total_overheat_loss_kwh * elec_price
    total_loss_eur = annual_loss_eur * years
    
    overheat_info = {
        "hours": overheat_hours,
        "annual_loss_eur": round(annual_loss_eur, 2),
        "total_loss_eur": round(total_loss_eur, 2),
        "should_warn": overheat_hours > 0
    }

    # Determine worst year for active loan (y_idx <= 20)
    active_loan_years = [d for d in sim_data if d['year'] <= 20]
    if active_loan_years:
        worst_year_data = min(active_loan_years, key=lambda x: x['dscr'])
        worst_y_idx = worst_year_data['year']
        worst_year_dscr = worst_year_data['dscr']
    else:
        worst_y_idx = 1
        worst_year_dscr = 99.99
        
    # Get worst year's specific multipliers
    worst_capacity_multiplier = 1.0
    
    # Recalculate capacity_multiplier up to worst_y_idx
    temp_cap_mult = 1.0
    for y_i in range(1, worst_y_idx + 1):
        sim_year = year + y_i - 1
        y_degr = adjusted_degradation
        if (use_future_projections or op_cost_mode == 'model') and sim_year in proj_by_year:
            proj = proj_by_year[sim_year]
            if use_future_projections:
                extreme_wind_days = proj.get(f'extreme_wind_speed_days_{rcp_scenario}', 10.0)
                wind_excess = max(0.0, extreme_wind_days - 10.0)
                y_degr = adjusted_degradation + (0.0002 * wind_excess)
        temp_cap_mult *= (1.0 - y_degr)
    
    # Yield multiplier for worst year
    worst_year_yield_multiplier = 1.0
    sim_year = year + worst_y_idx - 1
    if (use_future_projections or op_cost_mode == 'model') and sim_year in proj_by_year:
        proj = proj_by_year[sim_year]
        if use_future_projections:
            heatwaves = proj.get(f'heatwaves_{rcp_scenario}', 0)
            worst_year_yield_multiplier = max(0.5, 1.0 - (0.008 * heatwaves))

    # Simulate the worst year daily
    daily_data = []
    cum_rev = 0.0
    
    # Compute the hourly outputs
    hourly_outputs = []
    for hour_data in hourly_weather:
        w_code = hour_data['weather_code']
        rad = hour_data['radiation']
        temp = hour_data['temp']
        wind = hour_data['wind']
        
        if check_wetter_ausfall(w_code) or rad <= 0:
            hourly_outputs.append(0.0)
            continue
            
        t_cell = berechne_zell_temperatur(temp, rad, wind)
        wirkungsgrad_pen = berechne_hitze_wirkungsgrad(t_cell, wind)
        rohleistung_pen = (pred_mw * 1000.0) * (rad / 1000.0) * wirkungsgrad_pen * soiling_loss_factor
        output_pen = min(rohleistung_pen, pred_mw * 1000.0 * 0.95)
        hourly_outputs.append(output_pen)
        
    # Calculate daily totals
    for d in range(1, 366):
        day_start = (d - 1) * 24
        day_end = min(8760, d * 24)
        day_prod_kwh = sum(hourly_outputs[day_start:day_end]) * temp_cap_mult * worst_year_yield_multiplier
        day_rev = day_prod_kwh * elec_price
        
        cum_rev += day_rev
        cum_opex = (opex_annual_bank / 365.0) * d
        cum_cashflow = cum_rev - cum_opex
        cum_debt_service = (annuity_bank / 365.0) * d
        target_liquidity = 1.20 * cum_debt_service
        
        daily_data.append({
            "day": d,
            "cum_cashflow": float(cum_cashflow),
            "target_liquidity": float(target_liquidity),
            "is_breached": bool(cum_cashflow < target_liquidity)
        })
        
    covenants_info = {
        "capex_bank": capex_bank,
        "loan_bank": loan_bank,
        "annuity_bank": annuity_bank,
        "opex_annual_bank": opex_annual_bank,
        "has_covenant_breach": any(d['covenant_breached'] for d in sim_data),
        "worst_year_idx": worst_y_idx,
        "worst_year_simulated": int(year + worst_y_idx - 1),
        "worst_year_dscr": float(worst_year_dscr),
        "daily_covenant_curve": daily_data
    }

    response = {
        "pred_mw": pred_mw,
        "total_cost": total_cost,
        "specific_yield": specific_yield,
        "roi": roi,
        "payback_year": payback_year,
        "total_revenue": sum(d['revenue'] for d in sim_data),
        "total_op_cost": sum(d['op_cost'] for d in sim_data),
        "total_net_profit": cum_net_profit,
        "net_profit_after_purchase": cum_net_profit - total_cost,
        "weather_source": weather_source,
        "risk_profile": inverted_risk_profile,
        "overheat_info": overheat_info,
        "simulation": sim_data,
        "future_projections_active": use_future_projections,
        "rcp_scenario": rcp_scenario,
        "covenants_info": covenants_info
    }

    return jsonify(response)

if __name__ == '__main__':
    # Get port from environment or use 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
