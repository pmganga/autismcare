# AutismCare

Live site: https://autismcare-mjtb.onrender.com (free Render instance: the first visit after a quiet spell can take up to a minute while it wakes)

| Increment | Weeks | Status |
|---|---|---|
| 1. Therapist directory | 3–5 | Built |
| 2a. Screening: questionnaire and risk scoring | 6 | Built |
| 2b. Screening: PDF report and referral flow | 7 | Built |
| 3. AI teaching assistant | 8–9 | Built |

## AI teaching assistant (Weeks 8–9)

| Requirement / diagram | Where it's built |
|---|---|
| Teacher registers, logs in, adds learners by nickname only | `learning/views.py` (`/teach/register/`, `/teach/`) |
| Configure sensory settings: audio on/off, colour mode (soft, high contrast, dim), session length | `learning/forms.py` `SessionSettingsForm` |
| FR 4.1 High-contrast picture flashcards with simple word choices, one per screen, no animation | `templates/learning/play.html`, `static/js/play.js` |
| FR 4.2 Adaptive level: after every 3 cards, 3/3 correct = up, ≤1 = down, else same (levels 1–5) | `learning/engine.py` `evaluate()` |
| Calm audio cue (spoken word + soft chime) for correct; gentle visual hint for wrong | `static/js/play.js` |
| AI/NLP service generates new cards for the learner's level (local Qwen model via Ollama), in the background with built-in fallback | `learning/ai.py`, `learning/services.py` |
| Progress summary: accuracy, level change, response times, card by card | `templates/learning/summary.html` |

### AI setup (optional)

New cards are made by Qwen 3.5 (2B), an open-source
model that runs on the same computer through [Ollama](https://ollama.com). No
learner data leaves the machine and there is no per-request cost.

```powershell
ollama pull qwen3.5:2b                         # once (2.7 GB)
python manage.py generate_flashcards           # optional: fill the bank before a class or demo
```

- Background generation: on a laptop CPU the model takes 15–60 seconds per
  request, so it never holds up a learner. A session starts at once with the
  card bank, the model works in the background, and its cards join the bank
  when ready (status shown on the session summary).
- Picture check: every AI card is checked before use: a simple lowercase word,
  a real emoji whose official Unicode name contains that word (so 🚌 "bus" passes,
  💧 "water" is rejected), an allowed category, a not-child-safe word list, and
  no duplicates.
- Fallback: if Ollama isn't running (or `OLLAMA_URL` is empty, as on the
  cloud deployment), sessions use the 60 built-in cards (12 per level). The
  module always works.

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

### Questionnaire wording

Using M-CHAT-R/F in an app requires permission from its
authors. Until permission is granted, `seed_questions` loads placeholder text with
the same structure (20 yes/no items; items 2, 5 and 12 reverse-scored). The
scoring rules work unchanged once the real wording is loaded.

### Encryption at rest (NFR 3)

Planned at the infrastructure level, using a
managed PostgreSQL host with AES-256 storage encryption turned on.

## Therapist directory (Weeks 3–5)

