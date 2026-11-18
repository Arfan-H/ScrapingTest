"""Tahap 2: normalisasi nama layanan + kategori standar."""
import re

import pandas as pd

ABBR = {
    "usg": "ultrasonografi",
    "ekg": "elektrokardiografi",
    "ecg": "elektrokardiografi",
    "eeg": "elektroensefalografi",
    "ct": "ct",
    "sc": "sectio caesarea",
    "iud": "alat kontrasepsi dalam rahim",
    "ngt": "nasogastric tube",
    "dc": "dower kateter",
    "hb": "hemoglobin",
    "gdp": "gula darah puasa",
    "gds": "gula darah sewaktu",
    "gd2pp": "gula darah 2 jam pp",
    "bta": "bakteri tahan asam",
    "sgot": "sgot ast",
    "sgpt": "sgpt alt",
    "omd": "oesophagus maag duodenum",
    "bno": "bno",
    "ivp": "intravenous pyelografi",
    "hiv": "hiv",
    "hbsag": "hbsag",
    "rontgen": "foto",
    "photo": "foto",
    "thorak": "thorax",
    "thoraks": "thorax",
    "toraks": "thorax",
    "pyshio": "physio",
    "fisio": "physio",
}

CAT_RULES = [
    ("Laboratorium", r"laborat|patologi|hematolog|kimia|serolog|imunolog|urin|feses|"
     r"darah|glukosa|kolesterol|hbsag|hiv|widal|dengue|ns1|igm|igg|elektrolit|"
     r"kreatinin|ureum|sgot|sgpt|bilirubin|albumin|trombosit|leukosit|bta|kultur"),
    ("Radiologi", r"radiolog|foto|ct.?scan|mri|ultrasonograf|usg|rontgen|thorax|"
     r"mammograf|panoramic|cranium|ap/lat|lateral|oblique|enema|pyelograf"),
    ("Rehab Medik", r"rehab|physio|terapi|okupasi|occupation|speech|speak|ergocycle|"
     r"uji fungsi|ortho|prothes|exercise|tens|infra red|swd|mwd"),
    ("Gigi", r"gigi|tambal|ekstraksi gigi|scaling|ortodon|endodon|pulp|crown|denture"),
    ("Akomodasi & Visite", r"rawat inap|kamar|akomodasi|visite|jasa dokter|makan|"
     r"\bkelas\b|vvip|vip|icu|hcu|nicu|picu|perinatologi"),
    ("Rawat Jalan & Darurat", r"rawat jalan|darurat|konsultasi|poliklinik|pendaftaran"),
    ("Kebidanan", r"kebidanan|persalinan|partus|curet|kuret|sectio|iud|spiral|"
     r"implant|vakum|forceps"),
    ("Mata/THT/Kulit", r"mata|katarak|lensa|refraksi|tonomet|telinga|hidung|"
     r"tht|estetik|peeling|acne|laser|kulit"),
]


def split_glued(s: str) -> str:
    # "EkstraksiBenda AsingHidung" -> "Ekstraksi Benda Asing Hidung"
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)


def norm_name(s: str) -> str:
    s = split_glued(str(s))
    s = s.lower()
    s = re.sub(r"[()\[\],;:+*]", " ", s)
    s = re.sub(r"\s*/\s*", " / ", s)
    s = re.sub(r"[^a-z0-9/<>\-. ]", " ", s)
    toks = [ABBR.get(t, t) for t in s.split()]
    return re.sub(r"\s+", " ", " ".join(toks)).strip(" .-")


KAT_ONLY = [
    ("Laboratorium", r"^pemeriksaan( sederhana| canggih| khusus| mikrobiologi| patologi anatomi)?$|laborat"),
    ("Radiologi", r"^(ct-scan|ultrasonografi|imaging|tarif tindakan radiologi)"),
]


def std_category(kategori: str, nama: str) -> str:
    for cat, pat in KAT_ONLY:
        if re.search(pat, str(kategori).strip().lower()):
            return cat
    text = f"{kategori} {nama}".lower()
    for cat, pat in CAT_RULES:
        if re.search(pat, text):
            return cat
    return "Tindakan Lain"


def load_items(paths):
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    df["kategori"] = df["kategori"].fillna("")
    df["kelas"] = df["kelas"].fillna("")
    df["nama_norm"] = df["nama_asli"].map(norm_name)
    df["kategori_std"] = [std_category(k, n) for k, n in zip(df.kategori, df.nama_norm)]
    return df
