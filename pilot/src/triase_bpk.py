"""Triase dataset BPK: ukur setiap file supaya bisa dipilah menjadi buku tarif vs bukan,
lalu PDF teks vs scan. Langkah ini hanya MENGUKUR (tidak memindahkan file).

Untuk tiap PDF:
  - hal_teks  : halaman dengan >= 200 karakter teks
  - hal_scan  : halaman dengan < 50 karakter teks tetapi berisi gambar
  - item_teks : baris "nama layanan ... harga" di lapisan teks
  - med_teks  : bagian dari item_teks yang memuat istilah layanan medis
  - bila lapisan teks kurang (< 50% halaman), OCR 3 halaman contoh dari 60% bagian belakang
    dokumen dengan RapidOCR, lalu hitung item_ocr dan med_ocr

Pemakaian: python -I pilot/src/triase_bpk.py <folder_bpk> <keluaran.csv> [jumlah_proses]
"""
import csv
import multiprocessing as mp
import os
import re
import sys
import time

PRICE = r"\d{1,3}(?:[.,]\d{3})+(?:,-|,00)?"
ITEM = re.compile(rf"[A-Za-z]{{3,}}.*?(?:Rp\.?\s*)?({PRICE})\s*,?-?\s*$")
MED = re.compile(
    r"pemeriksaan|tindakan|rawat|kelas|operasi|bedah|laborat|darah|urin|foto|rontgen|thorax|usg|ct.?scan|ekg|"
    r"konsul|visite|kamar|persalinan|partus|gigi|kateter|infus|injeksi|jahit|luka|biopsi|ekstraksi|terapi|fisio|"
    r"poli|igd|icu|dokter|perawat|ambulan|jenazah|hecting|kultur|\btes\b|test|gula|kolesterol|hb\b|sgot|sgpt|"
    r"ureum|kreatinin|widal|hematologi|radiologi|anestesi|kuret|sirkumsisi|khitan|nebul|oksigen|ventilator|"
    r"vip|utama|perinatologi|isolasi|mcu|check up|visum|rehab|akupunktur|hemodialisa|endoskopi|cito", re.I)


def count_items(lines):
    items = [l for l in lines if ITEM.search(l)]
    vals = []
    for l in items:
        v = int(re.sub(r"[.,]|,-|,00$", "", ITEM.search(l).group(1)).replace("-", "") or 0)
        vals.append(v)
    items = [l for l, v in zip(items, vals) if v >= 1000]
    med = sum(1 for l in items if MED.search(l))
    return len(items), med


def ocr_lines(page, engine):
    import numpy as np
    pix = page.get_pixmap(dpi=150, colorspace="gray")
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    res, _ = engine(img)
    if not res:
        return []
    boxes = []
    for box, text, _score in res:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), text))
    boxes.sort()
    lines, cur, cy = [], [], None
    for yc, h, x, text in boxes:
        if cy is None or abs(yc - cy) <= max(6, h * 0.6):
            cur.append((x, text))
            cy = yc if cy is None else (cy + yc) / 2
        else:
            lines.append(" ".join(t for _, t in sorted(cur)))
            cur, cy = [(x, text)], yc
    if cur:
        lines.append(" ".join(t for _, t in sorted(cur)))
    return lines


def page_lines(page):
    """Susun ulang baris dari posisi kata (PyMuPDF memecah sel tabel menjadi baris terpisah)."""
    words = page.get_text("words")
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, cy = [], [], None
    for w in words:
        yc, h = (w[1] + w[3]) / 2, w[3] - w[1]
        if cy is None or abs(yc - cy) <= max(2.5, h * 0.45):
            cur.append((w[0], w[4]))
            cy = yc if cy is None else cy
        else:
            lines.append(" ".join(t for _, t in sorted(cur)))
            cur, cy = [(w[0], w[4])], yc
    if cur:
        lines.append(" ".join(t for _, t in sorted(cur)))
    return lines


NONMED = re.compile(r"praktik|praktek|magang|penelitian|studi banding|mahasiswa|peserta|siswa|\bsma\b|\bd-?iii\b|\bs1\b|"
                    r"sederajat|sewa|parkir|kendaraan|motor|mobil pribadi|kantin|aula|gedung|listrik|pelatihan|diklat|"
                    r"institusi|pendidikan|kost|asrama|narasumber|bimbingan", re.I)
CLEAN_WORD = re.compile(r"^[A-Za-z][a-z]{2,}[.,:)]?$|^[A-Z]{2,}[.,:)]?$|^\(?[A-Za-z][a-z]+\)?$")


def text_quality(path):
    """Mutu lapisan teks pada baris item: persen kata wajar di bagian nama, dan persen baris non-medis."""
    import pymupdf
    doc = pymupdf.open(path)
    items = []
    for page in doc:
        if len((page.get_text() or "").strip()) >= 50:
            items += [l for l in page_lines(page) if ITEM.search(l)]
    if not items:
        return 0.0, 0.0, 0
    good = tot = 0
    for l in items:
        name = re.split(r"(?:Rp\.?\s*)?\d{1,3}(?:[.,]\d{3})", l)[0]
        for w in name.split():
            if re.search(r"[A-Za-z]", w):
                tot += 1
                good += bool(CLEAN_WORD.match(w))
    nonmed = sum(1 for l in items if NONMED.search(l)) / len(items)
    return (good / tot if tot else 0.0), nonmed, len(items)


