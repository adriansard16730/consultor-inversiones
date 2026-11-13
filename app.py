import math
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Mi consultor de inversiones",
    layout="wide"
)

st.title("Mi consultor de inversiones")
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


@st.cache_data(ttl=3600, max_entries=100)
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


@st.cache_data(ttl=300, max_entries=100)
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
