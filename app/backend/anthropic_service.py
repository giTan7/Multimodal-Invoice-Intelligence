"""
Everything Claude.  (No Langfuse code in here.)

Sends the REAL document to Claude: an image, a PDF (native document block),
or CSV text (a text block). Images and PDFs are the multimodal part:

    messages = [{"role": "user", "content": [
        {"type": "image" | "document", "source": {base64 ...}},   <- the uploaded file
        {"type": "text", "text": "Please extract the required fields from this invoice."},
    ]}]
    system = <system prompt text that came from Langfuse>
"""
import json
from dataclasses import dataclass
from typing import Optional

import anthropic

from app.utils import config
from app.utils.file_handling import PreparedDocument

MAX_OUTPUT_TOKENS = 1000


class ClaudeCallFailed(Exception):
    """The Claude API call itself failed. `status` is the HTTP code we should return."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class ClaudeOutput:
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: Optional[str]
    parsed: Optional[dict]          # None if the text was not valid JSON
    parse_error: Optional[str]


def _parse_json(text: str):
    """Claude is told to return bare JSON; we still tolerate stray fences/wrapper text."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return None, "No JSON object found in the model output."
    try:
        # parse_float/parse_int=str keeps numbers exactly as Claude wrote them (18880.00 stays '18880.00')
        obj = json.loads(text[start:end + 1], parse_float=str, parse_int=str)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    return (obj, None) if isinstance(obj, dict) else (None, "JSON was not an object.")


class AnthropicService:
    def __init__(self):
        self.client = None
        if config.ANTHROPIC_API_KEY:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY,
                                              max_retries=2, timeout=90.0)

    @property
    def configured(self) -> bool:
        return self.client is not None

    def extract(self, *, model: str, system_text: str, user_text: str,
                document: PreparedDocument) -> ClaudeOutput:
        if self.client is None:
            raise ClaudeCallFailed("ANTHROPIC_API_KEY is missing. Set it in .env and restart the backend.", 500)
        try:
            kwargs = {}
            if system_text:                       # a prompt version may have no system message
                kwargs["system"] = system_text
            response = self.client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                messages=[{"role": "user",
                           "content": [document.to_claude_block(), {"type": "text", "text": user_text}]}],
                **kwargs,
            )
        except anthropic.AuthenticationError:
            raise ClaudeCallFailed("Anthropic rejected the API key (401). Check ANTHROPIC_API_KEY in .env.", 502)
        except anthropic.NotFoundError:
            raise ClaudeCallFailed(f"Model '{model}' was not found (404).", 502)
        except anthropic.RateLimitError:
            raise ClaudeCallFailed("Anthropic rate limit reached. Wait a moment and try again.", 429)
        except anthropic.APIConnectionError:
            raise ClaudeCallFailed("Could not reach Anthropic. Check your internet connection.", 503)
        except anthropic.BadRequestError as e:
            raise ClaudeCallFailed(f"Anthropic rejected the request: {getattr(e, 'message', e)}", 400)
        except anthropic.APIStatusError as e:
            raise ClaudeCallFailed(f"Anthropic API error ({e.status_code}): {getattr(e, 'message', e)}", 502)

        text = "".join(b.text for b in response.content if b.type == "text")
        parsed, err = _parse_json(text)
        return ClaudeOutput(text=text, input_tokens=response.usage.input_tokens,
                            output_tokens=response.usage.output_tokens,
                            stop_reason=response.stop_reason, parsed=parsed, parse_error=err)
