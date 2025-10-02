# PendingChangesBot

PendingChangesBot is a Django application that inspects pending changes on Wikimedia
projects using the Flagged Revisions API. It fetches the 50 oldest pending pages for a
selected wiki, caches their pending revisions together with editor metadata, and exposes a
Vue.js interface for reviewing the results.

## Installation

1. **Clone the repository**
   ```bash
   git clone git@github.com:Wikimedia-Suomi/PendingChangesBot-temp.git
   cd PendingChangesBot-temp
   ```
2. **Create and activate a virtual environment** (recommended)
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: .venv\\Scripts\\activate
   ```
3. **Install Python dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Running the application

The Django project serves both the API and the Vue.js frontend from the same codebase.

```bash
cd backend
python manage.py runserver
```

Open <http://127.0.0.1:8000/> in your browser to use the interface. JSON endpoints are
available under `/api/wikis/<wiki_id>/…`, for example `/api/wikis/1/pending/`.

## Running unit tests

Unit tests live in the Django backend project. Run them from the `backend/` directory so Django can locate the correct settings module.

```bash
cd backend
python manage.py test
```

## Running Flake8

Run Flake8 from the repository root to lint the code according to the configuration provided in `.flake8`.

```bash
flake8
```

If you are working inside a virtual environment, ensure it is activated before executing the command.
