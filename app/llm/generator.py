"""Local LLM inference module using Ollama and Qwen2.5:3b.

Connects to the local Ollama daemon, verifies service and model availability,
and produces context-grounded responses without any external cloud APIs.
"""

from __future__ import annotations

import logging
from typing import Any
import requests

from app.config import AppConfig

logger = logging.getLogger(__name__)


class OllamaServiceError(Exception):
    """Raised when the Ollama service is unreachable or returns an error."""


class ModelNotFoundError(OllamaServiceError):
    """Raised when the configured model is not pulled in Ollama."""


class OllamaLLM:
    """Interface to local Ollama inference server."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        temperature: float = 0.1,
        timeout: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    @classmethod
    def from_config(cls, cfg: AppConfig) -> OllamaLLM:
        return cls(
            base_url=cfg.ollama_base_url,
            model=cfg.ollama_model,
            temperature=cfg.llm_temperature,
            timeout=cfg.llm_timeout,
        )

    def check_connection(self) -> tuple[bool, str]:
        """Check whether Ollama is running and the configured model is ready.

        Returns:
            Tuple of (is_available, status_message).
        """
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False, f"Ollama returned HTTP {resp.status_code}: {resp.text}"

            models_data = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models_data]

            # Match model name (e.g. 'qwen2.5:3b' or 'qwen2.5:3b-latest')
            matched = any(
                self.model == name or self.model == name.split(":")[0] or name.startswith(self.model)
                for name in model_names
            )

            if not matched:
                return False, (
                    f"Ollama is running, but model '{self.model}' is not installed.\n"
                    f"Please run: `ollama pull {self.model}`"
                )

            return True, f"Ollama is online with model '{self.model}' ready."

        except requests.exceptions.ConnectionError:
            return False, (
                f"Cannot connect to Ollama at {self.base_url}.\n"
                "Please verify that Ollama is installed and running (`ollama serve`)."
            )
        except Exception as e:
            return False, f"Error checking Ollama status: {e}"

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate text completion from local Ollama model.

        Args:
            prompt: User prompt string.
            system_prompt: Optional system instruction prompt.
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            Completed response string.

        Raises:
            OllamaServiceError: If communication or generation fails.
        """
        temp = temperature if temperature is not None else self.temperature
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temp,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 404:
                raise ModelNotFoundError(f"Model '{self.model}' not found in Ollama.")
            if resp.status_code != 200:
                raise OllamaServiceError(f"Ollama generation failed (HTTP {resp.status_code}): {resp.text}")

            result = resp.json()
            return result.get("response", "").strip()

        except requests.exceptions.ConnectionError as e:
            msg = (
                f"Failed to connect to Ollama at {self.base_url}. "
                "Ensure the Ollama service is active."
            )
            logger.error(msg)
            raise OllamaServiceError(msg) from e
        except requests.exceptions.Timeout as e:
            msg = f"Ollama request timed out after {self.timeout}s."
            logger.error(msg)
            raise OllamaServiceError(msg) from e
        except Exception as e:
            logger.error("Ollama inference error: %s", e)
            raise OllamaServiceError(f"Ollama generation error: {e}") from e

    def answer_with_context(self, question: str, context: str) -> str:
        """Answer question strictly grounded in retrieved document context."""
        system_prompt = (
            "You are Cognify, an accurate and professional AI document assistant.\n"
            "Your task is to answer the user's question based STRICTLY and ONLY on the provided context.\n"
            "Rules:\n"
            "1. Rely only on clear facts directly mentioned in the context.\n"
            "2. Do not assume or extrapolate beyond what is stated.\n"
            "3. If the context does not contain enough information to answer the question, clearly state:\n"
            "   'The provided documents do not contain information regarding this question.'\n"
            "4. Never fabricate citations, policies, or facts."
        )

        user_prompt = (
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

        return self.generate(prompt=user_prompt, system_prompt=system_prompt)

