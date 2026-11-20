"""Bangun dataset tarif standar dari buku tarif BPK (format long, sheet seperti pilot).

Masukan:
  bpk_v3/klasifikasi.csv              : file mana yang buku tarif teks
  bpk_v3/metadata.csv, bpk_v3/list.csv : metadata BPK (nama, judul, jenis, tahun, relasi antarperaturan)
  pilot/out/bpk/uji_parser_baris_bhp.csv.gz : baris tarif hasil konverter + status BHP
  pilot/out/bpk/bhp_pasal.csv          : status BHP per dokumen dari pasal
  pilot/config/wilayah/*.csv           : kab/kota -> provinsi (Kemendagri, 34 provinsi)

Keluaran (pilot/out/dataset/):
  tarif.csv.gz       : satu baris = satu harga (nama x kelas)
  dokumen.csv        : satu baris = satu peraturan (beberapa file bisa milik satu peraturan)
  rumah_sakit.csv    : RS yang disebut di judul peraturan
  dokumen_rs.csv     : peraturan -> RS
  relasi.csv         : relasi antarperaturan (mengubah, mencabut) yang tertaut ke dokumen di dataset
  tarif_standar_bpk.xlsx : semua sheet kecuali tarif (tarif terlalu besar untuk Excel yang nyaman dibuka)

Pemakaian: python -I pilot/src/bangun_dataset.py
"""
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from normalize import norm_name, std_category  # noqa: E402

BASE = os.path.join(os.path.dirname(__file__), "..")
ROOT = os.path.join(BASE, "..")
OUT = os.path.join(BASE, "out", "dataset")

JENIS = [(r"peraturan\s+menteri\s+keuangan|\bpmk\b", "PMK"), (r"peraturan\s+gubernur|\bpergub\b", "Pergub"),
         (r"peraturan\s+wali\s*kota|\bperwali\b|\bperwal\b|\bperwako\b", "Perwali"),
         (r"peraturan\s+bupati|\bperbup\b", "Perbup"), (r"peraturan\s+daerah|\bperda\b", "Perda")]


def parse_peraturan(s):
    """'Perbup Kab. Pasaman No. 10 Tahun 2023 tentang ...' -> (jenis, daerah, nomor, tahun)."""
    s = str(s)
    head = re.split(r"\btentang\b", s, maxsplit=1, flags=re.I)[0]
    jenis = next((j for rx, j in JENIS if re.search(rx, head, re.I)), "")
    m = re.search(r"\b(?:No\.?|Nomor)\s*([0-9]+)", head, re.I)
    nomor = m.group(1) if m else ""
    m = re.search(r"\bTahun\s*((?:19|20)\d\d)", head, re.I) or re.search(r"/((?:19|20)\d\d)\b", head)
    tahun = m.group(1) if m else ""
    m = re.search(r"\b(Kab(?:upaten)?\.?|Kota|Prov(?:insi)?\.?)\s+(.+?)\s+(?:No\.?|Nomor)\b", head, re.I)
    if m:
        lvl = m.group(1).lower()
        lvl = "Kota" if lvl.startswith("kota") else ("Provinsi" if lvl.startswith("prov") else "Kabupaten")
        daerah = f"{lvl} {m.group(2).strip()}"
    else:  # "Peraturan Bupati Rembang Nomor 13 Tahun 2011"
        m = re.search(r"(?:Bupati|Wali\s*kota|Walikota|Gubernur|Daerah)\s+(.+?)\s+(?:No\.?|Nomor)\b", head, re.I)
        daerah = m.group(1).strip() if m and not re.search(r"\(", m.group(1)) else ""
    return jenis, daerah, nomor, tahun


ALIAS = {"kutai kertanegara": "kutai kartanegara", "pali": "penukal abab lematang ilir", "kotabaru": "kota baru",
         "fak fak": "fakfak", "tolitoli": "toli toli", "pangkep": "pangkajene dan kepulauan", "diy": "yogyakarta",
         "di yogyakarta": "yogyakarta", "daerah istimewa yogyakarta": "yogyakarta", "dki jakarta": "jakarta"}


