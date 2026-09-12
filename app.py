"""Aplicación Streamlit para la conciliación diaria TSW."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from conciliacion import (
    conciliar_sistemas,
    generar_reporte_excepciones,
    leer_csv,
)


POS_MAPPING = {
    "Ticket_No": "id_referencia",
    "Monto_Total": "monto",
}

DATAFAST_MAPPING = {
    "Num_Autorizacion": "id_referencia",
    "Valor_Liquidado": "monto",
}


def datos_de_ejemplo() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve datos de demostración para explorar la aplicación."""
    pos = pd.DataFrame(
        {
            "Ticket_No": ["T-1001", "T-1002", "T-1003", "T-1004", "T-1005"],
            "Fecha": ["2026-09-12"] * 5,
            "Metodo_Pago": [
                "Tarjeta",
                "Tarjeta",
                "Tarjeta",
                "Tarjeta",
                "Efectivo",
            ],
            "Monto_Total": [500.00, 100.00, 50.00, 75.50, 25.00],
        }
    )
    datafast = pd.DataFrame(
        {
            "Num_Autorizacion": ["T-1001", "T-1002", "T-1004", "T-9999"],
            "Fecha_Proceso": ["2026-09-12"] * 4,
            "Valor_Liquidado": [480.00, 100.00, 75.50, 200.00],
        }
    )
    return pos, datafast


