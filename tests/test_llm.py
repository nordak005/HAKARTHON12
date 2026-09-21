"""
tests/test_llm.py
=================
Unit tests for LLM provider abstraction, code parsing, prompts, and code generation.
"""

import os
import pytest
from constraint_guard.llm.base import LLMProvider
from constraint_guard.llm.parser import extract_python_code
from constraint_guard.llm.prompts import (
    build_code_generation_prompt,
    build_repair_prompt,
)
from constraint_guard.llm.provider import (
    DeterministicMockProvider,
    FallbackMockProvider,
    OpenAICompatibleProvider,
    get_default_provider,
)
from constraint_guard.llm.service import generate_code


class TestCodeParsing:
    def test_markdown_python_block(self):
        raw = "Here is your code:\n```python\ndef foo():\n    return 42\n```\nHope this helps!"
        extracted = extract_python_code(raw)
        assert extracted == "def foo():\n    return 42"

    def test_markdown_generic_block(self):
        raw = "```\nx = 10\ny = 20\n```"
        extracted = extract_python_code(raw)
        assert extracted == "x = 10\ny = 20"

    def test_plain_python_code(self):
        raw = "def bar(a, b):\n    return a + b"
        extracted = extract_python_code(raw)
        assert extracted == "def bar(a, b):\n    return a + b"

    def test_empty_string(self):
        assert extract_python_code("") == ""

    def test_type_fragment_and_docstring_preamble_stripping(self):
        raw = """\
Union[str, Iterable[Any]]
The original input if it is non-empty.

Raises
------
ValueError
    If the input is empty.

def find_max(numbers):
    if not numbers:
        return None

    result = numbers[0]
    for number in numbers[1:]:
        if number > result:
            result = number

    return result
"""
        extracted = extract_python_code(raw)
        assert "Union[str" not in extracted
        assert "Raises" not in extracted
        assert extracted.startswith("def find_max(numbers):")
        assert "return result" in extracted

    def test_code_block_with_leading_prose_and_docstring_specs(self):
        raw = """\
```python
Union[str, Iterable[Any]]
The original input if it is non-empty.

def find_max(numbers):
    return numbers[0]
```
"""
        extracted = extract_python_code(raw)
        assert "Union[str" not in extracted
        assert extracted == "def find_max(numbers):\n    return numbers[0]"

    def test_raw_text_with_trailing_explanation(self):
        raw = """\
def find_max(numbers):
    return numbers[0]

Explanation: The max() function was replaced with direct indexing.
"""
        extracted = extract_python_code(raw)
        assert "Explanation:" not in extracted
        assert extracted == "def find_max(numbers):\n    return numbers[0]"



class TestLLMProviders:
    def test_fallback_provider_when_no_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        provider = get_default_provider()
        assert isinstance(provider, FallbackMockProvider)
        assert not provider.is_configured()

        code = generate_code([{"turn": 1, "text": "find max"}], provider=provider)
        assert "def find_max" in code

    def test_deterministic_provider_registration(self):
        provider = DeterministicMockProvider()
        provider.register_response("custom_key", "def custom_func(): pass")
        res = provider.generate("Prompt containing custom_key")
        assert "def custom_func(): pass" in res

    def test_openai_provider_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        provider = OpenAICompatibleProvider()
        with pytest.raises(RuntimeError, match="LLM_API_KEY is not configured"):
            provider.generate("Hello")


class TestPromptFormatting:
    def test_build_code_generation_prompt(self):
        conv = [
            {"turn": 1, "text": "Do not use max()."},
            {"turn": 2, "text": "Handle empty list."},
        ]
        prompt = build_code_generation_prompt(conv)
        assert "Turn 1: Do not use max()." in prompt
        assert "Turn 2: Handle empty list." in prompt

    def test_build_repair_prompt(self):
        conv = [{"turn": 1, "text": "Do not use max()."}]
        prompt = build_repair_prompt(
            conversation=conv,
            code="def f(x): return max(x)",
            active_constraints=[],
            violated_results=[],
        )
        assert "=== ORIGINAL CONVERSATION ===" in prompt
        assert "=== CURRENT GENERATED CODE ===" in prompt
