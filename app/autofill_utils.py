from typing import Dict, Iterable, Tuple


FIELD_ALIASES = {
    "nombre": ("nombre", "Nombre", "NOMBRE", "name", "Name"),
    "fecha": ("fecha", "Fecha", "FECHA", "date", "Date"),
}


def _normalize_field_name(field_name: str) -> str:
    return (field_name or "").strip().casefold()


def build_text_autofill_data(
    dataset: Dict[str, Dict[str, str]],
    values: Dict[str, str],
    aliases: Dict[str, Iterable[str]] | None = None,
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, str]]:
    """
    Construye el objeto `data` para Canva respetando los nombres exactos del dataset.
    """
    aliases = aliases or FIELD_ALIASES
    dataset = dataset or {}
    values = values or {}

    normalized_dataset = {
        _normalize_field_name(field_name): field_name for field_name in dataset.keys()
    }

    data: Dict[str, Dict[str, str]] = {}
    resolved_fields: Dict[str, str] = {}

    for semantic_key, value in values.items():
        if value is None:
            continue

        candidates = [semantic_key, *aliases.get(semantic_key, ())]
        matched_field_name = None

        for candidate in candidates:
            real_field_name = normalized_dataset.get(_normalize_field_name(candidate))
            if real_field_name:
                matched_field_name = real_field_name
                break

        if not matched_field_name:
            continue

        field_def = dataset.get(matched_field_name) or {}
        if field_def.get("type") != "text":
            continue

        data[matched_field_name] = {
            "type": "text",
            "text": str(value),
        }
        resolved_fields[semantic_key] = matched_field_name

    return data, resolved_fields
