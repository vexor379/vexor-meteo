import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from streamlit_folium import st_folium
import folium
from datetime import datetime, timedelta

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Vexor Meteo Suite", page_icon="🏔️", layout="wide") 

st.title("🌍 VEXOR METEO SUITE v8.1 (Full Optional)")

# --- SESSION STATE ---
defaults = {
    'lat': 44.25,
    'lon': 7.78,
    'elevation': 1500, # Default Prato Nevoso
    'location_name': "Prato Nevoso (Default)",
    'box_text': "",
    'start_analysis': False
}
for key, val in defaults.items():
    if key not in st.session_state: st.session_state[key] = val

# --- MOTORE 1: PREVISIONE MULTI-MODELLO ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_forecast_multi_model(lat, lon, elevation, days):
    models = [
        {"id": "ecmwf_ifs025", "label": "ECMWF", "c": "red"},
        {"id": "gfs_seamless", "label": "GFS", "c": "blue"},
        {"id": "icon_seamless", "label": "ICON", "c": "green"},
        {"id": "jma_seamless", "label": "JMA", "c": "purple"}
    ]
    
    params_base = "temperature_2m,precipitation,snowfall,pressure_msl,wind_speed_10m,wind_gusts_10m,apparent_temperature,freezing_level_height,cloud_cover,snow_depth"
    
    data_temp = {}
    acc = {k: [] for k in ["precip", "snow", "press", "wind", "gust", "app_temp", "freezing", "cloud", "depth"]}
    times_index = None
    
    for m in models:
        p = {
            "latitude": lat, "longitude": lon, 
            "elevation": elevation, 
            "hourly": params_base, 
            "models": m["id"], 
            "timezone": "auto", 
            "forecast_days": days,
            "past_days": 2
        }
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast", params=p, timeout=8).json()
            if 'hourly' in r:
                h = r["hourly"]
                current_time_index = pd.to_datetime(h["time"])
                if times_index is None: times_index = current_time_index
                
                min_len = min(len(times_index), len(h["temperature_2m"]))
                
                data_temp[m["label"]] = h["temperature_2m"][:min_len]
                acc["precip"].append([x if x else 0.0 for x in h.get("precipitation", [])][:min_len])
                acc["snow"].append([x if x else 0.0 for x in h.get("snowfall", [])][:min_len])
                acc["press"].append([x if x else np.nan for x in h.get("pressure_msl", [])][:min_len])
                acc["wind"].append([x if x else 0.0 for x in h.get("wind_speed_10m", [])][:min_len])
                acc["gust"].append([x if x else 0.0 for x in h.get("wind_gusts_10m", [])][:min_len])
                acc["app_temp"].append([x if x else np.nan for x in h.get("apparent_temperature", [])][:min_len])
                acc["freezing"].append([x if x else np.nan for x in h.get("freezing_level_height", [])][:min_len])
                acc["cloud"].append([x if x else 0.0 for x in h.get("cloud_cover", [])][:min_len])
                acc["depth"].append([x if x else 0.0 for x in h.get("snow_depth", [])][:min_len])
        except: continue
        
    return data_temp, acc, times_index

# --- MOTORE 2: STORICO STAGIONALE ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_seasonal_history(lat, lon, elevation):
    today = datetime.now().date()
    start_season = datetime(today.year if today.month > 8 else today.year - 1, 11, 1).date()
    days_since_nov1 = (today - start_season).days
    
    params = {
        "latitude": lat, "longitude": lon, "elevation": elevation,
        "hourly": "snowfall,precipitation,snow_depth",
        "models": "ecmwf_ifs025",
        "timezone": "auto",
        "past_days": max(days_since_nov1, 3), 
        "forecast_days": 0
    }
    
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10).json()
        h = r.get("hourly", {})
        df = pd.DataFrame({
            "time": pd.to_datetime(h.get("time", [])),
            "snow": h.get("snowfall", []),
            "precip": h.get("precipitation", []),
            "depth": h.get("snow_depth", [])
        })
        return df
    except: return None

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
            st.session_state.elevation = loc.get("elevation", 1000)
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
    
    st.info(f"🏔️ Quota Forzata: **{st.session_state.elevation:.0f}m**")

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
        st.session_state.location_name = f"Punto Mappa ({clat:.2f}, {clon:.2f})"
        st.session_state.box_text = st.session_state.location_name
        st.session_state.start_analysis = True
        st.rerun()

