# SPEC-001: Data Chat — Natural Language SQL Server Assistant

**Status:** Initial Draft  
**Project:** Data Chat  
**Specification Version:** 1.0

## 1. Purpose

Build a web-based chat application that allows users to ask questions in natural language about information stored in a Microsoft SQL Server database.

The application must use a Large Language Model (LLM) provided by OpenAI to interpret user questions, identify the information required, retrieve relevant data from SQL Server through controlled queries, and generate a natural-language response grounded in the retrieved data.

The system must prioritize security, accuracy, traceability, maintainability, and clear separation of responsibilities.

## 2. Technology Stack

### Development Environment

- Operating system: Windows.
- IDE: Visual Studio Code.
- Python: 3.14.7 currently installed.
- Python virtual environment: `.venv`.
- Database: Microsoft SQL Server, administered through SQL Server Management Studio (SSMS).
- LLM provider: OpenAI API.

### Proposed Technologies

- Backend: Python and FastAPI.
- Data validation: Pydantic.
- SQL Server access: SQLAlchemy and pyodbc, subject to compatibility verification.
- LLM integration: Official OpenAI Python SDK.
- Frontend: React, TypeScript, and Vite.
- Automated testing: pytest.
- Configuration: Environment variables and a local `.env` file excluded from version control.

The implementation agent must verify actual dependency compatibility before installing packages. It must not silently change the Python version or introduce additional technologies without explaining the reasons.

## 3. Functional Requirements

### 3.1. Chat Interface

Users must be able to:

- Submit questions in natural language.
- Receive answers based on SQL Server data.
- Continue a conversation using an active conversation identifier.
- Receive clear messages when a question cannot be answered by the supported query catalog.
- Receive an appropriate response when the available data is insufficient to answer a question.

### 3.2. Question Interpretation

The application must use the LLM to convert a natural-language question into a structured representation.

The structured representation may include:

- Intent identifier.
- Required parameters.
- Date ranges, when applicable.
- Supported filters.
- An indication that clarification is required.

The LLM response must be validated against explicitly defined schemas before it can influence database access.

Invalid, incomplete, or unsupported intents must not trigger database queries.

### 3.3. SQL Server Data Access

The backend must execute predefined, explicitly authorized queries.

For the initial version:

- The LLM must not execute arbitrary SQL.
- Supported intents must be registered in a query catalog.
- Each intent must define its allowed parameters and validation rules.
- SQL queries must use parameterized inputs.
- User input must never be concatenated directly into executable SQL.
- Queries must have configurable execution timeouts and result limits.
- The database account must follow the principle of least privilege and preferably have read-only access to the required data.
- Database tables, columns, relationships, and business rules must be documented only after inspecting the actual database schema.

### 3.4. Answer Generation

After retrieving the required data, the backend may call the LLM again to formulate a natural-language answer.

The answer must:

- Be grounded in the retrieved database results.
- Avoid inventing values, records, calculations, or conclusions unsupported by the available data.
- Clearly indicate when the data is insufficient to answer the question.
- Present dates, quantities, and units explicitly when relevant.
- Avoid exposing internal exceptions, credentials, connection strings, or sensitive implementation details.

When practical, important numeric answers should be calculated deterministically in Python or SQL rather than relying on the LLM to perform arithmetic.

### 3.5. Error Handling

The application must handle the following conditions gracefully:

- Invalid user input.
- Unsupported intents.
- Invalid LLM output.
- Empty query results.
- SQL Server connection failures.
- Query timeouts.
- OpenAI API errors or rate limits.
- Invalid application configuration.

Errors returned to the user must be understandable and must not expose internal technical details.

## 4. Main Request Flow

The expected request flow is:

1. The frontend sends a chat message to the backend API.
2. FastAPI validates the request.
3. The interpretation service sends the question and relevant context to OpenAI.
4. The backend validates the structured intent and its parameters.
5. The authorization and query-catalog layers determine whether the requested operation is permitted.
6. The data-access layer executes the corresponding predefined SQL query.
7. The backend validates and limits the retrieved results.
8. The response-generation service formulates an answer grounded in those results.
9. The API returns the answer to the frontend.
10. The application records useful diagnostic information without unnecessarily logging sensitive data.

