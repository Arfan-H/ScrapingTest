"""Bangun graf tarif dari tabel standar (Excel hasil to_standard.py), untuk berapa pun dokumen.

Model (v3):
  Dokumen -BERLAKU_UNTUK-> RumahSakit
  Dokumen -TARIF{kelas,komponen,bhp,sumber_bhp,harga,halaman}-> Layanan
  Dokumen -TARIF_GOLONGAN{kelas,harga}-> Golongan
  Layanan -MASUK_GOLONGAN-> Golongan
  Layanan -KATEGORI-> KategoriStd
  Layanan -USULAN_KODE{skor,status=usulan}-> Kode      (peringkat 1 dari suggest_codes, belum divalidasi)
  Layanan -SAMA_NAMA-> Layanan                           (nama ternormalisasi identik, dokumen berbeda)
  Layanan -SAMA_DENGAN{sumber}-> Layanan                 (opsional: pasangan pilot dari compare_v2.py)

Layanan = satu node per (dokumen, nama_norm). Baris berflag nama_terpotong atau duplikat tidak dimasukkan.

Pemakaian:
  python -I pilot/src/build_graph.py --xlsx tarif_standar.xlsx --out graf.graphml
  python -I pilot/src/build_graph.py --xlsx tarif_standar_pilot.xlsx --out graf_pilot.graphml --pasangan perbandingan_harga_v2.csv
"""
import argparse
import os
from itertools import combinations

import networkx as nx
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "out")


def build(xlsx, pasangan=None):
    S = pd.read_excel(os.path.join(OUT, xlsx), sheet_name=None)
    tarif, rs, dok, drs, gol, pem = (S[k] for k in ["tarif", "rumah_sakit", "dokumen", "dokumen_rs", "golongan_tarif", "pemetaan"])
    G = nx.MultiDiGraph()
    for r in rs.itertuples():
        G.add_node(r.rs_id, tipe="RumahSakit", nama=r.nama_rs, kab_kota=r.kab_kota, provinsi=r.provinsi,
                   kelas_rs=str(r.kelas_rs) if pd.notna(r.kelas_rs) and str(r.kelas_rs) else "belum_dicek")
    for r in dok.itertuples():
        G.add_node(r.dokumen_id, tipe="Dokumen", jenis=r.jenis, nomor=str(r.nomor), tahun=int(r.tahun),
                   cakupan=str(r.cakupan), bhp_dokumen=str(getattr(r, "bhp_dokumen", "") if pd.notna(getattr(r, "bhp_dokumen", "")) else ""))
    for r in drs.itertuples():
        G.add_edge(r.dokumen_id, r.rs_id, rel="BERLAKU_UNTUK")

    t = tarif[~tarif.flag_qc.astype(str).str.contains("nama_terpotong|duplikat")]
    lid = lambda d, n: f"L:{d}:{n}"  # noqa: E731
    for (d, n), g in t.groupby(["dokumen_id", "nama_norm"]):
        G.add_node(lid(d, n), tipe="Layanan", nama=str(g.nama_asli.iloc[0]), nama_norm=n, dokumen=d)
        G.add_node(g.kategori_std.iloc[0], tipe="KategoriStd")
        G.add_edge(lid(d, n), g.kategori_std.iloc[0], rel="KATEGORI")
    for r in gol.itertuples():
        G.add_node(r.golongan_id, tipe="Golongan", nama=r.golongan, punya_tarif=True)
        G.add_edge(r.dokumen_id, r.golongan_id, rel="TARIF_GOLONGAN", kelas=r.kelas, harga=float(r.harga))
    for r in t.itertuples():
        node = lid(r.dokumen_id, r.nama_norm)
        if r.sumber_harga == "via_golongan":
            if r.golongan not in G:
                G.add_node(r.golongan, tipe="Golongan", nama=r.golongan, punya_tarif=False)
            G.add_edge(node, r.golongan, rel="MASUK_GOLONGAN")
        elif pd.notna(r.harga):
            G.add_edge(r.dokumen_id, node, rel="TARIF", tarif_id=r.tarif_id, kelas=str(r.kelas), komponen=r.komponen,
                       termasuk_bhp=str(r.termasuk_bhp),
                       sumber_bhp=str(getattr(r, "sumber_bhp", "")) if pd.notna(getattr(r, "sumber_bhp", "")) else "",
                       harga=float(r.harga), halaman=int(r.halaman))

    # usulan kode (peringkat 1)
    if "usulan_top1" in pem.columns:
        top = pem[pem.kode_sistem.isin(["ICD-9-CM", "LOINC"]) & pem.usulan_top1.notna()].set_index("nama_norm")
        for (d, n) in t.groupby(["dokumen_id", "nama_norm"]).size().index:
            if n in top.index:
                row = top.loc[n]
                kode, nama_kode = str(row.usulan_top1).split(" | ", 1)
                kid = f"{row.kode_sistem}:{kode}"
                if kid not in G:
                    G.add_node(kid, tipe="Kode", sistem=row.kode_sistem, kode=kode, nama=nama_kode)
                G.add_edge(lid(d, n), kid, rel="USULAN_KODE", skor=float(row.skor), status="usulan")

    # nama identik lintas dokumen
    by_name = t.groupby("nama_norm").dokumen_id.unique()
    for n, docs in by_name.items():
        for a, b in combinations(sorted(docs), 2):
            G.add_edge(lid(a, n), lid(b, n), rel="SAMA_NAMA")

    if pasangan:
        P = pd.read_csv(os.path.join(OUT, pasangan))
        for r in P.itertuples():
            a, b = lid("PERBUP-CIANJUR-3-2025", r.norm_cianjur), lid("PERBUP-REMBANG-16-2023", r.norm_rembang)
            if a in G and b in G:
                G.add_edge(a, b, rel="SAMA_DENGAN", sumber=r.cocok_via)
    assert all(G.nodes[n].get("tipe") for n in G), "ada node tanpa tipe"
    return G


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="tarif_standar.xlsx")
    ap.add_argument("--out", default="graf.graphml")
    ap.add_argument("--pasangan", default=None)
    a = ap.parse_args()
    G = build(a.xlsx, a.pasangan)
    nx.write_graphml(G, os.path.join(OUT, a.out))
    tipe = pd.Series(dict(G.nodes(data="tipe"))).value_counts().to_dict()
    rel = pd.Series([d["rel"] for *_, d in G.edges(data=True)]).value_counts().to_dict()
    print("Node:", tipe)
    print("Edge:", rel)


if __name__ == "__main__":
    main()
