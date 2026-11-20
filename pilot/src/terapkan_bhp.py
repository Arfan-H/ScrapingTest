"""Terapkan status BHP hasil bhp_pasal.py ke baris tarif hasil uji_parser_bpk.py.

Urutan prioritas per baris:
  1. catatan di lampiran (sudah diisi konverter: catatan_lokal / catatan_bagian)
  2. pengecualian per bagian dari pasal (mis. "tarif pelayanan gigi belum termasuk BHP") -> baris
     yang kategori standarnya cocok menjadi "tidak" (sumber: pasal_bagian)
  3. status dokumen dari pasal (definisi jasa sarana / pengecualian umum) (sumber: pasal_dokumen)

Pemakaian: python -I pilot/src/terapkan_bhp.py pilot/out/bpk/uji_parser_baris.csv.gz pilot/out/bpk/bhp_pasal.csv <keluaran.csv.gz>
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from normalize import norm_name, std_category  # noqa: E402


def main(rows_path, bhp_path, out_path):
    R = pd.read_csv(rows_path, low_memory=False)
    B = pd.read_csv(bhp_path, dtype=str).fillna("").set_index("file")
    if "sumber_bhp" not in R.columns:
        R["sumber_bhp"] = ""
    R["sumber_bhp"] = R["sumber_bhp"].fillna("")
    before = (R.termasuk_bhp != "tidak_jelas").mean()
    R["kategori_std"] = [std_category(k if isinstance(k, str) else "", norm_name(n))
                         for k, n in zip(R.kategori_asli, R.nama_asli.astype(str))]
    doc = R.dokumen_id.map(B.bhp_auto).fillna("tidak_jelas")
    kat_tidak = R.dokumen_id.map(B.kategori_tidak).fillna("")
    open_ = R.termasuk_bhp == "tidak_jelas"
    hit = pd.Series([bool(kt) and k in kt.split("|") for k, kt in zip(R.kategori_std, kat_tidak)], index=R.index)
    part = open_ & hit
    R.loc[part, ["termasuk_bhp", "sumber_bhp"]] = ["tidak", "pasal_bagian"]
    rest = open_ & ~part & (doc != "tidak_jelas")
    R.loc[rest, "termasuk_bhp"] = doc[rest]
    R.loc[rest, "sumber_bhp"] = "pasal_dokumen"
    after = (R.termasuk_bhp != "tidak_jelas").mean()
    R.to_csv(out_path, index=False)
    print(f"baris: {len(R):,} | BHP terbaca: {before:.1%} -> {after:.1%}")
    print(R.groupby(["termasuk_bhp", "sumber_bhp"]).size().to_string())
    d = R.groupby("dokumen_id").termasuk_bhp.apply(lambda s: (s != "tidak_jelas").mean())
    print(f"dokumen dengan >= 90% baris berstatus BHP: {(d >= 0.9).sum()} dari {len(d)}")
    per_doc = os.path.join(os.path.dirname(out_path), "uji_parser_per_dokumen.csv")
    if os.path.exists(per_doc):
        M = pd.read_csv(per_doc)
        M["pct_bhp_terbaca_akhir"] = M.dokumen_id.map((d * 100).round(1))
        M["bhp_dokumen_auto"] = M.dokumen_id.map(B.bhp_auto)
        M.to_csv(per_doc, index=False)


if __name__ == "__main__":
    main(*sys.argv[1:4])
