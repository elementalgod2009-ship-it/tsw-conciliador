"""Aplicación Streamlit para la conciliación diaria y auditoría con Datia (Mapeo Dinámico y Robustez)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from conciliacion import (
    conciliar_sistemas,
    detectar_posibles_desfases,
    generar_html_reporte_ejecutivo,
    generar_reporte_excepciones,
    generar_reporte_ia,
    leer_csv,
    normalizar_dataframe,
)


def datos_de_ejemplo() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve datos de demostración inspirados en los casos de Portete."""
    pos = pd.DataFrame(
        {
            "Ticket_No": ["T-1001", "T-1002", "T-1003", "T-1004", "T-1005", "T-1006"],
            "Fecha": ["2026-09-12"] * 6,
            "Hora": ["08:15", "09:30", "11:45", "14:10", "16:40", "20:05"],
            "Surtidor": ["Surtidor 01", "Surtidor 02", "Surtidor 01", "Surtidor 03", "Surtidor 02", "Surtidor 01"],
            "Metodo_Pago": ["Tarjeta"] * 5 + ["Efectivo"],
            "Monto_Total": [500.00, 100.00, 50.00, 75.50, 42.00, 25.00],
        }
    )
    datafast = pd.DataFrame(
        {
            "Num_Autorizacion": ["T-1001", "T-1002", "T-1004", "T-9988", "T-9999"],
            "Fecha_Proceso": ["2026-09-12"] * 5,
            "Hora": ["08:15", "09:30", "14:10", "16:40", "22:00"],
            "Valor_Liquidado": [480.00, 100.00, 75.50, 42.00, 200.00],
        }
    )
    return pos, datafast


def mostrar_resumen(resultado: dict[str, pd.DataFrame]) -> tuple[float, float, int]:
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

    return pct_salud, monto_riesgo_total, total_registros


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

st.title("⛽ Datia: Asistente de Auditoría de Cierre de Caja")
st.caption("Plataforma de investigación operativa basada en evidencia para Estaciones de Servicio")

with st.sidebar:
    st.header("⚙️ Configuración & Fuentes")
    usar_ejemplos = st.checkbox("Usar datos de ejemplo (Escenario Portete)", value=True)

    if usar_ejemplos:
        pos_crudo, datafast_crudo = datos_de_ejemplo()
    else:
        archivo_pos = st.file_uploader("Archivo de ventas POS (Pista)", type=["csv"])
        archivo_datafast = st.file_uploader("Archivo de liquidaciones Datafast", type=["csv"])

        if archivo_pos and archivo_datafast:
            pos_crudo = leer_csv(archivo_pos)
            datafast_crudo = leer_csv(archivo_datafast)
        else:
            st.info("👋 Carga ambos archivos CSV para comenzar.")
            st.stop()

    st.divider()
    st.header("🔀 Mapeo de Columnas")

    cols_pos = list(pos_crudo.columns)
    idx_ref_pos = cols_pos.index("Ticket_No") if "Ticket_No" in cols_pos else 0
    idx_monto_pos = cols_pos.index("Monto_Total") if "Monto_Total" in cols_pos else (1 if len(cols_pos) > 1 else 0)

    pos_col_ref = st.selectbox("POS: Columna Referencia/Ticket", cols_pos, index=idx_ref_pos)
    pos_col_monto = st.selectbox("POS: Columna Monto", cols_pos, index=idx_monto_pos)

    cols_df = list(datafast_crudo.columns)
    idx_ref_df = cols_df.index("Num_Autorizacion") if "Num_Autorizacion" in cols_df else 0
    idx_monto_df = cols_df.index("Valor_Liquidado") if "Valor_Liquidado" in cols_df else (1 if len(cols_df) > 1 else 0)

    df_col_ref = st.selectbox("Datafast: Columna Autorización", cols_df, index=idx_ref_df)
    df_col_monto = st.selectbox("Datafast: Columna Monto", cols_df, index=idx_monto_df)

    tolerancia = st.number_input("Tolerancia máxima ($)", min_value=0.0, value=0.0, step=0.01, format="%.2f")

# Normalización con el mapeo dinámico
pos_norm = normalizar_dataframe(pos_crudo, pos_col_ref, pos_col_monto, "POS")
datafast_norm = normalizar_dataframe(datafast_crudo, df_col_ref, df_col_monto, "Datafast")

# --- FILTROS OPERATIVOS EN SIDEBAR ---
with st.sidebar:
    st.divider()
    st.header("🎯 Filtros Operativos")
    
    surtidores = ["Todos"]
    if "Surtidor" in pos_norm.columns:
        surtidores += sorted(pos_norm["Surtidor"].dropna().unique().tolist())
    surtidor_sel = st.selectbox("Filtrar por Surtidor/Isla", surtidores)

    if surtidor_sel != "Todos":
        pos_norm = pos_norm[pos_norm["Surtidor"] == surtidor_sel].copy()

resultado = conciliar_sistemas(pos_norm, datafast_norm, tolerancia_max=tolerancia)

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
tab_resumen, tab_agente, tab_desfases, tab_excepciones, tab_export, tab_pos, tab_datafast = st.tabs(
    ["📊 Resumen & KPIs", "🤖 Asistente Datia", "🔍 Posibles Desfases", "⚠️ Gestión de Excepciones", "📄 Reporte Imprimible", "📋 POS", "💳 Datafast"]
)

with tab_resumen:
    pct_salud, monto_riesgo, total_reg = mostrar_resumen(resultado)

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
                st.session_state["diagnostico_ia"] = diagnostico

        if "diagnostico_ia" in st.session_state:
            st.markdown(st.session_state["diagnostico_ia"])

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
        st.session_state["df_editado"] = df_editado

        st.download_button(
            "📥 Descargar Reporte con Resoluciones Confirmadas (CSV)",
            data=df_editado.to_csv(index=False).encode("utf-8"),
            file_name="reporte_excepciones_confirmadas.csv",
            mime="text/csv",
            use_container_width=True,
        )

with tab_export:
    st.subheader("📄 Generación de Reporte Ejecutivo Imprimible")
    st.caption("Descarga una hoja de auditoría oficial en formato HTML lista para imprimir como PDF o enviar por WhatsApp/Correo.")

    df_para_html = st.session_state.get("df_editado", reporte_excepciones)
    diag_ia_para_html = st.session_state.get("diagnostico_ia", "")

    html_reporte = generar_html_reporte_ejecutivo(
        salud_financiera=pct_salud,
        monto_riesgo=monto_riesgo,
        total_reg=total_reg,
        reporte_excepciones=df_para_html,
        diagnostico_ia=diag_ia_para_html
    )

    st.download_button(
        "📥 Descargar Informe Ejecutivo (HTML / PDF)",
        data=html_reporte,
        file_name="Informe_Ejecutivo_Datia.html",
        mime="text/html",
        use_container_width=True,
        type="primary"
    )

    st.divider()
    st.write("👀 **Vista previa del Informe:**")
    st.components.v1.html(html_reporte, height=500, scrolling=True)

with tab_pos:
    mostrar_tabla(
        "Ventas cargadas del POS",
        pos_crudo,
        "No hay ventas POS cargadas.",
    )

with tab_datafast:
    mostrar_tabla(
        "Liquidaciones cargadas de Datafast",
        datafast_crudo,
        "No hay liquidaciones Datafast cargadas.",
    )
