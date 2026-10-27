# TraceMem-Code development candidate

The coding track tests reuse of historical engineering experience. The current
AML scored suite is CAMBench Coding:150 base tasks in relevant/noisy conditions,
300 attempts. The official repository says its coding data and verifiers remain
unreleased. No official score can be produced locally from those private tasks.
SWEContextBench is a public reference, explicitly not the current AML scored suite.

Sources checked on2026-10-27:
- https://agentmemoryleaderboard.ai/api-guide
- https://github.com/AML-memory/agent-memory-leaderboard/blob/main/README.md
- https://github.com/jiayuanz3/SWEContextBench

## Model requirements

The official Academic/Open-source rules cover Coding too: embeddings must use
`text-embedding-v4`; all LLM-related components must use `gpt-4o-mini`.
Reranker models are unrestricted by AML. Commercial/Industry entries do not have
these model restrictions. The platform fixes its own answering model and scorer;
this submission only manages and returns memory evidence. Our exact-Qwen rule is
an additional project constraint, not an AML mandate. See the API guide's
"How the platform works" section (checked2026-10-27).

## Candidate behavior

Development started in an isolated `codex/coding-memory-v1` worktree derived from
multimodal commit18aff5a1da91a7ab8817e603c1e577824dd98cbf. The user requires the
audited Coding release to live in a separate `cenzihan/trace-mem-code` repository.
Existing deployed multimodal code,
container, data, model weights and submission are unchanged.

Add preserves source strings and indexes contiguous spans up to4096UTF8 bytes.
Each nonempty span may receive a source-grounded engineering summary from the
permitted `gpt-4o-mini`; `text-embedding-v4` produces256-dimensional vectors.
Search fuses code-aware BM25, exact file/symbol anchors, and dense ranks.
Zero-overlap lexical rows are excluded from fusion. Search returns original
source substrings, with stable parent/offset IDs, at most3 spans per source,
bounded by the requested top_k and32768UTF8 response bytes. Summaries are never
returned as source evidence. Queries/options are not persisted.

The first live profile does not invoke a reranker. The optional scorer interface
accepts only the original Qwen/Qwen3-VL-Reranker-2B revision and weight identity;
there is no hosted alias substitution. No new GPU process is required.

## Development validation

Synthetic tests cover Unicode/source integrity, idempotence and conflicts,
cross-user isolation, partial-index detection, uncertain-call no-replay,
restart persistence, response limits, HTTP authentication, and persistent call caps.
These are contract checks, not real-model benchmark results.

`scripts/prepare_coding_git_history.py` freezes4 earlier public changes from our
audited repository, paired with real later change subjects/file metadata. Only
historical patches are read; target patches/test answers are not supplied.
One-history and four-history conditions exercise protocol and retrieval behavior.
This is a real Git-history engineering fixture with constructed query envelopes,
not CAMBench, SWEContextBench, independent evidence, or a task-solve benchmark.
The Hugging Face SWEContextBench card preview exposed several Astropy rows during
license review; those rows are not used for development or reported evaluation.

The frozen live plan is8 Add,8 Search, one post-restart Search:31 expected provider
calls (14 GPT and17 embedding), a durable maximum32 calls and at mostCNY8 within the
originalCNY500 ledger. No second money ledger, old632-call grant reset, official
Smoke, Full run, or automatic unknown-request replay is permitted. Actual results
and accounting must be recorded before claiming live validation.

## Integration limits

The opt-in factory is `agent_memory.coding_app:create_app()`. It requires a separate
`coding-*` runtime, Bearer secret, original server-ledger authority, verified prices,
an immutable lifetime provider-call cap, and a development lease within7days.
Current Add capacity is16 messages,128KiB per message and64 source spans per call;
query capacity is8192UTF8 bytes. Add is synchronous and acknowledged only after
durable raw/index commit. Failed or uncertain model outcomes block automatic retry.
Capacity must be evaluated against official Coding Smoke before a scored run.
`compose.coding.yaml` binds only loopback port8768 and shares the original ledger
directory, while mounting the multimodal state read-only. A separate Bearer token
and expiry are mandatory. This is a finite development deployment, not an official
endpoint: after its pilot, the remaining call slots must not be reset or reused for
an unplanned run. The Docker build context excludes runtime and private fixtures.

An Eval Key has not yet been observed in this task. The multimodal access request
was submitted; a coding-track registration/binding is a separate unfinished step.
The existing total official Smoke authorization is5 across this task, not5 new
calls per track. Full remains outside the authorized scope.
