"""
Regenerates the five FICTIONAL sample documents + ground_truth.json.
You do NOT need to run this; the files are already here.

    pip install reportlab          (Pillow is already in requirements.txt)
    python samples/make_samples.py

Every name, GSTIN, licence number and amount below is made up.
Each sample is built to test something specific (see "tests" in the app's sample picker).

ground_truth.json uses the app's CANONICAL formats: date = YYYY-MM-DD, total = digits with 2 decimals.
"""
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent

FONTS = {
    "sans": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf",
             "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "mono": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/cour.ttf",
             "/System/Library/Fonts/Courier.ttc"],
}


def font(size, kind="sans"):
    for path in FONTS[kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


# --------------------------------------------------------------------------- 1. clean invoice (PNG)
def clean_invoice():
    img = Image.new("RGB", (900, 1180), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 110], fill="#1f3a5f")
    d.text((40, 30), "TAX INVOICE", font=font(44, "bold"), fill="white")
    d.text((560, 45), "SAMPLE - FICTIONAL DATA", font=font(18, "bold"), fill="#ffd166")
    d.text((40, 135), "Sunrise Stationery Pvt Ltd", font=font(28, "bold"), fill="black")
    d.text((40, 175), "12 Demo Street, Sampletown, West Bengal 700000", font=font(18), fill="#333")
    d.text((40, 205), "GSTIN: 19ABCDE1234F1Z5", font=font(20, "bold"), fill="black")
    d.text((540, 135), "Invoice No: INV-2026-0042", font=font(20, "bold"), fill="black")
    d.text((540, 170), "Invoice Date: 15-Sep-2026", font=font(20), fill="black")
    d.text((540, 205), "Order Date: 10-Sep-2026", font=font(18), fill="#555")
    d.text((540, 235), "Due Date: 30-Sep-2026", font=font(18), fill="#555")
    d.text((540, 265), "PO Ref: PO-7781", font=font(18), fill="#555")
    d.text((40, 270), "Bill To:", font=font(20, "bold"), fill="black")
    d.text((40, 300), "Example Buyer Traders", font=font(20), fill="black")
    d.text((40, 328), "Buyer GSTIN: 19PQRST5678K1Z9", font=font(18), fill="#333")
    top, cols = 410, [40, 80, 470, 560, 700]
    d.rectangle([40, top, 860, top + 40], fill="#e8eef7")
    for i, h in enumerate(["#", "Description", "Qty", "Rate (Rs.)", "Amount (Rs.)"]):
        d.text((cols[i] + 8, top + 8), h, font=font(18, "bold"), fill="black")
    y = top + 40
    for r in [("1", "A4 Notebook (pack of 10)", "20", "450.00", "9,000.00"),
              ("2", "Ball Pens (box of 50)", "10", "300.00", "3,000.00"),
              ("3", "Desk Organiser", "5", "800.00", "4,000.00")]:
        d.rectangle([40, y, 860, y + 44], outline="#999")
        for i, c in enumerate(r):
            d.text((cols[i] + 8, y + 11), c, font=font(18), fill="black")
        y += 44
    y += 30
    for label, val, bold in [("Subtotal", "16,000.00", False), ("GST @ 18%", "2,880.00", False),
                             ("TOTAL (Rs.)", "18,880.00", True)]:
        d.text((540, y), label, font=font(22, "bold" if bold else "sans"), fill="black")
        d.text((730, y), val, font=font(22, "bold" if bold else "sans"), fill="black")
        y += 40
    d.text((40, y + 10), "Amount in words: Rupees Eighteen Thousand Eight Hundred Eighty Only",
           font=font(16), fill="#333")
    d.text((40, 1130), "This is a computer-generated sample invoice with fictional data.", font=font(16), fill="#666")
    img.save(OUT / "invoice_clean.png")


