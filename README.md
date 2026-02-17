# Luviio Platform

Redefining Digital Physics.

## Deployment on Koyeb

This repository is optimized for deployment on [Koyeb](https://www.koyeb.com/).

### Configuration

- **Build Strategy**: Buildpack (Automatic) or Docker.
- **Run Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (handled by `Procfile`).
- **Environment Variables**:
  - `SUPABASE_URL`: Your Supabase project URL.
  - `SUPABASE_KEY`: Your Supabase API key.

### Local Development

1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`.
3. Run the app: `uvicorn app.main:app --reload`.

## Project Structure

- `app/`: Main application logic.
  - `core/`: Config and services.
  - `routers/`: API endpoints.
  - `schemas/`: Data models.
  - `static/`: CSS, JS, and images.
  - `templates/`: Jinja2 HTML templates.
- `requirements.txt`: Python dependencies.
- `Procfile`: Koyeb deployment instructions.
