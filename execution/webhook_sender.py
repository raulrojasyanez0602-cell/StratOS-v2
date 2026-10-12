# ============================================================================
# webhook_sender.py — Envio de senales al Apps Script
# Maneja 2 tipos de payload:
#   - type: "entrada" (nueva posicion)
#   - type: "cierre"  (cerrar posicion existente)
# Auth por token en el body. Retry con backoff exponencial.
# ============================================================================
import os
import time
import requests
from typing import Optional

WEBHOOK_URL = os.getenv("APPS_SCRIPT_WEBHOOK_URL")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN")

# Comision roundtrip (0.18%) que Apps Script usara para el calculo de PnL
COMISION_ROUNDTRIP = 0.0018


def _post(payload: dict, descripcion: str, max_retries: int = 3) -> Optional[dict]:
    """
    POST con retry exponencial. Devuelve dict con respuesta o None si falla.
    """
    if not WEBHOOK_URL:
        print(f"  [{descripcion}] ERROR: APPS_SCRIPT_WEBHOOK_URL no configurado")
        return None

    for intento in range(max_retries):
        try:
            r = requests.post(
                WEBHOOK_URL,
                json=payload,
                timeout=20,
                allow_redirects=True,
            )

            if r.status_code == 200:
                try:
                    data = r.json()
                    print(f"  [{descripcion}] OK -> {data.get('data', data)}")
                    return data
                except ValueError:
                    print(f"  [{descripcion}] Respuesta no-JSON: {r.text[:200]}")
                    return None

            print(f"  [{descripcion}] HTTP {r.status_code} (intento {intento+1}): {r.text[:200]}")

        except requests.exceptions.RequestException as e:
            print(f"  [{descripcion}] Error de red (intento {intento+1}): {e}")

        if intento < max_retries - 1:
            time.sleep(2 ** intento)  # 1s, 2s, 4s

    return None


def enviar_entrada(
    bot_id: str,
    symbol: str,
    timeframe: str,
    action: str,
    precio: float,
    tp_price: Optional[float],
    sl_price: float,
    bar_close_time: str,
) -> Optional[dict]:
    """
    Envia una senal de ENTRADA al Sheet.

    Args:
        bot_id:        ej: "Bot_BB_SOL_1H"
        symbol:        ej: "SOLUSDT"
        timeframe:     ej: "1h"
        action:        "LONG" (siempre en nuestros bots long-only)
        precio:        precio de entrada
        tp_price:      take profit en precio (o None si es trailing)
        sl_price:      stop loss en precio
        bar_close_time: ISO UTC de la vela que genero la senal
    """
    payload = {
        "type": "entrada",
        "token": WEBHOOK_TOKEN,
        "bot_id": bot_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "action": action,
        "price": precio,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "bar_close_time": bar_close_time,
        "comision": COMISION_ROUNDTRIP,
    }
    return _post(payload, f"ENTRADA {bot_id}")


def enviar_cierre(
    trade_id: str,
    exit_price: float,
    exec_type: str,
) -> Optional[dict]:
    """
    Envia un CIERRE de posicion al Sheet.

    Args:
        trade_id:    ID unico del trade (viene del Sheet)
        exit_price:  precio al que se cierra
        exec_type:   "INTRA_CANDLE_TP" / "INTRA_CANDLE_SL" / "TIME_STOP" / "TRAIL_STOP"
    """
    payload = {
        "type": "cierre",
        "token": WEBHOOK_TOKEN,
        "trade_id": trade_id,
        "exit_price": exit_price,
        "exec_type": exec_type,
    }
    return _post(payload, f"CIERRE {trade_id}")