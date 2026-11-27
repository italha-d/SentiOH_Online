# Case closure and portable audit

## Normal lifecycle

A case does not disappear when the last operational task is completed.

For CONFIRMED exposure:

```text
CONFIRMED
  -> RESPONDING
  -> all tasks COMPLETED
  -> all required reviews REVIEWED
  -> RESOLVED
  -> authorised final closure
  -> CLOSED
```

For POSSIBLE exposure:

```text
REVIEW_REQUIRED
  -> evidence-gathering tasks COMPLETED
  -> required review REVIEWED
  -> RESOLVED
     (the deterministic exposure classification remains POSSIBLE)
  -> authorised final closure
  -> CLOSED
```

A later source update or new evidence can still reopen a case for re-analysis.

## Final closure authority

Only:

- Recall / Incident Manager
- Senior Responsible Manager

can close a RESOLVED case.

The Response tab treats RESOLVED as still open and displays one final human
closure action to an authorised role.

## Audit source of truth

The live case source of truth remains:

```text
runtime/sentioh_cases.db
```

Each case is stored as JSON in the SQLite `cases.payload` field and includes
the complete `audit_timeline`.

## Portable final audit

When a case becomes CLOSED and is persisted, SentiOH automatically creates:

```text
audit_exports/<CASE-ID>_audit.json
audit_exports/<CASE-ID>_audit.sha256
```

The JSON contains:

- case identity and lifecycle
- official source recall evidence
- deterministic exposure result
- resolution and closure metadata
- tasks and human approvals
- human reviews
- task/review history
- recall-version information
- LLM recommendation/evidence-gap reasoning
- full chronological audit timeline

The `.sha256` sidecar contains the checksum of the exact JSON export. The
dashboard's download button returns that exact persisted JSON file.

Closed cases remain available to authorised management users in the
**Closed Case Archive**.

## Two-approval quick-close demonstration

The prototype includes a deliberately streamlined, clearly labelled demo-only
case. It is based on the genuine bundled FSAI 2026.38 recall and the synthetic
company SKU398 evidence.

Operational containment and trace evidence are pre-recorded **for demo
purposes only**, and the audit explicitly says so.

Exactly two approval tasks remain:

1. Warehouse Manager:
   `Approve containment evidence package`
2. Recall / Incident Manager:
   `Approve response package for closure`

After approval 2, the case automatically becomes RESOLVED. The logged-in
Recall / Incident Manager then records the final closure decision. SentiOH
shows `CASE CLOSED`, closure metadata and the downloadable complete audit.

This quick profile is intentionally separate from the full operational
CONFIRMED-case workflow and does not change normal workflow rules.
