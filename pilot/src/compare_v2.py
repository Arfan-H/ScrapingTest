"""Perbandingan harga v2, dibaca dari tabel standar (tarif_standar_pilot.csv).

Perbaikan dari versi pertama (build_graph.py):
  - Rembang dibandingkan pada kelas III saja (sebelumnya median kelas III + II tercampur)
  - status BHP kedua sisi dicatat; ringkasan hanya memakai pasangan yang BHP-nya sama
  - baris dengan flag nama_terpotong dibuang
"""
import json
import os

import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "out")
t = pd.read_csv(f"{OUT}/tarif_standar_pilot.csv")
t = t[~t.flag_qc.str.contains("nama_terpotong")]
gol = pd.read_excel(f"{OUT}/tarif_standar_pilot.xlsx", sheet_name="golongan_tarif")
g3 = gol[gol.kelas == "III"].set_index("golongan_id").harga

C = t[(t.rs_id == "RSUD-KAB-CIANJUR-KLS-C") & (t.kelas == "Non-kelas") & t.harga.notna()]
R = t[t.rs_id == "RSUD-REMBANG-SOETRASNO"].copy()
R.loc[R.sumber_harga == "via_golongan", "harga"] = R.loc[R.sumber_harga == "via_golongan", "golongan"].map(g3)
R.loc[R.sumber_harga == "via_golongan", "kelas"] = "III"
R = R[R.harga.notna()]


def pick(df, prefer):
    """Satu harga per nama_norm. Untuk Rembang utamakan kelas III, lalu Non-kelas."""
    out = {}
    for n, g in df.groupby("nama_norm"):
        for k in prefer:
            gg = g[g.kelas == k]
            if len(gg):
                out[n] = dict(harga=float(gg.harga.min()), n_harga=gg.harga.nunique(), kelas=k,
                              bhp=gg.termasuk_bhp.iloc[0], nama=gg.nama_asli.iloc[0],
                              kategori=gg.kategori_std.iloc[0], halaman=int(gg.halaman.iloc[0]),
                              sumber=gg.sumber_harga.iloc[0])
                break
    return out


Cp = pick(C, ["Non-kelas"])
Rp = pick(R, ["III", "Non-kelas"])

# pasangan: nama identik + label silver pilot (dipetakan lewat nama_norm)
pairs = [(n, n, "exact") for n in Cp if n in Rp]
Q = pd.read_csv(f"{OUT}/_query.csv").set_index("q_id").nama_norm
T = pd.read_csv(f"{OUT}/_target.csv").set_index("t_id").nama_norm
lab = {int(k): v for k, v in json.load(open(f"{OUT}/label_pilot.json")).items() if not k.startswith("_")}
seen = {p[0] for p in pairs}
for q, v in lab.items():
    if isinstance(v, list) and v and Q[q] not in seen and Q[q] in Cp and T[v[0]] in Rp:
        pairs.append((Q[q], T[v[0]], "label_silver"))
        seen.add(Q[q])

rows = []
for cn, rn, src in pairs:
    c, r = Cp[cn], Rp[rn]
    rows.append(dict(nama_cianjur=c["nama"], nama_rembang=r["nama"], kategori_std=c["kategori"],
                     harga_cianjur=c["harga"], harga_rembang_kelas3=r["harga"], kelas_rembang=r["kelas"],
                     sumber_harga_rembang=r["sumber"], bhp_cianjur=c["bhp"], bhp_rembang=r["bhp"],
                     hlm_cianjur=c["halaman"], hlm_rembang=r["halaman"],
                     harga_ganda=(c["n_harga"] > 1) or (r["n_harga"] > 1), cocok_via=src))
P = pd.DataFrame(rows)
P["rasio"] = P.harga_cianjur / P.harga_rembang_kelas3
P["bhp_setara"] = (P.bhp_cianjur == P.bhp_rembang) & (P.bhp_cianjur != "tidak_jelas")
P = P.sort_values("rasio")
P.to_csv(f"{OUT}/perbandingan_harga_v2.csv", index=False)

S = P[P.bhp_setara & ~P.harga_ganda]
print(f"pasangan total {len(P)} (exact {sum(P.cocok_via == 'exact')}, silver {sum(P.cocok_via == 'label_silver')})")
print(f"dipakai ringkasan (BHP setara, harga tidak ganda): {len(S)}")
print("median rasio semua:", round(P.rasio.median(), 2), "| ringkasan:", round(S.rasio.median(), 2))
print(S.groupby("kategori_std").rasio.agg(["size", "median"]).round(2).to_string())
print("contoh lab:", S[S.kategori_std == "Laboratorium"][["nama_cianjur", "harga_cianjur", "harga_rembang_kelas3"]].head(6).to_string(index=False))
