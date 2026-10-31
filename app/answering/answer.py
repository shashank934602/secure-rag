"""Answer a question from retrieved chunks, with validated citations, or return a No-Answer."""

from pathlib import Path
from string import Template

from langchain.chat_models import init_chat_model
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.answering.citations import all_citations_retrieved, parse_citations
from app.answering.graph import AnswerState, build_graph
from app.config import Settings
from app.db import make_pool
from app.domain import AnswerResult, Citation, ScoredChunk
from app.ingestion.chunking import chunk_pages
from app.ingestion.loaders import load_pages
from app.retrieval.embeddings import make_embeddings
from app.retrieval.pg_search import PgRetriever
from app.retrieval.rerank import CrossEncoderReranker, Reranker
from app.retrieval.retriever import Retriever
from app.retrieval.search import ChunkIndex

NO_ANSWER = "I don't know based on the documents I can access."
RETRY_NOTE = (
    "Your reply was rejected: every claim needs a citation copied from a document tag, such as "
    "[leave-policy:1], and only the documents above may be cited. Answer again following the "
    f"rules, or reply with exactly: {NO_ANSWER}"
)
PROMPT_VERSION = "answer_v1"
_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


class Answerer:
    def __init__(
        self,
        index: Retriever,
        chat_model: BaseChatModel,
        top_k: int,
        *,
        reranker: Reranker | None = None,
        candidates: int = 20,
        threshold: float = 0.0,
    ) -> None:
        self.index = index
        self.chat_model = chat_model
        self.top_k = top_k
        self.reranker = reranker
        self.candidates = candidates  # searched, then reranked down to top_k
        self.threshold = threshold  # best reranker score below this → No-Answer, no LLM call
        self.graph = build_graph(self)
        template = Template((_PROMPTS / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8"))
        self._system_prompt = template.substitute(no_answer=NO_ANSWER)

    def answer(self, question: str) -> AnswerResult:
        final = self.graph.invoke({"question": question})
        if final["status"] == "no_answer":
            return self._result("no_answer", NO_ANSWER, [], final["retrieved"])
        answer, citations = final["replies"][-1], final["citations"]
        return self._result("answered", answer, citations, final["retrieved"])

    def retrieve(self, question: str) -> list[ScoredChunk]:
        """The top_k chunks the LLM will see: searched directly, or reranked from candidates."""
        if self.reranker is None:
            return self.index.search(question, k=self.top_k)
        candidates = self.index.search(question, k=self.candidates)
        return self.reranker.rerank(question, candidates, k=self.top_k)

    # --- graph steps (app/answering/graph.py wires them together) -------------------------

    def retrieve_step(self, state: AnswerState) -> AnswerState:
        return {"retrieved": self.retrieve(state["question"]), "replies": []}

    def after_retrieve(self, state: AnswerState) -> str:
        retrieved = state["retrieved"]
        if not retrieved or (self.reranker and retrieved[0].score < self.threshold):
            return "no_answer"  # nothing relevant: don't spend an LLM call
        return "generate"

    def generate_step(self, state: AnswerState) -> AnswerState:
        messages = [
            SystemMessage(self._system_prompt),
            HumanMessage(_user_message(state["question"], state["retrieved"])),
        ]
        if state["replies"]:  # a retry: show the rejected reply and say why
            messages += [AIMessage(state["replies"][-1]), HumanMessage(RETRY_NOTE)]
        reply = self.chat_model.invoke(messages)
        return {"replies": [*state["replies"], reply.text.strip()]}

    def check_step(self, state: AnswerState) -> AnswerState:
        text = state["replies"][-1]
        if NO_ANSWER in text:
            return {"status": "no_answer"}  # the model's own refusal is final
        citations = parse_citations(text)
        if citations and all_citations_retrieved(citations, state["retrieved"]):
            return {"status": "answered", "citations": citations}
        return {}  # invalid: the graph retries once, then gives a No-Answer

    def _result(
        self, status: str, answer: str, citations: list[Citation], retrieved: list[ScoredChunk]
    ) -> AnswerResult:
        return AnswerResult(
            status=status,
            answer=answer,
            citations=citations,
            retrieved=retrieved,
            prompt_version=PROMPT_VERSION,
        )


def _user_message(question: str, retrieved: list[ScoredChunk]) -> str:
    documents = "\n\n".join(
        f'<document id="{r.chunk.doc_id}:{r.chunk.page}">\n{r.chunk.text}\n</document>'
        for r in retrieved
    )
    return f"{documents}\n\nQuestion: {question}"


def build_answerer(
    settings: Settings,
    *,
    embeddings: Embeddings | None = None,
    chat_model: BaseChatModel | None = None,
    retriever: Retriever | None = None,
    reranker: Reranker | None = None,
) -> Answerer:
    """Create the answerer: the given retriever, or an in-memory index over the corpus
    (loaded, chunked, and embedded on every start), plus the chat model named in settings."""
    if retriever is None:
        pages = load_pages(settings.corpus_dir)
        chunks = chunk_pages(
            pages,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            encoding_name=settings.tokenizer_encoding,
        )
        retriever = ChunkIndex(chunks, embeddings or make_embeddings(settings.embedding_model))
    model = chat_model or init_chat_model(
        settings.chat_model, temperature=settings.chat_temperature
    )
    if reranker is None and settings.rerank:
        reranker = CrossEncoderReranker(settings.reranker_model)
    return Answerer(
        index=retriever,
        chat_model=model,
        top_k=settings.top_k,
        reranker=reranker,
        candidates=settings.candidates,
        threshold=settings.rerank_threshold,
    )


def build_db_answerer(
    settings: Settings,
    *,
    embeddings: Embeddings | None = None,
    chat_model: BaseChatModel | None = None,
    reranker: Reranker | None = None,
) -> Answerer:
    """Create the answerer over Postgres: chunks were embedded once by `python -m app.ingest`,
    so each question embeds only itself."""
    if not settings.database_url:
        raise ValueError("DATABASE_URL is not set (see .env.example)")
    retriever = PgRetriever(
        make_pool(settings.database_url, name="rag-answerer"),
        embeddings or make_embeddings(settings.embedding_model),
        tenant=settings.tenant,
        roles=settings.roles,
        mode=settings.retrieval_mode,
        candidates=settings.candidates,
    )
    return build_answerer(settings, chat_model=chat_model, retriever=retriever, reranker=reranker)
