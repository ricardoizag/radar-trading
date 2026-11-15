import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import io
import sys
import subprocess

# Asegurar que openpyxl esté instalado para exportar a Excel
try:
    import openpyxl
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl

st.set_page_config(page_title="Radar Predictivo de Trading Pro", layout="wide")

st.title("📊 Radar Predictivo de Trading: Análisis Individual y Escáner de Cartera")
st.caption("Motor híbrido basado en Regresión Lineal, Reversión a la Media (Bollinger/RSI), Volatilidad ATR y Volumen Institucional.")

# Diccionario de enlaces comunes de Investing.com a su símbolo bursátil (Ticker)
investing_map = {
    "first-solar-inc": "FSLR",
    "apple-computer-inc": "AAPL",
    "microsoft-corp": "MSFT",
    "tesla-motors": "TSLA",
    "nvidia-corp": "NVDA",
    "amazon-com-inc": "AMZN",
    "meta-platforms-inc": "META",
    "alphabet-inc": "GOOGL",
    "uber-technologies-inc": "UBER",
    "ouster": "OUST",
    "transmedics-group": "TMDX",
    "vishay-precision-group": "VPG",
    "auna-sa": "AUNA"
}

# ==============================================================================
# FUNCIÓN CENTRAL DE ANÁLISIS (USADA POR AMBAS PESTAÑAS)
# ==============================================================================
def analizar_accion(ticker):
    accion = yf.Ticker(ticker)
    df = accion.history(period="1y")
    if df.empty or len(df) < 50:
        return None
    
    try:
        info = accion.info
    except Exception:
        info = {}

    # 1. Indicadores Técnicos
    df['EMA_9'] = ta.trend.ema_indicator(df['Close'], window=9)
    df['SMA_20'] = ta.trend.sma_indicator(df['Close'], window=20)
    df['SMA_50'] = ta.trend.sma_indicator(df['Close'], window=50)
    df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
    df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)

    bb = ta.volatility.BollingerBands(close=df['Close'], window=20, window_dev=2)
    df['BB_High'] = bb.bollinger_hband()
    df['BB_Low'] = bb.bollinger_lband()

    macd = ta.trend.MACD(df['Close'])
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()

    df['Vol_Promedio_20'] = df['Volume'].rolling(window=20).mean()
    df['RVOL'] = df['Volume'] / df['Vol_Promedio_20']

    ultimo_precio = float(df['Close'].iloc[-1])
    cambio_hoy_pct = float(((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100)
    ema9_actual = float(df['EMA_9'].iloc[-1])
    sma20_actual = float(df['SMA_20'].iloc[-1])
    sma50_actual = float(df['SMA_50'].iloc[-1])
    rsi_actual = float(df['RSI'].iloc[-1])
    atr_actual = float(df['ATR'].iloc[-1])
    macd_actual = float(df['MACD'].iloc[-1])
    macd_sig = float(df['MACD_Signal'].iloc[-1])
    rvol_actual = float(df['RVOL'].iloc[-1]) if not np.isnan(df['RVOL'].iloc[-1]) else 1.0

    soporte_min = float(df['Low'].tail(30).min())
    resistencia_max = float(df['High'].tail(30).max())

    nombre_empresa = info.get('shortName', ticker)
    pe_ratio = info.get('trailingPE', None)
    target_price = info.get('targetMeanPrice', None)

    # 2. Sistema de Puntuación (Score 0 a 100)
    score = 50
    razones_didacticas = []

    if ultimo_precio > ema9_actual and ema9_actual > sma20_actual:
        score += 12
        razones_didacticas.append("🟢 **Impulso de Corto Plazo Alcista:** El precio supera su media rápida (EMA 9) y su media de 20 días.")
    elif ultimo_precio < ema9_actual and ema9_actual < sma20_actual:
        score -= 12
        razones_didacticas.append("🔴 **Tendencia de Corto Plazo Bajista:** El precio cotiza debajo de las medias de 9 y 20 días.")
    else:
        razones_didacticas.append("🟡 **Tendencia en Transición:** El precio está cruzando sus medias móviles de corto plazo.")

    if rsi_actual < 32:
        score += 15
        razones_didacticas.append(f"🟢 **Oportunidad por Sobreventa (RSI en {rsi_actual:.1f}):** Castigo excesivo; alta probabilidad de rebote elástico.")
    elif rsi_actual > 70:
        score -= 15
        razones_didacticas.append(f"🔴 **Riesgo por Sobrecompra (RSI en {rsi_actual:.1f}):** Subida acelerada; riesgo de toma de ganancias.")
    else:
        razones_didacticas.append(f"🟡 **Fuerza Relativa Neutral (RSI en {rsi_actual:.1f}):** Sin agotamiento extremo (rango normal 32-70).")

    if macd_actual > macd_sig:
        score += 8
        razones_didacticas.append("🟢 **Cruce MACD Positivo:** Aceleración compradora activa.")
    else:
        score -= 8
        razones_didacticas.append("🔴 **MACD Negativo:** Momento dominado por presión vendedora.")

    if rvol_actual > 1.25 and cambio_hoy_pct > 0:
        score += 8
        razones_didacticas.append(f"🟢 **Fuerte Volumen Institucional (RVOL {rvol_actual:.2f}x):** Subida respaldada por compras fuertes.")
    elif rvol_actual > 1.25 and cambio_hoy_pct < 0:
        score -= 8
        razones_didacticas.append(f"🔴 **Distribución Institucional (RVOL {rvol_actual:.2f}x):** Caída con alto volumen vendedor.")
    else:
        razones_didacticas.append(f"🟡 **Volumen Normal ({rvol_actual:.2f}x):** Participación estándar del mercado hoy.")

    if pe_ratio and pe_ratio < 16:
        score += 10
        razones_didacticas.append(f"🟢 **Fundamentalmente Barata (PER {pe_ratio:.1f}x):** Múltiplo bajo respecto a sus utilidades.")
    elif pe_ratio and pe_ratio > 35:
        score -= 5
        razones_didacticas.append(f"🟡 **Valoración Exigente (PER {pe_ratio:.1f}x):** Múltiplo alto; exige fuerte crecimiento.")

    if target_price and target_price > ultimo_precio * 1.15:
        upside = ((target_price - ultimo_precio) / ultimo_precio) * 100
        score += 10
        razones_didacticas.append(f"🟢 **Respaldo de Wall Street:** Objetivo consenso de **${target_price:.2f}** (+{upside:.1f}% potencial).")

    score = max(5, min(95, int(score)))

    # 3. Motor Predictivo Híbrido a 5 Días
    ventana = 15
    y_hist = df['Close'].tail(ventana).values
    x_hist = np.arange(ventana)
    pendiente_reg, _ = np.polyfit(x_hist, y_hist, 1)

    distancia_sma20 = sma20_actual - ultimo_precio
    peso_reversion = 0.65 if (rsi_actual < 32 or rsi_actual > 70) else 0.35
    peso_tendencia = 1.0 - peso_reversion
    volatilidad_diaria = float(df['Close'].pct_change().tail(30).std())

    ultima_fecha = df.index[-1]
    fechas_futuras = []
    fecha_cursor = ultima_fecha
    while len(fechas_futuras) < 5:
        fecha_cursor += timedelta(days=1)
        if fecha_cursor.weekday() < 5:
            fechas_futuras.append(fecha_cursor)

    proyecciones = []
    precio_reversion = ultimo_precio
    for i in range(1, 6):
        pred_tendencia = ultimo_precio + (pendiente_reg * i * 0.75)
        empuje_rsi = 0.0045 if rsi_actual < 32 else (-0.0045 if rsi_actual > 70 else 0.0)
        ajuste_hacia_media = (distancia_sma20 * 0.12)
        precio_reversion = precio_reversion + ajuste_hacia_media + (precio_reversion * empuje_rsi)

        consenso = (pred_tendencia * peso_tendencia) + (precio_reversion * peso_reversion)
        margen_volatilidad = consenso * volatilidad_diaria * np.sqrt(i)
        rango_min = consenso - margen_volatilidad
        rango_max = consenso + margen_volatilidad
        variacion_pct = ((consenso - ultimo_precio) / ultimo_precio) * 100

        proyecciones.append({
            "Día": f"Día +{i} ({fechas_futuras[i-1].strftime('%d/%m/%Y')})",
            "Piso Probable (Mín)": round(rango_min, 2),
            "Modelo Tendencia": round(pred_tendencia, 2),
            "Modelo Reversión Media": round(precio_reversion, 2),
            "Precio Estimado (Consenso)": round(consenso, 2),
            "Techo Probable (Máx)": round(rango_max, 2),
            "Variación Esperada (%)": round(variacion_pct, 2)
        })

    df_proyeccion = pd.DataFrame(proyecciones)
    precio_dia5 = proyecciones[-1]["Precio Estimado (Consenso)"]
    var_dia5_pct = proyecciones[-1]["Variación Esperada (%)"]

    # 4. Gestión de Riesgo ATR
    es_alcista = score >= 52 or (rsi_actual < 32 and score >= 42)
    if es_alcista:
        direccion_op = "COMPRA (Posición Larga)"
        stop_loss = ultimo_precio - (1.5 * atr_actual)
        take_profit = ultimo_precio + (3.0 * atr_actual)
    else:
        direccion_op = "VENTA / ESPERA (Sesgo Bajista)"
        stop_loss = ultimo_precio + (1.5 * atr_actual)
        take_profit = ultimo_precio - (3.0 * atr_actual)

    riesgo_pct = abs((stop_loss - ultimo_precio) / ultimo_precio) * 100
    beneficio_pct = abs((take_profit - ultimo_precio) / ultimo_precio) * 100

    if score >= 62:
        senal_corta = "🟢 COMPRA CONFIRMADA"
        veredicto_texto = f"COMPRA CONFIRMADA (Score {score}/100): Confluencia técnica y fundamental favorable."
        tipo_alerta = "success"
    elif rsi_actual < 32 and score >= 45:
        senal_corta = "🟡 COMPRA REBOTE (SOBREVENTA)"
        veredicto_texto = f"COMPRA DE REBOTE POR SOBREVENTA (Score {score}/100): Acción muy castigada con valor fundamental. Vigilar piso de ${soporte_min:.2f}."
        tipo_alerta = "warning"
    elif score >= 45:
        senal_corta = "🟡 NEUTRAL / ESPERAR"
        veredicto_texto = f"NEUTRAL / ESPERAR CONFIRMACIÓN (Score {score}/100): Fuerzas equilibradas; esperar ruptura de ${ema9_actual:.2f}."
        tipo_alerta = "warning"
    else:
        senal_corta = "🔴 VENTA / EVITAR"
        veredicto_texto = f"VENTA / NO COMPRAR AÚN (Score {score}/100): Presión bajista dominante. Esperar formación de piso."
        tipo_alerta = "error"

    return {
        "ticker": ticker,
        "nombre_empresa": nombre_empresa,
        "df": df,
        "ultima_fecha": ultima_fecha,
        "fechas_futuras": fechas_futuras,
        "ultimo_precio": ultimo_precio,
        "cambio_hoy_pct": cambio_hoy_pct,
        "ema9_actual": ema9_actual,
        "sma20_actual": sma20_actual,
        "sma50_actual": sma50_actual,
        "rsi_actual": rsi_actual,
        "atr_actual": atr_actual,
        "rvol_actual": rvol_actual,
        "soporte_min": soporte_min,
        "resistencia_max": resistencia_max,
        "pe_ratio": pe_ratio,
        "target_price": target_price,
        "score": score,
        "senal_corta": senal_corta,
        "veredicto_texto": veredicto_texto,
        "tipo_alerta": tipo_alerta,
        "razones_didacticas": razones_didacticas,
        "direccion_op": direccion_op,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "riesgo_pct": riesgo_pct,
        "beneficio_pct": beneficio_pct,
        "df_proyeccion": df_proyeccion,
        "precio_dia5": precio_dia5,
        "var_dia5_pct": var_dia5_pct
    }


# ==============================================================================
# CREACIÓN DE LAS 2 PESTAÑAS DEL APLICATIVO
# ==============================================================================
tab_individual, tab_escaner = st.tabs([
    "🔍 1. Análisis Individual Profundo", 
    "🚀 2. Escáner Multi-Acciones (Ranking de Favoritas)"
])


# ==============================================================================
# PESTAÑA 1: ANÁLISIS INDIVIDUAL PROFUNDO
# ==============================================================================
with tab_individual:
    col_input1, col_input2, col_btn = st.columns([2.2, 1, 1])

    with col_input1:
        entrada = st.text_input(
            "1. Pega el enlace de Investing.com o escribe el Ticker:", 
            "https://es.investing.com/equities/first-solar-inc"
        )

    ticker_detectado = entrada.strip().upper()
    if "investing.com/equities/" in entrada.lower():
        slug = entrada.lower().split("investing.com/equities/")[1].split("/")[0].split("?")[0]
        ticker_detectado = investing_map.get(slug, "FSLR")

    with col_input2:
        ticker = st.text_input(
            "2. Símbolo (Ticker) bursátil:", 
            value=ticker_detectado
        ).strip().upper()

    with col_btn:
        st.write("")
        st.write("")
        analizar_btn = st.button("🔍 Analizar Acción Ahora", use_container_width=True)

    if analizar_btn:
        with st.spinner(f"Analizando estructura institucional y calculando cono predictivo para {ticker}..."):
            res = analizar_accion(ticker)

            if res is None:
                st.error("❌ No se encontraron suficientes datos históricos. Verifica el Símbolo (Ticker), ej: FSLR, NVDA, AAPL.")
            else:
                df = res["df"]
                df_proyeccion = res["df_proyeccion"]

                st.markdown(f"### 🏢 {res['nombre_empresa']} (`{ticker}`) — Puntaje Global: **{res['score']}/100**")
                st.progress(res['score'] / 100)

                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Precio Actual", f"${res['ultimo_precio']:.2f}", f"{res['cambio_hoy_pct']:+.2f}% hoy")
                c2.metric("RSI (14 días)", f"{res['rsi_actual']:.1f}", "Sobreventa (<30)" if res['rsi_actual'] < 30 else ("Sobrecompra (>70)" if res['rsi_actual'] > 70 else "Zona Neutral"))
                c3.metric("Volumen Relativo (RVOL)", f"{res['rvol_actual']:.2f}x", "Alto interés" if res['rvol_actual'] > 1.2 else "Volumen normal")
                c4.metric("PER Fundamental", f"{res['pe_ratio']:.1f}x" if res['pe_ratio'] else "N/A", "Barata (<16x)" if (res['pe_ratio'] and res['pe_ratio'] < 16) else "Estándar")
                c5.metric("Objetivo Wall Street", f"${res['target_price']:.2f}" if res['target_price'] else "N/A", f"{((res['target_price']-res['ultimo_precio'])/res['ultimo_precio'])*100:+.1f}% potencial" if res['target_price'] else "")

                if res['tipo_alerta'] == "success":
                    st.success(f"🟢 **{res['veredicto_texto']}**")
                elif res['tipo_alerta'] == "warning":
                    st.warning(f"⚠️ **{res['veredicto_texto']}**")
                else:
                    st.error(f"🔴 **{res['veredicto_texto']}**")

                st.subheader(f"🛡️ Plan Operativo y Gestión de Riesgo ({res['direccion_op']} | Ratio 1:2)")
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Volatilidad Diaria (ATR)", f"${res['atr_actual']:.2f}", f"±{(res['atr_actual']/res['ultimo_precio'])*100:.2f}% diario", delta_color="off")
                r2.metric("🛑 Stop Loss Exacto", f"${res['stop_loss']:.2f}", f"-{res['riesgo_pct']:.2f}% riesgo máx", delta_color="inverse")
                r3.metric("🎯 Take Profit Exacto", f"${res['take_profit']:.2f}", f"+{res['beneficio_pct']:.2f}% meta ganancia", delta_color="normal")
                r4.metric("Piso / Techo (30 días)", f"${res['soporte_min']:.2f}", f"Techo: ${res['resistencia_max']:.2f}", delta_color="off")

                st.subheader("📈 Gráfico Didáctico: Velas Japonesas, Bandas de Bollinger y Cono Predictivo 5D")
                df_plot = df.tail(65)
                fechas_con_hoy = [df_plot.index[-1]] + res["fechas_futuras"]
                consenso_serie = [res["ultimo_precio"]] + df_proyeccion["Precio Estimado (Consenso)"].tolist()
                max_serie = [res["ultimo_precio"]] + df_proyeccion["Techo Probable (Máx)"].tolist()
                min_serie = [res["ultimo_precio"]] + df_proyeccion["Piso Probable (Mín)"].tolist()

                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.06,
                    row_heights=[0.72, 0.28],
                    subplot_titles=(f"Precio Histórico + Cono de Probabilidad a 5 Días ({ticker})", "Indicador RSI (14) — Debajo de 30: Sobreventa (Compra) | Arriba de 70: Sobrecompra (Venta)")
                )

                fig.add_trace(go.Candlestick(
                    x=df_plot.index, open=df_plot['Open'], high=df_plot['High'],
                    low=df_plot['Low'], close=df_plot['Close'], name="Velas Diarias"
                ), row=1, col=1)

                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA_9'], name="EMA 9 (Rápida)", line=dict(color="#2962FF", width=1.5)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['SMA_20'], name="SMA 20 (Media Bollinger)", line=dict(color="#FF6D00", width=1.5)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_High'], name="Banda Superior", line=dict(color="gray", width=1, dash="dot")), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Low'], name="Banda Inferior", line=dict(color="gray", width=1, dash="dot"), fill='tonexty', fillcolor='rgba(128,128,128,0.07)'), row=1, col=1)

                fig.add_trace(go.Scatter(x=fechas_con_hoy, y=max_serie, name="Techo Probable 5D", line=dict(width=0), showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=fechas_con_hoy, y=min_serie, name="Rango Probable 5D",
                    fill='tonexty', fillcolor='rgba(255, 165, 0, 0.25)',
                    line=dict(width=0)
                ), row=1, col=1)
                fig.add_trace(go.Scatter(
                    x=fechas_con_hoy, y=consenso_serie, name="Ruta Consenso (5 Días)",
                    line=dict(color="darkorange", width=3, dash="dash"), mode="lines+markers"
                ), row=1, col=1)

                fig.add_hline(y=res['take_profit'], line_dash="dot", line_color="green", annotation_text=f"Take Profit (${res['take_profit']:.2f})", row=1, col=1)
                fig.add_hline(y=res['stop_loss'], line_dash="dot", line_color="red", annotation_text=f"Stop Loss (${res['stop_loss']:.2f})", row=1, col=1)

                fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['RSI'], name="RSI (14)", line=dict(color="#7E57C2", width=2)), row=2, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
                fig.add_hrect(y0=0, y1=30, fillcolor="green", opacity=0.1, line_width=0, row=2, col=1)
                fig.add_hrect(y0=70, y1=100, fillcolor="red", opacity=0.1, line_width=0, row=2, col=1)

                fig.update_layout(height=680, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True)

                col_tabla, col_didactica = st.columns([1.4, 1])

                with col_tabla:
                    st.subheader("📅 Tabla Predictiva (Próximos 5 Días Hábiles)")
                    df_proyeccion_vista = pd.DataFrame({
                        "Día Hábil": df_proyeccion["Día"],
                        "Piso (Mín)": df_proyeccion["Piso Probable (Mín)"].map("${:.2f}".format),
                        "Precio Consenso": df_proyeccion["Precio Estimado (Consenso)"].map("${:.2f}".format),
                        "Techo (Máx)": df_proyeccion["Techo Probable (Máx)"].map("${:.2f}".format),
                        "Variación": df_proyeccion["Variación Esperada (%)"].map("{:+.2f}%".format)
                    })
                    st.dataframe(df_proyeccion_vista, use_container_width=True, hide_index=True)

                    df_resumen = pd.DataFrame([
                        {"Métrica / Indicador": "Empresa / Ticker", "Valor": f"{res['nombre_empresa']} ({ticker})"},
                        {"Métrica / Indicador": "Fecha de Último Cierre", "Valor": res['ultima_fecha'].strftime('%d/%m/%Y')},
                        {"Métrica / Indicador": "Puntaje Global (0-100)", "Valor": res['score']},
                        {"Métrica / Indicador": "Precio Actual (USD)", "Valor": round(res['ultimo_precio'], 2)},
                        {"Métrica / Indicador": "EMA 9 días (Corto Plazo)", "Valor": round(res['ema9_actual'], 2)},
                        {"Métrica / Indicador": "SMA 20 días (Media Bollinger)", "Valor": round(res['sma20_actual'], 2)},
                        {"Métrica / Indicador": "SMA 50 días", "Valor": round(res['sma50_actual'], 2)},
                        {"Métrica / Indicador": "RSI (14 días)", "Valor": round(res['rsi_actual'], 2)},
                        {"Métrica / Indicador": "Volumen Relativo (RVOL)", "Valor": round(res['rvol_actual'], 2)},
                        {"Métrica / Indicador": "Volatilidad Diaria ATR (14d)", "Valor": round(res['atr_actual'], 2)},
                        {"Métrica / Indicador": "Soporte Mínimo (30d)", "Valor": round(res['soporte_min'], 2)},
                        {"Métrica / Indicador": "Resistencia Máxima (30d)", "Valor": round(res['resistencia_max'], 2)},
                        {"Métrica / Indicador": "PER (P/E Fundamental)", "Valor": round(res['pe_ratio'], 2) if res['pe_ratio'] else "N/A"},
                        {"Métrica / Indicador": "Precio Objetivo Analistas (USD)", "Valor": round(res['target_price'], 2) if res['target_price'] else "N/A"},
                        {"Métrica / Indicador": "Dirección Operativa Sugerida", "Valor": res['direccion_op']},
                        {"Métrica / Indicador": "Stop Loss Recomendado (USD)", "Valor": round(res['stop_loss'], 2)},
                        {"Métrica / Indicador": "Take Profit Objetivo (USD)", "Valor": round(res['take_profit'], 2)},
                        {"Métrica / Indicador": "Veredicto Final", "Valor": res['veredicto_texto']}
                    ])

                    df_hist_export = df[['Open', 'High', 'Low', 'Close', 'Volume', 'EMA_9', 'SMA_20', 'SMA_50', 'RSI', 'RVOL', 'ATR', 'MACD']].tail(60).copy()
                    df_hist_export.index = df_hist_export.index.tz_localize(None)
                    df_hist_export = df_hist_export.round(2)

                    buffer_excel = io.BytesIO()
                    with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                        df_resumen.to_excel(writer, sheet_name='Resumen_y_Senales', index=False)
                        df_proyeccion.to_excel(writer, sheet_name='Proyeccion_5_Dias', index=False)
                        df_hist_export.to_excel(writer, sheet_name='Historial_60_Dias')

                    st.download_button(
                        label="📥 Descargar Reporte Individual en Excel (.xlsx)",
                        data=buffer_excel.getvalue(),
                        file_name=f"Reporte_Pro_{ticker}_{res['ultima_fecha'].strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

                with col_didactica:
                    st.subheader("🧠 Explicación Didáctica del Análisis")
                    st.write("¿Por qué el algoritmo toma esta decisión hoy?")
                    for razon in res["razones_didacticas"]:
                        st.markdown(f"- {razon}")
                    st.info("💡 **Cómo leer el Cono Naranja del gráfico:** La línea punteada central es el **Precio Consenso** más probable. El área sombreada muestra el **Piso y Techo diario** donde puede oscilar la acción según su volatilidad histórica.")


# ==============================================================================
# PESTAÑA 2: ESCÁNER MULTI-ACCIONES (RANKING DE FAVORITAS)
# ==============================================================================
with tab_escaner:
    st.subheader("🚀 Escáner Automático de Cartera y Acciones Favoritas")
    st.write("Ingresa tus símbolos separados por coma. El algoritmo analizará cada acción en tiempo real y las ordenará de **Mayor a Menor Puntaje de Compra**.")

    col_lista, col_btn_scan = st.columns([3, 1])
    with col_lista:
        lista_tickers_input = st.text_input(
            "Lista de acciones favoritas (separadas por coma):",
            "FSLR, OUST, AMZN, TMDX, UBER, VPG, AUNA, NVDA, AAPL, MSFT, QQQ"
        )
    with col_btn_scan:
        st.write("")
        st.write("")
        escanear_btn = st.button("⚡ Escanear y Ordenar Ahora", use_container_width=True)

    if escanear_btn:
        tickers_limpios = [t.strip().upper() for t in lista_tickers_input.split(",") if t.strip()]
        
        if not tickers_limpios:
            st.warning("⚠️ Ingresa al menos un símbolo bursátil válido.")
        else:
            barra_progreso = st.progress(0, text="Iniciando escaneo del mercado...")
            resultados_scan = []

            for idx, tk in enumerate(tickers_limpios):
                barra_progreso.progress((idx + 1) / len(tickers_limpios), text=f"Analizando {tk} ({idx+1}/{len(tickers_limpios)})...")
                datos_tk = analizar_accion(tk)
                if datos_tk is not None:
                    upside_analistas = ((datos_tk['target_price'] - datos_tk['ultimo_precio']) / datos_tk['ultimo_precio'] * 100) if datos_tk['target_price'] else None
                    resultados_scan.append({
                        "Ticker": datos_tk["ticker"],
                        "Empresa": datos_tk["nombre_empresa"],
                        "Puntaje (0-100)": datos_tk["score"],
                        "Señal Operativa": datos_tk["senal_corta"],
                        "Precio Actual ($)": round(datos_tk["ultimo_precio"], 2),
                        "Cambio Hoy (%)": round(datos_tk["cambio_hoy_pct"], 2),
                        "RSI (14d)": round(datos_tk["rsi_actual"], 1),
                        "Volumen RVOL (x)": round(datos_tk["rvol_actual"], 2),
                        "PER (P/E)": round(datos_tk["pe_ratio"], 1) if datos_tk["pe_ratio"] else np.nan,
                        "Proyección Día +5 ($)": round(datos_tk["precio_dia5"], 2),
                        "Var. Esperada 5D (%)": round(datos_tk["var_dia5_pct"], 2),
                        "Stop Loss ATR ($)": round(datos_tk["stop_loss"], 2),
                        "Take Profit ATR ($)": round(datos_tk["take_profit"], 2),
                        "Objetivo Wall St ($)": round(datos_tk["target_price"], 2) if datos_tk["target_price"] else np.nan,
                        "Potencial Wall St (%)": round(upside_analistas, 1) if upside_analistas is not None else np.nan
                    })

            barra_progreso.empty()

            if not resultados_scan:
                st.error("❌ No se pudieron obtener datos de los símbolos ingresados.")
            else:
                # Ordenar de Mayor a Menor Puntaje de Compra (y desempate por Variación Esperada 5D)
                df_ranking = pd.DataFrame(resultados_scan)
                df_ranking = df_ranking.sort_values(by=["Puntaje (0-100)", "Var. Esperada 5D (%)"], ascending=[False, False]).reset_index(drop=True)
                df_ranking.insert(0, " puesto", [f"#{i+1}" for i in range(len(df_ranking))])
                df_ranking.rename(columns={" puesto": "Ranking"}, inplace=True)

                # Tarjetas Destacadas del Escáner (Top Picks)
                mejor_accion = df_ranking.iloc[0]
                mas_sobrevendida = df_ranking.sort_values(by="RSI (14d)", ascending=True).iloc[0]
                mayor_proyeccion_5d = df_ranking.sort_values(by="Var. Esperada 5D (%)", ascending=False).iloc[0]

                k1, k2, k3 = st.columns(3)
                k1.metric(
                    "🏆 #1 Mejor Puntaje Global",
                    f"{mejor_accion['Ticker']} ({mejor_accion['Puntaje (0-100)']}/100)",
                    mejor_accion["Señal Operativa"]
                )
                k2.metric(
                    "💎 Mayor Sobreventa (Candidata Rebote)",
                    f"{mas_sobrevendida['Ticker']} (RSI {mas_sobrevendida['RSI (14d)']})",
                    f"Precio: ${mas_sobrevendida['Precio Actual ($)']:.2f}",
                    delta_color="off"
                )
                k3.metric(
                    "🚀 Mayor Proyección a 5 Días",
                    f"{mayor_proyeccion_5d['Ticker']} (${mayor_proyeccion_5d['Proyección Día +5 ($)']:.2f})",
                    f"{mayor_proyeccion_5d['Var. Esperada 5D (%)']:+.2f}% estimado en 5D"
                )

                # Mostrar Tabla Ranking Ordenada
                st.subheader("📋 Tabla Comparativa Ordenada por Puntaje de Compra")
                st.dataframe(df_ranking, use_container_width=True, hide_index=True)

                # Botón para Descargar el Ranking Completo en Excel
                buffer_scan_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_scan_excel, engine='openpyxl') as writer:
                    df_ranking.to_excel(writer, sheet_name='Ranking_Acciones', index=False)

                st.download_button(
                    label="📥 Descargar Ranking Comparativo Completo en Excel (.xlsx)",
                    data=buffer_scan_excel.getvalue(),
                    file_name=f"Ranking_Favoritas_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                # Gráficos Comparativos Didácticos
                st.subheader("📊 Gráficos Comparativos de Toma de Decisiones")
                g_col1, g_col2 = st.columns(2)

                with g_col1:
                    colores_barras = [
                        "#00C853" if s >= 62 else ("#FFB300" if s >= 45 else "#D50000")
                        for s in df_ranking["Puntaje (0-100)"]
                    ]
                    fig_bar = go.Figure(go.Bar(
                        x=df_ranking["Puntaje (0-100)"][::-1],
                        y=df_ranking["Ticker"][::-1],
                        orientation='h',
                        marker_color=colores_barras[::-1],
                        text=[f"{s} pts ({v:+.1f}% en 5D)" for s, v in zip(df_ranking["Puntaje (0-100)"][::-1], df_ranking["Var. Esperada 5D (%)"][::-1])],
                        textposition='auto'
                    ))
                    fig_bar.update_layout(
                        title="Ranking por Puntaje Global (Verde = Compra | Amarillo = Vigilar | Rojo = Venta)",
                        xaxis_title="Puntaje Algorítmico (0 a 100)",
                        yaxis_title="Acción",
                        height=440,
                        template="plotly_white"
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

                with g_col2:
                    fig_scatter = go.Figure()
                    fig_scatter.add_trace(go.Scatter(
                        x=df_ranking["RSI (14d)"],
                        y=df_ranking["Puntaje (0-100)"],
                        mode='markers+text',
                        text=df_ranking["Ticker"],
                        textposition="top center",
                        marker=dict(
                            size=np.clip(df_ranking["Volumen RVOL (x)"] * 14, 12, 35),
                            color=df_ranking["Puntaje (0-100)"],
                            colorscale="RdYlGn",
                            showscale=True,
                            colorbar=dict(title="Score")
                        ),
                        hovertemplate="<b>%{text}</b><br>RSI: %{x}<br>Puntaje: %{y}<extra></extra>"
                    ))
                    fig_scatter.add_vrect(x0=0, x1=32, fillcolor="green", opacity=0.1, line_width=0, annotation_text="Zona Sobreventa (Oportunidad)")
                    fig_scatter.add_vrect(x0=70, x1=100, fillcolor="red", opacity=0.1, line_width=0, annotation_text="Zona Sobrecompra (Riesgo)")
                    fig_scatter.add_hline(y=62, line_dash="dot", line_color="green", annotation_text="Umbral Compra Confirmada (62 pts)")
                    fig_scatter.update_layout(
                        title="Mapa Radar: RSI vs. Puntaje (Tamaño burbuja = Volumen RVOL)",
                        xaxis_title="RSI 14 Días (<32 Barata/Sobreventa | >70 Cara/Sobrecompra)",
                        yaxis_title="Puntaje Global (0-100)",
                        height=440,
                        template="plotly_white"
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True)