# --- MOTORE ANALISI ---
if st.session_state.start_analysis:
    st.divider()
    with st.spinner(f'📡 Analisi Completa (Multi-Modello + Storico)...'):
        
        # 1. SCARICO PREVISIONI
        data_temp, acc, times_index = get_forecast_multi_model(st.session_state.lat, st.session_state.lon, st.session_state.elevation, giorni)
        
        # 2. SCARICO STORICO
        df_season = get_seasonal_history(st.session_state.lat, st.session_state.lon, st.session_state.elevation)
        
        if not data_temp or times_index is None:
            st.error("Errore recupero dati forecast.")
        else:
            try:
                # --- ELABORAZIONE DATI ---
                min_len = len(times_index)
                for k in acc: acc[k] = [x[:min_len] for x in acc[k]]
                
                avg = {}
                for k, v_list in acc.items():
                    if v_list: avg[k] = np.nanmean(v_list, axis=0)
                    else: avg[k] = np.zeros(min_len)

                # Calcoli Forecast
                snow_mask = avg["snow"] > 0.1
                
                now = pd.Timestamp.now()
                is_future = times_index >= now
                
                tot_swe_forecast = np.sum(avg["precip"][is_future]) 
                tot_snow_forecast = np.sum(avg["snow"][is_future])
                max_gust = np.max(avg["gust"])
                
                # Calcoli Stagionali
                season_snow_total = 0
                current_depth_season = 0
                
                if df_season is not None:
                    past_mask = df_season["time"] < now
                    season_snow_total = df_season.loc[past_mask, "snow"].sum()
                    if len(df_season) > 0:
                        current_depth_season = df_season["depth"].iloc[-1] * 100 
                
                # --- CRUSCOTTO UNIFICATO (BARRA DI RIASSUNTO) ---
                st.subheader("📊 Cruscotto Unificato")
                c1, c2, c3, c4, c5 = st.columns(5)
                
                c1.metric("Neve Stagione", f"{season_snow_total:.0f} cm", help="Totale caduto dal 1° Novembre")
                c2.metric("Neve al Suolo (Oggi)", f"{current_depth_season:.0f} cm", help="Altezza manto nevoso attuale")
                c3.metric("Neve in Arrivo", f"{tot_snow_forecast:.0f} cm", delta="Forecast", help=f"Prossimi {giorni} giorni")
                c4.metric("SWE Previsto", f"{tot_swe_forecast:.1f} kg/m²", help="Acqua Equivalente (Pioggia + Neve)")
                c5.metric("Raffica Max", f"{max_gust:.0f} km/h", delta="Danger" if max_gust>60 else None)
                
                st.markdown("---")

                # --- 4 TABS COMPLETE ---
                tabs = st.tabs(["🔍 Analisi Dettagliata", "📉 Grafico Stagionale", "☁️ Cielo & Vento", "🎈 Pressione"])
                date_fmt = mdates.DateFormatter('%d/%m %Hh')
                
                def format_ax(ax):
                    ax.xaxis.set_major_formatter(date_fmt)
                    ax.tick_params(labelbottom=True)
                    ax.grid(True, alpha=0.3)

                # TAB 1: TEMP + PRECIP (Multi-Model)
                with tabs[0]:
                    st.caption("Confronto modelli per i prossimi giorni")
                    fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), gridspec_kw={'height_ratios': [1.5, 1], 'hspace': 0.3})
                    
                    # Temp
                    df_temp = pd.DataFrame({k: v[:min_len] for k,v in data_temp.items()}, index=times_index)
                    for col in df_temp.columns:
                        ax1.plot(df_temp.index, df_temp[col], label=col, lw=2, alpha=0.8)
                    ax1.plot(times_index, avg["app_temp"], color="gray", ls=":", label="Percepita")
                    ax1.axhline(0, c="black", lw=1)
                    ax1.legend(loc="upper left", fontsize=8); ax1.set_ylabel("°C"); ax1.set_title("Temperatura")
                    format_ax(ax1)
                    
                    # Pioggia/Neve
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
                    ax2.set_ylabel("Pioggia (mm)"); ax2b.set_ylabel("Neve (cm)"); ax2.set_title("Precipitazioni")
                    format_ax(ax2)
                    st.pyplot(fig1)

                # TAB 2: STAGIONALE
                with tabs[1]:
                    if df_season is not None:
                        fig_s, ax_s = plt.subplots(figsize=(14, 6))
                        ax_s.fill_between(df_season["time"], df_season["depth"]*100, color="cyan", alpha=0.4, label="Neve al Suolo (Storico)")
                        ax_s.plot(df_season["time"], df_season["depth"]*100, color="blue", lw=1)
                        ax_s.plot(times_index, avg["depth"]*100, color="red", ls="--", label="Previsione")
                        ax_s.axvline(now, color="black", ls=":", label="Oggi")
                        ax_s.set_ylabel("cm Neve"); ax_s.set_title("Stagione Invernale Completa (1 Nov -> Oggi -> Futuro)")
                        ax_s.legend(); ax_s.grid(True, alpha=0.3)
                        ax_s.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
                        st.pyplot(fig_s)
                    else:
                        st.warning("Dati stagionali non disponibili.")

                # TAB 3: CIELO, VENTO, ZERO TERMICO
                with tabs[2]:
                    fig_w, (ax_c, ax_w, ax_z) = plt.subplots(3, 1, figsize=(14, 15), gridspec_kw={'hspace': 0.3})
                    
                    # Nubi
                    ax_c.fill_between(times_index, avg["cloud"], 0, color="gray", alpha=0.4, label="Nubi (%)")
                    ax_c.plot(times_index, avg["cloud"], color="black", lw=1)
                    ax_c.set_ylim(0, 100); ax_c.set_ylabel("% Copertura"); ax_c.set_title("Copertura Nuvolosa")
                    ax_c.axhspan(0, 20, color="yellow", alpha=0.1, label="Soleggiato")
                    format_ax(ax_c)
                    
                    # Vento
                    ax_w.plot(times_index, avg["wind"], color="blue", label="Vento Medio")
                    ax_w.fill_between(times_index, avg["wind"], avg["gust"], color="red", alpha=0.2, label="Raffiche")
                    ax_w.set_ylabel("km/h"); ax_w.set_title("Vento")
                    format_ax(ax_w)
                    
                    # Zero Termico
                    ax_z.plot(times_index, avg["freezing"], color="green", lw=2, label="Quota 0°C")
                    ax_z.fill_between(times_index, avg["freezing"], 0, color="green", alpha=0.05)
                    ax_z.set_ylabel("Metri"); ax_z.set_title("Zero Termico")
                    format_ax(ax_z)
                    
                    st.pyplot(fig_w)

                # TAB 4: PRESSIONE (RIPRISTINATA!)
                with tabs[3]:
                    fig_p, ax_p = plt.subplots(figsize=(14, 6))
                    ax_p.plot(times_index, avg["press"], color="black", lw=2)
                    ax_p.set_ylabel("hPa"); ax_p.set_title("Pressione Atmosferica (MSL)")
                    format_ax(ax_p)
                    st.pyplot(fig_p)

                # CSV DOWNLOAD
                st.divider()
                df_export = pd.DataFrame({
                    "Data": times_index,
                    "Temp_Media": np.nanmean(list(data_temp.values()), axis=0)[:min_len],
                    "SWE_kg_m2": avg["precip"], "Neve_Prevista_cm": avg["snow"], 
                    "Vento_kmh": avg["wind"], "Pressione_hPa": avg["press"]
                })
                csv = df_export.to_csv(index=False).encode('utf-8')
                st.download_button("Scarica Dati Forecast (CSV)", data=csv, file_name="meteo_forecast.csv", mime="text/csv")

            except Exception as e:
                st.error(f"Errore grafico: {e}")