def norm_daerah(d):
    """Nama daerah tanpa kata tingkat di depan ('Kabupaten Kota Baru' -> 'kota baru')."""
    d = re.sub(r"[^a-z ]", " ", str(d).lower().replace("-", " "))
    d = re.sub(r"\s+", " ", d).strip()
    d = re.sub(r"^(kabupaten|kab|kota|provinsi|prov)\b\s*", "", d).strip()
    return ALIAS.get(d, d)


def load_wilayah():
    P = pd.read_csv(os.path.join(BASE, "config", "wilayah", "provinces.csv"), header=None, names=["id", "nama"])
    R = pd.read_csv(os.path.join(BASE, "config", "wilayah", "regencies.csv"), header=None, names=["id", "prov", "nama"])
    prov = dict(zip(P.id, P.nama.str.title()))
    kab = {}
    for r in R.itertuples():
        lvl = "Kota" if r.nama.startswith("KOTA") else "Kabupaten"
        kab[(lvl, norm_daerah(r.nama))] = (f"{lvl} {r.nama.split(' ', 1)[1].title()}", prov[r.prov])
    provs = {norm_daerah(v): v for v in prov.values()}
    provs = {re.sub(r"^(dki|di) ", "", k): v for k, v in provs.items()}
    provs.update({"babel": "Kepulauan Bangka Belitung"})
    return kab, provs


def resolve_wilayah(daerah, kab, provs):
    """-> (kab_kota, provinsi). Daerah tingkat provinsi: kab_kota kosong."""
    lvl = "Kota" if daerah.lower().startswith("kota") else ("Provinsi" if daerah.lower().startswith("prov") else "Kabupaten")
    n = norm_daerah(daerah)
    if lvl == "Provinsi":
        return "", provs.get(n, daerah.split(" ", 1)[-1].title())
    for key in [(lvl, n), ("Kabupaten", n), ("Kota", n)]:
        if key in kab:
            return kab[key]
    # ejaan berbeda ("Fak-Fak", "Pangkajene Kepulauan") -> cocokkan tanpa spasi
    flat = n.replace(" ", "")
    for (l2, k2), v in kab.items():
        if k2.replace(" ", "") == flat and (l2 == lvl or lvl == "Kabupaten"):
            return v
    import difflib  # ejaan dekat ("Tulungagung"/"Tulung Agung", "Kertanegara"/"Kartanegara")
    same = {k2: v for (l2, k2), v in kab.items() if l2 == lvl}
    m = difflib.get_close_matches(n, list(same), n=1, cutoff=0.85)
    return same[m[0]] if m else (daerah, "")


RS_RX = re.compile(r"(Rumah\s+Sakit|RSUD|RSU|RSJ|RSIA|RSKD|RS)\b(.*)$", re.I)
RS_CUT = re.compile(r"\s+(?:sebagai\s+badan|yang\s+menerapkan|pada\s+kementerian|pada\s+kepolisian|pada\s+dinas|dinas\s+kesehatan|"
                    r"dan\s+(?:pusat|unit|puskesmas|laboratorium)|selain\s+tarif|di\s+lingkungan)\b.*$", re.I)


