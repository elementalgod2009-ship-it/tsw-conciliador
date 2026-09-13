"""Módulo de lógica de negocio, detección de hipótesis y conciliación para Datia / TSW Conciliador."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from google import genai
import pandas as pd
import streamlit as st


def generar_reporte_ia(datos_descuadre: str) -> str:
    """Llama a Gemini para generar un análisis basado en hipótesis explicativas y no punitivas."""
    api_key = st.secrets.get("GOOGLE_API_KEY")
    if not api_key:
        return (
            "⚠️ No se encontró la clave 'GOOGLE_API_KEY' configurada en st.secrets. "
            "Por favor, agrégala en la configuración de la aplicación en Streamlit Cloud."
        )

    try:
        client = genai.Client(
            api_key=api_key,
            vertexai=False,
        )

        prompt = f"""
        Actúa como un Asistente Analítico de Auditoría para Estaciones de Servicio (Datia).
        Analiza las siguientes excepciones de cierre encontradas entre el sistema POS de pista y el procesador de tarjetas (Datafast):

        {datos_descuadre}

        Genera un informe con enfoque de investigación operativa y NO PUNITIVO (no asumas automáticamente robo o pérdida). 
        Estructura la respuesta estrictamente en estos 3 bloques:

        1. **HIPÓTESIS DE ORIGEN:** Propón causas probables para las diferencias encontradas (ej. posible cambio de medio de pago a efectivo en caja, transacción procesada en el lote del día/turno siguiente, error de digitación en el POS).
        2. **INFORMACIÓN Y EVIDENCIA FALTANTE:** Especifica qué documentos o soportes debe revisar el administrador para confirmar o descartar cada hipótesis (ej. vouchers físicos, reporte de lote del turno nocturno, bitácora de caja chica).
        3. **PASOS RECOMENDADOS DE VERIFICACIÓN:** Acciones concretas paso a paso para que el usuario confirme la resolución sin generar fricción con el personal de pista.
        """

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"❌ Error al consultar el servicio de Inteligencia Artificial: {str(e)}"


def normalizar_dataframe(
    df_crudo: pd.DataFrame,
    mapeo_columnas: dict[str, str],
    fuente: str,
) -> pd.DataFrame:
    """Adapta las columnas de una fuente al formato común de conciliación."""
    df = df_crudo.rename(columns=mapeo_columnas).copy()
    columnas_requeridas = {"id_referencia", "monto"}
    faltantes = columnas_requeridas - set(df.columns)
    if faltantes:
        faltantes_texto = ", ".join(sorted(faltantes))
        raise ValueError(
            f"Faltan columnas requeridas en {fuente}: {faltantes_texto}"
        )

    # Conservamos columnas auxiliares de filtro si existen en el dataframe crudo
    cols_a_preservar = ["id_referencia", "monto"]
    if "Hora" in df_crudo.columns:
        df["Hora"] = df_crudo["Hora"].astype(str)
        cols_a_preservar.append("Hora")
    if "Surtidor" in df_crudo.columns:
        df["Surtidor"] = df_crudo["Surtidor"].astype(str)
        cols_a_preservar.append("Surtidor")

    df = df[cols_a_preservar].copy()
    df["id_referencia"] = df["id_referencia"].astype("string").str.strip()
    df["monto"] = pd.to_numeric(
        df["monto"]
        .astype("string")
        .str.replace(r"[\$,]", "", regex=True)
        .str.strip(),
        errors="coerce",
    )
    df["fuente"] = fuente
    return df


def leer_csv(
    archivo: str | Path | Any,
    mapeo_columnas: dict[str, str],
    fuente: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lee un CSV y devuelve sus filas originales y su versión normalizada."""
    df_crudo = pd.read_csv(archivo)
    df_normalizado = normalizar_dataframe(df_crudo, mapeo_columnas, fuente)
    return df_crudo, df_normalizado


def conciliar_sistemas(
    df_pos: pd.DataFrame,
    df_datafast: pd.DataFrame,
    tolerancia_max: float = 0.0,
) -> dict[str, pd.DataFrame]:
    """Cruza POS y Datafast e identifica coincidencias y excepciones."""
    cruce = pd.merge(
        df_pos,
        df_datafast,
        on="id_referencia",
        how="outer",
        suffixes=("_pos", "_datafast"),
    )

    solo_datafast = cruce[cruce["monto_pos"].isna()].copy()
    solo_pos = cruce[cruce["monto_datafast"].isna()].copy()

    coincidentes = cruce.dropna(
        subset=["monto_pos", "monto_datafast"]
    ).copy()
    coincidentes["diferencia"] = (
        coincidentes["monto_pos"] - coincidentes["monto_datafast"]
    ).abs()

    diferencias_monto = coincidentes[
        coincidentes["diferencia"] > tolerancia_max
    ].copy()
    cuadran = coincidentes[
        coincidentes["diferencia"] <= tolerancia_max
    ].copy()

    return {
        "cruce": cruce,
        "cuadran": cuadran,
        "diferencias_monto": diferencias_monto,
        "solo_datafast": solo_datafast,
        "solo_pos": solo_pos,
    }


