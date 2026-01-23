from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List, Tuple

@dataclass(frozen=True)
class TermQuery:
    terms: Tuple[str, ...]
    mode: str = "any"  # any | all

class TermMatcher:
    def match(self, comments: Iterable[str], tq: TermQuery) -> tuple[int, int, List[str]]:
        """
        Returns: (total_term_hits, matched_comment_count, sample_comments)
        total_term_hits counts term occurrences across matched comments.
        """
        terms = [t.lower() for t in tq.terms if t.strip()]
        if not terms:
            return (0, 0, [])

        total_hits = 0
        matched_comments = 0
        samples: List[str] = []

        for c in comments:
            text = (c or "").lower()
            if not text:
                continue

            hits = sum(text.count(t) for t in terms)

            if tq.mode == "all":
                ok = all(t in text for t in terms)
            else:
                ok = any(t in text for t in terms)

            if ok:
                matched_comments += 1
                total_hits += hits
                if len(samples) < 3:  # keep v0 simple
                    samples.append(c)

        return (total_hits, matched_comments, samples)
