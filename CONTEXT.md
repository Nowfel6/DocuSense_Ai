# DocuSense AI — Final Project Workspace Contract

<!--
TEACHING NOTE:

This file is the CONTEXT.md for `final_project/`.

`final_project/` is the actual DocuSense AI production codebase.

The Planning Room is responsible for architecture, requirements, domain modeling,
implementation planning, API contracts, database specifications, and handoff.

This folder is responsible for implementing and integrating those approved plans.

Do not treat `planning_room/` as the production application.
Do not place experimental planning documents inside `final_project/` unless
explicitly required.

The final_project folder must remain runnable as an independent application.
-->

## 1. Purpose of This Folder

`final_project/` is the **main DocuSense AI application repository**.

All final implementation code, configuration, tests, infrastructure definitions,
and application-specific resources belong here.

The production workflow is:

```text
planning_room/
      │
      │ approved plans / contracts
      ↓
database_production/
backend_production/
frontend_production/
      │
      │ implementation and integration
      ↓
final_project/
      │
      ↓
Runnable DocuSense AI application
```

The Planning Room is the architectural source of truth.

`final_project/` is the implementation source of truth.

Do not copy planning-room files blindly into the production project.
Implement the approved design in the appropriate production module.

---

# 2. Separation of Responsibilities

The repository/workspace follows this separation:

```text
PLANNING
planning_room/
    ↓
Architecture
Business rules
Domain model
API contracts
Database design
RAG design
Implementation order
Testing strategy
    ↓
HANDOFF
    ↓
PRODUCTION
final_project/
    ↓
Actual source code
Configuration
Database implementation
Backend
Frontend
Workers
AI/RAG
Tests
Infrastructure
```

### Planning Room

Responsible for answering:

> What should be built?

### Production Project

Responsible for answering:

> How is the approved design actually implemented?

Do not move unfinished brainstorming directly into production code.

---

# 3. Final Project Technology Stack

The current DocuSense architecture is:

```text
Frontend
    Next.js
    Tailwind CSS

Backend
    FastAPI
    Python
    Pydantic
    SQLAlchemy

Database
    PostgreSQL
    pgvector
    Alembic

Background Processing
    Celery
    Redis

Document Storage
    MinIO for local development
    S3-compatible object storage for production

Document Parsing
    Docling / Unstructured

Embeddings
    Local embedding model initially
    Provider abstraction for future hosted models

LLM
    Configurable provider
    Gemini / Groq / OpenAI / Local model may be used

RAG
    Structure-aware / hierarchical chunking
    Vector retrieval
    Evidence-based extraction
    Deterministic validation
    Human-in-the-loop review
```

Do not introduce another framework or database without checking the existing
architecture and updating the relevant planning documents.

---

# 4. Required Final Project Structure

Use a shallow, feature-first structure. Create a folder only when it contains a
real source, configuration, test, migration, seed, or documentation file. Do not
pre-create empty architecture trees or keep empty folders with `.gitkeep`.

```text
final_project/
├── CONTEXT.md
├── registry.md
├── README.md
├── .gitignore
├── .env.example
│
├── backend/
│   ├── pyproject.toml
│   ├── .venv/                         # generated locally, never registered
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # create when application wiring exists
│   │   └── [feature]/
│   │       ├── routes.py
│   │       ├── service.py
│   │       ├── models.py              # only when finalized
│   │       └── ...                    # other feature-owned code only
│   └── tests/
│       └── [feature]/
│           └── test_[feature].py
│
├── database/
│   └── [feature]/
│       ├── migrations/
│       └── seeds/
│
├── frontend/
│   ├── package.json
│   └── [feature source folders]       # create only with implemented UI code
│
├── docs/
│   ├── architecture/
│   ├── api/
│   └── development/
│
└── infrastructure/
    └── docker-compose.yml
```

Every code artifact has exactly one canonical destination inside
`final_project/`. A folder may contain multiple closely related files for one
feature, but the same implementation must not be copied into multiple folders.
Cross-feature shared folders may be introduced only after shared code actually
exists.

---

# 5. Backend Virtual Environment Rule

The FastAPI backend **must run inside a Python virtual environment**.

The project must not depend on globally installed Python packages.

The expected backend environment is:

```text
final_project/
└── backend/
    └── .venv/
```

Create the environment from the `backend/` directory:

```text
python -m venv .venv
```

Activate it before installing or running backend dependencies.

### Windows

```text
.venv\Scripts\activate
```

