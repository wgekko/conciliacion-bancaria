import streamlit as st
import pandas as pd
import io
import numpy as np
from datetime import datetime
import plotly.express as px

st.set_page_config(page_title="Conciliación Bancaria", page_icon="img/banco1.png", layout="centered")

def cargar_estilos():
    with open("asset/style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

cargar_estilos()

def show_logo():
    st.image("img/banco.gif", width=50)

def show_logo_uno():
    st.image("img/conciliar.gif", width=50)

show_logo()
st.title("Conciliación Bancaria Automática")

# --- Funciones auxiliares ---
def cargar_archivo(file):
    ext = file.name.split(".")[-1].lower()
    if ext == "csv":
        return pd.read_csv(file, header=None)
    else:
        return pd.read_excel(file, header=None, engine="xlrd" if ext == "xls" else "openpyxl")

def detectar_fila_encabezado(df):
    for i in range(10):
        if df.iloc[i].notna().sum() >= 2:
            return i
    return 0

def convertir_a_fecha(col):
    try:
        return pd.to_datetime(col, errors='coerce')
    except:
        return col

def normalizar_dataframe(df_original, origen):
    fila_header = detectar_fila_encabezado(df_original)
    df = df_original.iloc[fila_header+1:].copy()
    df.columns = df_original.iloc[fila_header].astype(str).str.strip().str.lower()

    posibles_debito = ["débito", "debito", "debe", "Débito", "Debito"]
    posibles_credito = ["crédito", "credito", "haber", "Crédito", "Credito"]

    col_debito = next((col for col in df.columns if any(p in col for p in posibles_debito)), None)
    col_credito = next((col for col in df.columns if any(p in col for p in posibles_credito)), None)
    col_fecha = next((col for col in df.columns if "fecha" in col), None)

    if not col_debito or not col_credito:
        st.error(f"No se detectaron columnas de Débito o Crédito en el archivo de {origen}. Columnas disponibles: {list(df.columns)}")
        return None

    df[col_debito] = pd.to_numeric(df[col_debito], errors='coerce').fillna(0)
    df[col_credito] = pd.to_numeric(df[col_credito], errors='coerce').fillna(0)
    df['importe'] = (df[col_credito] - df[col_debito]).round(2)

    if col_fecha:
        df['fecha'] = convertir_a_fecha(df[col_fecha])
    else:
        df['fecha'] = pd.NaT

    df['__origen__'] = origen
    df['referencia'] = df.apply(lambda row: str(row.to_dict()), axis=1)
    return df[['importe', 'fecha', 'referencia', '__origen__']]

def conciliar(banco_df, sistema_df):
    coincidencias = pd.merge(banco_df, sistema_df, on='importe', how='inner').drop_duplicates(subset=['importe'])
    banco_sin = banco_df[~banco_df['importe'].isin(coincidencias['importe'])]
    sistema_sin = sistema_df[~sistema_df['importe'].isin(coincidencias['importe'])]
    return coincidencias, banco_sin, sistema_sin

def detectar_conciliaciones_parciales(banco_df, sistema_df):
    parciales = []
    for i, row in banco_df.iterrows():
        target = row['importe']
        subset = sistema_df.copy()
        for r in range(1, len(subset)+1):
            comb = subset.iloc[:r]
            if np.isclose(comb['importe'].sum(), target, atol=0.01):
                parciales.append((row.to_dict(), comb.to_dict(orient='records')))
                break
    return parciales

# Archivo completo (incluye coincidencias)
def generar_excel(coincidencias, faltantes_banco, faltantes_sistema, parciales):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        coincidencias.to_excel(writer, sheet_name='Coincidencias', index=False)
        faltantes_sistema.to_excel(writer, sheet_name='Faltantes en Contabilidad', index=False)
        faltantes_banco.to_excel(writer, sheet_name='Faltantes en Banco', index=False)
        if parciales:
            parcial_rows = []
            for base, subconjunto in parciales:
                for item in subconjunto:
                    parcial_rows.append({
                        "Movimiento Banco": str(base),
                        "Coincidencia Parcial Sistema": str(item)
                    })
            df_parciales = pd.DataFrame(parcial_rows)
            df_parciales.to_excel(writer, sheet_name='Conciliaciones parciales', index=False)
    output.seek(0)
    return output

# Archivo solo con diferencias
def generar_excel_diferencias(faltantes_banco, faltantes_sistema):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Hoja con movimientos que están en el sistema pero no en el banco
        faltantes_banco.to_excel(writer, sheet_name='Faltantes en Banco', index=False)

        # Hoja con movimientos que están en el banco pero no en el sistema
        faltantes_sistema.to_excel(writer, sheet_name='Faltantes en Sistema', index=False)
    
    output.seek(0)
    return output

def mostrar_dashboard_resumen(coincidencias, total_banco, total_sistema):
    total_conciliado = len(coincidencias)
    total_transacciones = total_banco + total_sistema
    porcentaje = 100 * total_conciliado / total_transacciones if total_transacciones else 0
    st.metric("✅ Porcentaje conciliado", f"{porcentaje:.2f}%")
    fig = px.pie(
        names=["Conciliadas", "Coincidencias"],
        values=[total_conciliado, total_transacciones - total_conciliado],
        title="Resumen de conciliación",
        color_discrete_sequence=["green", "red"]
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Interfaz ---
st.markdown("Sube tus archivos del banco y del sistema contable para realizar la conciliación.")
st.warning("IMPORTANTE - el archivo de excel debe tener el siguiente el encabezado fecha, detalle/descripción, débito, crédito, saldo - antes de estos nombres de las columnas no debe haber ningun texto o datos, porque la app puede dar error al momento de ejecutar la búsqueda de diferencias #preferentemente con extensión xlsx#")

archivo_banco = st.file_uploader("📁 Subir archivo del **Banco**", type=['csv', 'xls', 'xlsx'])
archivo_sistema = st.file_uploader("📁 Subir archivo del **Sistema Contable**", type=['csv', 'xls', 'xlsx'])

with st.container(border=True):
    st.write("Opciones de filtrado por fecha para realizar una conciliación parcial:")
    fecha_inicio = st.date_input("📅 Fecha desde", value=None)
    fecha_fin = st.date_input("📅 Fecha hasta", value=None)

if archivo_banco and archivo_sistema:
    try:
        df_banco_raw = cargar_archivo(archivo_banco)
        df_sistema_raw = cargar_archivo(archivo_sistema)

        banco_df = normalizar_dataframe(df_banco_raw, "Banco")
        sistema_df = normalizar_dataframe(df_sistema_raw, "Sistema Contable")

        if banco_df is not None and sistema_df is not None:
            if pd.notnull(fecha_inicio):
                banco_df = banco_df[banco_df['fecha'] >= pd.to_datetime(fecha_inicio)]
                sistema_df = sistema_df[sistema_df['fecha'] >= pd.to_datetime(fecha_inicio)]
            if pd.notnull(fecha_fin):
                banco_df = banco_df[banco_df['fecha'] <= pd.to_datetime(fecha_fin)]
                sistema_df = sistema_df[sistema_df['fecha'] <= pd.to_datetime(fecha_fin)]

            coincidencias, falt_banco, falt_sistema = conciliar(banco_df, sistema_df)
            show_logo_uno()
            st.success("✅ Conciliación realizada con éxito.")
            st.write("### Coincidencias encontradas", coincidencias)
            st.write("### Faltantes en sistema contable", falt_banco)
            st.write("### Faltantes en banco", falt_sistema)

            mostrar_dashboard_resumen(coincidencias, len(banco_df), len(sistema_df))

            st.write("### 🔍 Conciliaciones parciales detectadas")
            parciales = detectar_conciliaciones_parciales(falt_banco, falt_sistema)
            if parciales:
                for base, subconjunto in parciales:
                    st.write("**Movimiento banco:**", base)
                    st.write("**Coincidencia parcial en sistema:**", subconjunto)
                    st.markdown("---")
            else:
                st.info("No se detectaron conciliaciones parciales.")

            # Botón para descargar informe completo
            excel_output_completo = generar_excel(coincidencias, falt_banco, falt_sistema, parciales)
            st.download_button(
                label="Descargar informe completo",
                data=excel_output_completo,
                file_name="informe_conciliacion.xlsx",
                icon=":material/download:",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Botón para descargar solo diferencias
            excel_output_diferencias = generar_excel_diferencias(falt_banco, falt_sistema)
            st.download_button(
                label="Descargar solo diferencias",
                data=excel_output_diferencias,
                file_name="solo_diferencias.xlsx",
                icon=":material/download:",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"❌ Error al procesar los archivos: {str(e)}")

# --------------- footer -----------------------------

st.write("---")
with st.container():
  #st.write("---")
  st.write("&copy; - derechos reservados -  2024 -  Walter Gómez - FullStack Developer - Data Science - Business Intelligence")
  #st.write("##")
  left, right = st.columns(2, gap='medium', vertical_alignment="bottom")
  with left:
    #st.write('##')
    st.link_button("Mi LinkedIn", "https://www.linkedin.com/in/walter-gomez-fullstack-developer-datascience-businessintelligence-finanzas-python/",use_container_width=True)
  with right: 
     #st.write('##') 
    st.link_button("Mi Porfolio", "https://walter-portfolio-animado.netlify.app/", use_container_width=True)
      