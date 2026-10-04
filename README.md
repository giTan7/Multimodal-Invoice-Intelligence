# Multimodal Invoice Intelligence

Upload an invoice as an **image, scan, PDF or CSV** → Claude extracts 5 fields → every request is traced in Langfuse.
The point of the project: **the extraction prompt lives in Langfuse, not in the code.** Publish a better prompt
version, pick it in the UI (or run all versions side by side), and watch the behaviour change with **zero code changes**.

```
Streamlit UI ──(file + version + user)──► FastAPI ──► Langfuse (get prompt vN, write trace)
 (no secrets)                               │
                                            └──► Claude API (image / PDF / CSV text + prompt) ──► JSON
```

## 1. Setup (Windows)

Command Prompt or PowerShell, inside this folder. Python 3.10+.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

(Mac/Linux: `source .venv/bin/activate` and `cp .env.example .env`.)

Open `.env` and fill in:

```
ANTHROPIC_API_KEY=sk-ant-...          # console.anthropic.com -> API Keys (needs some credit)
LANGFUSE_PUBLIC_KEY=pk-lf-...         # cloud.langfuse.com -> project -> Settings -> API Keys
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com    # US region: https://us.cloud.langfuse.com
```

Keys are read only by the backend. The Streamlit app never sees them. `.env` is git-ignored.

## 2. Create the prompt versions in Langfuse

```
python -m app.prompts.seed_prompts --reset
```

`--reset` deletes any older `invoice-extractor` prompt (it asks you to type `yes`) and creates the three versions below.
On a fresh Langfuse project plain `python -m app.prompts.seed_prompts` is enough. To create them one at a time
(for a live demo) use `--up-to 1`, later `--up-to 2`, then `--up-to 3`.

| Version | Quality | What the prompt does | What to expect |
|---|---|---|---|
| **v1** | **Vague** | "Look at the document and tell me what you find." No fields, no format. | Plain-text answer. The app has nothing to read, so it shows **Plain text** and the model's own words. |
| **v2** | **Loose** | Names the 5 JSON keys, nothing else. No null rule, no formats, no seller/buyer rule. | JSON, but messy: buyer's GSTIN instead of the seller's, `Rs. 18,880.00`, `15-Sep-2026`, an invented value where the field is absent. |
| **v3** | **Strict** | Your baseline prompt + field rules (seller only, 15-char GSTIN, licence numbers are not GSTINs), date as `YYYY-MM-DD`, total as `18880.00`, null when absent, notes for image / PDF / CSV input. | Clean, consistent output, `null` when a field isn't there. |

The user message ("Please extract the required fields from this invoice.") is identical in all three,
so only the system prompt changes the behaviour.

Important: those expectations describe what these prompts are designed to produce. Real model output can vary
run to run, so the **Compare** table below is the actual evidence, not this README.

## 3. Run

Two terminals, both with the virtual environment activated, both in the project folder.

```
# Terminal 1 - backend
uvicorn app.backend.main:app --reload --port 8000

# Terminal 2 - UI  (opens http://localhost:8501)
streamlit run app/frontend/streamlit_app.py
```

Backend docs: <http://localhost:8000/docs> · health check: <http://localhost:8000/health>

## 4. The demo

In the UI pick **Try a sample**, then click **Compare all 3 versions**. The same document runs through v1, v2 and v3
at once, in a table with the known answer next to it:

* green = correct (a correct `null` counts)
* amber = right value, wrong format (`Rs. 18,880.00` instead of `18880.00`)
* red = wrong, invented, or missing. v1 shows `–` and **0/5**, because a non-answer earns no credit.

Each of the three runs is a separate trace in Langfuse. Then try the other samples. You can also pick one
version and click **Extract with this version**, or upload your own file (JPG, PNG, PDF, CSV; no answer key, so no colours).

### The five samples

All data is fictional. Files are in `samples/`; the answer key is `samples/ground_truth.json`.

| Sample | Input type | What it tests |
|---|---|---|
| Clean invoice | PNG | Two GSTINs and three dates: seller vs buyer, invoice date vs due date |
| Scanned invoice | JPG | Tilted, noisy scan; date `03/10/2026` means 3 October; CGST/SGST lines |
| Invoice PDF | PDF, 2 pages | Page 2 has bank details and a PAN that are not GSTINs |
| Billing export | CSV | Tabular text; the total is in the INVOICE TOTAL row, not a line item |
| Retail bill | PNG | No GSTIN printed (correct answer is `null`), 2-digit year, FSSAI number that looks like an ID |

The answer key uses the app's canonical formats (date `YYYY-MM-DD`, total with 2 decimals).
That is why v2's `15-Sep-2026` is amber: right date, but not in the format the app asks v3 to produce.
(Regenerate the samples with `pip install reportlab` then `python samples/make_samples.py`.)

### Where to look in Langfuse

* **Tracing → Traces**: one `invoice-extraction` trace per run, with user, model, latency, token usage,
  the exact prompt text and the output. Metadata holds `request_id`, `prompt_version`, `filename` and `response_status`.
* **Prompts → invoice-extractor**: each trace is linked to the prompt version it used, so you can compare versions.
* **Cost** is calculated by Langfuse from the token usage and model ID. If it's blank, define the model under Settings → Models.

## 5. Prompt Studio (second page)

