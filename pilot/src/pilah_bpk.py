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
from triase_bpk import count_items_loose, count_nosep, text_quality  # noqa: E402

NONMED_JUDUL = re.compile(r"parkir|alokasi|pemanfaatan penerimaan|insentif|jasa pelayanan (?:bagi|kepada)|pembagian|remunerasi", re.I)
NONMED_TARIF_JUDUL = re.compile(r"non[ -]?medis|non[ -]?pelayanan|kegiatan non|^\s*tarif (?:pelayanan|layanan) lainnya", re.I)


FOLDERS = ["", "buku_tarif/teks", "buku_tarif/ocr", "other/pasal_saja", "other/item_sedikit", "other/tarif_nonmedis",
           "other/perlu_cek", "other/format_lain"]


def find_file(folder, name):
    """Lokasi file sekarang (di akar folder atau di salah satu subfolder kelas)."""
    for f in FOLDERS:
        p = os.path.join(folder, f, name)
        if os.path.exists(p):
            return p
    return os.path.join(folder, name)


STOP = set("dan atas pada di tentang yang dengan nomor tahun peraturan rumah sakit umum daerah badan layanan tarif "
           "pelayanan kesehatan perubahan kedua ketiga kab kabupaten kota provinsi".split())


def title_check(path, judul):
    """Bandingkan frasa 'TENTANG ...' di halaman pertama PDF dengan judul metadata BPK."""
    import pymupdf
    try:
        doc = pymupdf.open(path)
        head = " ".join(" ".join((doc[i].get_text() or "").split()) for i in range(min(2, doc.page_count)))
    except Exception:  # noqa: BLE001
        return "", 1.0
    t = re.search(r"TENTANG\s+(.{10,160})", head, re.I)
    apbd = bool(t and re.search(r"ANGGARAN PENDAPATAN DAN BELANJA", t.group(1), re.I))
    m = re.search(r"TENTANG\s+(.{10,200}?)(?:DENGAN RAHMAT|Menimbang|BUPATI|WALI ?KOTA|GUBERNUR|MENTERI)", head, re.I)
    if not m or not isinstance(judul, str):
        return ("apbd" if apbd else ""), 1.0
    a = {w for w in re.findall(r"[a-z]{3,}", m.group(1).lower())} - STOP
    b = {w for w in re.findall(r"[a-z]{3,}", judul.lower())} - STOP
    sim = len(a & b) / max(len(a | b), 1)
    return ("apbd" if apbd else ""), round(sim, 2)


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
    # harga tanpa titik ribuan (mis. "126000") dan baris bersatuan/desimal ("200.000,00 Per Tindakan")
    T["item_nosep"], T["item_longgar"] = 0, 0
    low = T[(T.ext == "pdf") & (T.item_teks < 10) & (T.hal_teks > 0)]
    print(f"menghitung ulang {len(low)} file berteks dengan item < 10...", flush=True)
    for i, r in low.iterrows():
        src = find_file(a.folder, r.file)
        try:
            T.at[i, "item_nosep"] = count_nosep(src)
            T.at[i, "item_longgar"] = count_items_loose(src)[0]
        except Exception:  # noqa: BLE001
            pass
    bonus = pd.concat([T.item_nosep.where(T.item_nosep >= 10, 0), T.item_longgar.where(T.item_longgar >= 10, 0)], axis=1).max(axis=1)
    T["item_teks"] = T.item_teks + bonus
    T["mutu"], T["nonmed"] = 1.0, 0.0
    cand = T[(T.ext == "pdf") & (T.item_teks >= 10)]
    print(f"mengukur mutu teks {len(cand)} file...", flush=True)
    for i, r in cand.iterrows():
        try:
            q, nm, _ = text_quality(find_file(a.folder, r.file))
        except Exception:  # noqa: BLE001
            q, nm = 0.0, 0.0
        T.at[i, "mutu"], T.at[i, "nonmed"] = round(q, 2), round(nm, 2)
    res = [decide(r) for r in T.itertuples()]
    T["folder"], T["jenis"], T["alasan"] = zip(*res)
    # judul yang jelas bukan buku tarif layanan
    m = T.judul.fillna("").str.contains(NONMED_TARIF_JUDUL) & T.folder.str.startswith("buku_tarif")
    T.loc[m, "folder"] = "other/tarif_nonmedis"
    T.loc[m, "alasan"] = T.loc[m, "alasan"] + "; judul menyebut tarif non-medis/non-pelayanan"
    m = T.judul.fillna("").str.contains(NONMED_JUDUL) & T.folder.str.startswith("buku_tarif")
    T.loc[m, "folder"] = "other/perlu_cek"
    T.loc[m, "alasan"] = T.loc[m, "alasan"] + "; judul menyiratkan bukan tarif layanan"
    # kecocokan isi PDF dengan judul metadata (sumber kadang mengunggah file yang salah)
    T["cek_judul"], T["kemiripan_judul"] = "", 1.0
    for i, r in T[T.folder.str.startswith("buku_tarif")].iterrows():
        flag, sim = title_check(find_file(a.folder, r.file), r.judul)
        T.at[i, "kemiripan_judul"] = sim
        if flag == "apbd":
            T.at[i, "folder"], T.at[i, "jenis"] = "other/perlu_cek", ""
            T.at[i, "alasan"] = "isi PDF adalah APBD, tidak sesuai judul metadata"
            T.at[i, "cek_judul"] = "isi_tidak_sesuai"
    T["path_baru"] = a.folder + "/" + T.folder + "/" + T.file
    cols = ["file", "folder", "jenis", "alasan", "nama", "judul", "hal", "hal_teks", "hal_scan", "item_teks",
            "med_teks", "item_nosep", "item_longgar", "mutu", "nonmed", "cek_judul", "kemiripan_judul", "hal_ocr", "item_ocr", "med_ocr", "error", "path_baru", "relasi_json"]
    T[cols].sort_values(["folder", "file"]).to_csv(a.out, index=False)
    print(T.folder.value_counts().to_string())
    print(T[T.folder == "buku_tarif/ocr"].jenis.value_counts().to_string())
    if a.pindah:
        for f in sorted(set(T.folder)):
            os.makedirs(os.path.join(a.folder, f), exist_ok=True)
        moved = 0
        for r in T.itertuples():
            src = find_file(a.folder, r.file)
            dst = os.path.join(a.folder, r.folder, r.file)
            if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(dst):
                subprocess.run(["git", "mv", "-k", src, dst], check=False)
                moved += 1
        print(f"dipindahkan: {moved}")


if __name__ == "__main__":
    main()
