"""
Script de prueba manual: genera un certificado individual via linea de comandos.
Uso: python scripts/run_certificador.py "Nombre del Alumno" "real|pase de fase|elite"
"""

import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.certificador import Certificador


async def main():
    if len(sys.argv) < 3:
        print("\nFaltan parametros.")
        print('Uso: python scripts/run_certificador.py "Nombre del Alumno" "real|pase de fase|elite"')
        print('Ejemplo: python scripts/run_certificador.py "Juan Perez" "elite"')
        return

    nombre = sys.argv[1]
    tipo = sys.argv[2]

    cert = Certificador()
    try:
        resultado = await cert.crear_certificado(nombre, tipo)

        if resultado["status"] == "success":
            print("\nEXITO")
            print(f"Archivo: {resultado['output_path']}")
            print(f"Tiempo: {resultado['elapsed_s']}s")
        else:
            error = resultado.get("error", {})
            print(f"\nERROR: {error.get('message', 'Error desconocido')}")
    finally:
        await cert.close()


if __name__ == "__main__":
    asyncio.run(main())
