"""Baca status BHP tingkat dokumen dari batang tubuh peraturan (pasal-pasal), secara otomatis.

Pola yang dicari (hasil pembacaan manual 9 dokumen pilot):
  TERMASUK BHP
    D1  definisi baku: "Jasa sarana adalah imbalan ... atas pemakaian sarana, fasilitas ... dan bahan"
        (+ definisi "Bahan adalah obat..., alat kesehatan habis pakai")
    D2  "tarif ... sudah termasuk ... (BHP | bahan habis pakai | alat kesehatan habis pakai)"
    D3  "jasa sarana ... meliputi/mencakup ... bahan habis pakai"
  TIDAK TERMASUK BHP
    N1  "(tidak|belum) termasuk ... (BHP | bahan habis pakai | alat/bahan ... habis pakai)"
    N2  "(BHP | bahan habis pakai) ... (dibayar|dibebankan|ditanggung|dihitung|ditagih) (tersendiri|terpisah)"
    N3  "pasien menanggung biaya (BHP | bahan habis pakai)"
    N4  "ditambah (biaya)? alat dan bahan" / "di luar (BHP | obat dan barang habis pakai)"
  Kalimat yang hanya tentang bahan kontras, resep, atau obat yang diresepkan diabaikan.

Keputusan: N mengalahkan D (pengecualian eksplisit lebih kuat dari definisi); bila keduanya ada,
kolom konflik = ya. Tanpa bukti: tidak_jelas (catatan bila hanya "tidak termasuk obat").

Pemakaian: python -I pilot/src/bhp_pasal.py <daftar_pdf.txt | folder> <keluaran.csv>
"""
import csv
import os
import re
import sys

BHP = r"(?:BHP|bahan\s+habis\s+pakai|alat\s+kesehatan\s+habis\s+pakai|alat\s*/\s*bahan\s+habis\s+pakai|barang\s+habis\s+pakai|alkes\s+habis\s+pakai)"
RULES = [
    ("N1", "tidak", re.compile(rf"(?:tidak|belum)\s+termasuk\b[^.;]{{0,120}}?{BHP}", re.I)),
    ("N2", "tidak", re.compile(rf"{BHP}[^.;]{{0,120}}?(?:dibayar|dibebankan|ditanggung|dihitung|ditagih|diperhitungkan)\s+"
                               rf"(?:secara\s+)?(?:tersendiri|terpisah)", re.I)),
    ("N3", "tidak", re.compile(rf"(?:pasien|pengguna\s+jasa)[^.;]{{0,40}}menanggung[^.;]{{0,30}}{BHP}", re.I)),
    ("N4", "tidak", re.compile(rf"ditambah\s+(?:biaya\s+)?alat\s+dan\s+bahan|di\s*luar\s+(?:dari\s+)?(?:obat\s+dan\s+)?{BHP}", re.I)),
    ("D2", "ya", re.compile(rf"(?:sudah|telah)\s+termasuk\b[^.;]{{0,120}}?{BHP}", re.I)),
    ("D3", "ya", re.compile(rf"jasa\s+sarana\b[^.;]{{0,160}}?(?:meliputi|mencakup|termasuk|terdiri\s+(?:atas|dari))[^.;]{{0,160}}?{BHP}", re.I)),
    # D1: definisi komponen sarana/jasa rumah sakit yang mencakup bahan. Boleh melewati singkatan bertitik
    # ("RSUD R. Ali"), tetapi berhenti di butir definisi berikutnya (" 14. Bahan adalah ...").
    ("D1", "ya", re.compile(
        r"(?:jasa\s+sarana|jasa\s+rumah\s+sakit(?:\s*\(\s*sarana\s*\))?|biaya\s+(?:jasa\s+)?sarana|hospital\s+service)"
        r"(?:\s*\([^)]{0,20}\))?\s+(?:yang\s+selanjutnya[^,]{0,40},?\s*)?adalah"
        r"(?:(?!\s\d{1,2}\s?[.)]\s)[^;]){0,220}?(?:pemakaian|penggunaan|berupa|meliputi)"
        r"(?:(?!\s\d{1,2}\s?[.)]\s)[^;]){0,120}?(?:\bbahan\b|habis\s+pakai)", re.I)),
]
SKIP = re.compile(r"kontras|diresepkan|resep\b|di\s*luar\s+jam|obat\s+yang\s+diresepkan|rumusan\s+tarif|"
                  r"pelatihan|diklat|peralatan|baterai|penelitian|praktik|magang", re.I)
