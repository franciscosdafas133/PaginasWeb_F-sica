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
# La Raspberry abrirá cuando lea la placa otra vez y escriba
# Placa_confirmación.
FIELD_CANDIDATES = {
    "placa": [
        "Numero_Placas",
        "Numero Placas",
        "numero_placas",
    ],
    "entrada_minuto": [
        "entrada_minuto",
        "Entrada_minuto",
        "Entrada Minuto",
    ],
    "minuto_actual": [
        "minuto_actual",
        "Minuto_actual",
        "Minuto Actual",
    ],
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

TARIFA_HORA = 4.00
_campos_cache = None


def obtener_token_baserow():
    return BASEROW_TOKEN


# ============================================================
# UTILIDADES BASEROW
# ============================================================

def quitar_tildes(texto):
    texto = str(texto)

    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
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

    url = (
        f"{BASEROW_API_URL}/api/database/"
        f"fields/table/{TABLE_ID}/"
    )

    headers = {
        "Authorization": f"Token {token}"
    }

    respuesta = requests.get(
        url,
        headers=headers,
        timeout=15,
    )

    if respuesta.status_code != 200:
        raise Exception(
            "Error leyendo campos de Baserow: "
            f"{respuesta.status_code} - "
            f"{respuesta.text}"
        )

    campos = {}

    for field in respuesta.json():
        nombre = field.get("name", "")
        campos[normalizar_nombre_campo(nombre)] = nombre

    _campos_cache = campos

    return _campos_cache


def resolver_campo(logico, token, obligatorio=True):
    campos = obtener_campos_baserow(token)

    for candidato in FIELD_CANDIDATES[logico]:
        clave = normalizar_nombre_campo(candidato)

        if clave in campos:
            return campos[clave]

    if obligatorio:
        esperados = ", ".join(
            FIELD_CANDIDATES[logico]
        )

        raise Exception(
            f"No encontré el campo {logico}. "
            f"Nombres esperados: {esperados}"
        )

    return None


def baserow_headers(token, json=True):
    headers = {
        "Authorization": f"Token {token}"
    }

    if json:
        headers["Content-Type"] = "application/json"

    return headers


# ============================================================
# UTILIDADES DE NEGOCIO
# ============================================================

def normalizar_placa(placa):
    """
    Normaliza una placa para compararla sin importar:

    - Mayúsculas o minúsculas.
    - Guiones.
    - Espacios.
    - Puntos.
    - Otros separadores.

    Ejemplos equivalentes:

    NGX-068
    NGX068
    ngx 068
    """

    texto = str(placa or "").upper().strip()

    return "".join(
        caracter
        for caracter in texto
        if caracter.isascii() and caracter.isalnum()
    )


def variantes_placa(placa):
    """
    Crea las formas equivalentes de la placa.

    Además de ignorar guiones, espacios y mayúsculas,
    permite encontrar placas divididas en dos bloques
    aunque el usuario escriba primero el bloque numérico.

    Ejemplos:

    NGX-068
    NGX068
    ngx 068
    068-NGX
    """

    texto = str(placa or "").upper().strip()
    placa_normalizada = normalizar_placa(texto)

    if not placa_normalizada:
        return set()

    variantes = {
        placa_normalizada
    }

    bloques = []
    bloque_actual = []

    for caracter in texto:
        if caracter.isascii() and caracter.isalnum():
            bloque_actual.append(caracter)

        elif bloque_actual:
            bloques.append(
                "".join(bloque_actual)
            )

            bloque_actual = []

    if bloque_actual:
        bloques.append(
            "".join(bloque_actual)
        )

    # Si la placa tiene dos bloques explícitos,
    # también acepta que se escriban en orden inverso.
    if len(bloques) == 2:
        placa_invertida = normalizar_placa(
            bloques[1] + bloques[0]
        )

        variantes.add(placa_invertida)

    # También reconoce placas clásicas de tres letras
    # y tres números escritas sin separador.
    if len(placa_normalizada) == 6:
        primer_bloque = placa_normalizada[:3]
        segundo_bloque = placa_normalizada[3:]

        primer_es_letras = primer_bloque.isalpha()
        primer_es_numeros = primer_bloque.isdigit()

        segundo_es_letras = segundo_bloque.isalpha()
        segundo_es_numeros = segundo_bloque.isdigit()

        formato_letras_numeros = (
            primer_es_letras
            and segundo_es_numeros
        )

        formato_numeros_letras = (
            primer_es_numeros
            and segundo_es_letras
        )

        if (
            formato_letras_numeros
            or formato_numeros_letras
        ):
            variantes.add(
                segundo_bloque + primer_bloque
            )

    return variantes


def pago_esta_pagado(valor):
    texto = quitar_tildes(
        str(valor or "")
    ).strip().lower()

    return texto == "pagado"


def placa_confirmacion_vacia(fila, token):
    campo = resolver_campo(
        "placa_confirmacion",
        token,
        obligatorio=True,
    )

    valor = fila.get(campo, "")

    return (
        valor is None
        or str(valor).strip() == ""
    )


def obtener_minuto_actual():
    return int(
        time.time() // 60
    )


def minuto_a_fecha_y_hora(minuto_epoch):
    segundos = minuto_epoch * 60

    estructura_tiempo = time.localtime(
        segundos
    )

    fecha = time.strftime(
        "%d/%m/%Y",
        estructura_tiempo,
    )

    hora = time.strftime(
        "%I:%M %p",
        estructura_tiempo,
    ).lstrip("0")

    return fecha, hora


def buscar_placa_en_baserow(placa, token):
    """
    Busca una placa en todas las filas de Baserow.

    Esta búsqueda:

    - No depende de mayúsculas o minúsculas.
    - No depende de guiones o espacios.
    - Revisa todas las páginas de la tabla.
    - No depende del orden visual de las filas.
    - Prioriza el registro abierto más reciente.
    - Si no existe uno abierto, devuelve igualmente
      el registro coincidente más reciente.

    No utiliza el parámetro search de Baserow porque
    esa búsqueda es literal. Por ejemplo, NGX068
    podría no encontrar un valor guardado como NGX-068.
    """

    variantes_buscadas = variantes_placa(
        placa
    )

    if not variantes_buscadas:
        return None

    campo_placa = resolver_campo(
        "placa",
        token,
    )

    campo_entrada = resolver_campo(
        "entrada_minuto",
        token,
    )

    campo_confirmacion = resolver_campo(
        "placa_confirmacion",
        token,
        obligatorio=False,
    )

    url = (
        f"{BASEROW_API_URL}/api/database/"
        f"rows/table/{TABLE_ID}/"
    )

    # Se solicitan 200 registros por página.
    # Luego se continúa usando el enlace "next"
    # hasta recorrer toda la tabla.
    params = {
        "user_field_names": "true",
        "size": 200,
    }

    coincidencias = []

    while url:
        respuesta = requests.get(
            url,
            headers=baserow_headers(
                token,
                json=False,
            ),
            params=params,
            timeout=15,
        )

        if respuesta.status_code != 200:
            raise Exception(
                "Error consultando Baserow: "
                f"{respuesta.status_code} - "
                f"{respuesta.text}"
            )

        datos = respuesta.json()
        filas = datos.get("results", [])

        for fila in filas:
            placa_guardada = fila.get(
                campo_placa,
                "",
            )

            variantes_guardadas = variantes_placa(
                placa_guardada
            )

            coincide = bool(
                variantes_buscadas.intersection(
                    variantes_guardadas
                )
            )

            if coincide:
                coincidencias.append(fila)

        # Si existe otra página, Baserow entrega
        # su dirección completa dentro de "next".
        url = datos.get("next")

        # El enlace siguiente ya contiene los parámetros
        # necesarios, por eso se dejan en None.
        params = None

    if not coincidencias:
        return None

    def clave_orden(fila):
        entrada = fila.get(
            campo_entrada,
            0,
        )

        try:
            entrada = int(
                float(entrada or 0)
            )

        except (TypeError, ValueError):
            entrada = 0

        try:
            row_id = int(
                fila.get("id", 0) or 0
            )

        except (TypeError, ValueError):
            row_id = 0

        return entrada, row_id

    # Ordena desde el registro más reciente
    # hasta el más antiguo.
    coincidencias.sort(
        key=clave_orden,
        reverse=True,
    )

    # Primero se busca una estancia abierta.
    # Se considera abierta cuando Placa_confirmación
    # está vacía.
    if campo_confirmacion:
        for fila in coincidencias:
            confirmacion = fila.get(
                campo_confirmacion,
                "",
            )

            esta_vacia = (
                confirmacion is None
                or str(confirmacion).strip() == ""
            )

            if esta_vacia:
                return fila

    # Si todas las coincidencias tienen confirmación,
    # ya no se devuelve "Placa no encontrada".
    # Se devuelve la coincidencia más reciente.
    return coincidencias[0]


def actualizar_minuto_actual(
    row_id,
    minuto_actual,
    token,
):
    campo_minuto_actual = resolver_campo(
        "minuto_actual",
        token,
    )

    url = (
        f"{BASEROW_API_URL}/api/database/"
        f"rows/table/{TABLE_ID}/{row_id}/"
        "?user_field_names=true"
    )

    datos = {
        campo_minuto_actual: minuto_actual
    }

    respuesta = requests.patch(
        url,
        headers=baserow_headers(token),
        json=datos,
        timeout=15,
    )

    if respuesta.status_code not in [200, 202]:
        raise Exception(
            "Error actualizando minuto_actual: "
            f"{respuesta.status_code} - "
            f"{respuesta.text}"
        )

    return respuesta.json()


def confirmar_pago_baserow(row_id, token):
    campo_pago = resolver_campo(
        "confirmacion_pago",
        token,
    )

    url = (
        f"{BASEROW_API_URL}/api/database/"
        f"rows/table/{TABLE_ID}/{row_id}/"
        "?user_field_names=true"
    )

    datos = {
        campo_pago: "pagado"
    }

    respuesta = requests.patch(
        url,
        headers=baserow_headers(token),
        json=datos,
        timeout=15,
    )

    if respuesta.status_code not in [200, 202]:
        raise Exception(
            "Error confirmando pago: "
            f"{respuesta.status_code} - "
            f"{respuesta.text}"
        )

    return respuesta.json()


def calcular_horas_cobradas(minutos_totales):
    """
    Regla: si los minutos excedentes pasan de 15,
    se redondea hacia arriba cobrando una hora
    completa más.
    """

    horas_completas = (
        minutos_totales // 60
    )

    minutos_excedentes = (
        minutos_totales % 60
    )

    if minutos_excedentes > 15:
        horas_cobradas = (
            horas_completas + 1
        )

    else:
        horas_cobradas = horas_completas

    return max(
        horas_cobradas,
        1,
    )


def calcular_pago(fila, token):
    row_id = fila.get("id")

    campo_placa = resolver_campo(
        "placa",
        token,
    )

    campo_entrada = resolver_campo(
        "entrada_minuto",
        token,
    )

    campo_pago = resolver_campo(
        "confirmacion_pago",
        token,
        obligatorio=False,
    )

    placa = fila.get(
        campo_placa,
        "",
    )

    entrada_minuto = fila.get(
        campo_entrada
    )

    if entrada_minuto in [None, ""]:
        raise Exception(
            "La placa existe, pero el campo "
            "entrada_minuto está vacío."
        )

    entrada_minuto = int(
        float(entrada_minuto)
    )

    minuto_actual = obtener_minuto_actual()

    minutos_estacionado = (
        minuto_actual - entrada_minuto
    )

    if minutos_estacionado < 0:
        return {
            "ok": False,
            "row_id": row_id,
            "placa": placa,
            "entrada_minuto": entrada_minuto,
            "minuto_actual": minuto_actual,
            "minutos_estacionado": minutos_estacionado,
        }

    horas_cobradas = calcular_horas_cobradas(
        minutos_estacionado
    )

    monto = (
        horas_cobradas * TARIFA_HORA
    )

    codigo_pago = (
        f"PARK-"
        f"{normalizar_placa(placa)}-"
        f"{row_id}-"
        f"{minuto_actual}"
    )

    actualizar_minuto_actual(
        row_id,
        minuto_actual,
        token,
    )

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
        "ya_pagado": (
            pago_esta_pagado(
                fila.get(campo_pago, "")
            )
            if campo_pago
            else False
        ),
    }


