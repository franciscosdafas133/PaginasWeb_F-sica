import time
import math
from io import BytesIO

import requests
import streamlit as st
import qrcode


BASEROW_TOKEN = "hVxGMBTks1fAopHga6Vqm2BKi2H5gnQj"
BASEROW_API_URL = "https://api.baserow.io"
TABLE_ID = "1032007"

CAMPO_PLACA = "Numero_Placas"
CAMPO_ENTRADA_MINUTO = "entrada_minuto"
CAMPO_MINUTO_ACTUAL = "minuto_actual"

TARIFA_HORA = 5.00


def normalizar_placa(placa):
    return placa.strip().upper().replace(" ", "")


def obtener_minuto_actual():
    return int(time.time() // 60)


def buscar_placa_en_baserow(placa):
    placa_buscada = normalizar_placa(placa)

    url = f"{BASEROW_API_URL}/api/database/rows/table/{TABLE_ID}/"

    headers = {
        "Authorization": f"Token {BASEROW_TOKEN}"
    }

    params = {
        "user_field_names": "true",
        "search": placa_buscada,
        "size": 100
    }

    filas = []

    while url:
        r = requests.get(url, headers=headers, params=params, timeout=15)

        if r.status_code != 200:
            raise Exception(f"Error consultando Baserow: {r.status_code} - {r.text}")

        data = r.json()
        filas.extend(data.get("results", []))

        url = data.get("next")
        params = None

    for fila in filas:
        placa_fila = normalizar_placa(str(fila.get(CAMPO_PLACA, "")))

        if placa_fila == placa_buscada:
            return fila

    return None


def actualizar_minuto_actual(row_id, minuto_actual):
    url = f"{BASEROW_API_URL}/api/database/rows/table/{TABLE_ID}/{row_id}/?user_field_names=true"

    headers = {
        "Authorization": f"Token {BASEROW_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        CAMPO_MINUTO_ACTUAL: minuto_actual
    }

    r = requests.patch(url, headers=headers, json=data, timeout=15)

    if r.status_code not in [200, 202]:
        raise Exception(f"Error actualizando minuto_actual: {r.status_code} - {r.text}")

    return r.json()


def calcular_pago(fila):
    row_id = fila.get("id")
    placa = fila.get(CAMPO_PLACA, "")

    entrada_minuto = fila.get(CAMPO_ENTRADA_MINUTO)

    if entrada_minuto in [None, ""]:
        raise Exception("La placa existe, pero el campo entrada_minuto está vacío.")

    entrada_minuto = int(float(entrada_minuto))

    minuto_actual = obtener_minuto_actual()

    minutos_estacionado = minuto_actual - entrada_minuto

    if minutos_estacionado < 0:
        return {
            "ok": False,
            "error": "entrada_minuto está en el futuro",
            "row_id": row_id,
            "placa": placa,
            "entrada_minuto": entrada_minuto,
            "minuto_actual": minuto_actual,
            "minutos_estacionado": minutos_estacionado
        }

    horas_cobradas = math.ceil(minutos_estacionado / 60)

    if horas_cobradas < 1:
        horas_cobradas = 1

    monto = horas_cobradas * TARIFA_HORA

    codigo_pago = f"PARK-{normalizar_placa(placa)}-{row_id}-{minuto_actual}"

    actualizar_minuto_actual(row_id, minuto_actual)

    return {
        "ok": True,
        "row_id": row_id,
        "placa": placa,
        "entrada_minuto": entrada_minuto,
        "minuto_actual": minuto_actual,
        "minutos_estacionado": minutos_estacionado,
        "horas_cobradas": horas_cobradas,
        "tarifa_hora": TARIFA_HORA,
        "monto": monto,
        "codigo_pago": codigo_pago
    }


def generar_qr_demo(texto):
    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=3
    )

    qr.add_data(texto)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer


st.set_page_config(
    page_title="Consulta de pago por placa",
    page_icon="🚗",
    layout="centered"
)


st.title("Consulta de pago por placa")
st.write("Ingrese la placa del vehículo para calcular el tiempo estacionado y el monto a pagar.")

placa = st.text_input("Placa", placeholder="Ejemplo: ASB-L3N")

if st.button("Consultar pago"):
    if not placa.strip():
        st.warning("Ingrese una placa.")
    else:
        try:
            fila = buscar_placa_en_baserow(placa)

            if fila is None:
                st.error("No se encontró la placa en Baserow.")
            else:
                resultado = calcular_pago(fila)

                if not resultado["ok"]:
                    st.error("El cálculo salió negativo. entrada_minuto está mayor que minuto_actual.")

                    st.subheader("Valores encontrados")
                    st.code(
                        f"entrada_minuto = {resultado['entrada_minuto']}\n"
                        f"minuto_actual = {resultado['minuto_actual']}\n"
                        f"minutos_estacionado = {resultado['minutos_estacionado']}"
                    )

                    st.warning("Para que funcione, entrada_minuto debe ser menor que minuto_actual.")

                else:
                    st.success("Placa encontrada.")

                    st.subheader("Datos del estacionamiento")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.metric("Placa", resultado["placa"])
                        st.metric("Entrada minuto", resultado["entrada_minuto"])
                        st.metric("Minuto actual", resultado["minuto_actual"])
                        st.metric("Minutos estacionado", resultado["minutos_estacionado"])

                    with col2:
                        st.metric("Horas cobradas", resultado["horas_cobradas"])
                        st.metric("Tarifa por hora", f"S/ {resultado['tarifa_hora']:.2f}")
                        st.metric("Monto total", f"S/ {resultado['monto']:.2f}")

                    st.subheader("Cálculo realizado")
                    st.code(
                        f"{resultado['minuto_actual']} - {resultado['entrada_minuto']} "
                        f"= {resultado['minutos_estacionado']} minutos"
                    )

                    st.subheader("Código de pago")
                    st.code(resultado["codigo_pago"])

                    texto_qr = (
                        f"PLACA: {resultado['placa']}\n"
                        f"ENTRADA_MINUTO: {resultado['entrada_minuto']}\n"
                        f"MINUTO_ACTUAL: {resultado['minuto_actual']}\n"
                        f"MINUTOS ESTACIONADO: {resultado['minutos_estacionado']}\n"
                        f"HORAS COBRADAS: {resultado['horas_cobradas']}\n"
                        f"MONTO: S/ {resultado['monto']:.2f}\n"
                        f"CODIGO: {resultado['codigo_pago']}"
                    )

                    qr_img = generar_qr_demo(texto_qr)

                    st.subheader("QR demo")
                    st.image(qr_img, caption="QR demo para prueba del proyecto")

                    st.info("Se actualizó minuto_actual en Baserow al momento de consultar.")

        except Exception as e:
            st.error("Ocurrió un error.")
            st.code(str(e))