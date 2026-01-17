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
st.set_page_config(page_title="Meteo Suite", page_icon="🏔️", layout="wide") 

st.title("🌍 METEO SUITE v9.0")

# --- SESSION STATE ---
defaults = {
    'lat': 44.25,
    'lon': 7.78,
    'elevation': 1500, # Default Prato Nevoso
    'location_name': "Prato Nevoso (Default)",
    'box_text': "",
    'start_analysis': True
}
for key, val in defaults.items():
    if key not in st.session_state: st.session_state[key] = val

# --- HELPER: PULIZIA DATI ---
def safe_float(x):
    if x is None: return 0.0
    return float(x)

# --- MOTORE 1: PREVISIONE MULTI-MODELLO (Solo Futuro) ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_forecast_safe(lat, lon, elevation, days):
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
            "past_days": 1 # Scarichiamo giusto 1 giorno per raccordare i grafici
        }
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast", params=p, timeout=8).json()
            if 'hourly' in r:
                h = r["hourly"]
                current_time_index = pd.to_datetime(h["time"], utc=True)
                if times_index is None: times_index = current_time_index
                
                min_len = min(len(times_index), len(h["temperature_2m"]))
                
                data_temp[m["label"]] = h["temperature_2m"][:min_len]
                acc["precip"].append([safe_float(x) for x in h.get("precipitation", [])][:min_len])
                acc["snow"].append([safe_float(x) for x in h.get("snowfall", [])][:min_len])
                acc["press"].append([safe_float(x) if x is not None else np.nan for x in h.get("pressure_msl", [])][:min_len])
                acc["wind"].append([safe_float(x) for x in h.get("wind_speed_10m", [])][:min_len])
                acc["gust"].append([safe_float(x) for x in h.get("wind_gusts_10m", [])][:min_len])
                acc["app_temp"].append([safe_float(x) if x is not None else np.nan for x in h.get("apparent_temperature", [])][:min_len])
                acc["freezing"].append([safe_float(x) if x is not None else np.nan for x in h.get("freezing_level_height", [])][:min_len])
                acc["cloud"].append([safe_float(x) for x in h.get("cloud_cover", [])][:min_len])
                acc["depth"].append([safe_float(x) for x in h.get("snow_depth", [])][:min_len])
        except: continue
        
    return data_temp, acc, times_index

# --- MOTORE 2: STORICO STAGIONALE IBRIDO (Archive + Forecast) ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_full_seasonal_history(lat, lon, elevation):
    # CALCOLO DATE
    today = datetime.now().date()
    # Inizio stagione: 1 Nov dell'anno corrente (o precedente se siamo a gen/feb/mar)
    year = today.year if today.month > 8 else today.year - 1
    start_date = f"{year}-11-01"
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 1. CHIAMATA ARCHIVIO (Dal 1 Nov a Ieri) - Questo non scade mai!
    params_archive = {
        "latitude": lat, "longitude": lon, "elevation": elevation,
        "start_date": start_date,
        "end_date": yesterday,
        "hourly": "snowfall,precipitation,snow_depth",
        "models": "best_match", # Usa ERA5 o modelli HR rianalizzati
        "timezone": "auto"
    }
    
    # 2. CHIAMATA FORECAST (Oggi + Futuro immediato per raccordo)
    params_forecast = {
        "latitude": lat, "longitude": lon, "elevation": elevation,
        "hourly": "snowfall,precipitation,snow_depth",
        "models": "best_match",
        "timezone": "auto",
        "forecast_days": 1 # Serve solo per avere il dato di "oggi" aggiornato
    }

    try:
        # Request Archivio
        r_hist = requests.get("https://archive-api.open-meteo.com/v1/archive", params=params_archive, timeout=10).json()
        
        # Request Forecast (per il dato di oggi)
        r_fore = requests.get("https://api.open-meteo.com/v1/forecast", params=params_forecast, timeout=10).json()
        
        # Creazione DataFrame Storico
        df_hist = pd.DataFrame()
        if 'hourly' in r_hist:
            df_hist = pd.DataFrame({
                "time": pd.to_datetime(r_hist["hourly"]["time"], utc=True),
                "snow": [safe_float(x) for x in r_hist["hourly"]["snowfall"]],
                "precip": [safe_float(x) for x in r_hist["hourly"]["precipitation"]],
                "depth": [safe_float(x) for x in r_hist["hourly"]["snow_depth"]]
            })

        # Creazione DataFrame Oggi/Domani
        df_fore = pd.DataFrame()
        if 'hourly' in r_fore:
             df_fore = pd.DataFrame({
                "time": pd.to_datetime(r_fore["hourly"]["time"], utc=True),
                "snow": [safe_float(x) for x in r_fore["hourly"]["snowfall"]],
                "precip": [safe_float(x) for x in r_fore["hourly"]["precipitation"]],
                "depth": [safe_float(x) for x in r_fore["hourly"]["snow_depth"]]
            })
             
        # FUSIONE DEI DUE DATI (Concat)
        if not df_hist.empty and not df_fore.empty:
            # Filtro df_fore per tenere solo da "Oggi" in poi, per non sovrapporre
            cutoff = pd.Timestamp(datetime.now().date(), tz='UTC')
            df_fore = df_fore[df_fore['time'] >= cutoff]
            
            # Unisco
            df_final = pd.concat([df_hist, df_fore]).drop_duplicates(subset='time').sort_values('time')
            return df_final.fillna(0.0)
        elif not df_hist.empty:
            return df_hist
        elif not df_fore.empty:
            return df_fore
        else:
            return None

    except Exception as e:
        # st.error(f"Debug: {e}") # Scommentare per debug
        return None

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
            st.sidebar.warning("Località non trovata.")
            return False
    except: return False

