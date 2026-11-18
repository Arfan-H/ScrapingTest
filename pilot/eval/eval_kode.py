"""Bandingkan varian pengusul kode (model x kamus) pada label silver gold_kode_v0.json."""
import json, os, sys
import numpy as np, pandas as pd, onnxruntime as ort
from tokenizers import Tokenizer
from sklearn.feature_extraction.text import TfidfVectorizer
HERE = os.path.dirname(__file__); sys.path.insert(0, os.path.join(HERE, "..", "src"))
from suggest_codes import load_targets, translate
from medterm_id_en import translate_v2
CACHE = sys.argv[3] if len(sys.argv) > 3 else "/tmp"

def embed(model_dir, texts, tag, batch=32):
    key = os.path.join(CACHE, f"emb_{tag}_{abs(hash(tuple(texts))) % 10**12}.npy")
    if os.path.exists(key): return np.load(key)
    tok = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
    tok.enable_padding(pad_id=1, pad_token="<pad>"); tok.enable_truncation(max_length=64)
    so = ort.SessionOptions(); so.intra_op_num_threads = os.cpu_count()
    sess = ort.InferenceSession(os.path.join(model_dir, "onnx", "model.onnx"), so)
    names = {i.name for i in sess.get_inputs()}; out = []
    for i in range(0, len(texts), batch):
        enc = tok.encode_batch(["query: " + t for t in texts[i:i+batch]])
        ids = np.array([e.ids for e in enc], dtype=np.int64); m = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": m}
        if "token_type_ids" in names: feed["token_type_ids"] = np.zeros_like(ids)
        h = sess.run(None, feed)[0]; v = (h * m[..., None]).sum(1) / m.sum(1, keepdims=True)
        out.append(v / np.linalg.norm(v, axis=1, keepdims=True))
    E = np.vstack(out); np.save(key, E); return E

models = {"e5-small": sys.argv[1], "e5-large": sys.argv[2]}
gold = json.load(open(os.path.join(HERE, "gold_kode_v0.json")))
p = pd.read_csv(os.path.join(HERE, "..", "out", "pemetaan_usulan.csv"))
seen = pd.read_csv(os.path.join(CACHE, "seen_idx.csv")).iloc[:, 0].tolist()
seen_icd, seen_lo = seen[:25], seen[25:]
items = []  # (split, system, row_index, gold codes)
for k, g in gold["seen"]["icd"].items(): items.append(("seen", "ICD-9-CM", seen_icd[int(k)], g))
for k, g in gold["seen"]["loinc"].items(): items.append(("seen", "LOINC", seen_lo[int(k)], g))
for k, g in gold["fresh"]["icd"].items(): items.append(("fresh", "ICD-9-CM", int(k), g))
for k, g in gold["fresh"]["loinc"].items(): items.append(("fresh", "LOINC", int(k), g))
items = [it for it in items if it[3]]
T = load_targets(); rows = []
for mname, mdir in models.items():
    for dname, fn in [("kamus v1", translate), ("kamus v2", translate_v2)]:
        for sysn in ["ICD-9-CM", "LOINC"]:
            tgt = T[sysn]; its = [it for it in items if it[1] == sysn]
            qs = [f"{p.nama_norm[it[2]]} {fn(p.nama_norm[it[2]])}" for it in its]
            Et = embed(mdir, list(tgt.teks), f"{mname}_{sysn}_tgt"); Eq = embed(mdir, qs, f"{mname}_{sysn}_{dname}")
            vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit(list(tgt.teks) + qs)
            S = 0.7 * (Eq @ Et.T) + 0.3 * (vec.transform(qs) @ vec.transform(tgt.teks).T).toarray()
            for it, srow in zip(its, S):
                top = [tgt.kode.iloc[j] for j in np.argsort(-srow)[:5]]
                rows.append(dict(model=mname, kamus=dname, sistem=sysn, split=it[0], nama=p.contoh_nama_asli[it[2]],
                                 hit1=top[0] in it[3], hit5=any(c in it[3] for c in top), top1=top[0]))
R = pd.DataFrame(rows); R.to_csv(os.path.join(HERE, "hasil_eval_kode.csv"), index=False)
summ = R.groupby(["sistem", "split", "model", "kamus"]).agg(n=("hit1", "size"), hit1=("hit1", "mean"), hit5=("hit5", "mean")).round(2)
print(summ.to_string())
