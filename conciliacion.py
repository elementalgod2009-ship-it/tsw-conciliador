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
        2. **INFORMACIÓN Y EVIDENCIA FALTANTE:** Especifica qué documentos o soportes debe revisar el administrador para confirmar o descartar cada hipótesis (ej. vauchers físicos, reporte de lote del turno nocturno, bitácora de caja chica).
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

    df = df[["id_referencia", "monto"]].copy()
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
        # Cruce buscando montos idénticos entre los registros no conciliados por id
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
