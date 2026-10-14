# Data Chat information flow

This document describes how a chat message moves through the local Data Chat
application, how the database is populated for the demo, and what information
is sent to OpenAI.

The LLM calls go through LangChain (`langchain-core` and `langchain-openai`).
LangChain is only a client library: it needs no separate account or key, and
it uses the same `OPENAI_API_KEY`. It does not choose queries or write SQL; it
only provides a provider-neutral way to request schema-constrained output. The
optional LangSmith tracing service is not used and stays off unless
`LANGSMITH_*` environment variables are set.

To start the backend and frontend locally, see "Quick start (local demo)" in
the [README](../README.md#quick-start-local-demo).

## Chat request and response

```text
Browser
  │ question + optional conversation_id
  ▼
React frontend
  │ POST /api/v1/chat/messages
  ▼
FastAPI request validation
  │ validates message length (1–2,000 characters) and request shape
  ▼
ChatWorkflow
  │ loads recent turns for the conversation_id (in-memory ConversationStore)
  │ sends the question + that history to the LLM for intent classification
  ▼
LangChainIntentInterpreter (langchain-openai ChatOpenAI, structured output)
  │ returns a structured decision, validated as IntentDecision
  ├── clarification_required ──► response asks the user for a missing detail
  ├── unsupported ─────────────► response says the topic is not supported
  └── query + validated parameters
         ▼
     Authorized query catalog
         │ selects one fixed, parameterized SQL statement
         │ validates parameters and limits results to at most 1,000 rows
         ▼
     CatalogRepository ─────────► SQL Server (wc2026 schema)
         │ returns matching rows and their source publisher/URL
         ▼
     ChatWorkflow
         ├── no rows ────────────► insufficient_data response
         └── rows found
                │ question + query ID + result rows sent to OpenAI
                ▼
            LangChainAnswerGenerator (structured output)
                │ returns a structured answer
                ▼
            ChatWorkflow
                │ validates answer, attaches approved source references,
                │ prefixes a demo-only warning for synthetic records,
                │ and stores the question/answer turn in the ConversationStore
                ▼
            FastAPI JSON response ──► React renders answer, status, sources
```

### 1. Browser to API

The frontend sends a JSON body to `POST /api/v1/chat/messages` containing the
question and an optional conversation ID. The frontend validates the response
shape and only keeps HTTPS links on the approved FIFA source domains.

The backend rejects malformed requests before processing them. Questions must
contain 1–2,000 characters; extra request fields are rejected. The conversation
ID keys a short in-memory history (see "Conversation memory" below); nothing
is persisted, and the history is never returned to the browser.

### 2. Intent classification

The backend sends the user's question, plus any recent turns of the same
conversation, to the LLM using the configured model.
OpenAI must return a structured intent: one of the supported query IDs and its
parameters, a clarification request, or an unsupported-topic result.

Pydantic validates the response against the closed `IntentDecision` schema.
Query parameters are then validated against that query's own parameter model.
If required information is missing or ambiguous, the workflow returns a
clarification and does not query SQL Server. The model is not given SQL
execution capability.

### 3. Approved SQL lookup

For a valid query intent, the backend selects a fixed statement from the
authorized catalog. It binds validated parameters rather than constructing SQL
from model output, and applies a maximum result limit of 1,000 rows. The
repository uses SQLAlchemy and ODBC to query the configured SQL Server
database. Unsupported query IDs, invalid parameters, and database failures do
not become successful answers.

### 4. Answer generation and sources

If rows are returned, the backend sends the question, approved query ID, and
those database rows to OpenAI. The answer prompt instructs the model to use
only those rows. The response must validate against the structured answer
schema; otherwise the API returns a safe error instead of an answer.

The application attaches source references from database rows, rather than
letting the model supply URLs. It accepts links only from HTTPS FIFA domains.
For synthetic demo rows, it labels the source as demo data, omits official
links, and adds a prominent warning to the answer.

If there are no matching rows, the workflow responds that no records were
found; it does not ask OpenAI to invent an answer.

## Demo-data loading flow

The synthetic fixture is kept in the separate SQL Server database
`WorldCup2026Demo`; `WorldCup2026Dev` remains separate. The fixture is
fictional and must not be presented as official FIFA information.

```text
001_world_cup_2026_schema.sql ──► creates wc2026 tables in WorldCup2026Demo
002_world_cup_2026_demo_seed.sql ─► inserts synthetic source, teams, group,
                                    venue, match, standings, and placements
                                   │
                                   ▼
                             approved SQL catalog
                                   │ demo query rows carry
                                   │ Publisher = "Synthetic demo data"
                                   ▼
                             chat labels answer and source as synthetic
```

The demo seed is transactional and safe to re-run. For local app testing, the
database name in `SQL_SERVER_ODBC_CONNECTION_STRING` in `.env` is set to
`WorldCup2026Demo`. Change it to `WorldCup2026Dev` only when intentionally
using that separate database. Do not commit `.env` or share its credentials.

## Example: ask for demo group standings

This example uses synthetic records from `WorldCup2026Demo`. The model's exact
wording and generated IDs can vary, but the backend validation and query choice
follow the rules below.

### Request 1: group is not specified

The browser sends this JSON. The conversation ID is omitted on the first turn:

```http
POST /api/v1/chat/messages
Content-Type: application/json

{
  "message": "Show the group standings"
}
```

**Code links:** [React submit handler](../frontend/src/App.tsx#L48) →
[API client POST request](../frontend/src/api/chat.ts#L109) →
[request schema and size limit](../backend/src/data_chat/schemas/chat.py#L14) →
[FastAPI chat route](../backend/src/data_chat/api/chat.py#L33).

**Backend processing before OpenAI:** FastAPI checks that `message` is a
non-empty string of no more than 2,000 characters and rejects extra fields.
The backend then sends the question to the intent adapter. At this point it
does not query SQL Server and does not send database rows to OpenAI.

**Code links:** [workflow entry point](../backend/src/data_chat/services/chat.py#L96) →
[intent adapter call](../backend/src/data_chat/services/chat.py#L120) →
[LangChain intent adapter](../backend/src/data_chat/llm/langchain_adapters.py#L63).

**What OpenAI receives for intent classification:**

- The configured model ID.
- The backend's fixed `INTENT_INSTRUCTIONS`, which lists the supported query
  IDs, their required parameters, and says to ask for clarification rather
  than guess missing values.
- The user text: `Show the group standings`.
- The `IntentDecision` JSON schema used for structured output. Its allowed
  outcomes are `query`, `clarification_required`, and `unsupported`.

OpenAI proposes a structured decision. In this case, it should ask for the
missing group code:

```json
{
  "outcome": "clarification_required",
  "query_id": null,
  "team_name": null,
  "venue_name": null,
  "group_code": null,
  "stage_name": null,
  "clarification_question": "Which group do you want the standings for?"
}
```

**Code links:** [supported intents and missing-parameter instructions](../backend/src/data_chat/llm/openai_intent.py#L2) →
[structured-output model](../backend/src/data_chat/llm/langchain_adapters.py#L58) →
[model call and error mapping](../backend/src/data_chat/llm/langchain_adapters.py#L142) →
[intent response model](../backend/src/data_chat/schemas/intent.py#L18).

**How the backend decides whether to act on it:** OpenAI does not select or
execute SQL. Pydantic first checks the response against the closed schema:
the outcome must be one of the allowed values, fields must have the correct
types, and extra fields are forbidden. The model validator then requires a
clarification question for this outcome and forbids query IDs and query
parameters on a clarification. Because the validated outcome is
`clarification_required`, `ChatWorkflow` returns the question immediately;
the repository is not called. If the model instead proposed a query without
the required `group_code`, validation would reject it and the request would
fail safely before SQL access.

**Code links:** [cross-field validation](../backend/src/data_chat/schemas/intent.py#L38) →
[clarification branch, which returns before SQL](../backend/src/data_chat/services/chat.py#L121).

The backend returns a response like this (IDs and wording are illustrative):

```json
{
  "conversation_id": "b1d4876a-915b-432f-9c99-24f3a2a6fc4e",
  "message_id": "53eeb8f9-cf3d-4d4c-af85-c55069a8f122",
  "answer": "Which group do you want the standings for?",
  "status": "clarification_required",
  "sources": []
}
```

The response shape is defined by
[ChatMessageResponse](../backend/src/data_chat/schemas/chat.py#L32).

### Request 2: user supplies the group code

The user can reply with just the group code. The browser reuses the
conversation ID from the first response, and the backend loads the earlier turn
from its in-memory store:

```http
POST /api/v1/chat/messages
Content-Type: application/json

{
  "conversation_id": "b1d4876a-915b-432f-9c99-24f3a2a6fc4e",
  "message": "DEMO-A"
}
```

**Code links:** [frontend sends message and conversation ID](../frontend/src/App.tsx#L48) →
[API request JSON](../frontend/src/api/chat.ts#L109) →
[history is loaded for this ID](../backend/src/data_chat/services/chat.py#L98).

**Intent-classification input:** The backend sends the fixed intent
instructions plus `HISTORY_INSTRUCTIONS`, the schema, and the messages
`Show the group standings` (user), `Which group do you want the standings
for?` (assistant) and `DEMO-A` (user). The history is untrusted context used
only to combine a short reply with the earlier request. Every query parameter
must still be stated by the user in a user turn, never taken from assistant
text alone. No database content is sent for this step.

**Code links:** [history instructions](../backend/src/data_chat/llm/langchain_adapters.py#L25) →
[history becomes alternating human/AI messages](../backend/src/data_chat/llm/langchain_adapters.py#L63).

**Intent decision:** OpenAI returns a structured proposal such as:

```json
{
  "outcome": "query",
  "query_id": "group_standings",
  "team_name": null,
  "venue_name": null,
  "group_code": "DEMO-A",
  "stage_name": null,
  "clarification_question": null
}
```

**Code links:** [allowlisted query IDs](../backend/src/data_chat/schemas/intent.py#L6) →
[decision/parameter validation](../backend/src/data_chat/schemas/intent.py#L38) →
[query parameter extraction](../backend/src/data_chat/schemas/intent.py#L64).

The backend accepts this proposal only after checking all of the following:

1. `query_id` is one of the literal allowlisted query IDs, not arbitrary SQL.
2. `group_standings` is present in `AUTHORIZED_QUERIES`.
3. The catalog's `GroupCodeParameters` accepts exactly a non-empty `group_code`
   of at most eight characters; unrelated parameters are forbidden.
4. The outcome/query fields are consistent under the `IntentDecision`
   cross-field validator.

These checks are what authorize the next step—not the model's confidence or
the wording of its answer. The backend chooses the already-written standings
statement from `catalog.py`, binds `DEMO-A` as a parameter, and applies the
1,000-row maximum. Conceptually, it is a lookup shaped like:

```sql
SELECT TOP (:result_limit) ...
FROM wc2026.OfficialGroupStanding AS standings
JOIN wc2026.Tournament AS tournament
  ON tournament.TournamentId = standings.TournamentId
JOIN wc2026.Team AS team
  ON team.TeamId = standings.TeamId
JOIN wc2026.SourceReference AS source
  ON source.SourceReferenceId = standings.SourceReferenceId
WHERE tournament.EditionYear = 2026
  AND standings.GroupCode = :group_code
ORDER BY standings.OfficialPosition
```

**Code links:** [fixed group-standings query and parameter model](../backend/src/data_chat/data/catalog.py#L211) →
[catalog validates and executes the selected statement](../backend/src/data_chat/data/catalog.py#L269) →
[repository obtains a SQL Server connection](../backend/src/data_chat/data/repository.py#L24).

SQL Server receives `group_code="DEMO-A"` as a bound value; the model cannot
change the SQL text. The fixed query joins standings to the tournament, team,
and source-reference tables, filters to edition year 2026 and group `DEMO-A`,
and sorts by official position. It returns four rows. These are the result
fields the backend processes and passes onward:

```json
[
  {
    "group_code": "DEMO-A",
    "official_position": 1,
    "team_name": "Demo Aurora FC",
    "played": 1,
    "wins": 1,
    "draws": 0,
    "losses": 0,
    "goals_for": 2,
    "goals_against": 1,
    "goal_difference": 1,
    "points": 3,
    "qualification_status": "Demo qualifier",
    "source_url": "https://example.invalid/world-cup-2026-demo",
    "source_publisher": "Synthetic demo data"
  },
  {
    "group_code": "DEMO-A",
    "official_position": 2,
    "team_name": "Demo Borealis FC",
    "played": 1,
    "wins": 0,
    "draws": 0,
    "losses": 1,
    "goals_for": 1,
    "goals_against": 2,
    "goal_difference": -1,
    "points": 0,
    "qualification_status": "Demo participant",
    "source_url": "https://example.invalid/world-cup-2026-demo",
    "source_publisher": "Synthetic demo data"
  },
  {
    "group_code": "DEMO-A",
    "official_position": 3,
    "team_name": "Demo Cinder FC",
    "played": 0,
    "wins": 0,
    "draws": 0,
    "losses": 0,
    "goals_for": 0,
    "goals_against": 0,
    "goal_difference": 0,
    "points": 0,
    "qualification_status": "Demo participant",
    "source_url": "https://example.invalid/world-cup-2026-demo",
    "source_publisher": "Synthetic demo data"
  },
  {
    "group_code": "DEMO-A",
    "official_position": 4,
    "team_name": "Demo Drift FC",
    "played": 0,
    "wins": 0,
    "draws": 0,
    "losses": 0,
    "goals_for": 0,
    "goals_against": 0,
    "goal_difference": 0,
    "points": 0,
    "qualification_status": "Demo participant",
    "source_url": "https://example.invalid/world-cup-2026-demo",
    "source_publisher": "Synthetic demo data"
  }
]
```

**Code links:** [catalog selects the source publisher](../backend/src/data_chat/data/catalog.py#L211) →
[demo publisher is inserted by the fixture](../backend/sql/002_world_cup_2026_demo_seed.sql#L30) →
[synthetic standings rows are seeded](../backend/sql/002_world_cup_2026_demo_seed.sql#L177).

**What OpenAI receives for answer generation:** The backend makes a second
OpenAI request (no conversation history is included) containing the fixed
answer instructions, the question text of this turn, the approved query ID, and the SQL result rows serialized as JSON.
The serialized rows include the returned source URL and publisher, too. For
this example, the effective input has this shape:

```text
Approved query ID: group_standings
User question: DEMO-A
Database result rows (JSON): [{"group_code":"DEMO-A", ...,
  "source_publisher":"Synthetic demo data"}]
```

**Code links:** [answer-generation instructions](../backend/src/data_chat/llm/openai_answer.py#L1) →
[structured answer request and serialized inputs](../backend/src/data_chat/llm/langchain_adapters.py#L105).

If the serialized rows exceed 30,000 characters, or the final answer would
exceed 2,000 characters, the backend skips or discards the answer and returns a
"narrow your question" clarification instead.

The answer instructions tell OpenAI to use only these rows, treat the question
and row values as untrusted data, and return the structured
`GeneratedAnswer(status, answer)` schema. The model is not asked to choose a
query again and is instructed not to supply source links. The backend checks
the answer schema and length, then independently checks the `source_publisher`
value in the rows. Since all returned rows are marked `Synthetic demo data`,
the backend prepends its own warning and attaches a synthetic-data source
label with no URLs. If there were no rows, it would return
`insufficient_data` without making this second OpenAI request.

**Code links:** [workflow checks rows and validates the answer](../backend/src/data_chat/services/chat.py#L177) →
[demo notice is added by the backend](../backend/src/data_chat/services/chat.py#L190) →
[narrow-your-question response](../backend/src/data_chat/services/chat.py#L203) →
[frontend renders answer and sources](../frontend/src/App.tsx#L131).

```json
{
  "conversation_id": "b1d4876a-915b-432f-9c99-24f3a2a6fc4e",
  "message_id": "77347191-7c82-46bb-b0e8-efedc17305fd",
  "answer": "DEMO DATA ONLY - synthetic examples; not official FIFA facts. 1. Demo Aurora FC — 3 points; 2. Demo Borealis FC — 0 points; 3. Demo Cinder FC — 0 points; 4. Demo Drift FC — 0 points.",
  "status": "answered",
  "sources": [
    {
      "query_id": "group_standings",
      "label": "Synthetic demo data - not official FIFA information",
      "urls": []
    }
  ]
}
```

## Conversation memory

`ConversationStore` ([source](../backend/src/data_chat/services/conversations.py))
keeps, per conversation ID, the last 6 question/answer turns (answers truncated
to 500 characters), for at most 30 minutes and 1,000 conversations. It lives in
the backend process memory only: it is lost on restart, is never returned to
the client, and has no ownership or authentication, so anyone who knows a
conversation UUID could add to it. History is used for intent classification
only, as untrusted context. The backend never writes questions or answers to
its logs.

## External data and privacy

With a configured chat workflow, the user question (and up to 6 recent turns of
the same conversation) is sent to OpenAI for intent
classification. If the approved SQL query returns rows, the question and those
rows are sent to OpenAI again for answer generation. Do not include private or
sensitive information in questions. The OpenAI API key stays in the local
backend configuration and is not sent to the browser.

At application startup, settings are read and the chat model, SQL engine,
repository, conversation store, and workflow are assembled only when required settings are
configured. Startup itself does not send a question to OpenAI. Database
connections are made when a query is executed. Resources are closed when the
backend shuts down.

## Failure behavior

The API validates requests before using providers. Provider unavailability
returns a safe service error; malformed provider output and database errors
return safe error responses; a SQL query timeout has its own timeout response.
Detailed secrets, raw provider output, and database exception details are not
included in the response to the browser.

## Code locations

- Frontend request and response handling: `frontend/src/api/chat.ts`
- HTTP route and contract: `backend/src/data_chat/api/chat.py` and
  `backend/src/data_chat/schemas/chat.py`
- Intent contract and validation: `backend/src/data_chat/schemas/intent.py`
- Workflow and source/demo labeling: `backend/src/data_chat/services/chat.py`
- LangChain intent and answer adapters and chat-model factory:
  `backend/src/data_chat/llm/langchain_adapters.py`
- Intent/answer instructions and shared LLM error types:
  `backend/src/data_chat/llm/openai_intent.py` and
  `backend/src/data_chat/llm/openai_answer.py`
- In-memory conversation history: `backend/src/data_chat/services/conversations.py`
- Fixed SQL query catalog: `backend/src/data_chat/data/catalog.py`
- SQL Server repository and connection: `backend/src/data_chat/data/repository.py`
  and `backend/src/data_chat/data/connection.py`
- Schema and synthetic fixture: `backend/sql/001_world_cup_2026_schema.sql` and
  `backend/sql/002_world_cup_2026_demo_seed.sql`