### Linux / macOS

```text
source .venv/bin/activate
```

After activation:

```text
python --version
pip --version
```

must refer to the virtual environment.

Install dependencies only through the project's declared dependency files.

Do not instruct developers or agents to install project dependencies globally.

The `.venv/` directory must normally be excluded from Git.

---

# 6. Backend Dependency Management

The backend must have a reproducible dependency definition.

Prefer:

```text
backend/pyproject.toml
```

as the primary dependency configuration.

A `requirements.txt` file may also be maintained when useful for deployment or
environment reproducibility.

The agent must not manually install random packages without recording them in
the project's dependency configuration.

After adding a dependency:

```text
dependency change
    ↓
update dependency definition
    ↓
test installation
    ↓
commit dependency configuration
```

---

# 7. Backend Run Rule

FastAPI must be started from the backend environment.

Conceptually:

```text
final_project/backend
        ↓
activate .venv
        ↓
run FastAPI application
```

Example development command:

```text
uvicorn app.main:app --reload
```

The exact command may change according to the final application configuration,
but the backend must always execute using the project's virtual environment.

Celery workers must use the **same backend virtual environment**, because they
execute the same Python application dependencies.

Example conceptual setup:

```text
Terminal 1
    → FastAPI

Terminal 2
    → Celery worker

Terminal 3
    → Celery worker (optional)

Terminal 4
    → supporting services / local infrastructure
```

---

# 8. Frontend Environment Rule

The frontend uses the Node.js ecosystem independently from the Python backend.

```text
final_project/frontend/
```

must contain its own frontend dependency configuration.

The frontend must not depend on Python packages.

The frontend stack is:

```text
Next.js
React
TypeScript
Tailwind CSS
```

Use the project's declared package manager and lockfile consistently.

Do not mix package managers unnecessarily.

---

# 9. Database Responsibility

The database implementation belongs to:

```text
final_project/database/
```

The target database is:

```text
PostgreSQL
+
pgvector
```

The project must keep:

```text
database schema
migrations
indexes
constraints
vector configuration
```

under controlled versioning.

Application-level database access is implemented in the backend through the
approved Python database architecture.

Do not use Prisma unless the architecture is explicitly changed to support it.

The database is the persistent source of truth for:

```text
Users
Organizations
Documents
Document metadata
Processing jobs
Chunks
Extraction results
Validation results
Review records
Audit logs
API keys
Webhooks
Export records
```

---

# 10. Object Storage Responsibility

Actual PDF files and other large binary artifacts must not normally be stored
directly in PostgreSQL.

Use:

```text
Local development
    → MinIO

Production
    → AWS S3 or another S3-compatible object store
```

The backend should access storage through a storage abstraction where practical.

Conceptually:

```text
StorageProvider
    ├── MinIOStorage
    └── S3Storage
```

The application should store references such as:

```text
document_id
storage_key
filename
content_type
size
```

in PostgreSQL.

---

# 11. Redis and Celery Responsibility

Redis is infrastructure for asynchronous job processing.

Celery is responsible for executing background jobs.

The architecture is:

```text
Next.js
   ↓
FastAPI
   ↓
Create persistent ProcessingJob
   ↓
Celery task
   ↓
Redis broker
   ↓
Celery worker
```

Use background workers for long-running operations such as:

```text
PDF parsing
OCR
partitioning
chunking
embedding generation
vector indexing
RAG retrieval
LLM extraction
validation
large exports
webhook delivery
```

Do not perform long-running document-processing operations directly inside
normal HTTP request handlers.

---

# 12. AI / RAG Module Boundaries

The RAG implementation must remain modular.

Recommended conceptual interfaces:

```text
DocumentParser
        ↓
ChunkingService
        ↓
EmbeddingProvider
        ↓
VectorStore
        ↓
Retriever
        ↓
LLMProvider
        ↓
ExtractionService
        ↓
ValidationService
        ↓
Review / Persistence
```

Possible implementations:

```text
DocumentParser
    → Docling
    → Unstructured

EmbeddingProvider
    → Local Hugging Face model
    → Future hosted provider

VectorStore
    → PostgreSQL + pgvector

LLMProvider
    → Gemini
    → Groq
    → OpenAI
    → Local model
```

Do not tightly couple business logic to one vendor.

---

# 13. Production Module Dependency Rules

The project follows this dependency direction:

```text
Frontend
    ↓
FastAPI API
    ↓
Backend Services
    ↓
Repositories / Infrastructure
    ↓
Database / Storage
```

