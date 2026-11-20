"""Usulan kode standar untuk semua nama layanan unik di dataset BPK (pilot/out/dataset/tarif.csv.gz).

Metode sama dengan suggest_codes.py (pilot): kategori standar menentukan sistem kode
  Laboratorium -> LOINC (Universal Lab Orders, 1.519 tes)
  Radiologi, Tindakan Lain, Gigi, Kebidanan, Mata/THT/Kulit, Rehab Medik -> ICD-9-CM Vol. 3 (3.882 prosedur)
  Akomodasi & Visite, Rawat Jalan & Darurat -> Lokal (tanpa kode standar)
skor = 0,7 x cosine multilingual-e5-small + 0,3 x cosine TF-IDF karakter, atas nama + terjemahan istilah (kamus v2).
Hasilnya USULAN; kolom kode diisi manusia (PMIK).

Keluaran (pilot/out/dataset/):
  pemetaan_kode.csv.gz     : satu baris per nama_norm (n_rs, n_baris, contoh nama, usulan top-1, top-5, skor)
  sampel_validasi_pmik.xlsx: sampel bertingkat untuk divalidasi PMIK (nama sering + acak), kolom isian kosong

Pemakaian: E5_DIR=<folder model> python -I pilot/src/petakan_kode_bpk.py [<folder cache embedding>]
"""
import os
import re
import sys

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, os.path.dirname(__file__))
from align import e5_embed  # noqa: E402
from medterm_id_en import translate_v2  # noqa: E402
from suggest_codes import TARGET, load_targets  # noqa: E402

BASE = os.path.join(os.path.dirname(__file__), "..")
DS = os.path.join(BASE, "out", "dataset")


MODALITY = r"x-?ray|foto|photo|rontgen|r[oö]ntgen|usg|ultrasono|ct\b|ct scan|mri|mammo|fluoro|scan|echo|doppler|grafi|graphy"


def build_query(nama, kategori):
    q = f"{nama} {translate_v2(nama)}"
    # radiologi tanpa modalitas tertulis ("cranium ap / lateral") hampir selalu foto polos
    if kategori == "Radiologi" and not re.search(MODALITY, nama, re.I):
        q = f"x-ray {q}"
    return q


def embed_store(texts, cache):
    """Embedding per teks unik; disimpan di <cache>/store.npz agar run berikutnya hanya menghitung teks baru."""
    f = os.path.join(cache, "store.npz")
    have = {}
    if os.path.exists(f):
        z = np.load(f, allow_pickle=True)
        have = dict(zip(z["texts"].tolist(), z["vecs"]))
    todo = [t for t in dict.fromkeys(texts) if t not in have]
    for i in range(0, len(todo), 5000):
        V = e5_embed(todo[i:i + 5000], batch=128).astype(np.float32)
        have.update(zip(todo[i:i + 5000], V))
        print(f"  embedding baru: {min(i + 5000, len(todo)):,}/{len(todo):,}", flush=True)
        np.savez(f, texts=np.array(list(have), dtype=object), vecs=np.vstack(list(have.values())))
    return np.vstack([have[t] for t in texts])


def embed_cached(texts, cache, tag, chunk=5000):
    """Embedding per potongan, disimpan di cache supaya bisa dilanjutkan bila proses terputus."""
    os.makedirs(cache, exist_ok=True)
    parts = []
    for i in range(0, len(texts), chunk):
        f = os.path.join(cache, f"{tag}_{i:07d}_{len(texts)}.npy")
        if not os.path.exists(f):
            np.save(f, e5_embed(texts[i:i + chunk], batch=128).astype(np.float32))
            print(f"  {tag}: {min(i + chunk, len(texts)):,}/{len(texts):,}", flush=True)
        parts.append(np.load(f))
    return np.vstack(parts)


