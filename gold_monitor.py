# ============================================================================
# gold_monitor.py — Radar Macro de Oro para Honorio
# Descarga datos, genera grafico tecnico y lo envia a Telegram
# ============================================================================
import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import mplfinance as mpf
from datetime import datetime, timezone
import matplotlib.pyplot as plt

# --- Configuracion ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8684016919:AAEU0X7SsPoyPlD-VsryA_d4BuvWIQnSLfQ")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1004412236518")
SYMBOL_BINANCE = "PAXGUSDT"
TIMEFRAME = "1d"  # Diario para macro tendencia

def calcular_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def descargar_datos():
    print("[gold_monitor] Descargando datos de PAXG (Binance)...")
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={SYMBOL_BINANCE}&interval={TIMEFRAME}&limit=300"
    r = requests.get(url)
    data = r.json()
    
    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbb", "tbq", "ignore"
    ])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df.set_index("timestamp", inplace=True)
    
    # Calcular indicadores
    df["EMA_200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["RSI"] = calcular_rsi(df["close"])
    
    # Descargar DXY (Dolar Index)
    print("[gold_monitor] Descargando DXY (Yahoo Finance)...")
    try:
        dxy = yf.download("DX-Y.NYB", period="1mo", interval="1d", progress=False)
        if not dxy.empty:
            dxy_close = float(dxy["Close"].iloc[-1].squeeze())
        else:
            dxy_close = 0.0
    except Exception as e:
        print(f"Aviso: No se pudo obtener DXY ({e})")
        dxy_close = 0.0
        
    return df, dxy_close

def generar_grafico(df):
    print("[gold_monitor] Generando grafico...")
    colors = mpf.make_marketcolors(up="#26a69a", down="#ef5350", edge="inherit", wick="inherit", volume="in")
    s = mpf.make_mpf_style(base_mpf_style="nightclouds", marketcolors=colors, gridcolor="#2a2e39")

    add_plots = [
        mpf.make_addplot(df["EMA_200"], color="gold", width=1.5, label="EMA 200"),
        mpf.make_addplot(df["RSI"], panel=2, color="cyan", ylabel="RSI"),
    ]

    archivo = "gold_chart.png"
    mpf.plot(
        df, type="candle", style=s, 
        title=f"\n[HONORIO] - Reserva Estrategica ({SYMBOL_BINANCE})",
        ylabel="Precio (USD)", addplot=add_plots, volume=True,
        panel_ratios=(4, 1, 1), savefig=archivo, figsize=(10, 8)
    )
    return archivo

def enviar_telegram(imagen, df, dxy_close):
    print("[gold_monitor] Enviando a Telegram...")
    precio_actual = df["close"].iloc[-1]
    rsi_actual = df["RSI"].iloc[-1]
    ema_200 = df["EMA_200"].iloc[-1]
    
    # Logica macro de decision (Texto sin simbolos matematicos para evitar error de HTML)
    if precio_actual > ema_200:
        trend = "ALCISTA (Precio sobre EMA 200)"
        accion = "MANTENER 20% EN RESERVA"
    else:
        trend = "BAJISTA (Precio bajo EMA 200)"
        accion = "MANTENER 20% (Fase de acumulacion macro)"

    if rsi_actual < 30:
        accion = "OPORTUNIDAD: Rebalancear / Comprar mas Oro (RSI menor a 30)"
    elif rsi_actual > 70:
        accion = "PRECAUCION: Oro sobrecomprado. Tomar parciales si es necesario."

    caption = (
        f"<b>🧠 HONORIO — Radar Macro de Oro</b>\n\n"
        f"🪙 <b>{SYMBOL_BINANCE} (Oro Tokenizado):</b> ${precio_actual:,.2f}\n"
        f"📉 <b>RSI (14):</b> {rsi_actual:.1f}\n"
        f"📈 <b>Tendencia:</b> {trend}\n"
        f"💵 <b>DXY (Indice Dolar):</b> {dxy_close:.2f}\n\n"
        f"🎯 <b>Accion Sugerida:</b> {accion}"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    with open(imagen, "rb") as photo:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
        files = {"photo": photo}
        r = requests.post(url, data=payload, files=files)
        if r.status_code == 200:
            print("[gold_monitor] Enviado con exito!")
        else:
            print(f"[gold_monitor] Error: {r.text}")

if __name__ == "__main__":
    try:
        df, dxy = descargar_datos()
        img = generar_grafico(df)
        enviar_telegram(img, df, dxy)
    except Exception as e:
        print(f"Error en Gold Monitor: {e}")