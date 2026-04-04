"""
Script de prueba manual: genera un certificado individual vía línea de comandos.
Uso: python scripts/run_certificador.py "Nombre del Alumno" "real|pase de fase"
"""

import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.certificador import Certificador


async def main():
    if len(sys.argv) < 3:
        print("\n❌ Faltan parámetros.")
        print("Uso: python scripts/run_certificador.py \"Nombre del Alumno\" \"real|pase de fase\"")
        print("Ejemplo: python scripts/run_certificador.py \"Juan Perez\" \"real\"")
        return

    nombre = sys.argv[1]
    tipo = sys.argv[2]

    cert = Certificador()
    try:
        resultado = await cert.crear_certificado(nombre, tipo)

        if resultado["status"] == "success":
            print(f"\n✅ ¡ÉXITO!")
            print(f"Archivo: {resultado['output_path']}")
            print(f"Tiempo: {resultado['elapsed_s']}s")
        else:
            error = resultado.get("error", {})
            print(f"\n❌ ERROR: {error.get('message', 'Error desconocido')}")
    finally:
        await cert.close()


if __name__ == "__main__":
    asyncio.run(main())
