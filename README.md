
# Doctor-Supervised Test Results & Follow-up

An evidence-linked AI agent and fictional patient follow-up application developed for the Vultr Agent Rush Hackathon 2026.

**Status:** Functional local research prototype. Not a clinical product, authenticated clinic system, or publicly deployed application.

## The problem

Laboratory reports can arrive asynchronously with incomplete or ambiguous administrative references. Patients may be left uncertain while clinic staff investigate missing reports and coordinate clinician-reviewed follow-up.

This project demonstrates an AI-assisted administrative investigation workflow while keeping clinical decisions under explicit human control.

## What the application does

- Tracks ordered, received, and pending fictional laboratory reports.
- Uses Vultr Serverless Inference for bounded, model-selected investigation tools.
- Inspects source-linked laboratory evidence and drafts staff clarification requests.
- Withholds mismatched-patient records and prevents automatic report attachment.
- Simulates separate staff verification and version-checked report ingestion.
- Requires a separate fictional clinician approval before communication.
- Queues approved instructions and verifies delivery through an isolated fake destination.
- Records patient receipt acknowledgement separately from clinical follow-up completion.
- Maintains persistent SQLite records and a database-derived audit timeline.
- Displays aggregate synthetic FHIR research findings separately from the fictional case.

The AI does not diagnose, prescribe, authorize treatment, approve follow-up instructions, or independently send patient notifications.

## Technology

Python 3.12, FastAPI, SQLite, JavaScript, HTML/CSS, the OpenAI-compatible Python SDK, and Vultr Serverless Inference.

## Local setup

Requires Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create the persistent fictional demonstration database once:

```bash
python -c "from api.demo_state import prepare_demo_db; print(prepare_demo_db())"
```

This command refuses to overwrite an existing demo database.

## Run automated tests

```bash
python -m unittest discover -s tests -v
```

The test suite covers reconciliation, evidence access, agent tool boundaries, report ingestion, approvals, notification delivery, acknowledgement, audit history, reset behavior, HTTP endpoints, and research adapters.

Passing synthetic tests does not establish clinical safety or production security.

## Run the local application

Copy `.env.example` to `.env` and set `VULTR_SERVERLESS_INFERENCE_API_KEY` to enable the Vultr AI investigation. The application reads `.env` at startup; variables already set in the environment take precedence. `.env` is ignored by Git. Do not commit the key or place it in frontend code. Confirm that the selected model remains available in your Vultr account.

Alternatively, set the same variables (`FOLLOWUP_ENABLE_LOCAL_AGENT=1`, `VULTR_MODEL`, `VULTR_SERVERLESS_INFERENCE_API_KEY`) directly in your shell.

Start the development server:

```bash
python -m uvicorn api.dev_main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/

The patient, staff, clinician, notification, and acknowledgement actions are simulations using fictional identities and records.

The model-powered investigation requires a valid Vultr inference key. Other local workflow operations and the automated tests do not require model inference.

## Demonstration sequence

1. Open the fictional case with two of three reports received.
2. Run the Vultr AI investigation of the unresolved report.
3. Review source-linked evidence and the generated staff clarification.
4. Simulate independent lab confirmation and staff-verified report receipt.
5. Simulate clinician approval of administrative follow-up instructions.
6. Queue and verify the fictional notification.
7. Record fictional patient acknowledgement.
8. Inspect the persisted audit timeline.

The six patient-facing states are:

`AWAITING_REPORTS` → `AWAITING_CLINICIAN_REVIEW` → `APPROVED_FOR_COMMUNICATION` → `DELIVERY_UNCONFIRMED` → `DELIVERED` → `ACKNOWLEDGED`.

Acknowledgement records message receipt only, not completion of clinical care.

## Shared and guest modes

By default the application serves one shared fictional case, intended for a single local developer. Changes to it are accepted only from the local machine.

A public deployment must set `FOLLOWUP_GUEST_SESSIONS=1` (as `deploy/start.sh` does). Each browser then receives a private copy of the fictional case through an HttpOnly cookie, so no visitor can complete or change the demonstration for anyone else. Visitors can use **Start over** to get a fresh case. Guest cases are stored under `runtime/sessions/`, expire 24 hours after their last change, and the oldest are removed beyond `FOLLOWUP_MAX_GUEST_SESSIONS` (default 300).

Behind a reverse proxy every request appears to come from the local machine, which is why the shared case must not be served publicly.

| Variable | Purpose | Default |
|---|---|---|
| `FOLLOWUP_GUEST_SESSIONS` | `1` gives each visitor a private case | shared case |
| `FOLLOWUP_SECURE_COOKIES` | `1` marks the session cookie HTTPS-only | off |
| `FOLLOWUP_MAX_GUEST_SESSIONS` | Maximum stored guest cases | 300 |
| `FOLLOWUP_AI_RUNS_PER_SESSION_HOUR` | AI investigations per case per hour | 5 |
| `FOLLOWUP_AI_RUNS_PER_HOUR` | AI investigations per hour, all visitors | 60 |
| `FOLLOWUP_AI_MAX_CONCURRENT` | Simultaneous AI investigations | 2 |

The hourly AI limit for all visitors is the hard bound on inference spending, because a visitor can discard their cookie to start a new case. The limits apply per Uvicorn process; the deployment runs one worker.

## Reset the demonstration

In guest mode, visitors reset their own case with **Start over**. The steps below reset the shared case.

Stop Uvicorn before resetting.

```bash
python -m scripts.reset_demo --confirm-fictional-reset
```

The previous fictional demo directory is archived under `runtime/archives/`, and a fresh case is created.

The `runtime/` directory is excluded from Git.

## Research provenance

The repository contains research scripts and aggregate audit results for:

- MIMIC-IV Clinical Database Demo v2.2 (PhysioNet).
- SMART on FHIR Synthea-generated sample bulk datasets.

Raw downloaded source files are intentionally excluded from Git under `research/data/`.

The Synthea audit identified 11 Patient resources, 413 ServiceRequests, 780 DiagnosticReports, and 2,850 Observations. All 780 DiagnosticReports had patient references, but none had an explicitly resolved ServiceRequest linkage under the implemented audit method.

These findings do not establish missed clinical follow-up. The active fictional case `CASE-001` is not a reconstructed Synthea or MIMIC patient.

Research summaries retain source provenance and archive checksums.

## Security and limitations

**LOCAL DEVELOPMENT ONLY.**

Do not expose `api.dev_main:app` directly to the public internet, and never serve the shared case publicly. A public deployment must run in guest mode behind an HTTPS reverse proxy.

Guest sessions isolate fictional demo state; they are not authentication. Confirmation headers and fixed fictional actor identifiers do not identify real people. Any use beyond a fictional demonstration requires real access controls and a security review.

No real patients, real clinical decisions, real laboratory communications, or real notification services are involved.

## Project structure

- `agent/` — Bounded AI investigation and tools
- `api/` — Local HTTP integration and workflow actions
- `core/` — Deterministic reconciliation and patient states
- `storage/` — SQLite cases, approvals, outbox, and acknowledgements
- `services/` — Fictional notification gateway and worker
- `fixtures/` — Fictional demonstration records
- `research/` — Data audits and aggregate provenance
- `scripts/` — Evaluation, demo preparation, and reset
- `tests/` — Automated regression suite
- `web/` — Local patient and staff application

## Deployment status

A public Vultr-hosted URL has not yet been verified. Deployment and public access controls remain separate engineering tasks.
