"""PDF Perbup -> Excel tarif standar (long format, 6 sheet).

Sheet: tarif, rumah_sakit, dokumen, dokumen_rs, golongan_tarif, pemetaan.
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
ROOT = os.path.join(BASE, "..")

RS = [
    dict(rs_id="RSUD-CIMACAN", nama_rs="RSUD Cimacan", kepemilikan="kab/kota", kelas_rs="C",
         kab_kota="Kabupaten Cianjur", provinsi="Jawa Barat",
         catatan="Satu-satunya RSUD Kelas C Cianjur yang sudah dicek; RSUD lain ditambah lewat sheet dokumen_rs"),
    dict(rs_id="RSUD-REMBANG-SOETRASNO", nama_rs="RSUD dr. R. Soetrasno", kepemilikan="kab/kota",
         kelas_rs="", kab_kota="Kabupaten Rembang", provinsi="Jawa Tengah",
         catatan="Kelas RS belum diverifikasi"),
]
# Satu dokumen bisa berlaku untuk beberapa RS (Perbup Cianjur: semua RSUD Kelas C di kabupaten itu).
# Tarif disimpan per DOKUMEN, sehingga RS baru cukup ditambah satu baris di sini, tanpa menggandakan tarif.
DOKUMEN_RS = [
    dict(dokumen_id="PERBUP-CIANJUR-3-2025", rs_id="RSUD-CIMACAN", dasar="Perbup berlaku untuk RSUD Kelas C Kab. Cianjur"),
    dict(dokumen_id="PERBUP-REMBANG-16-2023", rs_id="RSUD-REMBANG-SOETRASNO", dasar="Judul Perbup menyebut RS ini"),
]
DOK = [
    dict(dokumen_id="PERBUP-CIANJUR-3-2025", jenis="Perbup", nomor="3", cakupan="Semua RSUD Kelas C di Kabupaten Cianjur",
         tahun=2025, tgl_ditetapkan="2025-01-13", tgl_berlaku="2025-01-14", status="berlaku (per unduhan)",
         mengubah_dokumen_id="", jenis_pdf="teks", halaman_lampiran_mulai=7,
         url="https://rsudcimacan.cianjurkab.go.id/public/assets/pdf/PB%203%202025%20TARIF%20KLS%20C%20terupdate.pdf",
         tgl_unduh="2026-11-18",
         aturan_umum="Sebagian besar bagian: tarif ditambah alat dan bahan (BHP di luar tarif)."),
    dict(dokumen_id="PERBUP-REMBANG-16-2023", jenis="Perbup", nomor="16", cakupan="RSUD dr. R. Soetrasno",
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


PRICE_TOK = re.compile(r"(?:Rp\.?\s*)?\d{1,3}(?:[.,]\d{3})+(?:,-|,00)?")


def clean_name(name):
    """Bersihkan sisa OCR/tabel: garis tegak, harga yang ikut terbaca di nama, 'Ill' untuk III."""
    name = name.replace("|", " ").replace("{", " ")
    name = PRICE_TOK.sub(" ", name)
    name = re.sub(r"\bRp\.?\s*$", " ", name)
    name = re.sub(r"\b(I[lI1]{2})\b", "III", name)
    name = re.sub(r"\b(I[l1])\b", "II", name)
    return re.sub(r"\s+", " ", name).strip(" :-.;")


def find_annex_page(pdf):
    """Halaman awal tabel tarif: yang lebih awal di antara (a) halaman pertama yang diawali LAMPIRAN dan
    diikuti tabel harga, dan (b) halaman pertama dengan >= 5 angka harga. (b) mencegah tabel terlewat
    bila kata LAMPIRAN baru muncul di halaman belakang (mis. Lampiran II)."""
    texts = [(p.extract_text() or "") for p in pdf.pages]
    cnt = [len(PRICE_TOK.findall(t)) for t in texts]
    lamp = next((i + 1 for i, t in enumerate(texts)
                 if re.search(r"\bLAMPIRAN\b", t[:400], re.I) and sum(cnt[i:i + 2]) >= 5), None)
    first = next((i + 1 for i, c in enumerate(cnt) if c >= 5), None)
    cands = [x for x in (lamp, first) if x]
    return min(cands) if cands else 1


# --- format kelas berjajar ke samping & angka terpecah spasi -------------------------------
SPLIT_NUM = re.compile(r"(?<![\d.,])(\d) (\d{1,2}(?:[.,]\d{3})+)(?!\d)")
CLASS_TOK = re.compile(
    r"(?:Kela[s$5]|K[l1]as|Kls)\s*(III|II|I|111|11|1|Ill|Il|l)\b|VVIP|VIP\s*[AB]\b|VIP|Utama|Perinatal|Isolasi|"
    r"PICU\s*/\s*NICU|ICU\s*/?\s*ICCU|ICU|HCU", re.I)
GROUP_TOK = re.compile(r"KOMPONEN\s+TARIF\s+(KELAS|UTAMA|VVIP|VIP\s*[AB]?)", re.I)
TABLE_HEAD = re.compile(r"\b(JENIS|NO)\b.*\b(TARIF|JASA|TOTAL|JUMLAH|LAYANAN|PELAYANAN|PEMERIKSAAN|TINDAKAN)\b", re.I)
ROMAN = {"III": "III", "111": "III", "ILL": "III", "II": "II", "11": "II", "IL": "II", "I": "I", "1": "I", "L": "I"}


def header_classes(line):
    out = []
    for m in CLASS_TOK.finditer(line):
        if m.group(1):
            out.append(ROMAN.get(m.group(1).upper(), m.group(1)))
        else:
            t = re.sub(r"\s+", "", m.group(0)).upper()
            out.append({"UTAMA": "Utama", "PERINATAL": "Perinatal", "ISOLASI": "Isolasi"}.get(t, t.replace("VIPA", "VIP A").replace("VIPB", "VIP B")))
    return out


def header_groups(line):
    lab = {"KELAS": "Kelas III-I", "UTAMA": "Utama"}
    return [lab.get(re.sub(r"\s+", " ", g.upper()), re.sub(r"\s+", " ", g.upper())) for g in GROUP_TOK.findall(line)]


def _close(a, b):
    return abs(a - b) <= max(2, 0.005 * max(a, b))


def total_first(p):
    """Urutan kolom total, sarana, pelayanan (total di depan)."""
    return len(p) >= 3 and _close(sum(p[1:]), p[0])


def sum_ok(p):
    if len(p) >= 3 and _close(sum(p[:-1]), p[-1]):
        return True
    return len(p) >= 6 and len(p) % 3 == 0 and all(_close(p[i] + p[i + 1], p[i + 2]) for i in range(0, len(p), 3))


def parse_prices(line):
    m = TRAIL_PRICES.search(line)
    if not m:
        return None, [], False
    toks = PRICE_RE.findall(m.group(1))
    lead0 = any(re.match(r"0[.,]?\d", t) for t in toks)
    return m, [p for p in (to_int(t) for t in toks) if 1_000 <= p <= 200_000_000], lead0


LOCAL_BHP = re.compile(r"(belum|tidak)\s+termasuk\s+(biaya\s+)?BHP", re.I)
QUOTE_MARK = re.compile(r"[\"\u201c\u201d*]")


def extract_doc(pdf_path, dok_id, start_page=None, bhp_default=""):
    rows, blocks = [], []
    seg_start = 0
    block = dict(id=0, kelas="", text="", top=True, section=0)
    blocks.append(block)
    category, pending, parent = "", None, ""
    cls_header, grp_header = [], []
    with pdfplumber.open(pdf_path) as pdf:
        if not start_page:
            start_page = find_annex_page(pdf)
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
                    seg_start = len(rows)
                # catatan kaki lokal ("Belum termasuk BHP" bertanda kutip): hanya untuk tabel ini
                lb = LOCAL_BHP.search(line)
                is_foot = bool(lb) and not re.search(r"kontras", line[:lb.start()], re.I) and (
                    QUOTE_MARK.search(line[:lb.start() + 1]) or lb.start() < 3 or re.match(r"(Ket|Catatan)\b", line, re.I))
                if is_foot:
                    seg = rows[seg_start:]
                    marked = [r for r in seg if QUOTE_MARK.search(r["baris_mentah"])]
                    for r in (marked or seg):
                        r.setdefault("_bhp_lokal", "tidak")
                else:
                    block["text"] += " " + line
                m, prices, lead0 = parse_prices(line)
                merged = SPLIT_NUM.sub(r"\1\2", line)
                if merged != line:
                    m2, p2, _ = parse_prices(merged)
                    if p2 and (lead0 or (sum_ok(p2) and not sum_ok(prices))
                               or (cls_header and len(p2) == len(cls_header) != len(prices))):
                        line, m, prices = merged, m2, p2
                if not m:
                    # judul tabel baru tanpa kelas -> lupakan judul kelas sebelumnya
                    if TABLE_HEAD.search(line):
                        seg_start = len(rows)
                    if (TABLE_HEAD.search(line) and len(header_classes(line)) < 3 and not header_groups(line)
                            and len(re.findall(r"\b(tarif|jumlah)\b", line, re.I)) < 2):
                        cls_header, grp_header = [], []
                    if len(header_groups(line)) >= 2:
                        grp_header, cls_header = header_groups(line), []
                    elif len(header_classes(line)) >= 3:
                        cls_header, grp_header = header_classes(line), []
                    body = NUMBERING.sub("", line).strip(" :-.")
                    if is_header(body):
                        category, pending = body[:60], None
                    elif NUMBERING.match(line) and len(body) >= 3:
                        pending = body
                    continue
                name = clean_name(NUMBERING.sub("", clean_name(line[: m.start()])).strip(" :-."))
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
                if re.search(r"(^|\s)(sebesar|adalah|yaitu|ditetapkan|dikenakan|setinggi|paling (tinggi|rendah)|"
                             r"maksimal|minimal|ayat|pasal)\s*$", nama, re.I):
                    continue  # kalimat pasal, bukan item tarif
                if FRAGMENT.match(nama):
                    flags.append("nama_terpotong")
                if re.search(r"(^|\s)\.\d{3}", raw):
                    flags.append("harga_ambigu")
                # tentukan arti kolom harga
                pairs = None  # [(kelas, harga)]
                if grp_header and len(prices) == 3 * len(grp_header) and sum_ok(prices):
                    pairs = [(g, prices[3 * k + 2]) for k, g in enumerate(grp_header)]
                elif cls_header and len(prices) == len(cls_header) and len(prices) >= 2 and not sum_ok(prices):
                    pairs = list(zip(cls_header, prices))
                if pairs:
                    flags = flags + ["dari_kolom_kelas"]
                elif (len(prices) >= 6 and len(prices) % 3 == 0 and sum_ok(prices)
                      and not _close(sum(prices[:-1]), prices[-1])):
                    # beberapa grup (sarana, pelayanan, total) berjajar tanpa judul kelas yang terbaca
                    pairs = [(f"grup {k + 1} (kelas tak diketahui)", prices[3 * k + 2]) for k in range(len(prices) // 3)]
                    flags.append("kelas_grup_tanpa_judul")
                elif total_first(prices) and not sum_ok(prices):
                    pairs = [(kelas or "Non-kelas", prices[0])]
                    flags.append("total_di_depan")
                else:
                    pairs = [(kelas or "Non-kelas", prices[-1])]
                    if len(prices) == 3 and not sum_ok(prices):
                        flags.append("komponen_tidak_jumlah")
                    elif len(prices) >= 4 and not sum_ok(prices):
                        flags.append("kolom_harga_tak_dikenal")
                for kel, harga in pairs:
                    rows.append(dict(
                        dokumen_id=dok_id, halaman=pno + 1, kategori_asli=category,
                        nama_asli=nama, kelas=kel or "Non-kelas", komponen="total",
                        n_kolom_harga=len(prices), harga=harga, sumber_harga="langsung",
                        golongan="", paket_id="", metode_ekstraksi="pdf_teks",
                        _blok=block["id"], _flags=list(flags), baris_mentah=raw.strip()))
    # Status BHP: catatan "Komponen tarif ... kelas X ..." bisa muncul di akhir bagian,
    # sesudah tabel lain. Terapkan ke blok terdekat sebelumnya dengan kelas X di bagian yang sama.
    def status(txt):
        for mm in BHP_NO.finditer(txt):
            if re.search(r"kontras", txt[max(0, mm.start() - 40):mm.start()], re.I):
                continue
            if re.search(r"(tarif|biaya|komponen)", txt[max(0, mm.start() - 150):mm.end()], re.I):
                return "tidak"
        for mm in BHP_YES.finditer(txt):
            if re.search(r"(tarif|biaya|komponen)", txt[max(0, mm.start() - 150):mm.start()], re.I):
                return "ya"
        return None
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
        if r.get("_bhp_lokal"):
            r["termasuk_bhp"], r["sumber_bhp"] = r.pop("_bhp_lokal"), "catatan_lokal"
        elif bhp[r["_blok"]] != "tidak_jelas":
            r["termasuk_bhp"], r["sumber_bhp"] = bhp[r["_blok"]], "catatan_bagian"
        elif bhp_default:
            r["termasuk_bhp"], r["sumber_bhp"] = bhp_default, "pasal_dokumen"
        else:
            r["termasuk_bhp"], r["sumber_bhp"] = "tidak_jelas", ""
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
    rows = [dict(dokumen_id="PERBUP-REMBANG-16-2023", halaman=r.page,
                 kategori_asli=f"Tindakan medis {r.jenis}", nama_asli=r.nama_asli, kelas="",
                 komponen="total", n_kolom_harga=0, harga=None, sumber_harga="via_golongan",
                 golongan=r.golongan_id, paket_id="", metode_ekstraksi="pdf_teks",
                 termasuk_bhp="tidak", sumber_bhp="catatan_bagian", _flags=[] if r.golongan_id in set(gt_out.golongan_id) else ["golongan_tanpa_tarif"],
                 baris_mentah=f"{r.jenis} / {r.golongan}: {r.nama_asli}") for r in ga.itertuples()]
    return gt_out, rows


def load_config(only=None):
    cfg = pd.read_csv(f"{BASE}/config/dokumen.csv", dtype=str).fillna("")
    cfg = cfg[cfg.aktif == "ya"]
    if only:
        cfg = cfg[cfg.dokumen_id.isin(only)]
    extra_dok = {d["dokumen_id"]: d for d in DOK}
    extra_rs = {r["rs_id"]: r for r in RS}
    dok = []
    for r in cfg.itertuples():
        d = dict(dokumen_id=r.dokumen_id, jenis=r.jenis, nomor=r.nomor, tahun=r.tahun, cakupan=r.cakupan,
                 tgl_berlaku=r.tgl_berlaku, file=os.path.basename(r.file), catatan=r.catatan,
                 bhp_dokumen=getattr(r, "bhp_dokumen", ""), bukti_bhp=getattr(r, "bukti_bhp", ""))
        for k, v in extra_dok.get(r.dokumen_id, {}).items():
            d.setdefault(k, v)
        dok.append(d)
    rs = []
    for rid, g in cfg.groupby("rs_id", sort=False):
        r = g.iloc[0]
        rs.append(dict(rs_id=rid, nama_rs=r.nama_rs, kepemilikan="kab/kota", kelas_rs=r.kelas_rs,
                       kab_kota=r.kab_kota, provinsi=r.provinsi,
                       catatan=extra_rs.get(rid, {}).get("catatan", "Kelas RS belum diverifikasi" if not r.kelas_rs else "")))
    drs = [dict(dokumen_id=r.dokumen_id, rs_id=r.rs_id, dasar=f"Cakupan: {r.cakupan}") for r in cfg.itertuples()]
    return cfg, dok, rs, drs


def main(out_name="tarif_standar.xlsx", only=None):
    cfg, DOK_OUT, RS_OUT, DRS_OUT = load_config(only)
    rows = []
    for r in cfg.itertuples():
        rows += extract_doc(os.path.join(ROOT, r.file), r.dokumen_id, int(r.hlm_lampiran) if r.hlm_lampiran else None,
                            getattr(r, "bhp_dokumen", ""))
    if "PERBUP-REMBANG-16-2023" in set(cfg.dokumen_id):
        gol, grows = golongan_rows()
    else:
        gol, grows = pd.DataFrame(), []
    df = pd.DataFrame(rows + grows)
    df["nama_norm"] = df.nama_asli.map(norm_name)
    df["kategori_std"] = [std_category(k, n) for k, n in zip(df.kategori_asli, df.nama_norm)]
    df["satuan"] = ""

    # QC lintas baris
    key = ["dokumen_id", "nama_norm", "kategori_asli", "kelas", "harga"]
    dup = df.duplicated(key, keep="first") & df.harga.notna()
    df.loc[dup, "_flags"] = df.loc[dup, "_flags"].map(lambda f: f + ["duplikat"])
    order = {"III": 0, "II": 1, "I": 2}
    d3 = df[df.kelas.isin(order) & df.harga.notna()].copy()
    d3["o"] = d3.kelas.map(order)
    for (dk, n), g in d3.groupby(["dokumen_id", "nama_norm"]):
        g = g.sort_values("o")
        if g.kelas.nunique() > 1 and (g.groupby("o").harga.min().diff().dropna() < 0).any():
            for i in g.index:
                df.at[i, "_flags"] = df.at[i, "_flags"] + ["urutan_kelas_aneh"]
    df["flag_qc"] = df["_flags"].map(lambda f: ";".join(dict.fromkeys(f)) or "ok")

    pref = {d: re.sub(r"[^A-Z0-9]", "", d.split("-")[1])[:6] + d[-2:] for d in df.dokumen_id.unique()}
    pref.update({"PERBUP-CIANJUR-3-2025": "CJR25", "PERBUP-REMBANG-16-2023": "RBG23"})
    df["tarif_id"] = [f"{pref[d]}-{i:05d}" for i, d in zip(df.groupby("dokumen_id").cumcount() + 1, df.dokumen_id)]
    cols = ["tarif_id", "dokumen_id", "halaman", "kategori_asli", "nama_asli", "nama_norm",
            "kategori_std", "golongan", "kelas", "komponen", "termasuk_bhp", "sumber_bhp", "satuan", "harga",
            "sumber_harga", "paket_id", "metode_ekstraksi", "flag_qc", "n_kolom_harga", "baris_mentah"]
    tarif = df[cols]

    pem = (tarif.groupby("nama_norm").agg(kategori_std=("kategori_std", "first"), contoh_nama_asli=("nama_asli", "first"),
                                         jumlah_dokumen=("dokumen_id", "nunique"), jumlah_baris=("tarif_id", "size"))
           .reset_index())
    pem = pem.assign(kode_sistem="", kode="", nama_kode="", skor="", status="belum", reviewer="", catatan="")

    path = f"{OUT}/{out_name}"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        tarif.to_excel(xw, sheet_name="tarif", index=False)
        pd.DataFrame(RS_OUT).to_excel(xw, sheet_name="rumah_sakit", index=False)
        pd.DataFrame(DOK_OUT).to_excel(xw, sheet_name="dokumen", index=False)
        pd.DataFrame(DRS_OUT).to_excel(xw, sheet_name="dokumen_rs", index=False)
        gol.to_excel(xw, sheet_name="golongan_tarif", index=False)
        pem.to_excel(xw, sheet_name="pemetaan", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                w = max(len(str(c.value or "")) for c in list(col)[:300])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 48)
    tarif.to_csv(f"{OUT}/{out_name.replace('.xlsx', '.csv')}", index=False)

    print(f"-> {path}")
    print("baris tarif:", len(tarif), "| per dokumen:", tarif.groupby("dokumen_id").size().to_dict())
    print("kelas:", tarif.kelas.value_counts().to_dict())
    print("termasuk_bhp:", tarif.groupby(["dokumen_id", "termasuk_bhp"]).size().to_dict())
    print("flag_qc:", tarif.flag_qc.str.split(";").explode().value_counts().to_dict())
    print("golongan_tarif sel:", len(gol), "| pemetaan nama unik:", len(pem))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tarif_standar.xlsx")
    ap.add_argument("--only", nargs="*", help="dokumen_id yang diproses (default: semua yang aktif)")
    a = ap.parse_args()
    main(a.out, a.only)
