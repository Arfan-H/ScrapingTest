"""Buat bahan gold set ekstraksi v2 (dinilai manusia): pilot/eval/gold/gold_ekstraksi_v2.xlsx

Desain (v2; v1 ada di gold/v1_tidak_dipakai/, digantikan karena hanya mengukur presisi, berkluster 30 dok x 10 baris,
strata kurang, urutan tidak diacak, tanpa butir kontrol):
- Dokumen yang pernah disentuh saat pengembangan dikecualikan (sampel cek visual v3-v10, dokumen yang ditelusuri saat
  debugging, dokumen pilot, dokumen yang gambarnya dilihat saat menyiapkan gold v1) -> gold/dokumen_dikecualikan.csv.
- Strata dokumen = sumber teks (teks_pdf / ocr_ulang) x bentuk tabel (golongan / per_kelas / satu_harga).
  Populasi tiap strata dan jumlah sampel dicatat di gold/gold_ekstraksi_v2_strata.csv (untuk pembobotan).
  Strata ocr_ulang/per_kelas hanya punya 2 dokumen di seluruh data dan keduanya dikecualikan -> tidak bisa diisi.
- Lebih banyak dokumen, lebih sedikit baris per dokumen (default 60 dokumen x 5 baris) karena unit efektif = dokumen.
  Ketidakpastian dihitung dengan bootstrap per dokumen di dalam strata (pilot/eval/nilai_gold_ekstraksi.py).
- Dua arah:
  * PRESISI (sheet 'nilai_baris'): baris acak dari DATA -> apakah nama/kelas/komponen/harga sesuai PDF?
  * CAKUPAN/recall (sheet 'cek_baris_pdf'): baris acak dari PDF yang memuat angka mirip harga, diambil dari halaman
    di rentang halaman tarif dokumen -> apakah semua harganya tercatat di data? (menangkap baris hilang/tergabung)
- Butir kontrol: ~10% baris tambahan di 'nilai_baris' yang nilainya SENGAJA diubah (harga/kelas/nama), untuk mengukur
  ketelitian penilai (bias jangkar). Tidak ikut dihitung dalam akurasi.
- Urutan baris diacak, sehingga 'no 1-60' untuk penilai kedua adalah sampel acak lintas dokumen.
- Split dev/test di tingkat dokumen, bergantian di dalam strata. Bila parser TIDAK diubah setelah penilaian, dev+test
  boleh digabung untuk angka akhir; bila parser diubah, hanya 'test' yang sah dan perubahan harus diberi versi.
- Penilai tidak diberi flag_qc / split / tanda butir kontrol; semuanya ada di manifest.

Pemakaian: python -I pilot/eval/buat_gold_ekstraksi.py [jumlah_dokumen=60] [baris_per_dokumen=5] [baris_pdf_per_dokumen=2]
"""
import glob
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
from PIL import ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from to_standard import lines_from_words, load_ocr, page_lines  # noqa: E402

VER = "v2"
OUT = os.path.join(HERE, "gold")
IMG = os.path.join(OUT, f"gambar_{VER}")
PDF_DIR = os.path.join(ROOT, "bpk_v3", "buku_tarif", "teks")
SEED = 20261124
PARSER_COMMIT = "cb968f4"
EXCL_LISTS = [("dokumen_debugging.txt", "ditelusuri saat debugging parser"),
              ("dokumen_dilihat_gold_v1.txt", "gambarnya dilihat saat menyiapkan gold v1")]
KELAS_STD = ["III", "II", "I", "VIP", "VVIP", "Utama"]
GOLONGAN = re.compile(r"(?:\b(?:golongan|kelompok|gol)\s*[ivx0-9a-e]+\b|(?:^|\s)(?:kecil|sedang|besar|khusus|canggih)$"
                      r"|\boperasi (?:kecil|sedang|besar|khusus))")
PRICE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+|\d{4,8})(?![\d])")


