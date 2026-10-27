# DeepSeek Harness design review and Coding adaptation

Reviewed2026-10-27 against DeepSeek-AI's official repository at
`22ddee3792402c3e70ec5f86a63c3e3e895a2f60`:

- [Architecture](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/docs/architecture.md)
- [Session log and derived surface](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/docs/subsystems/session.md)
- [Compaction and tool-pair boundaries](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/docs/subsystems/compaction.md)

## What transfers to a memory service

DSH is an agent runtime, not a Coding-memory benchmark method. Its typed,
append-only event log is the original record; model context is a derived view.
View replacements cite source events. Compaction records its range, lifecycle and
outcome, and preserves tool-call/result pairing. Plugins separate these policies
from the agent loop. These are useful engineering principles, not evidence of a
retrieval-score improvement for TraceMem-Code.

Our existing raw-message store, derived index and durable Add state already
separate source evidence from summaries and detect unfinished operations. The
new candidate extends source-grounded **context projection** after ranking:

1. Preserve the ranked match and load its original message within the same user.
2. Validate that parent's indexed spans against their source hashes and offsets.
3. Add at most one directly contiguous preceding span and one following span.
   Check the preceding neighbor first; never cross an unindexed gap or message.
4. Return the original contiguous substring, stable parent/range ID and the
   match's score. Diagnostics identify the matched span, all source spans and the
   resulting content hash. They are transient, with no query or content log added.

The source-window mode defaults to12288UTF8 bytes per window and32768 total,
honors top_k and returns at most one window per original message. It never crops
a matched span to fit. This trades evidence diversity for local continuity and
is enabled in the v0.2.0 access candidate. Retrieval-quality improvement remains unproven. It does not restore whole tool
episodes: AML's text Add schema has user/assistant messages, not DSH tool-call
events, so missing structural labels cannot be invented.

This window algorithm is our original implementation, inspired by the separation
of source and context projection. It is not DSH compaction, a port of DSH source,
or a claim to reproduce DSH performance. No DeepSeek runtime or model is installed.
We deliberately do not copy model-visible prompt logging because this service's
privacy policy excludes persistent evaluation queries and raw provider responses.

## Activation and validation

The versioned `coding_official_app` factory enables `source-window`, strict GPT
JSON Schema,20-message admission and16 bounded HTTP admissions with one active
model operation. `compose.coding-official.yaml` deploys v0.2.0 separately from
the unchanged v0.1 development state and its exhausted pilot authorization.
The constructor default remains `matched-spans` for existing research callers.

Synthetic tests cover original order, source references, Unicode budgets,
unindexed gaps, user/parent isolation, corrupted neighbors, stable restart,
source integrity and unchanged provider-call counts. These are offline contracts,
not a new real-model run or a scored ablation. The completed31-call pilot and its
remaining slot are not reused. Before a later online comparison, freeze a new
independent public-history selection and compare both modes with the same index,
ranked candidates, top_k and response-byte budget; report retrieval and task-level
effects separately. Do not tune on the already examined four-case proxy.

## Model and agent boundaries

AML Academic rules still require text-embedding-v4 and gpt-4o-mini for their
respective embedding and LLM components. Rerankers are unrestricted by AML;
the project's exact-Qwen constraint is additional. DSH's plugin architecture does
not authorize changing models. Search still returns source evidence, never a final
answer, and never executes the retrieved code or instructions. Tool loops,
subagents and agent teams are outside this memory API's scope.
