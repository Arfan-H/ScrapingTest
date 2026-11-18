"""PDF Perbup -> Excel tarif standar (long format, 5 sheet).

Sheet: tarif, rumah_sakit, dokumen, golongan_tarif, pemetaan.
Satu baris di sheet `tarif` = satu harga (satu nama x satu kelas x satu komponen).

Dibanding extract.py, versi ini membaca KONTEKS bagian dokumen:
  - kelas dari judul bagian (mis. "PEMERIKSAAN LABORATORIUM KELAS III")
  - status BHP dari catatan di bagian itu (mis. "belum termasuk BHP",
    "ditambah alat dan bahan", "termasuk biaya BHP")
lalu menandai baris meragukan di kolom flag_qc.

Pemakaian:  python -I pilot/src/to_standard.py  (dari folder repo)
"""
import os
import re
import sys

import pandas as pd
import pdfplumber

sys.path.insert(0, os.path.dirname(__file__))
from extract import NUMBERING, PRICE_RE, TRAIL_PRICES, fix_numbers, is_header, to_int  # noqa: E402
from normalize import norm_name, std_category  # noqa: E402

BASE = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(BASE, "out")

RS = [
    dict(rs_id="RSUD-KAB-CIANJUR-KLS-C", nama_rs="RSUD Kelas C Kabupaten Cianjur (termasuk RSUD Cimacan)",
         kepemilikan="kab/kota", kelas_rs="C", kab_kota="Kabupaten Cianjur", provinsi="Jawa Barat",
         catatan="Satu Perbup berlaku untuk semua RSUD Kelas C di Kab. Cianjur"),
    dict(rs_id="RSUD-REMBANG-SOETRASNO", nama_rs="RSUD dr. R. Soetrasno", kepemilikan="kab/kota",
         kelas_rs="", kab_kota="Kabupaten Rembang", provinsi="Jawa Tengah",
         catatan="Kelas RS belum diverifikasi"),
]
DOK = [
    dict(dokumen_id="PERBUP-CIANJUR-3-2025", rs_id="RSUD-KAB-CIANJUR-KLS-C", jenis="Perbup", nomor="3",
         tahun=2025, tgl_ditetapkan="2025-01-13", tgl_berlaku="2025-01-14", status="berlaku (per unduhan)",
         mengubah_dokumen_id="", jenis_pdf="teks", halaman_lampiran_mulai=7,
         url="https://rsudcimacan.cianjurkab.go.id/public/assets/pdf/PB%203%202025%20TARIF%20KLS%20C%20terupdate.pdf",
         tgl_unduh="2026-11-18",
         aturan_umum="Sebagian besar bagian: tarif ditambah alat dan bahan (BHP di luar tarif)."),
    dict(dokumen_id="PERBUP-REMBANG-16-2023", rs_id="RSUD-REMBANG-SOETRASNO", jenis="Perbup", nomor="16",
         tahun=2023, tgl_ditetapkan="2023-06-27", tgl_berlaku="2023-07-17", status="berlaku (per unduhan)",
         mengubah_dokumen_id="mencabut Perbup 2021 (Berita Daerah 2021 No. 43)", jenis_pdf="teks",
         halaman_lampiran_mulai=9,
         url="https://jdih.rembangkab.go.id/produk_hukum/perbup/PERBUP_16_%202023%20-TARIF%20LAYANAN%20PADA%20RUMAH%20SAKIT%20UMUM%20DAERAH%20dr.%20R.%20SOETRASNO%20KABUPATEN%20REMBANG.pdf",
         tgl_unduh="2026-11-18",
         aturan_umum="Tabel kelas III dan kelas II; kelas I = 1,5x jasa kelas II, VIP = 2x jasa kelas II "
                     "(jasa sarana tetap). CITO tindakan operatif +75% jasa; radiologi +50%."),
]

# Judul bagian besar (awal blok konteks)
MAJOR = re.compile(
    r"^([a-z]\.\s+LAYANAN\b|\d+\.\s*[A-Z][A-Z /&()-]{5,}$|\d+\.\s*Tarif\s+[A-Z]|Tarif\s+[A-Z]|Paragraf\s+\d+)")
