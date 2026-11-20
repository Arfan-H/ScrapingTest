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
# kata "kelas" termasuk salah OCR yang sering muncul (Ketas, Kelss, Klas, Kls)
KELAS_W = r"(?:kelas|kelss|ketas|kclas|kelaa|klas|kls)"
KELAS_ROW = re.compile(
    rf"^({KELAS_W}\s*(iii|ill|ii|i)\s*[ab]?(\s*/\s*(rawat jalan|poli\w*|igd|iii|ii|i))?|({KELAS_W}\s*)?uta\.?ma(\s*(ii|i|[ab]))?|iii|ii|i|"
    r"perinatologi|perinatal|isolasi|igd|iw|iccu|ruang\s+bersalin|vk|"
    rf"({KELAS_W}\s*)?vvip|({KELAS_W}\s*)?vip(\s*(pratama|madya|utama|a|b))?(\s*&\s*madya)?|"
    r"presiden suite|vvip\s*/\s*presiden suite|icu|hcu|picu|nicu|semua kelas|one day( surgery)?)$", re.I)
# kelas di ujung nama ("Kecil VIP", "Rawat Inap Kelas II")
KELAS_SUFFIX = re.compile(rf"^(.*?[A-Za-z].*?)\s*[-,]?\s+((?:{KELAS_W}\s*(?:III|II|I|utama|vvip|vip)\b(?:\s*[AB]\b)?)|"
                          r"super\s*vip|vvip|vip(?:\s*[AB])?)$", re.I)
FRAGMENT = re.compile(
    r"^((ringan|sedang|berat|kecil|besar|khusus|sederhana|canggih)(\s+([A-D1-4]|i{1,3}|iv|hi|ill|lll|il))?|utama|tindakan|pemeriksaan|"
    r"reguler( / non)?|spesialis|subspesialis|lengkap|pagi|sore|umum|(dengan|tanpa) rujukan|pasien (baru|lama)|"
    r"baru|lama|anak|dewasa|bayi|elektif|cito)$", re.I)
BHP_NO = re.compile(r"(tidak|belum)\s+termasuk[^.]{0,80}\bBHP\b|ditambah\s*alat\s*dan\s*bahan|"
                    r"diluar\s+dari\s+obat\s+dan\s+barang\s+habis\s+pakai", re.I)
BHP_YES = re.compile(r"(?<!tidak )(?<!belum )termasuk\s+(biaya\s+)?BHP", re.I)
KELAS_STD = {"iii": "III", "ii": "II", "i": "I", "kelas iii": "III", "kelas ii": "II", "kelas i": "I",
             "kelas utama": "Utama", "utama": "Utama", "vvip": "VVIP", "vip": "VIP", "presiden suite": "Presiden Suite",
             "one day": "ODS", "one day surgery": "ODS", "icu": "ICU", "hcu": "HCU", "nicu": "NICU",
             "picu": "PICU", "semua kelas": "Semua kelas"}


# penomoran judul yang tidak tertangkap NUMBERING: "II Rawat Jalan", "A.1.1.4.1 TMO ..."
PAREN_NUM = re.compile(r"^\s*\(?(?:[a-z]|\d{1,3}|[ivx]{1,4})\)\.?\s+")  # "a) ", "2) ", "(1) "
HEAD_NUM = re.compile(r"^\s*(?:[IVX]{1,4}|[A-Z](?:\.\d+)+\.?)\s+(?=[A-Za-z(])")


def std_kelas(s):
    t = re.sub(r"\s+", " ", s.strip().lower())
    t = re.sub(rf"^{KELAS_W}\s*(?=(iii|ii|i|utama|vvip|vip)$)", "kelas ", t)
    t = re.sub(rf"^{KELAS_W}\b", "kelas", t)
    t = re.sub(r"\bill$", "iii", t)
    t = re.sub(r"[()]", "", t)
    t = re.sub(r"\s*/\s*(rawat jalan|poli\w*|igd)$", "", t)
    m = re.fullmatch(r"kelas\s*(iii|ii|i)\s*/\s*(iii|ii|i)", t)
    if m:
        return f"{m.group(1).upper()}-{m.group(2).upper()}"
    m = re.fullmatch(r"kelas\s*(iii|ii|i)\s*([ab])", t)
    if m:
        return f"{m.group(1).upper()} {m.group(2).upper()}"
    t = re.sub(r"^kelas\s+(vvip|vip|utama)", r"\1", t)
    t = t.replace("uta.ma", "utama")
    t = re.sub(r"^kelas\s+utama", "utama", t)
    m = re.fullmatch(r"utama\s*(ii|i|[ab])", t)
    if m:
        return f"Utama {m.group(1).upper()}"
    if t in ("igd", "iw", "vk", "iccu"):
        return t.upper()
    if t in ("perinatologi", "perinatal", "isolasi", "ruang bersalin"):
        return t.title()
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
    # huruf kode kolom kiri yang menempel: "f 4 Pasang ...", "D 7. Pelayanan ...", "a Sendi Bahu ..."
    name = re.sub(r"^\s*[A-Za-z]\s+(?=\d{1,3}\.?\s)", "", name)
    name = re.sub(r"^\s*[a-z]\s+(?=[A-Z])", "", name)
    name = re.sub(r"^\s*[a-z],\s+(?=[A-Za-z])", "", name)  # penomoran "b, Jasa medis"
    name = PRICE_TOK.sub(" ", name)
    name = re.sub(r"\bRp\.?\s*$", " ", name)
    name = re.sub(r"(?<![A-Za-z])R[pPo]\.?(?![A-Za-z])", " ", name)  # sisa 'Rp'/'RP' dari kolom harga
    name = re.sub(r"\b(I[lI1]{2})\b", "III", name)
    name = re.sub(r"\b(I[l1])\b", "II", name)
    name = re.sub(r"\s+per\s+(tindakan|hari|kali|pemeriksaan|jam|paket|orang|lembar|sesi|unit)\s*$", "", name, flags=re.I)
    name = re.sub(r"(^|\s)/\s*tindakan\b", " ", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" :-.;,")


DOUBLED = re.compile(r"(?:([A-Za-z])\1){3,}")


def lines_by_overlap(page):
    return lines_from_words(page.extract_words(x_tolerance=1.5, y_tolerance=3, keep_blank_chars=False))