def excluded_docs(doc_ids):
    rows = []
    for g in sorted(glob.glob(os.path.join(HERE, "cek_manual_40_v*.csv"))):
        for d in pd.read_csv(g).dokumen_id.unique():
            rows.append((d, f"sampel cek visual {os.path.basename(g)}"))
    for fn, why in EXCL_LISTS:
        p = os.path.join(OUT, fn)
        if os.path.exists(p):
            rows += [(d, why) for d in open(p, encoding="utf-8").read().split()]
    for d in pd.read_csv(os.path.join(ROOT, "pilot", "config", "dokumen.csv")).dokumen_id:
        rows.append((d, "dokumen pilot"))
    E = pd.DataFrame(rows, columns=["dokumen_id", "alasan"])
    return E[E.dokumen_id.isin(doc_ids)].groupby("dokumen_id").alasan.apply(lambda s: "; ".join(dict.fromkeys(s))).reset_index()


_cache = {}


def page_data(pdf_path, page_no, ocr):
    """(halaman pdfplumber, daftar baris [(teks, kata)]) dengan cache sederhana."""
    key = (pdf_path, page_no, ocr)
    if key not in _cache:
        if len(_cache) > 40:
            for k in list(_cache)[:20]:
                _cache[k][2].close()
                del _cache[k]
        pdf = pdfplumber.open(pdf_path)
        pg = pdf.pages[page_no - 1]
        if ocr:
            PL = lines_from_words([w for w in load_ocr(pdf_path).get(page_no, []) if w.get("score", 1) >= 0.5])
        else:
            PL = page_lines(pg)
        _cache[key] = (pg, PL, pdf)
    return _cache[key][:2]


def render(pg, PL, j):
    """Potongan halaman di sekitar baris ke-j (judul tabel/kolom di atasnya ikut), baris ditandai merah."""
    y0 = min(w["top"] for w in PL[j][1])
    y1 = max(w["bottom"] for w in PL[j][1])
    x0b, y0b, x1b, y1b = pg.bbox
    ctx = max(90, 0.22 * (y1b - y0b))
    top, bot = max(y0b, y0 - ctx), min(y1b, y1 + 35)
    near = [w for _, ws in PL for w in ws if w["bottom"] >= top and w["top"] <= bot] or PL[j][1]
    box = (max(x0b, min(w["x0"] for w in near) - 15), top, min(x1b, max(w["x1"] for w in near) + 15), bot)
    try:
        im = pg.crop(box).to_image(resolution=110).original.convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    d = ImageDraw.Draw(im)
    sy = im.height / (box[3] - box[1])
    d.rectangle([0, (y0 - box[1]) * sy - 2, 7, (y1 - box[1]) * sy + 2], fill="red")
    d.rectangle([0, (y0 - box[1]) * sy - 2, im.width - 1, (y1 - box[1]) * sy + 2], outline="red", width=2)
    if im.width > 900:
        im = im.resize((900, int(im.height * 900 / im.width)))
    return im


def find_line(PL, raw):
    return next((k for k, (t, ws) in enumerate(PL) if ws and t.strip() == str(raw).strip()), None)


def is_price_line(t):
    m = PRICE.findall(t)
    return any(not re.fullmatch(r"(19|20)\d\d", x) for x in m)


def norm(t):
    return re.sub(r"[^0-9a-z]", "", str(t).lower())


def prices(t):
    out = set()
    for m in PRICE.findall(t):
        if re.fullmatch(r"(19|20)\d\d", m):
            continue
        out.add(int(re.sub(r"[.,]", "", m)))
    return out


def rows_from_line(xp, line):
    """Data dari baris PDF: baris_mentah sama / saling memuat (baris gabungan), lalu harga sama di halaman yang sama."""
    nl = norm(line)
    bm = xp.baris_mentah.astype(str)
    same = (bm.str.strip() == line.strip()) | bm.map(lambda b: len(nl) >= 6 and (nl in norm(b) or (len(norm(b)) >= 6 and norm(b) in nl)))
    pr = prices(line)
    other = ~same & xp.harga.isin(pr) if pr else same & False
    return xp[same], xp[other]


def mutate(c, rng):
    """Butir kontrol: ubah satu nilai yang ditampilkan. Mengembalikan (kolom, nilai_tampil)."""
    kind = rng.choice(["harga", "harga", "kelas", "nama"])
    if kind == "kelas" and c.kelas in KELAS_STD + ["Non-kelas"]:
        return "kelas", rng.choice([k for k in KELAS_STD + ["Non-kelas"] if k != c.kelas])
    words = str(c.nama_asli).split()
    if kind == "nama" and len(words) >= 3:
        return "nama_asli", " ".join(words[:-1])
    s = str(int(c.harga))
    if len(s) >= 3 and rng.random() < 0.6:
        i = int(rng.integers(1, len(s) - (2 if len(s) > 3 else 1)))
        nd = str((int(s[i]) + int(rng.integers(1, 9))) % 10)
        return "harga", int(s[:i] + nd + s[i + 1:])
    return "harga", int(c.harga) * 10


