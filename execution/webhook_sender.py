# ============================================================================
# webhook_sender.py — Envío de señales a la API de Render (stratOS-Web)
# ============================================================================
import os
import time
import requests
from typing import Optional

# 1. Traemos la URL de Render (por defecto la de producción si no hay variable)
# Asegúrate de no poner la barra '/' al final de la URL
RENDER_API_URL = os.getenv("RENDER_API_URL", "https://stratos-web.onrender.com")

# Mantenemos la comisión por si el backend la necesita (aunque Python la calcula)
COMISION_ROUNDTRIP = 0.0018

def _post(url: str, payload: dict, descripcion: str, max_retries: int = 3) -> Optional[dict]:
    """POST con retry exponencial a Render."""
    if not RENDER_API_URL:
        print(f"  [{descripcion}] ERROR: RENDER_API_URL no configurado en los Secrets")
        return None

    for intento in range(max_retries):
        try:
            r = requests.post(
                url,
                json=payload,
                timeout=20,
                # allow_redirects=True (Render no lo necesita, lo quitamos)
            )

            if r.status_code == 200:
                try:
                    data = r.json()
                    print(f"  [{descripcion}] OK -> {data}")
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
    Envia una senal de ENTRADA al endpoint /api/entrada de Render.
    """
    # Apuntamos a la ruta exacta de entrada en FastAPI
    url = f"{RENDER_API_URL}/api/entrada"
    
    # Mapeamos los datos exactamente como los espera EntradaPayload en main.py
    payload = {
        "bot_id": bot_id,
        "action": action,
        "symbol": symbol,
        "price": precio,       # OJO: FastAPI espera 'price', no 'precio'
        "tp_price": tp_price,
        "sl_price": sl_price,
        "timeframe": timeframe,
        "bar_close_time": bar_close_time
    }
    
    return _post(url, payload, f"ENTRADA {bot_id}")


def enviar_cierre(
    trade_id: str,
    exit_price: float,
    exec_type: str,
) -> Optional[dict]:
    """
    Envia un CIERRE de posicion al endpoint /api/cierre de Render.
    """
    # Apuntamos a la ruta exacta de cierre en FastAPI
    url = f"{RENDER_API_URL}/api/cierre"
    
    # Mapeamos los datos exactamente como los espera CierrePayload en main.py
    payload = {
        "trade_id": trade_id,
        "exit_price": exit_price,
        "exec_type": exec_type,
    }
    
    return _post(url, payload, f"CIERRE {trade_id}")