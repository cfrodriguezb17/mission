#!/bin/sh
set -eu

# Ejecutar una vez al preparar una instalación DEMO; retirar luego del pre-deploy.
python manage.py migrate --noinput
python manage.py seed_data
python manage.py migrate --check
