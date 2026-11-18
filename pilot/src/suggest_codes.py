"""Usulkan 5 kode standar teratas untuk setiap nama di sheet `pemetaan`.

Target per kategori standar:
  Laboratorium                     -> LOINC (Universal Lab Orders Value Set, 1.519 tes)
  Radiologi, Tindakan Lain, Gigi,
  Kebidanan, Mata/THT/Kulit, Rehab -> ICD-9-CM Volume 3 v32 (3.882 prosedur, CMS)
  Akomodasi & Visite, Rawat Jalan  -> Lokal (tanpa kode standar)

Skor = 0,7 x cosine embedding multilingual-e5-small + 0,3 x cosine TF-IDF karakter
(nama Indonesia diberi varian "terjemahan" istilah medis sebelum dicocokkan).
Hasilnya USULAN: kolom `kode` tetap kosong sampai dipilih manusia (PMIK).

Pemakaian: E5_DIR=<folder model> python -I pilot/src/suggest_codes.py
"""
import csv
import os
import re
import sys

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, os.path.dirname(__file__))
from align import e5_embed  # noqa: E402

BASE = os.path.join(os.path.dirname(__file__), "..")
ROOT = os.path.join(BASE, "..")
OUT = os.path.join(BASE, "out")
csv.field_size_limit(10 ** 8)

TARGET = {"Laboratorium": "LOINC", "Radiologi": "ICD-9-CM", "Tindakan Lain": "ICD-9-CM", "Gigi": "ICD-9-CM",
          "Kebidanan": "ICD-9-CM", "Mata/THT/Kulit": "ICD-9-CM", "Rehab Medik": "ICD-9-CM",
          "Akomodasi & Visite": "Lokal", "Rawat Jalan & Darurat": "Lokal"}

# istilah Indonesia -> Inggris (kata utuh), lalu akhiran
WORDS = {
    "operasi": "operation", "pemasangan": "insertion", "pasang": "insertion", "lepas": "removal",
    "pelepasan": "removal", "pengangkatan": "removal", "angkat": "removal", "insisi": "incision",
    "eksisi": "excision", "ekstirpasi": "excision", "eksterpasi": "excision", "biopsi": "biopsy",
    "jahit": "suture", "jahitan": "suture", "hecting": "suture", "repair": "repair", "rekonstruksi": "reconstruction",
    "reposisi": "reduction", "fraktur": "fracture", "tulang": "bone", "kulit": "skin", "mata": "eye",
    "telinga": "ear", "hidung": "nose", "tenggorok": "throat", "gigi": "tooth", "rahim": "uterus",
    "kandung": "bladder", "kemih": "urinary", "ginjal": "kidney", "hati": "liver", "paru": "lung",
    "jantung": "heart", "usus": "intestine", "lambung": "stomach", "payudara": "breast", "kepala": "head",
    "leher": "neck", "dada": "chest", "perut": "abdomen", "tangan": "hand", "kaki": "foot", "jari": "finger",
    "lutut": "knee", "panggul": "pelvis", "tumor": "tumor", "kista": "cyst", "abses": "abscess",
    "luka": "wound", "bakar": "burn", "kateter": "catheter", "cateter": "catheter", "infus": "infusion",
    "transfusi": "transfusion", "darah": "blood", "suntik": "injection", "injeksi": "injection",
    "foto": "x-ray", "photo": "x-ray", "rontgen": "x-ray", "ultrasonografi": "ultrasound diagnostic",
    "ct": "computerized axial tomography", "mri": "magnetic resonance imaging", "kontras": "contrast",
    "persalinan": "delivery", "partus": "delivery", "kuretase": "curettage", "kuret": "curettage",
    "curretage": "curettage", "sectio": "cesarean section", "seksio": "cesarean section", "sesarea": "cesarean",
    "caesaria": "cesarean", "caesar": "cesarean", "khitan": "circumcision", "sirkumsisi": "circumcision",
    "cirkumsisi": "circumcision", "pencabutan": "extraction", "cabut": "extraction", "tambalan": "filling",
    "penambalan": "filling", "terapi": "therapy", "fisioterapi": "physical therapy", "punksi": "puncture",
    "pungsi": "puncture", "aspirasi": "aspiration", "drainase": "drainage", "irigasi": "irrigation",
    "pemeriksaan": "examination", "tes": "test", "uji": "test", "kanan": "", "kiri": "", "dan": "and",
    "atau": "or", "dengan": "with", "tanpa": "without", "posisi": "view", "lengkap": "complete",
    "sederhana": "simple", "kecil": "minor", "besar": "major", "dewasa": "adult", "anak": "child",
    "gula": "glucose", "puasa": "fasting", "sewaktu": "random", "kolesterol": "cholesterol",
    "trigliserida": "triglyceride", "asam urat": "uric acid", "urin": "urine", "urine": "urine",
    "feses": "stool", "tinja": "stool", "dahak": "sputum", "hemoglobin": "hemoglobin", "trombosit": "platelets",
    "leukosit": "leukocytes", "eritrosit": "erythrocytes", "golongan": "group", "kultur": "culture",
}
SUFFIX = [("ektomi", "ectomy"), ("ektomy", "ectomy"), ("otomi", "otomy"), ("tomi", "tomy"), ("ostomi", "ostomy"),
          ("plasti", "plasty"), ("plasty", "plasty"), ("skopi", "scopy"), ("grafi", "graphy"), ("sintesis", "centesis"),
          ("sentesis", "centesis"), ("rafi", "rrhaphy"), ("pexi", "pexy"), ("peksi", "pexy")]