And for processing:

```text
FastAPI
    ↓
Celery
    ↓
RAG / Document Processing Services
    ↓
Storage / Vector DB / LLM
```

The frontend must not directly connect to PostgreSQL.

The frontend must not contain database credentials.

The frontend must not bypass FastAPI for business-critical operations.

The backend must not contain UI-specific logic.

---

# 14. Configuration and Secrets

All environment-specific values must be configurable through environment
variables or an equivalent configuration mechanism.

Example:

```text
DATABASE_URL
REDIS_URL

S3_ENDPOINT
S3_BUCKET
S3_ACCESS_KEY
S3_SECRET_KEY

LLM_PROVIDER
LLM_API_KEY

EMBEDDING_PROVIDER

JWT / AUTH configuration
```

Never hard-code credentials into source files.

Maintain:

```text
.env.example
```

with placeholder values only.

Actual `.env` files containing secrets must not be committed to Git.

---

# 15. Development Order

When implementing a new approved feature, follow the dependency order from
the Planning Room.

Default order:

```text
1. Verify approved planning artifact
        ↓
2. Verify / update domain model
        ↓
3. Implement database changes
        ↓
4. Implement backend models/schemas/services
        ↓
5. Implement background jobs if required
        ↓
6. Implement AI/RAG module if required
        ↓
7. Implement API endpoints
        ↓
8. Implement frontend API integration
        ↓
9. Implement frontend UI
        ↓
10. Integration testing
        ↓
11. End-to-end validation
        ↓
12. Production hardening
```

The agent must not skip directly to frontend implementation when required
backend/data contracts do not yet exist.

---

# 16. Modular Development Rule

Organize code by feature first, then by responsibility inside that feature.

```text
backend/app/auth/
├── routes.py
├── service.py
└── models.py

backend/tests/auth/
└── test_auth.py

database/auth/
├── migrations/
└── seeds/
```

Use the same pattern for `documents`, `extraction`, `review`, and later features.
Keep a file small and focused, but do not create a new folder for a single helper
or an architecture layer that has no implementation yet. Shared infrastructure
belongs in a shared folder only when two or more feature modules use it.

---

# 17. Changeability Rule

The architecture must allow individual technologies to be replaced with
minimal impact.

Examples:

```text
MinIO
   ↕
S3

Gemini
   ↕
Groq
   ↕
OpenAI
   ↕
Local Qwen

Docling
   ↕
Unstructured

Local embedding model
   ↕
Hosted embedding provider
```

Business logic should depend on the abstraction/interface rather than directly
embedding vendor-specific logic everywhere.

The agent should introduce an abstraction when a component is genuinely likely
to be replaced or when the abstraction provides a clear architectural boundary.

Do not over-engineer simple components.

---

# 18. Planning Room Handoff Rule

Production implementation must originate from an approved Planning Room plan.

Before implementing a feature, inspect the relevant planning artifacts:

```text
planning_room/final/
```

Relevant documents may include:

```text
[feature]-plan.md
[feature]-data-model.md
[feature]-api-contract.md
[feature]-job-workflow.md
[feature]-rag-architecture.md
[feature]-frontend-plan.md
[feature]-test-plan.md
```

The implementation agent must identify which documents apply before writing code.

If the plan is incomplete or contradictory, stop implementation of the affected
part and report the planning dependency rather than inventing a conflicting
architecture.

---

# 19. Where Production Code Goes

All completed implementation belongs inside:

```text
final_project/
```

Examples:

```text
FastAPI code
    → final_project/backend/

Next.js code
    → final_project/frontend/

Database implementation
    → final_project/database/[feature]/

Backend feature code
    → final_project/backend/app/[feature]/

Backend feature tests
    → final_project/backend/tests/[feature]/

Docker/infrastructure
    → final_project/infrastructure/

Project documentation
    → final_project/docs/
```

Do not create production implementation files inside:

```text
planning_room/
```

The Planning Room may describe implementation, but the actual code belongs here.

---

# 20. Completion and Handoff Tracking

The Planning Room maintains the planning-level completion record.

The `final_project/` workspace maintains implementation-level status through
normal project documentation, commits, tests, and release information.

When a production agent completes a feature, it should be possible to identify:

```text
Which planning contract was implemented?
Which database changes were made?
Which backend modules were added?
Which frontend modules were added?
Which tests were added?
Which environment/configuration changes were required?
```

Do not mark a feature complete merely because files were created.

