"""
Sistema de Cochera Automatizada - Regla de Redondeo a 15 Minutos
----------------------------------------------------------------
App académica en Streamlit que consulta placas en Baserow, calcula el
monto a pagar según el tiempo estacionado y simula un flujo de pago
estilo billetera digital (Yape/Plin).
"""

import time
from io import BytesIO
import unicodedata

import requests
import streamlit as st
import qrcode


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASEROW_TOKEN = "hVxGMBTks1fAopHga6Vqm2BKi2H5gnQj"
BASEROW_API_URL = "https://api.baserow.io"
TABLE_ID = "1032007"

# No usamos Activo, Estado ni Monto porque no existen en tu Baserow.
# La salida queda habilitada con Confirmación de Pago = pagado.
# La Raspberry abrirá cuando lea la placa otra vez y escriba Placa_confirmación.
FIELD_CANDIDATES = {
    "placa": ["Numero_Placas", "Numero Placas", "numero_placas"],
    "entrada_minuto": ["entrada_minuto", "Entrada_minuto", "Entrada Minuto"],
    "minuto_actual": ["minuto_actual", "Minuto_actual", "Minuto Actual"],
    "confirmacion_pago": [
        "Confirmación de Pago",
        "Confirmacion de Pago",
        "Confirmacion_Pago",
        "confirmación_pago",
        "confirmacion_pago",
    ],
    "placa_confirmacion": [
        "Placa_confirmación",
        "Placa_confirmacion",
        "Placa confirmación",
        "Placa confirmacion",
        "placa_confirmación",
        "placa_confirmacion",
    ],
}

TARIFA_HORA = 4.00  # S/ 4.00 por hora
_campos_cache = None


def obtener_token_baserow():
    return BASEROW_TOKEN


# ============================================================
# UTILIDADES BASEROW
# ============================================================

def quitar_tildes(texto):
    texto = str(texto)
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def normalizar_nombre_campo(nombre):
    nombre = quitar_tildes(nombre).lower().strip()
    nombre = nombre.replace(" ", "_").replace("-", "_")
    while "__" in nombre:
        nombre = nombre.replace("__", "_")
    return nombre


def obtener_campos_baserow(token):
    global _campos_cache

    if _campos_cache is not None:
        return _campos_cache

    url = f"{BASEROW_API_URL}/api/database/fields/table/{TABLE_ID}/"
    headers = {"Authorization": f"Token {token}"}

    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise Exception(f"Error leyendo campos de Baserow: {r.status_code} - {r.text}")

    campos = {}
    for field in r.json():
        name = field.get("name", "")
        campos[normalizar_nombre_campo(name)] = name

    _campos_cache = campos
    return _campos_cache


def resolver_campo(logico, token, obligatorio=True):
    campos = obtener_campos_baserow(token)

    for candidato in FIELD_CANDIDATES[logico]:
        clave = normalizar_nombre_campo(candidato)
        if clave in campos:
            return campos[clave]

    if obligatorio:
        esperados = ", ".join(FIELD_CANDIDATES[logico])
        raise Exception(f"No encontré el campo {logico}. Nombres esperados: {esperados}")

    return None


def baserow_headers(token, json=True):
    headers = {"Authorization": f"Token {token}"}
    if json:
        headers["Content-Type"] = "application/json"
    return headers


# ============================================================
# UTILIDADES DE NEGOCIO
# ============================================================

def normalizar_placa(placa):
    return str(placa).strip().upper().replace(" ", "")


def normalizar_placa_busqueda(placa):
    """
    Normaliza la placa únicamente para compararla durante la búsqueda.
    No cambia cómo se muestra la placa ni cómo se genera el código de pago.

    Ejemplos equivalentes:
    ASB-L3N, ASBL3N, asb l3n
    """
    texto = str(placa or "").strip().upper()
    return "".join(
        caracter
        for caracter in texto
        if caracter.isascii() and caracter.isalnum()
    )


def pago_esta_pagado(valor):
    return quitar_tildes(str(valor or "")).strip().lower() == "pagado"


def placa_confirmacion_vacia(fila, token):
    campo = resolver_campo("placa_confirmacion", token, obligatorio=True)
    valor = fila.get(campo, "")
    return valor is None or str(valor).strip() == ""


