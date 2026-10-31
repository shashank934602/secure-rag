"""The answering flow as a LangGraph state machine (spec 03 D6, ISS-032).

    retrieve ──(nothing relevant)──────────────────────────▶ no_answer ─▶ END
       │
       ▼
    generate ─▶ check_citations ──(valid)───────────────────────────────▶ END
       ▲               │
       └──(invalid, first time: retry with a correction note)
                       └──(invalid again, or the model said "I don't know")─▶ no_answer ─▶ END

Each node reads the shared state and returns only the keys it changes. Later phases add their
steps (input guard, context guard, grounding judge, audit) as nodes and edges here.
"""

from typing import TYPE_CHECKING, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.domain import Citation, ScoredChunk

if TYPE_CHECKING:
    from app.answering.answer import Answerer

MAX_ATTEMPTS = 2  # the first answer plus one retry


class AnswerState(TypedDict, total=False):
    question: str
    retrieved: list[ScoredChunk]
    replies: list[str]  # every model reply, in order
    citations: list[Citation]
    status: Literal["answered", "no_answer"]  # unset while the flow is still deciding


def build_graph(answerer: "Answerer") -> CompiledStateGraph:
    graph = StateGraph(AnswerState)
    graph.add_node("retrieve", answerer.retrieve_step)
    graph.add_node("generate", answerer.generate_step)
    graph.add_node("check_citations", answerer.check_step)
    graph.add_node("no_answer", lambda state: {"status": "no_answer", "citations": []})

    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges(
        "retrieve", answerer.after_retrieve, {"generate": "generate", "no_answer": "no_answer"}
    )
    graph.add_edge("generate", "check_citations")
    graph.add_conditional_edges(
        "check_citations",
        _after_check,
        {"answered": END, "retry": "generate", "no_answer": "no_answer"},
    )
    graph.add_edge("no_answer", END)
    return graph.compile()


def _after_check(state: AnswerState) -> Literal["answered", "retry", "no_answer"]:
    if state.get("status") == "answered":
        return "answered"
    if state.get("status") is None and len(state["replies"]) < MAX_ATTEMPTS:
        return "retry"
    return "no_answer"
