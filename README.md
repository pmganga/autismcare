# AutismCare: Increment 1 (Therapist Directory)

The SRS's Weeks 3–5 increment: database schemas, therapist and clinic profiles,
map and geospatial search, and search filters.

| Requirement | Where it's built |
|---|---|
| FR 1.2 Authentication (12-character passwords, lock after 5 failures) | `accounts/backends.py`, `accounts/services.py` |
| FR 3.1 Radius search (5–50 km, GPS or typed location) | `directory/search.py`, `static/js/find.js` |
| FR 3.2 Filters (specialization, insurance, consultation mode) | `directory/search.py` |
| FR 3.3 Therapist profile management and licence upload | `directory/views.py`, `directory/api_views.py` |
| Admin licence verification | `directory/admin.py` (approve/reject actions) |
| NFR 1 Search under 500 ms at 10k clinics / 100 users | bounding box + indexed lat/lng; `perf/locustfile.py` |
| SRS 3.1 UI (low-saturation colours, 48 px targets, inline errors) | `static/css/style.css`, `templates/` |
| SRS 3.4 5-second timeout and list-only fallback | `directory/geocoding.py`, `static/js/find.js` |

## Run it

```powershell
cd C:\Users\Peter\autismcare
.\venv\Scripts\activate
python manage.py migrate
python manage.py seed                 # demo therapists and filter options
python manage.py createsuperuser      # your admin account
python manage.py runserver
```

Then open:
- http://127.0.0.1:8000/ for the home page
- http://127.0.0.1:8000/find/ to search for a therapist
- http://127.0.0.1:8000/login/ for therapist login (demo account: `therapist01@demo.autismcare.test` / `DemoTherapist2026!`)
- http://127.0.0.1:8000/admin/ for the admin panel (go to *Licence verifications*, select rows, then Approve)

## Switch to PostgreSQL

Without a `.env` file the app uses a local SQLite file. To use PostgreSQL:

1. Open **SQL Shell (psql)** from the Start menu and log in as `postgres`. Then run:
   ```sql
   CREATE USER autismcare_user WITH PASSWORD 'choose-a-strong-password';
   CREATE DATABASE autismcare OWNER autismcare_user;
   ALTER USER autismcare_user CREATEDB;  -- lets the test runner create its test database
   ```
2. Copy `.env.example` to `.env` and put the same password in `DB_PASSWORD`.
3. Run `python manage.py migrate`, `python manage.py seed` and `python manage.py createsuperuser` again.

## Tests

```powershell
python manage.py test
```

## Load test (NFR 1)

```powershell
python manage.py seed --bulk 10000
pip install locust
locust -f perf/locustfile.py --host http://127.0.0.1:8000 --users 100 --spawn-rate 10 --run-time 2m --headless
```

## API

| Method | URL | Who |
|---|---|---|
| POST | `/api/auth/register/`, `/api/auth/login/`, `/api/auth/logout/` | therapists |
| GET/PATCH | `/api/therapists/me/` | logged-in therapist |
| GET/POST | `/api/therapists/me/license/` | logged-in therapist |
| GET/POST | `/api/clinics/`, GET/PATCH/DELETE `/api/clinics/<id>/` | logged-in therapist (own clinics) |
| GET | `/api/therapists/search/?lat=&lng=&radius=&specialization=&insurance=&mode=` | public |
| GET | `/api/therapists/<id>/` | public (verified only) |
| GET | `/api/filter-options/`, `/api/geocode/?q=` | public |

Authenticated API calls send the header `Authorization: Token <token>`.

## Notes

- Licence documents are stored in `private_media/` and are never served publicly. Only staff can open them, through the admin panel.
- Geocoding uses OpenStreetMap Nominatim (free, roughly 1 request per second). If an address can't be found, the therapist enters coordinates by hand.
- All demo data uses fake names and `@demo.autismcare.test` emails. Run `python manage.py seed --reset` to recreate it.
