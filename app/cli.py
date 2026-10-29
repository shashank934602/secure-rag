"""Ask a question about the sample corpus from the command line.

    uv run python -m app.cli "How many days of annual leave do I get?" [--debug]

Exit code 0 for an answer or a No-Answer; 1 if something went wrong.
"""

import argparse
import sys
from collections.abc import Callable

from app.answering.answer import Answerer, build_answerer, build_db_answerer
from app.config import Settings, get_settings
from app.domain import AnswerResult


def main(
    argv: list[str] | None = None,
    build: Callable[[Settings], Answerer] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.split("\n")[0])
    parser.add_argument("question", help="the question to ask")
    parser.add_argument(
        "--debug", action="store_true", help="also show retrieved chunks and their scores"
    )
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
        build = build or _default_build(settings)
        result = build(settings).answer(args.question)
    except Exception as error:
        if args.debug:
            raise
        print(f"Error: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    print(_format(result, debug=args.debug))
    return 0


def _default_build(settings: Settings) -> Callable[[Settings], Answerer]:
    """Search Postgres when a database is configured (run `python -m app.ingest` first);
    otherwise fall back to the in-memory index over the corpus folder."""
    return build_db_answerer if settings.database_url else build_answerer


def _format(result: AnswerResult, *, debug: bool) -> str:
    lines = [result.answer]

    if result.citations:
        filenames = {(r.chunk.doc_id, r.chunk.page): r.chunk.source for r in result.retrieved}
        lines += ["", "Sources:"]
        lines += [f"  - {c} ({filenames[(c.doc_id, c.page)]})" for c in result.citations]

    if debug:
        lines += ["", f"status: {result.status} | prompt: {result.prompt_version}"]
        lines += [f"Retrieved (top {len(result.retrieved)}):"]
        for r in result.retrieved:
            text = " ".join(r.chunk.text.split())
            preview = text if len(text) <= 70 else text[:69] + "…"
            lines.append(f"  {r.score:.3f}  {r.chunk.id:<32} {preview}")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
