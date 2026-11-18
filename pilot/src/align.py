"""Tahap 3: alignment nama layanan RSUD A (query) -> RSUD B (target).

Metode yang dibandingkan:
  M1 exact   : nama ternormalisasi identik
  M2 tfidf   : TF-IDF karakter 3-5 gram, cosine
  M3 e5      : embedding multilingual-e5-small (zero-shot), cosine
  M4 hybrid  : 0.5*tfidf + 0.5*e5 + bonus jika kategori standar sama
               (fitur "struktur graf" paling sederhana: tetangga kategori)

Harga sengaja TIDAK dipakai sebagai fitur supaya analisis selisih harga
setelahnya tidak sirkular.
"""
import json
import os
import sys

import numpy as np
import onnxruntime as ort
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from tokenizers import Tokenizer

sys.path.insert(0, os.path.dirname(__file__))
from normalize import load_items, norm_name, std_category  # noqa: E402

MODEL_DIR = os.environ.get("E5_DIR")
OUT = os.path.join(os.path.dirname(__file__), "..", "out")


def e5_embed(texts, batch=64):
    tok = Tokenizer.from_file(os.path.join(MODEL_DIR, "tokenizer.json"))
    tok.enable_padding(pad_id=1, pad_token="<pad>")
    tok.enable_truncation(max_length=64)
    sess = ort.InferenceSession(os.path.join(MODEL_DIR, "onnx", "model.onnx"))
    names = {i.name for i in sess.get_inputs()}
    out = []
    for i in range(0, len(texts), batch):
        enc = tok.encode_batch(["query: " + t for t in texts[i : i + batch]])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.zeros_like(ids)
        h = sess.run(None, feed)[0]
        v = (h * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)
        out.append(v / np.linalg.norm(v, axis=1, keepdims=True))
    return np.vstack(out)


def main(rs_q="RSUD_CIMACAN", rs_t="RSUD_REMBANG"):
    df = load_items([f"{OUT}/items_rembang.csv", f"{OUT}/items_cimacan.csv"])
    df = df[(df.kelas == "") & (df.nama_norm.str.len() >= 3)]
    df["sumber"] = "harga_langsung"
    # anggota golongan Rembang: harga diturunkan dari matriks golongan x kelas (kelas III)
    gt = pd.read_csv(f"{OUT}/rembang_golongan_tarif.csv")
    gt = gt[gt.kelas == "III"].set_index(["jenis", "golongan"]).total
    ga = pd.read_csv(f"{OUT}/rembang_golongan_anggota.csv")
    ga["harga_total"] = [gt.get((j, g)) for j, g in zip(ga.jenis, ga.golongan)]
    ga = ga.dropna(subset=["harga_total"])
    ga = pd.DataFrame(dict(
        rs="RSUD_REMBANG", page=ga.page, kategori="Tindakan " + ga.jenis + " / " + ga.golongan,
        nama_asli=ga.nama_asli, kelas="", harga_total=ga.harga_total,
        nama_norm=ga.nama_asli.map(norm_name), sumber="golongan:" + ga.jenis + "/" + ga.golongan))
    ga["kategori_std"] = [std_category("", n) for n in ga.nama_norm]
    df = pd.concat([df, ga], ignore_index=True)
    # satu baris per (rs, nama_norm); harga = median bila duplikat (beda kelas/kolom)
    uniq = (
        df.groupby(["rs", "nama_norm"], as_index=False)
        .agg(nama_asli=("nama_asli", "first"), kategori=("kategori", "first"),
             kategori_std=("kategori_std", "first"), harga=("harga_total", "median"),
             sumber=("sumber", "first"),
             n=("harga_total", "size"))
    )
    uniq.to_csv(f"{OUT}/layanan_unik.csv", index=False)
    Q = uniq[uniq.rs == rs_q].reset_index(drop=True)
    T = uniq[uniq.rs == rs_t].reset_index(drop=True)

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit(uniq.nama_norm)
    s_tfidf = (vec.transform(Q.nama_norm) @ vec.transform(T.nama_norm).T).toarray()
    E = e5_embed(list(Q.nama_norm) + list(T.nama_norm))
    s_e5 = E[: len(Q)] @ E[len(Q) :].T
    qc = Q.kategori_std.to_numpy(dtype=object)
    tc = T.kategori_std.to_numpy(dtype=object)
    same_cat = (qc[:, None] == tc[None, :]).astype(float)
    s_hyb = 0.5 * s_tfidf + 0.5 * s_e5 + 0.05 * same_cat
    exact = {n: i for i, n in enumerate(T.nama_norm)}

    np.save(f"{OUT}/_s_tfidf.npy", s_tfidf)
    np.save(f"{OUT}/_s_e5.npy", s_e5)
    np.save(f"{OUT}/_s_hyb.npy", s_hyb)

    rows = []
    for i, q in Q.iterrows():
        r = dict(q_id=i, q_nama=q.nama_asli, q_norm=q.nama_norm, q_cat=q.kategori_std,
                 q_harga=q.harga)
        r["exact_t"] = exact.get(q.nama_norm, -1)
        for key, S in [("tfidf", s_tfidf), ("e5", s_e5), ("hyb", s_hyb)]:
            top = np.argsort(-S[i])[:3]
            r[f"{key}_top3"] = top.tolist()
            r[f"{key}_s1"] = float(S[i, top[0]])
        rows.append(r)
    cand = pd.DataFrame(rows)
    cand.to_json(f"{OUT}/kandidat.json", orient="records", force_ascii=False, indent=1)
    T.to_csv(f"{OUT}/_target.csv", index_label="t_id")
    Q.to_csv(f"{OUT}/_query.csv", index_label="q_id")
    print(f"Query {rs_q}: {len(Q)} layanan unik | Target {rs_t}: {len(T)} layanan unik")
    print("Exact match:", int((cand.exact_t >= 0).sum()))


if __name__ == "__main__":
    main()
