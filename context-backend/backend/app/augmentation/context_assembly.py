"""
L9: Context / Token / Compression Management -> AssembledContext.

Steps (in L07's evidence order; scores are not comparable across retrievers,
cross-encoder logits and RRF, so there is no absolute score cut-off):
  1. Integrity validation  - drop empty items
  2. Deduplication         - same chunk_id or identical text is kept once
  3. Token trimming        - cap each item at _MAX_ITEM_TOKENS
  4. Budget packing        - fit the token budget; the last item that does
                             not fit is compressed (trimmed) if enough room
                             is left, otherwise packing stops
  5. Conflict preservation - L06 conflicts between packed items become notes
                             so the model reports the disagreement
Ranks are renumbered 1..n so [N] citations map to what the model saw.
"""

import re

from app.retrieval.evidence.package import EvidencePackage
from app.augmentation.schemas import AssembledContext, ContextItem

_DEFAULT_BUDGET_TOKENS = 3_000
_MAX_ITEM_TOKENS = 400
_MIN_COMPRESSED_TOKENS = 80   # below this a trimmed item is not worth including

_WS = re.compile(r"\s+")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _trim(text: str, max_tokens: int) -> str:
    cut = text[: max_tokens * 4]
    # Prefer ending on a sentence or word boundary.
    for sep in (". ", "\n", " "):
        idx = cut.rfind(sep)
        if idx > len(cut) * 0.6:
            return cut[: idx + 1].rstrip()
    return cut


def assemble_context(package: EvidencePackage, budget_tokens: int = _DEFAULT_BUDGET_TOKENS) -> AssembledContext:
    items: list[ContextItem] = []
    used = 0
    truncated = False
    dropped = 0
    seen_chunks: set[str] = set()
    seen_text: set[str] = set()
    evidence = list(package.evidence)

    for index, item in enumerate(evidence):
        content = (item.content or "").strip()
        if not content:
            dropped += 1
            continue

        normalized = _WS.sub(" ", content).lower()
        if item.source.chunk_id in seen_chunks or normalized in seen_text:
            dropped += 1
            continue

        if _estimate_tokens(content) > _MAX_ITEM_TOKENS:
            content = _trim(content, _MAX_ITEM_TOKENS)
            truncated = True
        tokens = _estimate_tokens(content)

        remaining = budget_tokens - used
        if tokens > remaining:
            if remaining >= _MIN_COMPRESSED_TOKENS:
                content = _trim(content, remaining)
                tokens = _estimate_tokens(content)
            else:
                truncated = True
                dropped += len(evidence) - index
                break
            truncated = True

        seen_chunks.add(item.source.chunk_id)
        seen_text.add(normalized)
        items.append(ContextItem(
            rank=len(items) + 1,
            evidence_id=item.evidence_id,
            content=content,
            document_id=item.source.document_id,
            document_name=item.source.document_name,
            chunk_id=item.source.chunk_id,
            score=item.score,
            tokens=tokens,
        ))
        used += tokens

    rank_by_chunk = {ci.chunk_id: ci.rank for ci in items}
    notes: list[str] = []
    for conflict in package.conflicts:
        ranks = sorted({rank_by_chunk[c] for c in conflict.chunk_ids if c in rank_by_chunk})
        if len(ranks) >= 2:
            refs = " and ".join(f"[{r}]" for r in ranks)
            notes.append(f"Evidence {refs} disagree: {conflict.reason}.")
        elif len(ranks) == 1:
            notes.append(f"Evidence [{ranks[0]}] is contradicted by other evidence: {conflict.reason}.")

    return AssembledContext(
        items=items,
        total_tokens=used,
        budget_tokens=budget_tokens,
        truncated=truncated,
        items_dropped=dropped,
        conflict_notes=notes,
    )
