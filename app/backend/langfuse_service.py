"""
Everything Langfuse: prompt retrieval + tracing.  (No Claude code in here.)

PROMPTS : one prompt called "invoice-extractor" with many integer VERSIONS (1, 2, 3 ...).
          We fetch the version the user picked, at request time, so changing a prompt
          in Langfuse needs NO change to this Python code.
TRACING : one trace per request, containing one "generation" (the Claude call).
          Passing the prompt object to the generation LINKS the trace to that prompt
          version, so Langfuse can show per-version latency / tokens / cost.

Rule: prompt retrieval is essential (errors are raised); tracing is optional
(errors are swallowed so a Langfuse hiccup never breaks an extraction).
"""
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from typing import List, Optional

from langfuse import Langfuse, propagate_attributes

from app.utils import config


# Langfuse labels are unique across versions of a prompt, so the version that carries this label
# IS the active one. Moving the label to another version is the rollback.
ACTIVE_LABEL = "production"


def _is_not_found(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404 or "not found" in str(exc).lower()


def _display_name(version: int, commit_message, cfg) -> str:
    """Human-readable name: Prompt Studio stores it in config; older versions use their commit message."""
    if isinstance(cfg, dict) and cfg.get("display_name"):
        return str(cfg["display_name"])
    text = re.sub(rf"^v{version}\s*[-:\u2013\u2014]\s*", "", (commit_message or "").strip(), flags=re.I)
    text = text.split(":", 1)[0].strip()               # "strict: schema, null rule..." -> "strict"
    return (text[:1].upper() + text[1:]) if text else f"Version {version}"


def _system_text(prompt_client) -> str:
    """The raw system message of a prompt version (shown and editable in Prompt Studio)."""
    raw = prompt_client.prompt
    if isinstance(raw, str):                            # a plain text prompt
        return raw
    return "\n\n".join(m.get("content", "") for m in raw
                        if isinstance(m, dict) and m.get("role") == "system"
                        and isinstance(m.get("content"), str))


class LangfuseUnavailable(Exception):
    """Langfuse is not configured or cannot be reached."""


class PromptNotFound(Exception):
    pass


class TraceHandle:
    """Handed to the caller inside the `with` block. Methods never raise."""

    def __init__(self):
        self._generation = None
        self.trace_id: Optional[str] = None
        self.trace_url: Optional[str] = None
        self.note: Optional[str] = None

    def record(self, *, input, output, model, input_tokens, output_tokens,
               error: Optional[str] = None, warning: Optional[str] = None,
               metadata: Optional[dict] = None) -> None:
        if self._generation is None:
            return
        try:
            self._generation.update(
                input=input,
                output=output,
                model=model,
                # Token usage as returned by Claude. We send NO cost: Langfuse infers
                # cost from model + tokens using its built-in Anthropic price list.
                usage_details={"input": input_tokens, "output": output_tokens,
                               "total": input_tokens + output_tokens},
                metadata=metadata or {},
                level="ERROR" if error else ("WARNING" if warning else "DEFAULT"),
                status_message=error or warning,
            )
        except Exception as e:
            self.note = f"Langfuse update failed: {e}"


class LangfuseService:
    def __init__(self):
        self.client: Optional[Langfuse] = None
        self.problem: Optional[str] = None
        if not (config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY):
            self.problem = "Langfuse keys are missing. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env."
            return
        try:
            self.client = Langfuse(public_key=config.LANGFUSE_PUBLIC_KEY,
                                   secret_key=config.LANGFUSE_SECRET_KEY,
                                   base_url=config.LANGFUSE_BASE_URL)
        except Exception as e:
            self.problem = f"Langfuse could not start: {e}"

    def _require(self) -> Langfuse:
        if self.client is None:
            raise LangfuseUnavailable(self.problem or "Langfuse is not configured.")
        return self.client

    # ------------------------------------------------------------------ prompts
    def list_versions(self) -> List[int]:
        """All existing versions of our prompt, newest first (fills the UI dropdown)."""
        client = self._require()
        try:
            page = client.api.prompts.list(name=config.PROMPT_NAME, limit=50)
        except Exception as e:
            raise LangfuseUnavailable(f"Could not reach Langfuse: {e}")
        for meta in page.data:
            if meta.name == config.PROMPT_NAME:
                return sorted(meta.versions, reverse=True)
        return []

    def get_prompt(self, version: int):
        """Fetch one specific version of the chat prompt from Langfuse."""
        client = self._require()
        try:
            # cache_ttl_seconds=0 -> always fetch fresh, so edits show up instantly (nice for demos)
            return client.get_prompt(config.PROMPT_NAME, version=version, type="chat",
                                     cache_ttl_seconds=0, max_retries=1, fetch_timeout_seconds=10)
        except Exception as e:
            if getattr(e, "status_code", None) == 404 or "not found" in str(e).lower():
                raise PromptNotFound(
                    f"Prompt '{config.PROMPT_NAME}' version {version} does not exist in Langfuse. "
                    f"Create it first (see README step A).")
            raise LangfuseUnavailable(f"Could not fetch the prompt from Langfuse: {e}")

    # ------------------------------------------------------------ Prompt Studio helpers
    def get_active_version(self) -> Optional[int]:
        """The version carrying the "production" label, or None if no version is active yet."""
        client = self._require()
        try:
            prompt = client.get_prompt(config.PROMPT_NAME, label=ACTIVE_LABEL, type="chat",
                                       cache_ttl_seconds=0, max_retries=1, fetch_timeout_seconds=10)
        except Exception as e:
            if _is_not_found(e):
                return None
            raise LangfuseUnavailable(f"Could not read the active version from Langfuse: {e}")
        return prompt.version

    def list_prompt_versions(self) -> List[dict]:
        """Every version with its display name, labels and system prompt (newest first)."""
        versions = self.list_versions()
        active = self.get_active_version()

        def load(v: int) -> dict:
            try:
                p = self.get_prompt(v)
                return {"version": v, "name": _display_name(v, p.commit_message, p.config),
                        "commit_message": p.commit_message, "labels": list(p.labels or []),
                        "system_prompt": _system_text(p), "load_error": None}
            except (PromptNotFound, LangfuseUnavailable) as e:
                return {"version": v, "name": f"Version {v}", "commit_message": None, "labels": [],
                        "system_prompt": "", "load_error": str(e)}

        with ThreadPoolExecutor(max_workers=6) as pool:
            items = list(pool.map(load, versions))
        for item in items:
            item["is_active"] = item["version"] == active
        return items

    def next_version_number(self) -> int:
        """Highest existing version + 1, always read from Langfuse (never a local counter)."""
        return max(self.list_versions(), default=0) + 1

    def create_prompt_version(self, name: str, system_prompt: str) -> int:
        """
        Save a NEW version of the prompt. Existing versions are never touched, and the new version
        is NOT made active (use set_active_version for that).
        """
        from app.prompts.seed_prompts import USER_MESSAGE   # same user message as v1-v3
        client = self._require()
        expected = self.next_version_number()
        try:
            created = client.create_prompt(
                name=config.PROMPT_NAME,
                type="chat",
                prompt=[{"role": "system", "content": system_prompt},
                        {"role": "user", "content": USER_MESSAGE}],
                labels=[],                                   # do not steal the active label
                commit_message=name,
                config={"display_name": name, "created_by": "prompt-studio"},
            )
        except Exception as e:
            raise LangfuseUnavailable(f"Could not save the new version to Langfuse: {e}")
        if created.version != expected:                      # e.g. someone saved at the same moment
            print(f"[prompt-studio] expected v{expected} but Langfuse assigned v{created.version}")
        return created.version

    def set_active_version(self, version: int) -> int:
        """Move the "production" label to `version` (rollback = pick an older one). Nothing is deleted."""
        client = self._require()
        if version not in self.list_versions():
            raise PromptNotFound(f"Version {version} does not exist in Langfuse.")
        try:
            client.update_prompt(name=config.PROMPT_NAME, version=version, new_labels=[ACTIVE_LABEL])
        except Exception as e:
            raise LangfuseUnavailable(f"Could not set version {version} active: {e}")
        active = self.get_active_version()                   # read it back to be sure
        if active != version:
            raise LangfuseUnavailable(f"Langfuse did not confirm version {version} as active (it reports {active}).")
        return active

    # ------------------------------------------------------------------ tracing
    @contextmanager
    def trace_generation(self, *, request_id: str, user_id: str, model: str,
                         prompt, filename: str):
        # `prompt` is None for a Prompt Studio draft (not saved in Langfuse yet)
        """Open a trace + generation around the Claude call (timed by Langfuse)."""
        handle = TraceHandle()
        stack = ExitStack()
        if self.client is not None:
            try:
                stack.enter_context(propagate_attributes(
                    user_id=user_id,
                    trace_name="invoice-extraction" if prompt is not None else "prompt-studio-test",
                    tags=[f"{config.PROMPT_NAME}-v{prompt.version}" if prompt is not None else "prompt-studio-draft"],
                    metadata={"request_id": request_id,
                              "prompt_name": config.PROMPT_NAME,
                              "prompt_version": str(prompt.version) if prompt is not None else "draft",
                              "model": model, "filename": filename},
                ))
                handle._generation = stack.enter_context(self.client.start_as_current_observation(
                    as_type="generation",
                    name="claude-invoice-extraction",
                    model=model,
                    **({"prompt": prompt} if prompt is not None else {}),   # links the trace to the prompt version
                ))
                handle.trace_id = self.client.get_current_trace_id()
            except Exception as e:
                handle._generation = None
                handle.note = f"Langfuse tracing could not start: {e}"
        try:
            yield handle
        finally:
            try:
                stack.close()
            except Exception as e:
                handle.note = handle.note or f"Langfuse could not close the trace: {e}"
            if handle.trace_id and self.client is not None:
                try:
                    handle.trace_url = self.client.get_trace_url(trace_id=handle.trace_id)
                except Exception:
                    pass

    def flush(self) -> Optional[str]:
        """Send buffered trace data now (otherwise it goes out in the background)."""
        if self.client is None:
            return None
        try:
            self.client.flush()
        except Exception as e:
            return f"Langfuse flush failed: {e}"
        return None

    def shutdown(self) -> None:
        if self.client is not None:
            try:
                self.client.shutdown()
            except Exception:
                pass
