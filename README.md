# Data Chat

Data Chat is planned as a web-based assistant for questions about approved SQL
Server data. The current backend provides process health, validated settings,
OpenAI structured-intent and answer adapters, a mockable chat workflow and HTTP
contract, a SQL Server schema, and a fixed query catalog. The workflow
is assembled at app startup when valid OpenAI and SQL Server settings are
present; startup itself does not make provider or database requests. Without
those settings the chat endpoint returns a safe unavailable response. The
schema is applied to the local `WorldCup2026Dev` database; it contains no
tournament facts. The frontend is implemented but not yet served by the
backend.

## Requirements

- Windows and CPython 3.14.x (the project was dependency-resolved with Python
  3.14.7 on Windows x64).
- Node.js 22.14.0 or newer compatible with Vite 8 (the frontend packages were
  resolved with Node.js 22.14.0).
- A virtual environment at the repository root, such as `.venv`.

The SQL Server ODBC driver and a reachable SQL Server are not needed to run the
unit tests. The lazy SQLAlchemy/pyodbc adapter uses the ODBC connection string
in `SQL_SERVER_ODBC_CONNECTION_STRING`, supplied at runtime through the
settings layer. It creates an engine only when called and does not connect at
application startup. App startup may construct the lazy engine, but does not
open a SQL connection. Connections must explicitly set `Encrypt=yes` (or a
supported stricter mode). Certificate validation with
`TrustServerCertificate=no` is required by default. For local development only,
`TrustServerCertificate=yes` is accepted when `APP_ENVIRONMENT=development`;
it disables server certificate validation and must not be used outside a
trusted local development environment. Production and test environments reject
that setting. Choose a least-privilege identity for the actual environment; no
credentials are included here.

For the local Windows-authenticated SQL Server instance, after the development
database has been created, the ODBC connection string can be set in the local
`.env` file as:

```text
SQL_SERVER_ODBC_CONNECTION_STRING=Driver={ODBC Driver 17 for SQL Server};Server=DESKTOP-EN1QC5A;Database=WorldCup2026Dev;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;
```

## Setup

From the repository root, install the backend and development dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
Copy-Item .env.example .env
```

The `.env` file is local configuration and must not be committed. The example
contains defaults and placeholders only; replace `OPENAI_MODEL` with an
approved model ID and `OPENAI_API_KEY` with a local secret only when live
requests are authorized. Tests and API startup do not make OpenAI requests.

## Quick start (local demo)

Prerequisites: `.venv` and `.env` configured (see Setup) and the
`WorldCup2026Demo` database loaded (see "Synthetic demo database" below).
Use two terminals, both starting at the repository root.

Terminal 1 - backend (http://127.0.0.1:8000):

```powershell
.\.venv\Scripts\python.exe -m uvicorn data_chat.main:app --app-dir backend\src --host 127.0.0.1 --port 8000
```

Terminal 2 - frontend (http://localhost:5173):

```powershell
Push-Location frontend
npm ci   # first time only
npm run dev -- --host=localhost --port=5173
```

The `--host=` and `--port=` flags must use `=`; space-separated values fail.
Open http://localhost:5173. Every question calls OpenAI with your key and may
incur charges.

Check that both are up:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
(Invoke-WebRequest http://localhost:5173 -UseBasicParsing).StatusCode
```

Stop each server with `Ctrl+C` in its terminal. To stop background processes
from another shell, find them with `Get-NetTCPConnection -LocalPort 8000,5173 -State Listen`
and run `Stop-Process -Id <OwningProcess>`.

Run the backend tests from the `backend` directory so the right `.env` is used:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
```

## Run

Start the local API from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn data_chat.main:app --app-dir backend\src --reload
```

- Process health: `GET http://127.0.0.1:8000/api/v1/health`
- Chat contract: `POST http://127.0.0.1:8000/api/v1/chat/messages`
- OpenAPI documentation: `http://127.0.0.1:8000/docs`

