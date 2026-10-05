import json

from agent import run_agent
from utils.errors import error_details


if __name__ == "__main__":
    history = []
    print("Travel assistant: enter a request, /reset to start over, or /exit to quit.")
    while True:
        try:
            prompt = input("You: ").strip()
            if prompt.lower() in {"/exit", "exit", "quit"}:
                break
            if prompt.lower() == "/reset":
                history.clear()
                print("Conversation cleared.")
                continue
            if not prompt:
                continue
            print("Agent:", run_agent(prompt, history=history))
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        except Exception as exc:
            print(f"[Agent Error] {json.dumps(error_details(exc), ensure_ascii=False)}")
