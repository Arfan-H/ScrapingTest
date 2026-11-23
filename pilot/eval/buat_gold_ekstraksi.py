"""Buat bahan gold set ekstraksi (dinilai manusia): pilot/eval/gold/gold_ekstraksi_v1.xlsx

Desain:
- Dokumen yang pernah disentuh saat pengembangan parser dikecualikan (sampel cek visual v3-v10, dokumen yang ditelusuri
  saat debugging, dokumen pilot) -> gold/dokumen_dikecualikan.csv.
- Sampel diambil PER DOKUMEN, bertingkat 2x2: sumber teks (lapisan teks PDF vs OCR ulang) x bentuk tabel
  (harga per kelas vs satu harga). Tiap strata dibagi rata ke bagian 'dev' (boleh dipakai memperbaiki parser) dan
  'test' (hanya untuk mengukur akurasi akhir) di tingkat dokumen.
- Dari tiap dokumen diambil N baris acak (termasuk baris bertanda masalah) supaya akurasi keseluruhan bisa diukur.
- Penilai TIDAK diberi flag_qc / split, agar tidak terpengaruh; keduanya ada di gold/gold_ekstraksi_v1_manifest.csv.

Pemakaian: python -I pilot/eval/buat_gold_ekstraksi.py [jumlah_dokumen_per_strata=10] [baris_per_dokumen=8]
"""
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import pdfplumber
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from to_standard import lines_from_words, load_ocr, page_lines  # noqa: E402

OUT = os.path.join(HERE, "gold")
IMG = os.path.join(OUT, "gambar")
PDF_DIR = os.path.join(ROOT, "bpk_v3", "buku_tarif", "teks")
SEED = 20261123
PARSER_COMMIT = "cb968f4"
TRANSCRIPT_DOCS = os.path.join(OUT, "dokumen_debugging.txt")  # dokumen yang ditelusuri saat debugging (daftar tetap)


def excluded_docs(doc_ids):
    rows = []
    for g in sorted(glob.glob(os.path.join(HERE, "cek_manual_40_v*.csv"))):
        for d in pd.read_csv(g).dokumen_id.unique():
            rows.append((d, f"sampel cek visual {os.path.basename(g)}"))
    if os.path.exists(TRANSCRIPT_DOCS):
        for d in open(TRANSCRIPT_DOCS, encoding="utf-8").read().split():
            rows.append((d, "ditelusuri saat debugging parser"))
    pilot = pd.read_csv(os.path.join(ROOT, "pilot", "config", "dokumen.csv")).dokumen_id
    for d in pilot:
        rows.append((d, "dokumen pilot"))
    E = pd.DataFrame(rows, columns=["dokumen_id", "alasan"])
    E = E[E.dokumen_id.isin(doc_ids)].groupby("dokumen_id").alasan.apply(lambda s: "; ".join(dict.fromkeys(s))).reset_index()
    return E


def crop(pdf_path, page_no, raw, ocr):
    """Potongan halaman di sekitar baris (lebar penuh), atau None bila baris tidak ketemu."""
    with pdfplumber.open(pdf_path) as pdf:
        pg = pdf.pages[page_no - 1]
        if ocr:
            ow = load_ocr(pdf_path).get(page_no, [])
            PL = lines_from_words([w for w in ow if w.get("score", 1) >= 0.5])
        else:
            PL = page_lines(pg)
        j = next((k for k, (t, _) in enumerate(PL) if t.strip() == str(raw).strip()), None)
        if j is None or not PL[j][1]:
            return None
        y0 = min(w["top"] for w in PL[j][1])
        y1 = max(w["bottom"] for w in PL[j][1])
        x0b, y0b, x1b, y1b = pg.bbox
        ctx = max(90, 0.22 * (y1b - y0b))  # konteks di atas baris: judul kolom sering ikut terlihat
        top, bot = max(y0b, y0 - ctx), min(y1b, y1 + 35)
        near = [w for _, ws in PL for w in ws if w["bottom"] >= top and w["top"] <= bot] or PL[j][1]
        box = (max(x0b, min(w["x0"] for w in near) - 15), top, min(x1b, max(w["x1"] for w in near) + 15), bot)
        try:
            im = pg.crop(box).to_image(resolution=110).original.convert("RGB")
        except Exception:  # noqa: BLE001
            return None
        # tandai baris yang dinilai dengan garis merah di kiri
        d = ImageDraw.Draw(im)
        sy = im.height / (box[3] - box[1])
        d.rectangle([0, (y0 - box[1]) * sy - 2, 7, (y1 - box[1]) * sy + 2], fill="red")
        d.rectangle([0, (y0 - box[1]) * sy - 2, im.width - 1, (y1 - box[1]) * sy + 2], outline="red", width=2)
        return im