The health endpoint reports process health only; it does not test SQL Server or
OpenAI availability.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -c backend\pyproject.toml backend\tests
```

The tests do not require OpenAI credentials or an active SQL Server. Both
structured OpenAI adapters and the HTTP chat workflow are tested using mocks.
The local chat endpoint can be exercised for its safe unavailable response,
but no production workflow is configured.

## Frontend

Install and run the React/Vite app from `frontend`:

```powershell
Push-Location frontend
npm ci
npm run dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:8000`. Start the
backend separately to exercise the API. If valid OpenAI and SQL Server settings
are not configured, chat requests receive the safe unavailable response.
Frontend checks:

```powershell
Push-Location frontend
npm test
npm run build
```

## Chat API contract

`POST /api/v1/chat/messages` accepts a non-empty `message` of at most 2,000
characters and an optional UUID `conversation_id`. It returns UUID conversation
and message IDs, an answer, a status (`answered`, `clarification_required`,
`unsupported`, or `insufficient_data`), and optional approved-query source
references. Request-validation errors do not echo submitted values; upstream
and data errors use a generic error envelope.

Conversation IDs key a short, in-memory history (last 6 turns, 30-minute TTL,
at most 1,000 conversations, answers truncated to 500 characters). The history
is passed to the intent step only, as untrusted context, so a follow-up such as
"DEMO-B" after "Show the group standings" can be resolved. It is never returned
to clients, is lost on restart, and has no ownership or authentication: anyone
who knows a conversation UUID can append to it. Define persistence and
authorization before public exposure.

## LangChain

The LLM calls go through `langchain-core` / `langchain-openai`
(`backend/src/data_chat/llm/langchain_adapters.py`). Only the chat model
factory is OpenAI-specific; the intent and answer adapters use
`with_structured_output`, so another provider can be supported by changing
`create_chat_model`. Query selection is unchanged: the LLM still never writes
SQL.

## World Cup 2026 data model

`backend\sql\001_world_cup_2026_schema.sql` contains the reviewed initial
SQL Server DDL for the tournament, teams/groups, venues, matches, official
standings/placements, and source references. It has been applied to the local
`WorldCup2026Dev` development database, creating the empty `wc2026` schema and
its nine tables. It is a create-once script for a new development database;
review it and verify source fields before applying it to another database.

The approved query IDs and parameter validation are in
`backend\src\data_chat\data\catalog.py`. The catalog contains only fixed
parameterized statements. Each execution requires an explicit `max_rows`
between 1 and 1,000. The catalog is called through the SQL Server repository,
which is assembled into the chat workflow when configuration is complete. The
SQLAlchemy engine has been exercised against the local ODBC
driver and SQL Server. Query-timeout configuration was active during that
request, but timeout-trigger behavior has not been tested against a live
server. All seven fixed catalog queries execute successfully against the empty
schema and return no rows.
Regulation scores mean
the score after 90 minutes; extra-time scores are cumulative after extra time;
penalty scores are shootout kicks. Tournament rows must not be seeded until
each value and its official FIFA source are verified. `TimeZoneId` values must
also be verified before importing local kickoff times.

### Synthetic demo database

For local UI and workflow testing, `backend\sql\002_world_cup_2026_demo_seed.sql`
contains fictional records only. Apply it only to a dedicated database named
`WorldCup2026Demo`, never to the real-data development database. The fixture
uses names prefixed with `Demo`/`DEMO`, and its source publisher is
`Synthetic demo data`. Chat responses for these rows are labeled as synthetic,
are prefixed with a demo-only notice, and never include an official FIFA link.
The seed is transactional and safe to re-run.

Create the separate database, apply the schema, then apply the demo seed:

```powershell
sqlcmd -S DESKTOP-EN1QC5A -E -d master -b -Q "IF DB_ID(N'WorldCup2026Demo') IS NULL CREATE DATABASE WorldCup2026Demo"
sqlcmd -S DESKTOP-EN1QC5A -E -d WorldCup2026Demo -b -i backend\sql\001_world_cup_2026_schema.sql
sqlcmd -S DESKTOP-EN1QC5A -E -d WorldCup2026Demo -b -i backend\sql\002_world_cup_2026_demo_seed.sql
```

To run the app against the fixture, change only the database name in
`SQL_SERVER_ODBC_CONNECTION_STRING` in the local `.env` to
`WorldCup2026Demo`, then restart the backend. Change it back to
`WorldCup2026Dev` when you want the separate, official-data database.

#### Large synthetic dataset

`backend\sql\003_world_cup_2026_demo_large_seed.sql` extends the fixture to a
full 48-team tournament: 12 groups (`DEMO-A`..`DEMO-L`), 16 venues, 99 matches
(group stage plus knockout rounds with extra time and penalty shootouts), and
standings and final placements for every team. It is deterministic, idempotent,
refuses to run outside `WorldCup2026Demo`, and requires 001 and 002 first.

```powershell
sqlcmd -S DESKTOP-EN1QC5A -E -d WorldCup2026Demo -b -i backend\sql\003_world_cup_2026_demo_large_seed.sql
# Remove only the 003 rows (keeps the small 002 fixture):
sqlcmd -S DESKTOP-EN1QC5A -E -d WorldCup2026Demo -b -i backend\sql\003_world_cup_2026_demo_large_seed_reset.sql
```

Useful test questions: "List all teams" (48 rows), "Show standings for
DEMO-B", "Matches for Demo Team C2", "What was Demo Team B1's final
placement?". "Show all Demo Group Stage matches" returns 67 rows, which is too
large to summarize; the app asks the user to narrow the question.

## Current limitations

- Conversation history is in memory only (see the Chat API contract).
- The local DDL has been applied, but no FIFA facts have been imported.
- The SQL Server repository and OpenAI adapters are assembled at app startup
  only when all required settings are valid.
- No verified tournament facts have been imported, so supported data questions
  cannot yet return useful results.
- User authentication and per-user authorization are not configured.
- No live OpenAI request has been made. With valid settings, user questions and
  retrieved rows will be sent to OpenAI during chat requests.
- Keep the service local until authentication, data handling, and deployment
  requirements are approved and implemented.
