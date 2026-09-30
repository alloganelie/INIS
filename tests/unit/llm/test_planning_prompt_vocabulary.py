"""§8.4/§22.3 — the planning prompt states the closed vocabulary.

A planner that is not told the allowed actions can only guess them, and a guess
is refused downstream anyway. The prompt therefore carries the vocabulary and the
rule that comes with it: a step must declare one of its values as ``action``, and
any other value makes the whole plan invalid.
"""

from __future__ import annotations

from app.agents.pipeline.tool_dispatch import ACTIONS
from app.llm.prompts.planning_prompt import build


def _prompt(**overrides: object) -> str:
    arguments: dict = {
        "objective": "Compter les villes de plus de 100 000 habitants",
        "available_tools": ["collector", "web_search"],
        "available_actions": sorted(ACTIONS),
    }
    arguments.update(overrides)
    return build(**arguments)


class TestTheVocabularyIsStated:
    def test_every_action_of_the_vocabulary_appears(self) -> None:
        prompt = _prompt()

        for action in ACTIONS:
            assert action in prompt

    def test_the_prompt_says_the_vocabulary_is_closed(self) -> None:
        assert "Closed vocabulary of actions" in _prompt()

    def test_the_prompt_requires_an_action_field(self) -> None:
        prompt = _prompt()

        assert '"action"' in prompt
        assert "makes the whole plan invalid" in prompt

    def test_the_action_is_omitted_when_not_given(self) -> None:
        """An existing caller keeps its prompt: the vocabulary is optional."""
        prompt = _prompt(available_actions=None)

        assert "Closed vocabulary of actions" not in prompt
        assert "makes the whole plan invalid" not in prompt
