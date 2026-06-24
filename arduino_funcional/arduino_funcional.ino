#include <Servo.h>

Servo barrera;

const int pinRaspberry = 9;
const int trigPin = 2;
const int echoPin = 3;
const int pinServo = 8;

const int distanciaLimite = 15;

const int cerrado = 0;
const int abierto = 90;

bool ordenProcesada = false;

long medirDistancia() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(5);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duracion = pulseIn(echoPin, HIGH, 30000);

  if (duracion == 0) {
    return 999;
  }

  long distancia = duracion * 0.034 / 2;
  return distancia;
}

void abrirBarrera() {
  Serial.println("ABRIENDO BARRERA");
  barrera.write(abierto);
}

void cerrarBarrera() {
  Serial.println("CERRANDO BARRERA");
  barrera.write(cerrado);
}

void setup() {
  Serial.begin(9600);

  pinMode(pinRaspberry, INPUT);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  barrera.attach(pinServo);
  barrera.write(cerrado);

  Serial.println("====================================");
  Serial.println("SISTEMA ARDUINO LISTO");
  Serial.println("Pin 9  = senal desde Raspberry");
  Serial.println("Pin 2  = TRIG ultrasonico");
  Serial.println("Pin 3  = ECHO ultrasonico");
  Serial.println("Pin 8  = servo MG90S");
  Serial.println("Condicion: HIGH + distancia <= 15 cm");
  Serial.println("====================================");
}

void loop() {
  int permisoRaspberry = digitalRead(pinRaspberry);
  long distancia = medirDistancia();

  if (permisoRaspberry == HIGH && !ordenProcesada) {
    Serial.print("PERMISO HIGH RECIBIDO. Distancia: ");
    Serial.print(distancia);
    Serial.println(" cm");

    if (distancia <= distanciaLimite) {
      Serial.println("CONDICIONES CUMPLIDAS: HIGH + AUTO CERCA");

      abrirBarrera();

      Serial.println("Barrera levantada minimo 20 segundos...");
      delay(10000);

      while (medirDistancia() <= distanciaLimite) {
        long d = medirDistancia();
        Serial.print("Auto aun detectado. Distancia: ");
        Serial.print(d);
        Serial.println(" cm. Manteniendo barrera arriba...");
        delay(500);
      }

      Serial.println("Ya no hay auto cerca. Bajando barrera...");
      cerrarBarrera();

      ordenProcesada = true;
    } else {
      Serial.println("Hay permiso, pero NO hay auto a menos de 15 cm. No abre.");
    }
  }

  if (permisoRaspberry == LOW) {
    ordenProcesada = false;
  }

  delay(300);
}