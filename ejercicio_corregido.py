"""
GESTIÓN DE CLIENTES - VERSIÓN CORREGIDA (desarrollo seguro)
Basada en ejercicio_prueba.py

Antes de ejecutar, instalar la librería de contraseñas (una sola vez):
    pip install bcrypt

Cada corrección está marcada con un comentario "# [Cn]" para poder
relacionarla con la tabla de vulnerabilidades del informe.

  C1  Contraseñas guardadas como hash (bcrypt), nunca en texto plano
  C2  La contraseña ya no se muestra en pantalla (getpass + sin imprimirla)
  C3  Mensaje de login genérico (no revela si el usuario existe)
  C4  Bloqueo temporal tras varios intentos fallidos (anti fuerza bruta)
  C5  No se puede sobrescribir un usuario existente
  C6  Registro controlado: solo el primer usuario es libre; los demás
      los crea un administrador
  C7  Roles (mínimo privilegio): eliminar, cambiar deuda y crear usuarios
      solo para admin
  C8  Validación y sanitización de TODAS las entradas
  C9  Control de errores: el programa no se cae con datos inválidos
  C10 Datos personales enmascarados al mostrarlos
  C11 Clientes como diccionarios (se acabaron los índices cruzados que
      corrompían los datos)
  C12 Bug del menú "Mostrar" corregido
  C13 Confirmación antes de eliminar
  C14 Registro de auditoría (sin guardar datos sensibles)
  C15 Código ordenado en funciones y con main() (sin variables globales
      modificables con "global")
"""

import getpass
import logging
import re
import time

import bcrypt  # Librería externa oficial de PyPI

# ----------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------
MAX_INTENTOS = 3
SEGUNDOS_BLOQUEO = 30
MAX_LARGO_CLAVE = 64  # bcrypt solo usa los primeros 72 bytes
MONTO_MAXIMO = 100_000_000
TIPOS_CLIENTE = {101: "Plata", 102: "Oro", 103: "Platino"}
ROL_ADMIN = "admin"
ROL_OPERADOR = "operador"

# [C14] Auditoría: se registra QUIÉN hizo QUÉ, pero nunca claves ni RUN.
logging.basicConfig(
    filename="auditoria.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)

# "Base de datos" en memoria
clientes = {}
usuarios = {}
intentos_fallidos = {}

# Hash de mentira: se usa cuando el usuario no existe, para que el login
# tarde lo mismo exista o no el usuario [C3].
HASH_FALSO = bcrypt.hashpw(b"clave-falsa-123", bcrypt.gensalt())


# ----------------------------------------------------------------------
# [C8] [C9] LECTURA Y VALIDACIÓN DE ENTRADAS
# ----------------------------------------------------------------------
def limpiar_texto(texto):
    """Quita caracteres de control y espacios repetidos."""
    imprimible = "".join(c for c in texto if c.isprintable())
    return " ".join(imprimible.split())


def leer_texto(mensaje, patron, error):
    """Pide un texto hasta que cumpla el patrón permitido (lista blanca)."""
    while True:
        valor = limpiar_texto(input(mensaje))
        if re.fullmatch(patron, valor):
            return valor
        print(f"  ⚠ {error}")


def leer_entero(mensaje, minimo, maximo):
    """Pide un número entero dentro de un rango, sin caerse si escriben letras."""
    while True:
        texto = input(mensaje).strip()
        try:
            numero = int(texto)
        except ValueError:
            print("  ⚠ Debe ingresar un número entero.")
            continue
        if minimo <= numero <= maximo:
            return numero
        print(f"  ⚠ El número debe estar entre {minimo} y {maximo}.")


def confirmar(mensaje):
    return input(mensaje).strip().lower() in ("si", "sí")


def normalizar_run(texto):
    """Valida el RUN chileno (con dígito verificador) y lo deja como 12345678-5."""
    limpio = texto.replace(".", "").replace("-", "").replace(" ", "").upper()
    if not re.fullmatch(r"[0-9]{7,8}[0-9K]", limpio):
        return None
    cuerpo, digito = limpio[:-1], limpio[-1]
    suma, factor = 0, 2
    for numero in reversed(cuerpo):
        suma += int(numero) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    esperado = "K" if resto == 10 else "0" if resto == 11 else str(resto)
    return f"{cuerpo}-{digito}" if digito == esperado else None


def leer_run(mensaje):
    while True:
        run = normalizar_run(input(mensaje))
        if run:
            return run
        print("  ⚠ RUN inválido. Ejemplo: 12.345.678-5")


def leer_nombre(mensaje):
    return leer_texto(
        mensaje,
        r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' -]{2,50}",
        "Solo letras, espacios y guion (2 a 50 caracteres).",
    )


def leer_direccion(mensaje):
    return leer_texto(
        mensaje,
        r"[\w .,#°/\-]{5,100}",
        "Dirección inválida (5 a 100 caracteres, sin símbolos raros).",
    )


def leer_fono(mensaje):
    return leer_texto(
        mensaje, r"\+?[0-9]{8,12}", "Teléfono inválido. Ejemplo: +56912345678"
    )


def leer_correo(mensaje):
    return leer_texto(
        mensaje,
        r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,200}\.[A-Za-z]{2,}",
        "Correo inválido. Ejemplo: nombre@dominio.cl",
    )


