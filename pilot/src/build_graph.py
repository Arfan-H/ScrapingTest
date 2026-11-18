"""Tahap 5: bangun graf pilot + bandingkan harga pasangan terkonfirmasi."""
import json
import os

import networkx as nx
import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "out")
Q = pd.read_csv(f"{OUT}/_query.csv")
T = pd.read_csv(f"{OUT}/_target.csv")
c = pd.read_json(f"{OUT}/kandidat.json").set_index("q_id")
lab = {int(k): v for k, v in json.load(open(f"{OUT}/label_pilot.json")).items() if not k.startswith("_")}
gt = pd.read_csv(f"{OUT}/rembang_golongan_tarif.csv")
gt = gt[~((gt.jenis == "non operatif") & (gt.kelas == "One Day Surgery"))]  # sel salah baca

G = nx.MultiDiGraph()
for rs, meta in [("RSUD_CIMACAN", dict(kab="Cianjur", prov="Jawa Barat", kelas_rs="C", tahun=2025)),
                 ("RSUD_REMBANG", dict(kab="Rembang", prov="Jawa Tengah", kelas_rs="belum_dicek", tahun=2023))]:
    G.add_node(rs, tipe="RumahSakit", **meta)
for df, rs, pre in [(Q, "RSUD_CIMACAN", "C"), (T, "RSUD_REMBANG", "R")]:
    idcol = "q_id" if pre == "C" else "t_id"
    for r in df.itertuples():
        n = f"{pre}:{getattr(r, idcol)}"
        G.add_node(n, tipe="Layanan", nama=r.nama_asli, nama_norm=r.nama_norm)
        G.add_node(r.kategori_std, tipe="KategoriStd")
        G.add_edge(n, r.kategori_std, rel="KATEGORI")
        if str(r.sumber).startswith("golongan:"):
            g = "GOL:" + r.sumber.split(":", 1)[1]
            G.add_edge(n, g, rel="MASUK_GOLONGAN")
        else:
            G.add_edge(rs, n, rel="TARIF", harga=float(r.harga), kelas="(tunggal/III)")
for r in gt.itertuples():
    g = f"GOL:{r.jenis}/{r.golongan}"
    G.add_node(g, tipe="Golongan")
    G.add_node(f"Kelas {r.kelas}", tipe="KelasKamar")
    G.add_edge("RSUD_REMBANG", g, rel="TARIF_GOLONGAN", kelas=r.kelas, harga=float(r.total))

# SAMA_DENGAN: exact match + label silver
pairs = []
for q, r in c.iterrows():
    if r.exact_t >= 0:
        pairs.append((q, int(r.exact_t), "exact"))
for q, v in lab.items():
    if isinstance(v, list) and v and not any(p[0] == q for p in pairs):
        pairs.append((q, v[0], "label_silver"))
for q, t, src in pairs:
    G.add_edge(f"C:{q}", f"R:{t}", rel="SAMA_DENGAN", sumber=src)

nx.write_graphml(G, f"{OUT}/graf_pilot.graphml")
tipe = pd.Series(nx.get_node_attributes(G, "tipe")).value_counts()
rel = pd.Series([d["rel"] for *_, d in G.edges(data=True)]).value_counts()
print("Node:", tipe.to_dict()); print("Edge:", rel.to_dict())

# perbandingan harga pada pasangan terkonfirmasi
P = pd.DataFrame(pairs, columns=["q_id", "t_id", "sumber"])
P = P.merge(Q[["q_id", "nama_asli", "kategori_std", "harga"]], on="q_id").merge(
    T[["t_id", "nama_asli", "harga", "sumber"]].rename(columns={"sumber": "sumber_harga_R"}),
    on="t_id", suffixes=("_cimacan", "_rembang"))
P["rasio_C_per_R"] = P.harga_cimacan / P.harga_rembang
P["log2_rasio"] = np.log2(P.rasio_C_per_R)
P["flag"] = np.where(P.log2_rasio.abs() > 2, "JANGGAL (>4x)", "")
P.sort_values("log2_rasio").to_csv(f"{OUT}/perbandingan_harga.csv", index=False)
print(f"\nPasangan terkonfirmasi: {len(P)}  (exact {sum(P.sumber=='exact')}, silver {sum(P.sumber=='label_silver')})")
print("Median rasio Cimacan/Rembang:", round(P.rasio_C_per_R.median(), 2))
print(P.groupby("kategori_std").rasio_C_per_R.agg(["size", "median"]).round(2).to_string())
print("\nPasangan janggal (beda > 4x):")
print(P[P.flag != ""][["nama_asli_cimacan", "harga_cimacan", "nama_asli_rembang", "harga_rembang", "rasio_C_per_R"]]
      .round(2).to_string(index=False))
