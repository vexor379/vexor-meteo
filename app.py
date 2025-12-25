import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from streamlit_folium import st_folium
import folium

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Vexor Meteo Suite", page_icon="🏔️", layout="wide") 

st.title("🌍 VEXOR METEO SUITE v6")

# --- SESSION STATE ---
defaults = {
    'lat': 44.25,
    'lon': 7.78,
    'location_name': "Prato Nevoso (Default)",
    'box_text': "",
    'start_analysis': False
}
for key, val in defaults.items():
    if key not in st.session_state: st.session_state[key] = val

# --- FUNZIONE CACHED ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_meteo_data(lat, lon, days):
    models = [
        {"id": "ecmwf_ifs025", "label": "ECMWF", "c": "red"},
        {"id": "gfs_seamless", "label": "GFS", "c": "blue"},
        {"id": "icon_seamless", "label": "ICON", "c": "green"},
        {"id": "jma_seamless", "label": "JMA", "c": "purple"}
    ]
    
    # AGGIUNTO: snow_depth (spessore neve al suolo)
    params_base = "temperature_2m,precipitation,snowfall,pressure_msl,wind_speed_10m,wind_gusts_10m,apparent_temperature,freezing_level_height,cloud_cover,snow_depth"
    
    data_temp = {}
    # Aggiungo 'depth' agli accumulatori
    acc = {k: [] for k in ["precip", "snow", "press", "wind", "gust", "app_temp", "freezing", "cloud", "depth"]}
    times_index = None
    
    for m in models:
        p = {"latitude": lat, "longitude": lon, "hourly": params_base, "models": m["id"], 
                "timezone": "auto", "forecast_days": days}
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast", params=p, timeout=8).json()
            if 'hourly' in r:
                h = r["hourly"]
                current_time_index = pd.to_datetime(h["time"])
                
                if times_index is None: times_index = current_time_index
                min_len_local = min(len(times_index), len(h["temperature_2m"]))
                
                data_temp[m["label"]] = h["temperature_2m"][:min_len_local]
                
                acc["precip"].append([x if x else 0.0 for x in h.get("precipitation", [])][:min_len_local])
                acc["snow"].append([x if x else 0.0 for x in h.get("snowfall", [])][:min_len_local])
                acc["press"].append([x if x else np.nan for x in h.get("pressure_msl", [])][:min_len_local])
                acc["wind"].append([x if x else 0.0 for x in h.get("wind_speed_10m", [])][:min_len_local])
                acc["gust"].append([x if x else 0.0 for x in h.get("wind_gusts_10m", [])][:min_len_local])
                acc["app_temp"].append([x if x else np.nan for x in h.get("apparent_temperature", [])][:min_len_local])
                acc["freezing"].append([x if x else np.nan for x in h.get("freezing_level_height", [])][:min_len_local])
                acc["cloud"].append([x if x else 0.0 for x in h.get("cloud_cover", [])][:min_len_local])
                # snow_depth arriva in METRI, lo teniamo così e convertiamo dopo
                acc["depth"].append([x if x else 0.0 for x in h.get("snow_depth", [])][:min_len_local])
        except: continue
        
    return data_temp, acc, times_index

# --- FUNZIONE RICERCA ---
def cerca_citta(nome):
    if not nome: return False
    try:
        res = requests.get("https://geocoding-api.open-meteo.com/v1/search", 
                           params={"name": nome, "count": 1, "language": "it"}, timeout=5).json()
        if "results" in res:
            loc = res["results"][0]
            st.session_state.lat = loc["latitude"]
            st.session_state.lon = loc["longitude"]
            st.session_state.location_name = f"{loc['name']} ({loc.get('country','')})"
            st.session_state.box_text = f"{loc['name']} ({loc.get('country','')})"
            st.session_state.start_analysis = True
            return True
        else:
            st.sidebar.warning("❌ Località non trovata.")
            return False
    except: return False

# --- SIDEBAR ---
with st.sidebar:
    st.header("🎮 Controlli")
    with st.form("analysis_form"):
        city_input = st.text_input("📍 Cerca Località:", value=st.session_state.box_text)
        giorni = st.selectbox("📅 Durata Previsione:", [3, 7, 10, 14], index=1)
        st.markdown("---")
        submitted = st.form_submit_button("Lancia Analisi 🚀", type="primary", use_container_width=True)
    st.caption("Vexor Meteo Suite v6.0")

