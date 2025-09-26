# PendingChangesBot

PendingChangesBot is an application which tracks pending changes in Wikimedia Projects.

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

The Django project now serves both the API and the single-page frontend from the same codebase.

```bash
cd backend
python manage.py runserver
```

Open <http://127.0.0.1:8000/> in your browser to use the interface. The JSON API continues to be available at <http://127.0.0.1:8000/api/recent-edits/>.

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
