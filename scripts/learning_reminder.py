"""Print the learning-log rule and the latest entry, as context for a coding assistant.

Run automatically at session start and after context compaction (see .claude/settings.json),
so the rule survives even when the conversation history is lost.

    python3 scripts/learning_reminder.py
"""

import json
import re
from datetime import date
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "lessons" / "learning-log.md"

RULE = """LEARNING-BY-DOING PROJECT — standing rule (from the owner, 2026-10-13):
- We are not just building. Teach every step: explain what and why BEFORE doing it,
  and show what changed after.
- The learner writes the core code (retrieval, guards, audit chain, eval metrics)
  against tests you provide.
- Keep lessons/learning-log.md: every working session gets a dated entry
  (Where we are / What we learned / How we learned it / What I can now explain /
  Still unclear / Next session starts with), updated after each step, newest at the
  bottom, committed and pushed with the work.
- Read AGENTS.md and plan.md section 0 before working."""


def latest_entry(text: str) -> str:
    entries = re.split(r"(?m)^(?=## \d{4}-\d{2}-\d{2})", text)
    dated = [e.strip() for e in entries if re.match(r"## \d{4}-\d{2}-\d{2}", e)]
    return dated[-1] if dated else "(no entries yet)"


def main() -> None:
    today = date.today().isoformat()
    if LOG.exists():
        text = LOG.read_text(encoding="utf-8")
        entry = latest_entry(text)
        has_today = f"## {today}" in text
    else:
        entry = "(lessons/learning-log.md is missing — restore it from git history)"
        has_today = False

    todo = (
        f"Today ({today}) already has an entry: update it as steps complete."
        if has_today
        else f"Today ({today}) has NO entry yet: add one before the session ends."
    )
    context = f"{RULE}\n\n{todo}\n\nLatest learning-log entry:\n\n{entry}"
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                },
                "systemMessage": f"Learning log loaded. {todo}",
            }
        )
    )


if __name__ == "__main__":
    main()