KELAS_IN_HEAD = re.compile(r"\bKELAS\s+(III|II|I)\b", re.I)
KELAS_ROW = re.compile(
    r"^(kelas\s*(iii|ii|i|utama)|iii|ii|i|vvip|vip(\s*(pratama|madya|utama|a|b))?(\s*&\s*madya)?|"
    r"presiden suite|vvip\s*/\s*presiden suite|icu|hcu|picu|nicu|semua kelas|one day( surgery)?)$", re.I)
FRAGMENT = re.compile(
    r"^(ringan|sedang|berat|kecil|besar|khusus|sederhana|canggih|utama|tindakan|pemeriksaan|reguler( / non)?|"
    r"spesialis|subspesialis|lengkap|pagi|sore|umum)$", re.I)
BHP_NO = re.compile(r"(tidak|belum)\s+termasuk[^.]{0,80}\bBHP\b|ditambah\s*alat\s*dan\s*bahan|"
                    r"diluar\s+dari\s+obat\s+dan\s+barang\s+habis\s+pakai", re.I)
BHP_YES = re.compile(r"(?<!tidak )(?<!belum )termasuk\s+(biaya\s+)?BHP", re.I)
KELAS_STD = {"iii": "III", "ii": "II", "i": "I", "kelas iii": "III", "kelas ii": "II", "kelas i": "I",
             "kelas utama": "Utama", "vvip": "VVIP", "vip": "VIP", "presiden suite": "Presiden Suite",
             "one day": "ODS", "one day surgery": "ODS", "icu": "ICU", "hcu": "HCU", "nicu": "NICU",
             "picu": "PICU", "semua kelas": "Semua kelas"}


def std_kelas(s):
    t = re.sub(r"\s+", " ", s.strip().lower())
    if t in KELAS_STD:
        return KELAS_STD[t]
    if t.startswith("vip"):
        return "VIP " + t[3:].strip().title() if t[3:].strip() else "VIP"
    if "presiden" in t:
        return "Presiden Suite"
    return s.strip()


def extract_doc(pdf_path, rs_id, dok_id, prefix, start_page):
    rows, blocks = [], []
    block = dict(id=0, kelas="", text="", top=True, section=0)
    blocks.append(block)
    category, pending, parent = "", None, ""
    with pdfplumber.open(pdf_path) as pdf:
        for pno in range(start_page - 1, len(pdf.pages)):
            for raw in (pdf.pages[pno].extract_text() or "").splitlines():
                line = fix_numbers(raw.strip())
                if not line:
                    continue
                if (MAJOR.match(line) and not PRICE_RE.search(line)
                        and not re.search(r"\b(tidak|ditambah|sebagaimana|adalah|dikenakan)\b", line)):
                    km = KELAS_IN_HEAD.search(line)
                    top = bool(re.match(r"^[a-z]\.\s+LAYANAN", line)) or line.startswith("Paragraf")
                    block = dict(id=len(blocks), kelas=km.group(1).upper() if km else "", text="",
                                 top=top or not blocks, section=(len(blocks) if top else block.get("section", 0)))
                    blocks.append(block)
                block["text"] += " " + line
                m = TRAIL_PRICES.search(line)
                if not m:
                    body = NUMBERING.sub("", line).strip(" :-.")
                    if is_header(body):
                        category, pending = body[:60], None
                    elif NUMBERING.match(line) and len(body) >= 3:
                        pending = body
                    continue
                name = NUMBERING.sub("", line[: m.start()].strip(" :-.")).strip(" :-.")
                prices = [p for p in (to_int(t) for t in PRICE_RE.findall(m.group(1))) if 1_000 <= p <= 200_000_000]
                if not prices:
                    continue
                if len(re.sub(r"[^A-Za-z]", "", name)) < 3 and pending:
                    name = pending
                pending = None
                if len(re.sub(r"[^A-Za-z]", "", name)) < 3:
                    continue
                flags = []
                kelas = block["kelas"]
                nama = name
                if KELAS_ROW.match(name):
                    kelas = std_kelas(name)
                    if parent:
                        nama = parent
                        flags.append("nama_dari_baris_atas")
                    else:
                        flags.append("nama_terpotong")
                else:
                    parent = name
                if FRAGMENT.match(nama):
                    flags.append("nama_terpotong")
                if re.search(r"(^|\s)\.\d{3}", raw):
                    flags.append("harga_ambigu")
                rows.append(dict(
                    rs_id=rs_id, dokumen_id=dok_id, halaman=pno + 1, kategori_asli=category,
                    nama_asli=nama, kelas=kelas or "Non-kelas", komponen="total",
                    n_kolom_harga=len(prices), harga=prices[-1], sumber_harga="langsung",
                    golongan="", paket_id="", metode_ekstraksi="pdf_teks",
                    _blok=block["id"], _flags=flags, baris_mentah=raw.strip()))
    # Status BHP: catatan "Komponen tarif ... kelas X ..." bisa muncul di akhir bagian,
    # sesudah tabel lain. Terapkan ke blok terdekat sebelumnya dengan kelas X di bagian yang sama.
    def status(txt):
        return "tidak" if BHP_NO.search(txt) else ("ya" if BHP_YES.search(txt) else None)
    bhp = {}
    for b in blocks:
        segs = re.split(r"(?=Komponen tarif)", b["text"])
        for seg in segs:
            st = status(seg)
            if not st:
                continue
            km = re.match(r"Komponen tarif[^:]{0,80}?kelas\s+(III|II|I)\b", seg, re.I)
            target = b["id"]
            if km and b["kelas"] != km.group(1).upper():
                for prev in reversed(blocks[: b["id"]]):
                    if prev["section"] != b["section"]:
                        break
                    if prev["kelas"] == km.group(1).upper():
                        target = prev["id"]
                        break
            bhp.setdefault(target, st)
    bhp = {b["id"]: bhp.get(b["id"], "tidak_jelas") for b in blocks}
    for r in rows:
        r["termasuk_bhp"] = bhp[r["_blok"]]
    return rows


