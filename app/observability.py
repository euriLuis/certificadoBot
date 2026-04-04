import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Directorio de logs
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
JSON_LOG_FILE = LOG_DIR / "certificador_metrics.jsonl"

class JsonFormatter(logging.Formatter):
    """Formateador para logs estructurados en JSON."""
    def format(self, record):
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Incluir extras si existen
        if hasattr(record, "extra_fields"):
            log_obj.update(record.extra_fields)
        
        return json.dumps(log_obj, ensure_ascii=False)

# Configurar logger JSON
json_handler = logging.FileHandler(JSON_LOG_FILE, encoding='utf-8')
json_handler.setFormatter(JsonFormatter())
metrics_logger = logging.getLogger("Certificador.Metrics")
metrics_logger.addHandler(json_handler)
metrics_logger.setLevel(logging.INFO)

class MetricsCollector:
    """Coleccionista simple de métricas en memoria y persistencia en logs JSON."""
    def __init__(self):
        self.counts = {
            "autofill_success": 0,
            "autofill_failed": 0,
            "export_success": 0,
            "export_failed": 0,
            "token_refresh_success": 0,
            "token_refresh_failed": 0,
            "rate_limit_429": 0
        }
    
    def increment(self, metric_name: str):
        if metric_name in self.counts:
            self.counts[metric_name] += 1
            
    def record_job_telemetry(self, job_data: Dict[str, Any]):
        """Registra la telemetría completa de un trabajo en el log JSON."""
        metrics_logger.info("Job Telemetry", extra={"extra_fields": job_data})

    def get_summary(self) -> Dict[str, int]:
        return self.counts

# Instancia global
metrics = MetricsCollector()
