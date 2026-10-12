# ============================================================================
# indicators.py — Indicadores tecnicos
# Todas las funciones reciben Series/DataFrames de pandas y devuelven Series
# ============================================================================
import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    """EMA clasica."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI estilo Wilder."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range estilo Wilder."""
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index."""
    high, low, close = df["high"], df["low"], df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm), 0.0)
    minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm), 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr_s = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_s.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0)


def bollinger(series: pd.Series, period: int, std_mult: float):
    """Bandas de Bollinger. Devuelve (middle, upper, lower)."""
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return mid, upper, lower


def donchian(df: pd.DataFrame, period: int):
    """Canal de Donchian. Devuelve (highest, lowest) desplazados 1 vela."""
    highest = df["high"].rolling(period).max().shift(1)
    lowest = df["low"].rolling(period).min().shift(1)
    return highest, lowest


def volume_zscore(volume: pd.Series, lookback: int) -> pd.Series:
    """Z-Score del volumen respecto a su media movil."""
    mean = volume.rolling(lookback).mean()
    std = volume.rolling(lookback).std()
    return ((volume - mean) / std.replace(0, np.nan)).fillna(0)


def atr_percentil(atr_series: pd.Series, lookback: int) -> pd.Series:
    """Rank percentil del ATR dentro de su propia historia reciente."""
    return atr_series.rolling(lookback).rank(pct=True)