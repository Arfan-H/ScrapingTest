"""Adapter khusus format "golongan tindakan" (contoh: Perbup Rembang 16/2023).

Format ini tidak memberi harga per tindakan. Yang ada:
  (a) matriks tarif  Golongan x Kelas  (mis. Kelompok II, kelas I = 2.940.000)
  (b) daftar anggota "Jenis tindakan medis operatif kategori kelompok II ..."
Di graf:  Layanan -[MASUK_GOLONGAN]-> Golongan -[TARIF {kelas}]-> harga
"""
import csv
import re
import sys

import pdfplumber

KELAS_SEQ = ["III", "II", "I", "VIP Pratama & Madya", "VIP Utama", "One Day Surgery"]
GOL_ORDER = {
    "operatif": ["tindakan kecil", "kelompok i", "kelompok ii", "kelompok iii", "kelompok khusus"],
    "non operatif": ["tindakan kecil", "tindakan sedang", "tindakan besar", "tindakan khusus"],
}
PRICE = re.compile(r"\d{1,3}(?:\.\d{3})+")
HEAD = re.compile(r"Jenis tindakan medis\s+(non operatif|operatif)?\s*kategori\s+(.+?)\s+sebagai", re.I)
ITEM = re.compile(r"^\d+\.\d+\.\s+(.*)")


def run(pdf_path, out_prefix):
    with pdfplumber.open(pdf_path) as pdf:
        lines = []
        for pno in range(17, 42):
            for l in (pdf.pages[pno].extract_text() or "").splitlines():
                lines.append((pno + 1, l.strip()))

    # (a) matriks tarif
    tarif, jenis, block, k = [], None, -1, 0
    for pno, l in lines:
        if "TINDAKAN MEDIS OPERATIF" in l and "NON" not in l:
            jenis, block = "operatif", -1
        elif "TINDAKAN MEDIS NON OPERATIF" in l:
            jenis, block = "non operatif", -1
        if jenis is None:
            continue
        prices = PRICE.findall(l)
        if not prices or not re.match(r"^(TINDAKAN|KELOMPOK|III|II|I|VIP|One Day)\b", l):
            continue
        if re.match(r"^(TINDAKAN|KELOMPOK)\s+III\b", l):
            block, k = block + 1, 0
        if block < 0 or block >= len(GOL_ORDER[jenis]) or k >= len(KELAS_SEQ):
            continue
        tarif.append(dict(jenis=jenis, golongan=GOL_ORDER[jenis][block], kelas=KELAS_SEQ[k],
                          total=int(prices[-1].replace(".", "")), page=pno))
        k += 1

    # (b) anggota golongan
    anggota, cur = [], None
    for pno, l in lines:
        h = HEAD.search(l + " sebagai")  # judul kadang terpotong baris
        if h and "Jenis tindakan" in l:
            j = (h.group(1) or "operatif").lower()
            g = h.group(2).lower().replace("one day surgery", "one day surgery")
            cur = (j, g.strip())
            continue
        if cur is None:
            continue
        m = ITEM.match(l)
        if m:
            anggota.append(dict(jenis=cur[0], golongan=cur[1], nama_asli=m.group(1), page=pno))
        elif anggota and not re.match(r"^\d+\.\s", l) and not PRICE.search(l) and len(l) < 70:
            anggota[-1]["nama_asli"] += " " + l  # lanjutan baris
        elif re.match(r"^\d+\.\s", l) and not HEAD.search(l + " sebagai"):
            cur = None

    for name, rows in [("golongan_tarif", tarif), ("golongan_anggota", anggota)]:
        with open(f"{out_prefix}_{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"tarif golongan: {len(tarif)} sel | anggota golongan: {len(anggota)} tindakan")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
