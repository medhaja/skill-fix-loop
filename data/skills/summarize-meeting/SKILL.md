---
name: summarize-meeting
description: Summarize a recorded meeting from its transcript and calendar entry.
expected_output:
  - "## Summary"
  - "## Action items"
---

# Summarize meeting

## When to use
Use this when the user asks for notes from a meeting that has a transcript.

## Steps
1. Call `calendar.fetch_events` to find the meeting and its attendees.
2. Call `transcripts.get` with the meeting id to load the transcript.
3. Write the summary.

## Output
- A `## Summary` section with 3 to 6 bullets.
