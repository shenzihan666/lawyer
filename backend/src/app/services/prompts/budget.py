from __future__ import annotations

from dataclasses import dataclass
import math

from .catalog import PromptSegment

APPROX_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    normalized = text or ""
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / APPROX_CHARS_PER_TOKEN))


def clip_text_to_token_budget(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    max_chars = max_tokens * APPROX_CHARS_PER_TOKEN
    normalized = text or ""
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max(0, max_chars - 3)].rstrip() + "..."


@dataclass(frozen=True, slots=True)
class TokenBudget:
    max_input_tokens: int
    reserved_output_tokens: int = 0

    @property
    def available_input_tokens(self) -> int:
        return max(0, self.max_input_tokens - self.reserved_output_tokens)


@dataclass(frozen=True, slots=True)
class PromptAssembly:
    text: str
    estimated_tokens: int
    used_segments: list[str]
    truncated_segments: list[str]


def assemble_prompt_segments(
    segments: list[PromptSegment],
    budget: TokenBudget,
) -> PromptAssembly:
    available_tokens = budget.available_input_tokens
    rendered_parts: list[str] = []
    used_segments: list[str] = []
    truncated_segments: list[str] = []
    spent_tokens = 0

    for segment in segments:
        prefix = f"[{segment.key}@{segment.version}]\n"
        candidate = prefix + segment.content.strip()
        candidate_tokens = estimate_tokens(candidate)
        separator_tokens = estimate_tokens("\n\n") if rendered_parts else 0

        if spent_tokens + separator_tokens + candidate_tokens <= available_tokens:
            if rendered_parts:
                rendered_parts.append("\n\n")
            rendered_parts.append(candidate)
            used_segments.append(segment.key)
            spent_tokens += separator_tokens + candidate_tokens
            continue

        remaining_tokens = available_tokens - spent_tokens - separator_tokens
        if remaining_tokens <= 8:
            truncated_segments.append(segment.key)
            continue

        clipped = prefix + clip_text_to_token_budget(
            segment.content.strip(), remaining_tokens
        )
        if rendered_parts:
            rendered_parts.append("\n\n")
        rendered_parts.append(clipped)
        used_segments.append(segment.key)
        truncated_segments.append(segment.key)
        spent_tokens += separator_tokens + estimate_tokens(clipped)

    text = "".join(rendered_parts).strip()
    return PromptAssembly(
        text=text,
        estimated_tokens=estimate_tokens(text),
        used_segments=used_segments,
        truncated_segments=truncated_segments,
    )