| Requirement | Where it's built |
|---|---|
| FR 1.2 Authentication (12-character passwords, lock after 5 failures) | `accounts/backends.py`, `accounts/services.py` |
| FR 3.1 Radius search (5–50 km, GPS or typed location) | `directory/search.py`, `static/js/find.js` |
| FR 3.2 Filters (specialization, insurance, consultation mode) | `directory/search.py` |
| FR 3.3 Therapist profile management and licence upload | `directory/views.py`, `directory/api_views.py` |
| Admin licence verification | `directory/admin.py` (approve/reject actions) |
| Licence documents kept private in the database, so they survive server restarts | `directory/storage.py` |
| Admin "Monitor System Performance" (response times, database health, errors, usage) | `config/monitoring.py`, `/admin/performance/` |
| NFR 1 Search under 500 ms at 10k clinics / 100 users | `directory/search.py` (bounding box, indexed lat/lng, saved list of verified therapists); `perf/locustfile.py` |
| NFR 2 Pages under 2.5 MB, fast on 3G | `config/tests_page_weight.py`; see [Page size on 3G](#page-size-on-3g-nfr-2) |
| NFR 5 Accessibility (WCAG 2.1 AA) | `config/tests_accessibility.py`; see [Accessibility](#accessibility-nfr-5) |
| NFR 8 Works in Chrome, Edge, Firefox, Safari and phone browsers | `e2e/browsers.py`; see [Browsers](#browsers-nfr-8) |
| SRS 2.4 Linux server and PostgreSQL | `config/settings.py`, `build.sh`; see [Linux server](#linux-server-srs-24) |
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
- http://127.0.0.1:8000/teach/ for the teaching assistant (demo teacher: `teacher01@demo.autismcare.test` / `DemoTherapist2026!`)
- http://127.0.0.1:8000/admin/ for the admin panel (go to *Licence verifications*, select rows, then Approve)

## Switch to PostgreSQL

Without a `.env` file the app uses a local SQLite file. To switch, run this in
your own PowerShell window. It asks for your `postgres` password, creates the
database and user, writes `.env`, and loads the tables and demo data:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_postgres.ps1
python manage.py createsuperuser
python manage.py test                 # runs every test on PostgreSQL
```

The code uses no SQLite-only features (no raw SQL), so the same tests run on both.

## Test on a phone

1. Connect the phone to the same Wi-Fi as the laptop. The setup script adds the laptop's Wi-Fi address to `DJANGO_ALLOWED_HOSTS`.
2. Run `python manage.py runserver 0.0.0.0:8000` and allow it through Windows Firewall if asked.
3. On the phone, open `http://<laptop Wi-Fi IP>:8000/` (find the IP with `ipconfig`).

Note: phone browsers only allow "Use my location" on HTTPS sites (or on
`localhost`), so over plain Wi-Fi use the typed-town search. GPS will work once
the app is deployed with HTTPS.

## Production-style server on this computer

`runserver` is for development only and handles one request at a time. To run
several worker processes with the production settings (needed for the NFR 1 load test):

```powershell
$env:DJANGO_DEBUG = "False"
$env:DJANGO_SECRET_KEY = "any-long-random-text-for-local-testing"
$env:DJANGO_SSL_REDIRECT = "False"     # plain http on this computer
python manage.py collectstatic --noinput
uvicorn config.asgi:application --host 127.0.0.1 --port 8000 --workers 3
```

## Linux server (SRS 2.4)

The production target is a Linux server with PostgreSQL. With `DJANGO_DEBUG=False`:
- `DJANGO_SECRET_KEY` must be set, or the app refuses to start.
- HTTPS is required: http requests are redirected, cookies are sent over HTTPS only,
  and browsers are told to use HTTPS for 30 days (HSTS).
- CSS and JavaScript are served by WhiteNoise, compressed (Brotli and gzip), with
  file names that change when the file changes, so browsers can cache them for a year.
- `DATABASE_URL` points to the PostgreSQL database.

Environment variables to set on the host:

| Variable | Example |
|---|---|
| `DJANGO_SECRET_KEY` | a long random string |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `autismcare.onrender.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://autismcare.onrender.com` |
| `DATABASE_URL` | given by the PostgreSQL host |
| `OLLAMA_URL` | empty (no AI model on the server; the built-in cards are used) |

Build and start commands:

```bash
./build.sh
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2
```

`build.sh` installs the packages, collects the static files, updates the database
and loads the screening questions. Use about two gunicorn workers per CPU core.

`python manage.py check --deploy` passes with two warnings, both left on purpose:
HSTS for subdomains and HSTS preload. On a shared host address the subdomains
belong to other sites.

## Tests

```powershell
python manage.py test
```

## Load test (NFR 1)

Test setup: SQLite, 10,000 clinics, 100 users each searching every 1–3 s for 2 minutes.
The laptop has 2 CPU cores (Intel i5-6300U) shared by the server, Locust and other programs.

| Setup | Median | 95th percentile | Requests/s | Errors |
|---|---|---|---|---|
| `runserver`, first search version | 3,100 ms | 8,600 ms | 17 | 0 |
| `runserver`, optimised search | 710 ms | 5,800 ms | 27 | 0 |
| uvicorn, 3 workers, optimised search | 350 ms | 1,700 ms | 25 | 0 |
| uvicorn, 3 workers, current search (best run) | 91 ms | 380 ms | 45 | 0 |
| uvicorn, 3 workers, current search (worst run) | 140 ms | 1,300 ms | 42 | 0 |

After the changes below, 3 of 5 runs met the 500 ms target at the 95th percentile
(380, 370 and 440 ms; the others were 510 and 1,300 ms; the runs used 3 or 4 workers
while the last change was being made). The slow runs happened while
another program on the laptop was using a lot of CPU. The server's own time, from the
`Server-Timing` header, was 350 ms at the 95th percentile in the best run. The rest is
the wait inside Locust, which shares the same 2 cores. To do: repeat the test against
the cloud deployment, with Locust on this laptop.

What made the current search faster:
- The list of verified therapists for each filter is saved for 30 seconds instead of
  being rebuilt on every search. It is cleared at once when a licence, profile or
  specialization changes (`directory/signals.py`, and the admin approve and reject actions).
- The search reads each clinic link's number ID instead of the clinic's UUID, and
  loads clinic details only for the results shown.
- Results are built as plain dictionaries instead of with a DRF serializer.
- uvicorn uses the faster `httptools` HTTP parser, and Locust uses `FastHttpUser`,
  which needs less CPU on a shared laptop.

A single search takes 15–60 ms (about 20 ms on average). Results are capped at the
30 nearest therapists (3 clinics each), with a total count, which keeps responses small on 3G.

```powershell
python manage.py seed --bulk 10000
pip install locust==2.47.0
locust -f perf/locustfile.py --host http://127.0.0.1:8000 --users 100 --spawn-rate 10 --run-time 2m --headless
```

Locust reports two rows: the time it measured, and `search (server time)`, the
server's own time from the `Server-Timing` header that every response carries.

## Page size on 3G (NFR 2)

Measured on the wire with the production settings (compressed, first visit, nothing cached):

| Page | Files | Size |
|---|---|---|
| Home, login, screening intro | 2 | 3.8–3.9 KB |
| Screening questions | 3 | 5.9 KB |
| Teacher classroom, session setup | 2 | 4.2 KB |
| Play screen | 3 | 5.8 KB |
| Find a therapist (with filter options) | 4 | 7.2 KB |
| A 50 km search (30 results) | 1 | 4.1 KB |
| Map after a search: Leaflet plus about 15 map tiles | 19 | 229 KB |

The heaviest view, a search with the map, is about 240 KB, a tenth of the 2.5 MB limit.
On a repeat visit the CSS and JavaScript come from the browser cache, so only the
page itself (2–4 KB) is downloaded.

What keeps pages small:
- No images or web fonts: the flashcards are emoji and the text uses the phone's own font.
- Pages and API replies are compressed with gzip (`GZipMiddleware`, which in
  Django includes protection against the BREACH attack).
- CSS and JavaScript are compressed with Brotli or gzip by WhiteNoise and cached for a year.
- The map library loads only after a search, and the results list shows before the map.
  If the map takes more than 5 seconds, the page shows the list only (SRS 3.4).
- Search results are capped at the 30 nearest therapists.

`python manage.py test config.tests_page_weight` keeps every page under 50 KB compressed.

Load times in Chromium with the Chrome DevTools 3G presets (first visit, empty cache):

| Page | Fast 3G (1.6 Mbps, 563 ms round trip) | Slow 3G (500 kbps, 2 s round trip) |
|---|---|---|
| Home | 1.4 s | 4.4 s |
| Screening questions | 1.4 s | 4.4 s |
| Find a therapist | 1.4 s | 4.3 s |

The pages are so small that the time is almost all network round trips, not download
time. These were measured against this computer over plain http. On the live site,
the first visit adds the DNS lookup and the HTTPS handshake: about 1–2 more round trips.

## Browsers (NFR 8)

`python e2e/browsers.py` runs the main flows in real browser engines against a running
server: Chromium (Chrome and Edge), Firefox and WebKit (Safari), on desktop and on an
emulated Android phone (Pixel 7) and iPhone (iPhone 13). The map's outside requests
are blocked, so the list-only fallback (SRS 3.4) is tested too.

| Browser | Home | Screening | Screening by keyboard | Therapist search | Teaching session |
|---|---|---|---|---|---|
| Chrome / Edge (desktop) | pass | pass | pass | pass | pass |
| Firefox (desktop) | pass | pass | pass | pass | pass |
| Safari (desktop) | pass | pass | pass | pass | pass |
| Chrome on Android | pass | pass | — | pass | pass |
| Safari on iPhone | pass | pass | — | pass | pass |

Run it with the server started as in [Production-style server on this computer](#production-style-server-on-this-computer),
plus `$env:AI_FLASHCARDS_ENABLED = "False"` so the AI model doesn't use the CPU during the test:

```powershell
pip install playwright==1.65.2
playwright install chromium firefox webkit
python e2e/browsers.py
```

The CSS and JavaScript were also checked against browser support data
(`eslint-plugin-compat` and `doiuse`). Every feature used works in the last 2 versions of
Chrome, Edge, Firefox, Safari, Samsung Internet, Chrome on Android and Safari on iPhone,
and in every browser with more than 0.5% use in Kenya (back to Chrome 109). Without
JavaScript, the screening questionnaire still works as one long form.

## Accessibility (NFR 5)

`python manage.py test config.tests_accessibility` checks against WCAG 2.1 AA:

- Every main page, as a visitor, therapist, teacher and admin and with form errors:
  page language and title, one `h1` and no skipped heading levels, image alt text,
  a label for every form field, names for every button and link, unique ids,
  working `aria-describedby` links to help and error text, no positive `tabindex`,
  zoom not blocked, and `autocomplete` on name, email, phone and password fields.
- Every colour pair in `style.css`, including the three play modes (soft, high
  contrast, dim): text at least 4.5:1, control borders and focus outlines at least 3:1.

Fixed during the audit:
- Error and help text are now linked to their fields for screen readers.
- The colour-mode radio buttons are grouped with a fieldset and legend.
- The focus outline shows on the dark header and in the high-contrast and dim play modes.
- Input and answer-button borders were darkened to reach 3:1.
- The screening questions page and the play screen each have an `h1`.
- On the screening questions, the arrow keys now only choose an answer; Enter or Next moves on.
  Tapping an answer still moves on straight away.
- On the play screen, focus moves to the new card instead of being lost.
- Search results: only the summary line is announced, each "Call" link names the
  therapist, and the radius slider is read as "10 km".

Still to check by hand in a browser: a keyboard-only walk through each flow, and a
screen reader pass (NVDA on Windows, TalkBack on Android).

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
