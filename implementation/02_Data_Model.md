Data Model

Purpose

The data model exists to preserve the distinction between:

* raw source material
* normalized observations
* factual assertions
* perceptual assertions
* AI interpretations
* user corrections
* created concepts
* conceptual revisions
* graph relationships
* semantic vectors
* planetarium projections

LociGraph must never collapse these into one undifferentiated memory object.

The core rule:

Raw data becomes observations.
Observations support claims.
Claims support concepts.
Concepts evolve through revisions.
Graphs and planetarium views are generated projections.

⸻

Core Storage Layers

Layer 1: Canonical Storage

Canonical storage contains durable system truth.

Stored in PostgreSQL.

Includes:

* sources
* fragments
* observations
* claims
* concepts
* revisions
* assertions
* contradictions
* user decisions
* audit logs

This layer is authoritative.

⸻

Layer 2: Semantic Space

Semantic storage contains generated embeddings and vector metadata.

Stored in PostgreSQL with pgvector.

Includes:

* observation embeddings
* claim embeddings
* concept embeddings
* revision embeddings
* embedding model metadata

This layer is rebuildable.

⸻

Layer 3: Planetarium Projection

Projection storage contains spatial coordinates for visualization.

Includes:

* spherical coordinates
* cartesian coordinates
* projection version
* projection algorithm
* visual metadata

This layer is rebuildable.

The planetarium is not truth.

It is navigation.

⸻

Entity Overview

sources
├── fragments
│   └── observations
│       ├── claims
│       │   ├── reality_assertions
│       │   ├── perception_assertions
│       │   └── interpretations
│       └── semantic_vectors
│
concepts
├── concept_aliases
├── concept_revisions
├── concept_claim_links
├── contradictions
├── graph_nodes
├── graph_edges
├── importance_signals
├── semantic_vectors
└── planetary_nodes

⸻

Sources

sources

Represents an imported file, export, or external data source.

Raw source files may be purged after successful ingestion.

