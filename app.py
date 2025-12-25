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

st.title("🌍 VEXOR METEO SUITE v7.0 (Season Edition)")

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

# --- FUNZIONE CACHED: DATI STAGIONALI + FORECAST ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_seasonal_analysis(lat, lon, elevation, forecast_days):
    # 1. Definiamo le date: Dal 1 Novembre (Inizio Stagione) a (Oggi + Forecast)
    today = datetime.now().date()
    start_season = datetime(today.year if today.month > 8 else today.year - 1, 11, 1).date() # 1 Nov dell'inverno corrente
    end_forecast = today + timedelta(days=forecast_days)
    
    # Calcoliamo i giorni nel passato (per l'API forecast past_days arriva max a 92, usiamo archive se serve, 
    # ma per semplicità qui usiamo il forecast esteso che spesso copre 3 mesi indietro o l'endpoint archive)
    # TRUCCO PRO: Usiamo l'endpoint "forecast" che accetta past_days fino a 92. 
    # Se siamo a fine stagione servirebbe l'archive, ma per ora (Dicembre/Gennaio) past_days basta.
    days_since_nov1 = (today - start_season).days
    
    # Parametri base
    models = [{"id": "ecmwf_ifs025", "label": "ECMWF", "c": "red"}] # Usiamo ECMWF come riferimento principale per lo storico
    
    # Aggiungo &elevation=... per FORZARE la quota reale!
    params = {
        "latitude": lat, "longitude": lon, 
        "elevation": elevation, # <--- IL FIX CHE CAMBIA TUTTO
        "hourly": "temperature_2m,precipitation,snowfall,snow_depth,freezing_level_height",
        "timezone": "auto",
        "past_days": max(days_since_nov1, 3), # Scarico tutto lo storico stagionale se < 92 gg
        "forecast_days": forecast_days
    }
    
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10).json()
        
        if 'hourly' not in r: return None, None
        
        h = r["hourly"]
        df = pd.DataFrame({
            "time": pd.to_datetime(h["time"]),
            "temp": h["temperature_2m"],
            "precip": h["precipitation"],
            "snow": h["snowfall"],
            "depth": h["snow_depth"], # Questo ora dovrebbe essere corretto grazie all'elevation!
            "freezing": h["freezing_level_height"]
        })
        
        # Calcoli Stagionali
        # Filtro dati dal 1 Nov ad Oggi (Escludo il futuro per i totali storici)
        now = pd.Timestamp.now()
        df_past = df[df["time"] < now]
        df_future = df[df["time"] >= now]
        
        stats = {
            "season_snowfall": df_past["snow"].sum(), # Totale neve caduta da inizio stagione
            "season_precip": df_past["precip"].sum(),
            "current_depth": df_past["depth"].iloc[-1] if len(df_past) > 0 else 0, # Neve al suolo ORA
            "forecast_snow": df_future["snow"].sum(),
            "forecast_rain": df_future["precip"].sum(), # Semplificato (assumiamo precip futura)
            "max_depth_forecast": df_future["depth"].max() if len(df_future) > 0 else 0
        }
        
        return df, stats
        
    except Exception as e:
        return None, None

# --- FUNZIONE RICERCA (Geocoding con ELEVAZIONE) ---
def cerca_citta(nome):
    if not nome: return False
    try:
        # Cerco la città e prendo anche l'elevazione
        res = requests.get("https://geocoding-api.open-meteo.com/v1/search", 
                           params={"name": nome, "count": 1, "language": "it"}, timeout=5).json()
        if "results" in res:
            loc = res["results"][0]
            st.session_state.lat = loc["latitude"]
            st.session_state.lon = loc["longitude"]
            st.session_state.elevation = loc.get("elevation", 1000) # Prendo la quota reale!
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
    
    st.info(f"🏔️ Quota Rilevata: **{st.session_state.elevation:.0f}m**\n\nIl modello verrà forzato a usare questa quota per correggere la neve.")

if submitted and city_input:
    if city_input != st.session_state.location_name:
        if cerca_citta(city_input): st.rerun()

# --- LAYOUT PRINCIPALE ---
st.markdown(f"### 🎯 Target: **{st.session_state.location_name}** (Quota: {st.session_state.elevation:.0f}m)")