def golongan_rows():
    gt = pd.read_csv(f"{OUT}/rembang_golongan_tarif.csv")
    # sel ODS non operatif = salah baca (baris dari tabel lain), dibuang
    gt = gt[~((gt.jenis == "non operatif") & (gt.kelas == "One Day Surgery"))]
    gt["golongan_id"] = ("GOL-" + gt.jenis.str.replace(" ", "_") + "-" + gt.golongan.str.replace(" ", "_")).str.upper()
    gt_out = pd.DataFrame(dict(
        dokumen_id="PERBUP-REMBANG-16-2023", golongan_id=gt.golongan_id,
        golongan=gt.jenis.str.title() + " / " + gt.golongan.str.title(),
        kelas=[std_kelas(k) if k not in ("VIP Pratama & Madya", "VIP Utama", "One Day Surgery") else
               {"VIP Pratama & Madya": "VIP Pratama/Madya", "VIP Utama": "VIP Utama", "One Day Surgery": "ODS"}[k]
               for k in gt.kelas],
        komponen="total", harga=gt.total, termasuk_bhp="tidak", halaman=gt.page))
    ga = pd.read_csv(f"{OUT}/rembang_golongan_anggota.csv")
    ga["golongan_id"] = ("GOL-" + ga.jenis.str.replace(" ", "_") + "-" + ga.golongan.str.replace(" ", "_")).str.upper()
    rows = [dict(rs_id="RSUD-REMBANG-SOETRASNO", dokumen_id="PERBUP-REMBANG-16-2023", halaman=r.page,
                 kategori_asli=f"Tindakan medis {r.jenis}", nama_asli=r.nama_asli, kelas="",
                 komponen="total", n_kolom_harga=0, harga=None, sumber_harga="via_golongan",
                 golongan=r.golongan_id, paket_id="", metode_ekstraksi="pdf_teks",
                 termasuk_bhp="tidak", _flags=[] if r.golongan_id in set(gt_out.golongan_id) else ["golongan_tanpa_tarif"],
                 baris_mentah=f"{r.jenis} / {r.golongan}: {r.nama_asli}") for r in ga.itertuples()]
    return gt_out, rows