def generar_qr_demo(texto):
    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=3,
    )

    qr.add_data(texto)
    qr.make(fit=True)

    imagen = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    buffer = BytesIO()

    imagen.save(
        buffer,
        format="PNG",
    )

    buffer.seek(0)

    return buffer


# ============================================================
# ESTADO DE SESIÓN
# ============================================================

def init_state():
    valores_iniciales = {
        "vista": "inicio",
        "resultado": None,
    }

    for clave, valor in valores_iniciales.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor


def reset_a_inicio():
    st.session_state["vista"] = "inicio"
    st.session_state["resultado"] = None


# ============================================================
# ESTILOS
# ============================================================

def inyectar_estilos():
    st.markdown(
        """
        <style>
        @import url(
            'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap'
        );

        #MainMenu,
        footer,
        header {
            visibility: hidden;
        }

        :root {
            --bg-app: #000000;
            --border-soft: #FFFFFF;
            --text-primary: #FFFFFF;
            --text-secondary: #FFFFFF;
        }

        html,
        body,
        [class*="css"],
        .stApp,
        h1,
        h2,
        h3,
        h4,
        h5,
        h6,
        p,
        span,
        div,
        label,
        input,
        textarea,
        button {
            font-family:
                'Inter',
                'Segoe UI',
                sans-serif !important;
        }

        .stApp {
            background-color: var(--bg-app);
        }

        .block-container {
            padding-top: 4rem;
            max-width: 500px !important;
        }

        p,
        span,
        label,
        .stMarkdown {
            color: var(--text-secondary);
        }

        h1,
        h2,
        h3 {
            color: var(--text-primary) !important;
            font-weight: 700 !important;
        }

        div[data-testid="stTextInput"] {
            width: 100% !important;
            margin-bottom: 0 !important;
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

        [data-testid="stBaseButton-primary"] *,
        button[kind="primary"] * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }

        div[data-testid="stButton"]
        button[kind="primary"]:hover {
            background-color: #000000 !important;
            border-color: #FFFFFF !important;
        }

        div[data-testid="stButton"]
        button[kind="primary"]:hover * {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }

        div[data-testid="stButton"]
        button[kind="secondary"] {
            background-color: #000000 !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            border: 1px solid var(--border-soft) !important;
            border-radius: 12px !important;
            font-weight: 600 !important;
            height: 3.5rem !important;
            width: 100% !important;
        }

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

        div[data-testid="stImage"] {
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            width: 100% !important;
        }

        div[data-testid="stImage"] > img {
            margin: 0 auto !important;
        }

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
        st.warning(
            "Ingresa una placa para continuar."
        )

        return

    try:
        fila = buscar_placa_en_baserow(
            placa_limpia,
            token,
        )

        if fila is None:
            st.error(
                "Placa no encontrada"
            )

            return

        resultado = calcular_pago(
            fila,
            token,
        )

        if not resultado["ok"]:
            st.error(
                "El registro de entrada parece inválido."
            )

            return

        st.session_state["resultado"] = resultado
        st.session_state["vista"] = "dashboard"

        st.rerun()

    except Exception as error:
        st.error(
            f"Error durante la consulta: {str(error)}"
        )


# ============================================================
# VISTAS PRINCIPALES
# ============================================================

def vista_inicio(token):
    st.markdown(
        """
        <h1 style="
            text-align:center;
            font-size:2.2rem;
            margin-bottom:10px;
            color:#FFFFFF;
        ">
            Cochera Automatizada
        </h1>

        <p style="
            text-align:center;
            color:#FFFFFF;
            font-size:1rem;
            margin-bottom:30px;
        ">
            Ingresa la placa de tu vehículo
            para consultar tu pago
        </p>
        """,
        unsafe_allow_html=True,
    )

    placa = st.text_input(
        "Placa",
        placeholder="Ejemplo: ASB-L3N",
        label_visibility="collapsed",
    )

    st.write("")

    if st.button(
        "Consultar",
        use_container_width=True,
        type="primary",
    ):
        procesar_consulta(
            placa,
            token,
        )


def vista_dashboard():
    resultado = st.session_state.get(
        "resultado"
    )

    if not resultado:
        reset_a_inicio()
        st.rerun()

    fecha_entrada, hora_entrada = (
        minuto_a_fecha_y_hora(
            resultado["entrada_minuto"]
        )
    )

    fecha_salida, hora_salida = (
        minuto_a_fecha_y_hora(
            resultado["minuto_actual"]
        )
    )

    st.markdown(
        f"""
        <div class="placa-vehicular">
            <div class="titulo-etiqueta">
                PLACA
            </div>

            <div class="valor">
                {resultado["placa"]}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    columna_1, columna_2 = st.columns(2)

    with columna_1:
        st.markdown(
            f"""
            <div class="tarjeta">
                <p style="
                    font-size:0.75rem;
                    margin:0;
                    opacity:0.6;
                    letter-spacing:0.5px;
                ">
                    FECHA ENTRADA
                </p>

                <b style="font-size:1.05rem;">
                    {fecha_entrada}
                </b>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="tarjeta">
                <p style="
                    font-size:0.75rem;
                    margin:0;
                    opacity:0.6;
                    letter-spacing:0.5px;
                ">
                    HORA ENTRADA
                </p>

                <b style="font-size:1.05rem;">
                    {hora_entrada}
                </b>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with columna_2:
        st.markdown(
            f"""
            <div class="tarjeta">
                <p style="
                    font-size:0.75rem;
                    margin:0;
                    opacity:0.6;
                    letter-spacing:0.5px;
                ">
                    FECHA SALIDA
                </p>

                <b style="font-size:1.05rem;">
                    {fecha_salida}
                </b>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="tarjeta">
                <p style="
                    font-size:0.75rem;
                    margin:0;
                    opacity:0.6;
                    letter-spacing:0.5px;
                ">
                    HORA SALIDA
                </p>

                <b style="font-size:1.05rem;">
                    {hora_salida}
                </b>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="tarjeta-monto">
            <p style="
                font-size:0.75rem;
                margin:0;
                opacity:0.7;
            ">
                Tiempo:
                {resultado["horas_transcurridas"]}h
                {resultado["minutos_restantes"]}m
                ({resultado["horas_cobradas"]}
                hora(s) cobradas)
            </p>

            <div style="
                font-size:2.2rem;
                font-weight:800;
                color:#FFF;
                margin-top:4px;
            ">
                S/ {resultado["monto"]:.2f}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "PAGAR",
        use_container_width=True,
        type="primary",
    ):
        st.session_state["vista"] = "pago"
        st.rerun()

    if st.button(
        "Cancelar",
        use_container_width=True,
        type="secondary",
    ):
        reset_a_inicio()
        st.rerun()


def vista_pago(token):
    resultado = st.session_state.get(
        "resultado"
    )

    if not resultado:
        reset_a_inicio()
        st.rerun()

    st.markdown(
        f"""
        <p style="
            text-align:center;
            margin-bottom:5px;
            color:#FFFFFF;
            font-size:1.3rem;
            font-weight:700;
        ">
            Pago con billetera digital
        </p>

        <p style="
            text-align:center;
            margin-bottom:5px;
            color:#888;
            font-size:0.9rem;
        ">
            Monto a transferir
        </p>

        <p style="
            text-align:center;
            font-size:2.2rem;
            font-weight:800;
            color:#FFFFFF;
            margin-bottom:20px;
        ">
            S/ {resultado["monto"]:.2f}
        </p>
        """,
        unsafe_allow_html=True,
    )

    texto_qr = (
        f"PLACA: {resultado['placa']}\n"
        f"MONTO: S/ {resultado['monto']:.2f}\n"
        f"CODIGO: {resultado['codigo_pago']}"
    )

    imagen_qr = generar_qr_demo(
        texto_qr
    )

    st.image(
        imagen_qr,
        width=250,
    )

    st.write("")

    if st.button(
        "Confirmar transferencia",
        use_container_width=True,
        type="primary",
    ):
        try:
            confirmar_pago_baserow(
                resultado["row_id"],
                token,
            )

            st.session_state["vista"] = "exito"

            st.rerun()

        except Exception as error:
            st.error(
                "No se pudo confirmar el pago "
                f"en Baserow: {str(error)}"
            )

    if st.button(
        "Atrás",
        use_container_width=True,
        type="secondary",
    ):
        st.session_state["vista"] = "dashboard"
        st.rerun()


def vista_exito():
    resultado = st.session_state.get(
        "resultado"
    )

    if not resultado:
        reset_a_inicio()
        st.rerun()

    with st.spinner(
        "Procesando pago..."
    ):
        time.sleep(1.2)

    st.markdown(
        f"""
        <div class="exito-contenedor">
            <div class="exito-marco">
                <div style="
                    width:24px;
                    height:12px;
                    border-left:3px solid #FFF;
                    border-bottom:3px solid #FFF;
                    transform:rotate(-45deg);
                    margin-top:-4px;
                ">
                </div>
            </div>

            <div class="exito-titulo">
                Transacción procesada
            </div>

            <p style="
                color:#FFFFFF;
                line-height:1.6;
                margin-bottom:20px;
                font-size:1rem;
            ">
                El pago ha sido confirmado correctamente.
                La barrera de salida ha sido habilitada
                para su vehículo.
            </p>

            <p style="
                font-size:0.75rem;
                color:#888;
                letter-spacing:1px;
            ">
                ID: {resultado["codigo_pago"]}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.success(
        "¡Pago realizado con éxito!"
    )

    time.sleep(3.0)

    reset_a_inicio()
    st.rerun()


# ============================================================
# CONTROL PRINCIPAL
# ============================================================

def main():
    st.set_page_config(
        page_title="Cochera Automatizada",
        layout="centered",
    )

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