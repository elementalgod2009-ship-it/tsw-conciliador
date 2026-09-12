from google import genai
import streamlit as st

def generar_reporte_ia(datos_descuadre):
    client = genai.Client(
        api_key=st.secrets["GOOGLE_API_KEY"],
        vertexai=False
    )

    prompt = f"""
    Actúa como un Auditor Financiero de Estaciones de Servicio.
    Analiza las siguientes discrepancias detectadas en el cierre:
    {datos_descuadre}

    Proporciona un reporte ejecutivo y serio estructurado únicamente en:
    1. HALLAZGO PRINCIPAL
    2. RIESGO FINANCIERO
    3. PROTOCOLO DE REVISIÓN
    """

    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=prompt,
    )
    return response.text


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
    """Cruza POS y Datafast y clasifica cada excepción."""
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
        datafast["tipo_error"] = "Sobra en Datafast"
        excepciones.append(datafast)

    if not solo_pos.empty:
        pos = solo_pos.copy()
        pos["tipo_error"] = "Falta en Datafast"
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