# --------------------------------------------------------------------------- 2. scanned invoice (JPG)
def scanned_invoice():
    random.seed(11)
    page = Image.new("RGB", (900, 1150), "#f2eee2")
    d = ImageDraw.Draw(page)
    d.text((450, 40), "KAVERI HARDWARE & TOOLS", font=font(34, "bold"), fill="#222", anchor="mt")
    d.text((450, 88), "45 Workshop Lane, Samplepuram, Tamil Nadu 600001", font=font(18), fill="#333", anchor="mt")
    d.text((450, 118), "GSTIN: 33AAAPK4321L1Z8   |   Ph: 99999 00000", font=font(19, "bold"), fill="#222", anchor="mt")
    d.line([40, 155, 860, 155], fill="#444", width=3)
    d.text((450, 175), "TAX INVOICE", font=font(28, "bold"), fill="#222", anchor="mt")
    d.text((50, 235), "Inv. No.: KHT/26-27/0318", font=font(21, "bold"), fill="#222")
    d.text((560, 235), "Date: 03/10/2026", font=font(21), fill="#222")
    d.text((50, 275), "Place of Supply: Tamil Nadu (33)", font=font(18), fill="#444")
    d.text((50, 330), "Buyer (Bill to):", font=font(19, "bold"), fill="#222")
    d.text((50, 362), "Modern Fabricators", font=font(21), fill="#222")
    d.text((50, 394), "GSTIN/UIN: 33BBBCM9876Q1ZP", font=font(18), fill="#333")
    top, cols = 460, [45, 90, 520, 600, 740]
    d.rectangle([45, top, 860, top + 38], outline="#333", width=2)
    for i, h in enumerate(["Sl", "Particulars", "Qty", "Rate", "Amount"]):
        d.text((cols[i] + 8, top + 8), h, font=font(18, "bold"), fill="#222")
    y = top + 38
    for r in [("1", "Hex bolt set M8", "40", "250.00", "10,000.00"),
              ("2", "Angle grinder 4 inch", "2", "3,500.00", "7,000.00"),
              ("3", "Cutting discs (pack)", "30", "100.00", "3,000.00")]:
        d.rectangle([45, y, 860, y + 42], outline="#555")
        for i, c in enumerate(r):
            d.text((cols[i] + 8, y + 10), c, font=font(18), fill="#222")
        y += 42
    y += 28
    for label, val, bold in [("Taxable value", "20,000.00", False), ("CGST @ 9%", "1,800.00", False),
                             ("SGST @ 9%", "1,800.00", False), ("Grand Total", "23,600.00", True)]:
        d.text((520, y), label, font=font(21, "bold" if bold else "sans"), fill="#222")
        d.text((700, y), val, font=font(21, "bold" if bold else "sans"), fill="#222")
        y += 38
    d.text((50, y + 25), "Rupees Twenty Three Thousand Six Hundred Only", font=font(17), fill="#333")
    d.text((560, 1080), "For Kaveri Hardware & Tools", font=font(17), fill="#333")
    page = page.rotate(-1.8, expand=True, fillcolor="#c9c5ba", resample=Image.BICUBIC)
    px = page.load()
    for _ in range(26000):                                   # scanner speckle
        x, yy = random.randrange(page.width), random.randrange(page.height)
        v = random.randint(110, 200)
        px[x, yy] = (v, v, v)
    page = page.filter(ImageFilter.GaussianBlur(0.7))
    page.save(OUT / "invoice_scanned.jpg", quality=74)


# --------------------------------------------------------------------------- 3. native PDF (2 pages)
def native_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = getSampleStyleSheet()
    right = ParagraphStyle("r", parent=st["Normal"], alignment=2)
    doc = SimpleDocTemplate(str(OUT / "invoice_native.pdf"), pagesize=A4, topMargin=40, bottomMargin=40)
    head = Table([[Paragraph("<b>Lotus Pharma Distributors LLP</b><br/>78 Market Road, Samplenagar, Maharashtra 400001"
                             "<br/>GSTIN: 27AACCL5566M1Z2", st["Normal"]),
                   Paragraph("<b>TAX INVOICE</b><br/>Invoice No.: LPD/2026/00917<br/>Inv. Dt.: 22 September 2026"
                             "<br/>Order Ref: SO-5530", right)]], colWidths=[290, 220])
    buyer = Paragraph("<b>Billed to:</b> Wellness Chemists<br/>GSTIN: 27DDDEF1234G1Z5", st["Normal"])
    rows = [["Item", "Qty", "Rate", "Amount"],
            ["Paracetamol 500mg (strip of 10)", "200", "45.00", "9,000.00"],
            ["Vitamin C 500mg (bottle of 60)", "150", "120.00", "18,000.00"],
            ["ORS sachets (box of 20)", "500", "24.00", "12,000.00"],
            ["", "", "Taxable value", "39,000.00"],
            ["", "", "CGST @ 6%", "2,340.00"],
            ["", "", "SGST @ 6%", "2,340.00"],
            ["", "", "Grand Total (Rs.)", "43,680.00"]]
    t = Table(rows, colWidths=[270, 50, 100, 90])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, 3), 0.6, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                           ("LINEABOVE", (2, 4), (-1, 4), 0.8, colors.black)]))
    page2 = [PageBreak(), Paragraph("<b>Terms &amp; Conditions</b>", st["Heading2"]),
             Paragraph("1. Goods once sold will not be taken back.<br/>2. Payment due within 15 days.<br/>"
                       "3. Subject to Samplenagar jurisdiction.", st["Normal"]), Spacer(1, 14),
             Paragraph("<b>Bank details</b><br/>A/c Name: Lotus Pharma Distributors LLP<br/>A/c No.: 000123456789012"
                       "<br/>IFSC: SAMP0000123<br/>PAN: AACCL5566M", st["Normal"]), Spacer(1, 20),
             Paragraph("<i>Fictional sample document for software testing.</i>", st["Normal"])]
    doc.build([head, Spacer(1, 16), buyer, Spacer(1, 16), t] + page2)