NOSEP = re.compile(r"[A-Za-z]{3,}.*?(?<![\d.,])(\d{4,7})(?:,-|,00)?\s*$")
NOT_PRICE_LINE = re.compile(r"tahun|nomor|nip\b|no\.|pasal|lembaran|tambahan|kode pos|tanggal|januari|februari|maret|april|"
                            r"mei|juni|juli|agustus|september|oktober|nopember|november|desember", re.I)


def count_nosep(path):
    """Baris item dengan harga tanpa titik ribuan (mis. 'Akomodasi 126000 189000'), tanpa baris tanggal/nomor."""
    import pymupdf
    n = 0
    for page in pymupdf.open(path):
        if len((page.get_text() or "").strip()) < 50:
            continue
        for l in page_lines(page):
            m = NOSEP.search(l)
            if m and 1000 <= int(m.group(1)) <= 50_000_000 and not NOT_PRICE_LINE.search(l):
                n += 1
    return n


_ENGINE = None


def measure(path, force_ocr=False):
    global _ENGINE
    import pymupdf
    t0 = time.time()
    name = os.path.basename(path)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    out = dict(file=name, ext=ext, hal=0, hal_teks=0, hal_scan=0, item_teks=0, med_teks=0,
               hal_ocr=0, item_ocr=0, med_ocr=0, error="", detik=0)
    if ext != "pdf":
        out["error"] = "bukan_pdf"
        return out
    try:
        doc = pymupdf.open(path)
        out["hal"] = doc.page_count
        lines, scan_pages = [], []
        for i, page in enumerate(doc):
            txt = page.get_text() or ""
            n = len(txt.strip())
            if n >= 200:
                out["hal_teks"] += 1
            elif n < 50 and page.get_images():
                out["hal_scan"] += 1
                scan_pages.append(i)
            if n >= 50:
                lines += page_lines(page)
        out["item_teks"], out["med_teks"] = count_items(lines)
        need = out["hal"] and (out["hal_teks"] / out["hal"] < 0.5 or (out["item_teks"] < 10 and len(scan_pages) >= 2))
        if scan_pages and (need or force_ocr):
            if _ENGINE is None:
                from rapidocr_onnxruntime import RapidOCR
                _ENGINE = RapidOCR()
            back = [p for p in scan_pages if p >= int(out["hal"] * 0.4)] or scan_pages
            pick = sorted(set(back[int(k * (len(back) - 1) / 2)] for k in range(3))) if len(back) > 2 else back
            olines = []
            for p in pick:
                olines += ocr_lines(doc[p], _ENGINE)
            out["hal_ocr"] = len(pick)
            out["item_ocr"], out["med_ocr"] = count_items(olines)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {str(e)[:80]}"
    out["detik"] = round(time.time() - t0, 1)
    return out


def main(folder, out_csv, procs=4):
    files = sorted(os.path.join(folder, f) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)))
    files = [f for f in files if not f.lower().endswith(".csv") and not f.lower().endswith(".txt")]
    done = set()
    if os.path.exists(out_csv):
        with open(out_csv, encoding="utf-8") as h:
            done = {r["file"] for r in csv.DictReader(h)}
    todo = [f for f in files if os.path.basename(f) not in done]
    print(f"{len(files)} file, {len(done)} sudah diukur, {len(todo)} diproses", flush=True)
    fields = list(measure.__defaults__ or []) or None
    new = not os.path.exists(out_csv)
    with open(out_csv, "a", newline="", encoding="utf-8") as h, mp.Pool(procs) as pool:
        w = None
        for k, r in enumerate(pool.imap_unordered(measure, todo, chunksize=2), 1):
            if w is None:
                w = csv.DictWriter(h, fieldnames=list(r.keys()))
                if new:
                    w.writeheader()
            w.writerow(r)
            h.flush()
            if k % 25 == 0:
                print(f"  {k}/{len(todo)}", flush=True)
    print("selesai", flush=True)


def _forced(path):
    return measure(path, force_ocr=True)


def ocr_pass(folder, in_csv, out_csv, procs=4):
    """Putaran kedua: OCR untuk file berlampiran scan yang belum di-OCR di putaran pertama."""
    with open(in_csv, encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    todo = [os.path.join(folder, r["file"]) for r in rows
            if r["ext"] == "pdf" and int(r["hal_ocr"] or 0) == 0 and int(r["hal_scan"] or 0) >= 2 and int(r["item_teks"] or 0) < 10]
    print(f"OCR putaran kedua: {len(todo)} file", flush=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as h, mp.Pool(procs) as pool:
        w = None
        for k, r in enumerate(pool.imap_unordered(_forced, todo), 1):
            if w is None:
                w = csv.DictWriter(h, fieldnames=list(r.keys()))
                w.writeheader()
            w.writerow(r)
            h.flush()
            if k % 10 == 0:
                print(f"  {k}/{len(todo)}", flush=True)
    print("selesai", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "--ocr-pass":
        ocr_pass(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]) if len(sys.argv) > 5 else 4)
    else:
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4)