# subjek pengecualian per bagian -> kategori standar baris yang terkena
SCOPE = [
    (r"gigi", "gigi", ["Gigi"]),
    (r"penunjang|laborator", "penunjang", ["Laboratorium", "Radiologi"]),
    (r"radiolog|radiodiagnost|rontgen", "radiologi", ["Radiologi"]),
    (r"rawat\s+inap|akomodasi|kamar|perawatan\s+penderita", "rawat inap", ["Akomodasi & Visite"]),
    (r"rawat\s+jalan|poliklinik|rawat\s+darurat|gawat\s+darurat|\bigd\b", "rawat jalan/darurat", ["Rawat Jalan & Darurat"]),
    (r"persalinan|kebidanan", "kebidanan", ["Kebidanan"]),
    (r"rehabilitasi|fisioterapi", "rehab medik", ["Rehab Medik"]),
    (r"jenazah", "jenazah", []),
    (r"hemodialisa|hemodialisis|cuci\s+darah", "hemodialisa", []),
    (r"elektromedi|diagnostik\s+elektro", "elektromedik", []),
    (r"psikiatri|kesehatan\s+jiwa|psikolog", "psikiatri", []),
    (r"ambulan|mobil\s+jenazah", "ambulans", []),
    (r"visum|medikolegal|medico\s*legal|surat\s+keterangan", "medikolegal", []),
    (r"medical\s+check|\bmcu\b|pemeriksaan\s+kesehatan", "MCU", []),
    (r"operasi|operatif|bedah", "operasi", ["Tindakan Lain", "Mata/THT/Kulit", "Kebidanan"]),
    (r"endoskop|endoscop|colonoscop|kolonoskop", "endoskopi", []),
    (r"kemoterapi|onkologi|neoplasma", "kemoterapi", []),
    (r"tindakan", "tindakan", ["Tindakan Lain", "Mata/THT/Kulit", "Kebidanan"]),
]
SCOPE_RX = [(re.compile(rx, re.I), lab, kat) for rx, lab, kat in SCOPE]


def scope_of(text, start, end=None):
    """Subjek kalimat pengecualian: kata kunci bagian layanan di kalimat/ayat yang sama (sebelum dan di dalam
    kalimat pengecualian). Bila subjeknya merujuk 'sebagaimana dimaksud pada ayat (n)', ayat sebelumnya ikut dibaca."""
    pre = text[max(0, start - 160):start]
    # mulai dari awal ayat ("(4) Retribusi ...") atau kalimat; "ayat (3) tidak ..." bukan awal ayat
    pre = re.split(r"\(\d+\)\.?\s+(?=[A-Z])|\.\s+(?=[A-Z])", pre)[-1]
    if re.search(r"sebagaimana\s+dimaksud\s+(?:pada|dalam)\s+ayat", pre, re.I):
        prev = text[max(0, start - 450):start]
        parts = re.split(r"\(\d+\)\.?\s+(?=[A-Z])", prev)
        pre = " ".join(parts[-2:]) if len(parts) >= 2 else prev
    span = pre + " " + (text[start:end] if end else "")
    best = None
    for rx, lab, kat in SCOPE_RX:
        for m in rx.finditer(span):
            if best is None or m.start() > best[0]:
                best = (m.start(), lab, kat)
    return (best[1], best[2]) if best else (None, [])
OBAT_SAJA = re.compile(r"(?:tidak|belum)\s+termasuk\b[^.;]{0,60}obat", re.I)


def read_pages(path):
    import pymupdf
    doc = pymupdf.open(path)
    out = []
    for i, p in enumerate(doc):
        t = p.get_text() or ""
        t = re.sub(r"-\s*\n\s*", "", t)          # sambung kata terpotong
        out.append((i + 1, " ".join(t.split())))
    return out


PRICE_TOK = re.compile(r"\d{1,3}(?:[.,]\d{3})+")


