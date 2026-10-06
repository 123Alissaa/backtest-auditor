"""Home: the landing page. Everything here comes from saved audits; no paid calls."""
import streamlit as st

import ui

# Old deep links (/?strategy=leaky) still work: forward them to the right page.
legacy = st.query_params.get("strategy")
if legacy in ("Your own strategy", "custom"):
    st.switch_page("audit.py")
elif legacy in ui.SAMPLES:
    st.switch_page("examples.py", query_params={"strategy": legacy})

st.markdown('<div class="ba-land"><h1>Is your backtest lying?</h1><div class="sub">Catch lookahead bias, data '
            'leakage and overfitting before they cost you. Paste a trading strategy: we run it in an isolated '
            'Nebius sandbox, attack it four ways, and NVIDIA Nemotron explains what\'s wrong and fixes it. '
            'Every verdict comes from the tests, never from the AI.</div></div>', unsafe_allow_html=True)
b1, b2, _ = st.columns([1.25, 1, 2.2])
if b1.button("See a 50%/yr strategy get caught →", type="primary", key="cta_examples", width="stretch"):
    st.switch_page("examples.py", query_params={"strategy": "lookahead"})
if b2.button("✎ Audit your own code", key="cta_audit", width="stretch"):
    st.switch_page("audit.py")

# The money shot: the lookahead sample, reported vs. the same trades one day later.
demo = ui.load_sample("lookahead")
if demo:
    st.write("")
    m, s = demo["evidence"]["reported_metrics"], demo["curves"]
    shift = next(t for t in demo["evidence"]["tests"] if t["test"] == "signal_shift")["metrics"]
    t1, t2, t3 = st.columns(3)
    t1.markdown(f'<div class="ba-tile"><div class="lbl">What the backtest reports</div>'
                f'<div class="val">${s["original"][-1]:,.2f}</div>'
                f'<div class="sub2">from $1 · {m["cagr"]:.1%} a year · Sharpe {m["sharpe"]:.2f}</div></div>',
                unsafe_allow_html=True)
    t2.markdown(f'<div class="ba-tile"><div class="lbl">Same trades, one day later</div>'
                f'<div class="val">${s["shifted"][-1]:,.2f}</div>'
                f'<div class="sub2">Sharpe {shift["sharpe_shifted"]:.2f}: the edge was a peek at the future</div></div>',
                unsafe_allow_html=True)
    t3.markdown('<div class="ba-tile"><div class="lbl">Found in</div><div class="val">1 line</div>'
                '<div class="sub2">signal built from today\'s close, never shifted</div></div>',
                unsafe_allow_html=True)
    ui.equity_chart(s["dates"], ("What the backtest reports", "Same trades, one day later"),
                    s["original"], s["shifted"])

st.markdown("#### How it works")
st.markdown(ui.STEPS_HTML, unsafe_allow_html=True)

st.markdown("#### The gallery: 8 strategies, audited")
st.caption("Classic bugs, real-world mistakes from tutorials, and two honest strategies that should pass. "
           "Numbers come from the sandbox, not the AI.")
cards = [c for c in (ui.gallery_card(n) for n in ui.GALLERY) if c]
for row in range(0, len(cards), 4):
    cols = st.columns(4)
    for col, card in zip(cols, cards[row:row + 4]):
        with col:
            st.markdown(ui.gallery_card_html(card), unsafe_allow_html=True)
            st.page_link("examples.py", label="Open the audit →", query_params={"strategy": card["name"]})

st.markdown("#### Why you can trust the verdict")
w1, w2, w3 = st.columns(3)
w1.markdown('<div class="ba-why"><b>The tests decide, not the AI</b><span>Four deterministic tests produce every '
            'verdict and number. Nemotron explains them; if it disagrees, it\'s overruled and its numbers are '
            'checked against the evidence.</span></div>', unsafe_allow_html=True)
w2.markdown('<div class="ba-why"><b>Your code never runs here</b><span>Strategies run only inside an isolated '
            'Nebius Token Factory Sandbox with no secrets in it. This server just parses the code.</span></div>',
            unsafe_allow_html=True)
w3.markdown('<div class="ba-why"><b>Every fix is proven</b><span>Nemotron writes candidate fixes; each one is '
            're-tested in its own sandbox branch. A fix only counts if the tests pass and it still trades.'
            '</span></div>', unsafe_allow_html=True)

st.markdown(ui.FOOTER, unsafe_allow_html=True)