def obtener_minuto_actual():
    return int(time.time() // 60)


def minuto_a_fecha_y_hora(minuto_epoch):
    segundos = minuto_epoch * 60
    estructura_tiempo = time.localtime(segundos)
    fecha = time.strftime("%d/%m/%Y", estructura_tiempo)
    hora = time.strftime("%I:%M %p", estructura_tiempo).lstrip("0")
    return fecha, hora


def buscar_placa_en_baserow(placa, token):
    """
    Busca la fila ABIERTA más reciente de la placa, usando exactamente
    el formato de tiempo que crea la Raspberry: int(time.time() // 60).

    Solo esta búsqueda fue modificada:
    - Recorre todas las páginas de Baserow.
    - Compara placas ignorando guiones, espacios y mayúsculas/minúsculas.
    - Ignora placas vacías, NaN y registros con tiempo incompatible.
    - Solo considera filas abiertas (Placa_confirmación vacía).
    - Elige la fila abierta más reciente por ID.

    No convierte entrada_minuto, no modifica fechas y no cambia el cálculo.
    """
    placa_buscada = normalizar_placa_busqueda(placa)
    if not placa_buscada:
        return None

    campo_placa = resolver_campo("placa", token)
    campo_entrada = resolver_campo("entrada_minuto", token)

    url = f"{BASEROW_API_URL}/api/database/rows/table/{TABLE_ID}/"
    params = {
        "user_field_names": "true",
        "size": 200,
    }

    minuto_actual_raspberry = obtener_minuto_actual()
    candidatas = []

    while url:
        r = requests.get(
            url,
            headers=baserow_headers(token, json=False),
            params=params,
            timeout=15,
        )

        if r.status_code != 200:
            raise Exception(
                f"Error consultando Baserow: {r.status_code} - {r.text}"
            )

        data = r.json()

        for fila in data.get("results", []):
            placa_fila = normalizar_placa_busqueda(
                fila.get(campo_placa, "")
            )

            if placa_fila != placa_buscada:
                continue

            if not placa_confirmacion_vacia(fila, token):
                continue

            entrada = fila.get(campo_entrada)

            try:
                entrada_numero = int(float(entrada))
            except (TypeError, ValueError):
                continue

            # La Raspberry crea entrada_minuto con int(time.time() // 60).
            # Por eso un valor vacío, negativo o mayor que el minuto Unix
            # actual no corresponde al formato que usa este flujo.
            if entrada_numero <= 0 or entrada_numero > minuto_actual_raspberry:
                continue

            candidatas.append(fila)

        url = data.get("next")
        params = None

    if not candidatas:
        return None

    def id_fila(fila):
        try:
            return int(fila.get("id", 0) or 0)
        except (TypeError, ValueError):
            return 0

    candidatas.sort(key=id_fila, reverse=True)
    return candidatas[0]

def actualizar_minuto_actual(row_id, minuto_actual, token):
    campo_minuto_actual = resolver_campo("minuto_actual", token)

    url = f"{BASEROW_API_URL}/api/database/rows/table/{TABLE_ID}/{row_id}/?user_field_names=true"
    data = {campo_minuto_actual: minuto_actual}

    r = requests.patch(url, headers=baserow_headers(token), json=data, timeout=15)
    if r.status_code not in [200, 202]:
        raise Exception(f"Error actualizando minuto_actual: {r.status_code} - {r.text}")

    return r.json()


def confirmar_pago_baserow(row_id, token):
    campo_pago = resolver_campo("confirmacion_pago", token)

    url = f"{BASEROW_API_URL}/api/database/rows/table/{TABLE_ID}/{row_id}/?user_field_names=true"
    data = {campo_pago: "pagado"}

    r = requests.patch(url, headers=baserow_headers(token), json=data, timeout=15)
    if r.status_code not in [200, 202]:
        raise Exception(f"Error confirmando pago: {r.status_code} - {r.text}")

    return r.json()


def calcular_horas_cobradas(minutos_totales):
    """
    Regla: si los minutos excedentes pasan de 15,
    se redondea hacia arriba cobrando una hora completa más.
    """
    horas_completas = minutos_totales // 60
    minutos_excedentes = minutos_totales % 60

    if minutos_excedentes > 15:
        horas_cobradas = horas_completas + 1
    else:
        horas_cobradas = horas_completas

    return max(horas_cobradas, 1)


def calcular_pago(fila, token):
    row_id = fila.get("id")
    campo_placa = resolver_campo("placa", token)
    campo_entrada = resolver_campo("entrada_minuto", token)
    campo_pago = resolver_campo("confirmacion_pago", token, obligatorio=False)

    placa = fila.get(campo_placa, "")
    entrada_minuto = fila.get(campo_entrada)

    if entrada_minuto in [None, ""]:
        raise Exception("La placa existe, pero el campo entrada_minuto está vacío.")

    entrada_minuto = int(float(entrada_minuto))
    minuto_actual = obtener_minuto_actual()
    minutos_estacionado = minuto_actual - entrada_minuto

    if minutos_estacionado < 0:
        return {
            "ok": False,
            "row_id": row_id,
            "placa": placa,
            "entrada_minuto": entrada_minuto,
            "minuto_actual": minuto_actual,
            "minutos_estacionado": minutos_estacionado,
        }

    horas_cobradas = calcular_horas_cobradas(minutos_estacionado)
    monto = horas_cobradas * TARIFA_HORA
    codigo_pago = f"PARK-{normalizar_placa(placa)}-{row_id}-{minuto_actual}"

    actualizar_minuto_actual(row_id, minuto_actual, token)

    return {
        "ok": True,
        "row_id": row_id,
        "placa": placa,
        "entrada_minuto": entrada_minuto,
        "minuto_actual": minuto_actual,
        "minutos_estacionado": minutos_estacionado,
        "horas_transcurridas": minutos_estacionado // 60,
        "minutos_restantes": minutos_estacionado % 60,
        "horas_cobradas": horas_cobradas,
        "tarifa_hora": TARIFA_HORA,
        "monto": monto,
        "codigo_pago": codigo_pago,
        "ya_pagado": pago_esta_pagado(fila.get(campo_pago, "")) if campo_pago else False,
    }


def generar_qr_demo(texto):
    qr = qrcode.QRCode(version=1, box_size=8, border=3)
    qr.add_data(texto)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# ============================================================
# ESTADO DE SESIÓN
# ============================================================

def init_state():
    defaults = {
        "vista": "inicio",
        "resultado": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_a_inicio():
    st.session_state["vista"] = "inicio"
    st.session_state["resultado"] = None


# ============================================================
# ESTILOS (CSS Inyectado con limpieza absoluta)
# ============================================================

def inyectar_estilos():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght=400;500;600;700;800&display=swap');

        #MainMenu, footer, header {visibility: hidden;}

        :root {
            --bg-app: #000000;
            --border-soft: #FFFFFF;
            --text-primary: #FFFFFF;
            --text-secondary: #FFFFFF;
        }

        html, body, [class*="css"], .stApp,
        h1, h2, h3, h4, h5, h6, p, span, div, label,
        input, textarea, button {
            font-family: 'Inter', 'Segoe UI', sans-serif !important;
        }

        .stApp {
            background-color: var(--bg-app);
        }

        .block-container {
            padding-top: 4rem;
            max-width: 500px !important;
        }

        p, span, label, .stMarkdown {
            color: var(--text-secondary);
        }
        h1, h2, h3 {
            color: var(--text-primary) !important;
            font-weight: 700 !important;
        }

        /* ---- Input Placa ---- */
        div[data-testid="stTextInput"] {
            width: 100% !important;
            margin-bottom: 0px !important;
        }
        div[data-testid="stTextInput"] > div {
            background-color: transparent !important;
            border: none !important;
        }
        div[data-testid="stTextInput"] input {
            background-color: #000000 !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            border: 1px solid var(--border-soft) !important;
            border-radius: 12px !important;
            font-weight: 400 !important;
            padding: 1rem !important;
            font-size: 1.1rem !important;
            text-align: center !important;
            letter-spacing: 1px;
            box-sizing: border-box !important;
        }
        div[data-testid="stTextInput"] input::placeholder {
            color: #FFFFFF !important;
            opacity: 0.7 !important;
        }

        /* ---- Botón principal (Fondo blanco, texto negro) ---- */
        div[data-testid="stButton"] button[kind="primary"],
        button[kind="primary"],
        [data-testid="stBaseButton-primary"] {
            background-color: #FFFFFF !important;
            color: #000000 !important;
            border: 1px solid #FFFFFF !important;
            border-radius: 12px !important;
            font-weight: 700 !important;
            height: 3.5rem !important;
            font-size: 1.1rem !important;
            letter-spacing: 0.5px;
            transition: all 0.2s ease;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            box-sizing: border-box !important;
            width: 100% !important;
        }
        [data-testid="stBaseButton-primary"] *, button[kind="primary"] * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        div[data-testid="stButton"] button[kind="primary"]:hover {
            background-color: #000000 !important;
            border-color: #FFFFFF !important;
        }
        div[data-testid="stButton"] button[kind="primary"]:hover * {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }

        /* ---- Botón secundario ---- */
        div[data-testid="stButton"] button[kind="secondary"] {
            background-color: #000000 !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            border: 1px solid var(--border-soft) !important;
            border-radius: 12px !important;
            font-weight: 600 !important;
            height: 3.5rem !important;
            width: 100% !important;
        }

        /* ---- UI Paneles ---- */
        .placa-vehicular {
            background: #000000;
            border: 2px solid #FFFFFF;
            border-radius: 14px;
            padding: 16px 14px;
            text-align: center;
            margin-bottom: 20px;
        }
        .placa-vehicular .titulo-etiqueta {
            color: #FFFFFF;
            font-size: 0.85rem;
            font-weight: 600;
            letter-spacing: 2px;
            margin-bottom: 4px;
            opacity: 0.7;
        }
        .placa-vehicular .valor {
            color: #FFFFFF;
            font-size: 2.5rem;
            font-weight: 800;
            letter-spacing: 4px;
        }

        .tarjeta {
            background: #000000;
            border: 1px solid var(--border-soft);
            border-radius: 12px;
            padding: 14px 10px;
            margin-bottom: 12px;
            text-align: center;
        }
        .tarjeta-monto {
            background: #000000;
            border: 1px solid var(--border-soft);
            border-radius: 14px;
            padding: 22px;
            margin-bottom: 20px;
            text-align: center;
        }

        /* ---- Centrado del QR ---- */
        div[data-testid="stImage"] {
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            width: 100% !important;
        }
        div[data-testid="stImage"] > img {
            margin: 0 auto !important;
        }

        /* ---- Éxito ---- */
        .exito-contenedor {
            text-align: center;
            padding: 30px 10px;
        }
        .exito-marco {
            width: 70px;
            height: 70px;
            margin: 0 auto 24px auto;
            border: 2px solid #FFFFFF;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .exito-titulo {
            font-size: 1.75rem;
            margin-bottom: 12px;
            color: #FFFFFF;
            font-weight: 700;
        }

        div[data-testid="stAlert"] {
            background-color: #000000 !important;
            border: 1px solid #FFFFFF !important;
        }
        div[data-testid="stAlert"] p {
            color: #FFFFFF !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# LÓGICA DE PROCESAMIENTO DE CONSULTA
# ============================================================

def procesar_consulta(placa_texto, token):
    placa_limpia = placa_texto.strip()
    if not placa_limpia:
        st.warning("Ingresa una placa para continuar.")
        return
    try:
        fila = buscar_placa_en_baserow(placa_limpia, token)
        if fila is None:
            st.error("Placa no encontrada")
            return

        resultado = calcular_pago(fila, token)
        if not resultado["ok"]:
            st.error("El registro de entrada parece inválido.")
            return

        st.session_state["resultado"] = resultado
        st.session_state["vista"] = "dashboard"
        st.rerun()
    except Exception as e:
        st.error(f"Error durante la consulta: {str(e)}")


# ============================================================
# VISTAS PRINCIPALES
# ============================================================

def vista_inicio(token):
    st.markdown(
        "<h1 style='text-align:center; font-size: 2.2rem; margin-bottom:10px; color:#FFFFFF;'>"
        "Cochera Automatizada</h1>"
        "<p style='text-align:center; color:#FFFFFF; font-size:1rem; margin-bottom:30px;'>"
        "Ingresa la placa de tu vehículo para consultar tu pago</p>",
        unsafe_allow_html=True,
    )

    placa = st.text_input("Placa", placeholder="Ejemplo: ASB-L3N", label_visibility="collapsed")
    st.write("")
    
    if st.button("Consultar", use_container_width=True, type="primary"):
        procesar_consulta(placa, token)


def vista_dashboard():
    resultado = st.session_state.get("resultado")
    if not resultado:
        reset_a_inicio()
        st.rerun()

    fecha_ent, hora_ent = minuto_a_fecha_y_hora(resultado["entrada_minuto"])
    fecha_sal, hora_sal = minuto_a_fecha_y_hora(resultado["minuto_actual"])

    # Tarjeta de Placa con título "PLACA"
    st.markdown(
        f"""
        <div class="placa-vehicular">
            <div class="titulo-etiqueta">PLACA</div>
            <div class="valor">{resultado["placa"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="tarjeta"><p style="font-size:0.75rem;margin:0;opacity:0.6;letter-spacing:0.5px;">FECHA ENTRADA</p><b style="font-size:1.05rem;">{fecha_ent}</b></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="tarjeta"><p style="font-size:0.75rem;margin:0;opacity:0.6;letter-spacing:0.5px;">HORA ENTRADA</p><b style="font-size:1.05rem;">{hora_ent}</b></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="tarjeta"><p style="font-size:0.75rem;margin:0;opacity:0.6;letter-spacing:0.5px;">FECHA SALIDA</p><b style="font-size:1.05rem;">{fecha_sal}</b></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="tarjeta"><p style="font-size:0.75rem;margin:0;opacity:0.6;letter-spacing:0.5px;">HORA SALIDA</p><b style="font-size:1.05rem;">{hora_sal}</b></div>', unsafe_allow_html=True)

    # Tarjeta del total calculado y tiempo total transcurrido
    st.markdown(
        f"""
        <div class="tarjeta-monto">
            <p style="font-size:0.75rem;margin:0;opacity:0.7;">
                Tiempo: {resultado["horas_transcurridas"]}h {resultado["minutos_restantes"]}m ({resultado["horas_cobradas"]} hora(s) cobradas)
            </p>
            <div style="font-size:2.2rem;font-weight:800;color:#FFF;margin-top:4px;">S/ {resultado["monto"]:.2f}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("PAGAR", use_container_width=True, type="primary"):
        st.session_state["vista"] = "pago"
        st.rerun()

    if st.button("Cancelar", use_container_width=True, type="secondary"):
        reset_a_inicio()
        st.rerun()


def vista_pago(token):
    resultado = st.session_state.get("resultado")
    if not resultado:
        reset_a_inicio()
        st.rerun()

    st.markdown(
        f"""
        <p style="text-align:center; margin-bottom:5px; color:#FFFFFF; font-size:1.3rem; font-weight:700;">Pago con billetera digital</p>
        <p style="text-align:center; margin-bottom:5px; color:#888; font-size:0.9rem;">Monto a transferir</p>
        <p style="text-align:center; font-size:2.2rem; font-weight:800; color:#FFFFFF; margin-bottom:20px;">S/ {resultado['monto']:.2f}</p>
        """,
        unsafe_allow_html=True,
    )

    texto_qr = f"PLACA: {resultado['placa']}\nMONTO: S/ {resultado['monto']:.2f}\nCODIGO: {resultado['codigo_pago']}"
    qr_img = generar_qr_demo(texto_qr)
    st.image(qr_img, width=250)

    st.write("")

    if st.button("Confirmar transferencia", use_container_width=True, type="primary"):
        try:
            confirmar_pago_baserow(resultado["row_id"], token)
            st.session_state["vista"] = "exito"
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo confirmar el pago en Baserow: {str(e)}")
        
    if st.button("Atrás", use_container_width=True, type="secondary"):
        st.session_state["vista"] = "dashboard"
        st.rerun()


def vista_exito():
    resultado = st.session_state.get("resultado")
    if not resultado:
        reset_a_inicio()
        st.rerun()

    with st.spinner("Procesando pago..."):
        time.sleep(1.2)

    st.markdown(
        f"""
        <div class="exito-contenedor">
            <div class="exito-marco">
                <div style="width:24px; height:12px; border-left:3px solid #FFF; border-bottom:3px solid #FFF; transform:rotate(-45deg); margin-top:-4px;"></div>
            </div>
            <div class="exito-titulo">Transacción procesada</div>
            <p style="color:#FFFFFF; line-height:1.6; margin-bottom:20px; font-size:1rem;">
                El pago ha sido confirmado correctamente. La barrera de salida ha sido habilitada para su vehículo.
            </p>
            <p style="font-size:0.75rem; color:#888; letter-spacing:1px;">ID: {resultado['codigo_pago']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.success("¡Pago realizado con éxito!")

    time.sleep(3.0)
    reset_a_inicio()
    st.rerun()


# ============================================================
# CONTROL PRINCIPAL
# ============================================================

def main():
    st.set_page_config(page_title="Cochera Automatizada", layout="centered")

    init_state()
    inyectar_estilos()

    token = obtener_token_baserow()
    vista = st.session_state["vista"]

    if vista == "inicio":
        vista_inicio(token)
    elif vista == "dashboard":
        vista_dashboard()
    elif vista == "pago":
        vista_pago(token)
    elif vista == "exito":
        vista_exito()


if __name__ == "__main__":
    main()