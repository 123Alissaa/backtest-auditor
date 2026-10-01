"""First call to Nemotron on Token Factory. Run once credits are active:

    python -m scripts.hello_nemotron

Prints the raw response so you can see where the answer and reasoning live.
"""
from agent.config import settings
from agent.llm import chat


def main():
    model = settings.model_fast or settings.model_reasoning
    reply = chat([{"role": "user", "content": "Explain lookahead bias in trading backtests in one sentence."}], model=model)
    print("MODEL:", model)
    print("\nCONTENT:\n", reply.content or "(empty)")
    print("\nREASONING:\n", (reply.reasoning or "(none found)")[:800])
    print("\nRAW MESSAGE (check field names here):\n", reply.raw.choices[0].message)


if __name__ == "__main__":
    main()