def main():
    rows = extract_doc(f"{BASE}/raw_pdf/cianjur_cimacan_3_2025.pdf", "RSUD-KAB-CIANJUR-KLS-C",
                       "PERBUP-CIANJUR-3-2025", "CJR25", 7)
    rows += extract_doc(f"{BASE}/raw_pdf/rembang16_2023.pdf", "RSUD-REMBANG-SOETRASNO",
                        "PERBUP-REMBANG-16-2023", "RBG23", 9)
    gol, grows = golongan_rows()
    df = pd.DataFrame(rows + grows)
    df["nama_norm"] = df.nama_asli.map(norm_name)
    df["kategori_std"] = [std_category(k, n) for k, n in zip(df.kategori_asli, df.nama_norm)]
    df["satuan"] = ""

    # QC lintas baris
    key = ["rs_id", "nama_norm", "kategori_asli", "kelas", "harga"]
    dup = df.duplicated(key, keep="first") & df.harga.notna()
    df.loc[dup, "_flags"] = df.loc[dup, "_flags"].map(lambda f: f + ["duplikat"])
    order = {"III": 0, "II": 1, "I": 2}
    d3 = df[df.kelas.isin(order) & df.harga.notna()].copy()
    d3["o"] = d3.kelas.map(order)
    for (rs, n), g in d3.groupby(["rs_id", "nama_norm"]):
        g = g.sort_values("o")
        if g.kelas.nunique() > 1 and (g.groupby("o").harga.min().diff().dropna() < 0).any():
            for i in g.index:
                df.at[i, "_flags"] = df.at[i, "_flags"] + ["urutan_kelas_aneh"]
    df["flag_qc"] = df["_flags"].map(lambda f: ";".join(dict.fromkeys(f)) or "ok")

    pref = {"RSUD-KAB-CIANJUR-KLS-C": "CJR25", "RSUD-REMBANG-SOETRASNO": "RBG23"}
    df["tarif_id"] = [f"{pref[r]}-{i:05d}" for i, r in zip(df.groupby("rs_id").cumcount() + 1, df.rs_id)]
    cols = ["tarif_id", "rs_id", "dokumen_id", "halaman", "kategori_asli", "nama_asli", "nama_norm",
            "kategori_std", "golongan", "kelas", "komponen", "termasuk_bhp", "satuan", "harga",
            "sumber_harga", "paket_id", "metode_ekstraksi", "flag_qc", "n_kolom_harga", "baris_mentah"]
    tarif = df[cols]

    pem = (tarif.groupby("nama_norm").agg(kategori_std=("kategori_std", "first"), contoh_nama_asli=("nama_asli", "first"),
                                         jumlah_rs=("rs_id", "nunique"), jumlah_baris=("tarif_id", "size"))
           .reset_index())
    pem = pem.assign(kode_sistem="", kode="", nama_kode="", skor="", status="belum", reviewer="", catatan="")

    path = f"{OUT}/tarif_standar_pilot.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        tarif.to_excel(xw, sheet_name="tarif", index=False)
        pd.DataFrame(RS).to_excel(xw, sheet_name="rumah_sakit", index=False)
        pd.DataFrame(DOK).to_excel(xw, sheet_name="dokumen", index=False)
        gol.to_excel(xw, sheet_name="golongan_tarif", index=False)
        pem.to_excel(xw, sheet_name="pemetaan", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                w = max(len(str(c.value or "")) for c in list(col)[:300])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 48)
    tarif.to_csv(f"{OUT}/tarif_standar_pilot.csv", index=False)

    print(f"-> {path}")
    print("baris tarif:", len(tarif), "| per RS:", tarif.groupby("rs_id").size().to_dict())
    print("kelas:", tarif.kelas.value_counts().to_dict())
    print("termasuk_bhp:", tarif.groupby(["rs_id", "termasuk_bhp"]).size().to_dict())
    print("flag_qc:", tarif.flag_qc.str.split(";").explode().value_counts().to_dict())
    print("golongan_tarif sel:", len(gol), "| pemetaan nama unik:", len(pem))


if __name__ == "__main__":
    main()