m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=10)
folium.Marker([st.session_state.lat, st.session_state.lon], 
              popup=st.session_state.location_name, icon=folium.Icon(color="red", icon="info-sign")).add_to(m)
output_mappa = st_folium(m, height=250, use_container_width=True)

if output_mappa['last_clicked']:
    clat, clon = output_mappa['last_clicked']['lat'], output_mappa['last_clicked']['lng']
    if (abs(clat - st.session_state.lat) > 0.0001) or (abs(clon - st.session_state.lon) > 0.0001):
        st.session_state.lat = clat
        st.session_state.lon = clon
        # Se clicco sulla mappa, uso un'API esterna per l'elevazione o tengo la vecchia?
        # Per semplicità qui tengo la vecchia o uso un default, Open-Meteo downscalerà.
        # (L'ideale sarebbe una chiamata API Elevation, ma rallenta. Usiamo default intelligente).
        st.session_state.location_name = f"Punto Mappa ({clat:.2f}, {clon:.2f})"
        st.session_state.box_text = st.session_state.location_name
        st.session_state.start_analysis = True
        st.rerun()

# --- MOTORE ANALISI ---
if st.session_state.start_analysis:
    st.divider()
    with st.spinner(f'📡 Analisi Stagionale (1 Nov -> Oggi) + Previsione...'):
        
        df, stats = get_seasonal_analysis(st.session_state.lat, st.session_state.lon, st.session_state.elevation, giorni)
        
        if df is None:
            st.error("Errore nel recupero dati stagionali.")
        else:
            # --- DASHBOARD STAGIONALE ---
            st.subheader("❄️ Bilancio Stagionale (dal 1° Novembre)")
            
            # Metricona Principale
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Neve Caduta Totale", f"{stats['season_snowfall']:.0f} cm", help="Somma di tutta la neve caduta da inizio stagione (Nov 1)")
            c2.metric("Neve al Suolo (Modello)", f"{stats['current_depth']*100:.0f} cm", help="Altezza manto nevoso stimata ORA (con correzione quota)")
            c3.metric("Neve in Arrivo", f"{stats['forecast_snow']:.0f} cm", delta="Previsione")
            c4.metric("Precipitazioni Totali", f"{stats['season_precip']:.0f} mm", help="Pioggia + Neve fusa stagionale")
            
            st.markdown("---")

            # --- GRAFICO STORICO + PREVISIONE ---
            t1, t2 = st.tabs(["📉 Grafico Stagionale", "🔍 Focus Previsione"])
            
            now = pd.Timestamp.now()
            
            with t1:
                st.caption("Andamento dell'accumulo nevoso da inizio stagione")
                fig, ax = plt.subplots(figsize=(14, 6))
                
                # Area Neve al Suolo
                # Moltiplico per 100 per avere cm
                ax.fill_between(df["time"], df["depth"]*100, color="cyan", alpha=0.4, label="Neve al Suolo (cm)")
                ax.plot(df["time"], df["depth"]*100, color="blue", lw=1)
                
                # Linea verticale OGGI
                ax.axvline(now, color="red", ls="--", label="Oggi")
                
                ax.set_ylabel("Centimetri")
                ax.set_title("Andamento Manto Nevoso (Stagione + Previsione)")
                ax.legend()
                ax.grid(True, alpha=0.3)
                
                # Formattazione asse X per mesi
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
                st.pyplot(fig)

            with t2:
                # Grafico dettagliato solo forecast (simile ai precedenti)
                df_focus = df[df["time"] >= (now - pd.Timedelta(days=1))] # Ieri -> Futuro
                
                fig2, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
                
                # Temp
                ax1.plot(df_focus["time"], df_focus["temp"], color="red", label="Temperatura")
                ax1.axhline(0, color="black", lw=1)
                ax1.set_ylabel("°C"); ax1.grid(True)
                
                # Neve Focus
                ax2.bar(df_focus["time"], df_focus["snow"], width=0.04, color="cyan", edgecolor="blue", label="Neve Oraria (cm)")
                ax2.set_ylabel("cm / h"); ax2.grid(True)
                
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %Hh'))
                st.pyplot(fig2)

            # CSV Download
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Scarica Dati Stagionali (CSV)", data=csv, file_name="storico_neve.csv", mime="text/csv")
