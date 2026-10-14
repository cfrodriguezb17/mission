"""Un único servicio cron para el plan gratuito de Railway (horas UTC)."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys


def commands_for(now):
    commands = []
    if now.hour == 3 and now.minute < 15:
        commands.append(["update_tipos_cambio"])
    elif now.hour == 3 and now.minute < 30:
        commands.append(["sync_indicadores"])
    return commands + [["generar_alertas", "--limite", "1000"]]


def run(now=None):
    failed = False
    for command in commands_for(now or datetime.now(timezone.utc)):
        result = subprocess.run(
            [sys.executable, "manage.py", *command],
            cwd=Path(__file__).resolve().parent.parent,
            check=False,
        )
        failed = result.returncode != 0 or failed
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(run())
