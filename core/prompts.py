"""Prompt templates: loaded once, rendered strictly.

Two problems with how prompts were handled before, both fixed here:

* They were read with a bare relative path (`"prompts/system_prompt.txt"`), so
  the application only worked when launched from the repository root, and a
  missing file returned an empty string — the model was then asked to produce a
  brief with no instructions at all.
* They were filled in with chained `str.replace` calls. A renamed placeholder
  left a literal `{{context_blocks}}` in the text and nothing complained.

`render` here is strict in both directions: every placeholder in the template
must be supplied, and every value supplied must correspond to a placeholder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.exceptions import PromptError
from core.logging_config import get_logger

logger = get_logger(__name__)

#: Prompts live next to the package, not next to the working directory.
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Template names, so a typo is an ImportError rather than a missing file at the
# moment a user clicks "Generate brief".
BRIEF_SYSTEM = "system_prompt"
BRIEF_USER = "user_prompt"
QA_SYSTEM = "qa_system_prompt"
QA_USER = "qa_user_prompt"
PLANNER_SYSTEM = "planner_system"
PLANNER_USER = "planner_user"

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class Prompt:
    """One template, with the set of placeholders it declares."""

    name: str
    text: str
    placeholders: frozenset[str]

    def render(self, **values: Any) -> str:
        """Substitute every placeholder, refusing anything less than exact."""
        provided = frozenset(values)

        missing = self.placeholders - provided
        if missing:
            raise PromptError(
                f"Prompt '{self.name}' needs {sorted(missing)}, which were not "
                f"supplied. Declared placeholders: {sorted(self.placeholders)}."
            )

        unexpected = provided - self.placeholders
        if unexpected:
            raise PromptError(
                f"Prompt '{self.name}' has no placeholder for {sorted(unexpected)}. "
                f"Declared placeholders: {sorted(self.placeholders)}."
            )

        rendered = _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), self.text)

        # A value that itself contains `{{...}}` would otherwise smuggle an
        # unrendered placeholder into the prompt. Retrieved document text is a
        # plausible source of that, so it is checked rather than assumed.
        leftover = _PLACEHOLDER.findall(rendered)
        if leftover:
            raise PromptError(
                f"Prompt '{self.name}' still contains placeholders after "
                f"rendering: {sorted(set(leftover))}. A substituted value most "
                f"likely contained '{{{{...}}}}' itself."
            )
        return rendered


@lru_cache(maxsize=32)
def load_prompt(name: str, directory: Path | None = None) -> Prompt:
    """Load and cache one template by name (with or without the `.txt`)."""
    directory = directory or PROMPT_DIR
    stem = name[:-4] if name.endswith(".txt") else name
    path = directory / f"{stem}.txt"

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PromptError(f"Cannot read prompt template {path}: {error}") from error

    if not text.strip():
        raise PromptError(f"Prompt template {path} is empty.")

    placeholders = frozenset(_PLACEHOLDER.findall(text))
    logger.debug("Loaded prompt %s (%d chars, %s)", stem, len(text), sorted(placeholders))
    return Prompt(name=stem, text=text, placeholders=placeholders)


def render_prompt(name: str, /, **values: Any) -> str:
    """Load `name` and render it. The common case, in one call."""
    return load_prompt(name).render(**values)


def clear_prompt_cache() -> None:
    """Forget loaded templates. Call after editing a file in a live process."""
    load_prompt.cache_clear()


def load_prompt_template(prompt_file: str | Path) -> str:
    """Read a template by path, unrendered.

    Kept because `app.py` and the pre-overhaul orchestrator call it that way.
    Unlike the version in `core/synth.py` it raises instead of returning an
    empty string, and it resolves a bare `prompts/...` path against the package
    rather than the working directory.
    """
    path = Path(prompt_file)
    if not path.is_absolute() and not path.exists():
        path = PROMPT_DIR.parent / path

    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise PromptError(f"Cannot read prompt template {path}: {error}") from error
