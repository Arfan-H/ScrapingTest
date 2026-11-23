"""Hitung skor gold set ekstraksi v3 dari file penilaian yang sudah diisi.

Pemakaian: python -I pilot/eval/nilai_gold_ekstraksi.py <gold_ekstraksi_v3_terisi.xlsx> [gold_ekstraksi_v3_penilai2_terisi.xlsx]

Estimasi (ditetapkan sebelum penilaian):
- Unit sampling = dokumen (peluang sama di dalam strata).
- PRESISI: bobot butir = n_d / m_d (n_d = baris data dokumen, m_d = butir dokumen itu yang dinilai pada kolom tsb.);
  akurasi strata = sum(w*y)/sum(w). Bobot strata UTAMA = baris dokumen eligible (estimasi berlaku untuk dokumen yang
  tidak tersentuh saat pengembangan); SENSITIVITAS = baris seluruh dataset (generalisasi ke 505 dokumen).
- CAKUPAN: bobot butir = H_d/k_d x L_p (kebalikan peluang inklusi baris kandidat; H = halaman berkandidat, k = halaman
  diambil, L_p = baris kandidat di halaman). Hanya butir yang dinilai 'memuat tarif'. Bobot strata = (dokumen populasi /
  dokumen sampel) x jumlah baris kandidat dokumen sampel.
- Titik estimasi gabungan = sum_h W_h x estimasi_h atas strata ASLI. CI 95% = bootstrap persentil (2000 ulangan),
  dokumen diambil ulang dalam strata. Strata dengan < 3 dokumen pada bagian yang dihitung ditandai 'tidak andal';
  variabilitasnya dipinjam dari gabungan dokumen bersumber teks sama (titik estimasinya tetap dari strata sendiri).
- 'Tidak bisa dinilai'/kosong dikeluarkan per kolom. Butir kontrol tidak ikut akurasi.
- Angka utama = bagian 'test'. 'semua' (dev+test) sah hanya bila parser tidak diubah setelah penilaian.
- Kesepakatan: % sama, kappa Cohen, Gwet AC1 (kappa bisa rendah meski % sama tinggi bila hampir semua 'Ya').
- Ketelitian penilai: porsi butir kontrol yang kolom ubahannya dinilai 'Tidak'. Penilai pertama sudah tahu struktur
  butir kontrol v2 (bukan v3), jadi angka penilai kedua lebih bersih.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
G = os.path.join(HERE, "gold")
VER = "v3"
B = 2000
FIELDS = {"nama": "NAMA benar?", "kelas": "KELAS benar?", "varian_komponen": "VARIAN/KOMPONEN benar?",
          "harga": "HARGA benar?"}
CTRL_COL = {"nama_asli": "nama", "kelas": "kelas", "harga": "harga"}
C1, C2 = "Baris ini memuat TARIF layanan?", "Semua harga di baris ini ada di data dengan benar?"


def yn(s):
    v = s.astype(str).str.strip().str.lower()
    return pd.Series(np.where(v == "ya", 1.0, np.where(v == "tidak", 0.0, np.nan)), index=s.index)


def read(path):
    """Gabungkan isian dengan manifest. Mengembalikan (presisi+kontrol, cakupan, kolom id yang cocok)."""
    M = pd.read_csv(os.path.join(G, f"gold_ekstraksi_{VER}_manifest.csv"), keep_default_na=False)
    RM = pd.read_csv(os.path.join(G, f"gold_ekstraksi_{VER}_cakupan_manifest.csv"), keep_default_na=False)
    P = pd.read_excel(path, sheet_name="nilai_baris", dtype=str)
    R = pd.read_excel(path, sheet_name="cek_baris_pdf", dtype=str)
    idc = "id_p1" if P["id"].isin(M.id_p1).mean() > 0.9 else "id_p2"
    P = M.merge(P[["id"] + list(FIELDS.values())], left_on=idc, right_on="id", how="inner")
    for k, c in FIELDS.items():
        P[k] = yn(P[c])
    ok = P[list(FIELDS)]
    P["semua"] = np.where(ok.isna().any(axis=1), np.nan, ok.min(axis=1))
    R = RM.merge(R[["id", C1, C2]], left_on=idc, right_on="id", how="inner")
    R["tarif"] = R[C1].astype(str).str.strip().str.lower()
    v = R[C2].astype(str).str.strip().str.lower()
    R["lengkap"] = np.where(v == "ya semua", 1.0, np.where(v.isin(["sebagian", "tidak ada"]), 0.0, np.nan))
    R["hilang"] = np.where(v == "tidak ada", 1.0, np.where(v.isin(["sebagian", "ya semua"]), 0.0, np.nan))
    R.loc[R.tarif != "ya", ["lengkap", "hilang"]] = np.nan
    return P, R, idc


def combine(items, W):
    """items: strata, dokumen_id, y, w. W: bobot strata (Series). -> (gabungan, estimasi per strata)."""
    est = items.assign(wy=items.w * items.y).groupby("strata")[["wy", "w"]].sum()
    est = est.wy / est.w
    w = W.reindex(est.index).fillna(0)
    return (float(np.sum(est * w) / w.sum()) if w.sum() else np.nan), est


def estimate(items, W_fn, rng):
    """items sudah difilter (y tidak NaN) dan punya kolom w. W_fn(items) -> bobot strata.
    Bootstrap: dokumen diambil ulang di dalam strata; strata < 3 dokumen meminjam variabilitas dari gabungan dokumen
    bersumber teks sama (titik estimasinya tetap dari strata sendiri)."""
    if items.empty:
        return dict(est=np.nan, lo=np.nan, hi=np.nan, n=0, ndoc=0, lemah="")
    W = W_fn(items)
    point, est_s = combine(items, W)
    doc = items.assign(wy=items.w * items.y).groupby(["strata", "dokumen_id"])[["wy", "w"]].sum().reset_index()
    weak = [s for s in est_s.index if (doc.strata == s).sum() < 3]
    reps = {}
    for s in est_s.index:
        if s in weak:
            src = s.split("/")[0]
            pool = doc[doc.strata.str.startswith(src + "/")]
            if len(pool) < 3:
                pool = doc
            base = pool.wy.sum() / pool.w.sum()
            shift = est_s[s] - base
        else:
            pool, shift = doc[doc.strata == s], 0.0
        wy, ww = pool.wy.to_numpy(), pool.w.to_numpy()
        idx = rng.integers(0, len(pool), size=(B, len(pool)))
        reps[s] = wy[idx].sum(1) / ww[idx].sum(1) + shift
    w = W.reindex(est_s.index).fillna(0).to_numpy()
    mat = np.column_stack([reps[s] for s in est_s.index])
    boots = (mat * w).sum(1) / w.sum()
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return dict(est=point, lo=lo, hi=hi, n=len(items), ndoc=items.dokumen_id.nunique(), lemah=", ".join(weak))


def prec_items(P, col):
    d = P[(P.jenis == "presisi") & P[col].notna()].copy()
    d["y"] = d[col]
    d["w"] = d.n_baris_dok / d.groupby("dokumen_id").y.transform("size")
    return d


def rec_items(R, col):
    d = R[R[col].notna()].copy()
    d["y"] = d[col]
    d["w"] = d.H_halaman_berkandidat / d.k_halaman_diambil * d.L_kandidat_halaman
    return d


def agree(a, b):
    m = a.notna() & b.notna()
    a, b = a[m], b[m]
    if len(a) == 0:
        return np.nan, np.nan, np.nan, 0
    po = float((a == b).mean())
    cats = sorted(set(a) | set(b))
    pe_k = sum((a == c).mean() * (b == c).mean() for c in cats)
    kappa = (po - pe_k) / (1 - pe_k) if pe_k < 1 else np.nan
    pi = {c: ((a == c).mean() + (b == c).mean()) / 2 for c in cats}
    Q = max(len(cats), 2)
    pe_g = sum(p * (1 - p) for p in pi.values()) / (Q - 1)
    ac1 = (po - pe_g) / (1 - pe_g) if pe_g < 1 else np.nan
    return po, kappa, ac1, len(a)


def sensitivity(P):
    C = P[P.jenis == "kontrol"].copy()
    if C.empty:
        return "tidak ada butir kontrol di file ini"
    C["t"] = [1 - r[CTRL_COL[r.kolom_diubah]] if pd.notna(r[CTRL_COL[r.kolom_diubah]]) else np.nan for _, r in C.iterrows()]
    n = C.t.notna().sum()
    return (f"{int(C.t.sum())} dari {n} nilai yang sengaja diubah ditandai 'Tidak' ({C.t.mean():.0%}); per kolom: " +
            "; ".join(f"{k}: {g.t.mean():.0%} (n={g.t.notna().sum()})" for k, g in C.groupby("kolom_diubah")))


def pct(e):
    return f"{e['est']:.1%} | {e['lo']:.1%}-{e['hi']:.1%}"


def main(path, path2=None):
    rng = np.random.default_rng(7)
    S = pd.read_csv(os.path.join(G, f"gold_ekstraksi_{VER}_strata.csv")).set_index("strata")
    P, R, idc = read(path)
    out = [f"# Hasil gold set ekstraksi {VER}\n\nFile: `{os.path.basename(path)}` (penilai {1 if idc == 'id_p1' else 2})\n\n"]
    pres = P[P.jenis == "presisi"]
    out.append(f"Butir presisi terisi: {pres[list(FIELDS)].notna().any(axis=1).mean():.0%} dari {len(pres)}; "
               f"cakupan terisi: {R.tarif.isin(['ya', 'tidak']).mean():.0%} dari {len(R)}.\n\n")
    parts = {"test": lambda d: d[d.split == "test"], "dev": lambda d: d[d.split == "dev"], "semua": lambda d: d}

    for wname, wcol, dcol in [("UTAMA: dokumen eligible", "baris_eligible", "dok_eligible"),
                              ("sensitivitas: seluruh dataset", "baris_semua", "dok_semua")]:
        Wp = S[wcol].astype(float)
        out.append(f"## Presisi ({wname})\n\n| ukuran | bagian | estimasi | CI 95% | n butir | n dok | strata < 3 dok |\n|---|---|---|---|---|---|---|\n")
        for k in list(FIELDS) + ["semua"]:
            for pn, pf in parts.items():
                e = estimate(prec_items(pf(P), k), lambda it: Wp, rng)
                out.append(f"| {k} | {pn} | {pct(e)} | {e['n']} | {e['ndoc']} | {e['lemah']} |\n")

        def Wr(it, dcol=dcol):
            nd = it.groupby("strata").dokumen_id.nunique()
            Nk = it.drop_duplicates("dokumen_id").groupby("strata").N_kandidat_dokumen.sum()
            return S[dcol].reindex(nd.index).astype(float) / nd * Nk
        out.append(f"\n## Cakupan, baris PDF -> data ({wname})\n\n| ukuran | bagian | estimasi | CI 95% | n butir | n dok | strata < 3 dok |\n|---|---|---|---|---|---|---|\n")
        for k in ["lengkap", "hilang"]:
            for pn, pf in parts.items():
                e = estimate(rec_items(pf(R), k), Wr, rng)
                out.append(f"| {k} | {pn} | {pct(e)} | {e['n']} | {e['ndoc']} | {e['lemah']} |\n")
        out.append("\n")
    out.append(f"Baris PDF yang dinilai bukan tarif: {(R.tarif == 'tidak').sum()} dari {R.tarif.isin(['ya', 'tidak']).sum()}. "
               "Batasan cakupan: harga < 1.000 tidak pernah jadi kandidat; halaman tarif di luar rentang halaman yang punya "
               "data tidak terjangkau.\n\n")

    out.append("## Per strata (tanpa bobot antar-strata; 'semua kolom benar')\n\n| strata | bagian | n dok | n butir | presisi | cakupan lengkap |\n|---|---|---|---|---|---|\n")
    for pn in ["test", "semua"]:
        pp, rr = parts[pn](prec_items(P, "semua")), parts[pn](rec_items(R, "lengkap"))
        for s in sorted(set(pp.strata) | set(rr.strata)):
            a, b = pp[pp.strata == s], rr[rr.strata == s]
            nd = a.dokumen_id.nunique()
            pa = f"{np.sum(a.w * a.y) / np.sum(a.w):.1%}" if len(a) else "-"
            pb = f"{np.sum(b.w * b.y) / np.sum(b.w):.1%}" if len(b) else "-"
            out.append(f"| {s} | {pn} | {nd}{' (tidak andal)' if nd < 3 else ''} | {len(a)} | {pa} | {pb} |\n")

    out.append(f"\n## Ketelitian penilai (butir kontrol)\n\nPenilai {1 if idc == 'id_p1' else 2}: {sensitivity(P)}.\n")
    if path2:
        P2, R2, idc2 = read(path2)
        out.append(f"Penilai {1 if idc2 == 'id_p1' else 2} (`{os.path.basename(path2)}`): {sensitivity(P2)}.\n")
        out.append("\n## Kesepakatan antar-penilai (butir presisi yang dinilai keduanya)\n\n| kolom | % sama | kappa Cohen | Gwet AC1 | n |\n|---|---|---|---|---|\n")
        J = P[P.jenis == "presisi"].merge(P2[["tarif_id"] + list(FIELDS) + ["semua"]], on="tarif_id", suffixes=("", "_2"))
        for k in list(FIELDS) + ["semua"]:
            po, ka, ac, n = agree(J[k], J[f"{k}_2"])
            out.append(f"| {k} | {po:.0%} | {ka:.2f} | {ac:.2f} | {n} |\n")
        JR = R.merge(R2[["id_p1", "tarif", "lengkap"]], on="id_p1", suffixes=("", "_2"))
        for k in ["tarif", "lengkap"]:
            a = JR[k].replace({"ya": 1.0, "tidak": 0.0}) if k == "tarif" else JR[k]
            b = JR[f"{k}_2"].replace({"ya": 1.0, "tidak": 0.0}) if k == "tarif" else JR[f"{k}_2"]
            a, b = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
            po, ka, ac, n = agree(a, b)
            out.append(f"| cakupan: {k} | {po:.0%} | {ka:.2f} | {ac:.2f} | {n} |\n")
    txt = "".join(out)
    dst = os.path.join(G, "hasil_" + os.path.splitext(os.path.basename(path))[0] + ".md")
    open(dst, "w", encoding="utf-8").write(txt)
    print(txt)
    print("->", dst)


if __name__ == "__main__":
    main(*sys.argv[1:3])
