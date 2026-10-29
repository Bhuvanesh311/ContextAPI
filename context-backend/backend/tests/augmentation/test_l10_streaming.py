"""
Streaming answers: the Ollama client streams text to a callback, the
generator reports a length-limited answer, and GET /answer exposes the live
stage and partial text while a request runs.
"""

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.enums import ExecutionProfile, RetrievalRequestStatus as S
from app.infra.ollama.client import OllamaClient
from app.infra.ollama.exceptions import OllamaGenerationError
from app.augmentation.generator import generate
from app.augmentation.schemas import BuiltPrompt
from app.retrieval import router as retrieval_router
from app.retrieval.security.profiles import controls_for


def _ndjson(*chunks: dict) -> io.BytesIO:
    return io.BytesIO(b"".join(json.dumps(c).encode() + b"\n" for c in chunks))


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stream(*chunks: dict):
    return patch("app.infra.ollama.client.urllib_request.urlopen", return_value=_Resp(_ndjson(*chunks).getvalue()))


# --------------------------------------------------------------- client
def test_client_streams_text_and_reports_done_reason():
    seen = []
    with _stream({"response": "Hello", "done": False},
                 {"response": " world", "done": False},
                 {"response": "", "done": True, "done_reason": "length"}):
        text = OllamaClient(base_url="http://x", model="m").generate(
            "q", timeout=5, on_text=lambda t, reason: seen.append((t, reason)))
    assert text == "Hello world"
    assert seen == [("Hello", None), ("Hello world", None), ("Hello world", "length")]


def test_client_stream_without_done_is_an_error():
    with _stream({"response": "Hel", "done": False}), pytest.raises(OllamaGenerationError):
        OllamaClient(base_url="http://x", model="m").generate("q", timeout=5, on_text=lambda t, r: None)


def test_client_stream_error_chunk_raises():
    with _stream({"error": "model crashed"}), pytest.raises(OllamaGenerationError):
        OllamaClient(base_url="http://x", model="m").generate("q", timeout=5, on_text=lambda t, r: None)


# ------------------------------------------------------------ generator
def _prompt() -> BuiltPrompt:
    return BuiltPrompt(system_prompt="s", user_prompt="Question: q", intent="FACT_LOOKUP", estimated_tokens=100)


def _router_streaming(final_reason: str):
    router = MagicMock()

    def tier_b(prompt, timeout, system, on_text):
        on_text("Partial", None)
        on_text("Partial answer", final_reason)
        return "Partial answer"

    router.execute_tier_b_text.side_effect = tier_b
    return router


def test_generator_forwards_live_text_and_flags_length_limit():
    seen = []
    with patch("app.augmentation.generator._get_router", return_value=_router_streaming("length")):
        result = generate(_prompt(), controls_for(ExecutionProfile.DEEP), on_text=seen.append)
    assert seen == ["Partial", "Partial answer"]
    assert result.text == "Partial answer" and result.truncated is True


def test_generator_normal_stop_is_not_truncated():
    with patch("app.augmentation.generator._get_router", return_value=_router_streaming("stop")):
        result = generate(_prompt(), controls_for(ExecutionProfile.DEEP))
    assert result.truncated is False


# --------------------------------------------------------- answer endpoint
def _req(status):
    return SimpleNamespace(
        request_id="req_1", status=status, generated_answer=None, project_id="P1", scope={},
        query="q", execution_profile=ExecutionProfile.DEEP, results=[], sufficiency=None,
        error_code=None, error_message=None,
    )


def test_running_request_exposes_stage_and_partial_text():
    with patch.object(retrieval_router.progress, "read", return_value=("writing", "So far")):
        ans = retrieval_router._to_answer(_req(S.RUNNING))
    assert ans.done is False and ans.stage == "writing" and ans.partial_answer == "So far"


def test_running_request_without_progress_reports_searching():
    with patch.object(retrieval_router.progress, "read", return_value=(None, None)):
        assert retrieval_router._to_answer(_req(S.RUNNING)).stage == "searching"
        assert retrieval_router._to_answer(_req(S.PENDING)).stage == "queued"


def test_finished_request_has_no_live_fields():
    with patch.object(retrieval_router.progress, "read") as read:
        ans = retrieval_router._to_answer(_req(S.COMPLETED))
    read.assert_not_called()
    assert ans.stage is None and ans.partial_answer is None
