# Feedback notes (Nebius Token Factory, Sandboxes, NVIDIA tools)

Running log for the required feedback section (also eligible for Most Valuable Feedback prizes).
Format: date — product — what happened — what would have helped.

- 2026-10-01 — Token Factory / cookbook — `nebius/token-factory-cookbook` `models/nemotron/nemotron3-nano-30b.md` uses `nvidia/nvidia-nemotron-3-nano-30b-a3b`, which returns "model does not exist"; the live `/v1/models` ID is `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. Model IDs are case-sensitive and casing is inconsistent across models (`nemotron-3-super-120b-a12b` vs `Nemotron-3-Ultra-550b-a55b`) — case-insensitive IDs, or a "did you mean" in the error, would have helped.
- 2026-10-01 — Token Factory — reasoning output field differs by model: Nano returns only `reasoning`, Super returns both `reasoning` and `reasoning_content`; `content` starts with a stray `\n`. Not documented per model — a note in the model card would have helped.
- 2026-10-01 — Sandboxes docs — Contree SDK Getting Started uses placeholder `base_url="https://your-instance.of.contree"`; the real URL (`https://api.tokenfactory.nebius.com/sandboxes`) is only in the CLI configuration page.
