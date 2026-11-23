"""Hitung skor gold set ekstraksi v2 dari file penilaian yang sudah diisi.

Pemakaian: python -I pilot/eval/nilai_gold_ekstraksi.py <gold_terisi.xlsx> [gold_penilai_kedua.xlsx]

Estimasi (ditetapkan sebelum penilaian dilakukan):
- Unit sampling = dokumen. Di dalam strata, akurasi = sum(n_d * p_d) / sum(n_d) atas dokumen sampel
  (n_d = jumlah baris data dokumen, p_d = proporsi benar baris sampel dokumen itu).
- Gabungan = sum(W_h * akurasi_h), W_h = porsi baris strata h di SELURUH dataset (gold_ekstraksi_v2_strata.csv,
  kolom baris_semua), dinormalkan ulang atas strata yang punya sampel. Juga dilaporkan bobot 'eligible'.
- Interval 95% = bootstrap persentil (2000 ulangan), dokumen diambil ulang dengan pengembalian di dalam tiap strata.
- 'Tidak bisa dinilai' dan isian kosong dikeluarkan per kolom. Butir kontrol (nilai sengaja diubah) tidak ikut
  akurasi; dipakai untuk ketelitian penilai = porsi butir kontrol yang kolom ubahannya dinilai 'Tidak'.
- Angka akhir: bagian 'test'; 'semua' (dev+test) hanya sah bila parser tidak diubah setelah penilaian.
- Cakupan: di antara baris PDF yang dinilai memuat tarif, porsi 'Ya semua' (lengkap) dan 'Tidak ada' (hilang total).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(HERE, "gold")
B = 2000
FIELDS = {"nama": "NAMA benar?", "kelas": "KELAS benar?", "varian_komponen": "VARIAN/KOMPONEN benar?",
          "harga": "HARGA benar?"}
CTRL_COL = {"nama_asli": "nama", "kelas": "kelas", "harga": "harga"}


def read(path):
    P = pd.read_excel(path, sheet_name="nilai_baris")
    R = pd.read_excel(path, sheet_name="cek_baris_pdf")
    M = pd.read_csv(os.path.join(G, "gold_ekstraksi_v2_manifest.csv"))
    RM = pd.read_csv(os.path.join(G, "gold_ekstraksi_v2_cakupan_manifest.csv"))
    P = M.merge(P[["id_gold"] + list(FIELDS.values())], on="id_gold", how="left")
    for k, c in FIELDS.items():
        v = P[c].astype(str).str.strip().str.lower()
        P[k] = np.where(v == "ya", 1.0, np.where(v == "tidak", 0.0, np.nan))
    ok = P[list(FIELDS)]
    P["semua"] = np.where(ok.isna().any(axis=1), np.nan, ok.min(axis=1))
    c1, c2 = "Baris ini memuat TARIF layanan?", "Semua harga di baris ini ada di data dengan benar?"
    R = RM.merge(R[["id_gold", c1, c2]], on="id_gold", how="left")
    R["tarif"] = R[c1].astype(str).str.strip().str.lower()
    v = R[c2].astype(str).str.strip().str.lower()
    R["lengkap"] = np.where(v == "ya semua", 1.0, np.where(v.isin(["sebagian", "tidak ada"]), 0.0, np.nan))
    R["hilang"] = np.where(v == "tidak ada", 1.0, np.where(v.isin(["sebagian", "ya semua"]), 0.0, np.nan))
    R.loc[R.tarif != "ya", ["lengkap", "hilang"]] = np.nan
    return P, R


def estimate(df, col, W, rng):
    """(estimasi tertimbang, CI bawah, CI atas, n butir, n dokumen)."""
    d = df[df[col].notna()]
    if d.empty:
        return (np.nan,) * 3 + (0, 0)
    doc = d.groupby(["strata", "dokumen_id"]).agg(p=(col, "mean"), n=("n_baris_dok", "first")).reset_index()

    def est(dd):
        acc = dd.groupby("strata").apply(lambda g: np.sum(g.n * g.p) / np.sum(g.n), include_groups=False)
        w = W.reindex(acc.index).fillna(0)
        return float(np.sum(acc * w) / w.sum()) if w.sum() else np.nan

    point = est(doc)
    groups = {s: g.reset_index(drop=True) for s, g in doc.groupby("strata")}
    boots = []
    for _ in range(B):
        boots.append(est(pd.concat([g.iloc[rng.integers(0, len(g), len(g))] for g in groups.values()])))
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return point, lo, hi, len(d), doc.dokumen_id.nunique()


def kappa(a, b):
    m = a.notna() & b.notna()
    a, b = a[m], b[m]
    if len(a) == 0:
        return np.nan, 0
    po = (a == b).mean()
    cats = sorted(set(a) | set(b))
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0, len(a)


def main(path, path2=None):
    rng = np.random.default_rng(7)
    S = pd.read_csv(os.path.join(G, "gold_ekstraksi_v2_strata.csv")).set_index("strata")
    P, R = read(path)
    n_doc = P.drop_duplicates("dokumen_id").set_index("dokumen_id").n_baris_dok
    R["n_baris_dok"] = R.dokumen_id.map(n_doc)
    out = [f"# Hasil gold set ekstraksi v2\n\nFile: `{os.path.basename(path)}`\n"]
    pres = P[P.jenis == "presisi"]
    filled = pres[list(FIELDS)].notna().any(axis=1).mean()
    out.append(f"Baris presisi terisi: {filled:.0%} dari {len(pres)}.\n")
    for wname, wcol in [("seluruh dataset", "baris_semua"), ("dokumen eligible", "baris_eligible")]:
        W = S[wcol].astype(float)
        out.append(f"\n\n## Presisi (bobot strata: {wname})\n\n| ukuran | bagian | estimasi | CI 95% | n baris | n dok |\n|---|---|---|---|---|---|\n")
        for k in list(FIELDS) + ["semua"]:
            for part in ["test", "dev", "semua"]:
                d = pres if part == "semua" else pres[pres.split == part]
                e = estimate(d, k, W, rng)
                out.append(f"| {k} | {part} | {e[0]:.1%} | {e[1]:.1%}-{e[2]:.1%} | {e[3]} | {e[4]} |\n")
        if wcol == "baris_semua":
            out.append(f"\n\n## Cakupan (baris PDF -> data; bobot: {wname})\n\n| ukuran | bagian | estimasi | CI 95% | n baris | n dok |\n|---|---|---|---|---|---|\n")
            for k in ["lengkap", "hilang"]:
                for part in ["test", "dev", "semua"]:
                    d = R if part == "semua" else R[R.split == part]
                    e = estimate(d, k, W, rng)
                    out.append(f"| {k} | {part} | {e[0]:.1%} | {e[1]:.1%}-{e[2]:.1%} | {e[3]} | {e[4]} |\n")
            out.append(f"\nBaris PDF yang dinilai bukan tarif: {(R.tarif == 'tidak').sum()} dari {R.tarif.isin(['ya', 'tidak']).sum()}.\n")
    # per strata (tanpa bobot antar-strata)
    out.append("\n\n## Per strata (semua bagian, baris 'semua kolom benar')\n\n| strata | n dok | n baris | akurasi |\n|---|---|---|---|\n")
    for s, d in pres[pres.semua.notna()].groupby("strata"):
        out.append(f"| {s} | {d.dokumen_id.nunique()} | {len(d)} | {d.semua.mean():.1%} |\n")
    # ketelitian penilai
    C = P[P.jenis == "kontrol"].copy()
    C["terdeteksi"] = [r[CTRL_COL[r.kolom_diubah]] if r.kolom_diubah in CTRL_COL else np.nan for _, r in C.iterrows()]
    C["terdeteksi"] = 1 - C.terdeteksi
    out.append(f"\n\n## Ketelitian penilai (butir kontrol)\n\n{int(C.terdeteksi.sum()) if C.terdeteksi.notna().any() else 0} dari "
               f"{C.terdeteksi.notna().sum()} nilai yang sengaja diubah ditandai 'Tidak' "
               f"({C.terdeteksi.mean():.0%}). Per kolom: " +
               "; ".join(f"{k}: {g.terdeteksi.mean():.0%} (n={g.terdeteksi.notna().sum()})" for k, g in C.groupby("kolom_diubah")) + ".\n"
               "Bila jauh di bawah 100%, akurasi di atas kemungkinan terlalu tinggi (penilai cenderung setuju).\n")
    if path2:
        P2, R2 = read(path2)
        out.append(f"\n\n## Kesepakatan antar-penilai (`{os.path.basename(path2)}`)\n\n| kolom | kappa Cohen | % sama | n |\n|---|---|---|---|\n")
        J = P.merge(P2[["id_gold"] + list(FIELDS) + ["semua"]], on="id_gold", suffixes=("", "_2"))
        for k in list(FIELDS) + ["semua"]:
            kp, n = kappa(J[k], J[f"{k}_2"])
            m = J[k].notna() & J[f"{k}_2"].notna()
            out.append(f"| {k} | {kp:.2f} | {(J[k][m] == J[f'{k}_2'][m]).mean():.0%} | {n} |\n")
        JR = R.merge(R2[["id_gold", "lengkap"]], on="id_gold", suffixes=("", "_2"))
        kp, n = kappa(JR.lengkap, JR.lengkap_2)
        out.append(f"| cakupan: lengkap | {kp:.2f} | - | {n} |\n")
    txt = "".join(out)
    dst = os.path.join(G, "hasil_" + os.path.splitext(os.path.basename(path))[0] + ".md")
    open(dst, "w", encoding="utf-8").write(txt)
    print(txt)
    print("->", dst)


if __name__ == "__main__":
    main(*sys.argv[1:3])
