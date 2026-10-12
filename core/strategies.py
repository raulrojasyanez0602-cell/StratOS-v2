# ============================================================================
# strategies.py — Logica de senales por bot
# Cada funcion recibe el df con indicadores ya calculados y devuelve:
#   "LONG"  -> abrir posicion long
#   "HOLD"  -> no hacer nada
# ============================================================================
import pandas as pd

from core.indicators import (
    bollinger, rsi, adx, atr,
    donchian, volume_zscore, atr_percentil,
)


# ============================================================================
# BOT 1: Bollinger Reversion SOL 1H
# Entra LONG cuando:
#   - close < banda inferior BB(20, 2.5)
#   - RSI < 30
#   - ADX < 20
#   - ATR% rank > 0.70 (top 30% de volatilidad historica)
# TP: banda media | SL: entry - ATR * 1.5
# ============================================================================
def preparar_bb(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Calcula los indicadores necesarios para el Bot BB."""
    df = df.copy()

    mid, up, lo = bollinger(df["close"], params["bb_length"], params["bb_std"])
    df["bb_mid"] = mid
    df["bb_up"] = up
    df["bb_lo"] = lo

    df["rsi"] = rsi(df["close"], params["rsi_length"])
    df["atr"] = atr(df, params["atr_length"])
    df["adx"] = adx(df, params["adx_length"])

    # Filtro de volatilidad: rank percentil del ATR dentro de su historia
    df["atr_pct"] = df["atr"] / df["close"] * 100
    df["atr_rank"] = atr_percentil(df["atr_pct"], params["atr_pct_lookback"])

    return df


def senal_bollinger(df: pd.DataFrame, params: dict) -> str:
    """
    Evalua la ultima vela cerrada y devuelve la senal.
    Asume que df ya paso por preparar_bb().
    """
    if len(df) < 2:
        return "HOLD"

    row = df.iloc[-1]

    # Chequeos de NaN (ventana insuficiente)
    if pd.isna(row["bb_lo"]) or pd.isna(row["rsi"]) or pd.isna(row["adx"]) or pd.isna(row["atr_rank"]):
        return "HOLD"

    # Condiciones de entrada
    en_banda_inferior = row["close"] < row["bb_lo"]
    rsi_extremo = row["rsi"] < params["rsi_max"]
    adx_bajo = row["adx"] < params["adx_max"]
    volatilidad_alta = row["atr_rank"] > params["atr_pct_min_rank"]

    if en_banda_inferior and rsi_extremo and adx_bajo and volatilidad_alta:
        return "LONG"

    return "HOLD"


# ============================================================================
# BOT 2: Donchian Breakout ETH 4H
# Entra LONG cuando:
#   - close > canal Donchian(20) superior
#   - Volumen Z-Score >= 1.5
#   - ADX >= 25
# SL: entry - ATR * 1.5 | TP: trailing Chandelier (ATR * 3)
# ============================================================================
def preparar_donchian(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Calcula los indicadores necesarios para el Bot Donchian."""
    df = df.copy()

    highest, lowest = donchian(df, params["donchian_length"])
    df["dc_high"] = highest
    df["dc_low"] = lowest

    df["vol_z"] = volume_zscore(df["volume"], params["volume_lookback"])
    df["adx"] = adx(df, params["adx_length"])
    df["atr"] = atr(df, params["atr_length"])

    return df


def senal_donchian(df: pd.DataFrame, params: dict) -> str:
    """
    Evalua la ultima vela cerrada y devuelve la senal.
    Asume que df ya paso por preparar_donchian().
    """
    if len(df) < 2:
        return "HOLD"

    row = df.iloc[-1]

    if pd.isna(row["dc_high"]) or pd.isna(row["adx"]):
        return "HOLD"

    # Condiciones de entrada
    rompe_canal = row["close"] > row["dc_high"]
    volumen_fuerte = row["vol_z"] >= params["volume_zscore_min"]
    tendencia_fuerte = row["adx"] >= params["adx_min"]

    if rompe_canal and volumen_fuerte and tendencia_fuerte:
        return "LONG"

    return "HOLD"


# ============================================================================
# ROUTER: despacha a la estrategia correcta segun bot["strategy"]
# ============================================================================
def preparar_df(bot: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Prepara el df segun la estrategia del bot."""
    estrategia = bot["strategy"]

    if estrategia == "BOLLINGER_REVERSION":
        return preparar_bb(df, bot)
    elif estrategia == "DONCHIAN_BREAKOUT":
        return preparar_donchian(df, bot)
    else:
        raise ValueError(f"Estrategia no soportada: {estrategia}")


def detectar_senal(bot: dict, df: pd.DataFrame) -> str:
    """Devuelve 'LONG' o 'HOLD' segun la estrategia del bot."""
    estrategia = bot["strategy"]

    if estrategia == "BOLLINGER_REVERSION":
        return senal_bollinger(df, bot)
    elif estrategia == "DONCHIAN_BREAKOUT":
        return senal_donchian(df, bot)
    else:
        raise ValueError(f"Estrategia no soportada: {estrategia}")


# ============================================================================
# CALCULO DE TP/SL POR BOT (helper para el motor)
# ============================================================================
def calcular_tp_sl(bot: dict, df: pd.DataFrame, precio_entrada: float):
    """
    Calcula TP y SL para una entrada LONG.
    Devuelve (tp_price, sl_price) o (None, None) si faltan datos.
    """
    row = df.iloc[-1]
    atr_val = row.get("atr")

    if pd.isna(atr_val) or atr_val <= 0:
        return None, None

    estrategia = bot["strategy"]

    if estrategia == "BOLLINGER_REVERSION":
        # SL: entry - ATR * mult | TP: banda media
        sl = precio_entrada - atr_val * bot["sl_atr_mult"]
        tp = row.get("bb_mid")
        if pd.isna(tp) or tp <= precio_entrada:
            return None, None
        return tp, sl

    elif estrategia == "DONCHIAN_BREAKOUT":
        # SL: entry - ATR * mult | TP: trailing (se maneja por separado)
        # Devolvemos None en TP porque el Donchian usa trailing stop
        sl = precio_entrada - atr_val * bot["sl_atr_mult"]
        return None, sl

    else:
        raise ValueError(f"Estrategia no soportada: {estrategia}")