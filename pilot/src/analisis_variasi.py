"""Analisis variasi tarif awal antar-RSUD (data penuh BPK).

Pertanyaan: untuk layanan yang NAMANYA SAMA (nama_norm persis) dan KELAS yang sama, seberapa beda tarifnya antar-RSUD?

Penyaring (semua dicatat jumlahnya di laporan):
- hanya Perda/Perbup/Perwali/Pergub (PMK = RS pusat/BLU, bukan RSUD, dikeluarkan);
- hanya dokumen versi terbaru per RS (urutan_versi_rs == 1) -> satu tarif per RS;
- baris tanpa tanda masalah (qc_masalah False) dan harga terverifikasi cocok dengan teks PDF;
- komponen 'total', tanpa varian (Reguler/Cyto/dll. dikeluarkan), kelas standar (III, II, I, VIP, VVIP, Utama, Non-kelas);
- nama generik (Kecil, Sedang, Besar, Khusus, ... yang maknanya bergantung pada judul tabel) dikeluarkan;
- dalam satu RS, bila nama+kelas yang sama muncul lebih dari sekali, dipakai mediannya (dicatat sebagai 'ganda dalam RS').
Grup = nama_norm x kelas dengan >= MIN_RS rumah sakit.

Keterbatasan: harga nominal (tahun dokumen 2001-2026, belum disesuaikan inflasi); pencocokan nama persis saja
(sinonim/ejaan lain belum digabung; pemetaan kode masih usulan dan belum divalidasi); status BHP termasuk/tidak sering
tidak jelas. Hasil ini deskriptif, bukan perbandingan biaya yang setara.

Keluaran: pilot/out/analisis/{variasi_grup.csv, variasi_kategori.csv, indeks_provinsi.csv, perubahan_versi.csv,
LAPORAN_variasi_awal.md}
Pemakaian: python -I pilot/src/analisis_variasi.py [MIN_RS=10]
"""
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.join(HERE, "..", "out", "dataset")
OUT = os.path.join(HERE, "..", "out", "analisis")
KELAS_STD = ["III", "II", "I", "VIP", "VVIP", "Utama", "Non-kelas"]
GENERIK = re.compile(r"^(?:(?:tindakan|operasi|pemeriksaan|tarif|paket|kategori|golongan|tingkat)\s+)?"
                     r"(sederhana|kecil|sedang|besar|khusus|canggih|ringan|berat|kompleks|biasa|i{1,3}|iv|v|"
                     r"[a-e]|kelas \w+|lain lain|lainnya|dll|-+|\d+)$")


def gm_ratio(x):
    return float(np.exp(np.mean(np.log(x))))


def load():
    T = pd.read_csv(os.path.join(DS, "tarif.csv.gz"), low_memory=False)
    D = pd.read_csv(os.path.join(DS, "dokumen.csv"))
    return T, D


def filter_rows(T, D):
    steps = [("semua baris", len(T))]
    d_ok = D[(D.jenis != "PMK")]
    T = T[T.dokumen_id.isin(d_ok.dokumen_id)]
    steps.append(("tanpa PMK (RS pusat)", len(T)))
    T = T[T.dokumen_id.isin(d_ok[d_ok.urutan_versi_rs == 1].dokumen_id)]
    steps.append(("dokumen versi terbaru per RS", len(T)))
    T = T[~T.qc_masalah.astype(bool) & (T.verifikasi_harga != "tidak_cocok")]
    steps.append(("tanpa tanda masalah, harga terverifikasi", len(T)))
    T = T[(T.komponen == "total") & T.varian.isna() & T.kelas.isin(KELAS_STD)]
    steps.append(("komponen total, tanpa varian, kelas standar", len(T)))
    T = T[~T.nama_norm.fillna("").str.strip().str.match(GENERIK) & (T.nama_norm.str.len() >= 3) & (T.harga > 0)]
    steps.append(("tanpa nama generik", len(T)))
    return T, steps