def leer_tipo(mensaje):
    print("--------------------------------------------")
    for codigo, nombre in TIPOS_CLIENTE.items():
        print(f" CODIGO : {codigo} - {nombre}.")
    print("--------------------------------------------")
    while True:
        codigo = leer_entero(mensaje, 0, 999)
        if codigo in TIPOS_CLIENTE:
            return codigo
        print("  ⚠ Código de tipo no existe.")


# ----------------------------------------------------------------------
# [C10] ENMASCARAR DATOS PERSONALES
# ----------------------------------------------------------------------
def enmascarar_run(run):
    return "****" + run[-5:]  # ****678-5


def enmascarar_correo(correo):
    usuario, dominio = correo.split("@", 1)
    return usuario[0] + "***@" + dominio


def enmascarar_fono(fono):
    return "*" * (len(fono) - 4) + fono[-4:]


# ----------------------------------------------------------------------
# MENÚS
# ----------------------------------------------------------------------
def menu_usuarios():
    print("================================")
    print("   M E N Ú  U S U A R I O S     ")
    print("================================")
    print("       1.-  INICIAR SESIÓN      ")
    print("       2.-  REGISTRAR USUARIO   ")
    print("       3.-  Salir               ")
    print("================================")


def menu_principal(sesion):
    print("================================")
    print("   M E N Ú  P R I N C I P A L   ")
    print("================================")
    print("       1.- (C) INGRESAR         ")
    print("       2.- (R) MOSTRAR          ")
    print("       3.- (U) MODIFICAR        ")
    print("       4.- (D) ELIMINAR         ")
    print("       5.- (E) Cerrar sesión    ")
    if sesion["rol"] == ROL_ADMIN:
        print("       6.- CREAR USUARIO        ")
    print("================================")


def menu_mostrar():
    print("================================")
    print("     M E N Ú  M O S T R A R     ")
    print("================================")
    print("       1.- MOSTRAR TODO         ")
    print("       2.- MOSTRAR UNO          ")
    print("       3.- MOSTRAR PARCIAL      ")
    print("       4.- VOLVER               ")
    print("================================")


# ----------------------------------------------------------------------
# USUARIOS: REGISTRO Y LOGIN
# ----------------------------------------------------------------------
def clave_es_segura(clave):
    """Política de contraseñas: 8 a 64 caracteres, mayúscula, minúscula, número y símbolo."""
    return (
        8 <= len(clave) <= MAX_LARGO_CLAVE
        and re.search(r"[a-z]", clave) is not None
        and re.search(r"[A-Z]", clave) is not None
        and re.search(r"[0-9]", clave) is not None
        and re.search(r"[^A-Za-z0-9]", clave) is not None
    )


