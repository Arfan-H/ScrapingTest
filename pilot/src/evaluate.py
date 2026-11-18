"""Tahap 4: evaluasi alignment pada sampel berlabel + pemilihan ambang."""
import json
import os

import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "out")
lab = {int(k): v for k, v in json.load(open(f"{OUT}/label_pilot.json")).items() if not k.startswith("_")}
c = pd.read_json(f"{OUT}/kandidat.json").set_index("q_id")
S = {k: np.load(f"{OUT}/_s_{k}.npy") for k in ["tfidf", "e5", "hyb"]}

valid = {q: v for q, v in lab.items() if isinstance(v, list)}
n_x = sum(v == "X" for v in lab.values()); n_r = sum(v == "R" for v in lab.values())
pos = {q: v for q, v in valid.items() if v}
print(f"Sampel {len(lab)} | rusak {n_x} | ragu {n_r} | dievaluasi {len(valid)} "
      f"(punya padanan {len(pos)}, tidak punya {len(valid) - len(pos)})\n")

rows = []
# M1 exact
tp = sum(c.loc[q, "exact_t"] in v for q, v in pos.items())
fp = sum(c.loc[q, "exact_t"] >= 0 and c.loc[q, "exact_t"] not in v for q, v in valid.items())
rows.append(dict(metode="M1 exact", hit1=tp / len(pos), hit3=tp / len(pos),
                 thr="-", precision=tp / max(tp + fp, 1), recall=tp / len(pos)))
for key, name in [("tfidf", "M2 TF-IDF char"), ("e5", "M3 e5 zero-shot"), ("hyb", "M4 hybrid")]:
    h1 = np.mean([c.loc[q, f"{key}_top3"][0] in v for q, v in pos.items()])
    h3 = np.mean([any(t in v for t in c.loc[q, f"{key}_top3"]) for q, v in pos.items()])
    best = None
    for thr in np.arange(0.30, 0.96, 0.01):
        tp = fp = 0
        for q, v in valid.items():
            t, s = c.loc[q, f"{key}_top3"][0], c.loc[q, f"{key}_s1"]
            if s >= thr:
                tp += t in v
                fp += t not in v
        p = tp / max(tp + fp, 1); r = tp / len(pos); f1 = 2 * p * r / max(p + r, 1e-9)
        if best is None or f1 > best[0]:
            best = (f1, thr, p, r)
    rows.append(dict(metode=name, hit1=h1, hit3=h3, thr=round(best[1], 2),
                     precision=best[2], recall=best[3]))
res = pd.DataFrame(rows)
res["F1"] = 2 * res.precision * res.recall / (res.precision + res.recall)
print(res.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
res.to_csv(f"{OUT}/hasil_alignment.csv", index=False)
print("\nCatatan: ambang dipilih di sampel yang sama (optimistis) -> butuh dev/test terpisah.")
