"""
FastAPI routes ONLY. No business logic here.

Run from the project root:   uvicorn app.backend.main:app --reload --port 8000
Interactive docs:            http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.backend.anthropic_service import AnthropicService, ClaudeCallFailed
from app.backend.invoice_service import InvoiceService
from app.backend.langfuse_service import LangfuseService, LangfuseUnavailable, PromptNotFound
from app.backend.schemas import (CreateVersionRequest, CreateVersionResponse, ExtractResponse,
                                 PromptVersionInfo, SetActiveRequest, SetActiveResponse,
                                 StudioVersionsResponse, VersionsResponse)
from app.utils import config
from app.utils.file_handling import InvalidDocument

services = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    langfuse, claude = LangfuseService(), AnthropicService()
    services.update(langfuse=langfuse, claude=claude, invoice=InvoiceService(langfuse, claude))
    yield
    langfuse.shutdown()          # final flush so no trace is lost on shutdown


app = FastAPI(title="Indian Invoice Intelligence API", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "anthropic_configured": services["claude"].configured,
        "langfuse_configured": services["langfuse"].client is not None,
        "langfuse_problem": services["langfuse"].problem,
        "models": config.MODELS,
    }


@app.get("/prompts/versions", response_model=VersionsResponse)
def prompt_versions():
    try:
        versions = services["langfuse"].list_versions()
    except LangfuseUnavailable as e:
        raise HTTPException(503, str(e))
    try:
        active = services["langfuse"].get_active_version()
    except LangfuseUnavailable:
        active = None                       # knowing the active version is nice-to-have here
    return VersionsResponse(prompt_name=config.PROMPT_NAME, versions=versions, active_version=active)


@app.post("/extract", response_model=ExtractResponse)
def extract(file: UploadFile = File(...),
            prompt_version: int = Form(...),
            model_label: str = Form(config.DEFAULT_MODEL_LABEL),
            user_id: str = Form("demo_user")):
    model = config.MODELS.get(model_label)
    if model is None:
        raise HTTPException(400, f"Unknown model '{model_label}'.")
    user_id = (user_id or "demo_user").strip()[:100]

    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD_MB} MB.")

    try:
        return services["invoice"].extract(filename=file.filename or "upload", data=data,
                                           version=prompt_version, model=model, user_id=user_id)
    except InvalidDocument as e:
        raise HTTPException(400, str(e))
    except PromptNotFound as e:
        raise HTTPException(404, str(e))
    except LangfuseUnavailable as e:
        raise HTTPException(503, str(e))
    except ClaudeCallFailed as e:
        raise HTTPException(e.status, str(e))


# =============================================================================================
# Prompt Studio routes (additive: nothing above this line behaves differently)
# =============================================================================================
MAX_PROMPT_CHARS = 20_000


@app.get("/studio/versions", response_model=StudioVersionsResponse)
def studio_versions():
    """All versions (newest first) with names, labels, system prompts, the active one and the next number."""
    lf = services["langfuse"]
    try:
        items = lf.list_prompt_versions()
        return StudioVersionsResponse(
            prompt_name=config.PROMPT_NAME,
            versions=[PromptVersionInfo(**i) for i in items],
            active_version=next((i["version"] for i in items if i["is_active"]), None),
            next_version=lf.next_version_number())
    except LangfuseUnavailable as e:
        raise HTTPException(503, str(e))


@app.post("/studio/versions", response_model=CreateVersionResponse)
def studio_create_version(body: CreateVersionRequest):
    """Save a new version. The number is chosen from Langfuse's existing versions, never by the caller."""
    name, system_prompt = body.name.strip(), body.system_prompt.strip()
    if not name:
        raise HTTPException(400, "Prompt name is required.")
    if len(name) > 100:
        raise HTTPException(400, "Prompt name must be 100 characters or fewer.")
    if not system_prompt:
        raise HTTPException(400, "System prompt is required.")
    if len(system_prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(400, f"System prompt is too long (limit {MAX_PROMPT_CHARS:,} characters).")
    try:
        version = services["langfuse"].create_prompt_version(name, system_prompt)
    except LangfuseUnavailable as e:
        raise HTTPException(503, str(e))
    return CreateVersionResponse(version=version, name=name)


@app.put("/studio/active", response_model=SetActiveResponse)
def studio_set_active(body: SetActiveRequest):
    """Make `version` the active one (rollback = choose an older version). Nothing is deleted."""
    try:
        return SetActiveResponse(active_version=services["langfuse"].set_active_version(body.version))
    except PromptNotFound as e:
        raise HTTPException(404, str(e))
    except LangfuseUnavailable as e:
        raise HTTPException(503, str(e))


@app.post("/studio/test", response_model=ExtractResponse)
def studio_test(file: UploadFile = File(...),
                system_prompt: str = Form(...),
                model_label: str = Form(config.DEFAULT_MODEL_LABEL),
                user_id: str = Form("prompt-studio")):
    """Run an UNSAVED draft prompt on a document. Creates no Langfuse prompt version."""
    model = config.MODELS.get(model_label)
    if model is None:
        raise HTTPException(400, f"Unknown model '{model_label}'.")
    if not system_prompt.strip():
        raise HTTPException(400, "System prompt is required.")
    if len(system_prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(400, f"System prompt is too long (limit {MAX_PROMPT_CHARS:,} characters).")
    user_id = (user_id or "prompt-studio").strip()[:100]

    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD_MB} MB.")
    try:
        return services["invoice"].test_draft(filename=file.filename or "upload", data=data,
                                              system_prompt=system_prompt, model=model, user_id=user_id)
    except InvalidDocument as e:
        raise HTTPException(400, str(e))
    except ClaudeCallFailed as e:
        raise HTTPException(e.status, str(e))
