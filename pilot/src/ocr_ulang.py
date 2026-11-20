"""OCR ulang halaman scan yang lapisan teks OCR lamanya rusak (RapidOCR, 200 dpi).

Halaman dipilih bila: ada gambar sehalaman penuh, ada >= 3 angka harga di lapisan teks, dan skor kerusakan teks
(proporsi token satu huruf / simbol aneh / huruf-angka bercampur) > 0,05. Hasil disimpan per file sebagai kotak
teks dalam koordinat PDF (pt), dipakai konverter (to_standard.page_lines) bila versi OCR lebih bersih.

Pemakaian: python -I pilot/src/ocr_ulang.py <folder_pdf> <folder_cache> [proses]
"""
import gzip
import json
import multiprocessing as mp
import os
import re
import sys

PRICE = re.compile(r"\d{1,3}(?:[.,]\d{3})+")


def garble(text):
    toks = re.findall(r"\S+", text)
    if len(toks) < 20:
        return 0.0
    alpha = [t for t in toks if re.search(r"[A-Za-z]", t)]
    single = sum(1 for t in alpha if len(re.sub(r"[^A-Za-z]", "", t)) == 1)
    sym = sum(1 for t in toks if re.search(r"[«»~`^_{}\\]|[a-z][A-Z][a-z]|[A-Za-z]\d[A-Za-z]", t))
    return (single + sym) / len(toks)


def select_pages(path):
    import pymupdf
    doc = pymupdf.open(path)
    out = []
    for i, pg in enumerate(doc):
        area = pg.rect.width * pg.rect.height
        if not any((x["bbox"][2] - x["bbox"][0]) * (x["bbox"][3] - x["bbox"][1]) >= 0.6 * area for x in pg.get_image_info()):
            continue
        t = pg.get_text()
        if len(PRICE.findall(t)) >= 3 and garble(t) > 0.05:
            out.append(i)
    return out


def run_file(args):
    path, cache = args
    out = os.path.join(cache, os.path.basename(path) + ".json.gz")
    if os.path.exists(out):
        return path, -1
    import numpy as np
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR
    pages = select_pages(path)
    res = {}
    if pages:
        ocr = RapidOCR()
        doc = pymupdf.open(path)
        for i in pages:
            # 200 dpi, tapi sisi terpanjang dibatasi 3.500 px (ada scan dengan ukuran halaman salah, mis. 37x56 inci)
            r = doc[i].rect
            z = min(200 / 72, 3500 / max(r.width, r.height))
            pix = doc[i].get_pixmap(matrix=pymupdf.Matrix(z, z))
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
            boxes, _ = ocr(img)
            res[i + 1] = [dict(text=t, score=float(sc), x0=min(p[0] for p in b) / z, x1=max(p[0] for p in b) / z,
                               top=min(p[1] for p in b) / z, bottom=max(p[1] for p in b) / z)
                          for b, t, sc in (boxes or [])]
    with gzip.open(out, "wt", encoding="utf-8") as h:
        json.dump(res, h)
    return path, len(pages)


def main(folder, cache, procs=4):
    os.makedirs(cache, exist_ok=True)
    files = sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".pdf"))
    done = 0
    with mp.Pool(procs) as pool:
        for k, (p, n) in enumerate(pool.imap_unordered(run_file, [(f, cache) for f in files]), 1):
            done += max(n, 0)
            if k % 25 == 0:
                print(f"  {k}/{len(files)} file, {done} halaman di-OCR", flush=True)
    print("selesai", done, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4)
