import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Vexor Meteo", page_icon="⛈️")

st.title("🌍 VEXOR METEO MOBILE")
st.write("Il sistema di previsione multi-modello di Vexor & Tech.")

# --- 1. INPUT UTENTE ---
citta_scelta = st.text_input("Inserisci la città:", value="Prato Nevoso")

# Bottone per avviare (così non ricarica mentre scrivi)
if st.button("Analizza Meteo"):
    
    with st.spinner('📡 Tech sta interrogando i satelliti...'):
        try:
            # --- GEOCODING ---
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_res = requests.get(geo_url, params={"name": citta_scelta, "count": 1, "language": "it"}).json()
            
            if "results" not in geo_res:
                st.error("❌ Città non trovata. Controlla il nome.")
                st.stop()
                
            loc = geo_res["results"][0]
            LAT, LON, NAME = loc["latitude"], loc["longitude"], loc["name"]
            COUNTRY = loc.get("country", "")
            
            st.success(f"📍 Trovata: **{NAME}** ({COUNTRY})")

            # --- 2. SCARICO DATI (MODULARE) ---
            models = [
                {"id": "ecmwf_ifs025", "label": "ECMWF (EU)", "c": "red"},
                {"id": "gfs_seamless", "label": "GFS (USA)", "c": "blue"},
                {"id": "icon_seamless", "label": "ICON (DE)", "c": "green"},
                {"id": "jma_seamless", "label": "JMA (JP)", "c": "purple"}
            ]

            data_temp = {}
            precip_accum = []
            snow_accum = []
            press_accum = []
            times_index = None
            base_url = "https://api.open-meteo.com/v1/forecast"

            progress_bar = st.progress(0)
            
            for i, m in enumerate(models):
                # Aggiorno la barra di caricamento
                progress_bar.progress((i + 1) * 25)
                
                params = {
                    "latitude": LAT, "longitude": LON,
                    "hourly": "temperature_2m,precipitation,snowfall,pressure_msl",
                    "models": m["id"],
                    "timezone": "auto",
                    "forecast_days": 3 
                }
                
                try:
                    response = requests.get(base_url, params=params).json()
                    
                    if 'error' in response or "hourly" not in response:
                        continue
                        
                    hourly = response["hourly"]
                    
                    # Salvo i tempi dal primo modello valido
                    if times_index is None:
                        times_index = pd.to_datetime(hourly["time"])
                    
                    data_temp[m["label"]] = hourly["temperature_2m"]
                    
                    # Gestione dati
                    p = [x if x else 0.0 for x in hourly.get("precipitation", [])]
                    s = [x if x else 0.0 for x in hourly.get("snowfall", [])]
                    pr = [x if x else np.nan for x in hourly.get("pressure_msl", [])]
                    
                    precip_accum.append(p)
                    snow_accum.append(s)
                    press_accum.append(pr)
                    
                except Exception as e:
                    continue

            # --- 3. ELABORAZIONE E PLOT ---
            if not data_temp:
                st.error("❌ Nessun dato ricevuto dai modelli. Riprova più tardi.")
            else:
                # Allineamento lunghezze
                min_len = min([len(times_index)] + [len(x) for x in precip_accum])
                times_index = times_index[:min_len]
                
                avg_precip = np.mean([x[:min_len] for x in precip_accum], axis=0)
                avg_snow = np.mean([x[:min_len] for x in snow_accum], axis=0)
                avg_press = np.nanmean([x[:min_len] for x in press_accum], axis=0)
                
                df_temp = pd.DataFrame({k: v[:min_len] for k,v in data_temp.items()}, index=times_index)

                # Creazione Grafico
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12), sharex=True, gridspec_kw={'height_ratios': [1.5, 1]})
                
                # --- Grafico 1 ---
                for m in models:
                    if m["label"] in df_temp.columns:
                        ax1.plot(df_temp.index, df_temp[m["label"]], label=m["label"], color=m["c"], lw=2, alpha=0.8)
                
                ax1.axhline(0, color='black', lw=1)
                ax1.set_ylabel("Temperatura (°C)")
                ax1.grid(True, alpha=0.3)
                ax1.legend(loc='upper left', fontsize='small')
                
                ax1b = ax1.twinx()
                ax1b.plot(times_index, avg_press, color="gray", ls=":", lw=2, label="Pressione")
                ax1b.set_ylabel("hPa", color="gray")

                # --- Grafico 2 ---
                ax2.bar(times_index, avg_precip, width=0.04, color="dodgerblue", alpha=0.6, label="Pioggia")
                ax2.set_ylabel("Pioggia (mm)", color="dodgerblue")
                
                ax2b = ax2.twinx()
                snow_idx = avg_snow > 0.1
                if any(snow_idx):
                    bars = ax2b.bar(times_index[snow_idx], avg_snow[snow_idx], width=0.04, 
                            color="cyan", edgecolor="blue", hatch="///", label="Neve", alpha=0.9)
                    
                    # Etichette valori neve
                    for rect in bars:
                        h = rect.get_height()
                        if h > 0.5:
                            ax2b.text(rect.get_x() + rect.get_width()/2., 1.05*h,
                                    f'{h:.1f}', ha='center', va='bottom', fontsize=8, color='darkblue', fontweight='bold')

                ax2b.set_ylabel("NEVE (cm)", color="darkblue", fontweight='bold')
                
                # Formattazione
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m\n%H:%M'))
                ax2.xaxis.set_major_locator(mdates.HourLocator(interval=6))
                
                plt.tight_layout()
                
                # COMANDO MAGICO STREAMLIT PER MOSTRARE IL GRAFICO
                st.pyplot(fig)
                
        except Exception as e:
            st.error(f"Errore critico: {e}")
