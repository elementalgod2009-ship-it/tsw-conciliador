"""Aplicación Streamlit para la conciliación diaria y auditoría con Datia (UI Mejorada)."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st

from conciliacion import (
    conciliar_sistemas,
    detectar_posibles_desfases,
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
    """Devuelve datos de demostración inspirados en los casos de Portete."""
    pos = pd.DataFrame(
        {
            "Ticket_No": ["T-1001", "T-1002", "T-1003", "T-1004", "T-1005", "T-1006"],
            "Fecha": ["2026-09-12"] * 6,
            "Metodo_Pago": ["Tarjeta"] * 5 + ["Efectivo"],
            "Monto_Total": [500.00, 100.00, 50.00, 75.50, 42.00, 25.00],
        }
    )
    datafast = pd.DataFrame(
        {
            "Num_Autorizacion": ["T-1001", "T-1002", "T-1004", "T-9988", "T-9999"],
            "Fecha_Proceso": ["2026-09-12"] * 5,
            "Valor_Liquidado": [480.00, 100.00, 75.50, 42.00, 200.00],
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
    """Muestra métricas y gráficos interactivos del resultado de la conciliación."""
    cuadran = resultado["cuadran"]
    diferencias = resultado["diferencias_monto"]
    solo_datafast = resultado["solo_datafast"]
    solo_pos = resultado["solo_pos"]

    total_registros = len(resultado["cruce"])
    pct_salud = round((len(cuadran) / total_registros) * 100, 1) if total_registros > 0 else 0.0

    monto_descuadre = diferencias["diferencia"].sum() if not diferencias.empty else 0.0
    monto_sobrante = solo_datafast["monto_datafast"].sum() if not solo_datafast.empty else 0.0
    monto_faltante = solo_pos["monto_pos"].sum() if not solo_pos.empty else 0.0
    monto_riesgo_total = monto_descuadre + monto_sobrante + monto_faltante

    # KPI Cards estilizadas
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Salud Financiera", f"{pct_salud}%", help="% de transacciones conciliadas sin ajuste")
    col2.metric("Monto a Investigar", f"${monto_riesgo_total:,.2f}", delta="Riesgo Acumulado", delta_color="inverse")
    col3.metric("Conciliadas (1:1)", f"{len(cuadran)} reg")
    col4.metric("Excepciones Totales", f"{len(diferencias) + len(solo_datafast) + len(solo_pos)} reg")

    st.divider()

    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader("📊 Distribución por Criterio")
        df_criterio = pd.DataFrame(
            {
                "Criterio": ["Conciliadas", "Diferencia Monto", "Solo Datafast", "Solo POS"],
                "Cantidad": [len(cuadran), len(diferencias), len(solo_datafast), len(solo_pos)],
            }
        )
        fig_criterio = px.bar(
            df_criterio,
            x="Criterio",
            y="Cantidad",
            text="Cantidad",
            color="Criterio",
            color_discrete_sequence=["#10B981", "#F59E0B", "#3B82F6", "#EF4444"],
        )
        fig_criterio.update_traces(textposition="outside")
        fig_criterio.update_layout(
            showlegend=False,
            xaxis_title="",
            yaxis_title="Número de Registros",
            margin=dict(l=10, r=10, t=20, b=20),
            height=320,
        )
        st.plotly_chart(fig_criterio, use_container_width=True)

    with col_der:
        st.subheader("⚠️ Desglose del Riesgo Monetario")
        df_riesgo = pd.DataFrame(
            {
                "Tipo de Riesgo": ["Descuadre Monto", "Faltante POS", "Sobrante Datafast"],
                "Monto ($)": [monto_descuadre, monto_faltante, monto_sobrante],
            }
        )
        fig_riesgo = px.bar(
            df_riesgo,
            x="Tipo de Riesgo",
            y="Monto ($)",
            text_auto=".2f",
            color="Tipo de Riesgo",
            color_discrete_sequence=["#F59E0B", "#EF4444", "#8B5CF6"],
        )
        fig_riesgo.update_traces(textposition="outside")
        fig_riesgo.update_layout(
            showlegend=False,
            xaxis_title="",
            yaxis_title="Monto en Dólares ($)",
            margin=dict(l=10, r=10, t=20, b=20),
            height=320,
        )
        st.plotly_chart(fig_riesgo, use_container_width=True)


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
    page_title="Datia - Asistente de Cierre de Caja",
    page_icon="⛽",
    layout="wide",
)

# Estilos CSS Personalizados para UI Ejecutiva
st.markdown(
    """
    <style>
    .main { background-color: #0E1117; }
    div[data-testid="stMetricValue"] { font-size: 2rem; font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 6px 6px 0px 0px; padding: 8px 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("⛽ Datia: Asistente de Auditoría de Cierre de Caja")
st.caption("Plataforma de investigación operativa basada en evidencia para Estaciones de Servicio")

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
        "Usar datos de ejemplo (Escenario Portete)",
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

reporte_excepciones = generar_reporte_excepciones(
    resultado["diferencias_monto"],
    resultado["solo_datafast"],
    resultado["solo_pos"],
)

desfases_df = detectar_posibles_desfases(
    resultado["solo_pos"],
    resultado["solo_datafast"]
)

# --- PESTAÑAS DE NAVEGACIÓN ---
tab_resumen, tab_agente, tab_desfases, tab_excepciones, tab_pos, tab_datafast = st.tabs(
    ["📊 Resumen & KPIs", "🤖 Asistente Datia", "🔍 Posibles Desfases", "⚠️ Gestión de Excepciones", "📋 POS", "💳 Datafast"]
)

with tab_resumen:
    mostrar_resumen(resultado)

with tab_agente:
    st.subheader("🤖 Diagnóstico de Investigación e Hipótesis")
    st.caption("Generación de hipótesis explicativas con Gemini 3.6 Flash (Sin asunción automática de pérdida)")

    if reporte_excepciones.empty:
        st.success("🎉 Cierre impecable: No hay discrepancias que requieran investigación.")
    else:
        if st.button("Generar Hipótesis de Cierre", type="primary"):
            with st.spinner("Analizando evidencias y patrones con Datia..."):
                resumen_texto = reporte_excepciones.to_string(index=False)
                diagnostico = generar_reporte_ia(resumen_texto)
                st.markdown(diagnostico)

with tab_desfases:
    st.subheader("🔍 Coincidencias Cruzadas por Monto (Detección de Desfases/Escribanía)")
    st.caption("Registros que no coincidieron por Número de Referencia pero comparten el mismo monto exacto.")
    if desfases_df.empty:
        st.info("No se hallaron coincidencias de monto cruzado entre las discrepancias.")
    else:
        st.success(f"Se hallaron {len(desfases_df)} relaciones por monto que podrían resolver discrepancias sin pérdida.")
        st.dataframe(desfases_df, use_container_width=True)

with tab_excepciones:
    st.subheader("⚠️ Registro y Confirmación Humana de Excepciones")
    st.write("Modifica la columna 'Resolución Administrador' para confirmar el destino final de cada caso:")

    if reporte_excepciones.empty:
        st.info("No hay excepciones para mostrar.")
    else:
        if "Resolución Administrador" not in reporte_excepciones.columns:
            reporte_excepciones["Resolución Administrador"] = "Pendiente de Investigación"

        df_editado = st.data_editor(
            reporte_excepciones,
            column_config={
                "Resolución Administrador": st.column_config.SelectboxColumn(
                    "Resolución Administrador",
                    help="Confirmación del usuario que realiza o supervisa el cierre",
                    options=[
                        "Pendiente de Investigación",
                        "Aclarado: Error de Digitación (Referencia)",
                        "Aclarado: Cambio a Efectivo en Caja",
                        "Aclarado: Lote de Turno Siguiente",
                        "Faltante Confirmado (Descuento Pistero)",
                        "Sobrante Confirmado",
                    ],
                    required=True,
                )
            },
            disabled=["id_referencia", "monto_pos", "monto_datafast", "diferencia", "tipo_error"],
            hide_index=True,
            use_container_width=True,
        )

        st.download_button(
            "📥 Descargar Reporte con Resoluciones Confirmadas (CSV)",
            data=df_editado.to_csv(index=False).encode("utf-8"),
            file_name="reporte_excepciones_confirmadas.csv",
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
