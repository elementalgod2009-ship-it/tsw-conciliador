import streamlit as st
import pandas as pd

from conciliacion import (
    normalizar_dataframe,
    leer_csv,
    concili_sistemas,
    generar_reporte_excepciones,
    generar_reporte_ia,
)

st.set_page_config(
    page_title="DATIA - Asistente Financiero para Gasolineras",
    layout="wide"
)

st.title("DATIA - Sistema de Conciliacion y Asistente Financiero")
st.markdown("Automatizacion de conciliacion POS vs Datafast con analisis inteligente para estaciones de servicio.")

# Barra lateral para la carga de archivos
st.sidebar.header("1. Carga de Datos")
archivo_pos = st.sidebar.file_uploader("Reporte de Ventas POS (CSV/Excel)", type=["csv", "xlsx"])
archivo_datafast = st.sidebar.file_uploader("Reporte Datafast / Tarjetas (CSV/Excel)", type=["csv", "xlsx"])

empresa_id = st.sidebar.text_input("ID de Empresa / Estacion", value="Estacion_Central_01")

if archivo_pos and archivo_datafast:
    try:
        if archivo_pos.name.endswith('.csv'):
            df_pos_raw = leer_csv(archivo_pos)
        else:
            df_pos_raw = pd.read_excel(archivo_pos)

        if archivo_datafast.name.endswith('.csv'):
            df_df_raw = leer_csv(archivo_datafast)
        else:
            df_df_raw = pd.read_excel(archivo_datafast)

        st.sidebar.success("Archivos cargados correctamente.")

        st.subheader("2. Mapeo de Columnas")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### POS (Pista)")
            cols_pos = df_pos_raw.columns.tolist()
            ref_pos = st.selectbox("Columna Referencia / Voucher (POS)", cols_pos, key="ref_pos")
            monto_pos = st.selectbox("Columna Monto (POS)", cols_pos, key="monto_pos")

        with col2:
            st.markdown("### Datafast / Procesador")
            cols_df = df_df_raw.columns.tolist()
            ref_df = st.selectbox("Columna Referencia / Voucher (Datafast)", cols_df, key="ref_df")
            monto_df = st.selectbox("Columna Monto (Datafast)", cols_df, key="monto_df")

        if st.button("Ejecutar Conciliacion y Auditoria", type="primary"):
            df_pos_norm = normalizar_dataframe(df_pos_raw, ref_pos, monto_pos, fuente="POS")
            df_df_norm = normalizar_dataframe(df_df_raw, ref_df, monto_df, fuente="Datafast")

            resultados = concili_sistemas(df_pos_norm, df_df_norm, tolerancia_max=0.01)
            
            st.session_state["resultados"] = resultados
            st.session_state["empresa_id"] = empresa_id
            
            excepciones = generar_reporte_excepciones(
                resultados["diferencias_monto"],
                resultados["solo_datafast"],
                resultados["solo_pos"]
            )
            st.session_state["reporte_excepciones"] = excepciones

            st.success("Conciliacion completada con exito.")

    except Exception as e:
        st.error(f"Ocurrio un error al procesar los archivos: {str(e)}")

# Seccion principal de resultados y chat interactivo
if "resultados" in st.session_state:
    res = st.session_state["resultados"]
    excepciones = st.session_state["reporte_excepciones"]

    tab1, tab2, tab3 = st.tabs(["Resumen y KPIs", "Excepciones", "Chat Financiero de Auditoria"])

    with tab1:
        st.subheader("Resumen General del Cierre")
        total_transacciones = len(res["cruce"])
        cuadradas = len(res["cuadran"])
        
        salud = round((cuadradas / total_transacciones * 100) if total_transacciones > 0 else 0, 2)
        monto_riesgo = excepciones["monto_pos"].sum() if "monto_pos" in excepciones.columns else 0.0

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Salud Financiera", f"{salud}%")
        kpi2.metric("Monto en Riesgo / Desfase", f"${monto_riesgo:,.2f}")
        kpi3.metric("Transacciones Procesadas", total_transacciones)

        st.dataframe(res["cruce"].head(20), use_container_width=True)

    with tab2:
        st.subheader("Detalle de Excepciones Detectadas")
        if not excepciones.empty:
            st.dataframe(excepciones, use_container_width=True)
            
            if st.button("Generar Diagnostico de IA sobre Excepciones"):
                with st.spinner("Analizando anomalias con IA..."):
                    diagnostico = generar_reporte_ia(excepciones.to_string())
                    st.session_state["diagnostico_ia"] = diagnostico
                st.markdown("### Diagnostico Operativo")
                st.write(diagnostico)
        else:
            st.info("No se encontraron excepciones. Cierre de caja perfecto.")

    with tab3:
        st.subheader("Asistente Conversacional (Chat Financiero)")
        st.markdown("Pregunte al sistema sobre los desfases, faltantes o el estado de la conciliacion en lenguaje natural.")

        if "mensajes_chat" not in st.session_state:
            st.session_state["mensajes_chat"] = []

        for mensaje in st.session_state["mensajes_chat"]:
            with st.chat_message(mensaje["role"]):
                st.markdown(mensaje["content"])

        pregunta_usuario = st.chat_input("Ej: Cuales son los desfases de esta semana o que paso con los faltantes?")

        if pregunta_usuario:
            st.session_state["mensajes_chat"].append({"role": "user", "content": pregunta_usuario})
            with st.chat_message("user"):
                st.markdown(pregunta_usuario)

            pregunta_lower = pregunta_usuario.lower()
            respuesta_sistema = ""

            if any(palabra in pregunta_lower for palabra in ["desfase", "error", "discrepancia", "faltante", "sobra"]):
                if not excepciones.empty:
                    total_exc = len(excepciones)
                    monto_tot = excepciones['monto_pos'].sum() if 'monto_pos' in excepciones.columns else 0
                    respuesta_sistema = f"Se han detectado {total_exc} registros con discrepancias financieras, representando un monto total de ${monto_tot:,.2f}. Las principales anomalias se concentran en diferencias de montos y transacciones huerfanas entre POS y Datafast."
                else:
                    respuesta_sistema = "No se han detectado desfases ni anomalias en las cuentas procesadas."
            elif any(palabra in pregunta_lower for palabra in ["salud", "resumen", "estado"]):
                respuesta_sistema = f"La salud financiera actual del cierre es de {salud}%, con un total de {total_transacciones} transacciones procesadas."
            else:
                with st.spinner("Consultando al asistente analitico..."):
                    contexto_datos = excepciones.to_string() if not excepciones.empty else "Sin excepciones."
                    prompt_chat = f"Basado en estos datos de conciliacion:\n{contexto_datos}\n\nResponde de forma profesional y ejecutiva a la pregunta del usuario: {pregunta_usuario}"
                    respuesta_sistema = generar_reporte_ia(prompt_chat)

            st.session_state["mensajes_chat"].append({"role": "assistant", "content": respuesta_sistema})
            with st.chat_message("assistant"):
                st.markdown(respuesta_sistema)

else:
    st.info("Por favor, cargue los archivos del POS y Datafast en la barra lateral para comenzar la conciliacion y activar el chat financiero.")
