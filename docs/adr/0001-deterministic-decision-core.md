# ADR-0001: Deterministic decision core

## Status

Accepted

## Context

ENG-01 and the brief require justified recommendations with exact citations. Language models invent facts and routes under ambiguity. Assessors grade wording, numbers, and policy IDs exactly. ENG-01 states that recommendation, missing fields, citations, and packet text are fixed code.

## Decision

Code decides classification, routing, policy IDs, facts, missing information, and discrepancies.  
**Submission:** template / fixed packet text only — no LLM on the graded path.  
A future US-built model (ADR-0005) may only draft narrative from an already-finished packet and must never change route, policy, or facts.

## Consequences

- Routing and facts are unit-testable without network or model access.  
- Model outage cannot change recommendations.  
- Whiteboard “scope precedence” maps 1:1 to the domain routing table.