def body_pages(pages):
    """Halaman batang tubuh: sebelum tabel tarif (halaman LAMPIRAN bertabel harga atau halaman pertama
    dengan >= 5 angka harga, mana yang lebih awal). Catatan di lampiran ditangani per baris oleh konverter."""
    cnt = [len(PRICE_TOK.findall(t)) for _, t in pages]
    lamp = next((i for i, (_, t) in enumerate(pages)
                 if re.search(r"\bLAMPIRAN\b", t[:300], re.I) and sum(cnt[i:i + 2]) >= 5), None)
    first = next((i for i, c in enumerate(cnt) if c >= 5), None)
    cut = min([x for x in (lamp, first) if x is not None], default=len(pages))
    return pages[:cut]  # kosong bila file hanya berisi lampiran/tabel


def bhp_document(path):
    pages = body_pages(read_pages(path))
    if not pages:
        return dict(hal_tubuh=0, bhp_auto="tidak_jelas", aturan="", halaman="", bukti="", konflik="",
                    pengecualian_bagian="", kategori_tidak="", bukti_bagian="", n_bukti_ya=0, n_bukti_tidak=0,
                    catatan="tanpa batang tubuh (hanya lampiran); BHP dibaca dari catatan tabel")
    hits = []
    for pg, text in pages:
        for code, verdict, rx in RULES:
            for m in rx.finditer(text):
                ctx = text[max(0, m.start() - 120): m.end() + 60]
                if SKIP.search(text[max(0, m.start() - 60): m.end() + 10]):
                    continue
                # D2/D3 harus menyangkut tarif atau jasa sarana, bukan pelatihan/diklat
                if verdict == "ya" and re.search(r"pelatihan|diklat|penelitian|praktik|magang|BPJS|persen|\d\s?%", ctx, re.I):
                    continue
                scope = scope_of(text, m.start(), m.end()) if verdict == "tidak" else (None, [])
                hits.append((code, verdict, pg, ctx.strip(), scope))
    neg = [h for h in hits if h[1] == "tidak" and h[4][0] is None]      # pengecualian umum
    part = [h for h in hits if h[1] == "tidak" and h[4][0] is not None]  # pengecualian per bagian
    pos = [h for h in hits if h[1] == "ya"]
    if neg:
        verdict, main = "tidak", neg[0]
    elif pos:
        verdict, main = "ya", sorted(pos, key=lambda h: {"D2": 0, "D3": 1, "D1": 2}[h[0]])[0]
    else:
        verdict, main = "tidak_jelas", None
    note = ""
    if verdict == "tidak_jelas" and any(OBAT_SAJA.search(t) for _, t in pages):
        note = "hanya menyebut obat tidak termasuk; BHP tidak disebut"
    labs = sorted({h[4][0] for h in part})
    kats = sorted({k for h in part for k in h[4][1]})
    return dict(hal_tubuh=len(pages), bhp_auto=verdict, aturan=main[0] if main else "", halaman=main[2] if main else "",
                bukti=main[3][:300] if main else "", konflik="ya" if (neg and pos) else "",
                pengecualian_bagian="; ".join(f"{h[4][0]} (hlm {h[2]})" for h in part)[:300],
                kategori_tidak="|".join(kats), bukti_bagian=(part[0][3][:250] if part else ""),
                n_bukti_ya=len(pos), n_bukti_tidak=len(neg), catatan=note)


def main(src, out_csv):
    if os.path.isdir(src):
        files = sorted(os.path.join(src, f) for f in os.listdir(src) if f.lower().endswith(".pdf"))
    else:
        files = [l.strip() for l in open(src, encoding="utf-8") if l.strip()]
    rows = []
    for k, f in enumerate(files, 1):
        try:
            r = bhp_document(f)
        except Exception as e:  # noqa: BLE001
            r = dict(bhp_auto="tidak_jelas", aturan="", halaman="", bukti="", konflik="", n_bukti_ya=0,
                     n_bukti_tidak=0, catatan=f"galat: {type(e).__name__}")
        rows.append(dict(file=os.path.basename(f), **r))
        if k % 100 == 0:
            print(f"  {k}/{len(files)}", flush=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(Counter(r["bhp_auto"] for r in rows), "| konflik:", sum(r["konflik"] == "ya" for r in rows))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
