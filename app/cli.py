"""Text chat with the agent: python -m app.cli"""
import json

from .agent import Agent
from .llm import GroqClient


def main() -> None:
    agent = Agent(GroqClient())
    print("Renter intake agent (text mode). Commands: :state  :quit\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == ":quit":
            break
        if text == ":state":
            print(json.dumps(agent.state.snapshot(), indent=2, ensure_ascii=False))
            continue
        r = agent.turn(text)
        print(f"agent> {r.display_text}")
        for c in r.changes:
            print(f"  [memory] {c['field']}: {c['old']} -> {c['new']}")
        t = r.timings.to_dict()
        print(f"  [latency] llm {t['llm_ms']}ms ({t['llm_calls']} calls), tools {t['tool_ms']}ms, total {t['total_ms']}ms\n")


if __name__ == "__main__":
    main()
