#!/usr/bin/env bash
# Arranque de desarrollo para Linux: Django + Angular, con cierre conjunto.
set -Eeuo pipefail
set +m

if [[ "${1:-}" == '--help' || "${1:-}" == '-h' ]]; then
  cat <<'HELP'
Uso: ./run-local.sh
También: cd frontend && pnpm local

Inicia Django en http://127.0.0.1:8000 y Angular en http://localhost:4200.
Ctrl+C detiene ambos servicios y sus procesos hijos.

Requiere Linux, Bash 4.3+, setsid, curl, Node/pnpm, backend/.venv,
backend/.env, frontend/node_modules y PostgreSQL con migraciones aplicadas.
La preparación inicial se describe en README.md. No instala dependencias,
no aplica migraciones ni carga datos automáticamente.
HELP
  exit 0
fi
[[ $# -eq 0 ]] || { printf 'Argumento desconocido. Usa --help.\n' >&2; exit 2; }

fail() { printf '\nError: %s\n' "$*" >&2; exit 1; }
(( BASH_VERSINFO[0] > 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] >= 3) )) || fail 'Se requiere Bash 4.3 o posterior.'
for command_name in setsid curl node pnpm; do
  command -v "$command_name" >/dev/null || fail "Falta $command_name. Consulta la preparación inicial del README."
done

DATAPULSE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$DATAPULSE_ROOT/backend"
FRONTEND_DIR="$DATAPULSE_ROOT/frontend"
BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
[[ -x "$BACKEND_PYTHON" ]] || fail 'Falta backend/.venv. Crea el entorno Python e instala las dependencias del backend.'
[[ -r "$BACKEND_DIR/.env" ]] || fail 'Falta backend/.env. Copia .env.example y configura PostgreSQL.'
[[ -x "$FRONTEND_DIR/node_modules/.bin/ng" ]] || fail 'Faltan las dependencias del frontend. Ejecuta pnpm install --frozen-lockfile en frontend.'
"$BACKEND_PYTHON" -c 'import django, rest_framework, psycopg, corsheaders' || fail 'El entorno Python está incompleto. Instala backend/requirements-dev.txt.'

# Solo afecta a estos procesos; Django lee el resto de variables desde backend/.env.
export DJANGO_DEBUG=true
export DJANGO_SECURE_SSL_REDIRECT=false
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
export CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
export PYTHONUNBUFFERED=1

"$BACKEND_PYTHON" - <<'PY'
import socket
import sys

for port in (8000, 4200):
    try:
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', port))
    except OSError as error:
        print(f'No se puede usar el puerto {port}: {error}. Detén el servidor que ya lo usa y vuelve a ejecutar el script.', file=sys.stderr)
        sys.exit(1)
PY

printf 'Comprobando backend, PostgreSQL y migraciones…\n'
(
  cd -- "$BACKEND_DIR"
  "$BACKEND_PYTHON" manage.py check
  "$BACKEND_PYTHON" manage.py migrate --check
) || fail 'Revisa la conexión a PostgreSQL y aplica las migraciones pendientes desde backend con .venv/bin/python manage.py migrate.'

service_pids=()
cleanup() {
  trap '' INT TERM
  if (( ${#service_pids[@]} )); then
    printf '\nDeteniendo backend y frontend…\n'
    # Cada servicio tiene su propio grupo; nunca se detienen procesos ajenos.
    for service_pid in "${service_pids[@]}"; do
      kill -TERM -- "-$service_pid" 2>/dev/null || true
    done
    for ((attempt = 0; attempt < 50; attempt++)); do
      any_running=false
      for service_pid in "${service_pids[@]}"; do
        if kill -0 -- "-$service_pid" 2>/dev/null; then any_running=true; fi
      done
      if [[ "$any_running" == false ]]; then break; fi
      sleep 0.1
    done
    for service_pid in "${service_pids[@]}"; do
      kill -KILL -- "-$service_pid" 2>/dev/null || true
      wait "$service_pid" 2>/dev/null || true
    done
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_ready() {
  local service_name="$1" service_pid="$2" service_url="$3"
  local deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    kill -0 "$service_pid" 2>/dev/null || fail "$service_name terminó antes de iniciar. Revisa sus logs anteriores."
    if curl --noproxy '*' --silent --fail --max-time 1 "$service_url" >/dev/null; then return; fi
    sleep 0.2
  done
  fail "$service_name no respondió en 60 segundos. Revisa sus logs anteriores."
}

printf '\nIniciando Django…\n'
(
  cd -- "$BACKEND_DIR"
  exec setsid "$BACKEND_PYTHON" manage.py runserver 127.0.0.1:8000
) &
service_pids+=("$!")
wait_ready Backend "${service_pids[0]}" http://127.0.0.1:8000/health/

printf '\nIniciando Angular…\n'
(
  cd -- "$FRONTEND_DIR"
  exec setsid pnpm start --host 127.0.0.1 --port 4200
) &
service_pids+=("$!")
wait_ready Frontend "${service_pids[1]}" http://127.0.0.1:4200/

printf '\nDataPulse listo:\n  Frontend: http://localhost:4200\n  API:      http://127.0.0.1:8000/api/\n  Docs API: http://127.0.0.1:8000/api/docs/\n\nPulsa Ctrl+C para detener ambos. Los cambios de código se recargan automáticamente.\n\n'

service_status=0
wait -n "${service_pids[@]}" || service_status=$?
printf '\nUn servicio terminó (código %s); se cerrará también el otro.\n' "$service_status" >&2
if (( service_status == 0 )); then service_status=1; fi
exit "$service_status"
