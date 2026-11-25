#!/usr/bin/env bash
# Build step on the Linux server (SRS 2.4): install, collect static files, update the database.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py seed_questions
