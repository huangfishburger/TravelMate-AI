# Image requests

Start the existing terminal interface:

```powershell
.\venv\Scripts\python.exe main.py
```

Enter `/image`, then a local image path or HTTPS image URL, then a question.
Examples: identify a landmark, find visually similar places in a specified region,
or search for flights matching a screenshot. This is a terminal attachment flow;
there is no web upload interface in this project yet.

Python callers can supply multiple references:

```python
history = []
answer = run_agent(
    "Find similar coastal viewpoints in Seattle.",
    images=["reference.png"],
    history=history,
)
```

Local PNG/JPEG/WEBP/GIF images are encoded as image data URLs (20 MB maximum per
local file). Use nonanimated images. HTTPS URLs are passed to OpenAI for retrieval;
they must be accessible. Signature checks detect unsupported files but do not
guarantee that an image can be decoded. The API can reject corrupt or unsupported
images. No local OCR dependency is required.

Intent, planner, and itinerary evaluator receive actual image content. A follow-up
uses the same history to refer to previous images. Images are kept in history, so
later calls can include their input cost again; `/reset` clears them. Reference
images may be ambiguous; location guesses are not verified reverse-image matches.
Screenshot prices and flight details are historical visual evidence, not live
availability. Required unreadable details should be clarified before searching.
Text embedded in images is data, not instructions.

Current 50-case batch tests are text-only. Image transport is covered by mocked
unit tests; real photo recognition and screenshot extraction still need live
image fixtures and independent test-reviewer image evidence.

API format follows the official OpenAI image-input documentation:
https://developers.openai.com/api/docs/guides/images-vision
