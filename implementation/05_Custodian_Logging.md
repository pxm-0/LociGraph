# Custodian Logging

Custodian conversations are not only interface events.
They can become ingestion events.

## Purpose

The user should be able to say things like:

- Log this as an observation.
- Make this a concept.
- Attach this to Sovereignty.
- Mark this as perception, not reality.
- Create a contradiction for this.
- Pin this as important.
- Create a task from this.

## Core Tables

custodian_sessions
- id
- started_at
- ended_at
- model
- provider

custodian_messages
- id
- session_id
- role
- content
- timestamp

custodian_logged_items
- id
- session_id
- message_id
- item_type
- target_id
- content
- status
- created_at

## Item Types

- observation
- claim
- concept_candidate
- reality_assertion
- perception_assertion
- contradiction
- importance_signal
- task
- note

## Rule

Custodian chat logs are not automatically canonical.

They become canonical only when:
- explicitly logged by user, or
- proposed by Custodian and accepted by user.

## Status

- proposed
- accepted
- rejected
- superseded

## Design Principle

The Custodian can suggest memory.
The user grants memory.
