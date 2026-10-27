# Long-trajectory candidate v0.2.3-rc3

Status: offline candidate only. Not deployed, bound or officially evaluated.

The rc2 candidate adds a private, 64 KiB capped admission log inside the existing
Coding state directory and retention scope. Each entry contains only UTC time,
HTTP status and one of six fixed reasons: message count, per-message bytes,
per-Add bytes, source span count, remaining provider calls, or remaining original
budget. It never stores source text, identifiers, questions, credentials or raw
exception messages. Existing entries are not rotated away; a full/unwritable log
does not alter rejection or enable a model call. This can diagnose future
capacity failures but cannot recover the missing historical failure branch.

The earlier Coding service returned HTTP413 before model dispatch. Minimal HTTP
metadata cannot identify which old capacity guard rejected the input. This
candidate addresses all known source admission bottlenecks without reconstructing
or replaying official inputs. The [AML API guide](https://agentmemoryleaderboard.ai/api-guide)
defines ordered source messages and atomic, immediately searchable Add success;
it does not establish our old20-message implementation cap as a Coding limit.

The optional entry point is `agent_memory.coding_trajectory_app:create_app()`.
The existing `coding_official_app` entry point and its v0.2.2 defaults are retained.
No deployment configuration or published release tag changes in this patch.

| Capacity | Candidate limit |
| --- | --- |
| Messages per Add | 1024 |
| UTF-8 source bytes per message | 2MiB |
| UTF-8 source bytes per Add | 8MiB |
| Source spans per Add | 2048 |
| Source span | 4096UTF-8 bytes, lossless Unicode offsets |
| Embedding batch | At most8 spans |

These are explicit local admission bounds, not a promise that the finite provider
allowance can fund every maximum-size request. Before claiming an Add or calling
a model, the service checks the entire planned call count against the remaining
original512-call Coding lifetime guard and checks conservative cost against the
original money ledger. Rc3 also keeps16 calls and their conservative embedding
allowance available for Search, in addition to the existing5CNY readiness floor.
An Add that consumes every remaining slot would otherwise succeed but leave
the newly stored sources unavailable to query embedding. With11 lifetime calls
already used, up to431 source spans fit this guard:431 GPT calls plus54 embedding
batches leave16 query calls. A445-span Add would exhaust the guard and is rejected
before Add claim or model dispatch. These are call-count bounds, not latency or
benchmark guarantees. Per-call reservations remain authoritative if another
service consumes shared funds; this does not create a separate money budget.

All source messages, roles, timestamps and ordering remain intact. Index work is
batched internally; success is returned only after every source and index commits
together. A failure in a later batch records an uncertain Add, acknowledges no
partial write and cannot be automatically replayed. Successful replay after a
restart returns the original acknowledgement without paid calls.

The retrieval method is unchanged: GPT-4o-mini source indexing, text-embedding-v4
256-dimensional vectors, code BM25/exact anchors/RRF, and raw source windows.
This patch neither generates final answers nor uses a new model. Per-span GPT
work can still make large writes expensive or slow. The live capacity and latency
must be validated separately before a fixed release or another Coding Smoke.

Tests use independently authored synthetic code and Unicode text, including a
130-message trajectory over500KB, later-batch failure, replay, user isolation,
capacity rejection and unchanged money/call histories. They are not benchmark
results or evidence that the earlier official runtime error is resolved.
