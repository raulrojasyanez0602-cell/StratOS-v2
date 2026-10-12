# ============================================================================
# data_loader.py — Descarga de klines desde Binance (API publica)
# Solo endpoints publicos. No requiere API keys.
# Devuelve siempre VELAS CERRADAS (descarta la ultima en formacion).
# ============================================================================
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from typing import Optional


API_BASE = "https://api.binance.com/api/v3/klines"

# Mapeo de timeframe -> milisegundos por vela
TF_MS = {
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def descargar_klines(
    symbol: str,
    interval: str,
    limit: int = 100,
    timeout: int = 20,
) -> Optional[pd.DataFrame]:
    """
    Descarga las ultimas `limit` velas cerradas de Binance.

    Args:
        symbol:   'BTCUSDT', 'ETHUSDT', 'SOLUSDT'
        interval: '15m', '1h', '4h', '1d'
        limit:    numero de velas cerradas a devolver
        timeout:  segundos de timeout por request

    Returns:
        DataFrame con columnas: timestamp, open, high, low, close, volume
        o None si hay error.
    """
    if interval not in TF_MS:
        raise ValueError(f"Timeframe no soportado: {interval}. Usar: {list(TF_MS.keys())}")

    try:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit + 1,  # +1 para descartar la vela en formacion
        }
        r = requests.get(API_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()

        if not data or len(data) < 2:
            return None

        # Binance devuelve 12 columnas. Nos quedamos con las 6 importantes.
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tbb", "tbq", "ignore"
        ])
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()

        # Convertir tipos
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Descartar la ultima vela (aun en formacion)
        df = df.iloc[:-1].reset_index(drop=True)

        return df

    except Exception as e:
        print(f"[data_loader] Error {symbol} {interval}: {e}")
        return None


def descargar_historico(
    symbol: str,
    interval: str,
    anos: float = 1.0,
    timeout: int = 20,
) -> Optional[pd.DataFrame]:
    """
    Descarga años de historia usando paginacion (limite 1000 velas por request).
    Util para backtests.

    Args:
        anos: años de historia a descargar

    Returns:
        DataFrame completo o None si falla.
    """
    if interval not in TF_MS:
        raise ValueError(f"Timeframe no soportado: {interval}")

    tf_ms = TF_MS[interval]
    fin = int(datetime.now(timezone.utc).timestamp() * 1000)
    inicio = fin - int(anos * 365 * 24 * 3600 * 1000)

    todas = []
    cursor = inicio

    while cursor < fin:
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "limit": 1000,
            }
            r = requests.get(API_BASE, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()

            if not data:
                break

            todas.extend(data)
            cursor = data[-1][0] + tf_ms
            time.sleep(0.1)  # rate limit amigable

        except Exception as e:
            print(f"[data_loader] Error en pagina: {e}")
            break

    if not todas:
        return None

    df = pd.DataFrame(todas, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbb", "tbq", "ignore"
    ])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    # Deduplicar y ordenar
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)

    return df