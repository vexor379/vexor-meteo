import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from streamlit_folium import st_folium
import folium

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Vexor Meteo Pro", page_icon="❄️", layout="centered")

st.title("🌍 VEXOR METEO PRO")
st.write("Analisi Avanzata: Cerca località o clicca sulla mappa.")

# --- SESSION STATE ---
if 'lat' not in st.session_state: st.session_state.lat = 44.25
if 'lon' not in st.session_state: st.session_state.lon = 7.78
if 'location_name' not in st.session_state: st.session_state.location_name = "Prato Nevoso (Default)"
if 'start_analysis' not in st.session_state: st.session_state.start_analysis = False
# Variabile specifica per sincronizzare il testo della casella
if 'box_text' not in st.session_state: st.session_state.box_text = ""

# --- INPUT FORM ---
with st.form("analysis_form"):
    col_input, col_days = st.columns([3, 1])
    with col_input:
        # COLLEGAMENTO MAGICO: value=st.session_state.box_text
        city_input = st.text_input("Scrivi Località:", value=st.session_state.box_text, placeholder="Es. Roma, Livigno...")
    with col_days:
        giorni = st.selectbox("Durata:", [3, 7, 10], index=1)
    
    submitted = st.form_submit_button("Lancia Analisi 🚀", type="primary", use_container_width=True)

# --- GEOCODING (Se usi il testo) ---
if submitted and city_input:
    try:
        with st.spinner("🔍 Cerco la località..."):
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_res = requests.get(geo_url, params={"name": city_input, "count": 1, "language": "it"}).json()
            if "results" in geo_res:
                loc = geo_res["results"][0]
                st.session_state.lat = loc["latitude"]
                st.session_state.lon = loc["longitude"]
                country = loc.get('country','')
                st.session_state.location_name = f"{loc['name']} ({country})"
                
                # Aggiorno anche il testo della casella per coerenza
                st.session_state.box_text = f"{loc['name']} ({country})"
                
                st.session_state.start_analysis = True 
                st.rerun()
            else:
                st.error("❌ Città non trovata.")
    except Exception as e: st.error(f"Errore geocoding: {e}")

# --- MAPPA INTERATTIVA ---
st.markdown("---")
st.markdown("**Oppure clicca un punto sulla mappa:**")
m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=9)
folium.Marker(
    [st.session_state.lat, st.session_state.lon],
    popup=st.session_state.location_name,
    icon=folium.Icon(color="red", icon="info-sign"),
).add_to(m)

output_mappa = st_folium(m, height=350, use_container_width=True)

# --- LOGICA CLICK MAPPA (Aggiorna anche la casella!) ---
if output_mappa['last_clicked']:
    clicked_lat = output_mappa['last_clicked']['lat']
    clicked_lon = output_mappa['last_clicked']['lng']
    
    if clicked_lat != st.session_state.lat or clicked_lon != st.session_state.lon:
        st.session_state.lat = clicked_lat
        st.session_state.lon = clicked_lon
        
        # Creo un nome basato sulle coordinate
        nome_punto = f"Punto Mappa ({clicked_lat:.2f}, {clicked_lon:.2f})"
        st.session_state.location_name = nome_punto
        
        # AGGIORNO LA CASELLA DI TESTO!
        st.session_state.box_text = nome_punto
        
        st.session_state.start_analysis = True 
        st.rerun()

