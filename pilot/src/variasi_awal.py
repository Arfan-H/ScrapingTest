"""Analisis variasi tarif AWAL antar-RS (bahan RQ2), dari tabel standar banyak dokumen.

Cara:
  - kelompokkan layanan dengan nama ternormalisasi identik (SAMA_NAMA) yang muncul di >= MIN_RS dokumen
  - satu harga per dokumen: kelas III, lalu "Kelas III-I", lalu Non-kelas (harga terendah bila ganda)
  - buang baris berflag nama_terpotong, duplikat, kolom_harga_tak_dikenal, komponen_tidak_jumlah
  - catat status BHP tiap dokumen; ringkasan dihitung untuk semua dan untuk BHP yang seragam

Ini BUKAN hasil akhir: tahun peraturan berbeda (2013-2025, belum disesuaikan inflasi), kelas RS sebagian
belum dicek, dan nama identik belum tentu layanan identik.
"""
import os

import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "out")
MIN_RS = 3
PREF = ["III", "Kelas III-I", "Non-kelas"]

t = pd.read_csv(f"{OUT}/tarif_standar.csv")
t = t[t.harga.notna() & ~t.flag_qc.str.contains("nama_terpotong|duplikat|kolom_harga_tak_dikenal|komponen_tidak_jumlah")]
t = t[t.kelas.isin(PREF)]
dok = pd.read_excel(f"{OUT}/tarif_standar.xlsx", sheet_name="dokumen").set_index("dokumen_id")
tahun = dok.tahun.to_dict()

t["pref"] = t.kelas.map({k: i for i, k in enumerate(PREF)})
one = (t.sort_values(["pref", "harga"]).groupby(["nama_norm", "dokumen_id"], as_index=False).first())
cnt = one.groupby("nama_norm").dokumen_id.nunique()
one = one[one.nama_norm.isin(cnt[cnt >= MIN_RS].index)]

rows = []
for n, g in one.groupby("nama_norm"):
    h = g.harga.values
    bhp = set(g.termasuk_bhp)
    rows.append(dict(nama_norm=n, contoh_nama=g.nama_asli.iloc[0], kategori=g.kategori_std.mode().iloc[0],
                     n_rs=len(g), harga_min=h.min(), harga_median=np.median(h), harga_max=h.max(),
                     rasio_max_min=h.max() / h.min(), cv=h.std(ddof=0) / h.mean(),
                     bhp_seragam=(len(bhp) == 1 and "tidak_jelas" not in bhp),
                     rincian="; ".join(f"{d.split('-')[1]}-{tahun[d]}:{int(x):,}({k},{b})" for d, x, k, b in
                                       zip(g.dokumen_id, g.harga, g.kelas, g.termasuk_bhp))))
V = pd.DataFrame(rows).sort_values("n_rs", ascending=False)
V.to_csv(f"{OUT}/variasi_awal.csv", index=False)

print(f"Layanan dengan nama identik di >= {MIN_RS} RS: {len(V)} (di >= 5 RS: {(V.n_rs >= 5).sum()})")
print(f"Median rasio harga max/min: {V.rasio_max_min.median():.2f}x | median CV: {V.cv.median():.2f}")
print(f"Dengan BHP seragam: {V.bhp_seragam.sum()} layanan, median rasio {V[V.bhp_seragam].rasio_max_min.median():.2f}x")
print(V.groupby("kategori").agg(n=("n_rs", "size"), median_rasio=("rasio_max_min", "median"), median_cv=("cv", "median")).round(2).to_string())
print("\nContoh (paling banyak RS):")
print(V.head(12)[["contoh_nama", "n_rs", "harga_min", "harga_median", "harga_max", "rasio_max_min"]].to_string(index=False))
