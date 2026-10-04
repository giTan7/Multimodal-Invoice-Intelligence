"""
Orchestration: the only file that knows about BOTH Langfuse and Claude.

  1. validate/prepare the uploaded document
  2. fetch the chosen prompt version from Langfuse
  3. open a trace, call Claude, record usage
  4. check HOW the model answered (valid JSON? right keys?) and report it honestly
"""
import time
import uuid

from app.backend.anthropic_service import AnthropicService, ClaudeCallFailed
from app.backend.langfuse_service import LangfuseService
from app.backend.schemas import ExtractResponse, InvoiceFields, RequestInfo
from app.utils import config
from app.utils.file_handling import prepare_document

FIELD_NAMES = ["invoice_number", "vendor_name", "gstin", "invoice_date", "total_amount"]
DEFAULT_USER_TEXT = "Please extract the required fields from this invoice."
DOC_PLACEHOLDER = "the attached invoice document"


def _as_text(value):
    """Show everything as text; empty -> None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _split_prompt(prompt):
    """
    Langfuse prompt -> (system text, user text). The file itself is attached later.

    Robust on purpose, because prompts are edited by humans in the Langfuse UI:
      * `{{input}}` (a variable people often add) is filled with a short phrase, never left literal;
      * placeholder messages and non-text content are ignored;
      * a plain *text* prompt is treated as the system prompt.
    """
    compiled = prompt.compile(input=DOC_PLACEHOLDER)
    if isinstance(compiled, str):
        return compiled.strip(), DEFAULT_USER_TEXT

    system_parts, user_parts = [], []
    for message in compiled:
        role, content = message.get("role"), message.get("content")
        if not isinstance(content, str):
            continue
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            user_parts.append(content)
    user_text = "\n\n".join(user_parts).strip()
    if user_text in ("", DOC_PLACEHOLDER):
        user_text = DEFAULT_USER_TEXT
    return "\n\n".join(system_parts).strip(), user_text


def _judge_shape(parsed, raw_text):
    """Did the model follow the output contract? Returns (status, message, keys_returned)."""
    if parsed is None:
        return ("not_json",
                "The model answered in plain text, not JSON. This prompt version doesn't ask for a "
                "structured format, so the app has nothing to read the fields from.", [])
    keys = list(parsed.keys())
    missing = [k for k in FIELD_NAMES if k not in parsed]
    if missing:
        return ("off_schema",
                f"The model returned JSON, but without these expected keys: {', '.join(missing)}. "
                f"Keys it used instead: {', '.join(keys) or 'none'}. "
                f"This prompt version doesn't pin the key names.", keys)
    return "ok", None, keys


class InvoiceService:
    def __init__(self, langfuse: LangfuseService, claude: AnthropicService):
        self.langfuse = langfuse
        self.claude = claude

    # ---- a SAVED prompt version, fetched from Langfuse (the Invoice Extractor page) ----------
    def extract(self, *, filename: str, data: bytes, version: int,
                model: str, user_id: str) -> ExtractResponse:
        document = prepare_document(filename, data)                 # may raise InvalidDocument
        prompt = self.langfuse.get_prompt(version)                  # may raise PromptNotFound
        system_text, user_text = _split_prompt(prompt)
        return self._run(document=document, filename=filename, system_text=system_text,
                         user_text=user_text, prompt=prompt, prompt_version=prompt.version,
                         model=model, user_id=user_id)

    # ---- an UNSAVED draft from Prompt Studio: same Claude call, nothing is created in Langfuse ----
    def test_draft(self, *, filename: str, data: bytes, system_prompt: str,
                   model: str, user_id: str) -> ExtractResponse:
        document = prepare_document(filename, data)
        system_text = system_prompt.replace("{{input}}", DOC_PLACEHOLDER).strip()   # same rule as saved prompts
        return self._run(document=document, filename=filename, system_text=system_text,
                         user_text=DEFAULT_USER_TEXT, prompt=None, prompt_version=0,
                         model=model, user_id=user_id, prompt_label="draft")

    # ---- shared: trace + call Claude + judge the answer --------------------------------------------
    def _run(self, *, document, filename, system_text, user_text, prompt, prompt_version,
             model, user_id, prompt_label=None) -> ExtractResponse:
        request_id = "req_" + uuid.uuid4().hex[:12]
        trace_input = {"system": system_text, "user": user_text, "file": document.description}

        with self.langfuse.trace_generation(request_id=request_id, user_id=user_id, model=model,
                                            prompt=prompt, filename=filename) as trace:
            started = time.perf_counter()
            try:
                out = self.claude.extract(model=model, system_text=system_text,
                                          user_text=user_text, document=document)
            except ClaudeCallFailed as e:
                trace.record(input=trace_input, output=None, model=model,
                             input_tokens=0, output_tokens=0, error=str(e))
                self.langfuse.flush()
                raise
            latency_ms = int((time.perf_counter() - started) * 1000)

            status, status_message, keys = _judge_shape(out.parsed, out.text)
            trace.record(
                input=trace_input,
                output=out.parsed if out.parsed is not None else out.text,
                model=model, input_tokens=out.input_tokens, output_tokens=out.output_tokens,
                warning=status_message,
                metadata={"request_id": request_id, "latency_ms": latency_ms,
                          "stop_reason": out.stop_reason, "response_status": status},
            )
        flush_problem = self.langfuse.flush()

        parsed = out.parsed or {}
        fields = InvoiceFields(**{k: _as_text(parsed.get(k)) for k in FIELD_NAMES})
        info = RequestInfo(
            request_id=request_id, user_id=user_id, prompt_name=config.PROMPT_NAME,
            prompt_version=prompt_version, prompt_label=prompt_label, model=model,
            latency_ms=latency_ms,
            input_tokens=out.input_tokens, output_tokens=out.output_tokens,
            total_tokens=out.input_tokens + out.output_tokens,
            trace_id=trace.trace_id, trace_url=trace.trace_url,
            tracing_note=trace.note or flush_problem or self.langfuse.problem,
        )
        return ExtractResponse(status=status, status_message=status_message, keys_returned=keys,
                               fields=fields, raw_output=out.text, info=info)
