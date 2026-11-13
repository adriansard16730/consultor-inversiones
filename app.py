import math
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Mi consultor de inversiones",
    layout="wide"
)

st.title("Mi consultor de inversiones")
st.info(
    "CONDICIONES PARA MARCAR EN VERDE\n\n"
    "- RSI de 14 sesiones: menor que 40.\n"
    "- PEG: mayor que 0 y menor que 1.\n"
    "- PER histórico: mayor que 0 y menor que 30.\n"
    "- BPA anual/TTM: BPA TTM mayor que el último "
    "ejercicio fiscal cerrado, con fecha TTM posterior.\n"
    "- BPA trimestral: último BPA diluido trimestral "
    "mayor que el del mismo trimestre del año anterior.\n\n"
    "Si el TTM y el cierre anual coinciden, "
    "la comparación anual/TTM queda sin verde. "
    "La comparación trimestral se evalúa por separado.\n\n"
    "Los datos faltantes no se sustituyen por cero. "
    "En ETFs, BPA, PER y PEG no se evalúan en esta versión. "
    "El verde indica que se cumple tu filtro, "
    "no una recomendación de compra."
)
st.caption("Versión de prueba 2 — cotizaciones sin caché")
st.caption(
    "Fuente: Yahoo Finance mediante yfinance. "
    "No utiliza Stock Analysis."
)


# ---------- Funciones auxiliares ----------

def numero(valor):
    try:
        resultado = float(valor)
        return resultado if math.isfinite(resultado) else None
    except (TypeError, ValueError):
        return None


def formato(valor):
    valor = numero(valor)
    if valor is None:
        return "No disponible"
    texto = f"{valor:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def primero(*valores):
    for valor in valores:
        if valor is not None and valor != "":
            return valor
    return None


def fecha_texto(fecha):
    if fecha is None:
        return "fecha no disponible"
    return pd.Timestamp(fecha).strftime("%d/%m/%Y")


def rsi_wilder(cierres, periodo=14):
    precios = pd.to_numeric(cierres, errors="coerce").dropna()

    if len(precios) < periodo + 1:
        return None

    cambios = precios.diff().dropna()
    ganancias = cambios.clip(lower=0)
    perdidas = -cambios.clip(upper=0)

    media_ganancia = float(ganancias.iloc[:periodo].mean())
    media_perdida = float(perdidas.iloc[:periodo].mean())

    for i in range(periodo, len(cambios)):
        media_ganancia = (
            media_ganancia * (periodo - 1) + float(ganancias.iloc[i])
        ) / periodo
        media_perdida = (
            media_perdida * (periodo - 1) + float(perdidas.iloc[i])
        ) / periodo

    if media_perdida == 0:
        return 100.0 if media_ganancia > 0 else 50.0

    rs = media_ganancia / media_perdida
    return 100 - 100 / (1 + rs)


def extraer_bpa(tabla):
    if tabla is None or tabla.empty:
        return None, None

    fila = None
    for nombre in ("Diluted EPS", "DilutedEPS"):
        if nombre in tabla.index:
            fila = nombre
            break

    if fila is None:
        return None, None

    serie = tabla.loc[fila]

    if isinstance(serie, pd.DataFrame):
        serie = serie.iloc[0]

    candidatos = []
    hoy = pd.Timestamp.now().date()

    for columna, valor in serie.items():
        try:
            fecha = pd.Timestamp(columna)
            importe = numero(valor)
            if fecha.date() <= hoy and importe is not None:
                candidatos.append((fecha, importe))
        except Exception:
            continue

    if not candidatos:
        return None, None

    fecha, importe = max(candidatos, key=lambda x: x[0])
    return importe, fecha



def buscar_instrumentos(texto):
    resultados = []
    try:
        resultados = yf.Search(
            texto,
            max_results=12,
            news_count=0
        ).quotes or []
    except Exception:
        pass

    filas = []
    vistos = set()

    for item in resultados:
        simbolo = item.get("symbol")
        if not simbolo or simbolo in vistos:
            continue

        vistos.add(simbolo)
        filas.append({
            "symbol": simbolo,
            "nombre": (
                item.get("longname")
                or item.get("shortname")
                or simbolo
            ),
            "mercado": (
                item.get("exchDisp")
                or item.get("exchange")
                or "Mercado no informado"
            ),
            "tipo": item.get("quoteType") or "Tipo no informado"
        })

    return filas



def cargar_cotizacion(simbolo):
    activo = yf.Ticker(simbolo)
    avisos = []

    try:
        info = dict(activo.get_info() or {})
    except Exception:
        info = {}
        avisos.append("No se pudo recuperar la ficha completa.")

    try:
        historial = activo.history(
            period="1y",
            interval="1d",
            auto_adjust=True
        )
    except Exception:
        historial = pd.DataFrame()
        avisos.append("No se pudo recuperar el historial.")

    try:
        meta = activo.get_history_metadata() or {}
    except Exception:
        meta = {}

    return info, historial, meta, avisos