def per_rs(T, D):
    prov = D.set_index("dokumen_id").provinsi
    g = T.groupby(["nama_norm", "kelas", "rs_id"])
    R = g.agg(harga=("harga", "median"), n_baris=("harga", "size"), n_harga=("harga", "nunique"),
              tahun=("tahun", "first"), dokumen_id=("dokumen_id", "first"), kategori_std=("kategori_std", "first"),
              contoh=("nama_asli", "first"), kategori_asli=("kategori_asli", "first"), bhp=("termasuk_bhp", lambda s: s.mode().iat[0])).reset_index()
    R["provinsi"] = R.dokumen_id.map(prov)
    return R


def group_stats(R, min_rs):
    rows = []
    for (nm, kl), x in R.groupby(["nama_norm", "kelas"]):
        if len(x) < min_rs:
            continue
        h = x.harga.to_numpy(float)
        p10, p25, p50, p75, p90 = np.percentile(h, [10, 25, 50, 75, 90])
        rows.append(dict(nama_norm=nm, kelas=kl, kategori_std=x.kategori_std.mode().iat[0], contoh_nama=x.contoh.iat[0],
                         n_kata=len(nm.split()), n_judul_bagian=x.kategori_asli.str.lower().nunique(),
                         n_rs=len(x), n_provinsi=x.provinsi.nunique(), tahun_min=int(x.tahun.min()),
                         tahun_median=int(x.tahun.median()), tahun_max=int(x.tahun.max()),
                         harga_min=h.min(), p10=p10, p25=p25, median=p50, p75=p75, p90=p90, harga_max=h.max(),
                         rasio_p90_p10=p90 / p10, rasio_max_min=h.max() / h.min(), cv=h.std(ddof=1) / h.mean(),
                         pct_ganda_dalam_rs=round(100 * (x.n_harga > 1).mean(), 1),
                         pct_bhp_ya=round(100 * (x.bhp == "ya").mean(), 1),
                         pct_bhp_tidak=round(100 * (x.bhp == "tidak").mean(), 1)))
    return pd.DataFrame(rows).sort_values(["n_rs", "nama_norm"], ascending=[False, True])


def province_index(R, G):
    """Indeks harga provinsi: rata-rata geometrik (harga RS / median nasional grupnya), tiap RS diberi bobot sama."""
    key = G.set_index(["nama_norm", "kelas"])["median"]
    X = R.join(key.rename("med_nas"), on=["nama_norm", "kelas"], how="inner")
    X["lr"] = np.log(X.harga / X.med_nas)
    rs = X.groupby(["provinsi", "rs_id"]).lr.mean().reset_index()  # satu nilai per RS
    P = rs.groupby("provinsi").agg(n_rs=("rs_id", "size"), indeks=("lr", lambda s: float(np.exp(s.mean()))),
                                   indeks_rs_min=("lr", lambda s: float(np.exp(s.min()))),
                                   indeks_rs_max=("lr", lambda s: float(np.exp(s.max())))).reset_index()
    n_item = X.groupby("provinsi").size().rename("n_harga")
    return P.join(n_item, on="provinsi").sort_values("indeks", ascending=False)


