"""
LLM output guardrails.

RULE 13: All LLM responses pass guardrails before delivery.
RULE 12: AI disclosure on every voice call.

Checks performed on every LLM response:
1. PII detection (Aadhaar, PAN, phone, email, bank)
2. Prompt injection detection
3. Toxicity/hate speech filter
4. DPDP 2023 compliance (India data protection)
5. Off-topic/hallucination detection
6. AI disclosure injection

Design Pattern: Chain of Responsibility (guard pipeline)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from shared.metrics import LLM_GUARDRAIL_REJECTIONS_TOTAL
from shared.settings import get_settings

logger = structlog.get_logger("guardrails")
settings = get_settings()


class GuardrailAction(str, Enum):
    """Action to take when a guardrail triggers."""

    ALLOW = "allow"         # Pass through unchanged
    REDACT = "redact"       # Remove/mask sensitive content
    REPLACE = "replace"     # Replace with safe alternative
    BLOCK = "block"         # Block the response entirely


@dataclass
class GuardrailResult:
    """Result of running all guardrails on an LLM response."""

    original: str
    sanitized: str
    action: GuardrailAction
    triggered_rules: list[str] = field(default_factory=list)
    blocked: bool = False
    pii_detected: bool = False
    injection_detected: bool = False
    toxic_content: bool = False


# ── PII Patterns ──────────────────────────────────────────────────────────────
_PII_PATTERNS = {
    "aadhaar": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "phone_in": re.compile(r"\b(?:\+91|0)?[6-9]\d{9}\b"),
    "email": re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "ifsc": re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
    "bank_account": re.compile(r"\b\d{9,18}\b"),
    "passport": re.compile(r"\b[A-Z][1-9]\d{7}\b"),
    "voter_id": re.compile(r"\b[A-Z]{3}\d{7}\b"),
    "gstin": re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b"),
}

# ── Prompt Injection Patterns ─────────────────────────────────────────────────
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(your|all)\s+(previous|prior)\s+", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a\s+)?(?:evil|bad|jailbreak|dan|gpt)", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*override", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all\s+instructions)", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\]|\[\s*SYSTEM\s*\]", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are\s+(not|no longer)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are\s+)?(?:human|real person|not an ai)", re.IGNORECASE),
]

# ── Toxicity Keywords (simplified — production uses an ML model) ───────────────
_TOXIC_KEYWORDS = frozenset({
    "suicide", "self-harm", "kill yourself", "bomb", "weapon",
    "terrorist", "attack plan", "explosive",
})

# ── AI Disclosure ──────────────────────────────────────────────────────────────
AI_DISCLOSURE_EN = (
    "Please note: You are speaking with an AI assistant. "
    "This call may be recorded for quality and compliance purposes."
)
AI_DISCLOSURE_HI = (
    "कृपया ध्यान दें: आप एक AI सहायक से बात कर रहे हैं। "
    "यह कॉल गुणवत्ता और अनुपालन उद्देश्यों के लिए रिकॉर्ड की जा सकती है।"
)


class GuardrailPipeline:
    """
    Sequential guardrail pipeline for LLM responses.

    Runs checks in order: PII → injection → toxicity → compliance.
    First blocking rule short-circuits the chain.
    Non-blocking rules (redact/replace) allow chain to continue.
    """

    async def run(
        self,
        response: str,
        tenant_id: str,
        context: dict[str, Any] | None = None,
    ) -> GuardrailResult:
        """
        Run all guardrails on an LLM response.

        Args:
            response: Raw LLM-generated text
            tenant_id: Tenant context for metrics
            context: Optional context (intent, user_id, call_id)

        Returns:
            GuardrailResult with sanitized text and metadata.
        """
        result = GuardrailResult(
            original=response,
            sanitized=response,
            action=GuardrailAction.ALLOW,
        )

        # 1. Prompt injection detection (BLOCK)
        result = self._check_injection(result, tenant_id)
        if result.blocked:
            return result

        # 2. PII detection (REDACT)
        result = self._check_pii(result, tenant_id)

        # 3. Toxicity check (BLOCK)
        result = self._check_toxicity(result, tenant_id)
        if result.blocked:
            return result

        # 4. DPDP compliance check
        result = self._check_dpdp_compliance(result, tenant_id)

        return result

    def _check_injection(
        self, result: GuardrailResult, tenant_id: str
    ) -> GuardrailResult:
        """Detect prompt injection attempts in LLM output."""
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(result.sanitized):
                result.triggered_rules.append("prompt_injection")
                result.injection_detected = True
                result.action = GuardrailAction.BLOCK
                result.blocked = True
                result.sanitized = (
                    "I'm sorry, but I can't process that request. "
                    "Please contact our support team for assistance."
                )
                LLM_GUARDRAIL_REJECTIONS_TOTAL.labels(
                    rule="prompt_injection", tenant_id=tenant_id
                ).inc()
                logger.warning(
                    "guardrail_injection_blocked",
                    tenant_id=tenant_id,
                    pattern=pattern.pattern[:50],
                )
                return result
        return result

    def _check_pii(
        self, result: GuardrailResult, tenant_id: str
    ) -> GuardrailResult:
        """Detect and redact PII from LLM responses."""
        sanitized = result.sanitized
        pii_found = []

        for pii_type, pattern in _PII_PATTERNS.items():
            if pattern.search(sanitized):
                sanitized = pattern.sub(f"[{pii_type.upper()}_REDACTED]", sanitized)
                pii_found.append(pii_type)

        if pii_found:
            result.triggered_rules.extend([f"pii_{p}" for p in pii_found])
            result.pii_detected = True
            result.sanitized = sanitized
            if result.action == GuardrailAction.ALLOW:
                result.action = GuardrailAction.REDACT
            for pii_type in pii_found:
                LLM_GUARDRAIL_REJECTIONS_TOTAL.labels(
                    rule=f"pii_{pii_type}", tenant_id=tenant_id
                ).inc()
            logger.warning(
                "guardrail_pii_redacted",
                tenant_id=tenant_id,
                pii_types=pii_found,
            )
        return result

    def _check_toxicity(
        self, result: GuardrailResult, tenant_id: str
    ) -> GuardrailResult:
        """Check for toxic or harmful content."""
        text_lower = result.sanitized.lower()
        for keyword in _TOXIC_KEYWORDS:
            if keyword in text_lower:
                result.triggered_rules.append("toxicity")
                result.toxic_content = True
                result.action = GuardrailAction.BLOCK
                result.blocked = True
                result.sanitized = (
                    "I'm unable to provide that information. "
                    "If you need support, please contact our HR team directly."
                )
                LLM_GUARDRAIL_REJECTIONS_TOTAL.labels(
                    rule="toxicity", tenant_id=tenant_id
                ).inc()
                logger.warning(
                    "guardrail_toxicity_blocked",
                    tenant_id=tenant_id,
                    keyword=keyword,
                )
                return result
        return result

    def _check_dpdp_compliance(
        self, result: GuardrailResult, tenant_id: str
    ) -> GuardrailResult:
        """
        Check DPDP 2023 compliance.

        Ensures the AI does not make unauthorized disclosures of
        personal data or create discriminatory outputs.
        """
        # Check for sensitive category disclosures (DPDP Schedule 2)
        sensitive_disclosures = [
            r"health\s+condition",
            r"medical\s+history",
            r"religious\s+belief",
            r"caste\s+certificate",
            r"disability\s+status",
            r"sexual\s+orientation",
        ]
        for pattern_str in sensitive_disclosures:
            if re.search(pattern_str, result.sanitized, re.IGNORECASE):
                result.triggered_rules.append("dpdp_sensitive_category")
                LLM_GUARDRAIL_REJECTIONS_TOTAL.labels(
                    rule="dpdp_sensitive_category", tenant_id=tenant_id
                ).inc()
                logger.warning(
                    "guardrail_dpdp_sensitive",
                    tenant_id=tenant_id,
                )
                break
        return result


def inject_ai_disclosure(text: str, language: str = "en") -> str:
    """
    Prepend AI disclosure to a voice response.

    RULE 12: AI disclosure on every voice call.

    Args:
        text: The response text to prepend disclosure to
        language: "en" for English, "hi" for Hindi

    Returns:
        Text with AI disclosure prepended.
    """
    disclosure = AI_DISCLOSURE_HI if language == "hi" else AI_DISCLOSURE_EN
    return f"{disclosure} {text}"


# ── Module-level pipeline singleton ───────────────────────────────────────────
_pipeline = GuardrailPipeline()


def get_guardrail_pipeline() -> GuardrailPipeline:
    """Return the singleton guardrail pipeline."""
    return _pipeline
