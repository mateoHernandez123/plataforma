
import time
import tkinter as tk
from tkinter import messagebox
import serial
from serial.tools import list_ports

BAUDIOS = 9600
INTERVALO = 100  # Enviar cada 100 ms

TECLAS = {
    "Up": "F", "w": "F",
    "Down": "B", "s": "B",
    "Left": "L", "a": "L",
    "Right": "R", "d": "R"
}

NOMBRES = {
    "F": "AVANZAR",
    "B": "RETROCEDER",
    "L": "GIRAR IZQUIERDA",
    "R": "GIRAR DERECHA",
    "S": "DETENIDO"
}


class ControlAutito:
    def __init__(self, root):
        self.root = root
        self.root.title("Control de la Plataforma")
        self.root.geometry("440x600")
        self.root.configure(bg="#202938")
        self.root.resizable(False, False)

        self.serial = None
        self.listo = False
        self.comando = "S"
        self.teclas = []
        self.boton_actual = None
        self.botones = {}
        self.bloqueado = False
        self.buffer_serial = ""
        self.ultima_lectura = 0.0
        self.distancia_previa = None
        self.tiempo_previo = 0.0

        tk.Label(
            root, text="CONTROL DE LA PLATAFORMA",
            font=("Arial", 20, "bold"),
            bg="#202938", fg="white"
        ).pack(pady=20)

        # Conexion al Arduino
        frame = tk.Frame(root, bg="#202938")
        frame.pack(pady=8)

        tk.Label(
            frame, text="Puerto COM:",
            bg="#202938", fg="white"
        ).pack(side="left", padx=5)

        self.puerto = tk.StringVar(value="COM7")

        tk.Entry(
            frame, textvariable=self.puerto,
            width=8
        ).pack(side="left", padx=5)

        self.btn_conectar = tk.Button(
            frame, text="CONECTAR",
            command=self.conectar,
            bg="#3488ce", fg="white",
            width=12
        )
        self.btn_conectar.pack(side="left", padx=5)

        self.estado = tk.Label(
            root, text="Desconectado",
            bg="#202938", fg="#ff7777",
            font=("Arial", 11)
        )
        self.estado.pack(pady=8)

        self.indicador = tk.Label(
            root, text="DETENIDO",
            bg="#202938", fg="#75dfa8",
            font=("Arial", 17, "bold")
        )
        self.indicador.pack(pady=12)

        self.sensor = tk.Label(
            root, text="DISTANCIA: --\nVELOCIDAD: --",
            bg="#202938", fg="#d5deea",
            font=("Arial", 11),
            justify="center"
        )
        self.sensor.pack(pady=4)

        # Controles de direccion
        controles = tk.Frame(root, bg="#202938")
        controles.pack(pady=10)

        self.crear_boton(
            controles, "▲", "F", 0, 1
        )
        self.crear_boton(
            controles, "◀", "L", 1, 0
        )
        self.crear_boton(
            controles, "■ STOP", "S", 1, 1
        )
        self.crear_boton(
            controles, "▶", "R", 1, 2
        )
        self.crear_boton(
            controles, "▼", "B", 2, 1
        )

        # Control de velocidad
        tk.Label(
            root, text="VELOCIDAD",
            font=("Arial", 13, "bold"),
            bg="#202938", fg="white"
        ).pack(pady=(15, 3))

        self.velocidad = tk.IntVar(value=100)

        self.slider = tk.Scale(
            root,
            from_=0, to=100,
            orient="horizontal",
            variable=self.velocidad,
            length=330,
            bg="#202938",
            fg="white",
            troughcolor="#506784",
            highlightthickness=0
        )
        self.slider.pack()

        tk.Label(
            root,
            text="Mantene ↑ adelante o ↓ atras. Solta para parar.",
            font=("Arial", 9),
            bg="#202938", fg="#cccccc"
        ).pack(pady=8)

        # Teclado: bind_all para que las flechas anden
        # aunque el cursor este en el cuadro del puerto.
        root.bind_all("<KeyPress>", self.key_down)
        root.bind_all("<KeyRelease>", self.key_up)
        root.bind("<FocusOut>", self.focus_out)

        root.protocol("WM_DELETE_WINDOW", self.cerrar)

        self.enviar_periodicamente()

    def crear_boton(self, padre, texto, cmd, fila, col):
        boton = tk.Button(
            padre, text=texto,
            font=("Arial", 16, "bold"),
            width=7, height=2,
            bg="#bb4545" if cmd == "S" else "#3488ce",
            fg="white"
        )
        boton.grid(row=fila, column=col, padx=4, pady=4)
        self.botones[cmd] = boton

        if cmd == "S":
            boton.configure(command=self.detener)
        else:
            boton.bind(
                "<ButtonPress-1>",
                lambda e, c=cmd: self.iniciar_boton(c)
            )
            boton.bind(
                "<ButtonRelease-1>",
                lambda e: self.soltar_boton()
            )

    def iniciar_boton(self, cmd):
        if self.bloqueado and cmd in ("F", "L", "R"):
            return
        self.boton_actual = cmd
        self.actualizar_comando()

    def soltar_boton(self):
        self.boton_actual = None
        self.actualizar_comando()

    def key_down(self, event):
        if event.keysym == "space":
            self.detener()
            return "break"

        key = event.keysym
        if len(key) == 1:
            key = key.lower()

        if key in TECLAS and key not in self.teclas:
            if self.bloqueado and TECLAS[key] in ("F", "L", "R"):
                return "break"
            self.teclas.append(key)
            self.actualizar_comando()
            return "break"

    def key_up(self, event):
        key = event.keysym
        if len(key) == 1:
            key = key.lower()

        if key in self.teclas:
            self.teclas.remove(key)
            self.actualizar_comando()
            return "break"

    def focus_out(self, event):
        # Si se pierde el foco de la ventana,
        # el autito se detiene.
        self.detener()

    def actualizar_comando(self):
        if self.boton_actual:
            self.comando = self.boton_actual
        elif self.teclas:
            self.comando = TECLAS[self.teclas[-1]]
        else:
            self.comando = "S"

        if self.bloqueado and self.comando in ("F", "L", "R"):
            self.comando = "S"

        self.indicador.config(
            text=NOMBRES[self.comando],
            fg="#75dfa8" if self.comando == "S"
            else "#ffd479"
        )

    def detener(self):
        self.teclas.clear()
        self.boton_actual = None
        self.comando = "S"
        self.actualizar_comando()

    def conectar(self):
        if self.serial is not None:
            self.desconectar()
            return

        try:
            self.serial = serial.Serial(
                self.puerto.get().strip(),
                BAUDIOS,
                timeout=0,
                write_timeout=0.2
            )

            self.listo = False
            self.detener()
            self.estado.config(
                text="Conectando...",
                fg="#ffd479"
            )
            self.btn_conectar.config(text="DESCONECTAR")
            self.ultima_lectura = time.monotonic()
            self.distancia_previa = None

            # El Arduino Uno se reinicia al abrir COM.
            self.root.after(2000, self.conexion_lista)

        except (serial.SerialException, OSError) as e:
            messagebox.showerror("Error", str(e))

    def conexion_lista(self):
        if self.serial is not None:
            self.listo = True
            self.detener()
            self.estado.config(
                text="Arduino conectado",
                fg="#75dfa8"
            )

    def aplicar_bloqueo(self, bloqueado):
        if bloqueado == self.bloqueado:
            if bloqueado and self.comando in ("F", "L", "R"):
                self.comando = "S"
                self.indicador.config(text="OBSTACULO", fg="#ff7777")
            return

        self.bloqueado = bloqueado
        for cmd, boton in self.botones.items():
            if cmd in ("F", "L", "R"):
                boton.config(
                    state="disabled" if bloqueado else "normal",
                    bg="#506784" if bloqueado else "#3488ce"
                )

        if bloqueado and self.comando in ("F", "L", "R"):
            self.comando = "S"
            self.indicador.config(text="OBSTACULO", fg="#ff7777")
        elif not bloqueado:
            self.actualizar_comando()

    def leer_sensor(self):
        if self.serial is None:
            return

        try:
            esperando = self.serial.in_waiting
            if esperando:
                self.buffer_serial += self.serial.read(esperando).decode(
                    "ascii", errors="ignore"
                )
        except (serial.SerialException, OSError):
            self.desconexion_por_error()
            return

        if len(self.buffer_serial) > 1024:
            self.buffer_serial = ""

        while "\n" in self.buffer_serial:
            linea, self.buffer_serial = self.buffer_serial.split("\n", 1)
            partes = linea.strip().split(",")
            if len(partes) != 3 or partes[0] != "DIST":
                continue

            try:
                distancia = float(partes[1])
                estado = int(partes[2])
            except ValueError:
                continue

            self.ultima_lectura = time.monotonic()
            hay_obstaculo = distancia >= 0 and (estado == 1 or distancia <= 20)

            if distancia < 0:
                self.distancia_previa = None
                self.sensor.config(text="DISTANCIA: libre\nVELOCIDAD: --")
            else:
                ahora = time.monotonic()
                velocidad = 0.0
                if self.distancia_previa is not None:
                    dt = ahora - self.tiempo_previo
                    if dt > 0.02:
                        velocidad = (self.distancia_previa - distancia) / dt
                self.distancia_previa = distancia
                self.tiempo_previo = ahora
                self.sensor.config(
                    text=f"DISTANCIA: {distancia:.1f} cm\n"
                         f"VELOCIDAD: {velocidad:.0f} cm/s"
                )

            self.aplicar_bloqueo(hay_obstaculo)

    def enviar_periodicamente(self):
        self.leer_sensor()

        if self.serial is not None and self.listo:
            try:
                velocidad = self.velocidad.get()

                # Protocolo: DIRECCION,VELOCIDAD
                mensaje = f"{self.comando},{velocidad}\n"
                self.serial.write(mensaje.encode("ascii"))

            except (serial.SerialException, OSError):
                self.desconexion_por_error()

        self.root.after(INTERVALO, self.enviar_periodicamente)

    def desconexion_por_error(self):
        self.detener()
        self.listo = False

        if self.serial is not None:
            try:
                self.serial.close()
            except (serial.SerialException, OSError):
                pass

        self.serial = None
        self.buffer_serial = ""
        self.distancia_previa = None
        self.aplicar_bloqueo(False)
        self.sensor.config(text="DISTANCIA: --\nVELOCIDAD: --")
        self.estado.config(
            text="Conexion perdida", fg="#ff7777"
        )
        self.btn_conectar.config(text="CONECTAR")

    def desconectar(self):
        self.detener()

        if self.serial is not None:
            try:
                self.serial.write(b"S,0\n")
                self.serial.flush()
            except (serial.SerialException, OSError):
                pass

            try:
                self.serial.close()
            except (serial.SerialException, OSError):
                pass

        self.serial = None
        self.listo = False
        self.buffer_serial = ""
        self.distancia_previa = None
        self.aplicar_bloqueo(False)
        self.sensor.config(text="DISTANCIA: --\nVELOCIDAD: --")
        self.estado.config(
            text="Desconectado", fg="#ff7777"
        )
        self.btn_conectar.config(text="CONECTAR")

    def cerrar(self):
        self.desconectar()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ControlAutito(root)
    root.mainloop()