def main(cache):
    T = pd.read_csv(os.path.join(DS, "tarif.csv.gz"), low_memory=False,
                    usecols=["nama_norm", "nama_asli", "kategori_std", "rs_id", "dokumen_id", "qc_masalah"])
    T = T[T.nama_norm.notna() & (T.nama_norm.str.replace(r"[^a-z]", "", regex=True).str.len() >= 3)]
    P = T.groupby("nama_norm").agg(
        kategori_std=("kategori_std", lambda s: s.mode().iloc[0]),
        n_rs=("rs_id", "nunique"), n_dokumen=("dokumen_id", "nunique"), n_baris=("nama_norm", "size"),
        pct_qc_masalah=("qc_masalah", lambda s: round(s.mean() * 100, 1)),
        contoh_nama_asli=("nama_asli", lambda s: s.mode().iloc[0])).reset_index()
    P = P.sort_values(["n_rs", "n_baris"], ascending=False).reset_index(drop=True)
    P["kode_sistem"] = P.kategori_std.map(TARGET).fillna("ICD-9-CM")
    P["query"] = [build_query(n, k) for n, k in zip(P.nama_norm, P.kategori_std)]
    print(f"nama unik: {len(P):,} | per sistem: {P.kode_sistem.value_counts().to_dict()}", flush=True)

    targets = load_targets()
    coded = (P.kode_sistem != "Lokal").to_numpy()
    Q = P[coded]
    Eq = embed_store(list(Q["query"]), cache)
    res = {}
    for sysname, tgt in targets.items():
        Et = embed_store(list(tgt.teks), cache)
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True).fit(list(tgt.teks))
        Xt = vec.transform(tgt.teks)
        top1, top5, sc = [], [], []
        for i in range(0, len(Q), 4000):
            S = 0.7 * (Eq[i:i + 4000] @ Et.T) + 0.3 * (vec.transform(Q["query"].iloc[i:i + 4000]) @ Xt.T).toarray()
            idx = np.argsort(-S, axis=1)[:, :5]
            for r in range(len(idx)):
                j = idx[r]
                top1.append(f"{tgt.kode.iloc[j[0]]} | {tgt.nama.iloc[j[0]]}")
                top5.append(" ;; ".join(f"{tgt.kode.iloc[k]} | {tgt.nama.iloc[k]} | {S[r, k]:.2f}" for k in j))
                sc.append(round(float(S[r, j[0]]), 3))
        res[sysname] = (np.array(top1, dtype=object), np.array(top5, dtype=object), np.array(sc))
        print(f"{sysname}: {len(Q):,} nama dinilai -> {len(tgt):,} kode", flush=True)
    # pilih sistem: kategori jelas (Laboratorium -> LOINC; Radiologi/Gigi/... -> ICD-9-CM) tetap; kategori umum
    # 'Tindakan Lain' (banyak nama lab tanpa judul bagian) -> sistem dengan skor tertinggi
    sys_q = Q.kode_sistem.to_numpy().copy()
    generic = (Q.kategori_std == "Tindakan Lain").to_numpy()
    lo_better = res["LOINC"][2] > res["ICD-9-CM"][2]
    sys_q[generic & lo_better] = "LOINC"
    print(f"dialihkan ke LOINC berdasarkan skor: {(generic & lo_better).sum():,} nama 'Tindakan Lain'", flush=True)
    P["sistem_dari"] = np.where(coded, "kategori", "kategori")
    P.loc[coded, "sistem_dari"] = np.where(generic & lo_better, "skor_tertinggi", "kategori")
    P.loc[coded, "kode_sistem"] = sys_q
    pick = lambda k: np.where(sys_q == "LOINC", res["LOINC"][k], res["ICD-9-CM"][k])  # noqa: E731
    P["usulan_top1"], P["kandidat_top5"], P["skor"] = "", "", np.nan
    P.loc[coded, "usulan_top1"], P.loc[coded, "kandidat_top5"], P.loc[coded, "skor"] = pick(0), pick(1), pick(2)
    P["status"] = np.where(P.kode_sistem == "Lokal", "lokal_tanpa_kode", "usulan")
    P["kode"], P["nama_kode"], P["reviewer"], P["catatan"] = "", "", "", ""
    cols = ["nama_norm", "contoh_nama_asli", "kategori_std", "kode_sistem", "sistem_dari", "n_rs", "n_dokumen", "n_baris",
            "pct_qc_masalah", "usulan_top1", "skor", "kandidat_top5", "status", "kode", "nama_kode", "reviewer", "catatan"]
    P[cols].to_csv(os.path.join(DS, "pemetaan_kode.csv.gz"), index=False)

    # sampel validasi PMIK: 150 nama tersering + 150 acak (n_rs >= 2) per sistem kode
    rng = np.random.default_rng(42)
    S = []
    for sysname in ["ICD-9-CM", "LOINC"]:
        Q = P[(P.kode_sistem == sysname) & (P.pct_qc_masalah < 50)]
        top = Q.head(150).assign(strata="sering (n_rs tertinggi)")
        rest = Q.iloc[150:]
        rest = rest[rest.n_rs >= 2]
        rnd = rest.iloc[rng.choice(len(rest), size=min(150, len(rest)), replace=False)].assign(strata="acak (n_rs >= 2)")
        S += [top, rnd]
    S = pd.concat(S)
    k5 = S.kandidat_top5.str.split(" ;; ")
    for i in range(5):
        S[f"kandidat_{i + 1}"] = k5.map(lambda c, i=i: " | ".join(c[i].split(" | ")[:2]) if len(c) > i else "")
    S["pilihan (1-5 / kode lain / tidak_ada)"] = ""
    S["catatan_pmik"] = ""
    keep = ["kode_sistem", "strata", "nama_norm", "contoh_nama_asli", "kategori_std", "n_rs"] + \
           [f"kandidat_{i + 1}" for i in range(5)] + ["pilihan (1-5 / kode lain / tidak_ada)", "catatan_pmik"]
    with pd.ExcelWriter(os.path.join(DS, "sampel_validasi_pmik.xlsx")) as xw:
        pd.DataFrame({"petunjuk": [
            "Untuk tiap nama layanan, pilih kandidat kode yang benar (isi 1-5), atau tulis kode lain, atau 'tidak_ada'.",
            "ICD-9-CM: Volume 3 (prosedur), versi CMS v32. LOINC: Universal Lab Orders Value Set (LOINC 2.83).",
            "strata 'sering' = 150 nama yang muncul di RS terbanyak; 'acak' = 150 nama acak yang muncul di >= 2 RS.",
            "Usulan dibuat otomatis (embedding + TF-IDF); belum tentu benar."]}).to_excel(xw, sheet_name="petunjuk", index=False)
        for sysname in ["ICD-9-CM", "LOINC"]:
            S[S.kode_sistem == sysname][keep].to_excel(xw, sheet_name=sysname, index=False)
    cov = P.assign(w=P.n_baris)
    print("cakupan baris oleh nama n_rs>=2:", round(cov[cov.n_rs >= 2].w.sum() / cov.w.sum() * 100, 1), "%")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/emb_cache")
