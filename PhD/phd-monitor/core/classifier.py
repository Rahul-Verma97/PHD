"""
Classifier — two-stage signal detection.
Stage 1: Fast keyword matching (always runs, free).
Stage 2: Optional LLM verification for low-confidence hits (requires OPENAI_API_KEY).
"""
import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class Classifier:
    def __init__(self, keywords: dict):
        self.strong = [s.lower() for s in keywords.get("strong_signals", [])]
        self.weak   = [s.lower() for s in keywords.get("weak_signals", [])]
        self.neg    = [s.lower() for s in keywords.get("negative_filters", [])]
        self._openai_client = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def classify(self, text: str) -> Tuple[bool, str]:
        """
        Returns (is_hiring_signal, confidence).
        confidence is 'high', 'low', or 'none'.
        """
        is_hit, confidence = self._keyword_classify(text)
        if not is_hit:
            return False, "none"

        # Optionally verify low-confidence hits with LLM
        if confidence == "low" and os.getenv("OPENAI_API_KEY"):
            is_hit = self._llm_verify(text)
            if not is_hit:
                return False, "none"

        return True, confidence

    # ── Internal ───────────────────────────────────────────────────────────────

    def _keyword_classify(self, text: str) -> Tuple[bool, str]:
        lower = text.lower()

        # Negative filter check first
        for phrase in self.neg:
            if phrase in lower:
                logger.debug("Negative filter matched: %r", phrase)
                return False, "none"

        # Strong signal check
        for phrase in self.strong:
            if phrase in lower:
                logger.debug("Strong signal matched: %r", phrase)
                return True, "high"

        # Weak signal: need 2+ matches
        weak_matches = [p for p in self.weak if p in lower]
        if len(weak_matches) >= 2:
            logger.debug("Weak signals matched (%d): %s", len(weak_matches), weak_matches)
            return True, "low"

        return False, "none"

    def _llm_verify(self, text: str) -> bool:
        """Use GPT-3.5-turbo to verify ambiguous signals. ~$0.002/call."""
        try:
            if self._openai_client is None:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            snippet = text[:800]  # keep cost low
            response = self._openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You detect whether a professor is currently "
                            "accepting new PhD students. Answer only YES or NO."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Is this professor actively recruiting new PhD students?\n\n{snippet}",
                    },
                ],
                max_tokens=5,
                temperature=0,
            )
            answer = response.choices[0].message.content.strip().upper()
            logger.debug("LLM verification answer: %s", answer)
            return answer.startswith("YES")
        except Exception as e:
            logger.warning("LLM verification failed: %s — keeping low-confidence hit", e)
            return True  # fail-open: keep the alert rather than drop it