def registrar_usuario(rol):
    print("=======================================")
    print("        REGISTRO DE USUARIO            ")
    print("=======================================")
    username = leer_texto(
        "NOMBRE DE USUARIO (4-20 letras, números o _): ",
        r"[A-Za-z0-9_]{4,20}",
        "Nombre de usuario inválido.",
    ).lower()

    # [C5] No se permite pisar un usuario que ya existe
    if username in usuarios:
        print("  ⚠ Ese nombre de usuario no está disponible.")
        return

    # [C2] getpass: lo que se escribe no se ve en pantalla
    while True:
        clave = getpass.getpass("CONTRASEÑA (8-64, mayús., minús., número y símbolo): ")
        if not clave_es_segura(clave):
            print("  ⚠ Contraseña débil: revise los requisitos.")
            continue
        if clave != getpass.getpass("REPITA LA CONTRASEÑA: "):
            print("  ⚠ Las contraseñas no coinciden.")
            continue
        break

    nombre = leer_nombre("NOMBRE   : ")
    apellidos = leer_nombre("APELLIDOS: ")
    correo = leer_correo("CORREO   : ")

    # [C1] Se guarda SOLO el hash (con "sal" automática), nunca la clave
    hash_clave = bcrypt.hashpw(clave.encode("utf-8"), bcrypt.gensalt())

    usuarios[username] = {
        "id": len(usuarios) + 1,
        "username": username,
        "hash": hash_clave,
        "nombre": nombre,
        "apellidos": apellidos,
        "correo": correo,
        "rol": rol,
    }
    logging.info("Usuario creado: %s (rol=%s)", username, rol)
    print("Usuario registrado correctamente.")


def esta_bloqueado(username):
    registro = intentos_fallidos.get(username)
    return registro is not None and time.monotonic() < registro["bloqueado_hasta"]


def registrar_fallo(username):
    registro = intentos_fallidos.setdefault(
        username, {"fallos": 0, "bloqueado_hasta": 0.0}
    )
    registro["fallos"] += 1
    if registro["fallos"] >= MAX_INTENTOS:
        registro["bloqueado_hasta"] = time.monotonic() + SEGUNDOS_BLOQUEO
        registro["fallos"] = 0
        logging.warning("Usuario bloqueado temporalmente: %s", username)


def iniciar_sesion():
    """Devuelve el usuario si el login es correcto; si no, None."""
    username = limpiar_texto(input("Ingrese nombre de usuario: ")).lower()
    clave = getpass.getpass("Ingrese contraseña: ")

    # [C4] Anti fuerza bruta
    if esta_bloqueado(username):
        print(f"Demasiados intentos. Espere {SEGUNDOS_BLOQUEO} segundos.")
        return None

    usuario = usuarios.get(username)
    hash_a_comparar = usuario["hash"] if usuario else HASH_FALSO
    clave_ok = len(clave) <= MAX_LARGO_CLAVE and bcrypt.checkpw(
        clave.encode("utf-8"), hash_a_comparar
    )

    if usuario and clave_ok:
        intentos_fallidos.pop(username, None)
        logging.info("Login correcto: %s", username)
        # [C2] Ya no se imprime la contraseña
        print(f"Bienvenido {usuario['nombre']} {usuario['apellidos']} - id: {usuario['id']}.")
        return usuario

    # [C3] Mismo mensaje exista o no el usuario
    registrar_fallo(username)
    logging.warning("Login fallido para: %s", username)
    print("Usuario o contraseña incorrectos.")
    return None


# ----------------------------------------------------------------------
# [C7] CONTROL DE PERMISOS
# ----------------------------------------------------------------------
def requiere_admin(sesion, accion):
    if sesion["rol"] == ROL_ADMIN:
        return True
    logging.warning("Acceso denegado a %s para la acción: %s", sesion["username"], accion)
    print("  ⚠ No tiene permisos para esta acción.")
    return False


