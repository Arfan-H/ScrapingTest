"""Uji konverter (to_standard.extract_doc) pada semua buku tarif teks hasil pilah_bpk.py.

Keluaran:
  <out_dir>/uji_parser_per_dokumen.csv : metrik per dokumen
  <out_dir>/uji_parser_baris.csv.gz    : semua baris tarif hasil ekstraksi
Status BHP di sini hanya dari catatan lampiran; status dari pasal ditambahkan oleh bhp_pasal.py + terapkan_bhp.py.

Pemakaian: python -I pilot/src/uji_parser_bpk.py bpk_v3/klasifikasi.csv bpk_v3 <out_dir> [proses] [daftar_file.txt]
"""
import multiprocessing as mp
import os
import sys
import time
import warnings

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")


PROBLEM = {"nama_terpotong", "komponen_tidak_jumlah", "kolom_harga_tak_dikenal", "kelas_grup_tanpa_judul",
           "kelas_kolom_tanpa_judul", "harga_ambigu", "urutan_kelas_aneh", "label_kelas_tak_jelas"}


def run_one(args):
    path, dok_id, item_teks = args
    from to_standard import extract_doc  # impor di proses anak
    t0 = time.time()
    try:
        rows = extract_doc(path, dok_id)
        err = ""
    except Exception as e:  # noqa: BLE001
        rows, err = [], f"{type(e).__name__}: {str(e)[:100]}"
    df = pd.DataFrame(rows)
    m = dict(dokumen_id=dok_id, baris=len(df), item_teks_triase=item_teks, detik=round(time.time() - t0, 1), error=err)
    if len(df):
        flags = df["_flags"].map(lambda f: f or ["ok"]).explode()
        n = len(df)
        m.update(nama_unik=df.nama_asli.nunique(),
                 cakupan=round(df.baris_mentah.nunique() / max(item_teks, 1), 2),
                 pct_ok=round((df["_flags"].map(len) == 0).mean() * 100, 1),
                 # flag informatif (nama/kelas berhasil diturunkan dari konteks) tidak dihitung sebagai masalah
                 pct_bermasalah=round(df["_flags"].map(lambda f: bool(set(f) & PROBLEM)).mean() * 100, 1),
                 pct_dari_kolom_kelas=round((flags == "dari_kolom_kelas").sum() / n * 100, 1),
                 pct_komponen_tidak_jumlah=round((flags == "komponen_tidak_jumlah").sum() / n * 100, 1),
                 pct_kolom_tak_dikenal=round((flags == "kolom_harga_tak_dikenal").sum() / n * 100, 1),
                 pct_nama_terpotong=round((flags == "nama_terpotong").sum() / n * 100, 1),
                 pct_bhp_terbaca=round((df.termasuk_bhp != "tidak_jelas").mean() * 100, 1),
                 harga_median=float(df.harga.median()))
        df["flags"] = df["_flags"].map(lambda f: "|".join(f))
        df = df.drop(columns=["_flags", "_blok"], errors="ignore")
    return m, df


def main(klas_csv, folder, out_dir, procs=4, only=None):
    K = pd.read_csv(klas_csv)
    K = K[K.folder == "buku_tarif/teks"]
    if only:  # daftar nama file (satu per baris) untuk uji sebagian
        keep = {l.strip() for l in open(only, encoding="utf-8") if l.strip()}
        K = K[K.file.isin(keep)]
    jobs = []
    for r in K.itertuples():
        path = os.path.join(folder, r.folder, r.file)
        if not os.path.exists(path):
            path = os.path.join(folder, r.file)
        jobs.append((path, r.file, int(r.item_teks)))
    print(f"{len(jobs)} buku tarif teks", flush=True)
    os.makedirs(out_dir, exist_ok=True)
    metrics, parts = [], []
    with mp.Pool(procs) as pool:
        for k, (m, df) in enumerate(pool.imap_unordered(run_one, jobs), 1):
            metrics.append(m)
            if len(df):
                parts.append(df)
            if k % 25 == 0:
                print(f"  {k}/{len(jobs)}", flush=True)
    M = pd.DataFrame(metrics).sort_values("dokumen_id")
    M.to_csv(os.path.join(out_dir, "uji_parser_per_dokumen.csv"), index=False)
    if parts:
        pd.concat(parts, ignore_index=True).to_csv(os.path.join(out_dir, "uji_parser_baris.csv.gz"), index=False)
    print("selesai", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 4,
         sys.argv[5] if len(sys.argv) > 5 else None)
