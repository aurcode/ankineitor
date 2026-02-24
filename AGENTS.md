# Repository Guidelines

## Project Structure & Module Organization
- `src/ankineitor/`: core pipeline, application services, config, and security modules.
- `app/`: legacy Streamlit UI (`app/app.py`) and tab logic in `app/tabs/`.
- `web/backend/`: Django + DRF + Channels + Celery backend (`ankineitor_web/`, `pipeline_api/`).
- `web/frontend/`: React + TypeScript (Vite) UI (`src/pages/`, `src/components/`, `src/__tests__/`).
- `tests/`: primary pytest suite for pipeline, service, security, and web integration coverage.
- Runtime artifacts are mounted/written in `data/`, `media/`, `output/`, `logs/`, `my_audio_files/`, and `my_image_files/`.

## Build, Test, and Development Commands
- `docker-compose up --build app backend worker redis frontend`: run Streamlit, Django API, Celery worker, Redis, and React UI together.
- `docker-compose up --build`: full default stack (includes Caddy in this repo).
- `pip install -r requirements.txt -r test_requirements.txt`: install Python app + test tooling.
- `python web/backend/manage.py migrate`: apply Django migrations locally.
- `pytest`: run Python test suite.
- `pytest tests/test_web_pipeline_api.py tests/test_web_pipeline_ws.py tests/test_web_tabs_api.py`: run targeted migration/API tests.
- `cd web/frontend && npm install && npm run dev`: run frontend dev server.
- `cd web/frontend && npm run build` / `npm test`: production build and Vitest suite.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` for modules/functions, `PascalCase` for classes, and type hints for service/pipeline boundaries.
- React/TypeScript: `PascalCase` component files (for example `PipelinePage.tsx`), `camelCase` for helpers/state functions.
- Keep orchestration logic in `src/ankineitor/application/`; keep transform implementations in `src/ankineitor/pipeline/`.
- `black`, `flake8`, `isort`, and `mypy` are available in `test_requirements.txt`; run them before large refactors.

## Testing Guidelines
- Pytest is configured in `pytest.ini`: files `test_*.py`, functions `test_*`, tests under `tests/`.
- Use markers (`unit`, `integration`, `security`, `llm`, `benchmark`, etc.) for scope clarity.
- Django endpoint tests should include auth and owner-scoping checks (`@pytest.mark.django_db`).
- Frontend tests belong in `web/frontend/src/__tests__/` and run via `vitest` (`npm test`).

## Commit & Pull Request Guidelines
- Follow observed Conventional Commit style: `feat(scope): ...`, `test(scope): ...`, `chore(scope): ...`.
- Use imperative, specific summaries (example: `feat(web): add retry endpoint for failed jobs`).
- PRs should include: purpose, touched areas, env/migration notes, and exact test commands run.
- Add screenshots or short recordings for UI changes, especially tab flow/progress updates.

## Security & Configuration Tips
- Start from `.env.example` and keep secrets out of version control.
- API calls require `Authorization: Token <token>`; websocket auth uses `?token=<token>`.
- Do not commit generated runtime outputs unless they are intentional fixtures.