@st.cache_data(ttl=3600, max_entries=100)
def cargar_fundamentales(simbolo):
    activo = yf.Ticker(simbolo)
    avisos = []

    try:
        anual = activo.income_stmt
    except Exception:
        anual = pd.DataFrame()
        avisos.append("No se obtuvo el estado de resultados anual.")

    try:
        ttm = activo.ttm_income_stmt
    except Exception:
        ttm = pd.DataFrame()
        avisos.append("No se obtuvo el estado de resultados TTM.")

    return anual, ttm, avisos


def pintar_tabla(tabla, verdes):
    estilos = pd.DataFrame(
        "",
        index=tabla.index,
        columns=tabla.columns
    )
    for fila in verdes:
        estilos.loc[fila, "Actual / TTM"] = (
            "background-color: #d9ead3; color: #153b19;"
        )
    return estilos

def comparar_bpa_trimestral(simbolo):
    try:
        tabla = yf.Ticker(simbolo).quarterly_income_stmt
    except Exception:
        return None, None, None, None

    if tabla is None or tabla.empty:
        return None, None, None, None

    fila = None
    for nombre in ("Diluted EPS", "DilutedEPS"):
        if nombre in tabla.index:
            fila = nombre
            break

    if fila is None:
        return None, None, None, None

    serie = tabla.loc[fila]

    if isinstance(serie, pd.DataFrame):
        serie = serie.iloc[0]

    registros = []
    hoy = pd.Timestamp.now().date()

    for columna, valor in serie.items():
        try:
            fecha = pd.Timestamp(columna)
            importe = numero(valor)

            if fecha.date() <= hoy and importe is not None:
                registros.append((fecha, importe))
        except Exception:
            continue

    if not registros:
        return None, None, None, None

    fecha_actual, bpa_actual = max(
        registros,
        key=lambda registro: registro[0]
    )

    objetivo = fecha_actual - pd.DateOffset(years=1)

    # Permite pequeñas diferencias de fecha por calendarios fiscales.
    candidatos = [
        (fecha, importe)
        for fecha, importe in registros
        if fecha < fecha_actual
        and abs((fecha - objetivo).days) <= 15
    ]

    if not candidatos:
        return bpa_actual, fecha_actual, None, None

    fecha_anterior, bpa_anterior = min(
        candidatos,
        key=lambda registro: abs((registro[0] - objetivo).days)
    )

    return (
        bpa_actual,
        fecha_actual,
        bpa_anterior,
        fecha_anterior
    )
# ---------- Buscador ----------

st.subheader("1. Buscar instrumento")

with st.form("busqueda"):
    texto = st.text_input(
        "Nombre de empresa, fondo o ticker",
        placeholder="Ejemplo: Apple, AAPL o un ticker local"
    )
    buscar = st.form_submit_button("Buscar coincidencias")

if buscar:
    consulta = texto.strip()
    if consulta:
        st.session_state["coincidencias"] = buscar_instrumentos(consulta)
        st.session_state.pop("seleccion_instrumento", None)
    else:
        st.warning("Escribí un nombre o ticker.")

coincidencias = st.session_state.get("coincidencias", [])

if coincidencias:
    opciones = {
        (
            f"{item['nombre']} | {item['symbol']} | "
            f"{item['mercado']} | {item['tipo']}"
        ): item
        for item in coincidencias
    }

    seleccion = st.selectbox(
        "Seleccioná el resultado correcto",
        list(opciones.keys()),
        key="seleccion_instrumento"
    )

    elegido = opciones[seleccion]
    simbolo_elegido = elegido["symbol"]
    tipo_detectado = str(elegido["tipo"]).upper()
else:
    simbolo_elegido = ""
    tipo_detectado = ""
    st.caption(
        "Si no encontrás el instrumento, podés escribir "
        "su ticker exacto en el campo de abajo."
    )

ticker_manual = st.text_input(
    "Ticker exacto manual (opcional; reemplaza al resultado elegido)",
    placeholder="Escribilo tal como figura en Yahoo Finance"
)

simbolo = ticker_manual.strip().upper() or simbolo_elegido
uso_manual = bool(ticker_manual.strip())

st.subheader("2. Indicar qué instrumento vas a analizar")

tipos = ["Acción", "CEDEAR", "ETF"]
indice_tipo = 2 if tipo_detectado == "ETF" and not uso_manual else 0

tipo = st.selectbox(
    "Tipo de instrumento — revisá esta selección",
    tipos,
    index=indice_tipo
)

subyacente = ""
tipo_subyacente = "Acción"

