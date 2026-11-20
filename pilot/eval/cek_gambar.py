"""Pemakaian: python -I pilot/eval/cek_gambar.py pilot/out/dataset/tarif.csv.gz 40 <seed> <folder_keluaran>

Sampel acak baris dataset + potongan gambar halaman PDF di sekitar baris itu (untuk cek visual)."""
import glob
import os
import sys

import pandas as pd
import pdfplumber
from PIL import Image, ImageDraw

sys.path.insert(0, "pilot/src")
from to_standard import page_text, page_lines, load_ocr, lines_from_words  # noqa: E402

src, n, seed, outdir = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
os.makedirs(outdir, exist_ok=True)
T = pd.read_csv(src, low_memory=False)
s = T.sample(n, random_state=seed).reset_index(drop=True)
crops, info = [], []
for i, r in s.iterrows():
    f = glob.glob("bpk_v3/buku_tarif/teks/" + glob.escape(r.file))[0]
    same = T[(T.file == r.file) & (T.halaman == r.halaman) & (T.baris_mentah == r.baris_mentah)]
    with pdfplumber.open(f) as pdf:
        pg = pdf.pages[int(r.halaman) - 1]
        ocr = getattr(r, "metode_ekstraksi", "") == "ocr_ulang"
        if ocr:
            ow = load_ocr(f).get(int(r.halaman), [])
            PL = lines_from_words([w for w in ow if w.get("score", 1) >= 0.5])
        else:
            PL = page_lines(pg)
        L = [t for t, _ in PL]
        j = next((k for k, l in enumerate(L) if l.strip() == str(r.baris_mentah).strip()), None)
        hits = []
        if j is not None and PL[j][1]:
            hits = [dict(top=min(w["top"] for w in PL[j][1]), bottom=max(w["bottom"] for w in PL[j][1]))]
        for key in ([] if hits else [str(r.baris_mentah).strip()[:40], str(r.baris_mentah).strip()[-25:]]):
            try:
                hits = pg.search(key, regex=False)
            except Exception:  # noqa: BLE001
                hits = []
            if hits:
                break
        if hits:
            y0, y1 = hits[0]["top"], hits[0]["bottom"]
            x0b, y0b, x1b, y1b = pg.bbox
            box = (x0b, max(y0b, y0 - 70), x1b, min(y1b, y1 + 6))
            try:
                im = pg.crop(box).to_image(resolution=100).original.convert("RGB")
            except Exception:  # noqa: BLE001  halaman gagal dirender
                im = Image.new("RGB", (int(pg.width * 100 / 72), 40), "white")
        else:
            im = Image.new("RGB", (int(pg.width * 100 / 72), 40), "white")
    lab = f"#{i + 1} {r.dokumen_id} hlm {r.halaman}" + (" [OCR]" if ocr else "")
    canvas = Image.new("RGB", (im.width, im.height + 18), "white")
    canvas.paste(im, (0, 18))
    ImageDraw.Draw(canvas).text((4, 2), lab, fill="red")
    crops.append(canvas)
    info.append(f"\n#{i + 1} {r.dokumen_id} hlm {r.halaman}  [{'' if hits else 'POSISI TIDAK KETEMU'}]\n"
                f"   DATASET: nama={r.nama_asli!r} kelas={r.kelas!r} varian={getattr(r, 'varian', '')!r} komponen={getattr(r, 'komponen', '')!r} harga={r.harga:,.0f} flag={r.flag_qc} verif={r.verifikasi_harga}\n"
                f"   baris yg sama -> {list(zip(same.kelas, same.get('varian', same.kelas).fillna(''), same.komponen, same.harga.map(lambda h: f'{h:,.0f}')))[:8]}\n"
                + ("".join(f"     | {l[:140]}\n" for l in L[max(0, j - 6):j]) + f"   >>| {L[j][:140]}" if j is not None else
                   f"   (baris teks tak ketemu) {str(r.baris_mentah)[:140]}"))
# lembar kontak per 5 potongan
for k in range(0, len(crops), 5):
    group = crops[k:k + 5]
    W = max(c.width for c in group)
    H = sum(c.height for c in group) + 6 * len(group)
    sheet = Image.new("RGB", (W, H), "white")
    y = 0
    for c in group:
        sheet.paste(c, (0, y))
        y += c.height + 6
    sheet.save(os.path.join(outdir, f"sheet_{k // 5 + 1:02d}.png"))
open(os.path.join(outdir, "info.txt"), "w").write("\n".join(info))
print("ok", len(crops))