# --- MOTORE DI ANALISI ---
if st.session_state.start_analysis:
    st.divider()
    st.header(f"Analisi: {st.session_state.location_name}")
    
    with st.spinner(f'📡 Elaborazione dati SWE e modelli...'):
        try:
            LAT = st.session_state.lat
            LON = st.session_state.lon
            models = [
                {"id": "ecmwf_ifs025", "label": "ECMWF (EU)", "c": "red"},
                {"id": "gfs_seamless", "label": "GFS (USA)", "c": "blue"},
                {"id": "icon_seamless", "label": "ICON (DE)", "c": "green"},
                {"id": "jma_seamless", "label": "JMA (JP)", "c": "purple"}
            ]

            data_temp = {}
            precip_accum, snow_accum, press_accum = [], [], []
            wind_accum, gust_accum = [], []
            app_temp_accum, freezing_accum = [], []
            times_index = None
            base_url = "https://api.open-meteo.com/v1/forecast"
            
            for i, m in enumerate(models):
                params = {
                    "latitude": LAT, "longitude": LON,
                    "hourly": "temperature_2m,precipitation,snowfall,pressure_msl,wind_speed_10m,wind_gusts_10m,apparent_temperature,freezing_level_height",
                    "models": m["id"],
                    "timezone": "auto",
                    "forecast_days": giorni
                }
                try:
                    r = requests.get(base_url, params=params).json()
                    if 'hourly' in r:
                        h = r["hourly"]
                        if times_index is None: times_index = pd.to_datetime(h["time"])
                        data_temp[m["label"]] = h["temperature_2m"]
                        precip_accum.append([x if x else 0.0 for x in h.get("precipitation", [])])
                        snow_accum.append([x if x else 0.0 for x in h.get("snowfall", [])])
                        press_accum.append([x if x else np.nan for x in h.get("pressure_msl", [])])
                        wind_accum.append([x if x else 0.0 for x in h.get("wind_speed_10m", [])])
                        gust_accum.append([x if x else 0.0 for x in h.get("wind_gusts_10m", [])])
                        app_temp_accum.append([x if x else np.nan for x in h.get("apparent_temperature", [])])
                        freezing_accum.append([x if x else np.nan for x in h.get("freezing_level_height", [])])
                except: continue

            if not data_temp:
                st.error("Nessun dato dai modelli.")
            else:
                min_len = min([len(times_index)] + [len(x) for x in precip_accum])
                times_index = times_index[:min_len]
                
                def get_avg(data_list):
                    return np.nanmean([x[:min_len] for x in data_list], axis=0)

                avg_precip = get_avg(precip_accum)
                avg_snow = get_avg(snow_accum)
                avg_press = get_avg(press_accum)
                avg_wind = get_avg(wind_accum)
                avg_gust = get_avg(gust_accum)
                avg_app_temp = get_avg(app_temp_accum)
                avg_freezing = get_avg(freezing_accum)
                
                # --- CALCOLI SWE ---
                snow_mask = avg_snow > 0.1
                tot_swe = np.sum(avg_precip) 
                tot_pioggia_vera = np.sum(avg_precip[~snow_mask]) 
                tot_neve = np.sum(avg_snow)
                max_wind = np.max(avg_gust)
                
                # --- DASHBOARD ---
                st.markdown("### 📊 Riepilogo Evento")
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("SWE (Tot. H2O)", f"{tot_swe:.1f} mm", help="Totale acqua caduta (neve fusa + pioggia)")
                delta_rain = "Inverse" if tot_pioggia_vera > 5 else None 
                k2.metric("Solo Pioggia", f"{tot_pioggia_vera:.1f} mm", delta=delta_rain, delta_color="inverse", help="Solo pioggia liquida")
                k3.metric("Neve Fresca", f"{tot_neve:.1f} cm", delta="Powder!" if tot_neve > 10 else None)
                k4.metric("Raffica Max", f"{max_wind:.0f} km/h", delta="Danger" if max_wind > 60 else None)
                k5.metric("Press. Min", f"{np.nanmin(avg_press):.0f} hPa")

                st.divider()

                # --- GRAFICI ---
                tab1, tab2, tab3 = st.tabs(["🌡️ Temp & Neve", "🌬️ Vento & Zero", "📉 Pressione"])
                date_fmt = mdates.DateFormatter('%d/%m %Hh')
                
                with tab1:
                    fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 11), sharex=True, gridspec_kw={'height_ratios': [1.5, 1]})
                    df_temp = pd.DataFrame({k: v[:min_len] for k,v in data_temp.items()}, index=times_index)
                    for m in models:
                        if m["label"] in df_temp.columns:
                            ax1.plot(df_temp.index, df_temp[m["label"]], label=m["label"], color=m["
