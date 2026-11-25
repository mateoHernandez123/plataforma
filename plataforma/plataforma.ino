#include <Arduino.h>
#include <stdlib.h>
#include <string.h>

// Misma base de la primera version.
// Los dos motores reciben siempre la misma potencia.
// D11 queda en HIGH por si un enable del segundo driver sigue ahi.
const int EN_EXTRA = 11;

const int RPWM_IZQ = 5;
const int LPWM_IZQ = 6;
const int REN_IZQ = 7;
const int LEN_IZQ = 8;

const int RPWM_DER = 9;
const int LPWM_DER = 10;
const int REN_DER = 12;
const int LEN_DER = 13;

const int TRIG = 2;
const int ECHO = 3;

const int PWM_MAXIMO = 150;
const int PASO_RAMPA = 10;
const unsigned long INTERVALO_RAMPA = 20;
const float DISTANCIA_MINIMA = 20.0;

const unsigned long TIMEOUT = 400;
const unsigned long INTERVALO_SENSOR = 100;
const unsigned long PAUSA_GIRO = 200;

const bool INVERTIR_IZQ = false;
const bool INVERTIR_DER = false;

char movimiento = 'S';
int velocidad = 0;

float distancia = -1;
bool obstaculo = false;

unsigned long ultimoComando = 0;
unsigned long ultimaMedicion = 0;

char buffer[20];
byte posicion = 0;

int actualIzq = 0;
int actualDer = 0;
int magnitudAplicada = 0;
unsigned long ultimaRampa = 0;

unsigned long pausaIzq = 0;
unsigned long pausaDer = 0;

void escribirMotor(int rpwm, int lpwm, int pwm) {
    if (pwm > 0) {
        analogWrite(lpwm, 0);
        analogWrite(rpwm, pwm);
        return;
    }

    if (pwm < 0) {
        analogWrite(rpwm, 0);
        analogWrite(lpwm, -pwm);
        return;
    }

    analogWrite(rpwm, 0);
    analogWrite(lpwm, 0);
}

void controlarMotor(
    int rpwm, int lpwm,
    int objetivo,
    int &actual,
    unsigned long &pausa
) {
    unsigned long ahora = millis();

    if (objetivo == 0) {
        if (actual != 0) {
            escribirMotor(rpwm, lpwm, 0);
            actual = 0;
        }
        return;
    }

    if (actual != 0 && ((actual > 0) != (objetivo > 0))) {
        escribirMotor(rpwm, lpwm, 0);
        actual = 0;
        pausa = ahora + PAUSA_GIRO;
        return;
    }

    if ((long)(ahora - pausa) < 0) {
        return;
    }

    if (actual != objetivo) {
        escribirMotor(rpwm, lpwm, objetivo);
        actual = objetivo;
    }
}

void medirDistancia() {
    digitalWrite(TRIG, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG, LOW);

    unsigned long duracion = pulseIn(ECHO, HIGH, 25000UL);

    if (duracion == 0) {
        distancia = -1;
    } else {
        distancia = duracion * 0.0343f / 2.0f;
    }

    // Sin eco el frente esta libre. Solo frena con un eco real a 20 cm o menos.
    obstaculo = distancia >= 0 && distancia <= DISTANCIA_MINIMA;

    Serial.print(F("DIST,"));
    Serial.print(distancia, 1);
    Serial.print(',');
    Serial.println(obstaculo ? 1 : 0);
}

void procesarMensaje(char *mensaje) {
    char direccion = mensaje[0];

    if (mensaje[1] != ',' || strchr("FBLRS", direccion) == NULL) {
        movimiento = 'S';
        velocidad = 0;
        return;
    }

    char *fin;
    long porcentaje = strtol(mensaje + 2, &fin, 10);

    if (fin == mensaje + 2 || *fin != '\0' ||
        porcentaje < 0 || porcentaje > 100) {
        movimiento = 'S';
        velocidad = 0;
        return;
    }

    movimiento = direccion;
    velocidad = map(porcentaje, 0, 100, 0, PWM_MAXIMO);
    ultimoComando = millis();
}

