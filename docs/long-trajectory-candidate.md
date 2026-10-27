# Long-trajectory candidate v0.2.3-rc1

Status: offline candidate only. Not deployed, bound or officially evaluated.

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
original money ledger. It retains the existing5CNY readiness floor. Per-call
reservations remain authoritative if another service consumes shared funds.

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
