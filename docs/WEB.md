# Local web interface

Start the existing Python virtual environment, then run:

```powershell
.\venv\Scripts\python.exe web_app.py
```

Open `http://127.0.0.1:8000` in your browser. The interface shows the current trip state, chat and itinerary, a cost table when the agent returns structured costs, and an Agent Activity panel based on actual tool and replanning trace events. It does not display the model's private reasoning or raw tool payloads.
The planner follows the user's requested language; Chinese requests produce Traditional Chinese itinerary text and localized itinerary-card headings. Existing responses are not translated retroactively.
While a request is running, the chat status and Agent Activity panel update with the current stage, such as flight search, hotel search, budget check, quality review, or replanning. Completed actions remain visible after the answer arrives.
For new web requests, expand **Flight search** in Agent Activity to inspect the route, dates, filters, returned outbound options, and paired return options with times and prices. This compact search record stays in the browser session while the server runs; it is not a complete provider log or a record of private model reasoning. Earlier web replies cannot be reconstructed from it.
The trip card shows a known traveler count, and the Flight search details show how many adults were included in the price query. Existing replies retain their original search scope; they are not repriced retroactively.
For a new full itinerary, a **Flights & stays** summary appears above the cost breakdown when the final plan explicitly identifies the selected flights and hotels. Hotel date ranges are shown night by night; missing times and dates are left unspecified.
Connecting flights show each extracted segment. If the displayed outbound and return endpoints do not form a continuous round trip, the summary flags the route for review rather than silently presenting it as complete.
The cost table combines matching categories from the budget check and the itinerary's written cost notes. It compares the itemized sum with the checked total; if amounts still do not reconcile, it shows the difference and retains the original notes for review.

Use **Edit & export** on an itinerary response to open a Markdown editor with a live preview. The draft is saved in the current browser tab, and **Download .md** exports your edits as a Markdown file. Editing this copy does not update the agent's trip state, budget check, or chat response. Download the file before closing the tab if you want to keep it.

The browser session keeps its own conversation and trip memory while the server is running. **New trip** clears both. API keys and search credentials use the same environment configuration as `main.py`. The server listens only on localhost.

Use the **＋** button beside the message box to attach up to three PNG, JPEG, WEBP, or GIF images (8 MB each). You can send a picture with or without text, for example to identify a location or ask for a similar attraction. The browser keeps image names in the visible conversation; image bytes are sent to the multimodal agent and retained only in its recent conversation context while that session runs.
