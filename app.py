import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Vexor Meteo Ultimate", page_icon="🏔️", layout="centered")

st.title("🌍 VEXOR METEO ULTIMATE")
st.write("Stazione Meteo Tascabile Multi-Modello")

# --- INPUT ---
col1, col2 = st.columns([3, 1])
with col1:
    citta_scelta = st.text_input("Località:", value="Prato Nevoso")
with col2:
    giorni = st.selectbox("Durata:", [3, 7, 10], index=0)

if st.button("Lancia Analisi 🚀", type="primary"):
    
    with st.spinner(f'📡 Tech sta scaricando i dati completi per {citta_scelta}...'):
        try:
            # 1. GEOCODING
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_res = requests.get(geo_url, params={"name": citta_scelta, "count": 1, "language": "it"}).json()
            
            if "results" not in geo_res:
                st.error("❌ Città non trovata.")
                st.stop()
                
            loc = geo_res["results"][0]
            LAT, LON, NAME = loc["latitude"], loc["longitude"], loc["name"]
            COUNTRY = loc.get("country", "")
            
            # Mappa
            st.success(f"📍 Target: **{NAME}** ({COUNTRY})")
            map_data = pd.DataFrame({'lat': [LAT], 'lon': [LON]})
            st.map(map_data, zoom=10, use_container_width=True)

            # 2. SCARICO DATI
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
            bar = st.progress(0)
            
            for i, m in enumerate(models):
                bar.progress((i + 1) * 25)
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
            
            bar.empty()

            # 3. ELABORAZIONE
            if not data_temp:
                st.error("Nessun dato dai modelli.")
            else:
                # Allineamento
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
                
                tot_pioggia = np.sum(avg_precip)
                tot_neve = np.sum(avg_snow)
                max_wind = np.max(avg_gust)
                
                # --- DASHBOARD ---
                st.markdown("### 📊 Riepilogo Evento")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Tot. Pioggia", f"{tot_pioggia:.1f} mm")
                k2.metric("Tot. Neve", f"{tot_neve:.1f} cm", delta="Powder!" if tot_neve > 10 else None)
                k3.metric("Raffica Max", f"{max_wind:.0f} km/h", delta="Danger" if max_wind > 60 else None)
                k4.metric("Press. Min", f"{np.nanmin(avg_press):.0f} hPa")

                st.divider()

                # --- GRAFICI ---
                tab1, tab2, tab3 = st.tabs(["🌡️ Temp & Neve", "🌬️ Vento & Zero", "📉 Pressione"])
                
                # Formattatore data comune
                date_fmt = mdates.DateFormatter('%d/%m %Hh')
                
                # TAB 1: TEMP + PRECIPITAZIONI
                with tab1:
                    # Aumento spazio verticale (figsize)
                    fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 11), sharex=True, gridspec_kw={'height_ratios': [1.5, 1]})
                    
                    # Grafico SOPRA (Temp)
                    df_temp = pd.DataFrame({k: v[:min_len] for k,v in data_temp.items()}, index=times_index)
                    for m in models:
                        if m["label"] in df_temp.columns:
                            ax1.plot(df_temp.index, df_temp[m["label"]], label=m["label"], color=m["c"], lw=2, alpha=0.8)
                    ax1.plot(times_index, avg_app_temp, color="gray", ls=":", lw=1.5, label="Percepita")
                    ax1.axhline(0, color='black', lw=1)
                    ax1.set_ylabel("Temp (°C)")
                    ax1.grid(True, alpha=0.3)
                    ax1.legend(loc='upper left', fontsize=8)
                    
                    # MODIFICA: Mostro data anche sotto al grafico sopra
                    ax1.xaxis.set_major_formatter(date_fmt)
                    ax1.tick_params(labelbottom=True)

                    # Grafico SOTTO (Pioggia/Neve)
                    ax2.bar(times_index, avg_precip, width=0.04, color="dodgerblue", alpha=0.6, label="Pioggia")
                    
                    ax2b = ax2.twinx()
                    snow_idx = avg_snow > 0.1
                    if any(snow_idx):
                        bars = ax2b.bar(times_index[snow_idx], avg_snow[snow_idx], width=0.04, 
                                color="cyan", edgecolor="blue", hatch="///", label="Neve", alpha=0.9)
                        
                        # MODIFICA: Spaziatura etichette neve
                        # Aumento il limite Y per fare spazio ai numeri
                        max_h_snow = np.max(avg_snow[snow_idx])
                        ax2b.set_ylim(0, max_h_snow * 1.3) # +30% di spazio sopra

                        for rect in bars:
                            h = rect.get_height()
                            if h > 0.3: # Scrivo solo se rilevante
                                ax2b.text(rect.get_x() + rect.get_width()/2., 1.05*h,
                                        f'{h:.1f}', ha='center', va='bottom', fontsize=7, color='darkblue', fontweight='bold')

                    ax2.set_ylabel("Pioggia (mm)", color="dodgerblue")
                    ax2b.set_ylabel("Neve (cm)", color="darkblue")
                    
                    ax2.xaxis.set_major_formatter(date_fmt)
                    st.pyplot(fig1)

                # TAB 2: VENTO + ZERO TERMICO
                with tab2:
                    fig2, (ax3, ax4) = plt.subplots(2, 1, figsize=(10, 10), sharex=True)
                    
                    # Grafico SOPRA (Vento)
                    ax3.plot(times_index, avg_wind, color="blue", label="Media", lw=2)
                    ax3.fill_between(times_index, avg_wind, avg_gust, color="red", alpha=0.2, label="Raffiche")
                    ax3.plot(times_index, avg_gust, color="red", lw=1, ls="--")
                    ax3.set_ylabel("Km/h")
                    ax3.legend(loc='upper left', fontsize=8)
                    ax3.grid(True, alpha=0.3)
                    
                    # MODIFICA: Data visibile anche qui
                    ax3.xaxis.set_major_formatter(date_fmt)
                    ax3.tick_params(labelbottom=True)
                    
                    # Grafico SOTTO (Zero Termico)
                    ax4.plot(times_index, avg_freezing, color="green", lw=2, label="Quota 0°C")
                    ax4.fill_between(times_index, avg_freezing, 0, color="green", alpha=0.05)
                    ax4.set_ylabel("Metri (slm)")
                    ax4.legend(loc='upper left', fontsize=8)
                    ax4.grid(True, alpha=0.3)
                    
                    ax4.xaxis.set_major_formatter(date_fmt)
                    st.pyplot(fig2)

                # TAB 3: PRESSIONE
                with tab3:
                    fig3, ax5 = plt.subplots(figsize=(10, 6))
                    ax5.plot(times_index,
