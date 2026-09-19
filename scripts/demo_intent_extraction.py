"""Minimal demo script for testing Gemini structured intent extraction."""

import asyncio
import sys

from ai_search_journey.planner import extract_intent

DEFAULT_QUESTION = (
    "Find a coffee shop near Geekdom San Antonio for 6 people "
    "to work together, preferably quiet, and open after 8 PM."
)


async def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    print(f"\n--- Extracting Intent ---\nQuestion: {question}\n")
    try:
        intent = await extract_intent(question)
        print("Result (SearchIntent):")
        print(intent.model_dump_json(indent=2))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
