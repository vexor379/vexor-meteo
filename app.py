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

# --- SESSION STATE (Inizializzazione Sicura) ---
# Usiamo valori di default sicuri per evitare crash al primo avvio
defaults = {
    'lat': 44.25,
    'lon': 7.78,
    'location_name': "Prato Nevoso (Default)",
    'box_text': "",
    'start_analysis': False
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- FUNZIONE DI RICERCA CITTÀ (Per pulizia codice) ---
def cerca_citta(nome_citta):
    if not nome_citta: return
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        res = requests.get(url, params={"name": nome_citta, "count": 1, "language": "it"}, timeout=5).json()
        
        if "results" in res:
            loc = res["results"][0]
            st.session_state.lat = loc["latitude"]
            st.session_state.lon = loc["longitude"]
            st.session_state.location_name = f"{loc['name']} ({loc.get('country','')})"
            st.session_state.box_text = f"{loc['name']} ({loc.get('country','')})"
            st.session_state.start_analysis = True
            return True
        else:
            st.warning(f"⚠️ Località '{nome_citta}' non trovata. Riprova.")
            return False
    except Exception as e:
        st.error(f"Errore di connessione: {e}")
        return False

# --- INPUT FORM ---
with st.form("analysis_form"):
    col_input, col_days = st.columns([3, 1])
    with col_input:
        # Il value è collegato allo stato, così si aggiorna se clicchi sulla mappa
        city_input = st.text_input("Scrivi Località:", value=st.session_state.box_text, placeholder="Es. Roma, Livigno...")
    with col_days:
        giorni = st.selectbox("Durata:", [3, 7, 10], index=1)
    
    submitted = st.form_submit_button("Lancia Analisi 🚀", type="primary", use_container_width=True)

# --- LOGICA RICERCA TESTUALE ---
if submitted and city_input:
    # Se l'utente ha scritto qualcosa di diverso dall'ultima volta O ha forzato il click
    if city_input != st.session_state.location_name: 
        with st.spinner("🔍 Cerco coordinate..."):
            successo = cerca_citta(city_input)
            if successo:
                st.rerun()

# --- MAPPA INTERATTIVA ---
st.markdown("---")
st.markdown("**Oppure clicca un punto sulla mappa:**")

# Mappa centrata sull'ultima posizione valida
m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=9)
folium.Marker(
    [st.session_state.lat, st.session_state.lon],
    popup=st.session_state.location_name,
    icon=folium.Icon(color="red", icon="info-sign"),
).add_to(m)

# Riceviamo i dati dal click
output_mappa = st_folium(m, height=350, use_container_width=True)

# --- LOGICA CLICK MAPPA (Con Reverse Geocoding) ---
if output_mappa['last_clicked']:
    clicked_lat = output_mappa['last_clicked']['lat']
    clicked_lon = output_mappa['last_clicked']['lng']
    
    # Controllo per evitare loop infiniti: agisco solo se le coordinate sono NUOVE
    # Uso una tolleranza minima (abs < 0.0001) perché i float a volte cambiano di pochissimo
    if (abs(clicked_lat - st.session_state.lat) > 0.0001) or (abs(clicked_lon - st.session_state.lon) > 0.0001):
        
        st.session_state.lat = clicked_lat
        st.session_state.lon = clicked_lon
        
        # PROVO A TROVARE IL NOME DEL PUNTO CLICCATO (Reverse Geocoding)
        # Uso un trucco: cerco la città più vicina a queste coordinate
        try:
            # Open-Meteo non ha un reverse geocoding diretto semplice, ma possiamo usare il nome generico
            # Oppure lasciare le coordinate se siamo nel nulla.
            # Per stabilità e velocità, aggiorniamo subito con le coordinate, poi l'analisi partirà.
            nome_punto = f"Punto Mappa ({clicked_lat:.2f}, {clicked_lon:.2f})"
            st.session_state.location_name = nome_punto
            st.session_state.box_text = nome_punto
        except:
            pass
            
        st.session_state.start_analysis = True
        st.rerun()

