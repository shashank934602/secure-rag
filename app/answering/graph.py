"""The answering flow as a LangGraph state machine (spec 03 D6; guards: spec 05 D8).

    input_guard ──(attack)──────────────────────────────────▶ refused ─▶ END
       │
       ▼

    retrieve ─▶ context_guard ──(nothing relevant or left)────▶ no_answer ─▶ END
       │      (drop injected chunks, mask personal data)
       ▼
    generate ─▶ output_checks ─▶ check_citations ──(valid)─▶ grounding_judge ──(supported)─▶ END
       ▲     (strip links/images/HTML,   │                         │
       │      redact secrets, PII)       │                         │
       └──(invalid citations or unsupported claims, first time: retry with a note)
                                         └──(again, or the model said "I don't know")─▶ no_answer

Each node reads the shared state and returns only the keys it changes. Later phases add their
steps (input guard, context guard, grounding judge, audit) as nodes and edges here.
"""

from typing import TYPE_CHECKING, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.domain import AccessScope, Citation, GuardVerdict, ScoredChunk

if TYPE_CHECKING:
    from app.answering.answer import Answerer

MAX_ATTEMPTS = 2  # the first answer plus one retry


class AnswerState(TypedDict, total=False):
    question: str
    scope: AccessScope | None  # whose documents may be searched (None: the retriever default)
    retrieved: list[ScoredChunk]
    replies: list[str]  # every model reply, in order
    citations: list[Citation]
    outcome: Literal["valid", "invalid", "refusal"]  # of the latest citation check
    grounded: bool  # the latest grounding verdict
    retry_note: str  # why the last reply was rejected, shown to the model on its retry
    verdicts: list[GuardVerdict]  # every guard decision so far, in order
    status: Literal["answered", "no_answer", "refused"]  # unset while still deciding


def build_graph(answerer: "Answerer") -> CompiledStateGraph:
    graph = StateGraph(AnswerState)
    graph.add_node("input_guard", answerer.input_guard_step)
    graph.add_node("refused", lambda state: {"status": "refused", "citations": []})
    graph.add_node("retrieve", answerer.retrieve_step)
    graph.add_node("context_guard", answerer.context_guard_step)
    graph.add_node("generate", answerer.generate_step)
    graph.add_node("output_checks", answerer.output_step)
    graph.add_node("check_citations", answerer.check_step)
    graph.add_node("grounding_judge", answerer.grounding_step)
    graph.add_node("answered", lambda state: {"status": "answered"})
    graph.add_node("no_answer", lambda state: {"status": "no_answer", "citations": []})

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard", _after_input_guard, {"refused": "refused", "retrieve": "retrieve"}
    )
    graph.add_edge("refused", END)
    graph.add_edge("retrieve", "context_guard")
    graph.add_conditional_edges(
        "context_guard",
        answerer.after_context,
        {"generate": "generate", "no_answer": "no_answer"},
    )
    graph.add_edge("generate", "output_checks")
    graph.add_edge("output_checks", "check_citations")
    graph.add_conditional_edges(
        "check_citations",
        _after_check,
        {"judge": "grounding_judge", "retry": "generate", "no_answer": "no_answer"},
    )
    graph.add_conditional_edges(
        "grounding_judge",
        _after_grounding,
        {"answered": "answered", "retry": "generate", "no_answer": "no_answer"},
    )
    graph.add_edge("answered", END)
    graph.add_edge("no_answer", END)
    return graph.compile()


def _after_input_guard(state: AnswerState) -> Literal["refused", "retrieve"]:
    verdicts = state.get("verdicts") or []
    return "refused" if verdicts and verdicts[-1].decision == "BLOCK" else "retrieve"


def _retry_or_give_up(state: AnswerState) -> Literal["retry", "no_answer"]:
    # One retry in total, whether citations or grounding failed (the model said "I don't know"
    # itself → final, no retry).
    return "retry" if len(state["replies"]) < MAX_ATTEMPTS else "no_answer"


def _after_check(state: AnswerState) -> Literal["judge", "retry", "no_answer"]:
    if state["outcome"] == "valid":
        return "judge"
    if state["outcome"] == "refusal":
        return "no_answer"
    return _retry_or_give_up(state)


def _after_grounding(state: AnswerState) -> Literal["answered", "retry", "no_answer"]:
    return "answered" if state["grounded"] else _retry_or_give_up(state)
