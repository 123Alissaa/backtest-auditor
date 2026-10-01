# Backtest Auditor (working name)

**An AI agent that catches trading backtests that lie.**

Backtests (simulations of a trading strategy on past data) routinely look amazing because of subtle bugs: using information from the future, leaking future data into features, or trying hundreds of configurations and keeping the lucky one. Backtest Auditor runs a strategy in an isolated sandbox, attacks it with deterministic tests, and uses NVIDIA Nemotron to explain what it found, with evidence and an honest equity curve.

> ⚠️ Educational tool, not financial advice. It evaluates code; it does not recommend trades.

Built for the Nebius x NVIDIA Global AI Hackathon on Devpost — Coding & Agentic Engineering track.

## Status
🚧 In development. See [PROGRESS.md](PROGRESS.md).

## What it checks
| Test | Catches | How |
|---|---|---|
| Signal shift | Lookahead bias | Delay every position one bar; honest strategies barely change, cheating ones collapse |
| Point-in-time | Lookahead + data leakage | Hide the future and perturb today's price; honest positions must not change |
| Walk-forward | Overfitting | Pick the best config on past data, test on unseen data |
| Deflated Sharpe ratio | Overfitting | Probability the edge is real after accounting for how many configs were tried (Bailey & López de Prado, 2014) |

## Quick start (local, sample strategies only)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in your Token Factory key + model IDs
pytest -q
python -m scripts.run_local_audit --strategy lookahead
```

## How we use Nebius Token Factory and NVIDIA Nemotron
_To be written as we build: model routing (Nano vs Super/Ultra), Sandboxes usage, and anything else from Nebius._

## Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License
MIT — see [LICENSE](LICENSE).