# --------------------------------------------------------------------------- 4. CSV export
def csv_export():
    h = "GO-INV-5521,30/09/2026,Greenfield Organics Pvt Ltd,07AAECG2468H1ZK,Daily Basket Retail,07FFFGH7788J1Z3"
    lines = ["invoice_no,invoice_date,seller,seller_gstin,buyer,buyer_gstin,description,qty,rate,amount",
             f"{h},Cold-pressed mustard oil 5L,50,100.00,5000.00",
             f"{h},Organic jaggery 1kg,300,25.00,7500.00",
             f"{h},Subtotal,,,12500.00",
             f"{h},CGST 2.5%,,,312.50",
             f"{h},SGST 2.5%,,,312.50",
             f"{h},INVOICE TOTAL,,,13125.00"]
    (OUT / "invoice_export.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- 5. retail thermal bill
def retail_bill():
    w = 420
    img = Image.new("RGB", (w, 860), "#fbfbf7")
    d = ImageDraw.Draw(img)
    f, fb = font(19, "mono"), font(19, "mono")
    y = 24

    def center(text, size=19, kind="mono"):
        nonlocal y
        d.text((w // 2, y), text, font=font(size, kind), fill="#111", anchor="mt")
        y += size + 9

    def line(left, right="", kind="mono"):
        nonlocal y
        d.text((22, y), left, font=font(18, kind), fill="#111")
        if right:
            d.text((w - 22, y), right, font=font(18, kind), fill="#111", anchor="ra")
        y += 28

    def rule():
        nonlocal y
        d.text((22, y), "-" * 34, font=f, fill="#555")
        y += 26

    center("SHREE BALAJI", 26, "bold")
    center("SWEETS & SNACKS", 22, "bold")
    center("Station Road, Sampletown", 17)
    center("FSSAI Lic No: 12345678901234", 17)
    rule()
    line("Bill No: 10458")
    line("Date: 03-10-26", "18:42")
    line("Cashier: 02")
    rule()
    line("ITEM        QTY  RATE   AMT")
    line("KAJU KATLI 250G", "280.00")
    line("  1 x 280.00")
    line("SAMOSA", "80.00")
    line("  4 x 20.00")
    line("JALEBI 200G", "90.00")
    line("  1 x 90.00")
    rule()
    line("Sub Total", "450.00")
    line("CGST 2.5%", "11.25")
    line("SGST 2.5%", "11.25")
    rule()
    line("TOTAL Rs.", "472.50", "bold")
    rule()
    center("Thank you! Visit again", 18)
    center("*** FICTIONAL SAMPLE BILL ***", 15)
    img = img.crop((0, 0, w, y + 24)).filter(ImageFilter.GaussianBlur(0.4))
    img.save(OUT / "retail_bill.png")


GROUND_TRUTH = {
    "invoice_clean.png":   {"invoice_number": "INV-2026-0042", "vendor_name": "Sunrise Stationery Pvt Ltd",
                            "gstin": "19ABCDE1234F1Z5", "invoice_date": "2026-09-15", "total_amount": "18880.00"},
    "invoice_scanned.jpg": {"invoice_number": "KHT/26-27/0318", "vendor_name": "Kaveri Hardware & Tools",
                            "gstin": "33AAAPK4321L1Z8", "invoice_date": "2026-10-03", "total_amount": "23600.00"},
    "invoice_native.pdf":  {"invoice_number": "LPD/2026/00917", "vendor_name": "Lotus Pharma Distributors LLP",
                            "gstin": "27AACCL5566M1Z2", "invoice_date": "2026-09-22", "total_amount": "43680.00"},
    "invoice_export.csv":  {"invoice_number": "GO-INV-5521", "vendor_name": "Greenfield Organics Pvt Ltd",
                            "gstin": "07AAECG2468H1ZK", "invoice_date": "2026-09-30", "total_amount": "13125.00"},
    "retail_bill.png":     {"invoice_number": "10458", "vendor_name": "Shree Balaji Sweets & Snacks",
                            "gstin": None, "invoice_date": "2026-10-03", "total_amount": "472.50"},
}

if __name__ == "__main__":
    clean_invoice()
    scanned_invoice()
    native_pdf()
    csv_export()
    retail_bill()
    (OUT / "ground_truth.json").write_text(json.dumps(GROUND_TRUTH, indent=2), encoding="utf-8")
    print("Samples written to", OUT)
