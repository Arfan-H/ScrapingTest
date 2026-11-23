"""Buat bahan gold set ekstraksi v3 (dinilai manusia).

Keluaran (pilot/eval/gold/):
- gold_ekstraksi_v3.xlsx            : file penilai pertama (semua butir)
- gold_ekstraksi_v3_penilai2.xlsx   : file penilai kedua (subset acak + SEMUA butir kontrol), ID sendiri
- gold_ekstraksi_v3_lokasi.csv      : ID -> file PDF + halaman (aman dibuka penilai; tanpa flag/strata/kontrol)
- gold_ekstraksi_v3_manifest.csv, gold_ekstraksi_v3_cakupan_manifest.csv, gold_ekstraksi_v3_strata.csv
  (JANGAN dibuka penilai sebelum selesai)

Riwayat: v1 (hanya presisi, 30 dok x 10 baris) dan v2 (ID berurutan per dokumen sehingga butir kontrol bisa ditebak,
bobot cakupan dari sisi data) ada di gold/v1_tidak_dipakai dan gold/v2_tidak_dipakai. v3 memakai seed baru untuk
seluruh sampel karena isi sampel v2 sempat dilaporkan ke penilai pertama.

Desain v3:
- Dokumen yang pernah disentuh saat pengembangan atau gambarnya dilihat agen dikecualikan -> dokumen_dikecualikan.csv.
- Strata dokumen = sumber teks (teks_pdf / ocr_ulang) x bentuk tabel (golongan / per_kelas / satu_harga); alokasi sama
  rata per strata (strata kecil diambil semua). Populasi, sampel, dan baris yang dilewati dicatat di *_strata.csv.
- PRESISI (sheet 'nilai_baris'): baris data acak per dokumen. Setiap dokumen tampil dengan jumlah baris yang SAMA
  (baris_tampil): dokumen kontrol = (baris_tampil-1) baris asli + 1 butir kontrol; dokumen lain = baris_tampil baris asli.
- BUTIR KONTROL: nilai sengaja diubah (harga/kelas/nama) untuk mengukur ketelitian penilai. Dokumen, baris, dan
  ubahannya diambil dengan RNG terpisah (SEED_KONTROL), jadi bisa diganti tanpa mengubah sampel presisi/cakupan.
- CAKUPAN (sheet 'cek_baris_pdf'): per dokumen diambil k halaman acak tanpa pengembalian dari halaman (dalam rentang
  halaman yang punya data) yang memuat >= 1 baris kandidat (angka mirip harga >= 1.000), lalu 1 baris kandidat acak
  per halaman. Peluang inklusi baris ~ k/H x 1/L_p (H = halaman berkandidat, L_p = baris kandidat di halaman itu);
  H, L_p, dan total baris kandidat dokumen disimpan untuk bobot.
  Batasan: harga < 1.000 tidak pernah jadi kandidat; halaman tarif di luar rentang halaman ber-data tidak terjangkau.
- ID diacak SETELAH semua butir dipilih (tidak berkaitan dengan dokumen/urutan/jenis); urutan baris diacak terpisah.
  Sheet tidak memuat dokumen_id/halaman/flag.

Pemakaian: python -I pilot/eval/buat_gold_ekstraksi.py [jumlah_dokumen=60] [baris_tampil_per_dokumen=6] [halaman_cakupan_per_dokumen=2]
"""
import glob
import hashlib
import os
import subprocess
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

VER = "v3"
OUT = os.path.join(HERE, "gold")
IMG = os.path.join(OUT, f"gambar_{VER}")
PDF_DIR = os.path.join(ROOT, "bpk_v3", "buku_tarif", "teks")
SEED = 20261125
SEED_KONTROL = 90417
PARSER_COMMIT = "cb968f4"
N_P2_PRESISI, N_P2_CAKUPAN = 120, 30
EXCL_LISTS = [("dokumen_debugging.txt", "ditelusuri saat debugging parser"),
              ("dokumen_dilihat_agen.txt", "gambarnya dilihat agen saat menyiapkan gold v1/v2")]
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


