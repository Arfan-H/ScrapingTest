"""Uji estimator gold set v3 dengan penilai simulasi yang kebenarannya diketahui (hanya keluaran agregat).

Butir presisi dari manifest diberi jawaban simulasi: galat per dokumen e_d ~ Beta(mu_h * kappa, (1 - mu_h) * kappa)
(berkluster per dokumen; kappa kecil = sangat berkluster), lalu y ~ Bernoulli(1 - e_d). Nilai sebenarnya (target
superpopulasi / dokumen baru) = sum_h W_h (1 - mu_h). Fungsi estimasi diambil langsung dari nilai_gold_ekstraksi.py.
Tidak menampilkan isi sampel apa pun.

Hasil saat pra-registrasi (400 ulangan): lihat pilot/eval/gold/PRAREGISTRASI_gold_v3.md.
Pemakaian: python -I pilot/eval/simulasi_estimator_gold.py [ulangan=400]
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nilai_gold_ekstraksi as n  # noqa: E402

MU = [0.30, 0.25, 0.12, 0.05, 0.20, 0.08]  # galat rata-rata per strata (urut abjad), sengaja beragam


def main(reps=400):
    n.B = 1000
    G = os.path.join(HERE, "gold")
    M = pd.read_csv(os.path.join(G, "gold_ekstraksi_v3_manifest.csv"), keep_default_na=False)
    S = pd.read_csv(os.path.join(G, "gold_ekstraksi_v3_strata.csv")).set_index("strata")
    mu = dict(zip(sorted(S.index), MU))
    docs = M.drop_duplicates("dokumen_id")[["dokumen_id", "strata"]].to_numpy()
    rng = np.random.default_rng(2026)
    rows = []
    for kappa in [20, 4]:
        res = {}
        for _ in range(reps):
            e = {d: rng.beta(mu[s] * kappa, (1 - mu[s]) * kappa) for d, s in docs}
            P = M[M.jenis == "presisi"].copy()
            P["sim"] = (rng.random(len(P)) > P.dokumen_id.map(e).to_numpy()).astype(float)
            for name, makro, W, npop in [("makro (UTAMA)", True, S.dok_eligible.astype(float), None),
                                         ("makro sensus+FPC", True, S.dok_eligible.astype(float), S.dok_eligible),
                                         ("berbobot baris", False, S.baris_eligible.astype(float), None)]:
                it = n.prec_items(P, "sim", makro=makro)
                est = n.estimate(it, W, rng, N_pop=npop)
                hs = sorted(set(it.strata))
                w = W.reindex(hs)
                truth = float(sum(w[h] * (1 - mu[h]) for h in hs) / w.sum())
                res.setdefault(name, []).append((est["est"] - truth, est["lo"] <= truth <= est["hi"], est["hi"] - est["lo"]))
        for name, v in res.items():
            a = np.array(v, float)
            rows.append(dict(kappa=kappa, estimator=name, bias_pp=round(100 * a[:, 0].mean(), 2),
                             cakupan_CI95_pct=round(100 * a[:, 1].mean()), lebar_CI_pp=round(100 * a[:, 2].mean(), 1)))
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    print("Catatan: target superpopulasi; versi sensus+FPC menargetkan dataset ini, jadi cakupannya terhadap target ini "
          "boleh lebih rendah.")


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:2]))
