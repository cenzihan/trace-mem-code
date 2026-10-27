# TraceMem-Code

Coding-memory development candidate for AML's Academic / Open-source track.
This is a separate repository from [TraceMem-MM](https://github.com/cenzihan/trace-mem-mm).
It retrieves earlier engineering evidence; it does not solve the platform's tasks
or execute retrieved code. No official Coding score is claimed.

The [v0.2.3-rc1 long-trajectory candidate](docs/long-trajectory-candidate.md)
expands source admission and checks whole-Add model allowance before dispatch.
It is an offline candidate; the deployed v0.2.2 profile is unchanged.

The official v0.2 profile uses
[DSH-inspired source/context separation](docs/deepseek-harness-adaptation.md)
and bounded original-source windows. The v0.2.1 HTTPS preflight passed with
5 actual GPT calls and6 embedding calls on real public engineering history.
This is an engineering check, not an official benchmark score.

The existing Academic key supports Coding and Multimodal; another access key
is not required. The v0.2.2 [shared endpoint gateway](docs/shared-endpoint.md)
has been withdrawn from the registered route: the official contract permits
plain-string Multimodal requests, so payload types cannot identify a track.
Use an explicitly selected fixed backend for sequential evaluations. The two
repositories, models and stores remain independent. The100 offline checks do
not establish compatibility with every official request format.

## Model rules

Checked against the [official guide](https://agentmemoryleaderboard.ai/api-guide)
on 2026-10-27. These rules apply to Coding as well as the other Academic tracks.

| Component | Official requirement | This candidate |
|---|---|---|
| Embeddings | `text-embedding-v4` | Same model,256 dimensions |
| All LLM-related components | `gpt-4o-mini` | Source-grounded Add summaries only |
| Reranker | No AML model restriction | Disabled in this version |
| Final answers and scoring | Fixed by the platform | Not implemented by this service |

Our optional Qwen interface additionally requires the original pinned
`Qwen/Qwen3-VL-Reranker-2B` revision/weights; that is a project constraint rather
than an AML requirement. It has no role in the first Coding preflight.

## Method

Add durably stores original text and indexes contiguous UTF-8 spans. The index
combines an engineering summary, code-aware tokens, file/function anchors and
dense vectors. Search fuses BM25, exact-anchor and dense rankings. It returns
only original source substrings with stable IDs, preserving user isolation.
Idempotent Add, conflicting request IDs, uncertain-call no-replay, bounded costs
and restart persistence are enforced.

The current official suite is CAMBench Coding,150 tasks under relevant/noisy
conditions,300 attempts. Its data/verifiers are not publicly released.
SWEContextBench is a reference dataset, not the current scored AML suite.
Our four-case Git-history check is an engineering diagnostic using constructed
queries, not an unseen benchmark or task-solving score.

## Validation and deployment

Run `python scripts/run_checks.py` with Python3.11 and Pillow installed.
The standalone repository has41 Coding/transport checks. The development change
also passed639 regression tests in the original development checkout.
Offline tests use synthetic inputs and fake providers; they are not live results.
The [v0.1 live engineering preflight](docs/v0.1-validation.md) also passed8 Add,
8 Search and a post-restart Search using14 real GPT and17 embedding requests.
It is a four-case Git-history diagnostic, not an official benchmark score.

The pinned Dockerfile and `compose.coding.yaml` provide an independent development
container on loopback port8768. Run with the original server ledger directory,
separate Bearer token and explicit expiry configured as documented in
[the candidate notes](docs/coding-candidate.md). Configuration is deliberately
closed by default: a clean checkout cannot enable paid calls or create a budget.
The development profile has a durable32-provider-call lifetime cap, not capacity
for official Smoke/Full. It must not be reset to obtain another allowance.

`agent_memory.coding_app:create_app()` is the explicit Coding entry point.
The Dockerfile and Compose both select Coding explicitly; use
`docker compose -f compose.coding.yaml up -d` with the required variables.
The submitted multimodal API, image and model weights are unaffected.

## Source disclosure

Zihan Cen's original TraceMem-MM implementation at commit
`18aff5a1da91a7ab8817e603c1e577824dd98cbf` supplies the shared protocol, persistence,
accounting and provider support modules. Coding retrieval, prompt, bounded service,
tests and configuration were developed separately in commits
`c6aea61ec8101122472051f77171450479626528` and
`3b91c6763dabd77a5f0080e2f6ef61ea06d844a1` of the private development checkout.
The independent repository starts with a clean source snapshot and includes no
benchmark inputs, questions, receipts, contact details, credentials or model weights.
See [NOTICE.md](NOTICE.md) for rights; public source availability does not itself
grant an open-source license. Official acceptance and license review remain pending.
