"""Tahap 1: ekstraksi baris tarif dari PDF Perbup (PDF teks, tanpa OCR).

Parser generik berbasis baris:
  - baris yang diakhiri satu atau lebih angka harga -> item tarif
  - harga terakhir di baris dianggap TOTAL (kolom komponen diabaikan)
  - baris tanpa harga yang tampak seperti judul -> kategori aktif
  - baris tanpa harga yang diawali nomor -> nama item yang mungkin
    harganya ada di baris berikut (digabung bila baris berikut hanya angka)

Pemakaian:
  python -I pilot/src/extract.py <pdf> <rs_id> <start_page> <out_csv>
"""
import csv
import re
import sys

import pdfplumber

PRICE = r"\d{1,3}(?:[.,]\d{3})+(?:,-|,00)?|\d{4,7}(?:,-)?"
PRICE_RE = re.compile(PRICE)
TRAIL_PRICES = re.compile(rf"((?:\s*(?:Rp\.?\s*)?(?:{PRICE}))+)\s*-?\s*$")
NUMBERING = re.compile(r"^\s*(?:[A-Za-z]\.|\d+(?:\.\d+)*\.?|[ivxIVX]+\.)\s+")
KELAS_ONLY = re.compile(
    r"^(kelas\s*(i{1,3}|utama|1|2|3)|vvip|vip\s*[ab]?|presiden suite|"
    r"vvip\s*/\s*presiden suite|icu|hcu|picu|nicu|semua kelas)$",
    re.I,
)


def fix_numbers(line: str) -> str:
    # "3.750 .000" -> "3.750.000" ; "40\n,\n000" sudah hilang, abaikan
    line = re.sub(r"(\d)\s+([.,]\d{3})", r"\1\2", line)
    return line


def to_int(tok: str) -> int:
    tok = re.sub(r"(,-|,00)$", "", tok)
    return int(re.sub(r"[.,]", "", tok))


def is_header(text: str) -> bool:
    t = text.strip()
    if len(t) < 4 or len(t) > 80:
        return False
    letters = re.sub(r"[^A-Za-z]", "", t)
    if len(letters) < 4:
        return False
    if re.match(r"^(tarif tersebut|tarif \(rp|catatan|keterangan|no\b|jenis pelayanan)", t, re.I):
        return False
    if re.search(r"\d{2,}", t):
        return False
    if re.match(r"^(tarif|paragraf|pelayanan|layanan|tindakan|pemeriksaan)\b", t, re.I):
        return True
    return letters.isupper() and not t.lower().startswith(("no ", "pasal"))


def extract(pdf_path, rs_id, start_page):
    rows = []
    category = ""
    pending_name = None
    with pdfplumber.open(pdf_path) as pdf:
        for pno in range(start_page - 1, len(pdf.pages)):
            text = pdf.pages[pno].extract_text() or ""
            for raw in text.splitlines():
                line = fix_numbers(raw.strip())
                if not line:
                    continue
                m = TRAIL_PRICES.search(line)
                if m:
                    name = line[: m.start()].strip(" :-.")
                    prices = [to_int(t) for t in PRICE_RE.findall(m.group(1))]
                    prices = [p for p in prices if 1_000 <= p <= 200_000_000]
                    if not prices:
                        continue
                    name = NUMBERING.sub("", name).strip(" :-.")
                    if len(re.sub(r"[^A-Za-z]", "", name)) < 3 and pending_name:
                        name = pending_name  # harga di baris terpisah
                    pending_name = None
                    if len(re.sub(r"[^A-Za-z]", "", name)) < 3:
                        continue
                    rows.append(
                        dict(
                            rs=rs_id,
                            page=pno + 1,
                            kategori=category,
                            nama_asli=name,
                            kelas=name if KELAS_ONLY.match(name) else "",
                            harga_total=prices[-1],
                            n_kolom_harga=len(prices),
                            baris_mentah=raw.strip(),
                        )
                    )
                else:
                    body = NUMBERING.sub("", line).strip(" :-.")
                    if is_header(body):
                        category = body[:60]
                        pending_name = None
                    elif NUMBERING.match(line) and len(body) >= 3:
                        pending_name = body
    return rows


if __name__ == "__main__":
    pdf_path, rs_id, start, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    rows = extract(pdf_path, rs_id, start)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{rs_id}: {len(rows)} baris tarif -> {out}")
