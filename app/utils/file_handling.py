"""
Turns an uploaded file into the content block Claude expects.

  image (JPG/PNG) -> Pillow checks/fixes it -> base64 -> {"type": "image", ...}
  PDF             -> sent as-is (Claude reads PDFs natively) -> {"type": "document", ...}
  CSV             -> decoded to text -> {"type": "text", ...}   (tabular data, not pixels)
"""
import base64
import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".csv"}
MAX_IMAGE_SIDE = 2000      # Claude downsizes anything larger anyway; smaller = fewer tokens
MAX_CSV_CHARS = 60_000     # keeps the prompt (and cost) sane; larger files are rejected, not cut


class InvalidDocument(Exception):
    """The uploaded file cannot be used. The message is safe to show to the user."""


@dataclass
class PreparedDocument:
    kind: str                      # "image" | "document" (PDF) | "text" (CSV)
    media_type: str                # e.g. "image/png", "application/pdf", "text/csv"
    filename: str
    size_bytes: int
    data_b64: str = ""             # base64 for images / PDFs
    text: Optional[str] = None     # decoded content for CSV
    rows: int = 0

    def to_claude_block(self) -> dict:
        """The exact content block sent to the Anthropic Messages API."""
        if self.kind == "text":
            return {"type": "text",
                    "text": (f"The invoice below was provided as a CSV file named '{self.filename}'.\n\n"
                             f"<csv_file>\n{self.text}\n</csv_file>")}
        return {"type": self.kind,
                "source": {"type": "base64", "media_type": self.media_type, "data": self.data_b64}}

    @property
    def description(self) -> str:
        """Short text description we store in Langfuse instead of the raw file."""
        if self.kind == "text":
            return f"[csv: {self.filename}, {self.rows} rows]"
        return f"[{self.kind}: {self.filename}, {self.media_type}, {self.size_bytes // 1024} KB]"


def _prepare_csv(filename: str, data: bytes) -> PreparedDocument:
    text = None
    for encoding in ("utf-8-sig", "cp1252"):          # cp1252 = what Excel on Windows often saves
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None or "\x00" in text:
        raise InvalidDocument("This CSV could not be read as text. Save it as UTF-8 CSV and try again.")
    if len(text) > MAX_CSV_CHARS:
        raise InvalidDocument(f"This CSV is too large ({len(text):,} characters; limit {MAX_CSV_CHARS:,}).")
    try:
        rows = sum(1 for row in csv.reader(io.StringIO(text)) if any(c.strip() for c in row))
    except csv.Error:
        raise InvalidDocument("This file does not look like a valid CSV.")
    if rows == 0:
        raise InvalidDocument("The CSV file is empty.")
    return PreparedDocument("text", "text/csv", filename, len(data), text=text, rows=rows)


def prepare_document(filename: str, data: bytes) -> PreparedDocument:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidDocument("Unsupported file type. Please upload a JPG, PNG, PDF or CSV.")
    if not data:
        raise InvalidDocument("The uploaded file is empty.")

    if ext == ".csv":
        return _prepare_csv(filename, data)

    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise InvalidDocument("This file has a .pdf extension but is not a valid PDF.")
        return PreparedDocument("document", "application/pdf", filename, len(data),
                                data_b64=base64.standard_b64encode(data).decode())

    # ---- image ----
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise InvalidDocument("This image could not be read. It may be corrupted.")

    img = ImageOps.exif_transpose(img)            # fix phone photos that are rotated
    if max(img.size) > MAX_IMAGE_SIDE:
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))

    buf = io.BytesIO()
    if ext == ".png":
        img.save(buf, format="PNG")
        media_type = "image/png"
    else:
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        media_type = "image/jpeg"
    out = buf.getvalue()
    return PreparedDocument("image", media_type, filename, len(out),
                            data_b64=base64.standard_b64encode(out).decode())
