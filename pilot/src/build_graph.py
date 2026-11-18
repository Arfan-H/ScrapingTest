"""Bangun graf pilot dari tabel standar (out/tarif_standar_pilot.xlsx).

Model:
  Dokumen -BERLAKU_UNTUK-> RumahSakit      (satu Perbup bisa berlaku untuk beberapa RS)
  Dokumen -TARIF{kelas,komponen,bhp,harga,halaman}-> Layanan
  Dokumen -TARIF_GOLONGAN{kelas,harga}-> Golongan
  Layanan -MASUK_GOLONGAN-> Golongan
  Layanan -KATEGORI-> KategoriStd
  Layanan -SAMA_DENGAN{sumber}-> Layanan   (pasangan dari compare_v2.py)

Tarif menempel pada Dokumen, bukan RumahSakit, jadi menambah RSUD Kelas C Cianjur
lain cukup satu edge BERLAKU_UNTUK tanpa menggandakan tarif.
Baris flag nama_terpotong dan duplikat tidak dimasukkan.
"""
import os

import networkx as nx
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "out")
X = f"{OUT}/tarif_standar_pilot.xlsx"
tarif = pd.read_excel(X, sheet_name="tarif")
rs = pd.read_excel(X, sheet_name="rumah_sakit")
dok = pd.read_excel(X, sheet_name="dokumen")
drs = pd.read_excel(X, sheet_name="dokumen_rs")
gol = pd.read_excel(X, sheet_name="golongan_tarif")
pairs = pd.read_csv(f"{OUT}/perbandingan_harga_v2.csv")

G = nx.MultiDiGraph()
for r in rs.itertuples():
    G.add_node(r.rs_id, tipe="RumahSakit", nama=r.nama_rs, kab_kota=r.kab_kota, provinsi=r.provinsi,
               kelas_rs=str(r.kelas_rs) if pd.notna(r.kelas_rs) else "belum_dicek")
for r in dok.itertuples():
    G.add_node(r.dokumen_id, tipe="Dokumen", jenis=r.jenis, nomor=str(r.nomor), tahun=int(r.tahun),
               tgl_berlaku=r.tgl_berlaku, cakupan=r.cakupan)
for r in drs.itertuples():
    G.add_edge(r.dokumen_id, r.rs_id, rel="BERLAKU_UNTUK")

t = tarif[~tarif.flag_qc.str.contains("nama_terpotong|duplikat")]
lid = lambda d, n: f"L:{d}:{n}"  # noqa: E731
for (d, n), g in t.groupby(["dokumen_id", "nama_norm"]):
    node = lid(d, n)
    G.add_node(node, tipe="Layanan", nama=g.nama_asli.iloc[0], nama_norm=n, dokumen=d)
    G.add_node(g.kategori_std.iloc[0], tipe="KategoriStd")
    G.add_edge(node, g.kategori_std.iloc[0], rel="KATEGORI")
for r in gol.itertuples():
    G.add_node(r.golongan_id, tipe="Golongan", nama=r.golongan, punya_tarif=True)
for r in t.itertuples():
    node = lid(r.dokumen_id, r.nama_norm)
    if r.sumber_harga == "via_golongan":
        if r.golongan not in G:  # mis. One Day Surgery: daftar anggota ada, matriks tarif tidak
            G.add_node(r.golongan, tipe="Golongan", nama=r.golongan, punya_tarif=False)
        G.add_edge(node, r.golongan, rel="MASUK_GOLONGAN")
    elif pd.notna(r.harga):
        G.add_edge(r.dokumen_id, node, rel="TARIF", tarif_id=r.tarif_id, kelas=str(r.kelas),
                   komponen=r.komponen, termasuk_bhp=r.termasuk_bhp, harga=float(r.harga), halaman=int(r.halaman))
for r in gol.itertuples():
    G.add_edge(r.dokumen_id, r.golongan_id, rel="TARIF_GOLONGAN", kelas=r.kelas, harga=float(r.harga))
for r in pairs.itertuples():
    a, b = lid("PERBUP-CIANJUR-3-2025", r.norm_cianjur), lid("PERBUP-REMBANG-16-2023", r.norm_rembang)
    assert a in G and b in G, (a, b)
    G.add_edge(a, b, rel="SAMA_DENGAN", sumber=r.cocok_via)

nx.write_graphml(G, f"{OUT}/graf_pilot.graphml")
tipe = pd.Series(dict(G.nodes(data="tipe"))).value_counts().to_dict()
rel = pd.Series([d["rel"] for *_, d in G.edges(data=True)]).value_counts().to_dict()
lay = pd.Series([d for _, d in G.nodes(data="dokumen") if d]).value_counts().to_dict()
print("Node:", tipe)
print("Edge:", rel)
print("Layanan per dokumen:", lay)
assert all(G.nodes[n].get("tipe") for n in G), "ada node tanpa tipe"
kat = pd.DataFrame([(d["dokumen"], k) for n, d in G.nodes(data=True) if d.get("tipe") == "Layanan"
                    for _, k, e in G.out_edges(n, data=True) if e["rel"] == "KATEGORI"], columns=["dok", "kat"])
print("Layanan per kategori:", kat.groupby(["kat", "dok"]).size().unstack().fillna(0).astype(int).to_dict("index"))
print("Golongan bertarif:", sum(1 for _, d in G.nodes(data=True) if d.get("tipe") == "Golongan" and d.get("punya_tarif")))
