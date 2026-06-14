#!/usr/bin/env bash
# Build script for Render. Migrations are handled by preDeployCommand in render.yaml.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
