"""
LLM-powered match verification for ambiguous entity pairs.

When the similarity score falls in an uncertain range (default 0.55–0.80),
this verifier calls an LLM via litellm to make a binary match/no-match
decision.  This dramatically improves precision for hard cases like
nicknames, abbreviated company names, and varied address formats.

Supports any litellm-compatible model:
    openrouter/google/gemini-2.0-flash
    openai/gpt-4o
    anthropic/claude-3-5-sonnet-20241022
    ollama/mistral  (local, no API key needed)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import litellm

if TYPE_CHECKING:
    from ..config.er_config import LLMProviderConfig

logger = logging.getLogger(__name__)

#: Response budget for a single verdict, in tokens.
#:
#: This was 256, which silently destroyed verdicts. The model answers with JSON
#: whose ``reasoning`` field is free text, and a model that explains itself at
#: any length runs past the cap mid-string. The truncated JSON then fails to
#: parse, the verdict is discarded, and the pair is routed to human review as if
#: the model had never been asked. Measured on 200 ambiguous Amazon-Google pairs:
#: google/gemini-3.8-flash lost 57 of 200 verdicts (28%) at 256 tokens and 1 of
#: 200 at 1024. Terse models were unaffected (claude-opus-5 lost 5, llama3.1:8b
#: none), so the failure is invisible unless a verbose model is tried.
_DEFAULT_MAX_RESPONSE_TOKENS = 1024

#: Floor below which a complete verdict cannot be expressed. decision +
#: confidence + even a one-clause reason needs roughly this much.
_MIN_RESPONSE_TOKENS = 64

#: Where litellm stores the charge a provider reported for a call. OpenRouter
#: returns it in ``usage.cost``; litellm requests it and copies it here, but its
#: own ``completion_cost`` ignores it and prices from a model map instead, which
#: has no entry for many routed models.
_PROVIDER_COST_KEY = "llm_provider-x-litellm-response-cost"


def _as_cost(value: Any) -> Optional[float]:
    """A real number of dollars, or None. Anything else is not a price."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# Tolerant of empty/nested/`json`-tagged fenced blocks (the old split("```")[1]
# crashed on a single or empty fence).
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


MATCH_PROMPT_TEMPLATE = """\
You are an expert in data quality and entity resolution.

Two records have been compared and produced a similarity score of {score:.2f}
(scale 0–1), which is uncertain. Your job is to decide whether they refer to
the SAME real-world {entity_type}.

## Record A
{record_a}

## Record B
{record_b}

## Field-level similarity scores
{field_scores}

## Instructions
- Answer with ONLY a JSON object in this exact format:
  {{"decision": "match" | "no_match", "confidence": 0.0–1.0, "reasoning": "..."}}
- "match" means both records refer to the same {entity_type}.
- "no_match" means they are clearly different {entity_type}s.
- "confidence" is your certainty (0 = complete guess, 1 = certain).
- "reasoning" should be 1–2 sentences max.
- Do NOT add any text outside the JSON object.
"""


class LLMMatchVerifier:
    """
    Verifies ambiguous entity match pairs using an LLM.

    Parameters
    ----------
    model:
        Any litellm model string, e.g. "openrouter/google/gemini-2.0-flash"
        or "openai/gpt-4o".  Defaults to OPENROUTER_MODEL env var, falling
        back to "openrouter/google/gemini-2.0-flash".
    low_threshold:
        Pairs with scores **below** this are accepted as no_match without LLM.
    high_threshold:
        Pairs with scores **above** this are accepted as match without LLM.
    entity_type:
        Human-readable entity type for the prompt (e.g. "company", "person").
    api_key:
        Override API key; otherwise read from OPENROUTER_API_KEY / OPENAI_API_KEY.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        low_threshold: float = 0.55,
        high_threshold: float = 0.80,
        entity_type: str = "entity",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: int = 60,
        max_cost_usd: Optional[float] = None,
        max_calls: Optional[int] = None,
        mask_fields: Optional[List[str]] = None,
        max_response_tokens: int = _DEFAULT_MAX_RESPONSE_TOKENS,
    ) -> None:
        self.model = model or os.getenv("OPENROUTER_MODEL", "openrouter/google/gemini-2.0-flash")
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.entity_type = entity_type
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        #: Response budget for one verdict. See _DEFAULT_MAX_RESPONSE_TOKENS.
        if max_response_tokens < _MIN_RESPONSE_TOKENS:
            raise ValueError(
                f"max_response_tokens must be at least {_MIN_RESPONSE_TOKENS}; "
                f"a smaller budget truncates the verdict JSON and the answer is "
                f"discarded as unparseable"
            )
        self.max_response_tokens = max_response_tokens

        # Cost controls (None = unbounded).
        self.max_cost_usd = max_cost_usd
        self.max_calls = max_calls
        # Field values to replace with stable hashes before sending to the LLM.
        self.mask_fields = set(mask_fields or [])

        self._stats: Dict[str, Any] = {
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "unpriced_calls": 0,
            "parse_failures": 0,
            "budget_stops": 0,
        }

    @classmethod
    def from_provider_config(
        cls,
        provider_config: "LLMProviderConfig",
        **kwargs,
    ) -> "LLMMatchVerifier":
        """Build a verifier from a structured :class:`LLMProviderConfig`."""
        from entity_resolution.config.er_config import LLMProviderConfig as _LPC  # noqa: F811

        # The pipeline's verifier construction honours api_key_env; this
        # sibling path did not, so a key named in config was silently replaced
        # by whatever OPENROUTER_API_KEY / OPENAI_API_KEY held.
        if provider_config.api_key_env and "api_key" not in kwargs:
            kwargs["api_key"] = os.environ.get(provider_config.api_key_env)
        return cls(
            model=provider_config.to_litellm_model_string(),
            base_url=provider_config.base_url,
            timeout_seconds=provider_config.timeout_seconds,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _scrub(self, text: str) -> str:
        """Remove the API key from third-party error text before it is logged or returned.

        Provider exceptions are logged, returned in ``error`` and ``reasoning``,
        and reported by the pipeline's healthcheck. Whether a given provider
        echoes the key it was handed is not something this code controls, so the
        key is removed wherever it appears.
        """
        if self.api_key and len(self.api_key) >= 8:
            text = text.replace(self.api_key, "***")
        return text

    def healthcheck(self) -> Dict[str, Any]:
        """Check whether the configured model/provider is reachable.

        Sends a minimal one-token probe and reports latency.

        Returns:
            Dict with ``ok``, ``model``, ``latency_ms``, ``error``.
        """
        import time as _time

        start = _time.time()
        try:
            healthcheck_timeout = 30 if "ollama" in (self.model or "") else 5
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "timeout": healthcheck_timeout,
            }
            if self.base_url:
                kwargs["api_base"] = self.base_url
            litellm.completion(**kwargs)
            return {
                "ok": True,
                "model": self.model,
                "latency_ms": round((_time.time() - start) * 1000, 1),
                "error": None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "model": self.model,
                "latency_ms": None,
                "error": self._scrub(str(exc)),
            }

    def needs_verification(self, score: float) -> bool:
        """Return True if the score falls in the uncertain range."""
        return self.low_threshold <= score < self.high_threshold

    def stats(self) -> Dict[str, Any]:
        """Cumulative LLM usage: calls, tokens, cost (USD), parse/budget stops.

        ``cost_usd`` is None once any call could not be priced, because a sum
        that leaves calls out would read as the whole spend. ``cost_usd_known``
        is what was priced and ``unpriced_calls`` how many calls were not.
        """
        stats = dict(self._stats)
        stats["cost_usd_known"] = stats["cost_usd"]
        if stats["unpriced_calls"]:
            stats["cost_usd"] = None
        return stats

    def budget_exceeded(self) -> bool:
        """True once the per-run call or cost budget is reached.

        A cost budget fails closed: once a call could not be priced, the spend
        is unknown and the budget counts as reached.
        """
        if self.max_calls is not None and self._stats["calls"] >= self.max_calls:
            return True
        if self.max_cost_usd is not None:
            if self._stats["unpriced_calls"]:
                return True
            if self._stats["cost_usd"] >= self.max_cost_usd:
                return True
        return False

    def estimate_cost(self, num_pairs: int, avg_total_tokens: int = 400) -> Dict[str, Any]:
        """Best-effort pre-run cost estimate for *num_pairs* uncertain pairs.

        Splits ``avg_total_tokens`` 75/25 prompt/completion and uses litellm
        pricing when available; returns ``cost_usd: None`` if pricing is unknown.
        """
        prompt_tokens = int(avg_total_tokens * 0.75)
        completion_tokens = avg_total_tokens - prompt_tokens
        try:
            in_cost, out_cost = litellm.cost_per_token(
                model=self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            per_pair = float(in_cost) + float(out_cost)
            total = round(per_pair * num_pairs, 4)
        except Exception:
            per_pair = None
            total = None
        return {
            "num_pairs": num_pairs,
            "avg_total_tokens": avg_total_tokens,
            "cost_per_pair_usd": round(per_pair, 6) if per_pair is not None else None,
            "cost_usd": total,
        }

    def verify(
        self,
        record_a: Dict[str, Any],
        record_b: Dict[str, Any],
        score: float,
        field_scores: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call the LLM to verify whether *record_a* and *record_b* match.

        If the score is outside the uncertain range this returns immediately
        without making an LLM call.

        Returns a dict with keys:
        - ``decision``: "match" | "no_match" | "skipped"
        - ``confidence``: float (LLM's self-reported confidence)
        - ``reasoning``: str
        - ``score_override``: new score if LLM overrides original (or None)
        - ``llm_called``: bool
        - ``model``: model name used
        """
        # Fast-path for clear matches / non-matches
        if score >= self.high_threshold:
            return self._fast_result("match", score, llm_called=False)
        if score < self.low_threshold:
            return self._fast_result("no_match", score, llm_called=False)

        # Budget guard: once the run's cost/call ceiling is hit, stop calling
        # the LLM and route remaining uncertain pairs to human review.
        if self.budget_exceeded():
            self._stats["budget_stops"] += 1
            return {
                "decision": "pending_review",
                "confidence": 0.0,
                "reasoning": "LLM budget exhausted; routed to human review.",
                "score_override": None,
                "llm_called": False,
                "needs_review": True,
                "model": self.model,
            }

        # LLM call for uncertain pairs
        try:
            return self._call_llm(record_a, record_b, score, field_scores or {})
        except Exception as exc:
            error = self._scrub(str(exc))
            logger.warning("LLM verification failed (falling back to score): %s", error)
            decision = "match" if score >= (self.low_threshold + self.high_threshold) / 2 else "no_match"
            return {
                "decision": decision,
                "confidence": score,
                "reasoning": f"LLM unavailable ({error}); decision based on raw score.",
                "score_override": None,
                "llm_called": False,
                "model": self.model,
                "error": error,
            }

    def verify_batch(
        self,
        pairs: List[Tuple[Dict[str, Any], Dict[str, Any], float]],
        field_scores_list: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Verify a list of (record_a, record_b, score) tuples.

        Only calls the LLM for pairs in the uncertain range.
        """
        results = []
        for i, (a, b, score) in enumerate(pairs):
            fs = field_scores_list[i] if field_scores_list else None
            results.append(self.verify(a, b, score, fs))
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        record_a: Dict[str, Any],
        record_b: Dict[str, Any],
        score: float,
        field_scores: Dict[str, Any],
    ) -> Dict[str, Any]:
        # litellm is imported at module level

        fs_text = "\n".join(
            f"  {field}: {info.get('score', '?'):.2f} ({info.get('method', '?')})"
            for field, info in field_scores.items()
        ) or "  (no field breakdown available)"

        prompt = MATCH_PROMPT_TEMPLATE.format(
            score=score,
            entity_type=self.entity_type,
            record_a=json.dumps(self._clean(record_a), indent=2, default=str),
            record_b=json.dumps(self._clean(record_b), indent=2, default=str),
            field_scores=fs_text,
        )

        parsed, raw = self._complete_and_parse(prompt)

        # One structured re-prompt before giving up — never fabricate a verdict.
        if parsed is None:
            retry_prompt = (
                prompt
                + '\n\nIMPORTANT: Your previous reply was not valid JSON. Reply with '
                'ONLY a JSON object of the form '
                '{"decision": "match" | "no_match", "confidence": 0.0-1.0, "reasoning": "..."} '
                'and nothing else.'
            )
            parsed, raw = self._complete_and_parse(retry_prompt)

        if parsed is None:
            self._stats["parse_failures"] += 1
            logger.warning("LLM returned unparseable output after retry: %s", (raw or "")[:200])
            return {
                "decision": "error",
                "confidence": 0.0,
                "reasoning": f"LLM returned unparseable output; routed to human review. Raw: {(raw or '')[:120]}",
                "score_override": None,
                "llm_called": True,
                "needs_review": True,
                "model": self.model,
            }

        decision = parsed.get("decision", "no_match")
        confidence = float(parsed.get("confidence", score))
        reasoning = parsed.get("reasoning", "")

        # Synthesise a score override: if LLM says match, push above high_threshold
        if decision == "match" and score < self.high_threshold:
            score_override = self.high_threshold + (1.0 - self.high_threshold) * confidence
        elif decision == "no_match" and score >= self.low_threshold:
            score_override = self.low_threshold * (1.0 - confidence)
        else:
            score_override = None

        return {
            "decision": decision,
            "confidence": round(confidence, 4),
            "reasoning": reasoning,
            "score_override": round(score_override, 4) if score_override is not None else None,
            "llm_called": True,
            "model": self.model,
        }

    def _clean(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """Drop internal keys and mask configured PII fields before display.

        Masked fields are replaced with a stable hash so the same value masks
        identically across records, but the raw value never reaches the LLM.
        Note: masking degrades verdict quality for fuzzy fields (the LLM can
        only see exact equality), so reserve it for identifier-like fields.
        """
        out: Dict[str, Any] = {}
        for k, v in d.items():
            if k.startswith("_"):
                continue
            if k in self.mask_fields and v is not None and v != "":
                digest = hashlib.md5(str(v).encode("utf-8")).hexdigest()[:10]
                out[k] = f"masked:{digest}"
            else:
                out[k] = v
        return out

    def _complete_and_parse(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Call the LLM once, account cost/tokens, and parse the verdict JSON.

        Returns ``(parsed_or_None, raw_text)``. Counts toward call/cost budget.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_response_tokens,
            "temperature": 0.1,
            "timeout": self.timeout_seconds,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["api_base"] = self.base_url

        response = litellm.completion(**kwargs)
        self._account(response)
        raw = (response.choices[0].message.content or "").strip()
        return self._parse_verdict(raw), raw

    def _account(self, response: Any) -> None:
        """Accumulate call count, token usage, and cost (all best-effort)."""
        self._stats["calls"] += 1
        try:
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._stats["tokens_in"] += int(getattr(usage, "prompt_tokens", 0) or 0)
                self._stats["tokens_out"] += int(getattr(usage, "completion_tokens", 0) or 0)
        except (TypeError, ValueError):
            pass
        cost = self._price(response)
        if cost is not None:
            self._stats["cost_usd"] += cost
            return
        self._stats["unpriced_calls"] += 1
        if self._stats["unpriced_calls"] == 1:
            logger.warning(
                "No price for %s: neither the provider nor litellm reported what "
                "the call cost, so this run's LLM spend is unknown%s.",
                self.model,
                " and max_cost_usd stops further calls" if self.max_cost_usd is not None else "",
            )

    @staticmethod
    def _price(response: Any) -> Optional[float]:
        """What one call cost in USD, or None if nobody can say.

        The provider's own charge comes first, since it is what was billed;
        litellm's model map is the fallback.
        """
        hidden = getattr(response, "_hidden_params", None)
        if isinstance(hidden, dict):
            headers = hidden.get("additional_headers")
            if isinstance(headers, dict):
                cost = _as_cost(headers.get(_PROVIDER_COST_KEY))
                if cost is not None:
                    return cost
        cost = _as_cost(getattr(getattr(response, "usage", None), "cost", None))
        if cost is not None:
            return cost
        try:
            return _as_cost(litellm.completion_cost(completion_response=response))
        except Exception:
            # litellm raises for a model missing from its price map.
            return None

    @staticmethod
    def _parse_verdict(raw: str) -> Optional[Dict[str, Any]]:
        """Parse the verdict JSON, tolerating markdown fences. None on failure."""
        if not raw:
            return None
        match = _FENCE_RE.search(raw)
        candidate = match.group(1).strip() if match else raw.strip()
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(parsed, dict) or "decision" not in parsed:
            return None
        return parsed

    @staticmethod
    def _fast_result(decision: str, score: float, *, llm_called: bool) -> Dict[str, Any]:
        return {
            "decision": decision,
            "confidence": score,
            "reasoning": "Score outside uncertain range; no LLM call needed.",
            "score_override": None,
            "llm_called": llm_called,
            "model": None,
        }