CREATE TABLE sources (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    original_filename TEXT,
    original_mime_type TEXT,
    checksum_sha256 TEXT NOT NULL,
    file_size_bytes BIGINT,
    raw_storage_path TEXT,
    import_status TEXT NOT NULL,
    retention_policy TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    quarantined_until TIMESTAMPTZ,
    purged_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Allowed import_status values:

PENDING
INGESTING
VERIFIED
QUARANTINED
PURGED
FAILED

⸻

Fragments

fragments

A format-dependent piece of source data.

For JSON, a fragment may be one message object.

For Markdown, a fragment may be a paragraph or section.

For PDF, a fragment may be a page or text block.

CREATE TABLE fragments (
    id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES sources(id),
    raw_index INTEGER,
    raw_payload JSONB,
    extracted_text TEXT,
    timestamp TIMESTAMPTZ,
    author TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL
);

Fragments preserve parsing context.

They are not yet the canonical knowledge unit.

⸻

Observations

observations

A normalized, input-agnostic memory unit.

Observations are canonical.

CREATE TABLE observations (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES sources(id),
    fragment_id UUID REFERENCES fragments(id),
    observed_at TIMESTAMPTZ,
    speaker TEXT,
    content TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    confidence NUMERIC NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Observation statuses:

active
archived
deleted
superseded

Rule:

Observations should remain stable after creation.
Corrections should create new records or audit events, not silent mutation.

⸻

Claims

claims

Atomic statements extracted from observations.

Claims are smaller than observations and easier to reason over.

CREATE TABLE claims (
    id UUID PRIMARY KEY,
    observation_id UUID NOT NULL REFERENCES observations(id),
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    confidence NUMERIC NOT NULL,
    extraction_method TEXT NOT NULL,
    model_name TEXT,
    prompt_version TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Claim types:

fact
event
belief
preference
definition
relationship
emotion
interpretation
decision
task

Claim statuses:

proposed
accepted
rejected
superseded

Rule:

No claim exists without an observation.

⸻

Concepts

concepts

The primary unit of LociGraph.

Concepts are created objects.

CREATE TABLE concepts (
    id UUID PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    description TEXT,
    concept_type TEXT NOT NULL,
    creation_method TEXT NOT NULL,
    created_by TEXT NOT NULL,
    confidence NUMERIC,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Concept types:

idea
person
place
object
event
system
value
belief
theme
project

Creation methods:

user_created
ai_created
hybrid
imported

Statuses:

active
merged
archived
deleted

⸻

concept_aliases

Stores alternate names for concepts.

CREATE TABLE concept_aliases (
    id UUID PRIMARY KEY,
    concept_id UUID NOT NULL REFERENCES concepts(id),
    alias TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence NUMERIC,
    created_at TIMESTAMPTZ NOT NULL
);

⸻

concept_claim_links

Links claims to concepts.

CREATE TABLE concept_claim_links (
    id UUID PRIMARY KEY,
    concept_id UUID NOT NULL REFERENCES concepts(id),
    claim_id UUID NOT NULL REFERENCES claims(id),
    relationship_type TEXT NOT NULL,
    confidence NUMERIC NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

Relationship types:

supports
defines
mentions
challenges
revises
contradicts
contextualizes

⸻

Reality and Perception

reality_assertions

Factual claims about what happened.

CREATE TABLE reality_assertions (
    id UUID PRIMARY KEY,
    concept_id UUID REFERENCES concepts(id),
    claim_id UUID REFERENCES claims(id),
    assertion_text TEXT NOT NULL,
    evidence_observation_ids UUID[] NOT NULL,
    confidence NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Reality assertions should be indifferent.

They describe what is evidenced, not what it meant.

⸻

perception_assertions

Claims about experience, interpretation, emotional framing, or narrative meaning.

CREATE TABLE perception_assertions (
    id UUID PRIMARY KEY,
    concept_id UUID REFERENCES concepts(id),
    claim_id UUID REFERENCES claims(id),
    assertion_text TEXT NOT NULL,
    emotional_frame TEXT,
    narrative_frame TEXT,
    evidence_observation_ids UUID[] NOT NULL,
    confidence NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Perception assertions are allowed to be subjective.

They must still cite evidence.

⸻

Interpretations

interpretations

AI or user-generated meaning structures built from claims and assertions.

CREATE TABLE interpretations (
    id UUID PRIMARY KEY,
    concept_id UUID REFERENCES concepts(id),
    interpretation_text TEXT NOT NULL,
    reasoning TEXT,
    source_claim_ids UUID[] NOT NULL,
    source_assertion_ids UUID[],
    confidence NUMERIC,
    created_by TEXT NOT NULL,
    model_name TEXT,
    prompt_version TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Interpretations are not facts.

They are provisional meaning structures.

⸻

Concept Revisions

concept_revisions

Tracks how a concept changes over time.

CREATE TABLE concept_revisions (
    id UUID PRIMARY KEY,
    concept_id UUID NOT NULL REFERENCES concepts(id),
    revision_label TEXT,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    definition TEXT NOT NULL,
    delta_from_previous TEXT,
    evidence_claim_ids UUID[] NOT NULL,
    evidence_observation_ids UUID[] NOT NULL,
    created_by TEXT NOT NULL,
    confidence NUMERIC,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Concept revisions allow the system to represent belief evolution.

⸻

Contradictions

contradictions

Represents unresolved or classified tension between claims, assertions, or revisions.

CREATE TABLE contradictions (
    id UUID PRIMARY KEY,
    concept_id UUID REFERENCES concepts(id),
    left_ref_type TEXT NOT NULL,
    left_ref_id UUID NOT NULL,
    right_ref_type TEXT NOT NULL,
    right_ref_id UUID NOT NULL,
    contradiction_summary TEXT,
    status TEXT NOT NULL DEFAULT 'unresolved',
    classification TEXT,
    user_resolution_note TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Contradiction statuses:

unresolved
reviewed
resolved
dismissed

Classifications:

true_conflict
evolution
contextual
both_true
unknown

Default:

unresolved

Rule:

The system must not force contradiction into conflict or evolution without review.

⸻

Graph Model

graph_nodes

Graph nodes represent concepts, claims, observations, events, or people.

CREATE TABLE graph_nodes (
    id UUID PRIMARY KEY,
    node_type TEXT NOT NULL,
    ref_id UUID NOT NULL,
    label TEXT NOT NULL,
    weight NUMERIC,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

⸻

graph_edges

Edges represent relationships between graph nodes.

CREATE TABLE graph_edges (
    id UUID PRIMARY KEY,
    source_node_id UUID NOT NULL REFERENCES graph_nodes(id),
    target_node_id UUID NOT NULL REFERENCES graph_nodes(id),
    edge_type TEXT NOT NULL,
    weight NUMERIC NOT NULL,
    confidence NUMERIC,
    evidence_ids UUID[],
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Edge types:

supports
contradicts
revises
mentions
associated_with
subconcept_of
alias_of
caused_by
part_of
near

⸻

Semantic Vectors

semantic_vectors

Stores embeddings for observations, claims, concepts, and revisions.

CREATE TABLE semantic_vectors (
    id UUID PRIMARY KEY,
    ref_type TEXT NOT NULL,
    ref_id UUID NOT NULL,
    embedding VECTOR,
    embedding_model TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'
);

Important:

Vectors are generated data.
They can be rebuilt.
They are not canonical truth.

⸻

Planetarium

planetary_nodes

Stores spatial projection data for concept visualization.

CREATE TABLE planetary_nodes (
    id UUID PRIMARY KEY,
    concept_id UUID NOT NULL REFERENCES concepts(id),
    projection_version TEXT NOT NULL,
    projection_algorithm TEXT NOT NULL,
    x NUMERIC NOT NULL,
    y NUMERIC NOT NULL,
    z NUMERIC NOT NULL,
    radius NUMERIC NOT NULL,
    theta NUMERIC,
    phi NUMERIC,
    mass NUMERIC,
    brightness NUMERIC,
    color TEXT,
    visual_class TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Visual classes:

planet
moon
star
black_hole
constellation_anchor
archive_point

⸻

importance_signals

Stores factors that contribute to conceptual mass.

CREATE TABLE importance_signals (
    id UUID PRIMARY KEY,
    concept_id UUID NOT NULL REFERENCES concepts(id),
    signal_type TEXT NOT NULL,
    value NUMERIC NOT NULL,
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Signal types:

frequency
recency
emotional_intensity
user_pin
graph_centrality
time_depth
revision_count
ai_significance
custodian_interaction

Mass should be computed from signals using a versioned formula.

⸻

Custodian Logging

custodian_sessions

Represents a conversation with the Custodian.

CREATE TABLE custodian_sessions (
    id UUID PRIMARY KEY,
    provider TEXT,
    model_name TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'
);

⸻

custodian_messages

Stores messages exchanged with the Custodian.

CREATE TABLE custodian_messages (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES custodian_sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Roles:

user
custodian
system
tool

⸻

custodian_logged_items

Represents items explicitly logged from Custodian conversations.

CREATE TABLE custodian_logged_items (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES custodian_sessions(id),
    message_id UUID REFERENCES custodian_messages(id),
    item_type TEXT NOT NULL,
    target_ref_type TEXT,
    target_ref_id UUID,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Item types:

observation
claim
concept_candidate
reality_assertion
perception_assertion
contradiction
importance_signal
task
note

Rule:

The Custodian can suggest memory.
The user grants memory.

⸻

Jobs

jobs

Tracks background work.

CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    payload JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

Job types:

ingest_source
extract_claims
resolve_concepts
detect_revisions
detect_contradictions
build_graph
generate_embeddings
project_planetarium
purge_raw_source
janitor_cleanup

⸻

Audit Logs

audit_logs

Tracks meaningful changes and user decisions.

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    target_ref_type TEXT NOT NULL,
    target_ref_id UUID NOT NULL,
    before_state JSONB,
    after_state JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

Actor types:

user
custodian
librarian
system

⸻

Deletion Model

Deletion is tiered.

Raw Source Deletion

Deletes raw uploaded files after ingestion and verification.

Preserves:

* source metadata
* checksum
* observation count
* purge timestamp

⸻

Derived Data Deletion

Can delete and rebuild:

* embeddings
* graph edges
* planetarium projections
* summaries

⸻

Canonical Data Deletion

Requires explicit override.

May affect:

* observations
* claims
* concepts
* revisions
* assertions

Concepts can die, but only through deliberate user action or explicit policy.

⸻

Core Invariants

1. Raw sources are optional after verified ingestion.
2. Observations are the canonical memory unit.
3. Claims must cite observations.
4. Concepts are created and versioned.
5. Reality and perception are separate.
6. Interpretations are provisional.
7. Contradictions are unresolved by default.
8. Embeddings are rebuildable.
9. Planetarium projection is rebuildable.
10. User corrections override AI suggestions.
11. Custodian chat is not automatically canonical.
12. The user grants memory.