def main(n_docs=60, per_doc=5, per_doc_pdf=2):
    os.makedirs(IMG, exist_ok=True)
    rng = np.random.default_rng(SEED)
    T = pd.read_csv(os.path.join(ROOT, "pilot", "out", "dataset", "tarif.csv.gz"), low_memory=False)
    D = pd.read_csv(os.path.join(ROOT, "pilot", "out", "dataset", "dokumen.csv"))
    E = excluded_docs(set(D.dokumen_id))
    E.to_csv(os.path.join(OUT, "dokumen_dikecualikan.csv"), index=False)

    g = T.groupby("dokumen_id")
    S = pd.DataFrame({"n": g.size(), "ocr": g.metode_ekstraksi.apply(lambda s: (s == "ocr_ulang").mean()),
                      "kelas": g.flag_qc.apply(lambda s: s.str.contains("dari_kolom_kelas").mean()),
                      "gol": g.nama_norm.apply(lambda s: s.fillna("").str.contains(GOLONGAN).mean())}).reset_index()
    S["sumber"] = np.where(S.ocr > 0.5, "ocr_ulang", "teks_pdf")
    S["bentuk"] = np.where(S.gol >= 0.10, "golongan", np.where(S.kelas > 0.3, "per_kelas", "satu_harga"))
    S["strata"] = S.sumber + "/" + S.bentuk
    S["eligible"] = (S.n >= 20) & ~S.dokumen_id.isin(E.dokumen_id)
    pop = S.groupby("strata").agg(dok_semua=("n", "size"), baris_semua=("n", "sum")).join(
        S[S.eligible].groupby("strata").agg(dok_eligible=("n", "size"), baris_eligible=("n", "sum"))).fillna(0)

    # alokasi: sama rata per strata, sisa dari strata kecil dialihkan ke strata yang masih punya dokumen
    avail = S[S.eligible].groupby("strata").size().to_dict()
    quota = {s: 0 for s in avail}
    left = n_docs
    while left > 0 and any(quota[s] < avail[s] for s in avail):
        for s in sorted(avail, key=lambda s: quota[s]):
            if left and quota[s] < avail[s]:
                quota[s] += 1
                left -= 1
    pick = []
    for s, grp in S[S.eligible].groupby("strata"):
        sel = grp.iloc[rng.permutation(len(grp))[:quota[s]]].copy()
        sel["split"] = ["dev" if i % 2 == 0 else "test" for i in range(len(sel))]
        pick.append(sel)
    P = pd.concat(pick)
    pop["dok_sampel"] = P.groupby("strata").size()
    pop = pop.fillna(0).astype(int).reset_index()
    pop.to_csv(os.path.join(OUT, f"gold_ekstraksi_{VER}_strata.csv"), index=False)
    print(pop.to_string(index=False))

    n_ctrl = int(round(0.10 * n_docs * per_doc))
    ctrl_docs = set(P.dokumen_id.iloc[rng.permutation(len(P))[:n_ctrl]])
    rows, rec = [], []
    for r in P.itertuples():
        x = T[T.dokumen_id == r.dokumen_id]
        f = os.path.join(PDF_DIR, x.file.iat[0])
        if not os.path.exists(f):
            print("PDF hilang:", f)
            continue
        page_ocr = (x.metode_ekstraksi == "ocr_ulang").groupby(x.halaman).mean()
        # ---- presisi: baris data acak (+1 untuk butir kontrol) ----
        need = per_doc + (1 if r.dokumen_id in ctrl_docs else 0)
        got = 0
        for c in x.iloc[rng.permutation(len(x))].itertuples():
            if got >= need:
                break
            pg, PL = page_data(os.path.join(PDF_DIR, c.file), int(c.halaman), c.metode_ekstraksi == "ocr_ulang")
            j = find_line(PL, c.baris_mentah)
            im = render(pg, PL, j) if j is not None else None
            if im is None:
                continue
            ctrl = got == per_doc  # baris tambahan = butir kontrol
            show = dict(nama_asli=c.nama_asli, kelas=c.kelas, harga=int(c.harga))
            col, val = mutate(c, rng) if ctrl else ("", "")
            if ctrl:
                show[col] = val
            gid = f"P{len(rows) + 1:04d}"
            im.save(os.path.join(IMG, f"{gid}.jpg"), quality=68, optimize=True)
            rows.append(dict(id_gold=gid, jenis="kontrol" if ctrl else "presisi", kolom_diubah=col,
                             nilai_tampil=val, split=r.split, strata=r.strata, tarif_id=c.tarif_id,
                             dokumen_id=c.dokumen_id, file=c.file, halaman=int(c.halaman), baris_mentah=c.baris_mentah,
                             nama_asli=c.nama_asli, kelas=c.kelas, varian="" if pd.isna(c.varian) else c.varian,
                             komponen=c.komponen, harga=int(c.harga), tampil_nama=show["nama_asli"],
                             tampil_kelas=show["kelas"], tampil_harga=show["harga"], flag_qc=c.flag_qc,
                             qc_masalah=bool(c.qc_masalah), metode_ekstraksi=c.metode_ekstraksi,
                             n_baris_dok=r.n, img_w=im.width, img_h=im.height))
            got += 1
        # ---- cakupan: baris PDF acak yang memuat angka mirip harga ----
        lo, hi = int(x.halaman.min()), int(x.halaman.max())
        pages = list(range(lo, hi + 1))
        taken = 0
        for p in [pages[i] for i in rng.permutation(len(pages))]:
            if taken >= per_doc_pdf:
                break
            pg, PL = page_data(f, p, bool(page_ocr.get(p, float(r.sumber == "ocr_ulang")) > 0.5))
            cand = [k for k, (t, ws) in enumerate(PL) if ws and is_price_line(t)]
            if not cand:
                continue
            j = cand[int(rng.integers(len(cand)))]
            im = render(pg, PL, j)
            if im is None:
                continue
            got_rows, other = rows_from_line(x[x.halaman == p], PL[j][0])

            def lines(dd, tag=""):
                t = "\n".join(tag + f"{q.nama_asli} | {q.kelas} | {q.komponen}" + (f" | {q.varian}" if pd.notna(q.varian) else "")
                              + f" | {int(q.harga):,}".replace(",", ".") for q in dd.head(12).itertuples())
                return t + (f"\n... (+{len(dd) - 12} lagi)" if len(dd) > 12 else "")
            data_txt = lines(got_rows)
            if len(other):
                data_txt += ("\n" if data_txt else "") + lines(other, "[harga sama, dari baris PDF lain] ")
            rid = f"R{len(rec) + 1:04d}"
            im.save(os.path.join(IMG, f"{rid}.jpg"), quality=68, optimize=True)
            rec.append(dict(id_gold=rid, split=r.split, strata=r.strata, dokumen_id=r.dokumen_id, file=x.file.iat[0],
                            halaman=p, baris_pdf=PL[j][0], n_harga_di_baris=len([m for m in PRICE.findall(PL[j][0])
                                                                                 if not re.fullmatch(r"(19|20)\d\d", m)]),
                            n_data_dari_baris=len(got_rows), n_data_harga_sama=len(other),
                            tarif_ids=";".join(got_rows.tarif_id), tarif_ids_harga_sama=";".join(other.tarif_id),
                            data_tampil=data_txt or "(TIDAK ADA data yang berasal dari baris ini)",
                            n_halaman_rentang=len(pages), img_w=im.width, img_h=im.height))
            taken += 1

    M = pd.DataFrame(rows)
    M = M.iloc[rng.permutation(len(M))].reset_index(drop=True)
    M.insert(0, "no", range(1, len(M) + 1))
    R = pd.DataFrame(rec)
    R = R.iloc[rng.permutation(len(R))].reset_index(drop=True)
    R.insert(0, "no", range(1, len(R) + 1))
    M.drop(columns=["img_h", "img_w"]).assign(versi_parser=PARSER_COMMIT).to_csv(
        os.path.join(OUT, f"gold_ekstraksi_{VER}_manifest.csv"), index=False)
    R.drop(columns=["img_h", "img_w"]).assign(versi_parser=PARSER_COMMIT).to_csv(
        os.path.join(OUT, f"gold_ekstraksi_{VER}_cakupan_manifest.csv"), index=False)
    print("presisi:", (M.jenis == "presisi").sum(), "| kontrol:", (M.jenis == "kontrol").sum(), "| cakupan:", len(R),
          "| dokumen:", M.dokumen_id.nunique(), M.drop_duplicates("dokumen_id").split.value_counts().to_dict())

    # ---- workbook ----
    wb = Workbook()
    fill_in = PatternFill("solid", fgColor="FFF2CC")
    ynd = '"Ya,Tidak,Tidak bisa dinilai"'

    def sheet(ws, head, widths):
        ws.append(head)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w

    def put_img(ws, gid, w, h, cell, r):
        img = XLImage(os.path.join(IMG, f"{gid}.jpg"))
        sc = 760 / w
        img.width, img.height = int(w * sc), int(h * sc)
        ws.add_image(img, cell)
        ws.row_dimensions[r].height = max(40, img.height * 0.75 + 4)

    ws = wb.active
    ws.title = "nilai_baris"
    sheet(ws, ["no", "id_gold", "dokumen_id", "halaman", "gambar halaman PDF (baris bertanda merah)", "nama di data",
               "kelas di data", "varian di data", "komponen di data", "harga di data", "NAMA benar?", "nama seharusnya",
               "KELAS benar?", "kelas seharusnya", "VARIAN/KOMPONEN benar?", "seharusnya", "HARGA benar?",
               "harga seharusnya", "catatan"],
          [5, 8, 26, 7, 105, 34, 12, 12, 12, 12, 11, 30, 11, 16, 13, 18, 11, 16, 30])
    dv = DataValidation(type="list", formula1=ynd, allow_blank=True)
    ws.add_data_validation(dv)
    for i, r in enumerate(M.itertuples(), start=2):
        ws.append([r.no, r.id_gold, r.dokumen_id, r.halaman, "", r.tampil_nama, r.tampil_kelas, r.varian, r.komponen,
                   f"{int(r.tampil_harga):,}".replace(",", ".")] + [""] * 9)
        put_img(ws, r.id_gold, r.img_w, r.img_h, f"E{i}", i)
        for col in "FGHIJ":
            ws[f"{col}{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        for col in "KLMNOPQRS":
            ws[f"{col}{i}"].fill = fill_in
            ws[f"{col}{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        for col in "KMOQ":
            dv.add(f"{col}{i}")
    ws.freeze_panes = "F2"

    wr = wb.create_sheet("cek_baris_pdf")
    sheet(wr, ["no", "id_gold", "dokumen_id", "halaman", "gambar halaman PDF (baris bertanda merah)",
               "data yang berasal dari baris ini (nama | kelas | komponen | harga)", "Baris ini memuat TARIF layanan?",
               "Semua harga di baris ini ada di data dengan benar?", "harga/nama yang hilang atau salah", "catatan"],
          [5, 8, 26, 7, 105, 60, 14, 16, 34, 30])
    dv1 = DataValidation(type="list", formula1=ynd, allow_blank=True)
    dv2 = DataValidation(type="list", formula1='"Ya semua,Sebagian,Tidak ada,Tidak bisa dinilai"', allow_blank=True)
    wr.add_data_validation(dv1)
    wr.add_data_validation(dv2)
    for i, r in enumerate(R.itertuples(), start=2):
        wr.append([r.no, r.id_gold, r.dokumen_id, r.halaman, "", r.data_tampil, "", "", "", ""])
        put_img(wr, r.id_gold, r.img_w, r.img_h, f"E{i}", i)
        wr[f"F{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        for col in "GHIJ":
            wr[f"{col}{i}"].fill = fill_in
            wr[f"{col}{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        dv1.add(f"G{i}")
        dv2.add(f"H{i}")
    wr.freeze_panes = "F2"

    wp = wb.create_sheet("petunjuk")
    for line in open(os.path.join(OUT, "PETUNJUK_gold_ekstraksi.md"), encoding="utf-8").read().splitlines():
        wp.append([line])
    wp.column_dimensions["A"].width = 140
    wb.move_sheet("petunjuk", offset=-2)
    wb.active = 0
    out = os.path.join(OUT, f"gold_ekstraksi_{VER}.xlsx")
    wb.save(out)
    print("->", out)


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:4]))
