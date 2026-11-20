"""Verifikasi bahwa setiap harga di dataset tertulis di baris PDF sumbernya (kolom baris_mentah).

Untuk tiap baris tarif, semua angka harga di baris_mentah dibaca ulang secara independen dari konverter
(titik/koma ribuan, ",00", ",-", angka terpecah spasi seperti "1 4,453,125"). Harga dinyatakan:
  cocok_langsung : harga sama dengan salah satu angka di baris sumber
  cocok_gabungan : harga cocok setelah angka yang terpecah spasi digabung ("2 ,929,688" -> 2.929.688)
  cocok_digit_pemisah_dibetulkan : digit sama dengan token di PDF, pemisah ribuan dibetulkan ("6028.890" -> 6.028.890)
  tidak_cocok    : harga tidak ditemukan di baris sumber -> perlu dicek manual

Pemakaian: python -I pilot/src/verifikasi_harga.py pilot/out/dataset/tarif.csv.gz pilot/out/dataset/verifikasi_harga.csv
"""
import re
import sys

import pandas as pd

TOK = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:,\d{2})?|\d{4,9}(?:,\d{2})?")


def numbers(text):
    out = set()
    for t in TOK.findall(text):
        t = re.sub(r",\d{2}$", "", t) if re.search(r"[.,]\d{3},\d{2}$", t) or re.fullmatch(r"\d+,\d{2}", t) else t
        out.add(int(re.sub(r"[.,]", "", t)))
    return out


def check(raw, harga):
    raw = str(raw)
    h = int(round(harga))
    if h in numbers(raw.replace(",-", "")):
        return "cocok_langsung"
    # gabung angka terpecah spasi, hanya pola yang jelas: "3.750 .000", "2 ,929,688", "1 4,453,125", "5 7.000"
    fixed = raw.replace(",-", "")
    fixed = re.sub(r"(\d)\s+([.,]\d{3})", r"\1\2", fixed)
    fixed = re.sub(r"(?<![\d.,])(\d) (\d{1,2}(?:[.,]\d{3})+)(?!\d)", r"\1\2", fixed)
    if h in numbers(fixed):
        return "cocok_gabungan"
    # digit sama persis dengan satu token di PDF, hanya pemisah ribuan yang salah ("6028.890" -> 6.028.890)
    for tok in re.findall(r"\d[\d.,]*\d", raw):
        if int(re.sub(r"\D", "", re.sub(r"(,00|,-)$", "", tok))) == h:
            return "cocok_digit_pemisah_dibetulkan"
    return "tidak_cocok"


def main(src, out):
    T = pd.read_csv(src, low_memory=False, usecols=["tarif_id", "dokumen_id", "file", "halaman", "nama_asli", "kelas",
                                                    "harga", "flag_qc", "qc_masalah", "baris_mentah"])
    T["verifikasi"] = [check(r, h) for r, h in zip(T.baris_mentah, T.harga)]
    print(T.verifikasi.value_counts().to_dict())
    print("per qc_masalah:", T.groupby("qc_masalah").verifikasi.apply(lambda s: (s == "tidak_cocok").mean().round(4)).to_dict())
    T[T.verifikasi != "cocok_langsung"].to_csv(out, index=False)
    d = T.groupby("dokumen_id").verifikasi.apply(lambda s: (s == "tidak_cocok").mean())
    print("dokumen dengan >1% harga tidak cocok:", (d > 0.01).sum(), "dari", len(d))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