def translate(s):
    s = s.lower()
    for k, v in sorted(WORDS.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(rf"\b{re.escape(k)}\b", v, s)
    out = []
    for w in s.split():
        for a, b in SUFFIX:
            if w.endswith(a):
                w = w[: -len(a)] + b
                break
        out.append(w.replace("k", "c") if w.endswith(("ectomy", "otomy", "scopy")) else w)
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def load_targets():
    loinc_all = {r["LOINC_NUM"]: r for r in csv.DictReader(open(f"{ROOT}/Loinc_2.83/LoincTable/Loinc.csv", encoding="utf-8"))}
    uni = list(csv.DictReader(open(f"{ROOT}/Loinc_2.83/AccessoryFiles/LoincUniversalLabOrdersValueSet/LoincUniversalLabOrdersValueSet.csv", encoding="utf-8")))
    loinc = pd.DataFrame([dict(kode=r["LOINC_NUM"], nama=r["LONG_COMMON_NAME"],
                               teks=f'{r["LONG_COMMON_NAME"]} {loinc_all.get(r["LOINC_NUM"], {}).get("COMPONENT", "")} '
                                    f'{loinc_all.get(r["LOINC_NUM"], {}).get("SHORTNAME", "")}') for r in uni])
    rows = []
    for line in open(f"{BASE}/ref/icd9cm/CMS32_DESC_LONG_SG.txt", encoding="latin-1"):
        code, desc = line.rstrip("\n").split(" ", 1)
        code = code[:2] + "." + code[2:] if len(code) > 2 else code
        rows.append(dict(kode=code, nama=desc.strip(), teks=desc.strip()))
    return {"LOINC": loinc, "ICD-9-CM": pd.DataFrame(rows)}


def main():
    path = f"{OUT}/tarif_standar_pilot.xlsx"
    sheets = pd.read_excel(path, sheet_name=None)
    pem = sheets["pemetaan"].copy()
    pem["kode_sistem"] = pem.kategori_std.map(TARGET).fillna("ICD-9-CM")
    pem["query"] = [f"{n} {translate(n)}" for n in pem.nama_norm]
    T = load_targets()
    cand_col, top_col, score_col = [""] * len(pem), [""] * len(pem), [np.nan] * len(pem)
    for sysname, tgt in T.items():
        m = pem.kode_sistem == sysname
        Q = pem[m]
        if not len(Q):
            continue
        Eq = e5_embed(list(Q["query"]))
        Et = e5_embed(list(tgt.teks))
        s_e5 = Eq @ Et.T
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True).fit(list(tgt.teks) + list(Q["query"]))
        s_tf = (vec.transform(Q["query"]) @ vec.transform(tgt.teks).T).toarray()
        S = 0.7 * s_e5 + 0.3 * s_tf
        for row, i in enumerate(Q.index):
            top = np.argsort(-S[row])[:5]
            cand_col[i] = " ;; ".join(f"{tgt.kode.iloc[j]} | {tgt.nama.iloc[j]} | {S[row, j]:.2f}" for j in top)
            top_col[i] = f"{tgt.kode.iloc[top[0]]} | {tgt.nama.iloc[top[0]]}"
            score_col[i] = round(float(S[row, top[0]]), 3)
        print(f"{sysname}: {m.sum()} nama -> {len(tgt)} kode")
    pem["kandidat_top5"] = cand_col
    pem["usulan_top1"] = top_col
    pem["skor"] = score_col
    pem.loc[pem.kode_sistem == "Lokal", "status"] = "lokal_tanpa_kode"
    pem.loc[pem.kode_sistem != "Lokal", "status"] = "usulan"
    pem = pem.drop(columns=["query"])
    cols = ["nama_norm", "contoh_nama_asli", "kategori_std", "jumlah_dokumen", "jumlah_baris", "kode_sistem",
            "usulan_top1", "skor", "kandidat_top5", "kode", "nama_kode", "status", "reviewer", "catatan"]
    sheets["pemetaan"] = pem[cols]
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                w = max(len(str(c.value or "")) for c in list(col)[:300])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 60)
    pem[cols].to_csv(f"{OUT}/pemetaan_usulan.csv", index=False)
    print(pem.kode_sistem.value_counts().to_dict())


if __name__ == "__main__":
    main()
