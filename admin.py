
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

if "admin_logueado" not in st.session_state:
    st.session_state.admin_logueado = False

# ==========================================
# LOGIN
# ==========================================

def login_admin():

    st.set_page_config(
        page_title="Administrador AutoAccess",
        layout="wide"
    )

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
        "size": 20
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

def calcular_monto(
    entrada_minuto,
    minuto_actual
):

    try:

        entrada = int(
            float(entrada_minuto)
        )

        salida = int(
            float(minuto_actual)
        )

        minutos = max(
            salida - entrada,
            0
        )

        horas = max(
            round(minutos / 60),
            1
        )

        return horas * TARIFA_HORA

    except:

        return 0

# ==========================================
# DASHBOARD
# ==========================================

def dashboard():

    st.title(
        "📊 Panel Administrativo AutoAccess"
    )

    df = obtener_datos()

    if df.empty:
        return

    # ======================================
    # PROCESAR DATOS
    # ======================================

    fechas_ingreso = []
    horas_ingreso = []

    fechas_salida = []
    horas_salida = []

    montos = []

    for _, row in df.iterrows():

        fecha_in, hora_in = convertir_fecha(
            row.get(
                "entrada_minuto",
                0
            )
        )

        fecha_out, hora_out = convertir_fecha(
            row.get(
                "minuto_actual",
                0
            )
        )

        fechas_ingreso.append(
            fecha_in
        )

        horas_ingreso.append(
            hora_in
        )

        fechas_salida.append(
            fecha_out
        )

        horas_salida.append(
            hora_out
        )

        montos.append(
            calcular_monto(
                row.get(
                    "entrada_minuto",
                    0
                ),
                row.get(
                    "minuto_actual",
                    0
                )
            )
        )

    df["FechaIngreso"] = fechas_ingreso
    df["HoraIngreso"] = horas_ingreso

