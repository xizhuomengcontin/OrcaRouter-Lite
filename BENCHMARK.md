# OrcaRouter benchmark

_10 prompts × 4 models · last run 2026-09-12 05:03 UTC_

**TL;DR**: routing the cheapest capable model saved **~0%** vs. the most expensive (`llama-3.3-70b-versatile` → `gpt-4o-mini`)

| Model | Requests | Total cost | Avg latency | Success |
|---|---:|---:|---:|---:|
| `gpt-4o-mini` | 10 | $0.00 | 0 ms | 0% |
| `claude-3-5-haiku-latest` | 10 | $0.00 | 0 ms | 0% |
| `gemini-2.5-flash` | 10 | $0.00 | 0 ms | 0% |
| `llama-3.3-70b-versatile` | 10 | $0.00 | 0 ms | 0% |

_Run nightly via GitHub Actions; see `.github/workflows/benchmark.yml`._
_Reproduce: `python bench/run.py --prompts bench/prompts.jsonl`_
