"""Putuskan kelas tiap file BPK dari hasil triase_bpk.py, lalu (opsional) pindahkan ke folder.

Kelas akhir dan folder tujuan:
  buku_tarif/teks   : PDF teks berisi daftar item layanan + harga
  buku_tarif/ocr    : buku tarif yang perlu OCR (jenis: scan / campuran / teks_rusak = lapisan OCR lama tak terbaca)
  other/pasal_saja  : hanya pasal, tanpa daftar harga item
  other/tarif_nonmedis : ada daftar harga tetapi bukan layanan medis (parkir, sewa, diklat, dll.)
  other/item_sedikit: hanya 1-9 item harga (mis. tarif PCR atau satu jenis layanan)
  other/perlu_cek   : tidak bisa diputuskan otomatis (sampel OCR kosong, item sedikit, galat)
  other/format_lain : bukan PDF (doc, docx, xlsx, rar, html)

Pemakaian:
  python -I pilot/src/pilah_bpk.py <triase.csv> [<triase_ocr2.csv>] --metadata bpk_v3/metadata.csv --out bpk_v3/klasifikasi.csv
  tambah --pindah untuk benar-benar memindahkan file (git mv) di folder bpk_v3
"""
import argparse
import os
import re
import subprocess

import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from triase_bpk import count_nosep, text_quality  # noqa: E402

NONMED_JUDUL = re.compile(r"parkir|alokasi|pemanfaatan penerimaan|insentif|jasa pelayanan (?:bagi|kepada)|pembagian|remunerasi", re.I)


def decide(r):
    if r.ext != "pdf":
        return "other/format_lain", "", "bukan PDF"
    if isinstance(r.error, str) and r.error:
        return "other/perlu_cek", "", f"galat: {r.error}"
    hal = max(int(r.hal), 1)
    teks_ratio = r.hal_teks / hal
    scan_ratio = r.hal_scan / hal
    # cukup item di lapisan teks
    if r.item_teks >= 10:
        if r.nonmed >= 0.6:
            return "other/tarif_nonmedis", "", f"{r.item_teks} item, {r.nonmed:.0%} bernuansa non-medis"
        if r.mutu < 0.5:
            return "buku_tarif/ocr", "teks_rusak", f"{r.item_teks} item, mutu teks {r.mutu:.0%} (OCR lama rusak)"
        if scan_ratio >= 0.2 and r.hal_scan >= 3:
            return "buku_tarif/ocr", "campuran", f"{r.item_teks} item di teks, {r.hal_scan} hal scan"
        return "buku_tarif/teks", "teks", f"{r.item_teks} item ({r.med_teks} medis)"
    # lampiran mungkin scan: lihat sampel OCR
    if r.hal_ocr > 0:
        if r.item_ocr >= 5 and r.med_ocr >= 1:
            jenis = "scan" if teks_ratio < 0.5 else "campuran"
            return "buku_tarif/ocr", jenis, f"OCR {r.hal_ocr} hal: {r.item_ocr} item ({r.med_ocr} medis)"
        if r.item_ocr >= 5:
            return "other/perlu_cek", "", f"OCR menemukan {r.item_ocr} item tanpa istilah medis"
        if hal >= 10 and r.hal_scan >= 5:
            return "other/perlu_cek", "", f"scan {r.hal_scan} hal, sampel OCR tanpa harga"
        return "other/pasal_saja", "", f"sampel OCR tanpa daftar harga ({r.item_ocr} item)"
    if 1 <= r.item_teks < 10:
        return "other/item_sedikit", "", f"hanya {r.item_teks} item harga (mis. tarif satu jenis layanan)"
    if teks_ratio < 0.5 and r.hal_scan:
        return "other/perlu_cek", "", "scan tanpa sampel OCR"
    return "other/pasal_saja", "", f"{r.item_teks} item harga di {r.hal_teks} hal teks"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("triase", nargs="+")
    ap.add_argument("--metadata", default="bpk_v3/metadata.csv")
    ap.add_argument("--out", default="bpk_v3/klasifikasi.csv")
    ap.add_argument("--folder", default="bpk_v3")
    ap.add_argument("--pindah", action="store_true")
    a = ap.parse_args()
    T = pd.read_csv(a.triase[0])
    for extra in a.triase[1:]:  # hasil OCR putaran kedua menimpa baris yang sama
        E = pd.read_csv(extra)
        T = pd.concat([T[~T.file.isin(E.file)], E], ignore_index=True)
    T["error"] = T["error"].fillna("")
    for c in ["hal", "hal_teks", "hal_scan", "item_teks", "med_teks", "hal_ocr", "item_ocr", "med_ocr"]:
        T[c] = T[c].fillna(0).astype(int)
    M = pd.read_csv(a.metadata)
    M["file"] = M.file.astype(str).str.replace("\\", "/", regex=False).str.split("/").str[-1]
    M = M.drop_duplicates("file")[["file", "nama", "judul", "relasi_json"]]
    T = T.merge(M, on="file", how="left")
    T["mutu"], T["nonmed"] = 1.0, 0.0
    cand = T[(T.ext == "pdf") & (T.item_teks >= 10)]
    print(f"mengukur mutu teks {len(cand)} file...", flush=True)
    for i, r in cand.iterrows():
        try:
            q, nm, _ = text_quality(os.path.join(a.folder, r.file))
        except Exception:  # noqa: BLE001
            q, nm = 0.0, 0.0
        T.at[i, "mutu"], T.at[i, "nonmed"] = round(q, 2), round(nm, 2)
    # harga tanpa titik ribuan (mis. "126000"): tambahkan ke hitungan item
    T["item_nosep"] = 0
    low = T[(T.ext == "pdf") & (T.item_teks < 10) & (T.hal_teks > 0)]
    for i, r in low.iterrows():
        try:
            T.at[i, "item_nosep"] = count_nosep(os.path.join(a.folder, r.file))
        except Exception:  # noqa: BLE001
            pass
    T["item_teks"] = T.item_teks + T.item_nosep.where(T.item_nosep >= 10, 0)
    res = [decide(r) for r in T.itertuples()]
    T["folder"], T["jenis"], T["alasan"] = zip(*res)
    # judul yang jelas bukan buku tarif layanan
    m = T.judul.fillna("").str.contains(NONMED_JUDUL) & T.folder.str.startswith("buku_tarif")
    T.loc[m, "folder"] = "other/perlu_cek"
    T.loc[m, "alasan"] = T.loc[m, "alasan"] + "; judul menyiratkan bukan tarif layanan"
    T["path_baru"] = a.folder + "/" + T.folder + "/" + T.file
    cols = ["file", "folder", "jenis", "alasan", "nama", "judul", "hal", "hal_teks", "hal_scan", "item_teks",
            "med_teks", "item_nosep", "mutu", "nonmed", "hal_ocr", "item_ocr", "med_ocr", "error", "path_baru", "relasi_json"]
    T[cols].sort_values(["folder", "file"]).to_csv(a.out, index=False)
    print(T.folder.value_counts().to_string())
    print(T[T.folder == "buku_tarif/ocr"].jenis.value_counts().to_string())
    if a.pindah:
        for f in sorted(set(T.folder)):
            os.makedirs(os.path.join(a.folder, f), exist_ok=True)
        moved = 0
        for r in T.itertuples():
            src = os.path.join(a.folder, r.file)
            if os.path.exists(src):
                subprocess.run(["git", "mv", "-k", src, os.path.join(a.folder, r.folder, r.file)], check=False)
                moved += 1
        print(f"dipindahkan: {moved}")


if __name__ == "__main__":
    main()
