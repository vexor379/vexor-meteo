import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Vexor Meteo Pro", page_icon="❄️", layout="centered")

st.title("🌍 VEXOR METEO - ANALYTICS")
st.write("Analisi Multi-Modello (GFS, ECMWF, ICON, JMA)")

# --- INPUT ---
col1, col2 = st.columns([3, 1])
with col1:
    citta_scelta = st.text_input("Località:", value="Prato Nevoso")
with col2:
    giorni = st.selectbox("Durata:", [3, 7], index=0)

if st.button("Lancia Analisi 🚀", type="primary"):
    
    with st.spinner(f'📡 Tech sta triangolando i dati per {citta_scelta}...'):
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
            
            st.success(f"📍 Posizione agganciata: **{NAME}** ({COUNTRY}) - Lat: {LAT:.2f}, Lon: {LON:.2f}")

            # 2. SCARICO DATI
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

            # Progress bar visuale
            bar = st.progress(0)
            
            for i, m in enumerate(models):
                bar.progress((i + 1) * 25)
                params = {
                    "latitude": LAT, "longitude": LON,
                    "hourly": "temperature_2m,precipitation,snowfall,pressure_msl",
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
                        
                        # Accumulo dati (sostituisco None con 0.0)
                        precip_accum.append([x if x else 0.0 for x in h.get("precipitation", [])])
                        snow_accum.append([x if x else 0.0 for x in h.get("snowfall", [])])
                        press_accum.append([x if x else np.nan for x in h.get("pressure_msl", [])])
                except: continue
            
            bar.empty() # Rimuovo barra

            # 3. CALCOLI E VISUALIZZAZIONE
            if not data_temp:
                st.error("Nessun dato dai modelli.")
            else:
                # Allineamento array
                min_len = min([len(times_index)] + [len(x) for x in precip_accum])
                times_index = times_index[:min_len]
                
                # Calcolo MEDIE ORARIE
                avg_precip = np.mean([x[:min_len] for x in precip_accum], axis=0)
                avg_snow = np.mean([x[:min_len] for x in snow_accum], axis=0)
                avg_press = np.nanmean([x[:min_len] for x in press_accum], axis=0)
                
                # --- CALCOLO TOTALI (ACCUMULI) ---
                # Sommo tutte le ore per avere il totale dell'evento
                tot_pioggia = np.sum(avg_precip)
                tot_neve = np.sum(avg_snow)
                
                # --- DASHBOARD METRICHE ---
                st.markdown("### 📊 Riepilogo Totale Evento")
                kpi1, kpi2, kpi3 = st.columns(3)
                
                kpi1.metric("Totale Pioggia", f"{tot_pioggia:.1f} mm", delta_color="normal")
                
                # Logica colore Neve: se è > 5cm diventa verde (buono), se no normale
                kpi2.metric("Totale Neve", f"{tot_neve:.1f} cm", 
                            delta="Powder Alert!" if tot_neve > 10 else None)
                
                kpi3.metric("Pressione Minima", f"{np.nanmin(avg_press):.0f} hPa")

                st.markdown("---")

                # --- GRAFICI ---
                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12), sharex=True, gridspec_kw={'height_ratios': [1.5, 1]})
                
                # Grafico Temp
                df_temp = pd.DataFrame({k: v[:min_len] for k,v in data_temp.items()}, index=times_index)
                for m in models:
                    if m["label"] in df_temp.columns:
                        ax1.plot(df_temp.index, df_temp[m["label"]], label=m["label"], color=m["c"], lw=2, alpha=0.8)
                
                ax1.axhline(0, color='black', lw=1)
                ax1.set_ylabel("Temperatura (°C)")
                ax1.grid(True, alpha=0.3)
                ax1.legend(loc='upper left', fontsize=8)
                ax1.set_title(f"Meteogramma: {NAME}", fontweight='bold')

                # Pressione
                ax1b = ax1.twinx()
                ax1b.plot(times_index, avg_press, color="gray", ls=":", lw=1.5, alpha=0.5)
                ax1b.set_ylabel("hPa", color="gray")

                # Grafico Precipitazioni
                ax2.bar(times_index, avg_precip, width=0.04, color="dodgerblue", alpha=0.6, label="Pioggia (mm/h)")
                ax2.set_ylabel("Pioggia oraria (mm)", color="dodgerblue")
                
                ax2b = ax2.twinx()
                snow_idx = avg_snow > 0.1
                if any(snow_idx):
                    bars = ax2b.bar(times_index[snow_idx], avg_snow[snow_idx], width=0.04, 
                            color="cyan", edgecolor="blue", hatch="///", label="Neve (cm/h)", alpha=0.9)
                
                ax2b.set_ylabel("NEVE oraria (cm)", color="darkblue")
                
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:00'))
                ax2.xaxis.set_major_locator(mdates.HourLocator(interval=12))
                plt.xticks(rotation=45)
                
                st.pyplot(fig)
                
        except Exception as e:
            st.error(f"Errore tecnico: {e}")
