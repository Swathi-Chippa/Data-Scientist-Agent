"""
Unified LLM Client supporting:
1. Local Ollama (qwen2.5-coder:latest) - ultra-fast, zero-quota, local & private
2. Google Gemini (gemini-3.5-flash-lite / gemini-3.8-flash) - cloud secondary
3. Graceful fallback to deterministic pipeline if no LLM is reachable.
"""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

logger = logging.getLogger("DataScientistAgent.LLM")


class OllamaClient:
    """Fast local client for Ollama running qwen2.5-coder:latest."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:latest")
        self._cached_available: Optional[bool] = None

    def is_available(self) -> bool:
        """Checks if local Ollama daemon is running and has models."""
        if self._cached_available is not None:
            return self._cached_available
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, headers={"User-Agent": "DataScientistAgent"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check if requested model or family is available
                    available = any(self.model in m or "qwen2.5-coder" in m for m in models) or len(models) > 0
                    self._cached_available = available
                    if available:
                        logger.info(f"Connected to local Ollama with model {self.model}")
                    return available
        except Exception:
            pass
        self._cached_available = False
        return False

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None
    ) -> Optional[str]:
        """Calls local Ollama chat API."""
        if not self.is_available():
            return None
        try:
            url = f"{self.base_url}/api/chat"
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.2
                }
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning(f"Ollama generate_text failed: {e}")
            return None

    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Calls local Ollama chat API in native JSON format mode."""
        if not self.is_available():
            return None
        try:
            url = f"{self.base_url}/api/chat"
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0.0
                }
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                content = res.get("message", {}).get("content", "").strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                return json.loads(content.strip())
        except Exception as e:
            logger.warning(f"Ollama generate_json failed: {e}")
            return None


class GeminiClient:
    """Wrapper around official google.genai SDK for Gemini."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.client = None
        self._init_client()

    def _init_client(self):
        if not self.api_key:
            return
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            logger.warning(f"Failed to initialize Google GenAI Client: {e}")
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None and bool(self.api_key)

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None
    ) -> Optional[str]:
        if not self.is_available():
            return None
        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=0.2,
            system_instruction=system_instruction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )
        candidates = [model or self.model_name, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in candidates:
            try:
                response = self.client.models.generate_content(model=cand, contents=prompt, config=config)
                if response and response.text:
                    return response.text
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    return None
        return None

    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not self.is_available():
            return None
        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            system_instruction=system_instruction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )
        candidates = [model or self.model_name, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in candidates:
            try:
                response = self.client.models.generate_content(model=cand, contents=prompt, config=config)
                if response and response.text:
                    clean = response.text.strip().replace("```json", "").replace("```", "").strip()
                    return json.loads(clean)
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    return None
        return None


class UnifiedLLMClient:
    """Dispatches to local Ollama (qwen2.5-coder:latest) first, then Gemini cloud."""

    def __init__(self):
        self.ollama = OllamaClient()
        self.gemini = GeminiClient()
        self.provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    def is_available(self) -> bool:
        if self.provider == "ollama" and self.ollama.is_available():
            return True
        return self.gemini.is_available() or self.ollama.is_available()

    def get_active_model_name(self) -> str:
        if self.provider == "ollama" and self.ollama.is_available():
            return self.ollama.model
        if self.gemini.is_available():
            return self.gemini.model_name
        if self.ollama.is_available():
            return self.ollama.model
        return "deterministic-fallback"

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None
    ) -> Optional[str]:
        # Try Ollama first if configured or available
        if self.provider == "ollama" or self.ollama.is_available():
            res = self.ollama.generate_text(prompt, system_instruction)
            if res:
                return res

        # Try Gemini if Ollama didn't return
        if self.gemini.is_available():
            res = self.gemini.generate_text(prompt, system_instruction)
            if res:
                return res

        return None

    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        # Try Ollama first if configured or available
        if self.provider == "ollama" or self.ollama.is_available():
            res = self.ollama.generate_json(prompt, system_instruction)
            if res:
                return res

        # Try Gemini if Ollama didn't return
        if self.gemini.is_available():
            res = self.gemini.generate_json(prompt, system_instruction)
            if res:
                return res

        return None


# Singleton instance
_client_instance: Optional[UnifiedLLMClient] = None

def get_llm_client() -> UnifiedLLMClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = UnifiedLLMClient()
    return _client_instance

# Backwards compatibility alias
def get_gemini_client() -> UnifiedLLMClient:
    return get_llm_client()
