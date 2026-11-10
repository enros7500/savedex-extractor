# V2 roadmap

V1 provides a local extraction CLI with structured JSON, readable summaries, medium CPU transcription, local Qwen extraction, and OCR.

Potential V2 work:

- Improve completeness checks and source selection, particularly for descriptions that contain several relevant entities.
- Expand extraction evaluation across languages, media types, and noisy or ambiguous content.
- Evaluate LangGraph for explicit state, bounded retries, fallback routing, and resumable execution inside the CLI.
- Evaluate an optional AG-UI adapter in the consuming backend for progress, provisional findings, and final results.
- Evaluate local visual understanding for publications that require more than OCR.

These are proposals, not V1 capabilities. Public commands and JSON compatibility should be preserved where possible; genuine contract changes require explicit versioning. No V2 delivery date is committed.

Web investigation, official-link discovery, geolocation, and Maps lookup remain responsibilities of the consuming application.
