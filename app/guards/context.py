"""The context guard (spec 05 D2, D4): checks retrieved chunks before the LLM reads them.

1. Indirect injection: a chunk the classifier flags is dropped (the ingest scan should already
   have quarantined it; this catches chunks ingested before the scanner, or that slipped past it).
2. Sensitive personal data: masked for users without `pii:read`. The model can't repeat what it
   never saw; the database keeps the original text for those allowed to read it (ADR-0004).
"""

from app.domain import AccessScope, GuardVerdict, ScoredChunk
from app.guards.injection import GuardUnavailable, InjectionClassifier
from app.guards.pii import mask


class ContextGuard:
    def __init__(self, classifier: InjectionClassifier | None, threshold: float = 0.5) -> None:
        self.classifier, self.threshold = classifier, threshold

    def check(
        self, chunks: list[ScoredChunk], scope: AccessScope | None
    ) -> tuple[list[ScoredChunk], list[GuardVerdict]]:
        """The chunks the LLM may read (dropped or masked as needed), and a verdict per change."""
        kept, verdicts = [], []
        for hit in chunks:
            if self.classifier is not None:
                try:
                    score = self.classifier.score(hit.chunk.text)
                except Exception as error:
                    raise GuardUnavailable(f"context guard: {type(error).__name__}") from error
                if score >= self.threshold:
                    reason = f"injection in {hit.chunk.id}"
                    verdicts.append(
                        GuardVerdict(
                            guard="context", decision="DROP", score=round(score, 4), reason=reason
                        )
                    )
                    continue
            if not (scope and scope.can_read_pii):
                masked, kinds = mask(hit.chunk.text)
                if kinds:
                    chunk = hit.chunk.model_copy(update={"text": masked})
                    hit = ScoredChunk(chunk=chunk, score=hit.score)
                    reason = f"{hit.chunk.id}: {', '.join(kinds)}"
                    verdicts.append(GuardVerdict(guard="context", decision="MASK", reason=reason))
            kept.append(hit)
        if chunks and not verdicts:  # ran and changed nothing: say so (tester v0.6.0 T-5)
            reason = f"{len(chunks)} chunks checked"
            verdicts.append(GuardVerdict(guard="context", decision="PASS", reason=reason))
        return kept, verdicts
