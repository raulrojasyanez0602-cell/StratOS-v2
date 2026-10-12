# ============================================================================
# main.py — Orquestador del motor stratOS
# Ciclo completo:
#   1. Cargar configuracion (bots.yaml + .env)
#   2. Leer posiciones abiertas del Sheet
#   3. Cerrar posiciones que tocaron TP/SL
#   4. Evaluar nuevas senales por bot
#   5. Aplicar caps (global + por simbolo)
#   6. Enviar entradas al Sheet
# ============================================================================
import os
import sys
import yaml
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

from core.data_loader import descargar_klines
from core.strategies import preparar_df, detectar_senal, calcular_tp_sl
from execution.webhook_sender import enviar_entrada, enviar_cierre


# Cargar variables de entorno
load_dotenv()

APPS_URL = os.getenv("APPS_SCRIPT_WEBHOOK_URL")
TOKEN = os.getenv("WEBHOOK_TOKEN")
CAPITAL_INICIAL = float(os.getenv("CAPITAL_INICIAL", "650.0"))


# ============================================================================
# UTILIDADES
# ============================================================================
def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}")


def cargar_config(path: str = "config/bots.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def api_get(action: str, extra: str = "") -> dict:
    """GET al endpoint doGet de Apps Script."""
    if not APPS_URL:
        return {"success": False, "error": "APPS_URL no configurada"}
    url = f"{APPS_URL}?action={action}&token={TOKEN}{extra}"
    try:
        r = requests.get(url, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log(f"  [api_get {action}] error: {e}")
    return {"success": False, "data": []}


def to_iso(ts) -> str:
    """Convierte un timestamp a ISO UTC."""
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


# ============================================================================
# FASE 1: CERRAR POSICIONES QUE TOCARON TP/SL
# ============================================================================
def evaluar_salida(pos: dict) -> dict:
    """
    Descarga la ultima vela cerrada del timeframe de la posicion y evalua
    si toco TP o SL.
    """
    df = descargar_klines(pos["simbolo"], pos["timeframe"], limit=5)
    if df is None or len(df) < 1:
        return None

    k = df.iloc[-1]
    high, low = float(k["high"]), float(k["low"])

    tp = float(pos["tp"]) if pos.get("tp") else None
    sl = float(pos["sl"])
    tipo = pos["tipo"]

    if tipo != "LONG":
        # Solo operamos LONG por ahora
        return None

    # Detectar si tocaron ambos en la misma vela
    toco_tp = tp is not None and high >= tp
    toco_sl = low <= sl

    if toco_tp and toco_sl:
        # Vela alcista -> low vino primero (SL primero, proxy conservador)
        vela_alcista = float(k["close"]) > float(k["open"])
        if vela_alcista:
            return {"precio": sl, "exec_type": "AMBIGUOUS_SL"}
        else:
            return {"precio": tp, "exec_type": "AMBIGUOUS_TP"}

    if toco_tp:
        return {"precio": tp, "exec_type": "INTRA_CANDLE_TP"}
    if toco_sl:
        return {"precio": sl, "exec_type": "INTRA_CANDLE_SL"}

    return None


def cerrar_posiciones_abiertas(posiciones: list) -> int:
    """Cierra las posiciones que tocaron TP/SL. Devuelve cuantas cerro."""
    cerradas = 0
    for pos in posiciones:
        salida = evaluar_salida(pos)
        if salida:
            log(f"  -> {pos['trade_id']} ({pos['simbolo']}) toco "
                f"{salida['exec_type']} @ {salida['precio']}")
            enviar_cierre(pos["trade_id"], salida["precio"], salida["exec_type"])
            cerradas += 1
        else:
            log(f"  -> {pos['trade_id']} ({pos['simbolo']}) sigue abierta")
    return cerradas


# ============================================================================
# FASE 2: EVALUAR NUEVAS ENTRADAS
# ============================================================================
def pasa_caps(posiciones_abiertas: list, symbol: str, cfg: dict) -> tuple[bool, str]:
    """Verifica cap global y cap por simbolo. Devuelve (ok, razon)."""
    cap_global = cfg.get("cap_global", 3)
    cap_simbolo = cfg.get("cap_por_simbolo", 1)

    if len(posiciones_abiertas) >= cap_global:
        return False, "cap_global"

    mismo_simbolo = sum(1 for p in posiciones_abiertas if p["simbolo"] == symbol)
    if mismo_simbolo >= cap_simbolo:
        return False, "cap_simbolo"

    return True, ""


def evaluar_bot(bot: dict) -> dict:
    """Descarga klines, prepara indicadores y detecta senal."""
    df = descargar_klines(bot["symbol"], bot["timeframe"], limit=800)
    if df is None or len(df) < 100:
        log(f"  {bot['id']}: datos insuficientes ({len(df) if df is not None else 0} velas)")
        return None

    df = preparar_df(bot, df)
    signal = detectar_senal(bot, df)

    precio = float(df["close"].iloc[-1])
    bar_close = to_iso(df["timestamp"].iloc[-1])

    return {
        "signal": signal,
        "df": df,
        "precio": precio,
        "bar_close": bar_close,
    }


def procesar_entrada(bot: dict, evaluacion: dict, posiciones: list, cfg: dict):
    """Intenta abrir una nueva posicion segun el resultado de la evaluacion."""
    signal = evaluacion["signal"]
    precio = evaluacion["precio"]

    if signal == "HOLD":
        return False

    # Verificar caps
    ok, razon = pasa_caps(posiciones, bot["symbol"], cfg)
    if not ok:
        log(f"    bloqueado por {razon}")
        return False

    # Calcular TP/SL
    tp, sl = calcular_tp_sl(bot, evaluacion["df"], precio)
    if sl is None:
        log(f"    no se pudo calcular SL (falta ATR)")
        return False

    # Enviar al Sheet
    log(f"    ENTRANDO LONG @ {precio:.4f} | TP {tp} | SL {sl:.4f}")
    enviar_entrada(
        bot_id=bot["id"],
        symbol=bot["symbol"],
        timeframe=bot["timeframe"],
        action="LONG",
        precio=precio,
        tp_price=tp,
        sl_price=sl,
        bar_close_time=evaluacion["bar_close"],
    )
    return True


# ============================================================================
# CICLO PRINCIPAL
# ============================================================================
def run_stratOS():
    log("=" * 70)
    log("  stratOS engine — ciclo iniciado")
    log("=" * 70)

    # Cargar config
    try:
        config = cargar_config()
    except Exception as e:
        log(f"ERROR cargando config: {e}")
        return 1

    bots = config.get("bots", [])
    cfg_webhook = config.get("webhook", {})
    log(f"  Config cargada: {len(bots)} bots")

    # ========================================================================
    # FASE 1: Cerrar posiciones que tocaron TP/SL
    # ========================================================================
    log("")
    log("[FASE 1] Revisando salidas...")
    r = api_get("open")
    posiciones = r.get("data", [])
    log(f"  Posiciones abiertas: {len(posiciones)}")

    if posiciones:
        cerradas = cerrar_posiciones_abiertas(posiciones)
        log(f"  Cerradas: {cerradas}")

        # Releer posiciones (por si algunas se cerraron)
        r = api_get("open")
        posiciones = r.get("data", [])

    # ========================================================================
    # FASE 2: Evaluar nuevas entradas
    # ========================================================================
    log("")
    log("[FASE 2] Evaluando entradas...")

    entradas_nuevas = 0
    for bot in bots:
        if not bot.get("enabled", True):
            log(f"  {bot['id']}: disabled")
            continue

        log(f"  {bot['id']} ({bot['symbol']} {bot['timeframe']}):")

        evaluacion = evaluar_bot(bot)
        if evaluacion is None:
            continue

        signal = evaluacion["signal"]
        precio = evaluacion["precio"]
        log(f"    {signal} @ {precio:.4f}")

        if signal == "LONG":
            if procesar_entrada(bot, evaluacion, posiciones, cfg_webhook):
                entradas_nuevas += 1
                # Agregar a lista local para que el siguiente bot respete el cap
                posiciones.append({
                    "trade_id": f"{bot['id']}-pending",
                    "simbolo": bot["symbol"],
                    "tipo": "LONG",
                    "timeframe": bot["timeframe"],
                })

    # ========================================================================
    # RESUMEN
    # ========================================================================
    log("")
    log("=" * 70)
    log(f"  Ciclo finalizado | Nuevas entradas: {entradas_nuevas}")
    log("=" * 70)
    return 0


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    sys.exit(run_stratOS())