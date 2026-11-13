import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Mi consultor de inversiones",
    layout="centered"
)

st.title("Mi consultor de inversiones")
st.write("Ingresá un ticker y elegí los datos que querés consultar.")

st.info(
    "Esta primera versión usa Yahoo Finance, no Google Finance. "
    "La búsqueda es por ticker exacto, no por nombre de empresa."
)

CAMPOS = {
    "Nombre": "longName",
    "Moneda": "currency",
    "Precio de mercado": "regularMarketPrice",
    "Variación diaria (%)": "regularMarketChangePercent",
    "Cierre anterior": "regularMarketPreviousClose",
    "Apertura": "regularMarketOpen",
    "Mínimo del día": "dayLow",
    "Máximo del día": "dayHigh",
    "Volumen": "volume",
    "Capitalización de mercado": "marketCap",
    "PER histórico": "trailingPE",
    "Ganancia por acción": "trailingEps",
    "Mínimo de 52 semanas": "fiftyTwoWeekLow",
    "Máximo de 52 semanas": "fiftyTwoWeekHigh",
    "Sector": "sector",
    "Industria": "industry",
}

@st.cache_data(ttl=300, max_entries=100)
def consultar(ticker):
    activo = yf.Ticker(ticker)
    info = activo.get_info() or {}

    try:
        historial = activo.history(
            period="6mo",
            auto_adjust=False
        )
    except Exception:
        historial = pd.DataFrame()

    return info, historial


def formatear(valor, clave):
    if valor is None:
        return "No disponible"

    if isinstance(valor, (int, float)):
        if pd.isna(valor):
            return "No disponible"

        if clave == "regularMarketChangePercent":
            return f"{valor:+.2f}%"

        if clave in ("volume", "marketCap"):
            return f"{valor:,.0f}"

        return f"{valor:,.2f}"

    return str(valor)


with st.form("buscador"):
    ticker = st.text_input(
        "Ticker",
        placeholder="Ejemplo para probar: AAPL"
    )

    elegidos = st.multiselect(
        "¿Qué datos querés ver?",
        options=list(CAMPOS.keys()),
        default=[
            "Nombre",
            "Moneda",
            "Precio de mercado",
            "Variación diaria (%)"
        ]
    )

    mostrar_grafico = st.checkbox(
        "Mostrar gráfico de los últimos 6 meses",
        value=True
    )

    buscar = st.form_submit_button("Buscar")


if buscar:
    simbolo = ticker.strip().upper()

    if not simbolo:
        st.warning("Primero escribí un ticker.")

    elif not elegidos and not mostrar_grafico:
        st.warning("Elegí al menos un dato o activá el gráfico.")

    else:
        try:
            with st.spinner("Consultando datos..."):
                info, historial = consultar(simbolo)

            precio = info.get("regularMarketPrice")

            if precio is None:
                precio = info.get("currentPrice")

            if precio is None and not historial.empty:
                cierres = historial["Close"].dropna()
                if not cierres.empty:
                    precio = float(cierres.iloc[-1])

            if precio is None and historial.empty:
                st.warning(
                    "No se obtuvieron cotizaciones. "
                    "Revisá el ticker o probá nuevamente más tarde."
                )
            else:
                info["regularMarketPrice"] = precio

                nombre = (
                    info.get("longName")
                    or info.get("shortName")
                    or simbolo
                )

                st.subheader(nombre)
                st.caption(f"Símbolo consultado: {simbolo}")

                filas = []

                for etiqueta in elegidos:
                    clave = CAMPOS[etiqueta]
                    filas.append({
                        "Dato": etiqueta,
                        "Valor": formatear(info.get(clave), clave)
                    })

                if filas:
                    tabla = pd.DataFrame(filas)
                    st.dataframe(
                        tabla,
                        hide_index=True,
                        use_container_width=True
                    )

                if mostrar_grafico:
                    if not historial.empty:
                        st.subheader("Cierre diario: últimos 6 meses")
                        st.line_chart(historial["Close"])
                    else:
                        st.info("No hay historial disponible.")

                st.caption(
                    "La moneda es la informada por la fuente. "
                    "Los precios se muestran sin conversión. "
                    "Si no hay precio de mercado disponible, "
                    "se usa el último cierre histórico."
                )

        except Exception:
            st.error(
                "No se pudo completar la consulta. Puede deberse "
                "al ticker, a una interrupción de la fuente o "
                "a un límite temporal de consultas."
            )

st.caption(
    "Datos de Yahoo Finance mediante yfinance. "
    "Las consultas se reutilizan durante 5 minutos. "
    "No es una herramienta de cotizaciones en tiempo real "
    "ni de asesoramiento financiero."
)
