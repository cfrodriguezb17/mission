import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"fecha": self.formatTime(record), "nivel": record.levelname,
                   "logger": record.name, "mensaje": record.getMessage()}
        for key in ("sincronizacion", "pais", "motivo", "metodo", "ruta", "usuario", "duracion_ms", "estado_http", "tipo_error"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False, default=str)