def version_change(T, D):
    """RS dengan >= 2 versi: perubahan tarif nama+kelas yang sama antara versi terbaru dan versi sebelumnya."""
    d = D[(D.jenis != "PMK") & (D.urutan_versi_rs <= 2) & (D.n_versi_rs >= 2)][["dokumen_id", "rs_id", "urutan_versi_rs", "tahun"]]
    X = T[~T.qc_masalah.astype(bool) & (T.verifikasi_harga != "tidak_cocok") & (T.komponen == "total")
          & T.varian.isna() & T.kelas.isin(KELAS_STD)]
    X = X.merge(d.drop(columns="rs_id"), on="dokumen_id", suffixes=("", "_dok"))
    m = X.groupby(["rs_id", "urutan_versi_rs", "nama_norm", "kelas"]).agg(harga=("harga", "median"),
                                                                          tahun=("tahun_dok", "first")).reset_index()
    a = m[m.urutan_versi_rs == 1].drop(columns="urutan_versi_rs")
    b = m[m.urutan_versi_rs == 2].drop(columns="urutan_versi_rs")
    j = a.merge(b, on=["rs_id", "nama_norm", "kelas"], suffixes=("_baru", "_lama"))
    j = j[j.tahun_baru > j.tahun_lama]
    j["rasio"] = j.harga_baru / j.harga_lama
    rows = []
    for rs, x in j.groupby("rs_id"):
        yrs = int(x.tahun_baru.iat[0] - x.tahun_lama.iat[0])
        r = gm_ratio(x.rasio)
        rows.append(dict(rs_id=rs, tahun_lama=int(x.tahun_lama.iat[0]), tahun_baru=int(x.tahun_baru.iat[0]),
                         n_layanan_sama=len(x), rasio_median=float(x.rasio.median()), rasio_geomean=r,
                         pct_naik=round(100 * (x.rasio > 1.001).mean(), 1), pct_tetap=round(100 * (abs(x.rasio - 1) <= 0.001).mean(), 1),
                         pct_turun=round(100 * (x.rasio < 0.999).mean(), 1),
                         kenaikan_per_tahun_pct=round(100 * (r ** (1 / yrs) - 1), 2) if yrs > 0 else np.nan))
    return pd.DataFrame(rows).sort_values("n_layanan_sama", ascending=False)


def fmt(v):
    return f"{v:,.0f}".replace(",", ".")


def dec(v, d=2):
    return f"{v:.{d}f}".replace(".", ",")