# --- MOTORE DI ANALISI ---
# Questa parte parte SOLO se abbiamo coordinate valide confermate
if st.session_state.start_analysis:
    st.divider()
    st.header(f"Analisi: {st.session_state.location_name}")
    
    with st.spinner(f'📡 Elaborazione dati e modelli...'):
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
                    r = requests.get(base_url, params=params, timeout=10).json()
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
                st.error("Nessun dato dai modelli. Riprova tra poco.")
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
                            ax1.plot(df_temp.index, df_temp[m["label"]], label=m["label"], color=m["c"], lw=2, alpha=0.8)
                    ax1.plot(times_index, avg_app_temp, color="gray", ls=":", lw=1.5, label="Percepita")
                    ax1.axhline(0, color='black', lw=1)
                    ax1.set_ylabel("Temp (°C)")
                    ax1.grid(True, alpha=0.3)
                    ax1.legend(loc='upper left', fontsize=8)
                    ax1.xaxis.set_major_formatter(date_fmt)
                    ax1.tick_params(labelbottom=True)

                    precip_to_plot = avg_precip.copy()
                    precip_to_plot[snow_mask] = 0 

                    ax2.bar(times_index, precip_to_plot, width=0.04, color="dodgerblue", alpha=0.6, label="Pioggia Liquida")
                    ax2b = ax2.twinx()
                    if any(snow_mask):
                        bars = ax2b.bar(times_index[snow_mask], avg_snow[snow_mask], width=0.04, 
                                color="cyan", edgecolor="blue", hatch="///", label="Neve", alpha=0.9)
                        is_long_range = giorni > 3
                        rotation_val = 90 if is_long_range else 0
                        font_val = 6 if is_long_range else 7
                        threshold_val = 0.5 if is_long_range else 0.3 
                        max_h_snow = np.max(avg_snow[snow_mask])
                        ax2b.set_ylim(0, max_h_snow * (1.5 if is_long_range else 1.3))
                        for rect in bars:
                            h = rect.get_height()
                            if h > threshold_val: 
                                ax2b.text(rect.get_x() + rect.get_width()/2., 1.05*h,
                                        f'{h:.1f}', ha='center', va='bottom', fontsize=font_val, 
                                        rotation=rotation_val, color='darkblue', fontweight='bold')
                    ax2.set_ylabel("Pioggia (mm)", color="dodgerblue")
                    ax2b.set_ylabel("Neve (cm)", color="darkblue")
                    ax2.xaxis.set_major_formatter(date_fmt)
                    st.pyplot(fig1)

                with tab2:
                    fig2, (ax3, ax4) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
                    ax3.plot(times_index, avg_wind, color="blue", label="Media", lw=2)
                    ax3.fill_between(times_index, avg_wind, avg_gust, color="red", alpha=0.2, label="Raffiche")
                    ax3.plot(times_index, avg_gust, color="red", lw=1, ls="--")
                    ax3.set_ylabel("Km/h")
                    ax3.legend(loc='upper left', fontsize=8)
                    ax3.grid(True, alpha=0.3)
                    ax3.xaxis.set_major_formatter(date_fmt)
                    ax3.tick_params(labelbottom=True)
                    ax4.plot(times_index, avg_freezing, color="green", lw=2, label="Quota 0°C")
                    ax4.fill_between(times_index, avg_freezing, 0, color="green", alpha=0.05)
                    ax4.set_ylabel("Metri (slm)")
                    ax4.legend(loc='upper left', fontsize=8)
                    ax4.grid(True, alpha=0.3)
                    ax4.xaxis.set_major_formatter(date_fmt)
                    st.pyplot(fig2)

                with tab3:
                    fig3, ax5 = plt.subplots(figsize=(14, 6))
                    ax5.plot(times_index, avg_press, color="black", lw=2)
                    ax5.set_ylabel("hPa")
                    ax5.grid(True)
                    ax5.xaxis.set_major_formatter(date_fmt)
                    st.pyplot(fig3)
                
        except Exception as e:
            st.error(f"Errore tecnico: {e}")
