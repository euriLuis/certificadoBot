"""
Prueba separada del flujo de autofill para una plantilla de Canva.

Uso:
python scripts/test_autofill_template.py
python scripts/test_autofill_template.py EAHBZ9RY-qU "Trader Demo"
"""

import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.autofill_utils import build_text_autofill_data
from app.certificador import Certificador


async def main():
    template_id = sys.argv[1] if len(sys.argv) > 1 else "EAHBZ9RY-qU"
    nombre = sys.argv[2] if len(sys.argv) > 2 else "Trader Elite Demo"

    cert = Certificador(load_env=True)
    try:
        client = await cert._get_client()
        fecha = cert._get_fecha_actual()

        meta = await client.get_brand_template(template_id)
        dataset_response = await client.get_brand_template_dataset(template_id)
        dataset = dataset_response.get("dataset") or {}

        print("\nTEMPLATE")
        print(f"- id: {meta.get('brand_template', {}).get('id', template_id)}")
        print(f"- title: {meta.get('brand_template', {}).get('title', '(sin titulo)')}")

        print("\nDATASET")
        if not dataset:
            print("- sin campos autofillables")
            return

        for field_name, field_def in dataset.items():
            print(f"- {field_name}: {field_def.get('type')}")

        autofill_data, resolved_fields = build_text_autofill_data(
            dataset,
            {
                "nombre": nombre,
                "fecha": fecha,
            },
        )

        print("\nMAPPING")
        if not resolved_fields:
            print("- no se pudo resolver ningun campo de texto")
            return

        for semantic_key, real_field_name in resolved_fields.items():
            print(f"- {semantic_key} -> {real_field_name}")

        print("\nPAYLOAD")
        for field_name, field_value in autofill_data.items():
            print(f"- {field_name}: {field_value}")

        response = await client.create_autofill_job(
            brand_template_id=template_id,
            data=autofill_data,
            title=f"Prueba Autofill {nombre}",
        )
        job_id = response["job"]["id"]
        print("\nJOB")
        print(f"- id: {job_id}")
        print(f"- status: {response['job']['status']}")

        job_data = await cert._poll_con_backoff(client, job_id, "autofill")
        result = job_data.get("result", {})
        design = result.get("design", {})
        design_id = design.get("id") or result.get("design_id")

        print("\nRESULT")
        print(f"- final_status: {job_data.get('status')}")
        print(f"- design_id: {design_id}")
    finally:
        await cert.close()


if __name__ == "__main__":
    asyncio.run(main())
