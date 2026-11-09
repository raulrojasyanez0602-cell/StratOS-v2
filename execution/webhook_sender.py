import json
import os
import datetime

JSON_FILE = "trades.json"
CAPITAL_INICIAL = 650.0
COMISION_PCT = 0.0018

def _leer_json():
    if not os.path.exists(JSON_FILE):
        return []
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def _guardar_json(trades):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=4, ensure_ascii=False)

def enviar_entrada(bot_id, symbol, timeframe, action, precio, tp_price, sl_price, bar_close_time):
    trades = _leer_json()
    
    # 1. Calculamos el PnL acumulado y el balance actual
    pnl_acum = sum(t.get("pnl_neto", 0.0) for t in trades if t.get("estado") == "CERRADO")
    balance_actual = CAPITAL_INICIAL + pnl_acum
    
    # 2. Calculamos el nocional dinámico (30% del balance actual)
    nocional = round(balance_actual * 0.30, 2)
    
    trade_id = f"{bot_id}-{int(datetime.datetime.now().timestamp())}"
    
    # 3. Guardamos TODOS los datos necesarios para calcular el PnL al cerrar
    nuevo_trade = {
        "id": trade_id,
        "bot_id": bot_id,
        "simbolo": symbol,
        "accion": action,          # LONG o SHORT
        "precio_entrada": precio,  # Vital para calcular la ganancia
        "nocional": nocional,      # Tamaño de la posición
        "pnl_neto": 0.0,
        "estado": "ABIERTO",
        "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    trades.append(nuevo_trade)
    _guardar_json(trades)
    print(f"  [ENTRADA] Guardada en JSON: {trade_id} (Nocional: ${nocional})")
    return nuevo_trade

def enviar_cierre(trade_id, exit_price, exec_type):
    trades = _leer_json()
    
    for t in trades:
        if t["id"] == trade_id:
            t["estado"] = "CERRADO"
            
            # 4. Extraemos los datos que guardamos en la entrada
            precio_entrada = t.get("precio_entrada", exit_price)
            nocional = t.get("nocional", 195.0) # 195.0 es un fallback por si acaso
            accion = t.get("accion", "LONG")
            
            # 5. Matemática real del PnL
            if precio_entrada > 0:
                if accion == "LONG":
                    pnl_bruto = nocional * (exit_price - precio_entrada) / precio_entrada
                else: # SHORT
                    pnl_bruto = nocional * (precio_entrada - exit_price) / precio_entrada
                
                comision = nocional * COMISION_PCT
                t["pnl_neto"] = round(pnl_bruto - comision, 2)
            else:
                t["pnl_neto"] = 0.0
                
            print(f"  [CIERRE] Trade {trade_id} cerrado con PnL real: {t['pnl_neto']}")
            break
            
    _guardar_json(trades)