def detectar_posibles_desfases(
    solo_pos: pd.DataFrame, solo_datafast: pd.DataFrame
) -> pd.DataFrame:
    """Detecta coincidencias por monto idéntico que podrían sugerir un error de referencia o desfase de lote."""
    posibles_desfases = []

    if not solo_pos.empty and not solo_datafast.empty:
        cruce_monto = pd.merge(
            solo_pos[["id_referencia", "monto_pos"]],
            solo_datafast[["id_referencia", "monto_datafast"]],
            left_on="monto_pos",
            right_on="monto_datafast",
            suffixes=("_pos", "_datafast"),
        )

        for _, row in cruce_monto.iterrows():
            posibles_desfases.append({
                "Ref_POS": row["id_referencia_pos"],
                "Ref_Datafast": row["id_referencia_datafast"],
                "Monto Coincidente ($)": row["monto_pos"],
                "Hipótesis Suministrada": "Posible error de digitación de referencia o desfase de cierre de lote"
            })

    return pd.DataFrame(posibles_desfases)


def generar_reporte_excepciones(
    diferencias_monto: pd.DataFrame,
    solo_datafast: pd.DataFrame,
    solo_pos: pd.DataFrame,
) -> pd.DataFrame:
    """Unifica las excepciones en un reporte descargable."""
    excepciones: list[pd.DataFrame] = []

    if not diferencias_monto.empty:
        diferencias = diferencias_monto.copy()
        diferencias["tipo_error"] = "Diferencia en monto"
        excepciones.append(diferencias)

    if not solo_datafast.empty:
        datafast = solo_datafast.copy()
        datafast["tipo_error"] = "Sobra en Datafast (Sin registro en POS)"
        excepciones.append(datafast)

    if not solo_pos.empty:
        pos = solo_pos.copy()
        pos["tipo_error"] = "Falta en Datafast (Registrado en POS)"
        excepciones.append(pos)

    if not excepciones:
        return pd.DataFrame(
            columns=[
                "id_referencia",
                "monto_pos",
                "monto_datafast",
                "diferencia",
                "tipo_error",
            ]
        )

    return pd.concat(excepciones, ignore_index=True)


def generar_html_reporte_ejecutivo(
    salud_financiera: float,
    monto_riesgo: float,
    total_reg: int,
    reporte_excepciones: pd.DataFrame,
    diagnostico_ia: str = ""
) -> str:
    """Genera una plantilla HTML profesional lista para imprimir como PDF o enviar como informe."""
    filas_html = ""
    if not reporte_excepciones.empty:
        for _, row in reporte_excepciones.iterrows():
            ref = row.get("id_referencia", "N/A")
            m_pos = f"${row.get('monto_pos', 0):,.2f}" if pd.notna(row.get('monto_pos')) else "-"
            m_df = f"${row.get('monto_datafast', 0):,.2f}" if pd.notna(row.get('monto_datafast')) else "-"
            tipo = row.get("tipo_error", "Excepción")
            res = row.get("Resolución Administrador", "Pendiente")
            filas_html += f"<tr><td>{ref}</td><td>{m_pos}</td><td>{m_df}</td><td>{tipo}</td><td><strong>{res}</strong></td></tr>"
    else:
        filas_html = "<tr><td colspan='5' style='text-align:center;'>Sin excepciones registradas. Cierre perfecto.</td></tr>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Reporte de Auditoría Datia</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 30px; color: #1E293B; }}
            .header {{ border-bottom: 3px solid #2563EB; padding-bottom: 10px; margin-bottom: 20px; }}
            .title {{ font-size: 24px; font-weight: bold; color: #0F172A; }}
            .subtitle {{ font-size: 14px; color: #64748B; }}
            .kpi-container {{ display: flex; gap: 20px; margin-bottom: 25px; }}
            .kpi-card {{ background: #F8FAFC; border: 1px solid #E2E8F0; padding: 15px; border-radius: 8px; flex: 1; }}
            .kpi-title {{ font-size: 12px; color: #64748B; text-transform: uppercase; }}
            .kpi-value {{ font-size: 22px; font-weight: bold; color: #1E293B; margin-top: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ border: 1px solid #CBD5E1; padding: 10px; text-align: left; font-size: 13px; }}
            th {{ background-color: #F1F5F9; font-weight: bold; }}
            .ia-box {{ background: #EFF6FF; border-left: 4px solid #2563EB; padding: 15px; margin-top: 25px; font-size: 13px; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">⛽ Datia — Informe Oficial de Cierre de Caja</div>
            <div class="subtitle">Auditoría Operativa y Conciliación de Tarjetas | Estación de Servicio</div>
        </div>

        <div class="kpi-container">
            <div class="kpi-card">
                <div class="kpi-title">Salud Financiera</div>
                <div class="kpi-value">{salud_financiera}%</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Monto a Investigar</div>
                <div class="kpi-value" style="color: #DC2626;">${monto_riesgo:,.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-title">Transacciones Procesadas</div>
                <div class="kpi-value">{total_reg} reg</div>
            </div>
        </div>

        <h3>⚠️ Detalle de Excepciones y Resoluciones</h3>
        <table>
            <thead>
                <tr>
                    <th>Referencia</th>
                    <th>Monto POS</th>
                    <th>Monto Datafast</th>
                    <th>Tipo Anomalía</th>
                    <th>Resolución Administrador</th>
                </tr>
            </thead>
            <tbody>
                {filas_html}
            </tbody>
        </table>

        {f'<div class="ia-box"><h4>🤖 Diagnóstico del Agente Analítico</h4><p>{diagnostico_ia.replace(chr(10), "<br>")}</p></div>' if diagnostico_ia else ''}

        <br><br>
        <p style="font-size: 11px; color: #94A3B8; text-align: center;">Generado automáticamente por Datia - Asistente de Auditoría para Gasolineras.</p>
    </body>
    </html>
    """
    return html