# ----------------------------------------------------------------------
# CLIENTES (CRUD)
# ----------------------------------------------------------------------
def imprimir_cliente(cliente, completo=False):
    """[C10] Por defecto muestra datos enmascarados. [C11] Usa claves, no índices."""
    run = cliente["run"] if completo else enmascarar_run(cliente["run"])
    correo = cliente["correo"] if completo else enmascarar_correo(cliente["correo"])
    fono = cliente["fono"] if completo else enmascarar_fono(cliente["fono"])
    print(f" ID            : {cliente['id']}")
    print(f" RUN           : {run}")
    print(f" NOMBRE        : {cliente['nombre']} {cliente['apellido']}")
    print(f" DIRECCION     : {cliente['direccion']}")
    print(f" FONO          : {fono}")
    print(f" CORREO        : {correo}")
    print(f" TIPO          : {cliente['tipo']} - {TIPOS_CLIENTE[cliente['tipo']]}")
    print(f" MONTO CRÉDITO : {cliente['monto']}")
    print(f" DEUDA         : {cliente['deuda']}")
    print("-----------------------------------------")


def ingresar_cliente(sesion):
    print("=================================")
    print("     INGRESAR DATOS CLIENTE      ")
    print("=================================")
    run = leer_run("INGRESE RUN : ")
    if any(c["run"] == run for c in clientes.values()):
        print("  ⚠ Ya existe un cliente con ese RUN.")
        return
    nombre = leer_nombre("INGRESE NOMBRE : ")
    apellido = leer_nombre("INGRESE APELLIDO : ")
    direccion = leer_direccion("INGRESE DIRECCION : ")
    fono = leer_fono("INGRESE TELEFONO : ")
    correo = leer_correo("INGRESE CORREO : ")
    tipo = leer_tipo("Ingrese el codigo del Tipo de Cliente: ")
    monto = leer_entero("INGRESE MONTO CREDITO : ", 0, MONTO_MAXIMO)

    id_cliente = max(clientes, default=0) + 1
    clientes[id_cliente] = {
        "id": id_cliente,
        "run": run,
        "nombre": nombre,
        "apellido": apellido,
        "direccion": direccion,
        "fono": fono,
        "correo": correo,
        "tipo": tipo,
        "monto": monto,
        "deuda": 0,
    }
    # [C14] Se registra el ID, no los datos personales
    logging.info("Cliente %s creado por %s", id_cliente, sesion["username"])


def mostrar_todo():
    print("=================================")
    print("  MUESTRA DE TODOS LOS CLIENTES  ")
    print("=================================")
    if not clientes:
        print("No hay clientes registrados.")
        return
    for cliente in clientes.values():
        imprimir_cliente(cliente)


def mostrar_uno(sesion):
    print("=================================")
    print("   MUESTRA DE DATOS PARTICULAR   ")
    print("=================================")
    id_cliente = leer_entero("\n Ingrese el ID del Cliente : ", 1, 10**9)
    cliente = clientes.get(id_cliente)
    if cliente is None:  # [C9] antes esto hacía caer el programa
        print("  ⚠ No existe un cliente con ese ID.")
        return
    # Solo el admin ve los datos completos; los demás, enmascarados
    imprimir_cliente(cliente, completo=sesion["rol"] == ROL_ADMIN)
    logging.info("Cliente %s consultado por %s", id_cliente, sesion["username"])


def mostrar_parcial():
    print("=======================================")
    print("   MUESTRA PARCIALMENTE LOS CLIENTES   ")
    print("=======================================")
    if not clientes:
        print("No hay clientes registrados.")
        return
    cantidad = leer_entero("\nCantidad de Clientes a Mostrar : ", 1, len(clientes))
    for cliente in list(clientes.values())[:cantidad]:
        imprimir_cliente(cliente)


def mostrar(sesion):
    while True:
        menu_mostrar()
        opcion = leer_entero("  INGRESE OPCIÓN : ", 1, 4)
        # [C12] Ahora es if / elif / else bien encadenado
        if opcion == 1:
            mostrar_todo()
        elif opcion == 2:
            mostrar_uno(sesion)
        elif opcion == 3:
            mostrar_parcial()
        else:
            break
        input("\n PRESIONE ENTER PARA CONTINUAR")


CAMPOS_EDITABLES = [
    ("nombre", "NOMBRE", leer_nombre),
    ("apellido", "APELLIDO", leer_nombre),
    ("direccion", "DIRECCION", leer_direccion),
    ("fono", "TELEFONO", leer_fono),
    ("correo", "CORREO", leer_correo),
]


