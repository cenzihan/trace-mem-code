# TraceMem-Code v0.2.0 access candidate

This independent Coding service activates source-window context projection after
code-aware BM25, exact path/symbol anchors and dense reciprocal-rank fusion.
Original messages remain authoritative. GPT summaries are index-only metadata;
Search returns source substrings with stable range IDs, never a generated answer.
The [DeepSeek Harness review](deepseek-harness-adaptation.md) documents the design
inspiration and the limits of this adaptation. No DSH source code or runtime is
included and no DeepSeek model is used.

The Academic profile fixes gpt-4o-mini and text-embedding-v4 at256 dimensions.
There is no reranker. GPT uses strict source-card JSON Schema; invalid optional
quote metadata cannot be promoted to evidence. Search options are accepted but
not persisted. Source/query instructions are data and are never executed.

Run `compose.coding-official.yaml` with the existing server-owned ledger root,
separate service token and explicit expiry. The factory requires dedicated
`coding-official-v0.2` state and a fixed512-call lifetime traffic ceiling.
This is not another money allowance: every request uses the same original CNY500
ledger, with receipt-first accounting, unknown-call blocking and no automatic
provider retry. The previous32-call development guard and its31 used receipts
are preserved; it is not reset or reused for this release.

Limits:20 messages/Add,128KiB/source message,64 source segments/Add,4096UTF8
bytes/segment,8192UTF8 query bytes,12288bytes/source window and32768bytes total
returned text. Excess input fails explicitly instead of silently truncating
original evidence. These are declared local capacities, not AML-wide rules.
HTTP admits16 requests with30s bounded waiting and one active model operation.
Add is synchronous and replay-idempotent, Search respects user isolation and
top_k, and committed data survives process restart. Health checks make no model
calls. Source and derived data require a scheduled purge; financial metadata
must survive cleanup. Lease/retention dates belong to the concrete deployment.

Offline validation covers format/type failures, exact original windows,
cross-user isolation, Unicode/source offsets, idempotence, restart, immutable
call guards, lease expiry and concurrent admission. All75 checks passed without
providers. The earlier31-call pilot remains historical. Deployment preflight,
official approval and official Smoke are separate milestones; this release
does not claim an official score or a measured improvement over v0.1.

Public reviewable source retains NOTICE. No permissive open-source license is
asserted. Official application notes must disclose that status, exact models,
version, public authenticated endpoints and all operational limits.
