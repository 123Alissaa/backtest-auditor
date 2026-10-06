# Demo video script (target 2:50, hard limit 3:00)

Rules: public YouTube, under 3 minutes, show the project working, and the audio must explain how
**Nebius Token Factory** and **NVIDIA Nemotron** are used. About 330 spoken words (~2:20 of speech), leaving room for pauses.

**Before recording**
- Open https://backtest-auditor.streamlit.app a few minutes early so it's awake, then reboot it if you pushed code.
- Use a fresh browser session (live runs are capped at 3 per visitor).
- Record at 1280×800 or 1440×900, light mode, browser zoom 100%.
- Live numbers match the saved audit (Sharpe 3.43 → 0.14, 38 of 40 dates) because the data is fixed; the fix
  wording can vary run to run, but the result is checked by the same tests.
- Pre-record the live audit and the Fix it run, then speed up the waiting parts 2–4× in editing. Label the
  sped-up parts "sped up" on screen to stay honest.

| Time | Screen | Narration |
|---|---|---|
| 0:00–0:12 | Landing page, cursor on the $59.83 tile | "This trading strategy turns one dollar into fifty-nine. Fifty percent a year. It's lying, and you can't see why by reading the code." |
| 0:12–0:30 | Hover the chart: blue line vs. flat orange line | "Here's the same strategy with every trade delayed by one day. One dollar ten. The whole edge was a peek at the future. Bugs like this, lookahead, data leakage, overfitting, are how backtests lie, and they're everywhere." |
| 0:30–0:45 | Scroll to "How it works" | "Backtest Auditor catches them. It scans the code, attacks it with four deterministic tests inside a Nebius Token Factory Sandbox, and NVIDIA Nemotron explains, and fixes, what it finds." |
| 0:45–1:05 | Click **✎ Audit your own code** → Start from **Lookahead** → **Run audit**; progress steps tick (sped up) | "Let's audit one live. The code never runs on our server: it runs in an isolated Token Factory Sandbox. While the tests run, Nemotron Super reads the code and predicts what they'll find, and Nemotron Nano explains anything our rules flagged." |
| 1:05–1:35 | Report: red banner, the four test cards, then the highlighted line `signal = (c > sma)` | "Fail. Delaying the trades collapses the Sharpe from 3.4 to 0.1, and when we hide the future, the positions change on 38 of 40 dates. Nemotron points to the exact line: it compares today's close to its average and trades the same day. Every verdict and number here comes from the tests. If Nemotron disagrees, it's overruled, and its numbers are checked against the evidence." |
| 1:35–2:10 | Click **Fix it**: two attempts, "Fixed and proven", before/after table, diff | "Now the agent part. Nemotron Super writes two different minimal fixes. Token Factory Sandboxes let us snapshot the test setup once and branch it, so both fixes are tested in parallel. A fix only counts if the hide-the-future test passes, nothing fails, and it still trades. Fifty percent a year becomes an honest one percent, with a small, readable change." |
| 2:10–2:35 | Home → gallery → open **Weekly bfill** card, show the delay test WARN and hide-the-future FAIL | "The gallery has real-world mistakes from tutorials. This weekly strategy fools the delay test and no pattern rule catches it, but hiding the future does. The two honest strategies pass, so it doesn't cry wolf. Overfitting gets an honest explanation instead of a fake fix." |
| 2:35–2:50 | Home page top, then the GitHub README | "Backtest Auditor: Nemotron Super and Nano on Nebius Token Factory, with Token Factory Sandboxes for isolation and branching. Try it with your own strategy at backtest-auditor.streamlit.app. Educational tool, not financial advice." |

**Editing checklist:** captions on (auto-captions are fine), total under 3:00, upload as **Public** on YouTube, paste the link into Devpost.