void leerSerial() {
    while (Serial.available() > 0) {
        char c = Serial.read();

        if (c == '\n') {
            buffer[posicion] = '\0';
            procesarMensaje(buffer);
            posicion = 0;
        } else if (c != '\r') {
            if (posicion < sizeof(buffer) - 1) {
                buffer[posicion++] = c;
            } else {
                posicion = 0;
                movimiento = 'S';
                velocidad = 0;
            }
        }
    }
}

int acercar(int valor, int meta) {
    if (valor < meta) {
        valor += PASO_RAMPA;
        if (valor > meta) {
            valor = meta;
        }
    } else if (valor > meta) {
        valor -= PASO_RAMPA;
        if (valor < meta) {
            valor = meta;
        }
    }
    return valor;
}

int signo(int valor) {
    if (valor > 0) {
        return 1;
    }
    if (valor < 0) {
        return -1;
    }
    return 0;
}

void actualizarMotores() {
    int izq = 0;
    int der = 0;

    if (millis() - ultimoComando > TIMEOUT) {
        movimiento = 'S';
    }

    // A 20 cm o menos: frena avance y giros. La marcha atras sigue.
    bool caminoLibre = !obstaculo;

    switch (movimiento) {
        case 'F':
            if (caminoLibre) {
                izq = velocidad;
                der = velocidad;
            }
            break;

        case 'B':
            izq = -velocidad;
            der = -velocidad;
            break;

        case 'L':
            if (caminoLibre) {
                izq = -velocidad;
                der = velocidad;
            }
            break;

        case 'R':
            if (caminoLibre) {
                izq = velocidad;
                der = -velocidad;
            }
            break;
    }

    if (INVERTIR_IZQ) {
        izq = -izq;
    }
    if (INVERTIR_DER) {
        der = -der;
    }

    int magnitud = abs(izq);
    if (abs(der) > magnitud) {
        magnitud = abs(der);
    }

    if (millis() - ultimaRampa >= INTERVALO_RAMPA) {
        ultimaRampa = millis();
        magnitudAplicada = acercar(magnitudAplicada, magnitud);
    }

    controlarMotor(
        RPWM_IZQ, LPWM_IZQ,
        signo(izq) * magnitudAplicada,
        actualIzq, pausaIzq
    );
    controlarMotor(
        RPWM_DER, LPWM_DER,
        signo(der) * magnitudAplicada,
        actualDer, pausaDer
    );
}

void setup() {
    digitalWrite(REN_IZQ, LOW);
    digitalWrite(LEN_IZQ, LOW);
    digitalWrite(REN_DER, LOW);
    digitalWrite(LEN_DER, LOW);
    digitalWrite(EN_EXTRA, LOW);

    pinMode(REN_IZQ, OUTPUT);
    pinMode(LEN_IZQ, OUTPUT);
    pinMode(REN_DER, OUTPUT);
    pinMode(LEN_DER, OUTPUT);
    pinMode(EN_EXTRA, OUTPUT);

    pinMode(RPWM_IZQ, OUTPUT);
    pinMode(LPWM_IZQ, OUTPUT);
    pinMode(RPWM_DER, OUTPUT);
    pinMode(LPWM_DER, OUTPUT);

    pinMode(TRIG, OUTPUT);
    pinMode(ECHO, INPUT);
    digitalWrite(TRIG, LOW);

    escribirMotor(RPWM_IZQ, LPWM_IZQ, 0);
    escribirMotor(RPWM_DER, LPWM_DER, 0);
    actualIzq = 0;
    actualDer = 0;

    Serial.begin(9600);
    ultimoComando = millis();

    digitalWrite(REN_IZQ, HIGH);
    digitalWrite(LEN_IZQ, HIGH);
    digitalWrite(REN_DER, HIGH);
    digitalWrite(LEN_DER, HIGH);
    digitalWrite(EN_EXTRA, HIGH);
}

void loop() {
    leerSerial();

    if (millis() - ultimaMedicion >= INTERVALO_SENSOR) {
        ultimaMedicion = millis();
        medirDistancia();
    }

    actualizarMotores();
}
