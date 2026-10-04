"""
One-time helper: creates the demo prompt versions in Langfuse.

    python -m app.prompts.seed_prompts --up-to 1     # creates v1 only
    python -m app.prompts.seed_prompts --up-to 2     # later: adds v2
    python -m app.prompts.seed_prompts               # everything up to v3
    python -m app.prompts.seed_prompts --reset       # DELETE the old prompt, then recreate v1-v3

In Langfuse, saving a prompt under an existing name creates the NEXT VERSION. So without --reset
this script only adds versions that don't exist yet. Use --reset if you already have older
versions (for example from the first release of this project) and want these new ones as v1-v3.

The three versions are deliberately different in QUALITY. That is the whole demo:

  v1  VAGUE   never says what to extract or in what format        -> plain-text answer, no usable JSON
  v2  LOOSE   names the 5 keys, but no null rule, no formats,     -> JSON, but messy: buyer GSTIN,
              no seller/buyer rule                                   "N/A" strings, "Rs. 18,880.00", odd dates
  v3  STRICT  schema + null rule + field rules + formats +        -> clean, consistent, null when absent
              input-type notes (image / PDF / CSV)

The prompts are CHAT prompts (system + user message). They contain text only; the invoice
image / PDF / CSV is attached by the backend at request time.
"""
import argparse

from langfuse import Langfuse

from app.utils import config

# The user message is identical in every version, so only the SYSTEM prompt changes the behaviour.
USER_MESSAGE = "Please extract the required fields from this invoice."

# ---------------------------------------------------------------------------------------------
# v1 - VAGUE: no field list, no output format.
# ---------------------------------------------------------------------------------------------
V1 = """You are a helpful assistant that works with business documents.
Look at the document the user gives you and tell them what you find."""

# ---------------------------------------------------------------------------------------------
# v2 - LOOSE: asks for JSON with the right keys, but leaves every hard decision to the model.
# ---------------------------------------------------------------------------------------------
V2 = """You are an invoice extraction assistant.
Read the invoice and return the invoice number, vendor name, GSTIN, invoice date and total amount as JSON, using the keys invoice_number, vendor_name, gstin, invoice_date and total_amount."""

# ---------------------------------------------------------------------------------------------
# v3 - STRICT: your baseline prompt + precise field rules and output formats.
# ---------------------------------------------------------------------------------------------
V3 = """You are a precise invoice extraction assistant.

Analyze the provided invoice content carefully. Extract only information that is explicitly visible. Do not infer, guess, or invent missing information.

Return the extracted information strictly in valid JSON format using the keys specified below. If a field is not present or cannot be read, return null. Do not include markdown formatting or wrapper text outside of the JSON object.

JSON Keys to extract:

invoice_number
vendor_name
gstin
invoice_date
total_amount

The input may be a photo or scan, a PDF (possibly several pages: use the invoice itself, ignore terms, bank details and other pages), or CSV text exported from billing software (use the invoice header values and the INVOICE TOTAL row, never a single line item).

Field rules:
- invoice_number: the invoice, bill or receipt number only. Not an order, PO or reference number.
- vendor_name: the business that ISSUED the invoice (the seller), never the buyer or "Bill To" party.
- gstin: the SELLER's GSTIN only. A GSTIN is exactly 15 letters and digits (for example 22AAAAA0000A1Z5). Never return the buyer's GSTIN. Licence numbers (FSSAI), PAN, phone numbers and bank account numbers are NOT GSTINs. If the seller's GSTIN is not printed, return null.
- invoice_date: the date the invoice was issued (not the order or due date), as YYYY-MM-DD. Indian dates are day first: 03/10/2026 means 3 October 2026. Two-digit years mean 20YY.
- total_amount: the final grand total payable for this invoice including all taxes and round-off (not the subtotal, taxable value or any line amount), as digits with two decimals. No currency symbol, no commas. Example: 18880.00

Every value must be a JSON string, or null."""

PROMPTS = [
    ("v1 - vague: no fields, no format", V1),
    ("v2 - loose: keys named, no rules", V2),
    ("v3 - strict: schema, null rule, field rules, formats", V3),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--up-to", type=int, default=len(PROMPTS), choices=range(1, len(PROMPTS) + 1),
                        help="create versions up to this number (default: all)")
    parser.add_argument("--reset", action="store_true",
                        help="delete the existing prompt (all versions) first, then recreate from v1")
    args = parser.parse_args()

    if not (config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY):
        raise SystemExit("Langfuse keys are missing. Fill them in .env first.")

    lf = Langfuse(public_key=config.LANGFUSE_PUBLIC_KEY, secret_key=config.LANGFUSE_SECRET_KEY,
                  base_url=config.LANGFUSE_BASE_URL)

    def current_max_version() -> int:
        page = lf.api.prompts.list(name=config.PROMPT_NAME, limit=50)
        return max((max(m.versions) for m in page.data if m.name == config.PROMPT_NAME and m.versions),
                   default=0)

    try:
        existing = current_max_version()
    except Exception as e:
        raise SystemExit(f"Could not reach Langfuse: {e}")

    if args.reset and existing:
        answer = input(f"This permanently deletes ALL {existing} version(s) of '{config.PROMPT_NAME}'. "
                       f"Existing traces stay, but lose their link to the prompt. Type 'yes' to continue: ")
        if answer.strip().lower() != "yes":
            raise SystemExit("Cancelled. Nothing was changed.")
        try:
            lf.api.prompts.delete(config.PROMPT_NAME)
        except Exception as e:
            raise SystemExit(f"Could not delete the prompt: {e}")
        print(f"Deleted '{config.PROMPT_NAME}'.")
        existing = 0

    if existing >= args.up_to:
        raise SystemExit(f"'{config.PROMPT_NAME}' already has version {existing}. Nothing to do. "
                         f"(To replace old versions with these, run again with --reset.)")

    for i in range(existing, args.up_to):
        label, system_text = PROMPTS[i]
        created = lf.create_prompt(
            name=config.PROMPT_NAME,
            type="chat",
            prompt=[{"role": "system", "content": system_text},
                    {"role": "user", "content": USER_MESSAGE}],
            labels=["production"] if i == args.up_to - 1 else [],   # newest one created = production
            commit_message=label,
        )
        print(f"Created {config.PROMPT_NAME} version {created.version}  ({label})")
    lf.flush()
    lf.shutdown()


if __name__ == "__main__":
    main()
