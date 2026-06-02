# Running End-to-End Tests

This directory contains the automated Playwright UI tests. They execute against a specialized, ephemeral Docker Compose environment to ensure your development/production database is never touched.

## 1. Start the Ephemeral E2E Environment
From the root of the project, spin up the E2E cluster. This will build the frontend, backend, and an isolated PostgreSQL instance.
```bash
docker compose -f docker-compose.e2e.yml up --build -d
```
## Run migrations

```bash
$env:DATABASE_URL="postgresql+asyncpg://rit_test_user:rit_test_password@localhost:5433/resume_intelligence_test"; alembic upgrade head
```

## 2. Seed the Database
Our E2E environment needs predictable test data. Run the Python seeder script against the ephemeral database (which is exposed on port `5433` to not conflict with local dev).
```bash
# Ensure you are in the root directory and your Python virtual environment is active
export DATABASE_URL="postgresql+asyncpg://rit_test_user:rit_test_password@localhost:5433/resume_intelligence_test"
python -m src.db.seed
```
##OR
```bash
$env:DATABASE_URL="postgresql+asyncpg://rit_test_user:rit_test_password@localhost:5433/resume_intelligence_test"; python -m src.db.seed
```
## 3. Run the Tests
Now that the API is running (port `8080`) and the UI is served by Nginx (port `8081`), run Playwright from the `dashboard` directory: 
```bash
cd dashboard
npx playwright test
```

## 4. Teardown
Once you are done reviewing the test results (`npx playwright show-report`), destroy the ephemeral environment completely (including the temporary database volume):
```bash
cd ..
docker compose -f docker-compose.e2e.yml down -v
```