def cargar_datos(
    archivo_pos,
    archivo_datafast,
    usar_ejemplos: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carga y normaliza los dos archivos desde la interfaz."""
    if usar_ejemplos:
        pos_crudo, datafast_crudo = datos_de_ejemplo()
        pos_normalizado = leer_csv(
            BytesIO(pos_crudo.to_csv(index=False).encode("utf-8")),
            POS_MAPPING,
            "POS",
        )[1]
        datafast_normalizado = leer_csv(
            BytesIO(datafast_crudo.to_csv(index=False).encode("utf-8")),
            DATAFAST_MAPPING,
            "Datafast",
        )[1]
        return (
            pos_crudo,
            datafast_crudo,
            pos_normalizado,
            datafast_normalizado,
        )

    if archivo_pos is None or archivo_datafast is None:
        raise ValueError(
            "Carga los dos archivos CSV o activa los datos de ejemplo."
        )

    pos_crudo, pos_normalizado = leer_csv(
        archivo_pos,
        POS_MAPPING,
        "POS",
    )
    datafast_crudo, datafast_normalizado = leer_csv(
        archivo_datafast,
        DATAFAST_MAPPING,
        "Datafast",
    )
    return (
        pos_crudo,
        datafast_crudo,
        pos_normalizado,
        datafast_normalizado,
    )


def mostrar_resumen(resultado: dict[str, pd.DataFrame]) -> None:
    """Muestra métricas y gráficos del resultado de la conciliación."""
    cuadran = resultado["cuadran"]
    diferencias = resultado["diferencias_monto"]
    solo_datafast = resultado["solo_datafast"]
    solo_pos = resultado["solo_pos"]
    total_excepciones = (
        len(diferencias) + len(solo_datafast) + len(solo_pos)
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Conciliadas", len(cuadran))
    col2.metric("Diferencias", len(diferencias))
    col3.metric("Solo Datafast", len(solo_datafast))
    col4.metric("Solo POS", len(solo_pos))

    st.subheader("Distribución del resultado")
    resumen = pd.DataFrame(
        {
            "Estado": [
                "Conciliadas",
                "Diferencias de monto",
                "Solo Datafast",
                "Solo POS",
            ],
            "Cantidad": [
                len(cuadran),
                len(diferencias),
                len(solo_datafast),
                len(solo_pos),
            ],
        }
    ).set_index("Estado")
    st.bar_chart(resumen, color="#2563EB")

    if total_excepciones == 0:
        st.success("Todas las transacciones coinciden dentro de la tolerancia.")
    else:
        st.warning(f"Se encontraron {total_excepciones} excepciones para revisar.")

    if not diferencias.empty:
        st.subheader("Diferencias de monto")
        diferencias_grafico = diferencias[
            ["id_referencia", "diferencia"]
        ].set_index("id_referencia")
        st.bar_chart(diferencias_grafico, color="#F59E0B")


def mostrar_tabla(
    titulo: str,
    df: pd.DataFrame,
    mensaje_vacio: str,
) -> None:
    st.subheader(titulo)
    if df.empty:
        st.info(mensaje_vacio)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


st.set_page_config(
    page_title="TSW Conciliador",
    page_icon=None,
    layout="wide",
)

st.title("TSW Conciliador")
st.write(
    "Carga las ventas del POS y las liquidaciones de Datafast para "
    "detectar diferencias, pagos faltantes y movimientos no registrados."
)

with st.sidebar:
    st.header("Fuentes de datos")
    archivo_pos = st.file_uploader(
        "Archivo de ventas POS",
        type=["csv"],
        help="Debe incluir Ticket_No y Monto_Total.",
    )
    archivo_datafast = st.file_uploader(
        "Archivo de liquidaciones Datafast",
        type=["csv"],
        help="Debe incluir Num_Autorizacion y Valor_Liquidado.",
    )
    usar_ejemplos = st.checkbox(
        "Usar datos de ejemplo",
        value=archivo_pos is None and archivo_datafast is None,
    )
    tolerancia = st.number_input(
        "Tolerancia máxima por transacción",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        help="Las diferencias iguales o menores a este valor se consideran conciliadas.",
    )
    ejecutar = st.button(
        "Ejecutar conciliación",
        type="primary",
        use_container_width=True,
    )

if ejecutar or "resultado" not in st.session_state:
    try:
        (
            pos_crudo,
            datafast_crudo,
            pos_normalizado,
            datafast_normalizado,
        ) = cargar_datos(
            archivo_pos,
            archivo_datafast,
            usar_ejemplos,
        )
        st.session_state["pos_crudo"] = pos_crudo
        st.session_state["datafast_crudo"] = datafast_crudo
        st.session_state["resultado"] = conciliar_sistemas(
            pos_normalizado,
            datafast_normalizado,
            tolerancia_max=tolerancia,
        )
        st.session_state["tolerancia"] = tolerancia
    except (ValueError, pd.errors.ParserError) as error:
        st.error(str(error))
        st.stop()

resultado = st.session_state["resultado"]
st.caption(
    f"Tolerancia aplicada: ${st.session_state.get('tolerancia', tolerancia):.2f}"
)

tab_resumen, tab_pos, tab_datafast, tab_excepciones = st.tabs(
    ["Resumen", "Tabla POS", "Tabla Datafast", "Excepciones"]
)

with tab_resumen:
    mostrar_resumen(resultado)

with tab_pos:
    mostrar_tabla(
        "Ventas cargadas del POS",
        st.session_state["pos_crudo"],
        "No hay ventas POS cargadas.",
    )

with tab_datafast:
    mostrar_tabla(
        "Liquidaciones cargadas de Datafast",
        st.session_state["datafast_crudo"],
        "No hay liquidaciones Datafast cargadas.",
    )

with tab_excepciones:
    reporte = generar_reporte_excepciones(
        resultado["diferencias_monto"],
        resultado["solo_datafast"],
        resultado["solo_pos"],
    )
    mostrar_tabla(
        "Reporte de diferencias",
        reporte,
        "No hay excepciones para mostrar.",
    )
    if not reporte.empty:
        st.download_button(
            "Descargar reporte CSV",
            data=reporte.to_csv(index=False).encode("utf-8"),
            file_name="reporte_excepciones.csv",
            mime="text/csv",
            use_container_width=True,
        )

from conciliacion import generar_reporte_ia

st.write("**Auditoría Inteligente**")

# Asegúrate de usar la variable donde guardas el resultado de generar_reporte_excepciones()
# Aquí asumimos que la variable se llama df_excepciones
if not df_excepciones.empty: 
    if st.button("Generar Reporte Gerencial"):
        with st.spinner("Procesando auditoría financiera con Gemini..."):
            # Convertimos la tabla de errores a texto simple para no saturar la API
            resumen_datos = df_excepciones.to_string(index=False) 
            reporte = generar_reporte_ia(resumen_datos)
            
            st.info(reporte)
else:
    st.success("No se encontraron discrepancias. Cuadre perfecto.")

