"""Shapes of the data that the API returns (FastAPI also uses these for /docs)."""
from typing import List, Optional

from pydantic import BaseModel


class InvoiceFields(BaseModel):
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    gstin: Optional[str] = None
    invoice_date: Optional[str] = None
    total_amount: Optional[str] = None


class RequestInfo(BaseModel):
    request_id: str
    user_id: str
    prompt_name: str
    prompt_version: int
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    trace_id: Optional[str] = None
    trace_url: Optional[str] = None
    tracing_note: Optional[str] = None   # set if Langfuse had a problem (extraction still worked)
    prompt_label: Optional[str] = None   # "draft" for Prompt Studio tests (prompt_version is 0 then)


class ExtractResponse(BaseModel):
    # "ok"         = valid JSON with all 5 expected keys
    # "off_schema" = valid JSON, but some expected keys are missing (prompt didn't pin the keys)
    # "not_json"   = the model answered in plain text (prompt didn't ask for JSON)
    status: str
    status_message: Optional[str] = None
    keys_returned: List[str] = []
    fields: InvoiceFields
    raw_output: str
    info: RequestInfo


class VersionsResponse(BaseModel):
    prompt_name: str
    versions: List[int]
    active_version: Optional[int] = None     # the version carrying the "production" label in Langfuse


# ---------------------------------------------------------------- Prompt Studio
class PromptVersionInfo(BaseModel):
    version: int
    name: str                      # human-readable display name
    commit_message: Optional[str] = None
    labels: List[str] = []
    is_active: bool = False
    system_prompt: str = ""
    load_error: Optional[str] = None


class StudioVersionsResponse(BaseModel):
    prompt_name: str
    versions: List[PromptVersionInfo]    # newest first
    active_version: Optional[int] = None
    next_version: int                    # what the next save will be (highest existing + 1)


class CreateVersionRequest(BaseModel):
    name: str
    system_prompt: str


class CreateVersionResponse(BaseModel):
    version: int
    name: str


class SetActiveRequest(BaseModel):
    version: int


class SetActiveResponse(BaseModel):
    active_version: int
