#!/usr/bin/env bash
# Build step on the Linux server (SRS 2.4): install, collect static files, update the database.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
# Migrations use Neon's direct connection; the pooled one is for app traffic
DATABASE_URL="${DATABASE_URL_UNPOOLED:-$DATABASE_URL}" python manage.py migrate --noinput
DATABASE_URL="${DATABASE_URL_UNPOOLED:-$DATABASE_URL}" python manage.py seed_questions
