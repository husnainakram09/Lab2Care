
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

To enable the Vultr AI investigation, configure these variables in your local shell:

```bash
export FOLLOWUP_ENABLE_LOCAL_AGENT=1
export VULTR_MODEL="deepseek-v4.1-flash-1017"
```

Set `VULTR_SERVERLESS_INFERENCE_API_KEY` securely in the environment. Do not commit the key or place it in frontend code. Confirm that the selected model remains available in your Vultr account.

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

## Reset the demonstration

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

Do not expose `api.dev_main:app` directly to the public internet.

Local confirmation headers and fixed fictional actor identifiers are not authentication. The public version requires separate access controls, session isolation, inference usage limits, and security review.

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
