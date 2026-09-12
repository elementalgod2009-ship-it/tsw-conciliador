"""Aplicación Streamlit para la conciliación diaria TSW."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from conciliacion import (
    conciliar_sistemas,
    generar_reporte_excepciones,
    generar_reporte_ia,
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
    
    total_registros = len(resultado["cruce"])
    pct_salud = round((len(cuadran) / total_registros) * 100, 1) if total_registros > 0 else 0.0

    # Cálculo de monto total en riesgo
    monto_descuadre = diferencias["diferencia"].sum() if not diferencias.empty else 0.0
    monto_sobrante = solo_datafast["monto_datafast"].sum() if not solo_datafast.empty else 0.0
    monto_faltante = solo_pos["monto_pos"].sum() if not solo_pos.empty else 0.0
    monto_riesgo_total = monto_descuadre + monto_sobrante + monto_faltante

    # Tarjetas de Indicadores Superiores (KPIs)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Salud Financiera", f"{pct_salud}%", help="% de transacciones conciliadas")
    col2.metric("Monto en Riesgo", f"${monto_riesgo_total:,.2f}", delta="-Riesgo", delta_color="inverse")
    col3.metric("Conciliadas ($1:1$)", f"{len(cuadran)} reg")
    col4.metric("Excepciones Totales", f"{len(diferencias) + len(solo_datafast) + len(solo_pos)} reg")

    st.divider()

    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader(" Distribución por Criterio")
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

    with col_der:
        st.subheader(" Desglose del Riesgo Monetario")
        riesgo_df = pd.DataFrame(
            {
                "Tipo Anomalía": [
                    "Descuadres de Monto",
                    "Sobrantes Datafast",
                    "Faltantes POS",
                ],
                "Monto ($)": [
                    monto_descuadre,
                    monto_sobrante,
                    monto_faltante,
                ],
            }
        ).set_index("Tipo Anomalía")
        st.bar_chart(riesgo_df, color="#DC2626")

    total_excepciones = len(diferencias) + len(solo_datafast) + len(solo_pos)
    if total_excepciones == 0:
        st.success("🎉 ¡Excelente! Todas las transacciones coinciden dentro de la tolerancia.")
    else:
        st.warning(f"Se encontraron {total_excepciones} excepciones por un total de ${monto_riesgo_total:,.2f} para auditoría.")


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


# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="TSW Conciliador - Agente de Auditoría",
    page_icon="⛽",
    layout="wide",
)

st.title(" TSW Conciliador: Agente Analítico de Auditoría")
st.write(
    "Plataforma inteligente de auditoría diaria para Estaciones de Servicio. "
    "Cruza las ventas de pista (POS) contra las liquidaciones electrónicas (Datafast) "
    "e infiere el origen de las excepciones mediante Inteligencia Artificial."
)

with st.sidebar:
    st.header("⚙️ Configuración")
    archivo_pos = st.file_uploader(
        "Archivo de ventas POS (Pista)",
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
        "Tolerancia máxima ($)",
        min_value=0.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        help="Diferencias menores o iguales a este valor se considerarán cuadradas.",
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

# Cálculo unificado del reporte de excepciones
reporte_excepciones = generar_reporte_excepciones(
    resultado["diferencias_monto"],
    resultado["solo_datafast"],
    resultado["solo_pos"],
)

# --- PESTAÑAS DE NAVEGACIÓN ---
tab_resumen, tab_agente, tab_excepciones, tab_pos, tab_datafast = st.tabs(
    ["📊 Resumen & KPIs", "🤖 Agente IA", "⚠️ Excepciones", "📋 Tabla POS", "💳 Tabla Datafast"]
)

with tab_resumen:
    mostrar_resumen(resultado)

with tab_agente:
    st.subheader("🤖 Diagnóstico Narrativo de Auditoría")
    st.caption("Análisis contextual impulsado por el modelo Gemini 3.6 Flash")
    
    if reporte_excepciones.empty:
        st.success("🎉 No se detectaron discrepancias en este cierre. No se requiere diagnóstico de la IA.")
    else:
        st.info("El Agente examinará la tabla de excepciones para identificar patrones, evaluar riesgos y sugerir el protocolo de revisión.")
        if st.button("Generar Diagnóstico del Agente", type="primary"):
            with st.spinner("Analizando anomalías operativas con Gemini..."):
                resumen_texto = reporte_excepciones.to_string(index=False)
                diagnostico = generar_reporte_ia(resumen_texto)
                st.markdown(diagnostico)

with tab_excepciones:
    mostrar_tabla(
        "Reporte de diferencias y excepciones",
        reporte_excepciones,
        "No hay excepciones para mostrar.",
    )
    if not reporte_excepciones.empty:
        st.download_button(
            "📥 Descargar reporte de excepciones (CSV)",
            data=reporte_excepciones.to_csv(index=False).encode("utf-8"),
            file_name="reporte_excepciones.csv",
            mime="text/csv",
            use_container_width=True,
        )

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