# --- SIDEBAR ---
with st.sidebar:
    st.header("Controlli")
    with st.form("analysis_form"):
        city_input = st.text_input("Cerca Località:", value=st.session_state.box_text)
        giorni = st.selectbox("Durata Previsione:", [3, 7, 10, 14], index=1)
        st.markdown("---")
        submitted = st.form_submit_button("Lancia Analisi", type="primary", use_container_width=True)
    
    st.info(f"Quota Forzata: **{st.session_state.elevation:.0f}m**")

if submitted and city_input:
    if city_input != st.session_state.location_name:
        if cerca_citta(city_input): st.rerun()

# --- LAYOUT PRINCIPALE ---
st.markdown(f"### Target: **{st.session_state.location_name}**")

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
    
    data_temp = None
    times_index = None
    avg = {}
    season_stats = {}
    df_season = None
    
    with st.spinner(f'📡 Analisi Storica Profonda (Archive API) + Forecast...'):
        # CHIAMATA AL NUOVO MOTORE IBRIDO
        data_temp, acc, times_index = get_forecast_safe(st.session_state.lat, st.session_state.lon, st.session_state.elevation, giorni)
        df_season = get_full_seasonal_history(st.session_state.lat, st.session_state.lon, st.session_state.elevation)

    if not data_temp or times_index is None:
        st.error("Errore connessione dati. Riprova.")
    else:
        try:
            min_len = len(times_index)
            # Taglio gli array
            for k in acc: acc[k] = [x[:min_len] for x in acc[k]]
            
            # Calcolo le medie Forecast
            for k, v_list in acc.items():
                if v_list: avg[k] = np.nanmean(v_list, axis=0)
                else: avg[k] = np.zeros(min_len)

            snow_mask = avg["snow"] > 0.1
            now = pd.Timestamp.now(tz='UTC')
            
            # Statistiche Future
            is_future = times_index >= now
            tot_swe_forecast = np.sum(avg["precip"][is_future]) 
            tot_snow_forecast = np.sum(avg["snow"][is_future])
            max_gust = np.max(avg["gust"])
            
            # Statistiche Stagionali (DAL DATAFRAME IBRIDO)
            season_snow_total = 0
            current_depth_season = 0.0
            
            if df_season is not None and not df_season.empty:
                # Sommo tutto quello che è successo prima di "adesso"
                past_mask = df_season["time"] < now
                season_snow_total = df_season.loc[past_mask, "snow"].sum()
                
                # Per la neve al suolo, prendo l'ultimo dato disponibile prima del futuro
                if len(df_season) > 0:
                     # Cerchiamo il dato più vicino a "adesso"
                    current_idx = df_season["time"].searchsorted(now)
                    if current_idx < len(df_season):
                         current_depth_season = df_season["depth"].iloc[current_idx] * 100
                    else:
                         current_depth_season = df_season["depth"].iloc[-1] * 100
            
            season_stats = {
                "total": season_snow_total,
                "depth": current_depth_season,
                "forecast": tot_snow_forecast,
                "swe": tot_swe_forecast,
                "wind": max_gust
            }
            
        except Exception as e:
            st.error(f"Errore di calcolo: {e}")
            st.stop()

        # --- VISUALIZZAZIONE ---
        
        # CRUSCOTTO
        st.subheader("Cruscotto Unificato (Full Season)")
        c1, c2, c3, c4, c5 = st.columns(5)
        
        c1.metric("Neve Stagione", f"{season_stats['total']:.0f} cm", help="Totale reale dal 1° Novembre (Archive + Forecast)")
        c2.metric("Neve al Suolo (Oggi)", f"{season_stats['depth']:.0f} cm", help="Stima attuale")
        c3.metric("Neve in Arrivo", f"{season_stats['forecast']:.0f} cm", delta="Forecast")
        c4.metric("SWE Previsto", f"{season_stats['swe']:.1f} kg/m²")
        c5.metric("Raffica Max", f"{season_stats['wind']:.0f} km/h", delta="Danger" if season_stats['wind']>60 else None)
        
        st.markdown("---")

        # TABS
        tabs = st.tabs(["Analisi Dettagliata", "Grafico Stagionale", "Cielo & Vento", "Pressione"])
        date_fmt = mdates.DateFormatter('%d/%m %Hh', tz=times_index.tzinfo)
        season_fmt = mdates.DateFormatter('%d %b', tz=times_index.tzinfo)
        
        def format_ax(ax):
            ax.xaxis.set_major_formatter(date_fmt)
            ax.tick_params(labelbottom=True)
            ax.grid(True, alpha=0.3)

        # TAB 1: TEMP + PRECIP
        with tabs[0]:
            fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12), gridspec_kw={'height_ratios': [1.5, 1], 'hspace': 0.3})
            df_temp = pd.DataFrame({k: v[:min_len] for k,v in data_temp.items()}, index=times_index)
            for col in df_temp.columns: ax1.plot(df_temp.index, df_temp[col], label=col, lw=2, alpha=0.8)
            ax1.plot(times_index, avg["app_temp"], color="gray", ls=":", label="Percepita")
            ax1.axhline(0, c="black", lw=1); ax1.legend(loc="upper left"); ax1.set_ylabel("°C"); ax1.set_title("Temperatura")
            format_ax(ax1)
            
            rain_plot = avg["precip"].copy(); rain_plot[snow_mask] = 0
            ax2.bar(times_index, rain_plot, width=0.04, color="dodgerblue", alpha=0.6, label="Pioggia")
            ax2b = ax2.twinx()
            if any(snow_mask):
                bars = ax2b.bar(times_index[snow_mask], avg["snow"][snow_mask], width=0.04, color="cyan", hatch="///", edgecolor="blue")
            ax2.set_ylabel("mm"); ax2b.set_ylabel("cm"); ax2.set_title("Precipitazioni")
            format_ax(ax2)
            st.pyplot(fig1)

        # TAB 2: STAGIONALE IBRIDO
        with tabs[1]:
            if df_season is not None and not df_season.empty:
                fig_s, ax_s = plt.subplots(figsize=(14, 6))
                
                # Disegno lo storico COMPLETO (Archive + Forecast uniti)
                ax_s.fill_between(df_season["time"], df_season["depth"]*100, color="cyan", alpha=0.4, label="Neve al Suolo (Storico Completo)")
                ax_s.plot(df_season["time"], df_season["depth"]*100, color="blue", lw=1)
                
                # Aggiungo la linea rossa tratteggiata per la previsione futura (dati Forecast puri)
                ax_s.plot(times_index, avg["depth"]*100, color="red", ls="--", label="Forecast (Confronto)")
                
                ax_s.axvline(now, color="black", ls=":", label="Oggi")
                ax_s.set_ylabel("cm Neve"); ax_s.set_title(f"Stagione Invernale: {season_snow_total:.0f} cm totali caduti")
                ax_s.legend(); ax_s.grid(True, alpha=0.3)
                ax_s.xaxis.set_major_formatter(season_fmt)
                st.pyplot(fig_s)
            else:
                st.warning("Dati stagionali non disponibili.")

        # TAB 3: CIELO, VENTO
        with tabs[2]:
            fig_w, (ax_c, ax_w, ax_z) = plt.subplots(3, 1, figsize=(14, 15), gridspec_kw={'hspace': 0.3})
            ax_c.fill_between(times_index, avg["cloud"], 0, color="gray", alpha=0.4); ax_c.set_ylim(0, 100); ax_c.set_title("Nubi"); format_ax(ax_c)
            ax_w.plot(times_index, avg["wind"], color="blue"); ax_w.fill_between(times_index, avg["wind"], avg["gust"], color="red", alpha=0.2); ax_w.set_title("Vento"); format_ax(ax_w)
            ax_z.plot(times_index, avg["freezing"], color="green"); ax_z.set_title("Zero Termico"); format_ax(ax_z)
            st.pyplot(fig_w)

        # TAB 4: PRESSIONE
        with tabs[3]:
            fig_p, ax_p = plt.subplots(figsize=(14, 6))
            ax_p.plot(times_index, avg["press"], color="black"); ax_p.set_title("Pressione"); format_ax(ax_p)
            st.pyplot(fig_p)

        # CSV
        st.divider()
        df_export = pd.DataFrame({"Data": times_index, "Neve_Prevista": avg["snow"]})
        csv = df_export.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", data=csv, file_name="meteo.csv", mime="text/csv")
