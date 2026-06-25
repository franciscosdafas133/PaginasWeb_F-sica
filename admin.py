import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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

# Zona horaria del proyecto. Esto evita que Streamlit Cloud muestre
# la hora UTC en vez de la hora local de Perú.
ZONA_HORARIA = ZoneInfo("America/Lima")

# ==========================================
# LOGIN ADMIN
# ==========================================

ADMIN_USER = "AUTOACCESS"
ADMIN_PASS = "FISICA2026"

if "admin_logueado" not in st.session_state:
    st.session_state.admin_logueado = False

if "vista_grafico" not in st.session_state:
    st.session_state.vista_grafico = "semana"

if "vista_metrica" not in st.session_state:
    st.session_state.vista_metrica = "autos"

# ==========================================
# CSS PERSONALIZADO
# ==========================================

def aplicar_estilos():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
        .stApp { background-color: #F5F5F7; }
        section[data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E8E8ED;
        }
        .titulo-dashboard { font-size:28px; font-weight:700; color:#1C1C1E; margin-bottom:4px; }
        .subtitulo-dashboard { font-size:14px; color:#8E8E93; margin-bottom:24px; }
        .kpi-card {
            background:#FFFFFF; border-radius:16px; padding:24px;
            box-shadow:0 2px 8px rgba(0,0,0,0.06); height:140px;
            display:flex; flex-direction:column; justify-content:space-between;
            border:1px solid #F0F0F5;
        }
        .kpi-card-accent {
            background:#C8FF00; border-radius:16px; padding:24px;
            box-shadow:0 4px 16px rgba(200,255,0,0.30); height:140px;
            display:flex; flex-direction:column; justify-content:space-between;
        }
        .kpi-label { font-size:12px; font-weight:600; color:#8E8E93; text-transform:uppercase; letter-spacing:0.08em; }
        .kpi-label-dark { font-size:12px; font-weight:600; color:#3A3A2E; text-transform:uppercase; letter-spacing:0.08em; }
        .kpi-value { font-size:32px; font-weight:700; color:#1C1C1E; line-height:1; }
        .kpi-value-dark { font-size:32px; font-weight:700; color:#1C1C1E; line-height:1; }
        .kpi-sub { font-size:12px; color:#8E8E93; }
        .kpi-sub-dark { font-size:12px; color:#3A3A2E; }
        .seccion-titulo { font-size:16px; font-weight:600; color:#1C1C1E; margin-bottom:12px; margin-top:8px; }
        .stButton > button {
            border-radius:10px !important; font-weight:600 !important;
            font-size:13px !important; padding:8px 20px !important;
            border:none !important;
        }
        hr { border:none; border-top:1px solid #E8E8ED; margin:24px 0; }
    </style>
    """, unsafe_allow_html=True)


# ==========================================
# LOGIN
# ==========================================

def login_admin():
    st.set_page_config(page_title="AutoAccess — Admin", page_icon="🚗", layout="centered")
    aplicar_estilos()

    st.markdown("""
    <div style="text-align:center; padding:60px 0 32px 0;">
        <div style="font-size:48px">🚗</div>
        <div style="font-size:26px; font-weight:700; color:#1C1C1E; margin-top:12px;">AutoAccess</div>
        <div style="font-size:14px; color:#8E8E93; margin-top:4px;">Panel Administrativo</div>
    </div>
    """, unsafe_allow_html=True)

    usuario  = st.text_input("Usuario", placeholder="Ingresa tu usuario")
    password = st.text_input("Contraseña", type="password", placeholder="Ingresa tu contraseña")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("Ingresar →", use_container_width=True):
        if usuario == ADMIN_USER and password == ADMIN_PASS:
            st.session_state.admin_logueado = True
            st.rerun()
        else:
            st.error("Credenciales incorrectas.")


# ==========================================
# OBTENER DATOS BASEROW
# ==========================================

def obtener_datos():
    url = f"https://api.baserow.io/api/database/rows/table/{TABLE_ID}/"
    params = {"user_field_names": "true", "size": 200}

    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        if r.status_code != 200:
            st.error(f"Error Baserow: {r.status_code}")
            return pd.DataFrame()
        return pd.DataFrame(r.json()["results"])
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame()


# ==========================================
# HELPERS DE FECHA — reciben minutos Unix desde Raspberry
# y usan listas, nunca apply sobre datetime de pandas
# ==========================================

def epoch_a_dt(valor):
    """
    Minutos Unix → datetime Python nativo.

    La Raspberry guarda entrada_minuto y minuto_actual con:
        int(time.time() // 60)

    Por eso, antes de convertir a fecha, se multiplica por 60
    para recuperar los segundos Unix.
    """
    try:
        minutos_epoch = int(float(valor))
        if minutos_epoch <= 0:
            return None

        segundos_epoch = minutos_epoch * 60

        # Se convierte explícitamente a la hora de Perú y después se deja
        # como datetime sin zona para mantener compatibles los filtros actuales.
        return datetime.fromtimestamp(
            segundos_epoch,
            tz=ZONA_HORARIA
        ).replace(tzinfo=None)
    except Exception:
        return None


def fmt_fecha(dt):
    try:
        if dt is None:
            return "-"
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return "-"


def fmt_hora(dt):
    try:
        if dt is None:
            return "-"
        return dt.strftime("%H:%M")
    except Exception:
        return "-"


def fmt_dia(dt):
    try:
        if dt is None:
            return "Sin fecha"
        return dt.strftime("%a %d/%m")
    except Exception:
        return "Sin fecha"


# ==========================================
# CALCULAR MONTO
# ==========================================

def calcular_monto(entrada_epoch, salida_epoch):
    """
    Calcula el monto usando valores guardados en minutos Unix.

    Se conserva la misma lógica de redondeo que tenía este dashboard;
    únicamente se corrige la unidad de segundos a minutos.
    """
    try:
        entrada = int(float(entrada_epoch))
        salida = int(float(salida_epoch))

        minutos = max(salida - entrada, 0)
        horas = max(round(minutos / 60), 1)

        return horas * TARIFA_HORA
    except Exception:
        return 0


# ==========================================
# PROCESAR DATAFRAME
# ==========================================

def procesar_df(df):
    df = df.copy()

    # Convertir minutos Unix a datetime nativo
    entradas = [epoch_a_dt(v) for v in df["entrada_minuto"]]
    salidas  = [epoch_a_dt(v) for v in df["minuto_actual"]]

    df["fecha_ingreso_dt"] = entradas
    df["fecha_salida_dt"]  = salidas

    # Formatear usando listas: sin riesgo de NaT
    df["FechaIngreso"] = [fmt_fecha(d) for d in entradas]
    df["HoraIngreso"]  = [fmt_hora(d)  for d in entradas]
    df["FechaSalida"]  = [fmt_fecha(d) for d in salidas]
    df["HoraSalida"]   = [fmt_hora(d)  for d in salidas]

    df["Monto"] = [
        calcular_monto(e, s)
        for e, s in zip(df["entrada_minuto"], df["minuto_actual"])
    ]

    return df


# ==========================================
# FILTRAR POR PERÍODO
# ==========================================

def filtrar_periodo(df, periodo):
    hoy = datetime.now()
    if periodo == "semana":
        inicio = (hoy - timedelta(days=hoy.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        inicio = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    mask = [
        (d is not None) and (d >= inicio)
        for d in df["fecha_ingreso_dt"]
    ]
    return df[mask].copy()


# ==========================================
# DASHBOARD
# ==========================================

def dashboard():
    st.set_page_config(page_title="AutoAccess — Admin", page_icon="🚗", layout="wide")
    aplicar_estilos()

    # Sidebar
    with st.sidebar:
        st.markdown("""
        <div style="padding:8px 0 24px 0;">
            <div style="font-size:20px; font-weight:700; color:#1C1C1E;">🚗 AutoAccess</div>
            <div style="font-size:12px; color:#8E8E93; margin-top:2px;">Panel Administrativo</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("**Menú**")
        st.markdown("📊 Dashboard")
        st.markdown("🚗 Vehículos")
        st.markdown("📥 Reportes")
        st.markdown("---")
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.admin_logueado = False
            st.rerun()

    # Datos
    df_raw = obtener_datos()
    if df_raw.empty:
        st.warning("No se pudo obtener datos de Baserow.")
        return

    df        = procesar_df(df_raw)
    df_semana = filtrar_periodo(df, "semana")
    df_mes    = filtrar_periodo(df, "mes")

    # Encabezado
    st.markdown("""
    <div class="titulo-dashboard">📊 Dashboard</div>
    <div class="subtitulo-dashboard">Resumen de operaciones del estacionamiento</div>
    """, unsafe_allow_html=True)

    # ---- KPIs semana ----
    st.markdown('<div class="seccion-titulo">Esta semana</div>', unsafe_allow_html=True)

    rec_semana   = df_semana["Monto"].sum()
    autos_semana = len(df_semana)

    if "Confirmación de Pago" in df_semana.columns:
        pagados_semana = int(
            df_semana["Confirmación de Pago"]
            .astype(str).str.lower().str.contains("pagado", na=False).sum()
        )
    else:
        pagados_semana = 0

    pend_semana = autos_semana - pagados_semana

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="kpi-card-accent">
            <div class="kpi-label-dark">Recaudado</div>
            <div class="kpi-value-dark">S/ {rec_semana:.0f}</div>
            <div class="kpi-sub-dark">Semana actual</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Autos ingresados</div>
            <div class="kpi-value">{autos_semana}</div>
            <div class="kpi-sub">Semana actual</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Pagos confirmados</div>
            <div class="kpi-value">{pagados_semana}</div>
            <div class="kpi-sub">Semana actual</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Pendientes de pago</div>
            <div class="kpi-value">{pend_semana}</div>
            <div class="kpi-sub">Semana actual</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ---- KPIs mes ----
    st.markdown('<div class="seccion-titulo">Este mes</div>', unsafe_allow_html=True)

    rec_mes   = df_mes["Monto"].sum()
    autos_mes = len(df_mes)

    if "Confirmación de Pago" in df_mes.columns:
        pagados_mes = int(
            df_mes["Confirmación de Pago"]
            .astype(str).str.lower().str.contains("pagado", na=False).sum()
        )
    else:
        pagados_mes = 0

    pend_mes = autos_mes - pagados_mes

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Recaudado</div>
            <div class="kpi-value">S/ {rec_mes:.0f}</div>
            <div class="kpi-sub">Mes actual</div>
        </div>""", unsafe_allow_html=True)
    with c6:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Autos ingresados</div>
            <div class="kpi-value">{autos_mes}</div>
            <div class="kpi-sub">Mes actual</div>
        </div>""", unsafe_allow_html=True)
    with c7:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Pagos confirmados</div>
            <div class="kpi-value">{pagados_mes}</div>
            <div class="kpi-sub">Mes actual</div>
        </div>""", unsafe_allow_html=True)
    with c8:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Pendientes de pago</div>
            <div class="kpi-value">{pend_mes}</div>
            <div class="kpi-sub">Mes actual</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # ---- Gráfico dinámico con toggles período + métrica ----

    col_titulo, col_t1, col_t2 = st.columns([6, 1, 1])

    with col_titulo:
        st.markdown('<div class="seccion-titulo">Evolución de ingresos</div>', unsafe_allow_html=True)

    with col_t1:
        if st.button(
            "📅 Semana",
            use_container_width=True,
            type="primary" if st.session_state.vista_grafico == "semana" else "secondary"
        ):
            st.session_state.vista_grafico = "semana"
            st.rerun()

    with col_t2:
        if st.button(
            "🗓 Mes",
            use_container_width=True,
            type="primary" if st.session_state.vista_grafico == "mes" else "secondary"
        ):
            st.session_state.vista_grafico = "mes"
            st.rerun()

    df_grafico = df_semana if st.session_state.vista_grafico == "semana" else df_mes

    if not df_grafico.empty:
        df_g = df_grafico.copy()
        df_g["dt_orden"] = df_g["fecha_ingreso_dt"]
        df_g["Dia"]      = [fmt_dia(d) for d in df_g["fecha_ingreso_dt"]]

        por_dia = (
            df_g.groupby("Dia")
            .agg(
                Autos=("Monto", "count"),
                Recaudado=("Monto", "sum"),
                dt_orden=("dt_orden", "min")
            )
            .reset_index()
            .sort_values("dt_orden")
        )

        dias       = por_dia["Dia"].tolist()
        vals_autos = por_dia["Autos"].tolist()
        vals_soles = por_dia["Recaudado"].tolist()
        txt_autos  = [str(v) for v in vals_autos]
        txt_soles  = [f"S/{v:.0f}" for v in vals_soles]

        # Traza 0 — Autos
        trace_autos = go.Bar(
            name="Autos ingresados",
            x=dias,
            y=vals_autos,
            text=txt_autos,
            textposition="outside",
            marker_color="#C8FF00",
            visible=True,
            hovertemplate="<b>%{x}</b><br>Autos: %{y}<extra></extra>",
        )

        # Traza 1 — Soles
        trace_soles = go.Bar(
            name="Recaudado (S/)",
            x=dias,
            y=vals_soles,
            text=txt_soles,
            textposition="outside",
            marker_color="#A8D8FF",
            visible=False,
            hovertemplate="<b>%{x}</b><br>Recaudado: S/%{y:.0f}<extra></extra>",
        )

        fig = go.Figure(data=[trace_autos, trace_soles])

        fig.update_layout(
            updatemenus=[
                dict(
                    type="buttons",
                    direction="right",
                    x=0.0,
                    y=1.22,
                    xanchor="left",
                    showactive=True,
                    bgcolor="#FFFFFF",
                    bordercolor="#E8E8ED",
                    borderwidth=1,
                    font=dict(family="Inter", size=12, color="#1C1C1E"),
                    buttons=[
                        dict(
                            label="🚗  Autos",
                            method="update",
                            args=[
                                {"visible": [True, False]},
                                {"yaxis": {
                                    "title": "Cantidad de autos",
                                    "showgrid": True,
                                    "gridcolor": "#F0F0F5",
                                    "zeroline": False,
                                    "rangemode": "tozero"
                                }},
                            ],
                        ),
                        dict(
                            label="💰  Soles",
                            method="update",
                            args=[
                                {"visible": [False, True]},
                                {"yaxis": {
                                    "title": "Recaudado (S/)",
                                    "showgrid": True,
                                    "gridcolor": "#F0F0F5",
                                    "zeroline": False,
                                    "rangemode": "tozero"
                                }},
                            ],
                        ),
                        dict(
                            label="📊  Ambos",
                            method="update",
                            args=[
                                {"visible": [True, True]},
                                {"yaxis": {
                                    "title": "Autos / S/",
                                    "showgrid": True,
                                    "gridcolor": "#F0F0F5",
                                    "zeroline": False,
                                    "rangemode": "tozero"
                                }},
                            ],
                        ),
                    ],
                )
            ],
            barmode="group",
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            font=dict(family="Inter", size=12, color="#1C1C1E"),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.08,
                xanchor="right",
                x=1,
            ),
            yaxis=dict(
                title="Cantidad de autos",
                showgrid=True,
                gridcolor="#F0F0F5",
                zeroline=False,
                rangemode="tozero",
            ),
            xaxis=dict(showgrid=False, tickangle=-30),
            margin=dict(l=0, r=0, t=90, b=60),
            height=450,
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay registros para el período seleccionado.")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ---- Tabla historial ----
    st.markdown('<div class="seccion-titulo">🚗 Historial completo de vehículos</div>', unsafe_allow_html=True)

    tabla = pd.DataFrame({
        "Placa":         df.get("Numero_Placas", pd.Series(dtype=str)),
        "Fecha Ingreso": df["FechaIngreso"],
        "Hora Ingreso":  df["HoraIngreso"],
        "Fecha Salida":  df["FechaSalida"],
        "Hora Salida":   df["HoraSalida"],
        "Estado Pago":   df.get("Confirmación de Pago", pd.Series(dtype=str)),
        "Monto (S/)":    df["Monto"],
    })

    st.dataframe(tabla, use_container_width=True, hide_index=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    csv = tabla.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar reporte CSV",
        data=csv,
        file_name="reporte_autoaccess.csv",
        mime="text/csv"
    )


# ==========================================
# MAIN
# ==========================================

if not st.session_state.admin_logueado:
    login_admin()
else:
    dashboard()