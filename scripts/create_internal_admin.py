"""Explicit operator-only provisioning; never invoked during application startup."""

import argparse
import getpass
import sys
import warnings

from pydantic import ValidationError

from app.core.database import close_database
from app.core.errors import NuvlyError
from app.modules.auth.schemas import InternalUserCreateRequest
from app.modules.auth.service import AuthService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crear un administrador nuevo sin modificar cuentas existentes.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        print("Usa una terminal interactiva para introducir la contraseña de forma oculta.", file=sys.stderr)
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Contraseña nueva: ")
            confirmation = getpass.getpass("Confirmar contraseña: ")
        if password != confirmation:
            print("Las contraseñas no coinciden.", file=sys.stderr)
            return 1
        payload = InternalUserCreateRequest(
            email=args.email,
            name=args.name,
            password=password,
            internalRole="admin",
        )
        if not payload.name.strip():
            print("El nombre es obligatorio.", file=sys.stderr)
            return 1
        AuthService().create_internal_user(
            email=payload.email,
            name=payload.name,
            password=payload.password,
            internal_role=payload.internalRole,
        )
    except ValidationError, getpass.GetPassWarning:
        # ValidationError may include the submitted password; never print it.
        print(
            "Datos inválidos o terminal sin entrada oculta. Revisa email, nombre y política de contraseña.",
            file=sys.stderr,
        )
        return 1
    except NuvlyError as exc:
        print(f"No se creó el administrador ({exc.code}). Las cuentas existentes no se modifican.", file=sys.stderr)
        return 1
    except EOFError, KeyboardInterrupt:
        print("Creación cancelada.", file=sys.stderr)
        return 1
    except Exception:
        print("No se pudo completar la creación. Revisa la conexión y la configuración del entorno.", file=sys.stderr)
        return 1
    finally:
        close_database()
    print("Administrador creado. La contraseña no se muestra ni se guarda en archivos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