def modificar_cliente(sesion):
    print("===================================")
    print("      MODULO MODIFICAR CLIENTE     ")
    print("===================================")
    mostrar_todo()
    if not clientes:
        return
    id_cliente = leer_entero("\n ID del Cliente que desea Modificar : ", 1, 10**9)
    original = clientes.get(id_cliente)
    if original is None:
        print("  ⚠ No existe un cliente con ese ID.")
        return

    nuevo = dict(original)  # copia: si algo falla, el original no se daña [C11]
    for clave, etiqueta, lector in CAMPOS_EDITABLES:
        if confirmar(f"¿DESEA MODIFICAR {etiqueta}? [SI/NO] "):
            nuevo[clave] = lector(f"NUEVO {etiqueta}: ")

    if confirmar("¿DESEA MODIFICAR EL TIPO? [SI/NO] "):
        nuevo["tipo"] = leer_tipo("INGRESE EL TIPO : ")

    if confirmar("¿DESEA MODIFICAR EL MONTO DE CREDITO? [SI/NO] "):
        nuevo["monto"] = leer_entero(
            "INGRESE MONTO DE CREDITO : ", nuevo["deuda"], MONTO_MAXIMO
        )

    # [C7] Solo el admin puede tocar la deuda
    if sesion["rol"] == ROL_ADMIN and confirmar("¿DESEA MODIFICAR LA DEUDA? [SI/NO] "):
        nuevo["deuda"] = leer_entero("INGRESE DEUDA : ", 0, nuevo["monto"])

    clientes[id_cliente] = nuevo
    logging.info("Cliente %s modificado por %s", id_cliente, sesion["username"])
    print("Cliente modificado correctamente.")


def eliminar_cliente(sesion):
    print("===================================")
    print("      MODULO ELIMINAR CLIENTE      ")
    print("===================================")
    if not requiere_admin(sesion, "eliminar cliente"):
        return
    mostrar_todo()
    if not clientes:
        return
    id_cliente = leer_entero("ID del Cliente que desea Eliminar : ", 1, 10**9)
    if id_cliente not in clientes:  # [C9] antes: KeyError
        print("  ⚠ No existe un cliente con ese ID.")
        return
    if confirmar(f"¿Seguro que desea eliminar el cliente {id_cliente}? [SI/NO] "):  # [C13]
        del clientes[id_cliente]
        logging.info("Cliente %s eliminado por %s", id_cliente, sesion["username"])
        print("Cliente eliminado.")


# ----------------------------------------------------------------------
# FLUJO PRINCIPAL
# ----------------------------------------------------------------------
def sesion_activa(sesion):
    while True:
        menu_principal(sesion)
        opcion = leer_entero("INGRESE OPCIÓN: ", 1, 6)
        if opcion == 1:
            ingresar_cliente(sesion)
        elif opcion == 2:
            mostrar(sesion)
        elif opcion == 3:
            modificar_cliente(sesion)
        elif opcion == 4:
            eliminar_cliente(sesion)
        elif opcion == 5:
            if confirmar("¿DESEA CERRAR SESIÓN [SI/NO]: "):
                logging.info("Logout: %s", sesion["username"])
                return
        elif requiere_admin(sesion, "crear usuario"):
            registrar_usuario(ROL_OPERADOR)


def main():
    while True:
        menu_usuarios()
        opcion = leer_entero("INGRESE OPCIÓN: ", 1, 3)
        if opcion == 1:
            sesion = iniciar_sesion()
            if sesion:
                sesion_activa(sesion)
        elif opcion == 2:
            # [C6] Solo el PRIMER usuario puede registrarse libremente (admin)
            if usuarios:
                print("  ⚠ Solo un administrador puede crear usuarios nuevos.")
            else:
                print("Configuración inicial: este usuario será el administrador.")
                registrar_usuario(ROL_ADMIN)
        elif confirmar("¿DESEA SALIR [SI/NO]: "):
            break


# [C15] El programa solo arranca si se ejecuta este archivo directamente
if __name__ == "__main__":
    main()
    