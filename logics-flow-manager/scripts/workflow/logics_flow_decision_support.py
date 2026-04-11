from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PRODUCT_SIGNAL_RULES = {
    "conversion journey": ("checkout", "signup", "sign up", "onboarding", "activation", "funnel", "conversion"),
    "pricing and packaging": ("pricing", "plan", "subscription", "trial", "paywall"),
    "user segmentation": ("persona", "segment", "target user", "role based"),
    "navigation and discoverability": ("navigation", "search", "filter", "discover", "browse", "menu"),
    "engagement loop": ("notification", "retention", "sharing", "invite", "feed"),
    "experience scope": ("dashboard", "settings", "profile", "empty state", "first run"),
}

ARCHITECTURE_SIGNAL_RULES = {
    "data model and persistence": ("schema", "database", "storage", "migration", "persistence", "data model"),
    "contracts and integration": ("api", "contract", "webhook", "integration", "provider", "sdk"),
    "runtime and boundaries": ("monolith", "modular", "module", "microservice", "boundary"),
    "state and sync": ("cache", "state management", "offline", "sync", "queue", "event", "stream"),
    "security and identity": ("auth", "authentication", "authorization", "permission", "security", "secret"),
    "delivery and operations": ("deployment", "infra", "observability", "monitoring", "performance", "scaling"),
}


@dataclass(frozen=True)
class DecisionAssessment:
    product_level: str
    product_signals: tuple[str, ...]
    architecture_level: str
    architecture_signals: tuple[str, ...]


def _render_product_brief(
    title: str,
    product_ref: str,
    request_ref: str | None,
    backlog_ref: str | None,
    task_ref: str | None,
    architecture_refs: list[str],
) -> str:
    template_path = Path(__file__).resolve().parents[3] / "logics-product-brief-writer" / "assets" / "templates" / "product_brief.md"
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "DOC_REF": product_ref,
        "TITLE": title,
        "DATE": date.today().isoformat(),
        "STATUS": "Proposed",
        "REQUEST_REF": f"`{request_ref}`" if request_ref else "(none yet)",
        "BACKLOG_REF": f"`{backlog_ref}`" if backlog_ref else "(none yet)",
        "TASK_REF": f"`{task_ref}`" if task_ref else "(none yet)",
        "ARCHITECTURE_REF": ", ".join(f"`{ref}`" for ref in architecture_refs) if architecture_refs else "(none yet)",
        "OVERVIEW": "Summarize the product direction, the targeted user value, and the main expected outcomes.",
        "OVERVIEW_MERMAID": (
            "flowchart LR\n"
            "    Problem[User problem] --> Direction[Chosen product direction]\n"
            "    Direction --> Value[User value]\n"
            "    Direction --> Scope[Scoped experience]\n"
            "    Direction --> Outcome[Expected product outcomes]"
        ),
        "PROBLEM": "Describe the user or business problem this brief resolves.",
        "USER_1": "Primary user or segment",
        "GOAL_1": "Primary product goal",
        "NON_GOAL_1": "Explicit non-goal or excluded expectation",
        "IN_SCOPE_1": "Main capability or experience slice included",
        "OUT_OF_SCOPE_1": "Main capability explicitly excluded for now",
        "DECISION_1": "Key product trade-off or framing decision",
        "SUCCESS_SIGNAL_1": "Observable success signal or product metric",
        "QUESTION_1": "Main open product question to resolve",
    }
    return _render_template(template_text, values).rstrip() + "\n"