def main(per_strata=10, per_doc=8):
    os.makedirs(IMG, exist_ok=True)
    T = pd.read_csv(os.path.join(ROOT, "pilot", "out", "dataset", "tarif.csv.gz"), low_memory=False)
    D = pd.read_csv(os.path.join(ROOT, "pilot", "out", "dataset", "dokumen.csv"))
    E = excluded_docs(set(D.dokumen_id))
    E.to_csv(os.path.join(OUT, "dokumen_dikecualikan.csv"), index=False)

    g = T.groupby("dokumen_id")
    S = pd.DataFrame({"n": g.size(), "ocr": g.metode_ekstraksi.apply(lambda s: (s == "ocr_ulang").mean()),
                      "kelas": g.flag_qc.apply(lambda s: s.str.contains("dari_kolom_kelas").mean())}).reset_index()
    S = S[(S.n >= 20) & ~S.dokumen_id.isin(E.dokumen_id)]
    S["sumber"] = np.where(S.ocr > 0.5, "ocr_ulang", "teks_pdf")
    S["bentuk"] = np.where(S.kelas > 0.3, "per_kelas", "satu_harga")
    rng = np.random.default_rng(SEED)
    pick = []
    for (sb, bt), grp in S.groupby(["sumber", "bentuk"]):
        k = min(per_strata, len(grp))
        sel = grp.iloc[rng.permutation(len(grp))[:k]].copy()
        sel["split"] = ["dev" if i % 2 == 0 else "test" for i in range(k)]
        pick.append(sel)
    P = pd.concat(pick)
    print("dokumen eligible:", len(S), "| terpilih:", len(P), P.groupby(["sumber", "bentuk"]).size().to_dict())

    rows = []
    for r in P.itertuples():
        x = T[T.dokumen_id == r.dokumen_id]
        cand = x.iloc[rng.permutation(len(x))]
        got = 0
        for c in cand.itertuples():
            if got >= per_doc:
                break
            f = os.path.join(PDF_DIR, c.file)
            if not os.path.exists(f):
                continue
            im = crop(f, int(c.halaman), c.baris_mentah, c.metode_ekstraksi == "ocr_ulang")
            if im is None:
                continue
            gid = f"G{len(rows) + 1:04d}"
            if im.width > 900:
                im = im.resize((900, int(im.height * 900 / im.width)))
            im.save(os.path.join(IMG, f"{gid}.jpg"), quality=72, optimize=True)
            rows.append(dict(id_gold=gid, split=r.split, strata=f"{r.sumber}/{r.bentuk}", tarif_id=c.tarif_id,
                             dokumen_id=c.dokumen_id, file=c.file, halaman=int(c.halaman), baris_mentah=c.baris_mentah,
                             nama_asli=c.nama_asli, kelas=c.kelas, varian="" if pd.isna(c.varian) else c.varian,
                             komponen=c.komponen, harga=int(c.harga), flag_qc=c.flag_qc, qc_masalah=bool(c.qc_masalah),
                             metode_ekstraksi=c.metode_ekstraksi, img_h=im.height, img_w=im.width))
            got += 1
    M = pd.DataFrame(rows)
    M.drop(columns=["img_h", "img_w"]).assign(versi_parser=PARSER_COMMIT).to_csv(
        os.path.join(OUT, "gold_ekstraksi_v1_manifest.csv"), index=False)
    print("baris gold:", len(M), M.split.value_counts().to_dict())

    # ---- workbook untuk penilai ---------------------------------------------------------------------------------
    wb = Workbook()
    ws = wb.active
    ws.title = "nilai"
    head = ["no", "id_gold", "dokumen_id", "halaman", "gambar halaman PDF (baris bertanda merah)", "nama di data",
            "kelas di data", "varian di data", "komponen di data", "harga di data",
            "NAMA benar?", "nama seharusnya", "KELAS benar?", "kelas seharusnya", "VARIAN/KOMPONEN benar?",
            "seharusnya", "HARGA benar?", "harga seharusnya", "catatan"]
    ws.append(head)
    fill_in = PatternFill("solid", fgColor="FFF2CC")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    widths = [5, 8, 26, 7, 105, 34, 12, 12, 12, 12, 11, 30, 11, 16, 13, 18, 11, 16, 30]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    dv = DataValidation(type="list", formula1='"Ya,Tidak,Tidak bisa dinilai"', allow_blank=True)
    ws.add_data_validation(dv)
    for i, r in enumerate(M.itertuples(), start=2):
        ws.append([i - 1, r.id_gold, r.dokumen_id, r.halaman, "", r.nama_asli, r.kelas, r.varian, r.komponen,
                   f"{r.harga:,}".replace(",", ".")] + [""] * 9)
        img = XLImage(os.path.join(IMG, f"{r.id_gold}.jpg"))
        scale = 760 / r.img_w
        img.width, img.height = int(r.img_w * scale), int(r.img_h * scale)
        ws.add_image(img, f"E{i}")
        ws.row_dimensions[i].height = max(40, img.height * 0.75 + 4)
        for col in "FGHIJ":
            ws[f"{col}{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        for col in "KLMNOPQRS":
            ws[f"{col}{i}"].fill = fill_in
            ws[f"{col}{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        for col in "KMOQ":
            dv.add(f"{col}{i}")
    ws.freeze_panes = "F2"

    wp = wb.create_sheet("petunjuk")
    for line in open(os.path.join(OUT, "PETUNJUK_gold_ekstraksi.md"), encoding="utf-8").read().splitlines():
        wp.append([line])
    wp.column_dimensions["A"].width = 140
    wb.move_sheet("petunjuk", offset=-1)
    wb.save(os.path.join(OUT, "gold_ekstraksi_v1.xlsx"))
    print("->", os.path.join(OUT, "gold_ekstraksi_v1.xlsx"))


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:3]))
