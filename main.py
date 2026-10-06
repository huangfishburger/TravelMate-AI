import json

from agent import run_agent
from memory import new_memory
from utils.token_usage import token_totals
from utils.errors import error_details


if __name__ == "__main__":
    history = []
    memory = new_memory()
    print("Travel assistant: enter a request, /image to attach an image, /reset, or /exit.")
    while True:
        try:
            prompt = input("You: ").strip()
            if prompt.lower() in {"/exit", "exit", "quit"}:
                break
            if prompt.lower() == "/reset":
                history.clear()
                memory = new_memory()
                print("Conversation cleared.")
                continue
            if prompt.lower() == "/memory":
                print(json.dumps(memory, ensure_ascii=False, indent=2))
                continue
            if not prompt:
                continue
            images = None
            if prompt.lower() == "/image":
                image_path = input("Image path or HTTPS URL: ").strip().strip('"')
                prompt = input("Question about the image: ").strip()
                images = [image_path]
            trace = []
            try:
                answer = run_agent(prompt, history=history, images=images,
                                   memory=memory, trace=trace)
                print("Agent:", answer)
            finally:
                usage = token_totals(trace)
                if usage["calls"]:
                    print("Tokens:", json.dumps(usage, ensure_ascii=False))
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        except Exception as exc:
            print(f"[Agent Error] {json.dumps(error_details(exc), ensure_ascii=False)}")