A feature is complete only when the relevant implementation and validation are
finished.

### Final Project Code Registry

Maintain:

```text
final_project/registry.md
```

The registry is the implementation inventory for code integrated into the final
application. Update it whenever a code file is added, moved, replaced, or
removed. Each production-room handoff entry must identify:

```text
Verified 04-output source path
Final project destination path
Relevant integration or adaptation note
```

Do not register planning documents, completion manifests, caches, virtual
environments, dependency-installation output, or generated build artifacts as
application code.

The registry must point to one canonical destination for each code artifact.
Do not create a second copy to satisfy another architectural layer. If a file is
moved during refactoring, update its existing registry entry instead of adding a
duplicate entry.

---

# 21. Agent Startup Procedure

Every production agent entering `final_project/` must follow this sequence:

```text
1. Read final_project/CONTEXT.md
        ↓
2. Read final_project/registry.md
        ↓
3. Inspect the current repository structure
        ↓
4. Identify the requested feature
        ↓
5. Locate its approved Planning Room artifacts
        ↓
6. Determine dependencies
        ↓
7. Check existing implementation and registry before creating files
        ↓
8. Implement only the required modules
        ↓
9. Run appropriate tests/validation
        ↓
10. Update registry.md and documentation when required
        ↓
11. Report files created/modified and remaining work
```

Never blindly recreate files that already exist.

---

# 22. Agent File-Creation Rule

Before creating a new file:

```text
Search existing project
        ↓
Check whether equivalent module exists
        ↓
Extend existing module if appropriate
        ↓
Create new module only when justified
        ↓
Update final_project/registry.md
```

Do not create empty placeholder folders. A new folder must contain at least one
real project file when it is introduced.

Do not duplicate:

```text
services
repositories
API clients
configuration
validation utilities
UI components
```

without checking the existing project structure first.

---

# 23. Agent Architectural Change Rule

If the implementation agent discovers that the approved plan is insufficient,
the agent must not silently redesign the system.

Instead:

```text
Observed problem
      ↓
Impact analysis
      ↓
Document proposed change
      ↓
Identify affected modules
      ↓
Update / request Planning Room contract
      ↓
Implement after the design is consistent
```

Small implementation-level decisions may be made locally.

Major changes involving:

```text
database architecture
API contracts
authentication
storage
RAG architecture
job orchestration
major frontend routing
```

must be reflected in the Planning Room documentation.

---

# 24. Local Development Architecture

The expected local development environment is approximately:

```text
                    Local Machine
────────────────────────────────────────────

Next.js
  ↓
frontend/

FastAPI
  ↓
backend/.venv/

Celery Worker
  ↓
same backend/.venv/

Redis
  ↓
local service

PostgreSQL + pgvector
  ↓
local service

MinIO
  ↓
local object storage

LLM
  ↓
configured provider

Embedding Model
  ↓
local model
```

These services may be started manually or through Docker/Compose depending on
the infrastructure implementation.

The architecture should remain explicit regardless of how services are started.

---

# 25. Recommended Local Service Separation

The application should be developed so that infrastructure can later move from:

```text
Local
```

to:

```text
Production
```

without changing the business layer unnecessarily.

Example:

```text
LOCAL                         PRODUCTION

MinIO                  →      AWS S3
PostgreSQL             →      Managed PostgreSQL
Redis                  →      Managed Redis
Celery worker          →      Scaled workers
Local embeddings       →      Local/GPU or hosted embeddings
Gemini/Groq            →      Enterprise-approved LLM provider
```

---

# 26. Final Production Principle

The final project must optimize for:

```text
Modularity
Traceability
Testability
Security
Replaceability
Clear ownership
Reproducible development
```

The goal is not to create the largest possible number of files.

The goal is to create **clear boundaries between responsibilities** so that one
module can be changed without unnecessarily breaking unrelated modules.

The final architecture should therefore follow:

```text
                    DOCUSENSE AI
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
      FRONTEND        BACKEND       DATABASE
          │              │              │
      Next.js         FastAPI       PostgreSQL
      React           Pydantic      pgvector
      TypeScript      SQLAlchemy    Alembic
      Tailwind        Celery
                      Redis
                         │
                         ↓
                  AI / RAG SERVICES
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
       Parsing       Embeddings       LLM
          │              │              │
       Docling       Local model    Configurable
       / Unstructured               provider
```

`final_project/` is the place where these components become the **actual
integrated DocuSense AI application**.
