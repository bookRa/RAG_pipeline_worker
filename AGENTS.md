# AGENTS

This document outlines the roles and responsibilities of the AI agents involved in building and evolving the document-extraction pipeline.  
Following Specification-Driven Development (SDD), the specification is the single source of truth and agents operate on it to produce plans, code, and tests.  
Each agent works independently within well-defined boundaries, enabling parallel development while preserving cohesion.

---

## Research Agent

| Trigger & Inputs | Responsibilities | Outputs / Deliverables | Dependent on |
|------------------|------------------|--------------------------|---------------|
| Kick-off of a new feature or when requirements change | - Search authoritative sources (official docs, academic papers) to gather guidelines on chunking, metadata, observability, and architecture.<br>- Summarize findings with citations and highlight risks, trade-offs, and best practices.<br>- Provide background context for decision making. | Research report summarizing key facts and recommendations with citations, stored in `docs/research/*.md`. | — |

---

## Specification Agent

| Trigger & Inputs | Responsibilities | Outputs / Deliverables | Dependent on |
|------------------|------------------|--------------------------|---------------|
| After research or user feedback | - Draft and update Round Requirements documents (e.g., `Round_1_Requirements.md`) capturing product needs, user stories, and non-functional requirements.<br>- Define acceptance criteria and scope for each iteration.<br>- Resolve ambiguities and refine scope through dialogue with stakeholders. | Updated requirements files with clear acceptance criteria. | Research agent, Planning agent |

---

## Planning Agent

| Trigger & Inputs | Responsibilities | Outputs / Deliverables | Dependent on |
|------------------|------------------|--------------------------|---------------|
| New round of work after requirements are frozen | - Design high-level architecture and module breakdown that satisfy requirements and align with hexagonal principles.<br>- Identify domain models, ports, adapters, and services.<br>- Create a work plan specifying which modules to implement or modify and assign tasks to agents. | Implementation plan in Markdown outlining module responsibilities, sequence of work, and interface definitions. | Specification agent |

---

## Coding Agent

| Trigger & Inputs | Responsibilities | Outputs / Deliverables | Dependent on |
|------------------|------------------|--------------------------|---------------|
| When implementation plan is ready | - Generate the code skeleton corresponding to the plan.<br>- Implement data models, services, adapters, and API endpoints with stub or production logic.<br>- Ensure module interfaces match the specification and are stable.<br>- Respect separation of concerns; the domain layer must not depend on adapters.<br>- Update `requirements.txt` minimally. | Commit(s) containing source code under `src/`, updated `requirements.txt`, and documentation as needed. | Planning agent |

---

## Test Agent

| Trigger & Inputs | Responsibilities | Outputs / Deliverables | Dependent on |
|------------------|------------------|--------------------------|---------------|
| Concurrent with Coding Agent | - Write unit tests for each new or modified module using pytest.<br>- Create end-to-end tests that exercise the FastAPI endpoints via TestClient.<br>- Ensure tests reflect acceptance criteria in the specification.<br>- Provide mocks or fakes for external dependencies so that tests run offline. | Test files under `tests/` and test documentation. | Planning agent, Coding agent |

---

## Observability Agent

| Trigger & Inputs | Responsibilities | Outputs / Deliverables | Dependent on |
|------------------|------------------|--------------------------|---------------|
| When any pipeline stage is implemented or changed | - Propose logging/tracing instrumentation and metrics to capture the inputs and outputs of each service.<br>- Ensure that observability concerns are decoupled from business logic.<br>- Define structured log schemas that include metadata fields (e.g., chunk IDs, document IDs, processing times). | Documentation on observability strategy and logging code in `observability/` modules. | Planning agent, Coding agent |

---

## Review Agent

| Trigger & Inputs | Responsibilities | Outputs / Deliverables | Dependent on |
|------------------|------------------|--------------------------|---------------|
| Before merging new code | - Validate that the implementation matches the specification and planning documents.<br>- Review adherence to coding standards, linting, and test coverage.<br>- Identify inconsistencies or missing acceptance criteria and flag them for revision. | Review feedback as comments or change requests. | All prior agents |

---

## How Agents Collaborate

- The **Research Agent** gathers factual insights about chunking, metadata enrichment, cleaning operations, and architecture patterns.  
  These insights inform the specification and are cited in the requirements.

- The **Specification Agent** translates business needs and research into a well-formed requirements document.  
  The specification defines the shape of the data model and acceptable outputs for each pipeline stage.

- The **Planning Agent** decomposes the specification into modules and interfaces, adhering to hexagonal architecture guidelines that separate domain logic from external concerns.

- The **Coding Agent** and **Test Agent** work in parallel:  
  the former generates code based on the plan, and the latter writes tests based on the specification.  
  Tests serve as executable acceptance criteria, aligning with the SDD paradigm.

- The **Observability Agent** ensures each pipeline stage emits useful telemetry and can be traced end-to-end without polluting the business logic.

- The **Review Agent** checks that all artifacts—specifications, plans, code, and tests—are consistent.  
  Only when the review passes are changes merged back into the main branch.

---

## Notes

- This agent framework is flexible. For small iterations, some roles may be combined, but the responsibilities should always be clear.  
- The order of agents reflects the SDD workflow: **research → specification → planning → coding/testing → observability → review**.  
- Additional agents (e.g., Deployment or Security) can be added in future rounds as the pipeline evolves.