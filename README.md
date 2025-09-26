# PendingChangesBot

PendingChangesBot is a Django-based application that monitors recent changes on Wikimedia projects. The repository contains a backend Django project and a React frontend. The instructions below help you set up a local development environment and run the available quality checks.

## Prerequisites

- Python 3.11 or newer
- [pip](https://pip.pypa.io/en/stable/installation/)
- (Optional) [virtualenv](https://virtualenv.pypa.io/en/latest/) or another tool for managing Python virtual environments

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd PendingChangesBot-temp
   ```
2. **Create and activate a virtual environment** (recommended)
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\\Scripts\\activate
   ```
3. **Install Python dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

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
