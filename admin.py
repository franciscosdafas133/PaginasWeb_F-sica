
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# ==========================================
# CONFIGURACION BASEROW
# ==========================================

BASEROW_TOKEN = "hVxGMBTks1fAopHga6Vqm2BKi2H5gnQj"
TABLE_ID = "1032007"

HEADERS = {
    "Authorization": f"Token {BASEROW_TOKEN}"
}

# ==========================================
# CONFIGURACION PAGOS
# ==========================================

TARIFA_HORA = 4

# ==========================================
# LOGIN ADMIN
# ==========================================

ADMIN_USER = "AUTOACCESS"
ADMIN_PASS = "FISICA2026"

# ==========================================
# LOGIN
# ==========================================

def login_admin():

    st.title("🔐 Acceso Administrador")

    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):

        if (
            usuario == ADMIN_USER
            and
            password == ADMIN_PASS
        ):
            st.session_state.admin_logueado = True
            st.rerun()

        else:
            st.error("Credenciales incorrectas")

# ==========================================
# OBTENER DATOS BASEROW
# ==========================================

def obtener_datos():

    url = (
        f"https://api.baserow.io/api/database/rows/table/"
        f"{TABLE_ID}/"
    )

    params = {
        "user_field_names": "true",
        "size": 200
    }

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=20
        )

        if r.status_code != 200:
            st.error(
                f"Error Baserow: {r.status_code}"
            )
            return pd.DataFrame()

        return pd.DataFrame(
            r.json()["results"]
        )

    except Exception as e:

        st.error(
            f"Error de conexión: {e}"
        )

        return pd.DataFrame()

# ==========================================
# CONVERTIR MINUTOS EPOCH
# ==========================================

def convertir_fecha(minuto_epoch):

    try:

        minuto_epoch = int(
            float(minuto_epoch)
        )

        fecha = datetime.fromtimestamp(
            minuto_epoch * 60
        )

        return (
            fecha.strftime("%d/%m/%Y"),
            fecha.strftime("%H:%M")
        )

    except:

        return "-", "-"

# ==========================================
# CALCULAR MONTO
# ==========================================

def calcular_monto(entrada_minuto, minuto_actual):

    try:

        entrada = int(float(entrada_minuto))
        salida = int(float(minuto_actual))
        minutos = max(salida - entrada, 0)
        horas = max(round(minutos / 60), 1)
        return horas * TARIFA_HORA

    except:

        return 0

# ==========================================
# DASHBOARD
# ==========================================

def dashboard():

    st.title("📊 Panel Administrativo AutoAccess")

    if st.button("Cerrar sesión"):
        st.session_state.admin_logueado = False
        st.rerun()

    df = obtener_datos()

    if df.empty:
        st.warning("No se encontraron datos en Baserow.")
        return

    # ======================================
    # PROCESAR DATOS
    # ======================================

    fechas_ingreso = []
    horas_ingreso = []
    fechas_salida = []
    horas_salida = []
    montos = []

    campo_entrada = None
    campo_salida = None

    for col in df.columns:
        col_lower = col.lower().replace(" ", "_")
        if "entrada" in col_lower:
            campo_entrada = col
        if "minuto_actual" in col_lower or "salida" in col_lower:
            campo_salida = col

    for _, row in df.iterrows():

        fecha_in, hora_in = convertir_fecha(
            row.get(campo_entrada, 0) if campo_entrada else 0
        )
        fecha_out, hora_out = convertir_fecha(
            row.get(campo_salida, 0) if campo_salida else 0
        )

        fechas_ingreso.append(fecha_in)
        horas_ingreso.append(hora_in)
        fechas_salida.append(fecha_out)
        horas_salida.append(hora_out)
        montos.append(
            calcular_monto(
                row.get(campo_entrada, 0) if campo_entrada else 0,
                row.get(campo_salida, 0) if campo_salida else 0
            )
        )

    df["Fecha Ingreso"] = fechas_ingreso
    df["Hora Ingreso"] = horas_ingreso
    df["Fecha Salida"] = fechas_salida
    df["Hora Salida"] = horas_salida
    df["Monto (S/)"] = montos

    # ======================================
    # MÉTRICAS
    # ======================================

    total_registros = len(df)
    total_recaudado = sum(montos)

    col1, col2 = st.columns(2)
    col1.metric("Total registros", total_registros)
    col2.metric("Total recaudado", f"S/ {total_recaudado:.2f}")

    # ======================================
    # GRÁFICA INGRESOS POR FECHA
    # ======================================

    df_grafica = df[df["Fecha Ingreso"] != "-"].copy()

    if not df_grafica.empty:
        conteo = (
            df_grafica.groupby("Fecha Ingreso")
            .size()
            .reset_index(name="Vehículos")
        )
        fig = px.bar(
            conteo,
            x="Fecha Ingreso",
            y="Vehículos",
            title="Vehículos por día",
            color_discrete_sequence=["#636EFA"]
        )
        st.plotly_chart(fig, use_container_width=True)

    # ======================================
    # TABLA DE REGISTROS
    # ======================================

    st.subheader("Registros")

    columnas_mostrar = ["id", "Fecha Ingreso", "Hora Ingreso",
                        "Fecha Salida", "Hora Salida", "Monto (S/)"]
    columnas_existentes = [c for c in columnas_mostrar if c in df.columns]

    st.dataframe(df[columnas_existentes], use_container_width=True)


# ==========================================
# ENTRY POINT
# ==========================================

st.set_page_config(
    page_title="Administrador AutoAccess",
    layout="wide"
)

if "admin_logueado" not in st.session_state:
    st.session_state.admin_logueado = False

if st.session_state.admin_logueado:
    dashboard()
else:
    login_admin()