If a stage fails, the application must handle the failure without executing unauthorized operations or fabricating an answer.

## 5. Proposed Architecture

The backend must separate responsibilities into clearly defined components.

### API Layer

Responsibilities:

- Define HTTP endpoints.
- Validate incoming requests.
- Return consistent responses and HTTP errors.
- Expose API documentation through OpenAPI.

### Schemas

Responsibilities:

- Define Pydantic models for requests, responses, and structured LLM intents.
- Enforce field types, required parameters, and validation constraints.

### Services

Responsibilities:

- Coordinate the chat workflow.
- Manage interpretation, query execution, and response generation.
- Keep business orchestration separate from HTTP and database implementation details.

### LLM Integration

Responsibilities:

- Communicate with the OpenAI API.
- Manage prompts and structured outputs.
- Validate LLM responses.
- Handle provider errors and timeouts.
- Avoid coupling business logic directly to provider-specific implementation details where practical.

### Data Access

Responsibilities:

- Manage SQL Server connections.
- Execute authorized queries.
- Implement repositories and the query catalog.
- Apply query limits and timeouts.

### Core

Responsibilities:

- Load and validate application configuration.
- Configure logging.
- Define common exceptions and security-related utilities.

### Tests

Responsibilities:

- Contain unit, integration, and API tests.
- Allow unit tests to run without real OpenAI credentials or an active SQL Server connection.

The frontend must remain separate from the backend.

The initial version should avoid unnecessary microservices, autonomous agents, vector databases, and orchestration frameworks. These technologies may be considered later if concrete requirements justify them.

## 6. Initial API Contract

### POST `/api/v1/chat/messages`

Accepts a user message and an optional conversation identifier.

The initial request model should contain:

- `conversation_id`: optional conversation identifier.
- `message`: user's natural-language question.

The initial response model should contain:

- `conversation_id`: conversation identifier.
- `message_id`: identifier for the response message.
- `answer`: generated answer.
- `status`: processing outcome.
- `sources`: optional descriptive references to the data or approved queries used.

The exact models and error responses must be documented using Pydantic and OpenAPI.

### GET `/api/v1/health`

Returns the basic health status of the application process.

Dependency health checks for SQL Server and OpenAI should be distinguishable from basic process health so that a dependency outage does not prevent diagnosis of the backend itself.

Conversation persistence, user authentication, and conversation ownership rules remain open design decisions until the requirements are clarified.

## 7. Security Requirements

- Never commit OpenAI API keys or database credentials to version control.
- Exclude `.env` from Git and provide a `.env.example` containing placeholders only.
- Keep all database and OpenAI access in the backend.
- Use parameterized SQL and an explicit catalog of authorized operations.
- Apply limits to message length, result size, and execution time.
- Treat LLM-generated content as untrusted input.
- Validate LLM output before using it to select a query or provide parameters.
- Never delegate authorization decisions to the LLM.
- Do not expose stack traces, secrets, connection strings, or sensitive records in API error messages.
- Use a database identity with the minimum permissions necessary.
- Configure transport encryption appropriately for the actual SQL Server environment.
- Avoid logging full prompts or query results when they may contain sensitive information.
- Document any additional authentication, authorization, or rate-limiting requirements before exposing the application beyond a trusted development environment.

## 8. Configuration

Configuration must be supplied through environment variables or a validated settings layer.

Expected settings include:

- Application environment.
- SQL Server host, port, database, driver, and authentication configuration.
- OpenAI API key.
- OpenAI model identifier.
- Maximum query result size.
- SQL query timeout.
- OpenAI request timeout.
- Logging level.

The application must validate required configuration during startup and report missing settings without exposing their values.

## 9. Testing Requirements

The project must include tests for:

- Request and response validation.
- Structured LLM output parsing.
- Unknown or unsupported intent rejection.
- Invalid parameter rejection.
- Parameterized query execution.
- Empty query results.
- SQL Server errors and timeouts.
- OpenAI errors and timeouts.
- Answer generation based on retrieved data.
- HTTP endpoint behavior.
- Configuration validation.