def lines_from_words(words):
    """Susun baris dari kata: kata masuk baris yang sama bila kotaknya tumpang-tindih vertikal >= 50% dari tinggi
    kata yang lebih pendek. Angka yang tercetak sedikit naik/turun (mis. kolom total 3 pt lebih tinggi) tetap satu
    baris dengan namanya, padahal extract_text bawaan (toleransi posisi atas 3 pt) memisahkannya."""
    words = list(words)
    words.sort(key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"]))
    num = re.compile(r"^(?:Rp\.?)?[\d.,:;\-]+$", re.I)
    lines = []  # [top, bottom, [words], semua_angka]
    for w in words:
        h = w["bottom"] - w["top"]
        w_num = bool(num.match(w["text"]))
        best = None
        for ln in lines[-4:]:
            ov = min(ln[1], w["bottom"]) - max(ln[0], w["top"])
            lh = ln[1] - ln[0]
            # angka yang tercetak naik/turun boleh longgar (50%); teks harus hampir sejajar (75%) supaya baris
            # lanjutan nama di sel bertingkat ('kanguru)') tidak masuk ke baris berikutnya
            need = 0.5 if (w_num or ln[3]) else 0.75
            if ov >= need * min(h, lh) and (best is None or ov > best[0]):
                best = (ov, ln)
        if best:
            ln = best[1]
            ln[2].append(w)
            if ln[3] and not w_num:  # pita baris pindah ke kata teks pertama
                ln[0], ln[1], ln[3] = w["top"], w["bottom"], False
        else:
            lines.append([w["top"], w["bottom"], [w], w_num])
    lines.sort(key=lambda ln: ln[0])
    out = []
    for _, _, ws, _ in lines:
        ws.sort(key=lambda w: w["x0"])
        out.append((" ".join(w["text"] for w in ws), ws))
    return out


def garble(text):
    """Skor kerusakan teks OCR: proporsi token satu huruf, simbol aneh, atau huruf-angka bercampur."""
    toks = re.findall(r"\S+", text)
    if len(toks) < 20:
        return 0.0
    alpha = [t for t in toks if re.search(r"[A-Za-z]", t)]
    single = sum(1 for t in alpha if len(re.sub(r"[^A-Za-z]", "", t)) == 1)
    sym = sum(1 for t in toks if re.search(r"[«»~`^_{}\\]|[a-z][A-Z][a-z]|[A-Za-z]\d[A-Za-z]", t))
    return (single + sym) / len(toks)


OCR_CACHE = os.environ.get("OCR_CACHE", os.path.join(os.path.dirname(__file__), "..", "out", "bpk", "ocr_ulang"))


def load_ocr(pdf_path):
    """Kotak teks hasil ocr_ulang.py untuk file ini: {halaman: [kata]} (kosong bila tidak ada)."""
    import gzip
    import json
    f = os.path.join(OCR_CACHE, os.path.basename(pdf_path) + ".json.gz")
    if not os.path.exists(f):
        return {}
    with gzip.open(f, "rt", encoding="utf-8") as h:
        return {int(k): v for k, v in json.load(h).items()}


_VOCAB = None


def vocab_ratio(text):
    """Proporsi kata (>= 3 huruf) yang dikenal di kosakata nama layanan (pilot/config/kosakata_tarif.txt)."""
    global _VOCAB
    if _VOCAB is None:
        f = os.path.join(os.path.dirname(__file__), "..", "config", "kosakata_tarif.txt")
        _VOCAB = {ln.strip() for ln in open(f, encoding="utf-8") if ln.strip() and not ln.startswith("#")}
    ws = [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 3]
    return (sum(w in _VOCAB for w in ws) / len(ws)) if len(ws) >= 15 else None


def choose_ocr(text_lines, ocr_words):
    """Pakai baris OCR ulang bila teksnya jelas lebih bersih, angka harganya tidak banyak hilang, dan kata-katanya
    tidak lebih sering tak dikenal (OCR scan beresolusi rendah bisa 'bersih' tapi salah baca: AKOMODASI -> AKONODMSL)."""
    if not ocr_words:
        return None
    ocr_lines = lines_from_words([w for w in ocr_words if w.get("score", 1) >= 0.5])
    t_old = "\n".join(t for t, _ in text_lines)
    t_new = "\n".join(t for t, _ in ocr_lines)
    n_old, n_new = len(PRICE_TOK.findall(t_old)), len(PRICE_TOK.findall(t_new))
    if not (garble(t_new) + 0.02 < garble(t_old) and n_new >= 0.8 * n_old):
        return None
    v_old, v_new = vocab_ratio(t_old), vocab_ratio(t_new)
    if v_old is not None and v_new is not None and v_new < v_old - 0.05:
        return None
    return ocr_lines


def page_lines(page):
    """Baris halaman sebagai [(teks, kata)], kata = dict(text, x0, x1, top, bottom) untuk membaca posisi kolom."""
    t = page.extract_text() or ""
    if len(DOUBLED.findall(t)) >= 3:
        page = page.dedupe_chars(tolerance=1, extra_attrs=())
    area = float(page.width * page.height) or 1.0
    if any((im["x1"] - im["x0"]) * (im["bottom"] - im["top"]) >= 0.6 * area for im in page.images):
        # halaman scan: baris dari extract_text bawaan, kata ditempatkan menurut titik tengah vertikalnya
        words = page.extract_words()
        out = []
        for ln in page.extract_text_lines(strip=True):
            ws = [w for w in words if ln["top"] - 0.5 <= (w["top"] + w["bottom"]) / 2 <= ln["bottom"] + 0.5]
            out.append((ln["text"], sorted(ws, key=lambda w: w["x0"])))
        return out
    return lines_by_overlap(page)


def page_text(page):
    """Teks halaman (baris disusun berdasarkan tumpang-tindih vertikal kata). Huruf yang dicetak dua kali
    (efek tebal palsu, 'MMeenntteerrii') dibuang dulu; huruf kembar bergeser < 1 pt dan sering berbeda font."""
    t = page.extract_text() or ""
    if len(DOUBLED.findall(t)) >= 3:
        page = page.dedupe_chars(tolerance=1, extra_attrs=())
        t = page.extract_text() or ""
    # halaman hasil scan (gambar sehalaman + lapisan OCR): baris OCR sering miring, jadi penyusunan berdasarkan
    # tumpang-tindih bisa mencampur angka baris tetangga -> pakai extract_text bawaan
    area = float(page.width * page.height) or 1.0
    if any((im["x1"] - im["x0"]) * (im["bottom"] - im["top"]) >= 0.6 * area for im in page.images):
        return t
    return "\n".join(tx for tx, _ in lines_by_overlap(page))


def find_annex_page(pdf):
    """Halaman awal tabel tarif: yang lebih awal di antara (a) halaman pertama yang diawali LAMPIRAN dan
    diikuti tabel harga, dan (b) halaman pertama dengan >= 5 angka harga. (b) mencegah tabel terlewat
    bila kata LAMPIRAN baru muncul di halaman belakang (mis. Lampiran II)."""
    texts = [page_text(p) for p in pdf.pages]
    cnt = [len(PRICE_TOK.findall(t)) for t in texts]
    lamp = next((i + 1 for i, t in enumerate(texts)
                 if re.search(r"\bLAMPIRAN\b", t[:400], re.I) and sum(cnt[i:i + 2]) >= 5), None)
    first = next((i + 1 for i, c in enumerate(cnt) if c >= 5), None)
    cands = [x for x in (lamp, first) if x]
    return min(cands) if cands else 1


# --- format kelas berjajar ke samping & angka terpecah spasi -------------------------------
SPLIT_NUM = re.compile(r"(?<![\d.,])(\d) (\d{1,2}(?:[.,]\d{3})+)(?!\d)")
CLASS_TOK = re.compile(
    # kelas gabungan dulu ("Kelas I & II", "Kelas I/II", "Kelas II, I") -> satu kolom
    r"(?:Kela[s$58]|K[l1]as|Kls|Kalas)\s*(?P<g1>III|II|I)\s*(?:&|dan|/|,|-)\s*(?:Kelas\s*)?(?P<g2>III|II|I)\b|"
    r"(?:Kela[s$58]|K[l1]as|Kls|Kalas)\s*(?P<n>III|II|I|111|11|1|Ill|Il|l|3|2)\b|Utama\s*(?P<u>II|I)\b|Kelas\s+(?P<rs>[ABCD])\b(?!\s*\.)|Super\s*VIP|VIP\s*/\s*Utama|Utama\s*/\s*VIP|VIP\s*Utama|NON[ -]?VIP|VVIP|"
    r"VIP\s*[AB]\b|VIP|Utama|Teladan|PAV(?:ILIUN)?\b|Perinatal|Isolasi|PICU\s*/\s*NICU|ICU\s*/?\s*ICCU|ICU|HCU", re.I)
# angka romawi tanpa kata "Kelas" di baris judul tabel ("NO JENIS PEMERIKSAAN VIP I II III/POLI/IGD")
BARE_CLASS = re.compile(r"(?<![\w/])(III|II[AB]|II|I[AB]|I|Ill|VVIP|VIP\s*[AB]|VIP|Utama|ICU|HCU)(?!\w)", re.I)
HEAD_WORDS = re.compile(r"no|jenis|pelayanan|tindakan|pemeriksaan|tarif|rp|uraian|kelas|perawatan|layanan|satuan|"
                        r"jenispelayanan|nama", re.I)
GROUP_TOK = re.compile(r"KOMPONEN\s+TARIF\s+(KELAS|UTAMA|VVIP|VIP\s*[AB]?)", re.I)
TABLE_HEAD = re.compile(r"\b(JENIS|NO)\b.*\b(TARIF|JASA|TOTAL|JUMLAH|LAYANAN|PELAYANAN|PEMERIKSAAN|TINDAKAN)\b", re.I)
ROMAN = {"III": "III", "111": "III", "ILL": "III", "3": "III", "II": "II", "11": "II", "IL": "II", "2": "II",
         "I": "I", "1": "I", "L": "I"}
CLASS_LABEL = {"TELADAN": "Teladan", "PAV": "Paviliun", "PAVILIUN": "Paviliun", "UTAMA": "Utama", "PERINATAL": "Perinatal", "ISOLASI": "Isolasi", "SUPERVIP": "Super VIP",
               "VIPUTAMA": "VIP Utama", "VIP/UTAMA": "VIP/Utama", "UTAMA/VIP": "VIP/Utama", "NONVIP": "Non-VIP", "NON-VIP": "Non-VIP", "VIPA": "VIP A", "VIPB": "VIP B"}


def header_classes(line):
    out = []
    for m in CLASS_TOK.finditer(line):
        if m.group("g1"):
            out.append(f"{ROMAN[m.group('g1').upper()]}-{ROMAN[m.group('g2').upper()]}")
        elif m.group("rs"):
            out.append(f"RS kelas {m.group('rs').upper()}")
        elif m.group("u"):
            out.append(f"Utama {m.group('u').upper()}")
        elif m.group("n"):
            out.append(ROMAN.get(m.group("n").upper(), m.group("n")))
        else:
            t = re.sub(r"\s+", "", m.group(0)).upper()
            out.append(CLASS_LABEL.get(t, t))
    if not PRICE_RE.search(line):
        toks = BARE_CLASS.findall(line)
        rest = [w for w in re.findall(r"[A-Za-z]+", line) if not HEAD_WORDS.fullmatch(w)]
        has_num = any(m.group("n") or m.group("g1") or m.group("u") for m in CLASS_TOK.finditer(line))
        if len(toks) >= 3 and len(toks) > len(out) and len(toks) >= 0.6 * len(rest) and (len(out) < 3 or not has_num):
            out = [ROMAN.get(t.upper(), CLASS_LABEL.get(re.sub(r"\s+", "", t.upper()), t.upper())) for t in toks]
    # label ganda (mis. "VIP VIP") berarti judul terbaca tidak lengkap: beri nomor kolom agar tidak tertukar
    if len(set(out)) < len(out):
        seen = {}
        res = []
        for o in out:
            seen[o] = seen.get(o, 0) + 1
            res.append(o if out.count(o) == 1 else f"{o} ({seen[o]})")
        out = res
    return out


CLASS_ORDER = {"III": 0, "II-III": 0.5, "III-II": 0.5, "II": 1, "I-II": 1.5, "II-I": 1.5, "I": 2, "Utama": 3, "Utama II": 3, "Utama I": 3.5,
               "VIP": 4, "VIP/Utama": 4, "VIP Utama": 5, "VVIP": 6, "Super VIP": 6}


PRICE_WORD = re.compile(r"^(?:Rp\.?)?\d{1,3}(?:[.,]\d{3})+(?:,-|,00)?$|^(?:Rp\.?)?\d{4,7}(?:,-)?$", re.I)
HDR_HINT = re.compile(r"\b(kela[s$58]|klas|kls|vip|vvip|utama|iii|ii|paviliun|pav|teladan|icu|hcu)\b", re.I)


def price_words(lwords, n):
    """Kata harga di baris (urut x); None bila jumlahnya tidak sama dengan jumlah harga terbaca."""
    ws = [w for w in lwords if PRICE_WORD.match(w["text"].strip(".-:;|"))]
    return ws if len(ws) == n else None


COL_STOP = re.compile(r"^(?:no\.?|rp\.?|\(rp\.?\)?|rp\)|\d{1,2}|[()\-.:|/]+)$", re.I)
TOT_W = re.compile(r"\b(tarif|tarip|jumlah|total|harga|biaya)\b", re.I)
COMP_W = re.compile(r"\b(jasa|sarana|pelayanan|bahan|bhp|bmhp|alat|alkes|obat|akomodasi|japel|jaspel|medis|medik|"
                    r"paramedis|paramedik|operator|anest\w*|asisten|bidan|perawat|dokter|rs|rumah sakit)\b", re.I)
VAR_STRIP = re.compile(r"\(\s*rp\.?\s*\)|\b(tarif|tarip|harga|biaya|rp|jumlah)\b\.?|[():]", re.I)


# tabel rincian komponen: "Sedang dengan Narcose | Bahan dan Alat 350.000" lalu "Jasa Medik 300.000" ... "Jumlah Biaya"
_COMP = (r"bahan(\s*(dan|&)\s*alat)?(\s*kesehatan)?|alat(\s*kesehatan)?|alkes|bhp|bmhp|obat(\s*(dan|&)\s*bhp)?|"
         r"jasa(\s*(rumah\s*sakit|rsud|rs|sarana|pelayanan|medi[ks](\s*(anestesi|operator))?|paramedi[ks]|dokter|perawat(an)?|"
         r"keperawatan|anestesi|operator|asisten|bidan|tindakan))?|sarana|japel|jaspel|"
         r"sewa\s*(kamar|alat|ruang)(\s*\w+)?|dr\.?\s*(operator|anestesi|spesialis|umum|ahli)(\s*\w+)?|"
         r"dokter\s*(operator|anestesi|spesialis|umum)|perawat(\s*(ok|anestesi|instrumen|asisten|kamar\s*operasi))?(\s*\d)?|"
         r"paramedi[ks](\s*\w+)?|asisten(\s*\w+)?|operator|penata\s*anestesi")
COMP_NAME = re.compile(rf"(?i)^({_COMP})$")
TOTAL_NAME = re.compile(r"(?i)^(jumlah(\s*(biaya|tarif|total))?|sub\s*total|total(\s*paket)?(\s*(tarif|biaya))?|grand\s*total)$")
COMP_SUFFIX = re.compile(r"(?i)^(?P<item>.*[A-Za-z]{3}.*?)\s+(?P<k>bahan(\s*(dan|&)\s*alat)?(\s*kesehatan)?|"
                         r"jasa\s*(rumah\s*sakit|rsud|rs|sarana|pelayanan|medi[ks]))$")
COMP_PREFIX = re.compile(r"(?i)^(?P<k>jasa\s*(rumah\s*sakit|rsud|rs|sarana|pelayanan|medi[ks])|bahan(\s*(dan|&)\s*alat)?|"
                         r"pelayanan|sarana|jumlah|total)\s+(?P<item>.+)$")
# baris judul kolom (bukan judul item): "ELEKTIF CYTO", "TARIF (Rp)", "KELAS III II I"
COL_HEAD_LINE = re.compile(r"(?i)^((elektif|cito|cyto|reguler|eksekutif|non|paviliun|pagi|sore|malam|tarif|tarip|harga|rp\.?|"
                           r"\(rp\.?\)|kelas|[ivx]+|vip|vvip|utama|tanpa|dengan|kontras|total|jumlah)[\s/&,-]*)+$")
CLASS_LIST = re.compile(r"(?i)\s*(tarif\s*)?(kelas\s*)?((iii|ii|i|vip|vvip|utama|super\s*vip|icu|hcu|nicu|picu|iccu|odc|igd|"
                        r"isolasi|paviliun|[abc]|kelas)[\s,/&.-]*(dan\s*)?)+")
ROOM_NAME = re.compile(r"(?i)\b(suite|room)\b|^(utama|vip|vvip|super\s*vip)\s*(i{1,3}|[ab]|\d)?$")
CONNECT_END = re.compile(r"(&/|[/&,(+\-]|\b(dan|dengan|atau|untuk|pada|di|ke|tanpa|serta|per|yang|non))\s*$", re.I)


def tight_split(lw):
    """Angka terpecah oleh spasi karakter renggang ('1' + '50.000' menempel, jarak ~0): satu angka 150.000."""
    ws = sorted(lw or [], key=lambda w: w["x0"])
    for a, b in zip(ws, ws[1:]):
        if re.fullmatch(r"\d{1,2}", a["text"]) and re.fullmatch(r"\d{1,2}(?:[.,]\d{3})+(?:,-|,00)?", b["text"]):
            cw = (b["x1"] - b["x0"]) / max(len(b["text"]), 1)
            if b["x0"] - a["x1"] < 0.35 * cw:
                return True
    return False


def num_aligned(lw):
    """Nomor urut di awal baris sejajar (puncak sama) dengan kata pertama nama -> sel tabel rata atas."""
    ws = sorted(lw or [], key=lambda w: w["x0"])
    if len(ws) >= 2 and re.fullmatch(r"\(?(\d{1,3}|[A-Za-z])[.)]?", ws[0]["text"]) and re.search(r"[A-Za-z]{2}", ws[1]["text"]):
        return abs(ws[0]["top"] - ws[1]["top"]) < 1.5 and ws[1]["x0"] - ws[0]["x1"] < 40
    return False


def tail_owner(tail, q_top, q_name, q_aligned=False):
    """Pembagian baris teks tanpa nomor di antara dua baris harga P (atas) dan Q (bawah). Hasil k: k baris pertama
    milik P (lanjutan nama di bawah harga, mis. 'TERAPI REHABILITASI &/' -> 'DETOKSIKASI ...'), sisanya milik Q
    (awal nama baris berikutnya); None bila ragu. Dibelah di jarak vertikal terbesar (batas sel tabel)."""
    T = tail["texts"]
    if not T:
        return None
    if q_name is not None and KELAS_ROW.match(re.sub(r"[()]", "", q_name)):
        return None  # judul tabel per kelas berikutnya, bukan lanjutan
    txt = " ".join(t for _, _, t in T)
    pw0 = (tail["name"].lower().split() or [""])[0]
    if len(pw0) >= 3 and txt.lower().split()[0] == pw0:
        return 0 if q_name is not None and not (q_name.lower().split() or [""])[0] == pw0 else None  # item saudara
    p_open = CONNECT_END.search(tail["name"]) or tail["name"].count("(") > tail["name"].count(")") or re.match(r"^[a-z(/]", txt)
    q_open = CONNECT_END.search(txt) or txt.count("(") > txt.count(")")
    if p_open and not q_open:
        # baris pertama lanjutan nama atas; baris berikutnya ikut hanya bila jelas lanjutan, sisanya awal nama Q
        k = 1
        while k < len(T) and (re.match(r"^[a-z(/]", T[k][2]) or CONNECT_END.search(T[k - 1][2])
                              or T[k - 1][2].count("(") > T[k - 1][2].count(")")):
            k += 1
        return k if (k == len(T) or q_name is not None) else k
    if q_open and not p_open and q_name is not None:
        return 0
    h = max(tail["bottom"] - tail["top"], 4)
    tol = max(2.0, 0.25 * h)
    gaps = [T[0][0] - tail["bottom"]] + [T[i][0] - T[i - 1][1] for i in range(1, len(T))]
    if q_top is None:  # akhir halaman / baris bukan tabel: hanya lanjutan yang rapat dengan P
        k = 0
        while k < len(T) and gaps[k] < 0.4 * h:
            k += 1
        return k or None
    gaps.append(q_top - T[-1][1])
    # baris yang bertumpuk vertikal (jarak < -1) melekat ke sel di sisinya (sel rata tengah)
    if gaps[0] < -1 or gaps[-1] < -1:
        if gaps[0] < -1 and gaps[-1] < -1:
            if len(T) == 1:
                return None
            inner = range(1, len(T))
            return max(inner, key=lambda i: gaps[i])
        if gaps[0] < -1:  # bertumpuk dengan P: baris yang bertumpuk berantai ikut P, sisanya awal nama Q
            k = 1
            while k < len(T) and gaps[k] < -1:
                k += 1
            return k if (k == len(T) or q_name is not None) else None
        if q_name is None:
            return None
        k = len(T)  # bertumpuk dengan Q: baris terakhir (berantai) ikut Q
        while k > 1 and gaps[k - 1] < -1:
            k -= 1
        return k - 1
    big = max(range(len(gaps)), key=lambda i: gaps[i])
    if all(gaps[big] >= g + tol for i, g in enumerate(gaps) if i != big):
        return big if (big == len(T) or q_name is not None) else None
    if tail.get("aligned") and q_aligned and not q_open:
        return len(T)  # sel rata atas di kedua baris bernomor: teks di antaranya lanjutan nama di atas
    return None


def column_headers(pw, hist):
    """Judul tiap kolom harga, dibaca dari teks di atas baris yang sejajar horizontal dengan kolomnya.
    Baris data tabel yang sama (jumlah & posisi harga serupa) dilewati; berhenti di struktur tabel lain.
    hist: [(top, bottom, kata, pusat_harga)] baris halaman ini sebelum baris sekarang (pusat_harga None = tanpa harga).
    Hasil: daftar teks judul per kolom ('' bila kosong), atau None bila tidak ada judul yang sejajar."""
    n = len(pw)
    cs = [(w["x0"] + w["x1"]) / 2 for w in pw]
    g = min(b - a for a, b in zip(cs, cs[1:])) / 2 if n > 1 else 40
    bounds = []
    for i, w in enumerate(pw):
        lo = (pw[i - 1]["x1"] + w["x0"]) / 2 if i else w["x0"] - g
        hi = (w["x1"] + pw[i + 1]["x0"]) / 2 if i < n - 1 else w["x1"] + g
        bounds.append((lo, hi))
    span = bounds[-1][1] - bounds[0][0]
    labels = [[] for _ in pw]
    found, last_top, scanned = False, None, 0
    for top, bot, ws, pc in reversed(hist):
        scanned += 1
        if scanned > 80:
            break
        if pc is not None:
            if found:
                break
            if len(pc) == n and all(abs(a - b) <= 15 for a, b in zip(pc, cs)):
                continue  # baris data tabel yang sama
            if len(pc) >= 1 and any(bounds[0][0] <= c <= bounds[-1][1] for c in pc):
                return None  # tabel lain di atas: judul tabel ini tidak ada di halaman ini
            continue
        if found and last_top - bot > 30:
            break
        parts = [[] for _ in pw]
        # kata berdekatan (jarak < 10 pt) = satu frasa judul; frasa dipasangkan ke kolom harga terdekat
        phrases = []
        for w in sorted(ws, key=lambda w: w["x0"]):
            if phrases and w["x0"] - phrases[-1][-1]["x1"] < 10:
                phrases[-1].append(w)
            else:
                phrases.append([w])
        for ph in phrases:
            ph = [w for w in ph if not COL_STOP.match(w["text"].strip())]
            if not ph:
                continue
            x0, x1 = min(w["x0"] for w in ph), max(w["x1"] for w in ph)
            if x0 < bounds[0][0] or x1 > bounds[-1][1] + g or x1 - x0 > 0.9 * span:
                continue  # mulai di kolom nama (judul bagian yang memanjang) atau terlalu lebar
            c = (x0 + x1) / 2
            # judul grup yang membentang di atas dua kolom bersebelahan
            mid = next((k for k in range(n - 1) if x0 <= cs[k] + 0.3 * g and x1 >= cs[k + 1] - 0.3 * g), None)
            if mid is not None:
                parts[mid] += ph
                parts[mid + 1] += ph
                continue
            k = min(range(n), key=lambda k: abs(cs[k] - c))
            parts[k] += ph
        if any(parts):
            found, last_top = True, top
            for k in range(n):
                labels[k] = sorted(parts[k], key=lambda w: w["x0"]) + labels[k]
    if not found:
        return None
    return [re.sub(r"\s+", " ", " ".join(w["text"] for w in lab)).strip(" .:-|") for lab in labels]


def _var_label(t):
    t = re.sub(r"\s+", " ", VAR_STRIP.sub(" ", t)).strip(" .:-/&")
    keep = {"BPJS", "ICCU", "NICU", "PICU", "HCU", "ICU", "IGD", "VIP", "VVIP", "OK", "RS", "CT", "MRI", "USG", "GA"}
    return " ".join(w if (w.upper() in keep or (w.isupper() and len(w) <= 2)) else w.capitalize() for w in t.split())


def classify_two(labels):
    """Arti dua kolom harga dari judulnya: ('kelas', [k1, k2]) | ('varian', [v1, v2]) | ('komponen', [k1, k2])
    | ('komponen_total', None) | None (tidak jelas)."""
    if not labels or len(labels) != 2 or not all(labels):
        return None
    l1, l2 = labels
    c1, c2 = col_label(l1), col_label(l2)
    if c1 and c2 and c1 != c2:
        return "kelas", [c1, c2]
    t1, t2 = bool(TOT_W.search(l1)), bool(TOT_W.search(l2))
    k1, k2 = bool(COMP_W.search(l1)), bool(COMP_W.search(l2))
    if k1 and not t1 and t2:
        return "komponen_total", None
    if k1 and not t1 and k2 and not t2:
        return "komponen", [l1.lower(), l2.lower()]
    if t1 and not k1 and not t2 and k2:
        return None
    v1, v2 = _var_label(l1), _var_label(l2)
    # kata awal yang sama di kedua judul = judul grup/tabel ("Persalinan Normal Persalinan ...") -> buang
    a_, b_ = v1.split(), v2.split()
    k_ = 0
    while k_ < min(len(a_), len(b_)) - 1 and a_[k_].lower() == b_[k_].lower():
        k_ += 1
    if k_:
        v1, v2 = " ".join(a_[k_:]), " ".join(b_[k_:])
    if (header_classes(l1) or header_classes(l2)) and v1.lower() != v2.lower():
        return "kelas", [v1, v2]  # judul memuat kelas tetapi bukan satu kelas tunggal ("Kelas III, II, I")
    if len(re.sub(r"[^A-Za-z]", "", v1)) >= 2 and len(re.sub(r"[^A-Za-z]", "", v2)) >= 2 and v1.lower() != v2.lower():
        return "varian", [v1, v2]
    return None


def col_label(text):
    hc = header_classes(text)
    if len(hc) != 1 and re.fullmatch(r"(?i)\s*(iii|ii|i|ill|1|2|3)\s*", text):
        hc = header_classes("Kelas " + text)
    return hc[0] if len(hc) == 1 else None


def header_label_positions(block_lines):
    """[(pusat x, label)] tiap label kelas di blok judul; posisi = rata-rata pusat kata yang membentuk label."""
    out = []
    for ws in block_lines:
        ws = sorted(ws, key=lambda w: w["x0"])
        text, spans = "", []
        for w in ws:
            spans.append((len(text), len(text) + len(w["text"]), w))
            text += w["text"] + " "
        found = [(m.start(), m.end(), m.group(0)) for m in CLASS_TOK.finditer(text)]
        if len(found) < 3:  # angka romawi tanpa kata 'Kelas' ("III II I VIP")
            bare = [(m.start(), m.end(), m.group(0)) for m in BARE_CLASS.finditer(text)]
            rest = [x for x in re.findall(r"[A-Za-z]+", text) if not HEAD_WORDS.fullmatch(x)]
            if len(bare) >= 3 and len(bare) >= 0.6 * len(rest):
                found = bare
        for a, b, tok in found:
            lab = col_label(tok)
            cw = [w for s0, s1, w in spans if s0 < b and s1 > a]
            if lab and cw:
                out.append(((min(w["x0"] for w in cw) + max(w["x1"] for w in cw)) / 2, lab))
    return sorted(out)


def labels_by_x(intervals, hdr_lines, row_top):
    """Label kelas per kolom harga: tiap kolom dipasangkan ke label judul terdekat secara horizontal.
    Kolom judul yang kosong di baris ini (mis. ICU) otomatis terlewati. None bila ragu."""
    above = [(t, ws) for t, ws in hdr_lines if t < row_top]
    if not above:
        return None
    last = above[-1][0]
    labs = header_label_positions([ws for t, ws in above if last - t <= 45])
    if len(labs) < len(intervals) or len(labs) < 2:
        return None
    centers = [(a + b) / 2 for a, b in intervals]
    lx = [x for x, _ in labs]
    gap = min(b - a for a, b in zip(lx, lx[1:])) if len(lx) > 1 else 60
    tol = max(25.0, 0.6 * gap)
    picked = []
    for c in centers:
        k = min(range(len(labs)), key=lambda i: abs(labs[i][0] - c))
        if abs(labs[k][0] - c) > tol:
            return None
        picked.append(k)
    if len(set(picked)) != len(picked) or picked != sorted(picked):
        return None
    labels = [labs[k][1] for k in picked]
    return labels if len(set(labels)) == len(labels) else None


def recall_x(memory, centers, tol=8):
    """Label kolom dari memori bila pusat-pusat kolom sama posisinya (tabel bersambung tanpa judul berulang).
    Hanya untuk >= 4 kolom dan label yang tidak ganda: 3 kolom terlalu mirip sarana/pelayanan/total."""
    if len(centers) < 4:
        return None
    for mc, ml in reversed(memory):
        if any(re.search(r"\(\d\)$", str(x)) for x in ml):
            continue
        if len(mc) == len(centers) and all(abs(a - b) <= tol for a, b in zip(mc, centers)):
            return ml
    return None


def class_order_odd(pairs):
    """Harga per kelas mestinya tidak turun dari kelas III ke VIP (toleransi 2%)."""
    known = sorted(((CLASS_ORDER[k], h) for k, h in pairs if k in CLASS_ORDER), key=lambda t: t[0])
    return any(b < a * 0.98 for (_, a), (_, b) in zip(known, known[1:]))


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


# "1.025000": pemisah ribuan kedua hilang -> hanya satu bacaan wajar (1.025.000)
MISSING_SEP = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,]\d{3})*[.,]\d{6}(?:,00|,-)?(?![\d])")
# "6028.890": 4+ digit sebelum pemisah -> bisa titik hilang (6.028.890) atau digit ganda; perlu bukti dari baris
LONG_HEAD = re.compile(r"(?<![\d.,])\d{4,}[.,]\d{3}(?:[.,]\d{3})*(?:,00|,-)?(?![\d])")


