Technology Stack

Philosophy

LociGraph is not a web application with AI features.

LociGraph is a knowledge engine that happens to expose a web interface.

The stack is selected to support the Knowledge Kernel rather than define it.

The most important architectural constraint is that business logic must remain independent from transport, interface, and deployment technologies.

The Knowledge Kernel should be executable from:

* CLI
* Worker processes
* Custodian interactions
* API endpoints
* Future interfaces

without modification.

⸻

Architecture Overview

Frontend
    │
    ▼
API Layer
    │
    ▼
Knowledge Kernel
    │
    ├── Concept Engine
    ├── Revision Engine
    ├── Contradiction Engine
    ├── Graph Engine
    ├── Planetarium Engine
    ├── Custodian Engine
    └── Ingestion Engine
    │
    ▼
Storage Layer

The Knowledge Kernel is the product.

Everything else is infrastructure.

⸻

Frontend

Next.js

Purpose:

* User interface
* Graph visualization
* Planetarium visualization
* Timeline exploration
* Custodian interface

Reasons:

* Mature ecosystem
* Excellent React support
* Easy deployment
* Strong TypeScript tooling
* Good support for real-time updates

⸻

React Three Fiber

Purpose:

Planetarium rendering.

Reasons:

* Three.js ecosystem
* React integration
* Large visualization community

⸻

React Flow / Cytoscape

Purpose:

Graph visualization.

Reasons:

* Interactive graph exploration
* Node and edge customization
* Mature tooling

⸻

API Layer

FastAPI

Purpose:

Transport layer only.

Responsibilities:

* Authentication
* Request validation
* Job submission
* Query execution
* Resource retrieval

Non-responsibilities:

* Concept logic
* Revision logic
* Planetarium logic
* Contradiction logic

These belong to the Knowledge Kernel.

Reasons:

* Strong Python ecosystem
* AI tooling compatibility
* Async support
* Automatic schema generation

⸻

Knowledge Kernel

Python

Purpose:

Core business logic.

Reasons:

* AI ecosystem
* Data processing ecosystem
* Graph tooling
* Embedding tooling
* Scientific computing ecosystem

The kernel must be framework-independent.

Example:

kernel.ingest(source)
kernel.resolve_concepts()
kernel.rebuild_graph()
kernel.rebuild_planetarium()

No FastAPI dependencies should exist inside the kernel.

⸻

Storage Layer

PostgreSQL

Purpose:

Canonical storage.

Stores:

* Sources
* Observations
* Claims
* Concepts
* Revisions
* Assertions
* Contradictions
* Importance signals
* Audit records

Reasons:

* Reliability
* JSON support
* Mature indexing
* Strong ecosystem

PostgreSQL is the source of truth.

⸻

pgvector

Purpose:

Semantic storage.

Stores:

* Embeddings
* Similarity relationships
* Semantic search metadata

Reasons:

* Native Postgres integration
* No additional vector database required
* Easy operational model

Embeddings are rebuildable.

They are not canonical truth.

⸻

Queue Layer

Redis

Purpose:

Job orchestration.

Stores:

* Pending jobs
* Running jobs
* Retry state
* Temporary worker coordination

Reasons:

* Simplicity
* Reliability
* Wide ecosystem support

Redis is not a source of truth.

⸻

Worker Layer

Dramatiq

Purpose:

Background execution.

Responsibilities:

* Ingestion
* Claim extraction
* Concept resolution
* Revision analysis
* Contradiction detection
* Graph rebuilding
* Planetarium rebuilding
* Janitorial cleanup

Reasons:

* Simpler than Celery
* Good reliability
* Easy operational model

⸻

AI Layer

Provider Architecture

Provider agnostic.

Single active provider at runtime.

Supported providers:

* OpenAI
* Anthropic
* Bedrock
* Future providers

Configuration:

ACTIVE_AI_PROVIDER=openai

Only one provider should execute work at a time.

Reasons:

* Cost control
* Simpler debugging
* Cleaner observability

⸻

AI Roles

Custodian

Interactive agent.

Responsibilities:

* Answer questions
* Retrieve evidence
* Navigate concepts
* Create user-approved records

The Custodian may suggest memory.

The user grants memory.

⸻

Librarians

Specialized background agents.

Types:

* Claim Librarian
* Concept Librarian
* Revision Librarian
* Contradiction Librarian
* Planetarium Librarian
* Janitor Librarian

Librarians operate on jobs.

They do not interact directly with users.

⸻

Deployment

Docker Compose

Services:

frontend
backend
worker
postgres
redis
caddy

Reasons:

* Simple operations
* Self-hosting friendly
* Easy backups
* Low maintenance burden

Kubernetes is intentionally excluded.

⸻

Storage Strategy

Layer 1: Canonical Storage

PostgreSQL

Truth layer.

⸻

Layer 2: Semantic Space

pgvector

Meaning layer.

⸻

Layer 3: Planetarium Projection

Projection tables

Visualization layer.

⸻

The planetarium is not the truth.

The graph is not the truth.

The embeddings are not the truth.

The canonical archive is the truth.

Everything else is a generated representation.