Unit tests must not require real OpenAI credentials or an active SQL Server connection.

Integration tests requiring external services must be explicitly identified and configured separately.

## 10. Acceptance Criteria

The initial application is acceptable when:

1. The backend starts locally using documented commands.
2. The API exposes its endpoints through OpenAPI documentation.
3. Chat requests are validated before processing.
4. The interpretation layer produces validated structured intents.
5. Only explicitly authorized queries can be executed.
6. SQL parameters are validated and safely bound.
7. Retrieved database results are used to generate the final answer.
8. Empty results and external-service failures are handled correctly.
9. Secrets are excluded from version control.
10. Automated tests pass.
11. The frontend can send questions and display backend responses once the frontend phase is implemented.
12. The README documents setup, configuration, execution, testing, and known limitations.

## 11. Implementation Constraints

- Do not implement the entire project in a single step.
- Do not invent database schema details or business rules.
- Do not add dependencies without explaining their purpose.
- Do not modify production database settings or data as part of development without explicit authorization.
- Do not allow arbitrary SQL execution generated by the LLM.
- Do not mark tasks as complete without running the relevant verification steps.
- Do not proceed to the next implementation phase until the current phase has been reviewed and approved.
- If essential information is missing, document the question and request clarification before making a consequential assumption.
- Keep the implementation simple and maintainable.
- Update documentation and tests when implementation decisions change.

## 12. Implementation Plan

### Phase 1: Requirements and Architecture

- Review this specification.
- Identify ambiguities, risks, compatibility concerns, and unresolved decisions.
- Propose the architecture and implementation plan.
- Obtain user approval before implementation.

### Phase 2: Project Foundation

- Create the Python package structure.
- Configure dependencies and development tools.
- Configure application settings and logging.
- Create a minimal FastAPI application.
- Add a health endpoint and basic automated tests.

### Phase 3: Database Discovery and Data Access

- Inspect the actual SQL Server schema.
- Identify approved tables, columns, relationships, and business rules.
- Define the initial query catalog.
- Configure a secure database connection.
- Add repository implementations and tests.

### Phase 4: OpenAI Integration

- Integrate the official OpenAI Python SDK.
- Implement question interpretation using structured outputs.
- Validate intents and parameters.
- Add error handling and mocked tests.

### Phase 5: End-to-End Chat Workflow

- Connect interpretation, query execution, and answer generation.
- Validate complete request flows.
- Add appropriate result limits, timeouts, and diagnostics.

### Phase 6: Frontend

- Create a React and TypeScript application.
- Implement the chat interface.
- Connect the frontend to the backend API.
- Handle loading states, errors, and empty responses.

### Phase 7: Integration, Security, and Documentation

- Run integration and end-to-end tests.
- Review access controls and sensitive-data handling.
- Complete developer documentation.
- Document deployment prerequisites and known limitations.

Each phase must provide a summary of changes, created or modified files, verification commands, test results, and remaining issues. The user must review and approve each phase before the next begins.

## 13. Initial Open Questions

The following items must be clarified before implementing the corresponding functionality:

- Which SQL Server database and schema will the application use?
- Which business questions should the first version support?
- Which tables and views may the application access?
- Will users need authentication?
- Should conversations persist between sessions?
- Will the application be accessible only internally or exposed to external users?
- Which deployment environment will be used?
- What data sensitivity and retention requirements apply?

These questions must not block architecture planning when reasonable provisional recommendations can be made. However, database-specific queries and production-facing security decisions must not be invented.

## 14. Definition of Done

A phase is complete only when:

- Its acceptance criteria are satisfied.
- Relevant automated tests have been executed.
- Verification results are reported accurately.
- Documentation reflects the implemented behavior.
- Known issues and limitations are documented.
- The user has reviewed and approved the phase.

**The implementation agent must begin with analysis and planning only. It must not modify files, install dependencies, or implement functionality until the user explicitly approves the next step.**