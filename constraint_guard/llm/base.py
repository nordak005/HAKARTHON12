"""
constraint_guard.llm.base
=========================
Abstract base class for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMProvider(ABC):
    """Abstract interface for LLM interaction."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text completion from prompt."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if active credentials/endpoint are configured."""
        pass

    @abstractmethod
    def list_models(self) -> List[Dict[str, Any]]:
        """List models supported/available from provider endpoint."""
        pass

    @abstractmethod
    def test_model_availability(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Test access to specific model and return availability status dict."""
        pass
