"""Prompt loading and strict rendering."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.exceptions import PromptError
from core.prompts import (
    BRIEF_SYSTEM,
    BRIEF_USER,
    PROMPT_DIR,
    QA_SYSTEM,
    QA_USER,
    clear_prompt_cache,
    load_prompt,
    load_prompt_template,
    render_prompt,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_prompt_cache()
    yield
    clear_prompt_cache()


# --- The shipped templates --------------------------------------------------


def test_every_shipped_prompt_loads():
    for name in (BRIEF_SYSTEM, BRIEF_USER, QA_SYSTEM, QA_USER):
        assert load_prompt(name).text.strip()


def test_brief_prompts_declare_the_placeholders_the_synthesiser_fills():
    assert load_prompt(BRIEF_SYSTEM).placeholders == frozenset()
    assert load_prompt(BRIEF_USER).placeholders == {
        "title",
        "date",
        "context_blocks",
        "previous_meeting",
    }


def test_qa_prompts_declare_the_placeholders_the_synthesiser_fills():
    assert load_prompt(QA_SYSTEM).placeholders == frozenset()
    assert load_prompt(QA_USER).placeholders == {"question", "context_blocks"}


def test_system_prompt_is_no_longer_polluted_with_the_user_prompt():
    """The regression this chunk fixes.

    `system_prompt.txt` had accumulated a verbatim copy of the user prompt, the
    JSON schema, and a changelog from the chat session that produced it -- all
    of it sent to the model as the system message.
    """
    system = load_prompt(BRIEF_SYSTEM).text
    user = load_prompt(BRIEF_USER).text

    assert "MEETING_TITLE:" not in system
    assert "SCHEMA:" not in system
    assert "Changes:" not in system
    assert "{{" not in system

    # The two are genuinely different documents now, not one pasted into both.
    assert user.split("\n")[0] not in system


def test_prompts_no_longer_hand_write_the_json_contract():
    """Structured output supplies the schema; the prompt should not repeat it."""
    for name in (BRIEF_SYSTEM, BRIEF_USER):
        text = load_prompt(name).text
        assert "trailing comma" not in text.lower()
        assert "```" not in text


# --- Rendering --------------------------------------------------------------


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / f"{name}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_render_substitutes_every_placeholder(tmp_path: Path):
    _write(tmp_path, "greet", "Hello {{name}}, welcome to {{place}}.")
    prompt = load_prompt("greet", tmp_path)

    assert prompt.render(name="Ada", place="Cambridge") == (
        "Hello Ada, welcome to Cambridge."
    )


def test_render_accepts_the_name_with_a_txt_suffix(tmp_path: Path):
    _write(tmp_path, "greet", "Hello {{name}}.")
    assert load_prompt("greet.txt", tmp_path).render(name="Ada") == "Hello Ada."


def test_render_rejects_a_missing_value(tmp_path: Path):
    _write(tmp_path, "greet", "Hello {{name}} of {{place}}.")
    prompt = load_prompt("greet", tmp_path)

    with pytest.raises(PromptError, match="place"):
        prompt.render(name="Ada")


def test_render_rejects_a_value_with_no_placeholder(tmp_path: Path):
    """A renamed placeholder used to leave `{{...}}` in the text, silently."""
    _write(tmp_path, "greet", "Hello {{name}}.")
    prompt = load_prompt("greet", tmp_path)

    with pytest.raises(PromptError, match="context_blocks"):
        prompt.render(name="Ada", context_blocks="...")


def test_render_rejects_a_value_that_smuggles_in_a_placeholder(tmp_path: Path):
    _write(tmp_path, "greet", "Context: {{context_blocks}}")
    prompt = load_prompt("greet", tmp_path)

    with pytest.raises(PromptError, match="title"):
        prompt.render(context_blocks="a document mentioning {{title}}")


def test_render_coerces_non_string_values(tmp_path: Path):
    _write(tmp_path, "count", "There are {{n}} items.")
    assert load_prompt("count", tmp_path).render(n=3) == "There are 3 items."


def test_whitespace_inside_the_braces_is_tolerated(tmp_path: Path):
    _write(tmp_path, "greet", "Hello {{ name }}.")
    assert load_prompt("greet", tmp_path).render(name="Ada") == "Hello Ada."


# --- Failure modes ----------------------------------------------------------


def test_a_missing_template_raises_rather_than_returning_empty(tmp_path: Path):
    """`core.synth.load_prompt_template` returned "" and let the call proceed."""
    with pytest.raises(PromptError, match="Cannot read"):
        load_prompt("does_not_exist", tmp_path)


def test_an_empty_template_raises(tmp_path: Path):
    _write(tmp_path, "blank", "   \n  ")
    with pytest.raises(PromptError, match="empty"):
        load_prompt("blank", tmp_path)


# --- Caching and path resolution -------------------------------------------


def test_templates_are_cached(tmp_path: Path):
    path = _write(tmp_path, "greet", "Hello {{name}}.")
    first = load_prompt("greet", tmp_path)

    path.write_text("Goodbye {{name}}.", encoding="utf-8")
    assert load_prompt("greet", tmp_path) is first

    clear_prompt_cache()
    assert load_prompt("greet", tmp_path).text.startswith("Goodbye")


def test_prompts_resolve_relative_to_the_package_not_the_cwd(tmp_path: Path):
    """Launching Streamlit from anywhere but the repo root used to lose them."""
    original = Path.cwd()
    os.chdir(tmp_path)
    try:
        assert render_prompt(BRIEF_SYSTEM).strip()
        assert load_prompt_template("prompts/system_prompt.txt").strip()
    finally:
        os.chdir(original)


def test_prompt_dir_points_at_the_repository_prompts(tmp_path: Path):
    assert (PROMPT_DIR / "system_prompt.txt").exists()
