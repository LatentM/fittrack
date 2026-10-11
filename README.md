# Momentum — Fitness Tracking Management System

A full-stack fitness tracker built with **Django 5.2**. Users sign up, set their body stats once, and then log workouts, meals, body measurements and daily habits. Momentum turns that into a dashboard, goal progress and period reports.

Demo login after seeding: **`demo` / `Momentum@2026`**

---

## Features

**Authentication and security**
- Sign up with name, username, email and a validated password (strength meter, common-password check)
- Sign in with **username or email**, optional "keep me signed in for 2 weeks"
- **Lockout** after 5 failed sign-in attempts (15 minutes, per username + IP)
- Password change, **password reset by email**, and account deletion confirmed with the password
- Passwords hashed with PBKDF2; CSRF protection on every form; logout is POST-only
- Every record is scoped to its owner: another user's IDs return 404, never data
- Production hardening when `DEBUG` is off (secure cookies, no-sniff, clickjacking protection)

**Fitness tracking**
- **Onboarding**: age, sex, height, weight, activity level and goal → BMR (Mifflin–St Jeor), TDEE and a daily calorie target
- **Workouts**: 9 types, duration, intensity, distance with pace, exercises with sets × reps × kg and total volume; calories auto-estimated from MET values and your latest weight; search, filters, pagination; "repeat today"
- **Nutrition**: daily food diary by meal, macro targets (protein/carbs/fat), 24 common Indian foods that fill the form in one tap, "your usual foods" one-click re-log, sanity check on macros vs calories
- **Body**: weight, body fat %, waist, resting heart rate; weight trend chart; BMI with Asian cut-offs
- **Habits**: steps, sleep and mood check-in; one-tap water logging with undo; 14-day charts against targets
- **Goals**: target weight, workout count, minutes, distance or steps, with deadlines; progress is calculated automatically, marked achieved, and flagged "behind pace" when needed
- **Dashboard**: 26-week consistency heatmap, current and best streak, today's calories/water/steps, 7-day calorie balance, weekly progress ring, macros, goals and recent workouts
- **Reports**: 7 / 30 / 90 / 365 days or a custom range, compared with the previous period; time by workout type; **CSV export** of everything (opens in Excel)
- **Admin panel** at `/admin/` for managing users and all records
- Light and dark themes, fully responsive down to phone width, keyboard accessible

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.10+, Django 5.2 (auth, ORM, forms, admin) |
| Database | SQLite by default; PostgreSQL via `DATABASE_URL` |
| Frontend | Django templates, hand-written CSS, vanilla JavaScript |
| Charts | Chart.js 4 (bundled locally in `static/vendor`) |
| Fonts | Unbounded + Manrope (bundled locally, OFL licence) |
| Static files | WhiteNoise |
| Tests | Django test runner (30 tests) |

No CDN is needed at runtime, so it also works offline in a lab.

## Project structure

```
fittrack/
├── config/            settings, root URLs, WSGI
├── accounts/          sign-up, login/lockout, onboarding, settings, Profile model (BMR/TDEE)
├── tracker/
│   ├── models.py      Workout, Exercise, Meal, BodyMeasurement, WaterLog, DailyLog, Goal
│   ├── services.py    streaks, heatmap, goal progress, reports (all the maths)
│   ├── views.py       pages, CRUD, CSV export
│   ├── forms.py       validation (no future dates, one weigh-in per day, macro checks)
│   └── management/commands/seed_demo.py
├── templates/         base layouts, accounts/, tracker/, errors/
└── static/            css/app.css, js/app.js, fonts/, vendor/chart.umd.js
```

## Run it on your laptop (Windows)

Open **Command Prompt** or **PowerShell** in the `fittrack` folder:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in as `demo` / `Momentum@2026`, or create your own account.
On macOS, Linux or WSL use `source venv/bin/activate` instead of the second line.

- `seed_demo --reset` recreates the demo account with fresh data.
- Password-reset emails print in the terminal running `runserver` (no email setup needed locally).
- Run the tests with `python manage.py test`.

## Deploy to PythonAnywhere (free)

1. Create a free account at pythonanywhere.com. Your site will be `https://<username>.pythonanywhere.com`.
2. Upload the project: **Files** tab → upload the zip, then in a **Bash console**:
   ```bash
   unzip momentum-fitness-tracker.zip -d ~ && cd ~/fittrack
   python3.12 -m venv ~/venv && source ~/venv/bin/activate
   pip install -r requirements.txt
   ```
   (Or push the folder to GitHub and `git clone` it instead of uploading.)
3. Still in the console, generate a secret key and keep it for step 5:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```
4. **Web** tab → **Add a new web app** → **Manual configuration** → the same Python version (3.12). Then set:
   - **Source code**: `/home/<username>/fittrack`
   - **Virtualenv**: `/home/<username>/venv`
   - **Static files**: URL `/static/` → directory `/home/<username>/fittrack/staticfiles`
5. Open the **WSGI configuration file** link on the Web tab, delete everything in it, and paste:
   ```python
   import os, sys
   path = "/home/<username>/fittrack"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
   os.environ["DJANGO_DEBUG"] = "False"
   os.environ["DJANGO_SECRET_KEY"] = "<the key from step 3>"
   os.environ["DJANGO_ALLOWED_HOSTS"] = "<username>.pythonanywhere.com"
   os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://<username>.pythonanywhere.com"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
6. Back in the Bash console, with the virtualenv active and the same variables set:
   ```bash
   cd ~/fittrack
   export DJANGO_DEBUG=False DJANGO_SECRET_KEY="<the key from step 3>"
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py seed_demo
   python manage.py createsuperuser
   ```
7. Turn on **Force HTTPS** on the Web tab, press **Reload**, and open your site.

Free web apps need renewing from the Web tab every month. SQLite data persists between reloads.

## Deploy to Render (optional)

Render's free web services sleep when idle and wipe local files, so use Postgres there:
- Build command: `./build.sh` · Start command: `gunicorn config.wsgi:application`
- Environment: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS=<app>.onrender.com`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://<app>.onrender.com`, and `DATABASE_URL` from a Render Postgres database.

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | `True` | Must be `False` in production |
| `DJANGO_SECRET_KEY` | dev key | Required when `DEBUG` is off (startup fails without it) |
| `DJANGO_ALLOWED_HOSTS` | localhost, `.pythonanywhere.com`, `.onrender.com` | Comma-separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | – | e.g. `https://you.pythonanywhere.com` |
| `DATABASE_URL` | SQLite file | Postgres URL to switch databases |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | console backend | Real password-reset emails |
| `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS` | 5, 900 | Brute-force protection |

## How the numbers are calculated

- **BMR** (Mifflin–St Jeor): 10 × kg + 6.25 × cm − 5 × age, then +5 (male) or −161 (female)
- **TDEE** = BMR × activity factor (1.2 to 1.9); **calorie target** = TDEE − 500 to lose, +300 to gain
- **Macro targets**: 30 % protein, 45 % carbs, 25 % fat of the calorie target
- **Workout calories** = MET × intensity factor × body weight (kg) × hours
- **BMI** categories use the Asian cut-offs (healthy 18.5–22.9) recommended for Indian adults
- **Streak**: consecutive days with at least one workout; today still counts if you trained yesterday

These are general estimates, not medical advice.