def _fmt(mm):
    d = re.sub(r"\D", "", re.sub(r"(,00|,-)$", "", mm.group(0)))
    return f"{int(d):,}".replace(",", ".")


def repair_missing_sep(line):
    return MISSING_SEP.sub(_fmt, line)


def repair_malformed(line):
    """'6028.890' -> '6.028.890' (semua digit dipertahankan, pemisah ribuan dibetulkan)."""
    return LONG_HEAD.sub(_fmt, line)


def classes_plausible(p):
    """Harga per kelas berjajar: naik (atau turun) bertahap, tiap langkah <= 1,6x."""
    if len(p) < 4:
        return False
    for seq in (p, p[::-1]):
        if all(a <= b <= a * 1.6 for a, b in zip(seq, seq[1:])):
            return True
    return False


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
    category, pending, parent, head_ctx = "", None, "", ""
    bd_item, np_item, comp_ctx = None, None, None
    parent_np = ""  # nama induk terakhir dari judul tanpa harga (bukan dari baris berharga)
    grp2, item_x, grp_rows = "", None, []  # tabel dua kolom nama: kolom grup ("C. Praktik Klinik /") + kolom item bernomor ("1. SLTA")  # tabel rincian komponen: nama layanan induk, judul item, komponen aktif
    cls_header, grp_header = [], []
    x_memory = []  # [(pusat x kolom, label kelas)] yang pernah terbaca di dokumen ini, untuk tabel bersambung
    x2_memory = []  # [(pusat x 2 kolom harga, judul kolom)] untuk tabel 2 kolom yang bersambung ke halaman berikutnya
    tail = None  # baris harga terakhir + baris teks tanpa nomor sesudahnya (calon lanjutan nama)

    def regroup():
        """Teks kolom grup bertambah (baris lanjutan): perbarui nama baris-baris grup yang sudah dibuat."""
        g = re.sub(r"\s+", " ", grp2).strip(" /")
        for a, b, it in grp_rows:
            for r in rows[a:b]:
                r["nama_asli"] = f"{g} - {it}"

    def apply_tail(k):
        """k baris teks pertama -> lanjutan nama baris harga di atasnya (P); sisanya dikembalikan untuk baris Q.
        Konteks (kategori, judul) yang sempat diubah oleh teks itu dipulihkan."""
        nonlocal category, head_ctx, parent
        category, head_ctx, parent = tail["ctx"]
        del np_titles[tail["n_titles"]:]
        top_txt = " ".join(t for _, _, t in tail["texts"][:k])
        if top_txt:
            for r in rows[tail["i0"]:tail["i1"]]:
                r["nama_asli"] = clean_name(f"{r['nama_asli']} {top_txt}")
                r["_flags"] = r["_flags"] + ["nama_digabung"]
        return " ".join(t for _, _, t in tail["texts"][k:])
    kelas_ctx = ""  # dari baris "Kelas I" tanpa harga; berlaku sampai judul bagian/tabel berikutnya
    np_titles = []  # judul (baris tanpa harga) sejak baris berharga terakhir
    np_run = []  # baris tanpa harga sejak baris berharga terakhir (judul tabel bisa terbelah beberapa baris)
    rows_at_hdr = 0  # jumlah baris saat judul kelas terakhir dibaca (judul bertingkat tidak saling menghapus)
    ocr = load_ocr(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        if not start_page:
            start_page = find_annex_page(pdf)
        for pno in range(start_page - 1, len(pdf.pages)):
            kelas_ctx = ""  # konteks kelas tidak menyeberang halaman
            hdr_lines = []  # [(top, kata)] baris tanpa harga yang memuat kata kelas, untuk membaca judul per kolom
            hist = []  # [(top, bottom, kata, pusat harga | None)] semua baris halaman ini, untuk membaca judul kolom
            item_x = None
            if tail is not None and (k := tail_owner(tail, None, None)):
                apply_tail(k)
            tail = None
            plines = page_lines(pdf.pages[pno])
            metode = "pdf_teks"
            if (pno + 1) in ocr:
                alt = choose_ocr(plines, ocr[pno + 1])
                if alt:
                    plines, metode = alt, "ocr_ulang"
            for raw, lw in plines:
                line = fix_numbers(re.sub(r"(\d{3})\.-(?=\s|$)", r"\1,-", raw.strip()))  # "850.000.-" -> "850.000,-"
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
                    if p2 and (lead0 or (sum_ok(p2) and not sum_ok(prices)) or len(p2) > len(prices) + 1 or tight_split(lw)
                               or (cls_header and len(p2) == len(cls_header) != len(prices))):
                        line, m, prices = merged, m2, p2
                # angka cacat ("6028.890", "1,400000"): baca ulang semua digit; dipakai hanya bila baris jadi konsisten
                pre_flags = []
                ms_fixed = repair_missing_sep(line)
                if ms_fixed != line:
                    m4, p4, _ = parse_prices(ms_fixed)
                    if p4:
                        line, m, prices = ms_fixed, m4, p4
                        pre_flags.append("harga_diperbaiki")
                fixed = repair_malformed(line)
                if fixed != line:
                    m3, p3, _ = parse_prices(fixed)
                    if p3 and not sum_ok(prices) and (sum_ok(p3) or total_first(p3) or classes_plausible(p3)):
                        line, m, prices = fixed, m3, p3
                        pre_flags.append("harga_diperbaiki")
                    elif m:
                        pre_flags.append("harga_ambigu")
                if lw:
                    pws = [w for w in lw if PRICE_WORD.match(w["text"].strip(".-:;|"))] if (m and prices) else None
                    hist.append((min(w["top"] for w in lw), max(w["bottom"] for w in lw), lw,
                                 [(w["x0"] + w["x1"]) / 2 for w in pws] if pws else None))
                if not m and item_x is not None and lw:
                    if (max(w["x1"] for w in lw) < item_x - 5 and not TABLE_HEAD.search(line) and "|" not in line
                            and (grp2 or re.match(r"^[A-Z]\.\s", line))):
                        gt = re.sub(r"^[A-Z]\.\s*", "", line).strip()
                        if re.match(r"^[A-Z]\.\s", line):
                            grp2, grp_rows = gt, []
                        else:
                            grp2 = f"{grp2} {gt}".strip()
                            regroup()
                    elif TABLE_HEAD.search(line) or MAJOR.match(line):
                        item_x = None
                if not m:
                    if tail is not None:
                        tb = HEAD_NUM.sub("", PAREN_NUM.sub("", NUMBERING.sub("", line))).strip(" :.")
                        numbered_l = bool(NUMBERING.match(line) or HEAD_NUM.match(line) or PAREN_NUM.match(line)
                                          or re.match(r"^[A-Za-z]\s+[A-Z]", line) or re.search(r"\d{3}", tb)
                                or re.match(r"^[A-Za-z0-9]{1,3}(\.\d+)+\.?\s", line)
                                or sum(len(w) == 1 for w in tb.split()) > 0.3 * len(tb.split())
                                or len(re.sub(r"[^A-Za-z]", "", tb)) < 0.6 * len(re.sub(r"[^A-Za-z0-9]", "", tb))
                                or len(re.sub(r"[A-Za-z0-9\s()/\-.,&+:%<>=']", "", tb)) > 0.2 * len(tb.replace(" ", ""))
                                or re.search(r"(?i)termasuk|catatan|keterangan|\*\)|^ket\b", tb)
                                or (re.fullmatch(r"[A-Z]{3,}( [A-Z]{2,}){0,2}", tb) and not tail["name"].isupper()))
                        upper_ok = tail["name"].isupper() or not is_header(tb)
                        if (lw and not numbered_l and len(tail["texts"]) < 3 and upper_ok
                                and max(w["x1"] for w in lw) <= tail["px0"] + 2 and min(w["x0"] for w in lw) >= tail["nx0"] - 15
                                and len(re.sub(r"[^A-Za-z]", "", tb)) >= 2 and len(tb) <= 90 and not PRICE_RE.search(tb)
                                and not FRAGMENT.match(tb) and not TABLE_HEAD.search(line) and not KELAS_ROW.match(tb)
                                and not re.match(KELAS_W, tb, re.I) and not re.search(r"\b(jasa|sarana|tarif|jumlah|total)\b", tb, re.I)):
                            if not tail["texts"]:
                                tail["ctx"], tail["n_titles"] = (category, head_ctx, parent), len(np_titles)
                            tail["texts"].append((min(w["top"] for w in lw), max(w["bottom"] for w in lw), tb))
                        else:
                            if tail["texts"] and (k := tail_owner(tail, min(w["top"] for w in lw) if lw else None, None)):
                                apply_tail(k)
                            tail = None
                    np_run = (np_run + [line])[-6:]
                    if lw and HDR_HINT.search(line):
                        hdr_lines.append((min(w["top"] for w in lw), lw))
                    t_body = HEAD_NUM.sub("", PAREN_NUM.sub("", NUMBERING.sub("", line))).strip(" :-.|")
                    if (len(re.sub(r"[^A-Za-z]", "", t_body)) >= 4 and len(t_body) <= 90
                            and not (TABLE_HEAD.search(line) or len(header_classes(line)) >= 2 or header_groups(line)
                                     or re.search(r"\b(jasa|sarana|komponen|jumlah|tarif\s*\(rp|keterangan)\b", line, re.I))
                            and not KELAS_ROW.match(t_body) and not re.match(KELAS_W, t_body, re.I)
                            and not re.search(rf"{KELAS_W}\s*(iii|ii|i)\b", t_body, re.I)
                            and not re.match(r"^\W*no\b", line, re.I) and "|" not in t_body
                            and not re.fullmatch(r"(?i)(pratama|madya|utama|vip|vvip|&|dan|\s)+", t_body)
                            and sum(len(w) == 1 for w in t_body.split()) <= 0.3 * len(t_body.split())
                            and len(re.sub(r"[^A-Za-z]", "", t_body)) >= 0.5 * len(t_body.replace(" ", ""))
                            and not re.search(r"\b(adalah|sebagaimana|dikenakan|ditetapkan|ayat|pasal|rp)\b", t_body, re.I)
                            and not COL_HEAD_LINE.match(t_body) and not CONNECT_END.search(t_body)
                            and not (len(t_body.split()) >= 2 and all(FRAGMENT.match(w) for w in t_body.split()))):
                        np_titles.append(t_body)
                    # judul tabel baru tanpa kelas -> lupakan judul kelas sebelumnya
                    if TABLE_HEAD.search(line):
                        seg_start = len(rows)
                    hc = header_classes(line)
                    if (TABLE_HEAD.search(line) and len(hc) < 2 and not header_groups(line)
                            and len(re.findall(r"\b(tarif|jumlah)\b", line, re.I)) < 2 and len(rows) > rows_at_hdr):
                        cls_header, grp_header = [], []
                    if len(header_groups(line)) >= 2:
                        grp_header, cls_header, rows_at_hdr = header_groups(line), [], len(rows)
                    elif len(hc) >= 2:
                        cls_header, grp_header, rows_at_hdr = hc, [], len(rows)
                    body = PAREN_NUM.sub("", NUMBERING.sub("", line)).strip(" :-.")
                    numbered = bool(NUMBERING.match(line) or HEAD_NUM.match(line) or PAREN_NUM.match(line))
                    if HEAD_NUM.match(line):
                        body = HEAD_NUM.sub("", line).strip(" :-.")
                    if TABLE_HEAD.search(line) or MAJOR.match(line):
                        kelas_ctx = ""
                    if KELAS_ROW.match(body) and re.match(KELAS_W, body, re.I):
                        kelas_ctx = std_kelas(body)
                        continue
                    # judul bernomor yang menyebut kelas di ujungnya ("b. Rawat Inap Kelas I") -> konteks kelas
                    if numbered and (kh := re.search(rf"{KELAS_W}\s*(iii|ii|i|utama|vvip|vip)\s*$", body, re.I)):
                        kelas_ctx = std_kelas(kh.group(0))
                    if is_header(body) and not (COL_HEAD_LINE.match(body) or re.search(r"\b(komponen|gol|golongan)\b", body, re.I)):
                        category, pending, kelas_ctx = body[:60], None, ""
                    elif NUMBERING.match(line) and len(body) >= 3:
                        pending = body
                    # judul item/kelompok untuk baris berikutnya ("1. Tindakan Operatif" -> "Sederhana 100.000")
                    hdr_like = (TABLE_HEAD.search(line) or len(hc) >= 2 or header_groups(line)
                                or re.search(r"\b(jasa|sarana|komponen)\b", line, re.I))
                    multi_frag = len(body.split()) >= 2 and all(FRAGMENT.match(w) or re.fullmatch(r"(?i)[ivx]+|\d|&|/|-", w)
                                                               for w in body.split())
                    if (not hdr_like and not COL_HEAD_LINE.match(body) and not multi_frag
                            and not re.search(r"(?i)\b(besar\s+biaya|biaya\s+per|per\s+kelas|komponen\s+biaya)\b", body) and len(re.sub(r"[^A-Za-z]", "", body)) >= 4 and len(body) <= 90
                            and (numbered or is_header(body) or line.rstrip().endswith(":"))
                            and not re.search(r"\b(adalah|sebagaimana|dikenakan|ditetapkan|ayat|pasal|rp)\b", body, re.I)
                            and not re.match(KELAS_W, body, re.I) and not KELAS_ROW.match(body)
                            and not re.fullmatch(r"(tarif|jumlah|keterangan|total|harga)( \(rp\.?\))?", body, re.I)):
                        if FRAGMENT.match(body) and head_ctx:
                            parent = parent_np = f"{head_ctx} - {body}"
                        else:
                            head_ctx = parent = np_item = parent_np = body
                    continue
                name = clean_name(NUMBERING.sub("", clean_name(line[: m.start()])).strip(" :-."))
                name = PAREN_NUM.sub("", name).strip(" :-.")
                if not prices:
                    continue
                grp_flag = []
                if lw and prices:
                    ws_ = sorted(lw, key=lambda w: w["x0"])
                    px_ = min((w["x0"] for w in ws_ if PRICE_WORD.match(w["text"].strip(".-:;|"))), default=1e9)
                    inner = next((w for w in ws_ if re.fullmatch(r"\d{1,2}\.", w["text"]) and w["x1"] < px_
                                  and (w["x0"] - ws_[0]["x0"] > 60 or (item_x is not None and abs(w["x0"] - item_x) < 15))), None)
                    if inner is not None and (item_x is not None or ws_[0] is not inner):
                        left = " ".join(w["text"] for w in ws_ if w["x1"] <= inner["x0"])
                        item_t = clean_name(" ".join(w["text"] for w in ws_ if inner["x1"] <= w["x0"] and w["x1"] <= px_))
                        if KELAS_ROW.match(item_t) or re.match(KELAS_W, item_t, re.I) or "|" in left:
                            item_t = ""
                        elif left and not (grp2 or re.match(r"^[A-Z]\.\s", left)):
                            item_t = ""  # grup hanya dimulai dari penomoran huruf ("C. Praktik Klinik /")
                        if left and item_t:
                            gt = re.sub(r"^[A-Z]\.\s*", "", left).strip()
                            if re.match(r"^[A-Z]\.\s", left):
                                grp2, grp_rows = gt, []
                            else:
                                grp2 = f"{grp2} {gt}".strip()
                                regroup()
                        if item_t and grp2:
                            item_x = inner["x0"]
                            name = f"{re.sub(r'\s+', ' ', grp2).strip(' /')} - {item_t}"
                            grp_flag = [("nama_dari_judul", item_t)]
                    elif item_x is not None and not (inner is not None):
                        item_x = None
                if re.search(r"(?i)\b(tahun|nomor|tanggal|tangoal|tgl)\b", line) and all(1990 <= p_ <= 2035 for p_ in prices):
                    continue  # kepala lampiran "NOMOR 24 TAHUN 2017", bukan tarif
                tail_flag = []
                if not re.search(r"[A-Za-z]", name):
                    name = ""  # sisa nomor urut ("14") tanpa nama
                if tail is not None and tail["texts"]:
                    k = tail_owner(tail, min(w["top"] for w in lw) if lw else None, name, num_aligned(lw))
                    if k is not None:
                        rest = apply_tail(k)
                        if rest:
                            name = clean_name(f"{rest} {name}")
                            tail_flag = ["nama_digabung"]
                tail = None
                i_start = len(rows)
                # judul kelas multi-baris: dipakai hanya bila jumlah kelasnya cocok dengan jumlah harga baris ini
                fits = lambda h: h and (len(prices) == len(h) >= 3 or len(prices) == 3 * len(h) >= 6)  # noqa: E731
                if len(np_run) >= 2 and not fits(cls_header) and not (grp_header and len(prices) == 3 * len(grp_header)):
                    ml = header_classes(" ".join(np_run))
                    if fits(ml) and not any(re.search(r"\(\d\)$", c) for c in ml) and len(ml) > len(cls_header if len(cls_header) and fits(cls_header) else []):
                        cls_header, grp_header, rows_at_hdr = ml, [], len(rows)
                np_run = []
                titles, np_titles = np_titles, []
                # nama terbelah: '365 Sialendoskopi ... (' lalu '— | Anestesi Spinal / Ga Th 11.880.000'
                raw_head = line[: m.start()].strip()
                joined = False
                first = (raw_head.split() or [""])[0]
                if (pending and not NUMBERING.match(line) and len(re.sub(r"[^A-Za-z]", "", name)) >= 3
                        and not KELAS_ROW.match(re.sub(r"[()]", "", name)) and not FRAGMENT.match(pending)
                        and len(re.sub(r"[^A-Za-z]", "", pending)) >= 0.5 * len(pending.replace(" ", ""))
                        and pending.lower().split()[0] not in name.lower()
                        and (re.search(r"[(/,&-]\s*$", pending)
                             or re.match(r"^[^A-Za-z0-9(]", raw_head) or re.fullmatch(r"[a-z]{3,}\W*", first))):
                    name = clean_name(f"{pending} {name.lstrip('—|-. ')}")
                    joined = True
                if len(re.sub(r"[^A-Za-z]", "", name)) < 3 and pending:
                    name = pending
                pending = None
                if len(re.sub(r"[^A-Za-z]", "", name)) < 3:
                    continue
                flags = list(pre_flags) + (["nama_digabung"] if joined else []) + tail_flag + [g[0] for g in grp_flag]
                kelas = kelas_ctx or block["kelas"]
                nama = name
                if KELAS_ROW.match(re.sub(r"[()]", "", name)):
                    kelas = std_kelas(name)
                    if titles:  # judul tepat di atas baris-baris kelas = nama layanan
                        parent = titles[-1]
                        nama = parent
                        flags.append("nama_dari_judul_tabel")
                    elif parent:
                        # induk dari baris tipe kamar ("Utama Suite Room") -> pakai judul layanan di atasnya
                        nama = parent_np if (ROOM_NAME.search(parent) and parent_np) else parent
                        flags.append("nama_dari_baris_atas")
                    else:
                        flags.append("nama_terpotong")
                else:
                    ms = KELAS_SUFFIX.match(name)
                    pre = re.sub(rf"(\s+\d+\.?|\s+{KELAS_W})$", "", ms.group(1), flags=re.I).strip(" -,") if ms else ""
                    core = re.sub(r"\b(kelas|utama|vip|vvip|super|pratama|madya)\b", "", pre, flags=re.I)
                    if (ms and len(prices) <= 4 and len(re.sub(r"[^A-Za-z]", "", core)) >= 4
                            and not re.search(r"([/&]|\bnon)\s*$", ms.group(1), re.I)):
                        kelas, name = std_kelas(ms.group(2)), pre
                        nama = name
                        flags.append("kelas_dari_nama")
                    if FRAGMENT.match(name) and head_ctx:
                        nama = f"{head_ctx} - {name}"
                        flags.append("nama_dari_judul")
                    if ROOM_NAME.search(name) and kelas_ctx and parent_np and not KELAS_ROW.match(parent_np):
                        # baris tipe kamar di bawah "Kelas Utama": layanan = judul di atasnya, kelas = kelas + tipe kamar
                        kelas, nama = f"{kelas_ctx} - {name}", parent_np
                        flags.append("nama_dari_baris_atas")
                    else:
                        parent = nama
                # tabel rincian komponen (baris = komponen biaya suatu layanan)
                komp = "total"
                nm = re.sub(r"\s*\*+$", "", nama).strip()
                nama = re.sub(r"(\s+(0|-|0,00))+$", "", nama)  # sel bernilai 0 / '-' yang terbaca ikut nama
                nm = re.sub(r"(\s+(0|-|0,00))+$", "", nm)
                if TOTAL_NAME.match(nm) and bd_item:
                    nama = bd_item
                    flags.append("nama_dari_baris_atas")
                    bd_item = None
                elif COMP_NAME.match(nm) and (bd_item or np_item):
                    komp, nama = re.sub(r"\s+", " ", nm.lower()), bd_item or np_item
                    bd_item = nama
                    flags += ["komponen_terpisah", "nama_dari_baris_atas"]
                elif (mx := COMP_SUFFIX.match(nm)) and not COMP_NAME.match(mx.group("item")):
                    item = mx.group("item").strip(" -,")
                    item = f"{head_ctx} - {item}" if FRAGMENT.match(item) and head_ctx else item
                    komp, nama, bd_item = re.sub(r"\s+", " ", mx.group("k").lower()), item, item
                    flags.append("komponen_terpisah")
                elif (mx := COMP_PREFIX.match(nm)) and FRAGMENT.match(mx.group("item")):
                    k_ = re.sub(r"\s+", " ", mx.group("k").lower())
                    comp_ctx = "total" if k_ in ("jumlah", "total") else ("jasa " + k_ if k_ in ("pelayanan", "sarana") else k_)
                    item = mx.group("item")
                    komp, nama, bd_item = comp_ctx, (f"{head_ctx} - {item}" if head_ctx else item), None
                    flags.append("komponen_terpisah")
                elif comp_ctx and FRAGMENT.match(name):
                    komp = comp_ctx
                    flags.append("komponen_terpisah")
                else:
                    bd_item, comp_ctx = None, None
                np_item = None
                if re.search(r"(^|\s)(sebesar|adalah|yaitu|ditetapkan|dikenakan|setinggi|paling (tinggi|rendah)|"
                             r"maksimal|minimal|ayat|pasal)\s*$", nama, re.I):
                    continue  # kalimat pasal, bukan item tarif
                if re.fullmatch(r"(jumlah|sub\s*total|grand\s*total|total)(\s+tarif)?", nama, re.I):
                    continue  # baris jumlah tabel, bukan layanan
                if FRAGMENT.match(nama):
                    flags.append("nama_terpotong")
                if re.search(r"(^|\s)\.\d{3}", raw):
                    flags.append("harga_ambigu")
                # tentukan arti kolom harga
                pairs = None  # [(kelas, harga)]
                if grp_header and len(prices) == 3 * len(grp_header) and sum_ok(prices):
                    pairs = [(g, prices[3 * k + 2]) for k, g in enumerate(grp_header)]
                    pwg = price_words(lw, len(prices))
                    if pwg:
                        x_memory.append((tuple((pwg[3 * k + 2]["x0"] + pwg[3 * k + 2]["x1"]) / 2
                                               for k in range(len(prices) // 3)), [k for k, _ in pairs]))
                elif (cls_header and len(prices) == len(cls_header) and not sum_ok(prices) and not total_first(prices)
                      and (len(prices) >= 3 or all(c.startswith("RS kelas") for c in cls_header))):
                    pairs = list(zip(cls_header, prices))
                if pairs:
                    flags = flags + ["dari_kolom_kelas"]
                    if class_order_odd(pairs):
                        flags.append("urutan_kelas_aneh")
                    pw0 = price_words(lw, len(prices))
                    if pw0 and len(pairs) == len(prices):
                        x_memory.append((tuple((w["x0"] + w["x1"]) / 2 for w in pw0), [k for k, _ in pairs]))
                elif (cls_header and len(prices) == 3 * len(cls_header) and len(prices) >= 6
                      and all(_close(prices[i] + prices[i + 1], prices[i + 2]) for i in range(0, len(prices), 3))):
                    # judul kelas di atas kelompok (sarana, pelayanan, total) per kelas
                    pairs = [(c, prices[3 * k + 2]) for k, c in enumerate(cls_header)]
                    pwg = price_words(lw, len(prices))
                    if pwg:
                        x_memory.append((tuple((pwg[3 * k + 2]["x0"] + pwg[3 * k + 2]["x1"]) / 2
                                               for k in range(len(prices) // 3)), [k for k, _ in pairs]))
                    flags.append("dari_kolom_kelas")
                    if class_order_odd(pairs):
                        flags.append("urutan_kelas_aneh")
                elif (len(prices) >= 6 and len(prices) % 3 == 0 and sum_ok(prices)
                      and not _close(sum(prices[:-1]), prices[-1])
                      and (pw := price_words(lw, len(prices)))
                      and (xl := (labels_by_x([(pw[3 * k]["x0"], pw[3 * k + 2]["x1"]) for k in range(len(prices) // 3)],
                                              hdr_lines, pw[0]["top"])
                                  or (not any(t < pw[0]["top"] for t, _ in hdr_lines)) and recall_x(x_memory, [(pw[3 * k + 2]["x0"] + pw[3 * k + 2]["x1"]) / 2
                                                         for k in range(len(prices) // 3)])))):
                    # grup (sarana, pelayanan, total) per kelas; judul kelas dibaca dari posisi kolom
                    pairs = [(c, prices[3 * k + 2]) for k, c in enumerate(xl)]
                    flags += ["dari_kolom_kelas", "kelas_dari_posisi"]
                    x_memory.append((tuple((pw[3 * k + 2]["x0"] + pw[3 * k + 2]["x1"]) / 2
                                           for k in range(len(prices) // 3)), list(xl)))
                    if class_order_odd(pairs):
                        flags.append("urutan_kelas_aneh")
                elif (len(prices) >= 6 and len(prices) % 3 == 0 and sum_ok(prices)
                      and not _close(sum(prices[:-1]), prices[-1])):
                    # beberapa grup (sarana, pelayanan, total) berjajar tanpa judul kelas yang terbaca
                    pairs = [(f"grup {k + 1} (kelas tak diketahui)", prices[3 * k + 2]) for k in range(len(prices) // 3)]
                    flags.append("kelas_grup_tanpa_judul")
                elif ((kk := len(prices) // 2) >= 2 and len(prices) == 2 * kk + 1
                      and all(_close(prices[i] + prices[kk], prices[kk + 1 + i]) for i in range(kk))
                      or (kk := len(prices) // 3) >= 2 and len(prices) == 3 * kk
                      and all(_close(prices[i] + prices[kk + i], prices[2 * kk + i]) for i in range(kk))):
                    # blok per kelas berjajar: [komponen per kelas | komponen tetap | tarif per kelas]
                    # (tarif kelas X = komponen kelas X + komponen tetap) atau [sarana.. | pelayanan.. | total..]
                    tots = prices[-kk:]
                    pwt = price_words(lw, len(prices))
                    xl = labels_by_x([(w["x0"], w["x1"]) for w in pwt[-kk:]], hdr_lines, pwt[0]["top"]) if pwt else None
                    if xl:
                        pairs = list(zip(xl, tots))
                        flags += ["dari_kolom_kelas", "kelas_dari_posisi"]
                        x_memory.append((tuple((w["x0"] + w["x1"]) / 2 for w in pwt[-kk:]), list(xl)))
                    else:
                        pairs = [(f"kolom {i + 1}/{kk} (kelas tak terbaca)", t) for i, t in enumerate(tots)]
                        flags.append("kelas_kolom_tanpa_judul")
                elif total_first(prices) and not sum_ok(prices):
                    pairs = [(kelas or "Non-kelas", prices[0])]
                    flags.append("total_di_depan")
                elif (len(prices) == 4 and _close(prices[0] + prices[1], prices[2])
                      and prices[2] <= prices[3] <= prices[2] * 1.05 + 1000):
                    pairs = [(kelas or "Non-kelas", prices[3])]  # sarana, pelayanan, jumlah, tarif dibulatkan
                elif (3 <= len(prices) <= 8 and not sum_ok(prices) and not total_first(prices)
                      and (pw := price_words(lw, len(prices)))
                      and (xl := (labels_by_x([(w["x0"], w["x1"]) for w in pw], hdr_lines, pw[0]["top"])
                                  or (not any(t < pw[0]["top"] for t, _ in hdr_lines)
                                      and recall_x(x_memory, [(w["x0"] + w["x1"]) / 2 for w in pw]))))):
                    pairs = list(zip(xl, prices))
                    flags += ["dari_kolom_kelas", "kelas_dari_posisi"]
                    x_memory.append((tuple((w["x0"] + w["x1"]) / 2 for w in pw), list(xl)))
                    if class_order_odd(pairs):
                        flags.append("urutan_kelas_aneh")
                elif (4 <= len(prices) <= 8 and not sum_ok(prices) and not total_first(prices)
                      and (prices == sorted(prices) or prices == sorted(prices, reverse=True))):
                    # harga per kelas berjajar tanpa judul kelas yang terbaca: simpan semua kolom
                    pairs = [(f"kolom {k + 1}/{len(prices)} (kelas tak terbaca)", p) for k, p in enumerate(prices)]
                    flags.append("kelas_kolom_tanpa_judul")
                elif len(prices) == 2:
                    # dua kolom harga: arti kolom dari judulnya (varian / kelas / dua komponen / komponen + total)
                    k0 = kelas or "Non-kelas"
                    pw2 = price_words(lw, 2)
                    lab = column_headers(pw2, hist[:-1]) if pw2 else None
                    if lab is None and pw2:
                        cs2 = [(w["x0"] + w["x1"]) / 2 for w in pw2]
                        lab = next((lb for c, lb in reversed(x2_memory) if all(abs(a - b) <= 10 for a, b in zip(c, cs2))), None)
                    how = classify_two(lab)
                    if how and pw2:
                        x2_memory.append((tuple((w["x0"] + w["x1"]) / 2 for w in pw2), lab))
                    if how and how[0] == "kelas":
                        pairs = [(how[1][0], prices[0]), (how[1][1], prices[1])]
                        flags += ["dari_kolom_kelas", "kelas_dari_posisi"]
                        if not all(CLASS_LIST.fullmatch(lb) or col_label(lb) == lb for lb in how[1]):
                            flags.append("label_kelas_tak_jelas")  # judul kelas terbaca rusak (OCR)
                    elif how and how[0] == "varian":
                        pairs = [(k0, prices[0], how[1][0]), (k0, prices[1], how[1][1])]
                        flags.append("varian_dari_judul_kolom")
                    elif how and how[0] == "komponen":
                        pairs = [(k0, prices[0], "", how[1][0]), (k0, prices[1], "", how[1][1])]
                        flags.append("komponen_terpisah")
                    elif how and how[0] == "komponen_total":
                        pairs = [(k0, prices[1])]
                        if prices[0] > prices[1]:
                            flags.append("komponen_tidak_jumlah")
                    elif prices[0] >= prices[1]:
                        # kolom pertama >= kedua: pasti bukan (komponen, total) -> simpan keduanya, tandai
                        pairs = [(f"kolom {k + 1}/2 (judul tak terbaca)", p) for k, p in enumerate(prices)]
                        flags.append("kelas_kolom_tanpa_judul")
                    else:
                        pairs = [(k0, prices[1])]
                        flags.append("kolom_harga_tak_dikenal")
                else:
                    pairs = [(kelas or "Non-kelas", prices[-1])]
                    if len(prices) == 3 and not sum_ok(prices):
                        flags.append("komponen_tidak_jumlah")
                    elif len(prices) >= 4 and not sum_ok(prices):
                        flags.append("kolom_harga_tak_dikenal")
                if any(re.search(r"\(\d\)$", str(pr[0])) for pr in pairs):
                    flags.append("label_kelas_tak_jelas")  # judul kelas ganda ("I (1)", "I (2)"): judul tak terbaca utuh
                for pr in pairs:
                    kel, harga = pr[0], pr[1]
                    rows.append(dict(
                        dokumen_id=dok_id, halaman=pno + 1, kategori_asli=category,
                        nama_asli=nama, kelas=(kel or "Non-kelas").strip(),
                        varian=pr[2] if len(pr) > 2 else "", komponen=pr[3] if len(pr) > 3 else komp,
                        n_kolom_harga=len(prices), harga=harga, sumber_harga="langsung",
                        golongan="", paket_id="", metode_ekstraksi=metode,
                        _blok=block["id"], _flags=list(flags), baris_mentah=raw.strip()))
                if grp_flag and len(rows) > i_start:
                    grp_rows.append((i_start, len(rows), grp_flag[0][1]))
                pw_t = [w for w in lw if PRICE_WORD.match(w["text"].strip(".-:;|"))] if lw else []
                nw_t = [w for w in lw if not PRICE_WORD.match(w["text"].strip(".-:;|"))] if lw else []
                if pw_t and nw_t and len(rows) > i_start and not KELAS_ROW.match(re.sub(r"[()]", "", name)):
                    tail = dict(i0=i_start, i1=len(rows), name=rows[-1]["nama_asli"], texts=[],
                                top=min(w["top"] for w in lw), bottom=max(w["bottom"] for w in lw),
                                px0=min(w["x0"] for w in pw_t), nx0=min(w["x0"] for w in nw_t), ctx=None, n_titles=0,
                                aligned=num_aligned(lw))
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
            "kategori_std", "golongan", "kelas", "varian", "komponen", "termasuk_bhp", "sumber_bhp", "satuan", "harga",
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
