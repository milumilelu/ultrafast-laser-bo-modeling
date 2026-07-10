# KnowledgeUseGate and on-demand review

Implementation paths:

- Claim classification and pure decision rules: `ultrafast_domain.review`
- Persistence/reuse/revocation: `ultrafast_integrations.storage.knowledge_use_repository`
- Application service: `ultrafast_memory.knowledge_use.service`
- Versioned schema: migration `0003_knowledge_use_gate`

## Usage boundary

No review is created for literature search, background explanation, defect summaries, measurement methods, or raw value display.

Review is required before evidence affects:

- Parameter recommendations.
- BO search bounds.
- Candidate filtering.
- Process-prior promotion.
- Safety/damage thresholds.
- Conflicting knowledge decisions.

Unknown intended uses, missing equipment revisions, rejected evidence, absent high-risk evidence, or proposed values outside machine bounds are blocked.

## Classification

The classifier accepts an optional LLM classifier but validates its fixed enums and treats it only as classification. Any failure uses deterministic rules:

- Number + unit → at least `medium`.
- Numeric upper/lower/range → `high`.
- Recommended/optimal/should use → `high`.
- Safety or damage threshold → `critical`.
- Definition, mechanism, or measurement method without numeric recommendation → `low`.

Neither LLM nor classification can approve evidence.

## Aggregated review

At most one proactive decision is created per task. A bundle contains at most five evidence items; extra items are reported as truncated. The user actions are:

- Approve for current task.
- Approve as reusable process prior.
- Reject use.

Task approval never creates a process prior. Prior approval creates scoped `process_prior` rows only from explicitly approved parameter payloads. All approval, rejection, and revocation actions append to `knowledge_review_action` in the same transaction.

## Reuse and invalidation

The approval key hashes:

- Source revision.
- Claim revision.
- Material and grade.
- Process type.
- Equipment revision.
- Intended use.
- Applicable-condition hash.

Current-task approval also requires the same task ID. Process-prior approval can be reused by another task only when the complete key matches. Source, claim, material, equipment, use, or condition changes produce a different key. Revoked approvals are excluded from reuse and their process priors are marked `revoked`.

## BO enforcement

The BO application service rejects requests marked as using literature-derived parameters/evidence unless `knowledge_gate_decision.status == allowed`. Unapproved prior payloads are ignored; approved priors must carry an approval ID and remain clipped to equipment bounds.

## API

- `POST /tasks/{task_id}/knowledge/use-gate`
- `GET /knowledge/usage-decisions/{decision_id}`
- `POST /knowledge/usage-decisions/{decision_id}/approve-task`
- `POST /knowledge/usage-decisions/{decision_id}/approve-prior`
- `POST /knowledge/usage-decisions/{decision_id}/reject`
- `POST /knowledge/usage-approvals/{approval_id}/revoke`
