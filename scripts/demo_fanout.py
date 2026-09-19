"""Minimal demo script for testing dynamic query fan-out."""

import asyncio
import sys

from ai_search_journey.fanout import generate_fanout
from ai_search_journey.models import SearchIntent
from ai_search_journey.planner import extract_intent

DEFAULT_QUESTION = (
    "Find a coffee shop near Geekdom San Antonio for 6 people "
    "to work together, preferably quiet, and open after 8 PM."
)


def format_intent(intent: SearchIntent) -> str:
    """Format SearchIntent into a human-readable developer-demo string."""
    lines = ["PARSED INTENT", ""]

    lines.append("Search Intent:")
    if intent.intent_types:
        for it in intent.intent_types:
            label = it.value.replace("_", " ").title()
            lines.append(f"  - {label}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Category:")
    lines.append(f"  {intent.category}" if intent.category else "  None")
    lines.append("")

    lines.append("Location:")
    lines.append(f"  {intent.reference_location}" if intent.reference_location else "  None")
    lines.append("")

    lines.append("Group Size:")
    lines.append(f"  {intent.group_size}" if intent.group_size is not None else "  None")
    lines.append("")

    lines.append("Open After:")
    lines.append(f"  {intent.open_after}" if intent.open_after else "  None")
    lines.append("")

    lines.append("Open Before:")
    lines.append(f"  {intent.open_before}" if intent.open_before else "  None")
    lines.append("")

    lines.append("Hard Constraints:")
    if intent.hard_constraints:
        for c in intent.hard_constraints:
            lines.append(f"  - {c}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Preferences:")
    if intent.preferences:
        for p in intent.preferences:
            lines.append(f"  - {p}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Requested Results:")
    lines.append(f"  {intent.requested_result_count}")

    return "\n".join(lines)


async def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    print("\n--- QUERY FAN-OUT DEMO ---\n")
    print(f"QUESTION:\n{question}\n")

    try:
        intent = await extract_intent(question)
        print(format_intent(intent))
        print()

        fanout = await generate_fanout(intent)
        print("QUERY FAN-OUT:")
        for idx, q in enumerate(fanout, start=1):
            print(f"\n{idx}. [{q.tool.value.upper()}]")
            print(f"   Goal:   {q.goal}")
            print(f"   Query:  {q.query}")
            if q.reason:
                print(f"   Reason: {q.reason}")
        print()

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