def _render_architecture_decision(
    title: str,
    architecture_ref: str,
    request_ref: str | None,
    backlog_ref: str | None,
    task_ref: str | None,
) -> str:
    template_path = (
        Path(__file__).resolve().parents[3]
        / "logics-architecture-decision-writer"
        / "assets"
        / "templates"
        / "adr.md"
    )
    template_text = template_path.read_text(encoding="utf-8")
    values = {
        "DOC_REF": architecture_ref,
        "TITLE": title,
        "DATE": date.today().isoformat(),
        "STATUS": "Proposed",
        "DRIVERS": "List the main architectural drivers.",
        "REQUEST_REF": f"`{request_ref}`" if request_ref else "(none yet)",
        "BACKLOG_REF": f"`{backlog_ref}`" if backlog_ref else "(none yet)",
        "TASK_REF": f"`{task_ref}`" if task_ref else "(none yet)",
        "OVERVIEW": "Summarize the chosen direction, what changes, and the main impacted areas.",
        "OVERVIEW_MERMAID": (
            "flowchart LR\n"
            "    Current[Current architecture] --> Decision[Chosen direction]\n"
            "    Decision --> App[Application layer]\n"
            "    Decision --> Data[Data and contracts]\n"
            "    Decision --> Ops[Deployment and observability]\n"
            "    Decision --> Team[Delivery and maintenance]"
        ),
        "CONTEXT": "Describe the problem, constraints, and drivers.",
        "DECISION": "State the chosen option and rationale.",
        "ALT_1": "Alternative option",
        "CONSEQUENCE_1": "Operational/product consequence",
        "MIGRATION_1": "Describe the rollout or migration step.",
        "FOLLOW_UP_1": "List the backlog or task work enabled by this decision.",
    }
    return _render_template(template_text, values).rstrip() + "\n"


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    pattern = r"\b" + re.escape(normalized_phrase).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _detect_signal_labels(text: str, rules: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    normalized = _normalize_text(text)
    labels: list[str] = []
    for label, phrases in rules.items():
        if any(_contains_phrase(normalized, phrase) for phrase in phrases):
            labels.append(label)
    return tuple(labels)


def _decision_level(title_signals: tuple[str, ...], all_signals: tuple[str, ...]) -> str:
    if title_signals or len(all_signals) >= 2:
        return "Required"
    if all_signals:
        return "Consider"
    return "Not needed"


def _assess_decision_framing(title: str, text: str) -> DecisionAssessment:
    combined = f"{title}\n{text}".strip()
    product_title_signals = _detect_signal_labels(title, PRODUCT_SIGNAL_RULES)
    product_signals = _detect_signal_labels(combined, PRODUCT_SIGNAL_RULES)
    architecture_title_signals = _detect_signal_labels(title, ARCHITECTURE_SIGNAL_RULES)
    architecture_signals = _detect_signal_labels(combined, ARCHITECTURE_SIGNAL_RULES)
    return DecisionAssessment(
        product_level=_decision_level(product_title_signals, product_signals),
        product_signals=product_signals,
        architecture_level=_decision_level(architecture_title_signals, architecture_signals),
        architecture_signals=architecture_signals,
    )


def _signals_display(signals: tuple[str, ...]) -> str:
    if not signals:
        return "(none detected)"
    return ", ".join(signals)


def _decision_follow_up(level: str, kind: str) -> str:
    if kind == "product":
        if level == "Required":
            return "Create or link a product brief before implementation moves deeper into delivery."
        if level == "Consider":
            return "Review whether a product brief is needed before scope becomes harder to change."
        return "No product brief follow-up is expected based on current signals."
    if level == "Required":
        return "Create or link an architecture decision before irreversible implementation work starts."
    if level == "Consider":
        return "Review whether an architecture decision is needed before implementation becomes harder to reverse."
    return "No architecture decision follow-up is expected based on current signals."


def _apply_decision_assessment(values: dict[str, str], assessment: DecisionAssessment) -> None:
    values["PRODUCT_FRAMING_STATUS"] = assessment.product_level
    values["PRODUCT_FRAMING_SIGNALS"] = _signals_display(assessment.product_signals)
    values["PRODUCT_FRAMING_ACTION"] = _decision_follow_up(assessment.product_level, "product")
    values["ARCHITECTURE_FRAMING_STATUS"] = assessment.architecture_level
    values["ARCHITECTURE_FRAMING_SIGNALS"] = _signals_display(assessment.architecture_signals)
    values["ARCHITECTURE_FRAMING_ACTION"] = _decision_follow_up(assessment.architecture_level, "architecture")


def _print_decision_summary(
    doc_ref: str,
    assessment: DecisionAssessment,
    product_refs: list[str],
    architecture_refs: list[str],
) -> None:
    product_line = assessment.product_level
    if assessment.product_signals:
        product_line += f" ({_signals_display(assessment.product_signals)})"
    architecture_line = assessment.architecture_level
    if assessment.architecture_signals:
        architecture_line += f" ({_signals_display(assessment.architecture_signals)})"
    lines = [
        f"Decision framing for {doc_ref}:",
        f"- Product: {product_line}",
        f"- Architecture: {architecture_line}",
        f"- Product brief refs: {', '.join(product_refs) if product_refs else '(none yet)'}",
        f"- Architecture decision refs: {', '.join(architecture_refs) if architecture_refs else '(none yet)'}",
    ]
    if assessment.product_level in {"Consider", "Required"} and not product_refs:
        lines.append("- Suggested follow-up: create or link a product brief before delivery gets deeper.")
    if assessment.architecture_level in {"Consider", "Required"} and not architecture_refs:
        lines.append("- Suggested follow-up: create or link an architecture decision before irreversible implementation work.")
    print("\n".join(lines))


def _render_template(template_text: str, values: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", repl, template_text)


__all__ = [name for name in globals() if not name.startswith("__")]
