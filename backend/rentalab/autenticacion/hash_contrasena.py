import getpass
import sys
import warnings

from argon2 import PasswordHasher
from argon2.exceptions import HashingError


def principal() -> int:
    if len(sys.argv) != 1:
        print(
            "Este comando no acepta argumentos; introduce la contraseña interactivamente.",
            file=sys.stderr,
        )
        return 1
    try:
        # Rechaza la lectura alternativa de getpass: las contraseñas no deben quedar en historiales.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            contrasena = getpass.getpass("Contraseña de demostración: ")
            confirmacion = getpass.getpass("Repite la contraseña: ")
        if not contrasena or len(contrasena) > 1024:
            print("La contraseña debe contener entre 1 y 1024 caracteres.", file=sys.stderr)
            return 1
        if contrasena != confirmacion:
            print("Las contraseñas no coinciden.", file=sys.stderr)
            return 1
        print(PasswordHasher().hash(contrasena))
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("No se pudo leer la contraseña en una terminal interactiva.", file=sys.stderr)
        return 1
    except HashingError:
        print("No se pudo generar el hash de contraseña.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
