"""Hitung skor gold set ekstraksi v3 dari file penilaian yang sudah diisi.

Pemakaian: python -I pilot/eval/nilai_gold_ekstraksi.py <gold_ekstraksi_v3_terisi.xlsx> [gold_ekstraksi_v3_penilai2_terisi.xlsx]

Aturan yang DIKUNCI sebelum penilaian (pra-registrasi, tag git gold-v3-prereg; lihat
pilot/eval/gold/PRAREGISTRASI_gold_v3.md):
- Parser dibekukan (cb968f4); dev dan test DIGABUNG (60 dokumen). Kolom 'split' tidak dipakai.
- ANGKA UTAMA = akurasi MAKRO per dokumen: p_d = proporsi benar butir dokumen d; estimasi strata = rata-rata p_d;
  gabungan = sum_h W_h x estimasi_h dengan W_h = porsi dokumen ELIGIBLE (populasi: dokumen yang tidak tersentuh saat
  pengembangan). CI 95% = bootstrap persentil (2000 ulangan), dokumen diambil ulang di dalam strata (inferensi ke
  dokumen peraturan baru). Strata < 3 dokumen ber-isian ditandai tidak andal; variabilitasnya dipinjam dari gabungan
  dokumen bersumber teks sama (titik estimasi tetap dari strata sendiri).
- Hasil PER STRATA dilaporkan sejajar dengan angka gabungan (teks_pdf/satu_harga = ~68% populasi, 15 dok sampel).
- Pendamping: (a) sensus + FPC (klaim 'dataset ini': strata yang semua dokumennya terambil hanya memakai variasi butir
  di dalam dokumen; strata lain dikalikan sqrt(1-f)); (b) berbobot baris (bobot butir n_d/m_d, W_h = baris eligible);
  (c) makro dengan bobot seluruh dataset (W_h = semua dokumen).
- 'Tidak bisa dinilai' dan isian kosong dikeluarkan PER KOLOM; jumlahnya dilaporkan per kolom; skenario terburuk
  (tidak bisa dinilai = salah) dilaporkan sebagai sensitivitas.
- 'Semua kolom benar': SALAH bila ada >= 1 kolom 'Tidak'; BENAR bila keempat kolom 'Ya'; DIKELUARKAN hanya bila tidak
  ada 'Tidak' tetapi ada kolom yang tidak dinilai.
- Cakupan (baris PDF -> data): hanya butir yang dinilai 'memuat tarif'. Makro: p_d = sum(L_p*y)/sum(L_p) di dalam
  dokumen (H/k konstan per dokumen), lalu seperti presisi. Pendamping: bobot butir H/k x L_p dengan W_h = (dokumen
  populasi / dokumen sampel) x jumlah baris kandidat dokumen sampel. Cakupan = recall di dalam rentang halaman
  ber-data untuk harga >= 1.000, bukan recall seluruh dokumen.
- Butir kontrol tidak ikut akurasi. Ketelitian penilai = porsi butir kontrol yang kolom ubahannya dinilai 'Tidak',
  dengan CI Wilson, per penilai dan per kolom. Penilai pertama tidak buta terhadap desain kontrol.
- Kesepakatan: hanya butir presisi yang dinilai kedua penilai; % sama, kappa Cohen, Gwet AC1.
- Paparan: 30 dari 60 dokumen v3 pernah muncul di file v1/v2; 11 butir nilai_baris barisnya sama persis dengan butir
  v1/v2 (gold/v3_butir_sama_v1_v2.csv). Sensitivitas: hasil tanpa 11 butir itu.
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
TBD = "tidak bisa dinilai"


def low(s):
    return s.fillna("").astype(str).str.strip().str.lower()


def read(path):
    """Gabungkan isian dengan manifest. -> (presisi+kontrol, cakupan, kolom id yang cocok)."""
    M = pd.read_csv(os.path.join(G, f"gold_ekstraksi_{VER}_manifest.csv"), keep_default_na=False)
    RM = pd.read_csv(os.path.join(G, f"gold_ekstraksi_{VER}_cakupan_manifest.csv"), keep_default_na=False)
    P = pd.read_excel(path, sheet_name="nilai_baris", dtype=str)
    R = pd.read_excel(path, sheet_name="cek_baris_pdf", dtype=str)
    idc = "id_p1" if P["id"].isin(M.id_p1).mean() > 0.9 else "id_p2"
    P = M.merge(P[["id"] + list(FIELDS.values())], left_on=idc, right_on="id", how="inner")
    for k, c in FIELDS.items():
        v = low(P[c])
        P[k] = np.where(v == "ya", 1.0, np.where(v == "tidak", 0.0, np.nan))
        P[k + "_tbd"] = v == TBD
        P[k + "_terburuk"] = np.where(v == "ya", 1.0, np.where(v.isin(["tidak", TBD]), 0.0, np.nan))
    for suf in ["", "_terburuk"]:
        ok = P[[k + suf for k in FIELDS]]
        P["semua" + suf] = np.where((ok == 0).any(axis=1), 0.0, np.where((ok == 1).all(axis=1), 1.0, np.nan))
    R = RM.merge(R[["id", C1, C2]], left_on=idc, right_on="id", how="inner")
    R["tarif"] = low(R[C1])
    v = low(R[C2])
    R["lengkap"] = np.where(v == "ya semua", 1.0, np.where(v.isin(["sebagian", "tidak ada"]), 0.0, np.nan))
    R["hilang"] = np.where(v == "tidak ada", 1.0, np.where(v.isin(["sebagian", "ya semua"]), 0.0, np.nan))
    R["lengkap_terburuk"] = np.where(v == "ya semua", 1.0, np.where(v.isin(["sebagian", "tidak ada", TBD]), 0.0, np.nan))
    R["hilang_terburuk"] = np.where(v.isin(["tidak ada", TBD]), 1.0, np.where(v.isin(["sebagian", "ya semua"]), 0.0, np.nan))
    R["cakupan_tbd"] = (R.tarif == "ya") & (v == TBD)
    for c in ["lengkap", "hilang", "lengkap_terburuk", "hilang_terburuk"]:
        R.loc[R.tarif != "ya", c] = np.nan
    return P, R, idc


# ---- butir -> (strata, dokumen_id, y, w) ----
def prec_items(P, col, makro=True):
    d = P[(P.jenis == "presisi") & P[col].notna()].copy()
    d["y"] = d[col]
    m = d.groupby("dokumen_id").y.transform("size")
    d["w"] = 1.0 / m if makro else d.n_baris_dok / m
    return d


def rec_items(R, col, makro=True):
    d = R[R[col].notna()].copy()
    d["y"] = d[col]
    if makro:
        d["w"] = d.L_kandidat_halaman / d.groupby("dokumen_id").L_kandidat_halaman.transform("sum")
    else:
        d["w"] = d.H_halaman_berkandidat / d.k_halaman_diambil * d.L_kandidat_halaman
    return d


def estimate(items, W, rng, N_pop=None):
    """Titik estimasi tertimbang strata + CI bootstrap. N_pop (Series dokumen populasi per strata) -> versi sensus+FPC."""
    if items.empty:
        return dict(est=np.nan, lo=np.nan, hi=np.nan, n=0, ndoc=0, lemah="", per={})
    items = items.assign(wy=items.w * items.y)
    doc = items.groupby(["strata", "dokumen_id"])[["wy", "w"]].sum().reset_index()
    est_s = doc.groupby("strata").wy.sum() / doc.groupby("strata").w.sum()
    Wn = W.reindex(est_s.index).fillna(0)
    point = float(np.sum(est_s * Wn) / Wn.sum())
    weak = [] if N_pop is not None else [s for s in est_s.index if (doc.strata == s).sum() < 3]
    reps = {}
    for s in est_s.index:
        g = doc[doc.strata == s]
        f = len(g) / float(N_pop[s]) if N_pop is not None and N_pop.get(s, 0) else 0.0
        if N_pop is not None and f >= 1:   # sensus: ambil ulang butir di dalam tiap dokumen
            num, den = np.zeros(B), np.zeros(B)
            for _, it in items[items.strata == s].groupby("dokumen_id"):
                ii = rng.integers(0, len(it), (B, len(it)))
                wy, ww = it.wy.to_numpy()[ii].sum(1), it.w.to_numpy()[ii].sum(1)
                num += wy / ww * it.w.sum()
                den += it.w.sum()
            reps[s] = num / den
            continue
        if s in weak:
            pool = doc[doc.strata.str.startswith(s.split("/")[0] + "/")]
            if len(pool) < 3:
                pool = doc
            shift = est_s[s] - pool.wy.sum() / pool.w.sum()
        else:
            pool, shift = g, 0.0
        ii = rng.integers(0, len(pool), (B, len(pool)))
        r = pool.wy.to_numpy()[ii].sum(1) / pool.w.to_numpy()[ii].sum(1) + shift
        if N_pop is not None:
            r = est_s[s] + np.sqrt(1 - f) * (r - est_s[s])
        reps[s] = r
    mat = np.column_stack([reps[s] for s in est_s.index])
    boots = (mat * Wn.to_numpy()).sum(1) / Wn.sum()
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    per = {s: (est_s[s], *np.nanpercentile(reps[s], [2.5, 97.5]), int((doc.strata == s).sum())) for s in est_s.index}
    return dict(est=point, lo=lo, hi=hi, n=len(items), ndoc=items.dokumen_id.nunique(), lemah=", ".join(weak), per=per)


def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


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
    pe_g = sum(p * (1 - p) for p in pi.values()) / (max(len(cats), 2) - 1)
    ac1 = (po - pe_g) / (1 - pe_g) if pe_g < 1 else np.nan
    return po, kappa, ac1, len(a)


def sensitivity(P):
    C = P[P.jenis == "kontrol"].copy()
    if C.empty:
        return "tidak ada butir kontrol di file ini"
    C["t"] = [1 - r[CTRL_COL[r.kolom_diubah]] if pd.notna(r[CTRL_COL[r.kolom_diubah]]) else np.nan for _, r in C.iterrows()]
    parts = []
    for k, g in [("semua kolom", C)] + list(C.groupby("kolom_diubah")):
        n, x = int(g.t.notna().sum()), int(g.t.sum())
        lo, hi = wilson(x, n)
        parts.append(f"{k}: {x}/{n} ({x / n:.0%}, CI Wilson 95% {lo:.0%}-{hi:.0%})" if n else f"{k}: 0/0")
    return "; ".join(parts)


def pct(e):
    return f"{e['est']:.1%} | {e['lo']:.1%}-{e['hi']:.1%}"


def pct1(e):
    return f"{e['est']:.1%} ({e['lo']:.1%}-{e['hi']:.1%})"


def main(path, path2=None):
    rng = np.random.default_rng(7)
    S = pd.read_csv(os.path.join(G, f"gold_ekstraksi_{VER}_strata.csv")).set_index("strata")
    Wd, Wd_all, Wr_rows = S.dok_eligible.astype(float), S.dok_semua.astype(float), S.baris_eligible.astype(float)
    P, R, idc = read(path)
    pres = P[P.jenis == "presisi"]
    out = [f"# Hasil gold set ekstraksi {VER}\n\nFile: `{os.path.basename(path)}` (penilai {1 if idc == 'id_p1' else 2}). "
           "Aturan dan estimator dikunci di tag `gold-v3-prereg` (lihat docstring skrip ini).\n\n"]
    out.append("## Isian\n\n| kolom | Ya | Tidak | Tidak bisa dinilai | kosong |\n|---|---|---|---|---|\n")
    for k, c in FIELDS.items():
        v = low(pres[c])
        out.append(f"| {k} | {(v == 'ya').sum()} | {(v == 'tidak').sum()} | {(v == TBD).sum()} | {(v == '').sum()} |\n")
    v = low(R[C2])
    out.append(f"| cakupan (baris tarif) | {(v[R.tarif == 'ya'] == 'ya semua').sum()} | "
               f"{v[R.tarif == 'ya'].isin(['sebagian', 'tidak ada']).sum()} | {int(R.cakupan_tbd.sum())} | "
               f"{(R.tarif == '').sum()} (kolom 'memuat tarif' kosong) |\n")
    out.append(f"\nBaris PDF yang dinilai bukan tarif: {(R.tarif == 'tidak').sum()} dari {R.tarif.isin(['ya', 'tidak']).sum()}.\n\n")

    out.append("## HASIL UTAMA: akurasi makro per dokumen (60 dokumen, dev+test digabung; bobot dokumen eligible)\n\n"
               "Terburuk = butir 'Tidak bisa dinilai' dihitung salah (sensitivitas).\n\n"
               "| ukuran | estimasi | CI 95% | n butir | n dok | terburuk: estimasi | terburuk: CI 95% | strata < 3 dok |\n|---|---|---|---|---|---|---|---|\n")
    main_res = {}
    for k in list(FIELDS) + ["semua"]:
        e = estimate(prec_items(P, k), Wd, rng)
        w = estimate(prec_items(P, k + "_terburuk"), Wd, rng)
        main_res[k] = e
        out.append(f"| presisi: {k} | {pct(e)} | {e['n']} | {e['ndoc']} | {pct(w)} | {e['lemah']} |\n")
    for k in ["lengkap", "hilang"]:
        e = estimate(rec_items(R, k), Wd, rng)
        w = estimate(rec_items(R, k + "_terburuk"), Wd, rng)
        main_res["cakupan_" + k] = e
        out.append(f"| cakupan: {k} | {pct(e)} | {e['n']} | {e['ndoc']} | {pct(w)} | {e['lemah']} |\n")
    out.append("\nCakupan = recall di dalam rentang halaman yang punya data, untuk harga >= 1.000. CI bootstrap dengan sedikit "
               "dokumen efektif (Kish lintas strata ~30) cenderung terlalu sempit (simulasi: cakupan CI 86-92%); sajikan "
               "sebagai perkiraan kasar.\n\n")

    out.append("## HASIL INTI per strata (makro; CI bootstrap dokumen di dalam strata)\n\n"
               "| strata | dok sampel / populasi eligible | presisi 'semua kolom' | CI 95% | cakupan lengkap | CI 95% | catatan |\n|---|---|---|---|---|---|---|\n")
    ps, rs = main_res["semua"]["per"], main_res["cakupan_lengkap"]["per"]
    for s in S.index:
        if s not in ps and s not in rs:
            continue
        a, b = ps.get(s), rs.get(s)
        nd, ndr = (a[3] if a else 0), (b[3] if b else 0)
        note = "; ".join(x for x in [f"presisi tidak andal ({nd} dok)" if a and nd < 3 else "",
                                     f"cakupan tidak andal ({ndr} dok ber-isian)" if b and ndr < 3 else ""] if x)
        if note:
            note += "; CI dipinjam dari strata bersumber sama"
        if int(S.dok_sampel[s]) >= int(S.dok_eligible[s]):
            note = (note + "; " if note else "") + "semua dokumen eligible terambil (sensus)"
        fa = (f"{a[0]:.1%}", f"{a[1]:.1%}-{a[2]:.1%}") if a else ("-", "-")
        fb = (f"{b[0]:.1%}", f"{b[1]:.1%}-{b[2]:.1%}") if b else ("-", "-")
        out.append(f"| {s} | {int(S.dok_sampel[s])} / {int(S.dok_eligible[s])} | {fa[0]} | {fa[1]} | {fb[0]} | {fb[1]} | {note} |\n")

    out.append("\n## Pendamping\n\n| ukuran | (a) sensus + FPC: dataset ini | (b) berbobot baris | (c) makro, bobot seluruh dataset |\n|---|---|---|---|\n")
    for k in list(FIELDS) + ["semua"]:
        a = estimate(prec_items(P, k), Wd, rng, N_pop=S.dok_eligible)
        b = estimate(prec_items(P, k, makro=False), Wr_rows, rng)
        c = estimate(prec_items(P, k), Wd_all, rng)
        out.append(f"| presisi: {k} | {pct1(a)} | {pct1(b)} | {pct1(c)} |\n")

    def Wr_lines(it):
        nd = it.groupby("strata").dokumen_id.nunique()
        Nk = it.drop_duplicates("dokumen_id").groupby("strata").N_kandidat_dokumen.sum()
        return S.dok_eligible.reindex(nd.index).astype(float) / nd * Nk
    for k in ["lengkap", "hilang"]:
        a = estimate(rec_items(R, k), Wd, rng, N_pop=S.dok_eligible)
        it = rec_items(R, k, makro=False)
        b = estimate(it, Wr_lines(it), rng)
        c = estimate(rec_items(R, k), Wd_all, rng)
        out.append(f"| cakupan: {k} | {pct1(a)} | {pct1(b)} (bobot baris kandidat PDF) | {pct1(c)} |\n")

    same = pd.read_csv(os.path.join(G, "v3_butir_sama_v1_v2.csv")).tarif_id
    e0 = estimate(prec_items(P, "semua"), Wd, rng)
    e1 = estimate(prec_items(P[~P.tarif_id.isin(same)], "semua"), Wd, rng)
    out.append(f"\nSensitivitas paparan: presisi 'semua kolom' (makro) dengan semua butir {pct1(e0)}; tanpa "
               f"{int(P.tarif_id.isin(same).sum())} butir yang barisnya sama dengan butir v1/v2 {pct1(e1)}. "
               "30 dari 60 dokumen v3 pernah muncul di file v1/v2 (gold/v3_tumpang_tindih_v1_v2.csv).\n")
    out.append(f"\n## Ketelitian penilai (butir kontrol)\n\nPenilai {1 if idc == 'id_p1' else 2}: {sensitivity(P)}.\n")
    if idc == "id_p1":
        out.append("Penilai pertama tidak buta terhadap desain butir kontrol; angka ini bukan satu-satunya bukti ketelitian.\n")
    if path2:
        P2, R2, idc2 = read(path2)
        out.append(f"\nPenilai {1 if idc2 == 'id_p1' else 2} (`{os.path.basename(path2)}`; porsi kontrol di file ini lebih "
                   f"tinggi, ~22% vs ~9%, jadi tidak setara langsung): {sensitivity(P2)}.\n")
        out.append("\n## Kesepakatan antar-penilai (butir presisi yang dinilai keduanya)\n\n| kolom | % sama | kappa Cohen | Gwet AC1 | n |\n|---|---|---|---|---|\n")
        J = P[P.jenis == "presisi"].merge(P2[P2.jenis == "presisi"][["tarif_id"] + list(FIELDS) + ["semua"]],
                                          on="tarif_id", suffixes=("", "_2"))
        for k in list(FIELDS) + ["semua"]:
            po, ka, ac, n = agree(J[k], J[f"{k}_2"])
            out.append(f"| {k} | {po:.0%} | {ka:.2f} | {ac:.2f} | {n} |\n")
        JR = R.merge(R2[["id_p1", "tarif", "lengkap"]], on="id_p1", suffixes=("", "_2"))
        for k in ["tarif", "lengkap"]:
            a = pd.to_numeric(JR[k].replace({"ya": 1.0, "tidak": 0.0}) if k == "tarif" else JR[k], errors="coerce")
            b = pd.to_numeric(JR[f"{k}_2"].replace({"ya": 1.0, "tidak": 0.0}) if k == "tarif" else JR[f"{k}_2"], errors="coerce")
            po, ka, ac, n = agree(a, b)
            out.append(f"| cakupan: {k} | {po:.0%} | {ka:.2f} | {ac:.2f} | {n} |\n")

    out.append("\n## Lampiran: akurasi per dokumen\n\n| dokumen_id | strata | butir presisi dinilai | presisi 'semua kolom' | butir cakupan (tarif) | cakupan lengkap |\n|---|---|---|---|---|---|\n")
    a = prec_items(P, "semua")
    a = a.groupby(["dokumen_id", "strata"]).agg(n=("y", "size"), p=("y", "mean"))
    b = rec_items(R, "lengkap")
    b = b.assign(wy=b.w * b.y).groupby("dokumen_id").agg(n=("y", "size"), wy=("wy", "sum"), w=("w", "sum"))
    for (d, s), r in a.iterrows():
        rb = b.loc[d] if d in b.index else None
        out.append(f"| {d} | {s} | {int(r.n)} | {r.p:.0%} | {int(rb.n) if rb is not None else 0} | "
                   f"{(rb.wy / rb.w):.0%} |\n" if rb is not None else f"| {d} | {s} | {int(r.n)} | {r.p:.0%} | 0 | - |\n")
    txt = "".join(out)
    dst = os.path.join(G, "hasil_" + os.path.splitext(os.path.basename(path))[0] + ".md")
    open(dst, "w", encoding="utf-8").write(txt)
    print(txt)
    print("->", dst)


if __name__ == "__main__":
    main(*sys.argv[1:3])