def prices(t):
    return {int(re.sub(r"[.,]", "", m)) for m in PRICE.findall(t) if not re.fullmatch(r"(19|20)\d\d", m)}


def norm(t):
    return re.sub(r"[^0-9a-z]", "", str(t).lower())


def rows_from_line(xp, line):
    """Data dari baris PDF: baris_mentah sama / saling memuat (baris gabungan), lalu harga sama di halaman yang sama."""
    nl = norm(line)
    bm = xp.baris_mentah.astype(str)
    same = (bm.str.strip() == line.strip()) | bm.map(lambda b: len(nl) >= 6 and (nl in norm(b) or (len(norm(b)) >= 6 and norm(b) in nl)))
    pr = prices(line)
    other = (~same & xp.harga.isin(pr)) if pr else (same & False)
    return xp[same], xp[other]


def mutate(c, rng):
    """Butir kontrol: ubah satu nilai yang ditampilkan. Mengembalikan (kolom, nilai_tampil)."""
    kind = rng.choice(["harga", "harga", "kelas", "nama"])
    if kind == "kelas" and c.kelas in KELAS_STD + ["Non-kelas"]:
        return "kelas", str(rng.choice([k for k in KELAS_STD + ["Non-kelas"] if k != c.kelas]))
    words = str(c.nama_asli).split()
    if kind == "nama" and len(words) >= 3:
        return "nama_asli", " ".join(words[:-1])
    s = str(int(c.harga))
    if len(s) >= 3 and rng.random() < 0.6:
        i = int(rng.integers(1, len(s) - (2 if len(s) > 3 else 1)))
        nd = str((int(s[i]) + int(rng.integers(1, 9))) % 10)
        return "harga", int(s[:i] + nd + s[i + 1:])
    return "harga", int(c.harga) * 10


def rp(v):
    return f"{int(v):,}".replace(",", ".")


