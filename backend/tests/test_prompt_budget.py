from app.services.prompts import (
    PromptSegment,
    TokenBudget,
    assemble_prompt_segments,
    clip_text_to_token_budget,
    estimate_tokens,
)


def test_prompt_budget_truncates_segments_when_budget_is_tight() -> None:
    assembly = assemble_prompt_segments(
        [
            PromptSegment(key="a", version="v1", content="A" * 120),
            PromptSegment(key="b", version="v1", content="B" * 120),
        ],
        TokenBudget(max_input_tokens=35, reserved_output_tokens=0),
    )

    assert assembly.used_segments
    assert assembly.estimated_tokens <= 35
    assert assembly.truncated_segments


def test_clip_text_to_token_budget_preserves_short_strings() -> None:
    assert clip_text_to_token_budget("hello", 10) == "hello"
    assert clip_text_to_token_budget("x" * 200, 5).endswith("...")
    assert estimate_tokens("abcd") == 1
