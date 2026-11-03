"""Measure prompt tokens per LLM call for two fixed scenarios, using Groq's own usage numbers.

    python -m scripts.probe_tokens

fresh : first renter message, empty profile.
mid   : renter's 10th turn; full profile, a search result in state, 9 earlier turns of chat history.
Sends max_tokens=1 so the probe itself costs only the prompt.
"""
import httpx

from app.agent import Agent
from app.config import settings
from app.listings import SearchFilters, search_listings
from app.llm import LLMResponse

FILLED = {"budget_max": 30000, "areas": ["Sector 56", "Sector 57"], "bhk": [2], "move_in_date": "2026-12-01",
          "commute_destination": "Cyber City"}
CHATTER = [
    ("Hi, I need a flat in Gurgaon for me and my wife.", "Happy to help. What monthly budget do you have in mind?"),
    ("Around thirty thousand a month.", "Got it, 30,000. Which sectors or areas do you prefer?"),
    ("Sector 56 or Sector 57, near the Golf Course Extension Road.", "Noted. How many bedrooms do you need?"),
    ("Two BHK should be fine for us.", "Great. When do you want to move in?"),
    ("First of December. My office is at Cyber City.", "Here is your profile: budget up to 30,000, 2 BHK in Sector 56 or 57, moving 1 December, commute to Cyber City. Shall I search?"),
    ("Yes, that's right.", "Here are the best matches for you."),
    ("Which one is closest to my office?", "The first one is the closest by distance to Cyber City."),
    ("Does the second one allow pets?", "Yes, the second listing allows pets."),
    ("Okay and what about parking in the first?", "The first listing has parking available."),
]


class _Capture:
    def __init__(self):
        self.messages = self.tools = None

    def chat(self, messages, tools):
        self.messages, self.tools = messages, tools
        raise StopIteration  # stop after capturing the first request


def capture(agent_setup, text):
    cap = _Capture()
    agent = Agent(cap)
    agent_setup(agent)
    try:
        agent.turn(text)
    except StopIteration:
        pass
    return cap


def mid(agent):
    agent.state.update_profile(FILLED, dict.fromkeys(FILLED, "new"))
    agent.state.turn = 9
    agent.state.read_back()
    agent.state.turn = 10
    agent.state.confirm("yes", "yes")
    agent.state.last_search = search_listings(SearchFilters.from_profile(agent.state.profile))
    for user, assistant in CHATTER:
        agent.history += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]


def prompt_tokens(cap) -> int:
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                   headers={"Authorization": f"Bearer {settings.groq_api_key}"}, timeout=60,
                   json={"model": settings.groq_model, "messages": cap.messages, "tools": cap.tools,
                         "tool_choice": "required", "max_tokens": 1, "reasoning_effort": "low"})
    r.raise_for_status()
    return r.json()["usage"]["prompt_tokens"]


if __name__ == "__main__":
    for name, setup, text in [("fresh", lambda a: None, "I need a 2 BHK in Sector 56"), ("mid", mid, "What about the third one?")]:
        print(f"{name}: {prompt_tokens(capture(setup, text))} prompt tokens")