def rs_from_judul(judul, daerah):
    """Nama RS dari judul peraturan. 'di Kabupaten X' / 'Kelas B' tanpa nama -> RSUD <daerah> (generik)."""
    j = re.sub(r"\s+", " ", str(judul)).strip()
    m = RS_RX.search(j)
    if not m:
        return f"RSUD {daerah}".strip(), True
    name = RS_CUT.sub("", m.group(0)).strip(" ,.")
    # "Rumah Sakit BLUD pada Rumah Sakit Umum Daerah X" -> bagian sesudah 'pada' terakhir
    parts = re.split(r"\s+pada\s+(?=(?:Rumah\s+Sakit|RSU|RSJ|RS\b|Unit|UPT))", name, flags=re.I)
    name = parts[-1]
    name = re.sub(r"^(?:Unit\s+Pelaksana\s+Teknis(?:\s+Daerah)?|UPTD?|Unit\s+Organisasi\s+Bersifat\s+Khusus)\s+", "",
                  name, flags=re.I)
    name = re.sub(r"\bRumah\s+Sakit\s+Umum\s+Daerah\b|\bRumah\s+Sakit\s+Daerah\b", "RSUD", name, flags=re.I)
    name = re.sub(r"\bRumah\s+Sakit\s+Umum\b", "RSU", name, flags=re.I)
    name = re.sub(r"\bRumah\s+Sakit\s+Jiwa\b", "RSJ", name, flags=re.I)
    name = re.sub(r"\bRumah\s+Sakit\b", "RS", name, flags=re.I)
    name = re.sub(r"\(\s*RSUD\s*\)", "", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip()
    # kapital rapi: kata kapital semua -> Title, kecuali singkatan RS/RSUD/dr
    name = " ".join(w if re.fullmatch(r"RS\w{0,3}|[A-Z]{1,3}\.?|II|III|IV", w) else
                    (w.title() if w.isupper() else w) for w in name.split())
    core = re.sub(r"\b(RSUD|RSU|RS|RSJ|Badan|Layanan|Umum|Daerah|Kelas|[A-D]|Non|Pendidikan|Di|Pada|Kabupaten|Kota|"
                  r"Provinsi|Milik|Pemerintah|Unit|Pelaksana|Teknis|Blud|Uptd|Dan|Lainnya)\b", "", name, flags=re.I)
    generic = len(re.sub(r"[^A-Za-z]", "", core)) < 3
    if generic:
        name = f"RSUD {daerah}".strip()
    return name, generic


def slug(s):
    return re.sub(r"[^A-Z0-9]+", "-", str(s).upper()).strip("-")


def main():
    os.makedirs(OUT, exist_ok=True)
    K = pd.read_csv(os.path.join(ROOT, "bpk_v3", "klasifikasi.csv"))
    K = K[K.folder == "buku_tarif/teks"]
    M = pd.read_csv(os.path.join(ROOT, "bpk_v3", "metadata.csv"))
    M["file"] = M.file.astype(str).str.replace("\\", "/", regex=False).str.split("/").str[-1]
    L = pd.read_csv(os.path.join(ROOT, "bpk_v3", "list.csv"))
    D = K[["file", "hal", "mutu"]].merge(M[["file", "nama", "judul", "detail_url", "pdf_url"]], on="file", how="left")
    D = D.merge(L[["detail_url", "jenis", "tahun", "kategori", "dicabut", "relasi_json"]], on="detail_url", how="left",
                suffixes=("", "_list"))
    kab, provs = load_wilayah()

    # --- dokumen (per peraturan; satu peraturan bisa beberapa file) ---------------------------------
    parsed = D.nama.map(parse_peraturan)
    D["jenis_p"], D["daerah"], D["nomor"], D["tahun_p"] = zip(*parsed)
    D["jenis"] = D.jenis.fillna(D.jenis_p)
    D["tahun"] = D.tahun.fillna(D.tahun_p).astype(str).str[:4]
    D.loc[D.jenis == "PMK", "daerah"] = "Pemerintah Pusat"
    wil = [resolve_wilayah(d, kab, provs) if j != "PMK" else ("", "") for d, j in zip(D.daerah, D.jenis)]
    D["kab_kota"], D["provinsi"] = zip(*wil)
    D["dokumen_id"] = [slug(f"{j}-{norm_daerah(d) if j != 'PMK' else ''}-{n}-{t}").replace("--", "-")
                       for j, d, n, t in zip(D.jenis, D.daerah, D.nomor, D.tahun)]
    D["perubahan"] = D.judul.fillna("").str.contains(r"^\s*perubahan", case=False)
    files = D.groupby("dokumen_id").file.apply(lambda s: " | ".join(sorted(s)))
    B = pd.read_csv(os.path.join(BASE, "out", "bpk", "bhp_pasal.csv"), dtype=str).fillna("").set_index("file")
    D["bhp_dokumen"] = D.file.map(B.bhp_auto)
    D["bhp_aturan"] = D.file.map(B.aturan)
    D["bhp_pengecualian_bagian"] = D.file.map(B.pengecualian_bagian)
    doc = D.drop_duplicates("dokumen_id").copy()
    doc["file"] = doc.dokumen_id.map(files)
    doc["n_file"] = doc.file.str.count(r"\|") + 1

    # --- relasi antarperaturan -------------------------------------------------------------------------
    # semua peraturan di daftar BPK (termasuk yang bukan buku tarif) supaya rantai perubahan tetap utuh
    Lp = L.nama.map(parse_peraturan)
    L["key"] = [(j, norm_daerah(d), n, t) for j, d, n, t in Lp]
    known = {k: u for k, u in zip(L.key, L.detail_url)}
    by_url = dict(zip(doc.detail_url, doc.dokumen_id))

    def find(text):
        j, d, n, t = parse_peraturan(text)
        nd = norm_daerah(d)
        cands = [k for k in known if k[0] == j and k[2] == n and k[3] == t]
        if len(cands) > 1 and nd:
            cands = [k for k in cands if nd and (nd in k[1] or k[1] in nd)] or cands
        return known[cands[0]] if len(cands) == 1 else None

    rel = []
    for r in L.itertuples():
        if not isinstance(r.relasi_json, str):
            continue
        for k, vs in json.loads(r.relasi_json).items():
            for v in vs:
                rel.append(dict(sumber_url=r.detail_url, relasi=k, target_teks=v, target_url=find(v)))
    Rl = pd.DataFrame(rel)
    # arahkan semua relasi ke bentuk "A digantikan/diubah oleh B"
    inv = {"Mencabut": "dicabut_oleh", "Mengubah": "diubah_oleh", "Mengubah sebagian": "diubah_oleh",
           "Dicabut dengan": "dicabut_oleh", "Diubah dengan": "diubah_oleh", "Diubah sebagian dengan": "diubah_oleh"}
    edges = []
    for r in Rl.itertuples():
        if r.relasi not in inv or not r.target_url:
            continue
        if r.relasi.startswith(("Mencabut", "Mengubah")):   # sumber mencabut/mengubah target
            lama, baru = r.target_url, r.sumber_url
        else:                                               # sumber dicabut/diubah oleh target
            lama, baru = r.sumber_url, r.target_url
        edges.append(dict(lama_url=lama, baru_url=baru, jenis_relasi=inv[r.relasi]))
    E = pd.DataFrame(edges).drop_duplicates()
    nama_url = dict(zip(L.detail_url, L.nama))
    E["lama_dokumen_id"] = E.lama_url.map(by_url)
    E["baru_dokumen_id"] = E.baru_url.map(by_url)
    E["lama_nama"] = E.lama_url.map(nama_url)
    E["baru_nama"] = E.baru_url.map(nama_url)
    E = E[E.lama_dokumen_id.notna() | E.baru_dokumen_id.notna()]
    st = {}
    for r in E.itertuples():
        if isinstance(r.lama_dokumen_id, str):
            cur = st.get(r.lama_dokumen_id, "")
            st[r.lama_dokumen_id] = "dicabut" if (r.jenis_relasi == "dicabut_oleh" or cur == "dicabut") else "diubah"
    doc["status_bpk"] = doc.dokumen_id.map(st).fillna("berlaku")
    doc.loc[doc.dicabut.eq("ya") & doc.status_bpk.eq("berlaku"), "status_bpk"] = "dicabut"
    doc["diganti_oleh"] = doc.dokumen_id.map(
        E.dropna(subset=["lama_dokumen_id"]).groupby("lama_dokumen_id").baru_nama.apply(lambda s: " | ".join(sorted(set(s.dropna())))))

    # --- rumah sakit ---------------------------------------------------------------------------------
    rs = [rs_from_judul(j, d if jn != "PMK" else "") for j, d, jn in zip(doc.judul, doc.daerah, doc.jenis)]
    doc["nama_rs"], doc["rs_generik"] = zip(*rs)
    doc.loc[(doc.jenis == "PMK") & doc.rs_generik, "nama_rs"] = "RS di lingkungan Kementerian Kesehatan (banyak RS)"

    def rs_key(name, kk, prov):
        # kunci RS: nama tanpa kata wilayah/kelas + wilayah, supaya 'RSUD Pulang Pisau' = 'RSUD Kabupaten Pulang Pisau'
        core = re.sub(r"\b(Kabupaten|Kab\.?|Kota|Provinsi|Prov\.?|Kelas\s+[A-D]|Non\s+Pendidikan|BLUD|Daerah)\b", " ",
                      name, flags=re.I)
        for w in str(kk).split()[1:] + str(prov).split():   # nama wilayah yang sudah masuk kunci
            core = re.sub(rf"\b{re.escape(w)}\b", " ", core, flags=re.I)
        core = re.sub(r"\bdr\.?\s*", "DR ", core, flags=re.I)
        return slug(f"{core}-{kk or prov}")
    doc["rs_id"] = [rs_key(n, kk, p) for n, kk, p in zip(doc.nama_rs, doc.kab_kota, doc.provinsi)]
    RS = (doc.groupby("rs_id").agg(nama_rs=("nama_rs", "first"), kab_kota=("kab_kota", "first"),
                                   provinsi=("provinsi", "first"), nama_generik=("rs_generik", "first"),
                                   n_dokumen=("dokumen_id", "nunique")).reset_index())
    DR = doc[["dokumen_id", "rs_id"]].assign(cakupan=doc.rs_generik.map({True: "RS daerah (nama RS tidak disebut di judul)",
                                                                         False: "RS disebut di judul"}))

    # --- tarif -------------------------------------------------------------------------------------
    T = pd.read_csv(os.path.join(BASE, "out", "bpk", "uji_parser_baris_bhp.csv.gz"), low_memory=False)
    T = T.rename(columns={"dokumen_id": "file"})
    T["dokumen_id"] = T.file.map(dict(zip(D.file, D.dokumen_id)))
    from to_standard import std_kelas
    T["kelas"] = T.kelas.fillna("Non-kelas").astype(str).str.strip()
    odd = T.kelas.str.match(r"(?i)^(kelas|klas|kls)\s*\S+$")
    T.loc[odd, "kelas"] = T.loc[odd, "kelas"].map(std_kelas)
    T["nama_norm"] = T.nama_asli.astype(str).map(norm_name)
    T["kategori_std"] = [std_category(k if isinstance(k, str) else "", n) for k, n in zip(T.kategori_asli, T.nama_norm)]
    T["flags"] = T["flags"].fillna("")
    dup = T.duplicated(["dokumen_id", "nama_norm", "kelas", "harga"], keep="first")
    T.loc[dup, "flags"] = (T.loc[dup, "flags"] + "|duplikat").str.strip("|")
    T["flag_qc"] = T["flags"].replace("", "ok").str.replace("|", ";", regex=False)
    PROBLEM = {"nama_terpotong", "komponen_tidak_jumlah", "kolom_harga_tak_dikenal", "kelas_grup_tanpa_judul",
               "kelas_kolom_tanpa_judul", "harga_ambigu", "urutan_kelas_aneh"}
    T["qc_masalah"] = T["flags"].map(lambda f: bool(set(f.split("|")) & PROBLEM))
    T = T.sort_values(["dokumen_id", "file", "halaman"], kind="stable")
    T["tarif_id"] = T.dokumen_id + "-" + (T.groupby("dokumen_id").cumcount() + 1).map("{:06d}".format)
    T["tahun"] = T.dokumen_id.map(dict(zip(doc.dokumen_id, doc.tahun)))
    T["rs_id"] = T.dokumen_id.map(dict(zip(doc.dokumen_id, doc.rs_id)))
    T["status_bpk"] = T.dokumen_id.map(dict(zip(doc.dokumen_id, doc.status_bpk)))
    cols = ["tarif_id", "dokumen_id", "rs_id", "tahun", "status_bpk", "file", "halaman", "kategori_asli", "nama_asli",
            "nama_norm", "kategori_std", "kelas", "komponen", "harga", "termasuk_bhp", "sumber_bhp", "n_kolom_harga",
            "sumber_harga", "metode_ekstraksi", "flag_qc", "qc_masalah", "baris_mentah"]
    T[cols].to_csv(os.path.join(OUT, "tarif.csv.gz"), index=False)

    # urutan versi per RS: 1 = peraturan terbaru (tahun terbesar, lalu nomor terbesar)
    doc["_t"] = pd.to_numeric(doc.tahun, errors="coerce")
    doc["_n"] = pd.to_numeric(doc.nomor, errors="coerce")
    doc = doc.sort_values(["rs_id", "_t", "_n"], ascending=[True, False, False])
    doc["urutan_versi_rs"] = doc.groupby("rs_id").cumcount() + 1
    doc["n_versi_rs"] = doc.groupby("rs_id").dokumen_id.transform("size")
    q = T.groupby("dokumen_id").agg(n_baris=("tarif_id", "size"),
                                    pct_ok=("flag_qc", lambda s: round((s == "ok").mean() * 100, 1)),
                                    pct_qc_masalah=("qc_masalah", lambda s: round(s.mean() * 100, 1)),
                                    pct_bhp_terbaca=("termasuk_bhp", lambda s: round((s != "tidak_jelas").mean() * 100, 1)))
    doc = doc.join(q, on="dokumen_id")
    dcols = ["dokumen_id", "jenis", "nomor", "tahun", "daerah", "kab_kota", "provinsi", "judul", "nama", "kategori",
             "perubahan", "status_bpk", "diganti_oleh", "urutan_versi_rs", "n_versi_rs", "rs_id", "nama_rs", "rs_generik", "bhp_dokumen", "bhp_aturan",
             "bhp_pengecualian_bagian", "n_baris", "pct_ok", "pct_qc_masalah", "pct_bhp_terbaca", "n_file", "file", "detail_url", "pdf_url"]
    doc = doc[dcols].sort_values(["provinsi", "kab_kota", "tahun"])
    doc.to_csv(os.path.join(OUT, "dokumen.csv"), index=False)
    RS.to_csv(os.path.join(OUT, "rumah_sakit.csv"), index=False)
    DR.to_csv(os.path.join(OUT, "dokumen_rs.csv"), index=False)
    E.to_csv(os.path.join(OUT, "relasi.csv"), index=False)
    with pd.ExcelWriter(os.path.join(OUT, "tarif_standar_bpk.xlsx")) as xw:
        pd.DataFrame({"keterangan": [
            "Dataset tarif RS dari buku tarif BPK (peraturan.bpk.go.id), format long.",
            "Sheet tarif disimpan terpisah di tarif.csv.gz (terlalu besar untuk dibuka nyaman di Excel).",
            "status_bpk: berlaku / diubah / dicabut menurut relasi di BPK (bukan kepastian hukum).",
            "urutan_versi_rs: 1 = peraturan terbaru untuk RS itu di dataset; peraturan perubahan bisa hanya memuat sebagian tarif.",
            "rs_generik = True: judul tidak menyebut nama RS; dipakai 'RSUD <daerah>'.",
            "qc_masalah (tarif.csv.gz): True bila baris punya flag masalah; flag lain (nama_dari_judul, dari_kolom_kelas, duplikat) hanya informatif.",
            "bhp_dokumen: status BHP dari pasal (ya/tidak/tidak_jelas); status per baris ada di tarif.csv.gz.",
            "Wilayah: daftar Kemendagri 34 provinsi (edwardsamuel/Wilayah-Administratif-Indonesia)."]}
        ).to_excel(xw, sheet_name="keterangan", index=False)
        doc.to_excel(xw, sheet_name="dokumen", index=False)
        RS.to_excel(xw, sheet_name="rumah_sakit", index=False)
        DR.to_excel(xw, sheet_name="dokumen_rs", index=False)
        E.to_excel(xw, sheet_name="relasi", index=False)
    print(f"dokumen {len(doc)} | file {doc.n_file.sum()} | RS {len(RS)} (generik {RS.nama_generik.sum()}) | "
          f"tarif {len(T):,} | relasi tertaut {len(E)}")
    print("status_bpk:", doc.status_bpk.value_counts().to_dict())
    print("jenis:", doc.jenis.value_counts().to_dict())
    print("provinsi kosong:", (doc.provinsi == "").sum(), "| provinsi unik:", doc.provinsi.nunique())


if __name__ == "__main__":
    main()
