import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from app.retrieval.intelligence.providers.base import AbstractModelProvider

def _json_system(schema: Dict[str, Any], system: Optional[str]) -> str:
    """Trusted instructions (if any) first, then the JSON output contract."""
    contract = (
        "You must output ONLY valid JSON matching this schema exactly:\n"
        f"{json.dumps(schema)}\n"
        "Do not include markdown blocks, just the raw JSON."
    )
    if system:
        return f"{system}\n\n{contract}"
    return "You are a structured data extraction assistant. " + contract


class BaseExternalProvider(AbstractModelProvider):
    def __init__(self, provider_name: str, api_key: str):
        self._provider_name = provider_name
        self._api_key = api_key

    def _ensure_api_key(self):
        if not self._api_key or self._api_key.startswith("MOCK_"):
            raise RuntimeError(f"{self._provider_name} API key is missing or is a mock placeholder.")

    def _post_json(self, url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode()
            if e.code == 429:
                raise RuntimeError(f"HTTP 429 Too Many Requests from {self._provider_name}: {err_msg}") from e
            raise RuntimeError(f"HTTP {e.code} from {self._provider_name}: {err_msg}") from e
        except Exception as e:
            raise RuntimeError(f"Request failed for {self._provider_name}: {e}") from e

class OpenAILikeProvider(BaseExternalProvider):
    """Generic OpenAI-compatible Chat Completions API adapter."""
    def __init__(self, provider_name: str, api_key: str, base_url: str, model_name: str):
        super().__init__(provider_name, api_key)
        self._base_url = base_url
        self._model_name = model_name

    def generate_structured(self, prompt: str, schema: Dict[str, Any], timeout: int = 60, system: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_api_key()
        
        system_prompt = _json_system(schema, system)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ContextAPI/1.0"
        }
        
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }

        resp = self._post_json(self._base_url, headers, payload, timeout)
        try:
            content = resp["choices"][0]["message"]["content"]
            # Sometimes models wrap in markdown despite instructions
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Malformed response from {self._provider_name}: {resp}") from e

class GroqProvider(OpenAILikeProvider):
    def __init__(self, api_key: str):
        super().__init__("Groq", api_key, "https://api.groq.com/openai/v1/chat/completions", "llama-3.1-8b-instant")

class DeepSeekProvider(OpenAILikeProvider):
    def __init__(self, api_key: str):
        super().__init__("DeepSeek", api_key, "https://api.deepseek.com/chat/completions", "deepseek-chat")

class OpenRouterProvider(OpenAILikeProvider):
    def __init__(self, api_key: str):
        # Using a fast/free openrouter model for tests
        super().__init__("OpenRouter", api_key, "https://openrouter.ai/api/v1/chat/completions", "google/gemini-2.5-flash")

class KimiProvider(OpenAILikeProvider):
    def __init__(self, api_key: str):
        super().__init__("Kimi", api_key, "https://api.moonshot.cn/v1/chat/completions", "moonshot-v1-8k")
        # Kimi doesn't strictly support response_format json_object in all versions, 
        # but system prompt enforces json. We'll pop it if it fails.
        
    def generate_structured(self, prompt: str, schema: Dict[str, Any], timeout: int = 60, system: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_api_key()
        system_prompt = _json_system(schema, system)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ContextAPI-L03/1.0"
        }
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0
        }
        resp = self._post_json(self._base_url, headers, payload, timeout)
        try:
            content = resp["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            return json.loads(content.strip())
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Malformed response from Kimi: {resp}") from e


class GeminiProvider(BaseExternalProvider):
    def __init__(self, api_key: str):
        super().__init__("Gemini", api_key)

    def generate_structured(self, prompt: str, schema: Dict[str, Any], timeout: int = 60, system: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_api_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self._api_key}"
        
        headers = {"Content-Type": "application/json", "User-Agent": "ContextAPI/1.0"}
        
        # Gemini expects a slightly different JSON Schema format (OpenAPI subset)
        # We'll just enforce it via system instruction and standard text generation
        # since deep nested schemas are sometimes rejected by their strict responseSchema.
        system_instruction = {
            "parts": [{"text": _json_system(schema, system)}]
        }
        
        payload = {
            "systemInstruction": system_instruction,
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        
        resp = self._post_json(url, headers, payload, timeout)
        try:
            content = resp["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(content.strip())
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Malformed response from Gemini: {resp}") from e