def md_table(df, cols, head=None):
    s = "| " + " | ".join(head or cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in df[cols].itertuples(index=False):
        out = []
        for c, v in zip(cols, r):
            if c.startswith("tahun") or isinstance(v, (str, bool)):
                out.append(str(v))
            elif isinstance(v, (int, np.integer)) or (isinstance(v, (float, np.floating)) and abs(v) >= 1000):
                out.append(fmt(v))
            else:
                out.append(dec(v, 1) if c.startswith("pct") else dec(v))
            out[-1] = out[-1].replace("|", "/")
        s += "| " + " | ".join(out) + " |\n"
    return s


def main(min_rs=10):
    os.makedirs(OUT, exist_ok=True)
    T, D = load()
    F, steps = filter_rows(T, D)
    R = per_rs(F, D)
    G = group_stats(R, min_rs)
    G.to_csv(os.path.join(OUT, "variasi_grup.csv"), index=False)
    K = G.groupby("kategori_std").agg(n_grup=("nama_norm", "size"), median_n_rs=("n_rs", "median"),
                                      median_rasio_p90_p10=("rasio_p90_p10", "median"), median_cv=("cv", "median"),
                                      pct_grup_rasio_ge_3=("rasio_p90_p10", lambda s: round(100 * (s >= 3).mean(), 1))
                                      ).reset_index().sort_values("median_rasio_p90_p10", ascending=False)
    K.to_csv(os.path.join(OUT, "variasi_kategori.csv"), index=False)
    P = province_index(R, G)
    P.to_csv(os.path.join(OUT, "indeks_provinsi.csv"), index=False)
    V = version_change(T, D)
    V.to_csv(os.path.join(OUT, "perubahan_versi.csv"), index=False)

    # tahun vs harga dalam grup: korelasi Spearman per grup (apakah dokumen lebih baru lebih mahal?)
    rho = []
    for (nm, kl), x in R.join(G.set_index(["nama_norm", "kelas"])[[]], on=["nama_norm", "kelas"], how="inner").groupby(["nama_norm", "kelas"]):
        if x.tahun.nunique() >= 3:
            rho.append(x.harga.rank().corr(x.tahun.rank()))
    rho = pd.Series(rho)

    # kelas: rasio harga kelas terhadap kelas III di RS yang sama (akomodasi/visite dan tindakan)
    W = R[R.kelas.isin(["III", "II", "I", "VIP", "VVIP"])].pivot_table(index=["rs_id", "nama_norm"], columns="kelas", values="harga")
    kr = {k: (W[k] / W["III"]).dropna() for k in ["II", "I", "VIP", "VVIP"] if k in W}

    n_rs_all = F.rs_id.nunique()
    top = G.sort_values("n_rs", ascending=False).head(25)
    wide = G[G.n_rs >= 20].sort_values("rasio_p90_p10", ascending=False).head(15)
    tight = G[G.n_rs >= 20].sort_values("rasio_p90_p10").head(10)
    rep = []
    rep.append("# Laporan variasi tarif awal antar-RSUD\n\n")
    rep.append(f"Dibuat oleh `pilot/src/analisis_variasi.py` (MIN_RS={min_rs}). Data: `pilot/out/dataset/tarif.csv.gz` "
               f"({fmt(len(T))} baris, parser dibekukan di cb968f4).\n")
    rep.append("**Status: deskriptif, awal.** Harga nominal (belum disesuaikan inflasi), nama dicocokkan persis "
               "(sinonim belum digabung), akurasi ekstraksi belum diukur dengan gold set. Jangan dikutip sebagai temuan "
               "akhir sebelum gold set dinilai.\n")
    rep.append("## 1. Penyaringan\n")
    rep.append("| langkah | baris tersisa |\n|---|---|\n" + "".join(f"| {a} | {fmt(b)} |\n" for a, b in steps))
    rep.append(f"\nSetelah penyaringan: {fmt(n_rs_all)} RS, {fmt(R.groupby(['nama_norm','kelas']).ngroups)} kombinasi "
               f"nama x kelas. Yang dimiliki >= {min_rs} RS: **{fmt(len(G))} grup** "
               f"({fmt(G.n_rs.sum())} harga RS). Sebaran tahun dokumen: "
               f"{int(F.tahun.min())}-{int(F.tahun.max())}, median {int(F.tahun.median())}.\n")
    rep.append("## 2. Besar variasi\n")
    rep.append(f"Rasio p90/p10 (harga RS di persentil 90 dibagi persentil 10) per grup: median "
               f"**{dec(G.rasio_p90_p10.median())}**, kuartil {dec(G.rasio_p90_p10.quantile(.25))}-{dec(G.rasio_p90_p10.quantile(.75))}. "
               f"{(G.rasio_p90_p10 >= 3).mean()*100:.0f}% grup punya rasio >= 3; {(G.rasio_p90_p10 >= 5).mean()*100:.0f}% >= 5. "
               f"Median koefisien variasi {dec(G.cv.median())}. Catatan metrik: angka ini adalah MEDIAN (antar-grup) dari "
               f"rasio p90/p10 di dalam grup; berbeda dari metrik pilot (rasio harga antara dua RS), jangan dipertukarkan. "
               f"Rasio mentah ini belum mengendalikan tahun dokumen ({int(F.tahun.min())}-{int(F.tahun.max())}); "
               f"analisis lanjut sebaiknya memakai model campuran log-harga (efek acak layanan; efek tetap tahun, kelas, "
               f"tipe/kepemilikan RS, wilayah).\n")
    rep.append("### Per kategori\n")
    rep.append(md_table(K, ["kategori_std", "n_grup", "median_n_rs", "median_rasio_p90_p10", "median_cv", "pct_grup_rasio_ge_3"],
                        ["kategori", "grup", "median RS/grup", "median p90/p10", "median CV", "% grup p90/p10 >= 3"]))
    rep.append("\n### 25 layanan yang paling banyak RS-nya\n")
    rep.append(md_table(top, ["contoh_nama", "kelas", "n_rs", "n_provinsi", "p10", "median", "p90", "rasio_p90_p10", "tahun_median"],
                        ["layanan", "kelas", "RS", "prov", "p10", "median", "p90", "p90/p10", "tahun med."]))
    rep.append("\n### Variasi terlebar (grup >= 20 RS)\n")
    rep.append("Variasi sangat lebar sering menandakan nama yang sama dipakai untuk layanan yang berbeda cakupannya "
               "(mis. paket vs satuan, per hari vs per tindakan) atau kesalahan ekstraksi; perlu dicek sebelum ditafsirkan.\n\n")
    rep.append(md_table(wide, ["contoh_nama", "kelas", "n_rs", "harga_min", "median", "harga_max", "rasio_p90_p10", "pct_ganda_dalam_rs"],
                        ["layanan", "kelas", "RS", "min", "median", "maks", "p90/p10", "% ganda dlm RS"]))
    nk = G.assign(b=np.where(G.n_kata == 1, "1 kata", np.where(G.n_kata == 2, "2 kata", ">= 3 kata"))).groupby("b").agg(
        n=("n_rs", "size"), r=("rasio_p90_p10", "median"), j=("n_judul_bagian", "median"))
    rep.append("\n**Nama pendek kehilangan konteks bagian.** Contoh: 'Thorax' termurah Rp 38.500 (tabel \"Pemeriksaan "
               "Radiologi\"), termahal Rp 3,5 juta (tabel \"CT ANGIOGRAPHY\" / \"CT-SCAN KONTRAS\"). Judul tabel tersimpan di "
               "kolom `kategori_asli`, tetapi tidak menjadi bagian `nama_norm`, sehingga X-ray dan CT-scan masuk satu grup. "
               "Median p90/p10 menurut panjang nama: " + "; ".join(
                   f"{k}: {dec(v.r)} ({int(v.n)} grup, median {dec(v.j, 0)} judul bagian berbeda)" for k, v in nk.iterrows()) +
               ". Untuk analisis lanjut, nama pendek perlu digabung dengan judul bagiannya.\n\n")
    rep.append("\n### Variasi tersempit (grup >= 20 RS)\n")
    rep.append(md_table(tight, ["contoh_nama", "kelas", "n_rs", "p10", "median", "p90", "rasio_p90_p10"],
                        ["layanan", "kelas", "RS", "p10", "median", "p90", "p90/p10"]))
    rep.append("\n## 3. Faktor yang ikut menjelaskan variasi\n")
    rep.append(f"- **Tahun dokumen.** Korelasi Spearman harga vs tahun di dalam grup (grup dengan >= 3 tahun berbeda, "
               f"n={len(rho)}): median {dec(rho.median())}; {(rho > 0).mean()*100:.0f}% grup positif. Sebagian variasi "
               f"adalah perbedaan waktu, jadi penyesuaian inflasi (IHK kesehatan BPS) diperlukan sebelum menyimpulkan.\n")
    if kr:
        rep.append("- **Kelas perawatan** (harga kelas X / kelas III untuk nama yang sama di RS yang sama): " +
                   "; ".join(f"{k}: median {dec(v.median())} (n={len(v)})" for k, v in kr.items()) + ".\n")
    rep.append(f"- **BHP.** Di grup yang dianalisis, rata-rata {G.pct_bhp_ya.mean():.0f}% harga RS tercatat termasuk BHP, "
               f"{G.pct_bhp_tidak.mean():.0f}% tidak termasuk, sisanya tidak jelas. Harga yang tidak termasuk BHP "
               f"belum lengkap; ini sumber bias yang harus disebut.\n")
    rep.append(f"- **Nama ganda dalam satu RS.** Rata-rata {dec(G.pct_ganda_dalam_rs.mean(), 1)}% RS per grup punya lebih dari satu "
               f"harga untuk nama+kelas yang sama (mis. di bagian berbeda); dipakai mediannya.\n")
    rep.append("\n## 4. Indeks harga provinsi (awal)\n")
    rep.append("Indeks = rata-rata geometrik (harga RS / median nasional grupnya) per RS, lalu dirata-rata per provinsi. "
               "1,00 = setara median nasional. Provinsi dengan sedikit RS tidak stabil; tahun dokumen belum dikendalikan.\n\n")
    rep.append(md_table(P, ["provinsi", "n_rs", "n_harga", "indeks", "indeks_rs_min", "indeks_rs_max"],
                        ["provinsi", "RS", "harga", "indeks", "RS terendah", "RS tertinggi"]))
    if len(V):
        rep.append("\n## 5. Perubahan tarif antar-versi di RS yang sama\n")
        rep.append(f"{len(V)} RS punya versi terbaru dan versi sebelumnya dengan nama+kelas yang sama. Median kenaikan "
                   f"per tahun (rata-rata geometrik per RS, disetahunkan): **{dec(V.kenaikan_per_tahun_pct.median(), 1)}%**; "
                   f"median porsi layanan yang naik {V.pct_naik.median():.0f}%, tetap {V.pct_tetap.median():.0f}%, "
                   f"turun {V.pct_turun.median():.0f}%. Banyak versi baru adalah perubahan sebagian yang mengulang tarif lama tanpa "
                   f"mengubahnya; penurunan besar di satu RS perlu dicek (bisa beda cakupan atau kesalahan ekstraksi). "
                   f"Bias seleksi: hanya RS yang punya >= 2 versi di BPK ({len(V)} dari {fmt(n_rs_all)} RS), jadi angka ini "
                   f"belum mewakili semua RSUD.\n\n")
        rep.append(md_table(V.head(20), ["rs_id", "tahun_lama", "tahun_baru", "n_layanan_sama", "rasio_median", "pct_naik", "kenaikan_per_tahun_pct"],
                            ["RS", "lama", "baru", "layanan sama", "rasio median", "% naik", "naik/thn %"]))
    rep.append("\n## 6. Langkah berikut\n")
    rep.append("1. Nilai gold set ekstraksi (`pilot/eval/gold/gold_ekstraksi_v1.xlsx`) untuk tahu seberapa besar variasi "
               "di atas bisa berasal dari kesalahan ekstraksi.\n"
               "2. Definisi kelompok dulu (mengubah semua angka): nama pendek (1-2 kata) digabung dengan judul bagian "
               "(`kategori_asli`) sebelum dikelompokkan; ini perubahan pada analisis, bukan parser, dan diberi versi.\n"
               "3. Sesuaikan harga ke tahun dasar dengan IHK (kelompok kesehatan) BPS (hanya menggeser skala); lalu gabungkan sinonim lewat pemetaan kode yang sudah divalidasi (bukan usulan otomatis).\n"
               "4. Cek manual grup dengan variasi terlebar (bagian 2) untuk memisahkan beda cakupan layanan vs kesalahan.\n"
               "5. Model penjelas (mis. regresi log-harga ~ tahun + kelas + provinsi + tipe RS + BHP) setelah langkah 1-3.\n")
    rep.append("\n## Berkas\n- `variasi_grup.csv`: statistik per nama x kelas\n- `variasi_kategori.csv`\n"
               "- `indeks_provinsi.csv`\n- `perubahan_versi.csv`\n")
    txt = "".join(x if x.endswith("\n\n") or x.startswith("|") or x.startswith("- ") or x[:2] in ("1.", "2.") else x + "\n" for x in rep)
    txt = re.sub(r"\n(#+ )", r"\n\n\1", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    open(os.path.join(OUT, "LAPORAN_variasi_awal.md"), "w", encoding="utf-8").write(txt)
    for a, b in steps:
        print(f"{a:50s} {b:>8,}")
    print("grup:", len(G), "| median p90/p10:", round(G.rasio_p90_p10.median(), 2), "| RS:", n_rs_all, "| versi:", len(V))


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:2]))
