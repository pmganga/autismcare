# AutismCare

| Increment | Weeks | Status |
|---|---|---|
| 1. Therapist directory | 3–5 | Built |
| 2a. Screening: questionnaire and risk scoring | 6 | Built |
| 2b. Screening: PDF report and referral flow | 7 | Built |
| 3. AI teaching assistant | 8–9 | Not started |

## Screening (Week 6)

| Requirement | Where it's built |
|---|---|
| FR 1.1 Intake questionnaire (20 yes/no items, one per screen) | `screening/views.py`, `templates/screening/`, `static/js/screening.js` |
| FR 2.1 Risk score within 1.5 s, Low/Medium/High tiers | `screening/scoring.py` (0–2 Low, 3–7 Medium, 8–20 High) |
| NFR 4 Anonymous: no personal information stored | `screening/models.py` (a test checks there are no personal-data fields) |
| NFR 7 Disclaimer on every screening screen | `templates/screening/_disclaimer.html` |
| FR 2.2 PDF guidance report (indicators, next steps, all answers, disclaimer) | `screening/report.py`; `/screening/result/<id>/report.pdf` |
| High result leads straight into a location-based therapist search (sequence diagram, alt tier == HIGH) | `templates/screening/result.html` + `templates/directory/_search_panel.html` |
| Medium/Low: guidance plus rescreen reminder, downloadable as a calendar file (.ics) | `screening/rescreen.py`, `screening/reminder.py` |
| End-to-end test of the screening-to-referral flow | `screening/tests_week7.py` (`EndToEndReferralTests`) |

```powershell
python manage.py seed_questions               # loads 20 PLACEHOLDER items
python manage.py seed_questions --file q.json # loads licensed text once permission is granted
```

**Questionnaire wording:** using M-CHAT-R/F in an app requires permission from its
authors. Until permission is granted, `seed_questions` loads placeholder text with
the same structure (20 yes/no items; items 2, 5 and 12 reverse-scored). The
scoring rules work unchanged once the real wording is loaded.

**Encryption at rest (NFR 3):** planned at the infrastructure level, using a
managed PostgreSQL host with AES-256 storage encryption turned on.

## Therapist directory (Weeks 3–5)

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
python manage.py seed_questions       # screening questionnaire (placeholder text)
python manage.py createsuperuser      # your admin account
python manage.py runserver
```

Then open:
- http://127.0.0.1:8000/ for the home page
- http://127.0.0.1:8000/find/ to search for a therapist
- http://127.0.0.1:8000/login/ for therapist login (demo account: `therapist01@demo.autismcare.test` / `DemoTherapist2026!`)
- http://127.0.0.1:8000/admin/ for the admin panel (go to *Licence verifications*, select rows, then Approve)

## Switch to PostgreSQL

Without a `.env` file the app uses a local SQLite file. To switch, run this in
your own PowerShell window. It asks for your `postgres` password, creates the
database and user, writes `.env`, and loads the tables and demo data:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_postgres.ps1
python manage.py createsuperuser
```

## Test on a phone

1. Connect the phone to the same Wi-Fi as the laptop. The setup script adds the laptop's Wi-Fi address to `DJANGO_ALLOWED_HOSTS`.
2. Run `python manage.py runserver 0.0.0.0:8000` and allow it through Windows Firewall if asked.
3. On the phone, open `http://<laptop Wi-Fi IP>:8000/` (find the IP with `ipconfig`).

Note: phone browsers only allow **"Use my location"** on HTTPS sites (or on
`localhost`), so over plain Wi-Fi use the typed-town search. GPS will work once
the app is deployed with HTTPS.

## Production-style server

`runserver` is for development only and handles one request at a time. To run
several worker processes (needed for the NFR 1 load test):

```powershell
uvicorn config.asgi:application --host 127.0.0.1 --port 8000 --workers 3
```

On the Linux deployment target (SRS 2.4), use gunicorn or uvicorn with one worker per CPU core.

## Tests

```powershell
python manage.py test
```

## Load test (NFR 1)

Results on the development laptop (4 CPU cores shared between the server and
Locust; SQLite; 10,000 clinics; 100 users each searching every 1–3 s):

| Setup | Median | 95th percentile | Requests/s | Errors |
|---|---|---|---|---|
| `runserver`, first search version | 3,100 ms | 8,600 ms | 17 | 0 |
| `runserver`, optimised search | 710 ms | 5,800 ms | 27 | 0 |
| uvicorn, 3 workers, optimised search | **350 ms** | 1,700 ms | 25 | 0 |

A single search takes 30–70 ms. Under load the median meets the 500 ms target,
but the 95th percentile doesn't yet, because the laptop runs out of CPU. Still to do:
re-run on PostgreSQL with Locust on a separate machine, or on the cloud deployment.

The results are capped at the 30 nearest therapists (3 clinics each), with a
total count. This keeps responses small on 3G.

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
| GET | `/api/screening/questionnaire/` | public |
| POST | `/api/screenings/` `{child_age_months, answers: [{question, value}]}`, which returns a result and a one-time `token` | public, anonymous |
| GET | `/api/screenings/<id>/?token=` | whoever holds the token |
| GET | `/api/screenings/<id>/report/?token=`, which returns the PDF report | whoever holds the token |

Authenticated API calls send the header `Authorization: Token <token>`.

## Notes

- Licence documents are stored in `private_media/` and are never served publicly. Only staff can open them, through the admin panel.
- Geocoding uses OpenStreetMap Nominatim (free, roughly 1 request per second). If an address can't be found, the therapist enters coordinates by hand.
- All demo data uses fake names and `@demo.autismcare.test` emails. Run `python manage.py seed --reset` to recreate it.