if submitted and city_input:
    if city_input != st.session_state.location_name:
        if cerca_citta(city_input): st.rerun()

# --- LAYOUT PRINCIPALE ---
st.markdown(f"### 🎯 Target: **{st.session_state.location_name}**")

m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=10)
folium.Marker([st.session_state.lat, st.session_state.lon], 
              popup=st.session_state.location_name, icon=folium.Icon(color="red", icon="info-sign")).add_to(m)
output_mappa = st_folium(m, height=250, use_container_width=True)

if output_mappa['last_clicked']:
    clat, clon = output_mappa['last_clicked']['lat'], output_mappa['last_clicked']['lng']
    if (abs(clat - st.session_state.lat) > 0.0001) or (abs(clon - st.session_state.lon) > 0.0001):
        st.session_state.lat = clat
        st.session_state.lon = clon
        nome_punto = f"Punto Mappa ({clat:.2f}, {clon:.2f})"
        st.session_state.location_name = nome_punto
        st.session_state.box_text = nome_punto
        st.session_state.start_analysis = True
        st.rerun()

# --- MOTORE ANALISI ---
if st.session_state.start_analysis:
    st.divider()
    with st.spinner(f'📡 Calcolo SWE in kg/m² e altezza neve...'):
        LAT, LON = st.session_state.lat, st.session_state.lon
        data_temp, acc, times_index = get_meteo_data(LAT, LON, giorni)
        
        if not data_temp or times_index is None:
            st.error("Dati mancanti. Riprova.")
        else:
            try:
                min_len = len(times_index)
                for k in acc: acc[k] = [x[:min_len] for x in acc[k]]
                
                avg = {}
                for k, v_list in acc.items():
                    if v_list: avg[k] = np.nanmean(v_list, axis=0)
                    else: avg[k] = np.zeros(min_len)

                # --- CALCOLI SCIENTIFICI ---
                snow_mask = avg["snow"] > 0.1
                
                # 1. SWE: mm e kg/m2 sono 1:1 per l'acqua
                tot_swe = np.sum(avg["precip"])
                tot_rain = np.sum(avg["precip"][~snow_mask])
                
                # 2. Neve Fresca (nuova caduta)
                tot_snow_fresh = np.sum(avg["snow"])
                
                # 3. Neve AL SUOLO (Depth) - Convertiamo da Metri a Centimetri
                # Prendiamo il valore attuale (indice 0) e il massimo previsto
                current_depth_cm = avg["depth"][0] * 100 if len(avg["depth"]) > 0 else 0
                max_depth_cm = np.max(avg["depth"]) * 100 if len(avg["depth"]) > 0 else 0
                
                max_gust = np.max(avg["gust"])
                
                # --- DASHBOARD (6 Colonne ora!) ---
                # Uso colonne strette per farci stare tutto
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                
                c1.metric("SWE", f"{tot_swe:.1f} kg/m²", help="Equivalente liquido (1 mm = 1 kg/m²)")
                c2.metric("Solo Pioggia", f"{tot_rain:.1f} mm", delta="Inverse" if tot_rain>5 else None, delta_color="inverse")
                c3.metric("Neve Fresca", f"{tot_snow_fresh:.1f} cm", delta="Accumulo" if tot_snow_fresh>5 else None)
                
                # NUOVE METRICHE NEVE SUOLO
                c4.metric("Neve Suolo (ORA)", f"{current_depth_cm:.0f} cm", help="Stima neve presente ora al suolo")
                c5.metric("Neve Suolo (MAX)", f"{max_depth_cm:.0f} cm", help="Massimo accumulo previsto (Vecchio + Nuovo)", delta=f"+{max_depth_cm-current_depth_cm:.0f} cm")
                
                c6.metric("Raffica Max", f"{max_gust:.0f} km/h", delta="Danger" if max_gust>60 else None)
                
                st.markdown("---")

                # --- GRAFICI ---
                t1, t2, t3, t4 = st.tabs(["🌡️ Temp & Neve", "☁️ Cielo & Sole", "🌬️ Vento & Zero", "📉 Pressione"])
                date_fmt = mdates.DateFormatter('%d/%m %Hh')
                
                # Funzione helper per mettere le date su tutti i grafici
                def format_xaxis(ax):
                    ax.xaxis.set_major_formatter(date_fmt)
                    ax.tick_params(labelbottom=True) # FORZA l'etichetta anche se il grafico è sopra
                    ax.grid(True, alpha=0.3)

                # T1
                with t1:
                    # Aumento hspace per far leggere bene le date del grafico sopra
                    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), gridspec_kw={'height_ratios': [1.5, 1], 'hspace': 0.3})
                    
                    df_temp = pd.DataFrame({k: v[:min_len] for k,v in data_temp.items()}, index=times_index)
                    for col in df_temp.columns:
                        ax1.plot(df_temp.index, df_temp[col], label=col, lw=2, alpha=0.8)
                    ax1.plot(times_index, avg["app_temp"], color="gray", ls=":", label="Percepita")
                    ax1.axhline(0, c="black", lw=1)
                    ax1.legend(loc="upper left", fontsize=8); ax1.set_ylabel("°C"); ax1.set_title("Temperatura")
                    format_xaxis(ax1) # Date visibili!
                    
                    rain_plot = avg["precip"].copy(); rain_plot[snow_mask] = 0
                    ax2.bar(times_index, rain_plot, width=0.04, color="dodgerblue", alpha=0.6, label="Pioggia")
                    ax2b = ax2.twinx()
                    if any(snow_mask):
                        bars = ax2b.bar(times_index[snow_mask], avg["snow"][snow_mask], width=0.04, color="cyan", hatch="///", edgecolor="blue")
                        thresh = 0.5 if giorni>3 else 0.2
                        for r in bars:
                            h = r.get_height()
                            if h > thresh:
                                ax2b.text(r.get_x()+r.get_width()/2, h*1.05, f"{h:.1f}", ha="center", fontsize=7, color="darkblue", rotation=90 if giorni>3 else 0)
                    ax2.set_ylabel("Pioggia (mm)"); ax2b.set_ylabel("Neve (cm)"); ax2.set_title("Precipitazioni Orarie")
                    format_xaxis(ax2)
                    st.pyplot(fig)

                # T2
                with t2:
                    fig_c, ax_c = plt.subplots(figsize=(14, 6))
                    ax_c.fill_between(times_index, avg["cloud"], 0, color="gray", alpha=0.4, label="Nubi (%)")
                    ax_c.plot(times_index, avg["cloud"], color="black", lw=1)
                    ax_c.set_ylim(0, 100); ax_c.set_ylabel("Copertura (%)")
                    ax_c.axhspan(0, 20, color="yellow", alpha=0.1, label="Zona Soleggiata")
                    ax_c.legend(loc="upper right")
                    format_xaxis(ax_c)
                    st.pyplot(fig_c)

                # T3
                with t3:
                    fig_w, (ax_w, ax_z) = plt.subplots(2, 1, figsize=(14, 12), gridspec_kw={'hspace': 0.3})
                    ax_w.plot(times_index, avg["wind"], color="blue", label="Vento")
                    ax_w.fill_between(times_index, avg["wind"], avg["gust"], color="red", alpha=0.2, label="Raffiche")
                    ax_w.legend(); ax_w.set_ylabel("km/h"); ax_w.set_title("Vento")
                    format_xaxis(ax_w) # Date visibili!
                    
                    ax_z.plot(times_index, avg["freezing"], color="green", lw=2, label="Quota 0°C")
                    ax_z.fill_between(times_index, avg["freezing"], 0, color="green", alpha=0.05)
                    ax_z.legend(); ax_z.set_ylabel("Metri"); ax_z.set_title("Zero Termico")
                    format_xaxis(ax_z)
                    st.pyplot(fig_w)

                # T4
                with t4:
                    fig_p, ax_p = plt.subplots(figsize=(14, 6))
                    ax_p.plot(times_index, avg["press"], color="black", lw=2)
                    ax_p.set_ylabel("hPa"); ax_p.set_title("Pressione")
                    format_xaxis(ax_p)
                    st.pyplot(fig_p)

                # CSV
                st.divider()
                st.subheader("📥 Dati Completi")
                df_export = pd.DataFrame({
                    "Data": times_index,
                    "Temp": np.nanmean(list(data_temp.values()), axis=0)[:min_len],
                    "SWE_kg_m2": avg["precip"], "Neve_Fresca_cm": avg["snow"], 
                    "Neve_Suolo_cm": np.array(avg["depth"])*100, # Export in cm
                    "Vento_kmh": avg["wind"]
                })
                csv = df_export.to_csv(index=False).encode('utf-8')
                st.download_button("Scarica CSV", data=csv, file_name=f"meteo_{st.session_state.location_name}.csv", mime="text/csv")

            except Exception as e:
                st.error(f"Errore grafico: {e}")
