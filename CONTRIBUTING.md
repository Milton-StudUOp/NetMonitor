# Contributing

## Workflow

1. Create a branch from `premium` for premium features or from `main` for the free edition.
2. Do not include credentials, `.env`, `.active-database`, databases, logs, or real data.
3. Preserve SQLite and PostgreSQL compatibility when changing models.
4. Add Pydantic validation, controlled error handling, and audit logging for administrative operations.
5. Update all affected documentation.

## Required validation

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall app
.\venv\Scripts\python.exe -c "from sqlalchemy.orm import configure_mappers; import app.models; configure_mappers()"

cd ..\frontend
npm ci
npm run build
```

## Databases and migrations

New tables are created by `Base.metadata.create_all`. Changes to existing tables must be added to `schema_migrations.py` and tested against an existing database. Changes to the promotion process must test:

- An empty destination.
- Relationships among devices, interfaces, and links.
- Counts for each table.
- Absence of URLs or passwords in responses and logs.
- Preservation of the source database.

## Pull requests

Describe the problem, solution, risks, required migration, and commands executed. For visual changes, include screenshots without real addresses or names.

## Security

Do not discuss vulnerabilities publicly before a coordinated fix. See [SECURITY.md](SECURITY.md).