def make_book(Msub, Rsub, idc, noc, path):
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
    sheet(ws, ["no", "id", "gambar halaman PDF (baris bertanda merah)", "nama di data", "kelas di data", "varian di data",
               "komponen di data", "harga di data", "NAMA benar?", "nama seharusnya", "KELAS benar?", "kelas seharusnya",
               "VARIAN/KOMPONEN benar?", "seharusnya", "HARGA benar?", "harga seharusnya", "catatan"],
          [5, 7, 105, 34, 12, 12, 12, 12, 11, 30, 11, 16, 13, 18, 11, 16, 30])
    dv = DataValidation(type="list", formula1=ynd, allow_blank=True)
    ws.add_data_validation(dv)
    for i, r in enumerate(Msub.sort_values(noc).itertuples(), start=2):
        ws.append([int(getattr(r, noc)), getattr(r, idc), "", r.tampil_nama, r.tampil_kelas, r.varian, r.komponen,
                   rp(r.tampil_harga)] + [""] * 9)
        put_img(ws, r.id_p1, r.img_w, r.img_h, f"C{i}", i)
        for col in "DEFGH":
            ws[f"{col}{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        for col in "IJKLMNOPQ":
            ws[f"{col}{i}"].fill = fill_in
            ws[f"{col}{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        for col in "IKMO":
            dv.add(f"{col}{i}")
    ws.freeze_panes = "D2"

    wr = wb.create_sheet("cek_baris_pdf")
    sheet(wr, ["no", "id", "gambar halaman PDF (baris bertanda merah)",
               "data yang berasal dari baris ini (nama | kelas | komponen | harga)", "Baris ini memuat TARIF layanan?",
               "Semua harga di baris ini ada di data dengan benar?", "harga/nama yang hilang atau salah", "catatan"],
          [5, 7, 105, 60, 14, 16, 34, 30])
    dv1 = DataValidation(type="list", formula1=ynd, allow_blank=True)
    dv2 = DataValidation(type="list", formula1='"Ya semua,Sebagian,Tidak ada,Tidak bisa dinilai"', allow_blank=True)
    wr.add_data_validation(dv1)
    wr.add_data_validation(dv2)
    for i, r in enumerate(Rsub.sort_values(noc).itertuples(), start=2):
        wr.append([int(getattr(r, noc)), getattr(r, idc), "", r.data_tampil, "", "", "", ""])
        put_img(wr, r.id_p1, r.img_w, r.img_h, f"C{i}", i)
        wr[f"D{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        for col in "EFGH":
            wr[f"{col}{i}"].fill = fill_in
            wr[f"{col}{i}"].alignment = Alignment(wrap_text=True, vertical="top")
        dv1.add(f"E{i}")
        dv2.add(f"F{i}")
    wr.freeze_panes = "D2"

    wp = wb.create_sheet("petunjuk")
    for line in open(os.path.join(OUT, "PETUNJUK_gold_ekstraksi.md"), encoding="utf-8").read().splitlines():
        wp.append([line])
    wp.column_dimensions["A"].width = 140
    wb.move_sheet("petunjuk", offset=-2)
    wb.active = 0
    wb.save(path)
    print("->", path)


def main(n_docs=60, per_doc=6, per_doc_pdf=2):
    os.makedirs(IMG, exist_ok=True)
    rng = np.random.default_rng(SEED)
    rng_k = np.random.default_rng(SEED_KONTROL)
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
    P = pd.concat(pick).reset_index(drop=True)
    n_ctrl = int(round(0.10 * n_docs * (per_doc - 0.5)))
    ctrl_docs = set(P.dokumen_id.iloc[rng_k.permutation(len(P))[:n_ctrl]])

    rows, rec, skip = [], [], []
    for r in P.itertuples():
        x = T[T.dokumen_id == r.dokumen_id]
        f = os.path.join(PDF_DIR, x.file.iat[0])
        if not os.path.exists(f):
            print("PDF hilang:", f)
            continue
        is_ctrl = r.dokumen_id in ctrl_docs
        n_asli = per_doc - 1 if is_ctrl else per_doc
        # ---- presisi: baris data acak; kontrol dari sisa baris dengan RNG terpisah ----
        got, tried, used = 0, 0, set()
        for i in rng.permutation(len(x)):
            if got >= n_asli:
                break
            c = x.iloc[i]
            tried += 1
            pg, PL = page_data(os.path.join(PDF_DIR, c.file), int(c.halaman), c.metode_ekstraksi == "ocr_ulang")
            j = find_line(PL, c.baris_mentah)
            im = render(pg, PL, j) if j is not None else None
            if im is None:
                continue
            used.add(i)
            rows.append(dict(jenis="presisi", c=c, im=im, r=r, col="", val=""))
            got += 1
        skip.append(dict(strata=r.strata, presisi_dicoba=tried, presisi_dilewati=tried - got))
        if is_ctrl:
            for i in rng_k.permutation(len(x)):
                if i in used:
                    continue
                c = x.iloc[i]
                pg, PL = page_data(os.path.join(PDF_DIR, c.file), int(c.halaman), c.metode_ekstraksi == "ocr_ulang")
                j = find_line(PL, c.baris_mentah)
                im = render(pg, PL, j) if j is not None else None
                if im is None:
                    continue
                col, val = mutate(c, rng_k)
                rows.append(dict(jenis="kontrol", c=c, im=im, r=r, col=col, val=val))
                break
        # ---- cakupan ----
        page_ocr = (x.metode_ekstraksi == "ocr_ulang").groupby(x.halaman).mean()

        def is_ocr(p):
            return bool(page_ocr.get(p, float(r.sumber == "ocr_ulang")) > 0.5)
        lo, hi = int(x.halaman.min()), int(x.halaman.max())
        cand = {}
        for p in range(lo, hi + 1):
            _, PL = page_data(f, p, is_ocr(p))
            k = [i for i, (t, ws) in enumerate(PL) if ws and prices(t)]
            if k:
                cand[p] = k
        H = len(cand)
        L_tot = sum(len(v) for v in cand.values())
        pages = sorted(cand)
        taken = 0
        for p in [pages[i] for i in rng.permutation(len(pages))]:
            if taken >= per_doc_pdf:
                break
            pg, PL = page_data(f, p, is_ocr(p))
            j = cand[p][int(rng.integers(len(cand[p])))]
            im = render(pg, PL, j)
            if im is None:
                skip.append(dict(strata=r.strata, cakupan_gagal_render=1))
                continue
            got_rows, other = rows_from_line(x[x.halaman == p], PL[j][0])

            def lines(dd, tag=""):
                t = "\n".join(tag + f"{q.nama_asli} | {q.kelas} | {q.komponen}" + (f" | {q.varian}" if pd.notna(q.varian) else "")
                              + f" | {rp(q.harga)}" for q in dd.head(12).itertuples())
                return t + (f"\n... (+{len(dd) - 12} lagi)" if len(dd) > 12 else "")
            data_txt = lines(got_rows)
            if len(other):
                data_txt += ("\n" if data_txt else "") + lines(other, "[harga sama, dari baris PDF lain] ")
            rec.append(dict(im=im, split=r.split, strata=r.strata, dokumen_id=r.dokumen_id, file=x.file.iat[0], halaman=p,
                            baris_pdf=PL[j][0], n_data_dari_baris=len(got_rows), n_data_harga_sama=len(other),
                            tarif_ids=";".join(got_rows.tarif_id), tarif_ids_harga_sama=";".join(other.tarif_id),
                            data_tampil=data_txt or "(TIDAK ADA data yang berasal dari baris ini)",
                            H_halaman_berkandidat=H, L_kandidat_halaman=len(cand[p]), N_kandidat_dokumen=L_tot,
                            k_halaman_diambil=min(per_doc_pdf, H), n_halaman_rentang=hi - lo + 1, n_baris_dok=r.n))
            taken += 1

    # ---- ID acak setelah semua butir dipilih; urutan acak terpisah ----
    rng_id = np.random.default_rng(SEED + 1)
    ids = rng_id.choice(np.arange(1000, 10000), len(rows) + len(rec), replace=False)
    ids2 = rng_id.choice(np.setdiff1d(np.arange(1000, 10000), ids), len(rows) + len(rec), replace=False)  # tidak bentrok
    M, R = [], []
    for k, d in enumerate(rows):
        c, r = d["c"], d["r"]
        show = dict(nama_asli=c.nama_asli, kelas=c.kelas, harga=int(c.harga))
        if d["jenis"] == "kontrol":
            show[d["col"]] = d["val"]
        gid = f"N{ids[k]}"
        d["im"].save(os.path.join(IMG, f"{gid}.jpg"), quality=68, optimize=True)
        M.append(dict(id_p1=gid, jenis=d["jenis"], kolom_diubah=d["col"], nilai_tampil=d["val"], split=r.split,
                      strata=r.strata, tarif_id=c.tarif_id, dokumen_id=c.dokumen_id, file=c.file, halaman=int(c.halaman),
                      baris_mentah=c.baris_mentah, nama_asli=c.nama_asli, kelas=c.kelas,
                      varian="" if pd.isna(c.varian) else c.varian, komponen=c.komponen, harga=int(c.harga),
                      tampil_nama=show["nama_asli"], tampil_kelas=show["kelas"], tampil_harga=show["harga"],
                      flag_qc=c.flag_qc, qc_masalah=bool(c.qc_masalah), metode_ekstraksi=c.metode_ekstraksi,
                      n_baris_dok=r.n, img_w=d["im"].width, img_h=d["im"].height))
    for k, d in enumerate(rec):
        gid = f"C{ids[len(rows) + k]}"
        d["im"].save(os.path.join(IMG, f"{gid}.jpg"), quality=68, optimize=True)
        R.append({"id_p1": gid, **{a: b for a, b in d.items() if a != "im"}, "img_w": d["im"].width, "img_h": d["im"].height})
    M, R = pd.DataFrame(M), pd.DataFrame(R)
    M = M.iloc[rng_id.permutation(len(M))].reset_index(drop=True)
    R = R.iloc[rng_id.permutation(len(R))].reset_index(drop=True)
    M.insert(0, "no_p1", range(1, len(M) + 1))
    R.insert(0, "no_p1", range(1, len(R) + 1))
    # penilai kedua: subset presisi acak + SEMUA kontrol; subset cakupan acak; ID dan urutan sendiri
    pres_idx = list(M.index[M.jenis == "presisi"])
    sel2 = list(rng_id.choice(pres_idx, min(N_P2_PRESISI, len(pres_idx)), replace=False)) + list(M.index[M.jenis == "kontrol"])
    sel2 = [sel2[i] for i in rng_id.permutation(len(sel2))]
    M["id_p2"], M["no_p2"] = "", 0
    for n, i in enumerate(sel2, start=1):
        M.loc[i, "id_p2"], M.loc[i, "no_p2"] = f"N{ids2[n - 1]}", n
    selr = list(rng_id.choice(list(R.index), min(N_P2_CAKUPAN, len(R)), replace=False))
    R["id_p2"], R["no_p2"] = "", 0
    for n, i in enumerate(selr, start=1):
        R.loc[i, "id_p2"], R.loc[i, "no_p2"] = f"C{ids2[len(sel2) + n - 1]}", n

    tpath = os.path.join(ROOT, "pilot", "out", "dataset", "tarif.csv.gz")
    data_sha = hashlib.sha256(open(tpath, "rb").read()).hexdigest()
    data_commit = subprocess.run(["git", "-C", ROOT, "log", "-1", "--format=%h", "--", "pilot/out/dataset/tarif.csv.gz"],
                                 capture_output=True, text=True).stdout.strip()
    ver = dict(versi_parser=PARSER_COMMIT, data_commit=data_commit, data_sha256=data_sha)
    M.drop(columns=["img_h", "img_w"]).assign(**ver).to_csv(
        os.path.join(OUT, f"gold_ekstraksi_{VER}_manifest.csv"), index=False)
    R.drop(columns=["img_h", "img_w"]).assign(**ver).to_csv(
        os.path.join(OUT, f"gold_ekstraksi_{VER}_cakupan_manifest.csv"), index=False)
    lok = pd.concat([M[["id_p1", "id_p2", "file", "halaman"]], R[["id_p1", "id_p2", "file", "halaman"]]])
    lok1 = lok[["id_p1", "file", "halaman"]].rename(columns={"id_p1": "id"})
    lok2 = lok[lok.id_p2 != ""][["id_p2", "file", "halaman"]].rename(columns={"id_p2": "id"})
    pd.concat([lok1, lok2]).sort_values("id").to_csv(os.path.join(OUT, f"gold_ekstraksi_{VER}_lokasi.csv"), index=False)

    SK = pd.DataFrame(skip).groupby("strata").sum(numeric_only=True)
    pop = pop.join(P.groupby("strata").size().rename("dok_sampel")).join(
        P[P.split == "test"].groupby("strata").size().rename("dok_sampel_test")).join(SK).fillna(0)
    pop.astype(int).reset_index().to_csv(os.path.join(OUT, f"gold_ekstraksi_{VER}_strata.csv"), index=False)

    make_book(M, R, "id_p1", "no_p1", os.path.join(OUT, f"gold_ekstraksi_{VER}.xlsx"))
    make_book(M[M.id_p2 != ""], R[R.id_p2 != ""], "id_p2", "no_p2", os.path.join(OUT, f"gold_ekstraksi_{VER}_penilai2.xlsx"))
    # hanya ringkasan struktur (tanpa isi sampel)
    print(f"dokumen {P.dokumen_id.nunique()} | butir nilai_baris {len(M)} | cek_baris_pdf {len(R)} | "
          f"penilai2: {int((M.id_p2 != '').sum())} + {int((R.id_p2 != '').sum())}")


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:4]))