if tipo == "CEDEAR":
    st.info(
        "El ticker principal debe ser el CEDEAR local. "
        "El precio, gráfico y RSI serán los del CEDEAR. "
        "Los fundamentos serán los del subyacente."
    )

    subyacente = st.text_input(
        "Ticker del subyacente",
        placeholder="Ejemplo: AAPL"
    ).strip().upper()

    tipo_subyacente = st.selectbox(
        "El subyacente es",
        ["Acción", "ETF"]
    )

    st.caption(
        "La relación CEDEAR/subyacente es manual. "
        "La app no la valida ni convierte importes por el ratio."
    )

analizar = st.button("Analizar instrumento", type="primary")

# ---------- Análisis ----------

if analizar:
    st.info("El botón funciona. Iniciando el análisis...")

    if not simbolo:
        st.warning("Primero elegí un resultado o escribí un ticker.")
        st.stop()

    if tipo == "CEDEAR" and not subyacente:
        st.warning("Indicá el ticker del subyacente.")
        st.stop()

    ticker_fundamental = (
        subyacente if tipo == "CEDEAR" else simbolo
    )

    es_fondo = (
        tipo == "ETF"
        or (
            tipo == "CEDEAR"
            and tipo_subyacente == "ETF"
        )
    )

    with st.spinner("Consultando precios e indicadores..."):
        info, historial, meta, avisos = cargar_cotizacion(simbolo)

        if ticker_fundamental == simbolo:
            info_fund = info
        else:
            info_fund, _, _, avisos_fund = cargar_cotizacion(
                ticker_fundamental
            )
            avisos += avisos_fund

        anual = pd.DataFrame()
        ttm = pd.DataFrame()

        if not es_fondo:
            anual, ttm, avisos_estados = cargar_fundamentales(
                ticker_fundamental
            )
            avisos += avisos_estados

    nombre = primero(
        info.get("longName"),
        info.get("shortName"),
        meta.get("longName"),
        meta.get("shortName"),
        simbolo
    )

    moneda = primero(
        info.get("currency"),
        meta.get("currency")
    )

    precio = numero(primero(
        info.get("regularMarketPrice"),
        info.get("currentPrice"),
        meta.get("regularMarketPrice")
    ))

    cierres = pd.Series(dtype=float)

    if not historial.empty and "Close" in historial:
        cierres = historial["Close"].dropna()

    precio_de_historial = False

    if precio is None and not cierres.empty:
        precio = numero(cierres.iloc[-1])
        precio_de_historial = True

    st.subheader(f"{nombre} — {simbolo}")
    st.write(f"Tipo seleccionado: {tipo}")
    st.write(
        f"Moneda de cotización: {moneda or 'No disponible'}"
    )
    st.write(f"Precio disponible: {formato(precio)}")

    if precio_de_historial:
        st.caption(
            "El precio mostrado procede del último cierre "
            "ajustado disponible en el historial."
        )

    if not cierres.empty:
        st.caption(
            "Último registro del historial: "
            + fecha_texto(cierres.index[-1])
        )

    if precio is None and cierres.empty:
        st.warning(
            "No se obtuvieron precios para este instrumento. "
            "Revisá el ticker o intentá nuevamente más tarde."
        )

    if tipo == "CEDEAR":
        st.warning(
            f"BPA, PER y PEG corresponden a "
            f"{ticker_fundamental}, no al certificado {simbolo}. "
            "El BPA no se convierte por el ratio del CEDEAR."
        )

    bpa_anual, fecha_anual = extraer_bpa(anual)
    bpa_ttm, fecha_ttm = extraer_bpa(ttm)

    per = numero(info_fund.get("trailingPE"))
    peg = numero(info_fund.get("trailingPegRatio"))
    rsi = rsi_wilder(cierres)

    filas = []
    verdes = []

    if es_fondo:
        filas.append({
            "Dato": "BPA diluido",
            "Actual / TTM": "No aplica: fondo",
            "Último ejercicio fiscal": "No aplica: fondo"
        })

        filas.append({
            "Dato": "PER",
            "Actual / TTM": "No disponible en esta versión",
            "Último ejercicio fiscal": "—"
        })

        filas.append({
            "Dato": "PEG",
            "Actual / TTM": "No aplica en esta versión",
            "Último ejercicio fiscal": "—"
        })

    else:
        filas.append({
            "Dato": "BPA diluido",
            "Actual / TTM": formato(bpa_ttm),
            "Último ejercicio fiscal": formato(bpa_anual)
        })

        filas.append({
            "Dato": "PER histórico",
            "Actual / TTM": formato(per),
            "Último ejercicio fiscal": "—"
        })

        filas.append({
            "Dato": "PEG de la fuente",
            "Actual / TTM": formato(peg),
            "Último ejercicio fiscal": "—"
        })

        if (
            bpa_ttm is not None
            and bpa_anual is not None
            and fecha_ttm is not None
            and fecha_anual is not None
            and fecha_ttm > fecha_anual
            and bpa_ttm > bpa_anual
        ):
            verdes.append(0)

        if per is not None and 0 < per < 30:
            verdes.append(1)

        if peg is not None and 0 < peg < 1:
            verdes.append(2)

    filas.append({
        "Dato": "RSI — 14 sesiones",
        "Actual / TTM": formato(rsi),
        "Último ejercicio fiscal": "—"
    })

    if rsi is not None and rsi < 40:
        verdes.append(3)

    if not es_fondo:
        with st.spinner("Comparando BPA trimestral..."):
            resultado_trimestral = comparar_bpa_trimestral(
                ticker_fundamental
            )

        (
            bpa_tri_actual,
            fecha_tri_actual,
            bpa_tri_anterior,
            fecha_tri_anterior
        ) = resultado_trimestral

        valor_tri_actual = formato(bpa_tri_actual)
        valor_tri_anterior = formato(bpa_tri_anterior)

        if fecha_tri_actual is not None:
            valor_tri_actual += (
                f" | cierre {fecha_texto(fecha_tri_actual)}"
            )

        if fecha_tri_anterior is not None:
            valor_tri_anterior += (
                f" | cierre {fecha_texto(fecha_tri_anterior)}"
            )

        indice_trimestral = len(filas)

        filas.append({
            "Dato": "BPA diluido — trimestre vs. mismo trimestre anterior",
            "Actual / TTM": valor_tri_actual,
            "Último ejercicio fiscal": valor_tri_anterior
        })

        if (
            bpa_tri_actual is not None
            and bpa_tri_anterior is not None
            and bpa_tri_actual > bpa_tri_anterior
        ):
            verdes.append(indice_trimestral)

        if (
            bpa_tri_actual is None
            or bpa_tri_anterior is None
        ):
            st.info(
                "No se obtuvieron los dos BPA trimestrales "
                "comparables. La fila trimestral queda sin verde."
            )

    tabla = pd.DataFrame(filas)

    tabla = tabla.rename(columns={
        "Último ejercicio fiscal": "Período de comparación"
    })

    st.subheader("Indicadores")

    tabla_con_colores = tabla.style.apply(
        lambda datos: pintar_tabla(datos, verdes),
        axis=None
    )

    st.dataframe(
        tabla_con_colores,
        hide_index=True,
        use_container_width=True
    )

    if not es_fondo:
        moneda_bpa = info_fund.get("financialCurrency")

        st.caption(
            f"Fundamentos de: {ticker_fundamental}. "
            "Moneda contable del BPA: "
            f"{moneda_bpa or 'No disponible'}."
        )

        st.caption(
            "Ejercicio anual terminado el: "
            f"{fecha_texto(fecha_anual)}. "
            "TTM terminado el: "
            f"{fecha_texto(fecha_ttm)}."
        )

        if fecha_anual is not None and fecha_ttm is not None:
            if fecha_anual == fecha_ttm:
                st.info(
                    "El cierre anual y el TTM tienen la misma "
                    "fecha. No se pinta el BPA porque no son "
                    "períodos distintos."
                )

            elif fecha_ttm < fecha_anual:
                st.warning(
                    "El TTM disponible es anterior al cierre "
                    "anual. No se pinta el BPA."
                )

        if bpa_ttm is None or bpa_anual is None:
            st.info(
                "Falta un BPA diluido comparable. "
                "Los valores faltantes no se sustituyen por cero "
                "ni por la suma de cuatro BPA trimestrales."
            )

        if peg is None:
            st.caption(
                "La fuente no entregó trailingPegRatio. "
                "No se sustituye por otro cálculo de PEG."
            )

    if not cierres.empty:
        st.subheader("Evolución del instrumento seleccionado")
        st.line_chart(cierres)

        st.caption(
            "Gráfico y RSI calculados con cierres diarios "
            "ajustados. El último registro puede pertenecer "
            "a una sesión todavía en curso."
        )

    else:
        st.warning(
            "No se obtuvo historial para calcular "
            "el RSI y el gráfico."
        )

    if es_fondo:
        st.info(
            "Vista de ETF: esta versión muestra cotización, "
            "gráfico y RSI. No presenta BPA empresarial "
            "ni un PER de cartera sin identificar."
        )

    if avisos:
        with st.expander("Avisos de la fuente"):
            for aviso in sorted(set(avisos)):
                st.write("- " + aviso)

    st.caption(
        "El verde indica que se cumple tu filtro. "
        "No equivale a una recomendación de compra."
    )

st.divider()

st.caption(
    "Los precios pueden tener demora. "
    "La búsqueda y los estados financieros se reutilizan "
    "durante una hora. Las cotizaciones se consultan "
    "al presionar Analizar instrumento. "
    "No es una herramienta de tiempo real."
)
