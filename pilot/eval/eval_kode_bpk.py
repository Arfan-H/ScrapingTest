"""Ukur akurasi usulan kode dataset BPK (pemetaan_kode.csv.gz) pada label silver gold_kode_v0.json.

Label silver dibuat untuk nama di pilot/out/pemetaan_usulan.csv (kunci = indeks baris). Nama yang juga muncul
di dataset BPK (nama_norm sama) dinilai: hit@1 / hit@5 = kode usulan termasuk salah satu kode benar.
Pemakaian: python -I pilot/eval/eval_kode_bpk.py
"""
import json
import os

import pandas as pd

HERE = os.path.dirname(__file__)
gold = json.load(open(os.path.join(HERE, "gold_kode_v0.json")))
p = pd.read_csv(os.path.join(HERE, "..", "out", "pemetaan_usulan.csv"))
B = pd.read_csv(os.path.join(HERE, "..", "out", "dataset", "pemetaan_kode.csv.gz")).set_index("nama_norm")
seen = pd.read_csv(os.path.join(HERE, "seen_idx.csv")).iloc[:, 0].tolist()  # indeks 'seen' -> baris pemetaan_usulan
seen_map = {"icd": seen[:25], "loinc": seen[25:]}
rows = []
for split in ["seen", "fresh"]:
    for sysk, sysname in [("icd", "ICD-9-CM"), ("loinc", "LOINC")]:
        for idx, codes in gold[split][sysk].items():
            if not codes:
                continue
            n = p.nama_norm.iloc[seen_map[sysk][int(idx)] if split == "seen" else int(idx)]
            if n not in B.index:
                rows.append(dict(split=split, sistem=sysname, nama=n, ada_di_bpk=False))
                continue
            r = B.loc[n]
            cand = [c.split(" | ")[0] for c in str(r.kandidat_top5).split(" ;; ")]
            rows.append(dict(split=split, sistem=sysname, nama=n, ada_di_bpk=True, n_rs=r.n_rs,
                             hit1=cand[0] in codes, hit5=any(c in codes for c in cand)))
R = pd.DataFrame(rows)
print(R.groupby(["sistem", "split"]).ada_di_bpk.agg(["size", "sum"]).rename(columns={"size": "label", "sum": "ada_di_bpk"}))
print(R[R.ada_di_bpk].groupby(["sistem", "split"])[["hit1", "hit5"]].mean().round(2))
R.to_csv(os.path.join(HERE, "hasil_eval_kode_bpk.csv"), index=False)
