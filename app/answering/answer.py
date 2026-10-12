"""Answer a question from retrieved chunks, with validated citations, or return a No-Answer."""

from pathlib import Path
from string import Template

from langchain.chat_models import init_chat_model
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.answering.citations import all_citations_retrieved, parse_citations
from app.config import Settings
from app.domain import AnswerResult, ScoredChunk
from app.ingestion.chunking import chunk_pages
from app.ingestion.loaders import load_pages
from app.retrieval.embeddings import make_embeddings
from app.retrieval.search import ChunkIndex

NO_ANSWER = "I don't know based on the documents I can access."
PROMPT_VERSION = "answer_v1"
_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


class Answerer:
    def __init__(self, index: ChunkIndex, chat_model: BaseChatModel, top_k: int) -> None:
        self.index = index
        self.chat_model = chat_model
        self.top_k = top_k
        template = Template((_PROMPTS / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8"))
        self._system_prompt = template.substitute(no_answer=NO_ANSWER)

    def answer(self, question: str) -> AnswerResult:
        retrieved = self.index.search(question, k=self.top_k)
        if not retrieved:
            return self._no_answer(retrieved)

        reply = self.chat_model.invoke(
            [SystemMessage(self._system_prompt), HumanMessage(_user_message(question, retrieved))]
        )
        text = reply.text.strip()

        citations = parse_citations(text)
        if NO_ANSWER in text or not citations or not all_citations_retrieved(citations, retrieved):
            return self._no_answer(retrieved)
        return AnswerResult(
            status="answered",
            answer=text,
            citations=citations,
            retrieved=retrieved,
            prompt_version=PROMPT_VERSION,
        )

    def _no_answer(self, retrieved: list[ScoredChunk]) -> AnswerResult:
        return AnswerResult(
            status="no_answer",
            answer=NO_ANSWER,
            citations=[],
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
) -> Answerer:
    """Load, chunk, and embed the corpus, and create the chat model named in settings."""
    pages = load_pages(settings.corpus_dir)
    chunks = chunk_pages(
        pages,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        encoding_name=settings.tokenizer_encoding,
    )
    index = ChunkIndex(chunks, embeddings or make_embeddings(settings.embedding_model))
    model = chat_model or init_chat_model(
        settings.chat_model, temperature=settings.chat_temperature
    )
    return Answerer(index=index, chat_model=model, top_k=settings.top_k)