The sidebar has two pages: **📄 Invoice Extractor** and **🧪 Prompt Studio**. Same app, same styling, one Streamlit process.

```
WRITE a prompt → TEST it (nothing saved) → SAVE as the next version → SET ACTIVE → use it → ROLLBACK anytime
```

1. **Write.** Give the prompt a human-readable name (e.g. *GST Strict Extraction*) and type the system prompt. "Start from a saved version" copies an existing prompt into the editor.
2. **Test.** Pick a sample and click **Test Prompt**. Your unsaved draft runs on that sample and is shown **side by side with the saved versions** (v1, v2 and v3 by default; you can choose others, but at least 2). Saved versions never change, so their results are reused during your session and only your draft re-runs when you tweak it. Testing creates nothing in Langfuse, so test as often as you like. (Each test run is still traced; draft runs are tagged `prompt-studio-draft`.)
3. **Save as New Version.** The number is assigned automatically: the highest version that exists in Langfuse, plus one (v1-v3 exist, so the first save is **v4**, then v5 and so on). You can't type a number. The name is stored as the version's commit message and `config.display_name`; the Langfuse prompt identifier stays `invoice-extractor`. Saving does **not** make the new version active.
4. **Version history.** Every version is listed newest first, with **🟢 ACTIVE** on the live one. Expand a row to read its prompt.
5. **Set Active / rollback.** Pick any version in the *Active version* dropdown and click **Set Active**. Nothing is deleted. Choosing v3 after v4 is the rollback.

### How "active" is stored

The active version is the one carrying Langfuse's **`production` label**. Langfuse labels are unique across versions of a prompt, so setting one version active moves the label from the previous one automatically. No database or local file is involved, and you can see the same thing in Langfuse under *Prompts → invoice-extractor*.

The **Invoice Extractor** knows the active version too: its dropdown selects it by default (marked 🟢) and the compare table marks it in the header. The dropdown still lists every version, so you can run any of them.

All Prompt Studio Langfuse work (listing, saving, setting active) runs on the backend through the existing `LangfuseService` (`/studio/...` routes), so keys never reach the browser.

## 6. How each input type reaches Claude

| Input | Path | Multimodal? |
|---|---|---|
| JPG / PNG | Pillow fixes rotation and shrinks huge images → base64 → `image` content block | Yes (vision) |
| PDF | Sent unchanged as a native `document` block; Claude reads the text **and** the page visuals | Yes (vision + text) |
| CSV | Decoded to text (UTF-8 or Windows-1252) → text block. Files over ~60,000 characters are rejected | Tabular text, not pixels |

The prompt fetched from Langfuse is text only; the file is never pasted into it. Output is always text (JSON).

## 7. If you see all nulls or an odd result

The app no longer hides a bad answer behind nulls. The **Response** pill and a banner explain what happened:

| Pill | Meaning |
|---|---|
| **Clean JSON** | Valid JSON with all 5 expected keys |
| **Wrong keys** | Valid JSON but the model used different key names (the banner lists the keys it used) |
| **Plain text** | The model didn't return JSON (the prompt never asked for it). The raw answer is shown |

Other causes: the document genuinely lacks a field (v3 returns `null` on purpose); or a prompt you wrote in the Langfuse UI.
The backend fills `{{input}}` with a short phrase, ignores placeholder messages, and accepts text-type prompts,
so those no longer break a run.

## 8. Files

| Layer | File | Job |
|---|---|---|
| UI | `app/frontend/streamlit_app.py` | Presentation only; talks to the backend over HTTP |
| UI | `app/frontend/prompt_studio.py` | The Prompt Studio page (write, test, save, set active) |
| UI | `app/frontend/grading.py` | Colours sample results against the answer key (not an LLM judge) |
| API | `app/backend/main.py` | Routes only (`/extract`, `/studio/versions`, `/studio/test`, `/studio/active`) |
| Orchestration | `app/backend/invoice_service.py` | Connects Langfuse and Claude; judges the response shape |
| Langfuse | `app/backend/langfuse_service.py` | Fetch prompt versions, create traces; create versions, read/set the active (`production`) version |
| Claude | `app/backend/anthropic_service.py` | The multimodal call, JSON parsing |
| Files | `app/utils/file_handling.py` | Validate; image / PDF / CSV preparation |
| Prompts | `app/prompts/seed_prompts.py` | Creates v1 / v2 / v3 in Langfuse (unchanged) |
| Config | `.streamlit/config.toml` | Theme colour only |

## Troubleshooting

| Symptom | Fix |
|---|---|
| UI: "Can't reach the backend" | Start Terminal 1; check `BACKEND_URL` in `.env` |
| "No versions ... exist" | Run `python -m app.prompts.seed_prompts`, then click Refresh versions |
| Old prompt text still showing | Run the seed script with `--reset` |
| Studio says "No version is active yet" | Choose a version in *Active version* and click Set Active |
| Studio save says "Could not save..." | Check the Langfuse keys and region; the message includes Langfuse's reason |
| "Langfuse keys are missing" / 503 | Fill the Langfuse keys; check the region in `LANGFUSE_BASE_URL` |
| "Anthropic rejected the API key" | Check `ANTHROPIC_API_KEY`; restart the backend after editing `.env` |
| CSV rejected | Save as UTF-8 CSV, under ~60,000 characters |
| Trace not visible | Wait ~10 s, refresh, confirm project and region |
