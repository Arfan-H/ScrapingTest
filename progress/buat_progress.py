"""Buat progress/PROGRESS_proyek.xlsx (status proyek, tugas, angka kunci, riwayat, saran lanjutan, risiko).

Isi ditulis di skrip ini supaya mudah diperbarui: ubah daftar di bawah, lalu jalankan
    python -I progress/buat_progress.py
Status per 2026-11-26. Tidak memuat isi sampel gold set v3 (penilaian belum selesai).
"""
import os

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
TANGGAL = "2026-11-26"

TAHAPAN = [
    # tahap, tujuan/RQ, status, persen, bukti, catatan
    ("A. Pengumpulan data", "Resource", "Selesai", 100,
     "bpk_v3/ (514 PDF, 505 peraturan)", "JDIH BPK 2001-2026; 342-343 RS, 34 provinsi; status berlaku/diubah/dicabut dan urutan versi per RS."),
    ("B. Ekstraksi & dataset tarif", "RQ1 / Resource", "Selesai (parser dibekukan)", 100,
     "pilot/src/to_standard.py @ cb968f4; pilot/out/dataset/tarif.csv.gz @ cd71555", "479.733 baris format panjang; OCR ulang untuk halaman scan; parser tidak diubah lagi sebelum gold set dinilai."),
    ("C. Verifikasi & kontrol mutu otomatis", "RQ1", "Selesai", 100,
     "pilot/out/dataset/verifikasi_harga.csv", "99,9% harga cocok dengan teks baris PDF (451 tidak cocok); ~15% baris bertanda qc_masalah. Ini konsistensi teks, BUKAN akurasi terhadap gambar PDF."),
    ("D. Evaluasi akurasi ekstraksi (gold set)", "RQ1", "Berjalan: menunggu penilaian", 45,
     "pilot/eval/gold/ (v3), tag gold-v3-prereg", "Desain v3 + pra-registrasi selesai dan dikunci (tag dibuat 2026-11-23). Penilaian penilai 1 dan 2 belum dimulai. Unggah pra-registrasi ke OSF/Zenodo belum."),
    ("E. Pemetaan kode ICD-9-CM / LOINC", "RQ2", "Berjalan: usulan otomatis saja", 35,
     "pilot/out/dataset/pemetaan_kode.csv.gz", "169.803 nama unik diberi usulan (e5 + TF-IDF). Belum ada validasi PMIK/analis lab; evaluasi silver n=14-15 tidak bisa dikutip."),
    ("F. Analisis variasi tarif", "RQ3", "Awal (deskriptif)", 25,
     "pilot/out/analisis/LAPORAN_variasi_awal.md", "826 grup nama x kelas, 330 RS; median p90/p10 = 4,36. Belum: kelompok nama + judul tabel, penyesuaian IHK, model campuran, kovariat RS."),
    ("G. Knowledge graph", "RQ4", "Pilot saja", 15,
     "pilot/out/graf_pilot.graphml, graf.graphml", "Model graf diuji pada 9 dokumen. Belum dibangun untuk 505 peraturan; belum ada evaluasi pasangan layanan antar-RS."),
    ("H. Literatur & penulisan", "Semua", "Berjalan", 15,
     "literatur/CLAUDE.md", "Peta tema, kata kunci, matriks metode. Rujukan 'ditemukan, belum dibaca penuh'. Draf paper belum."),
    ("I. Rilis dataset & lisensi", "Resource", "Belum", 10,
     "Loinc_2.83/NOTICE_LOINC.md", "Repo privat. Belum: datasheet, kamus data, lisensi data, DOI, keputusan soal tabel LOINC."),
    ("J. Parser Permenkes (proyek turunan)", "Perluasan", "Rencana", 5,
     "spesifikasi .md (di percakapan 2026-11-26)", "Kerangka CLAUDE.md untuk parser Permenkes -> Excel sudah ada; perlu satu PDF contoh untuk menyesuaikan aturan INA-CBG."),
]

TUGAS = [
    # id, tahap, tugas, status, PIC, prioritas, keluaran/bukti, catatan
    ("A1", "A", "Unduh 514 PDF tarif dari JDIH BPK + metadata", "Selesai", "Claude", "-", "bpk_v3/", ""),
    ("A2", "A", "Pilah buku tarif (teks/OCR) vs dokumen lain", "Selesai", "Claude", "-", "commit 902253d", ""),
    ("B1", "B", "Parser tata letak + OCR ulang + 12 putaran perbaikan", "Selesai", "Claude", "-", "commit cb968f4", "Cek visual v3->v10: 13 -> 3-4 salah tak bertanda (bias optimistis)."),
    ("B2", "B", "Bekukan parser sebelum evaluasi", "Selesai", "Claude", "-", "tag gold-v3-prereg", ""),
    ("C1", "C", "Verifikasi harga terhadap baris PDF sumber", "Selesai", "Claude", "-", "verifikasi_harga.csv", "451 baris tidak cocok ditandai."),
    ("C2", "C", "Status BHP dari pasal peraturan", "Selesai", "Claude", "-", "commit 0f22100", "~63% baris BHP 'tidak jelas'."),
    ("D1", "D", "Desain gold set v3 (presisi + cakupan, kontrol, 2 penilai)", "Selesai", "Claude", "-", "pilot/eval/buat_gold_ekstraksi.py", "v1, v2 digantikan (lihat folder *_tidak_dipakai)."),
    ("D2", "D", "Skrip skor + simulasi estimator + pra-registrasi", "Selesai", "Claude", "-", "nilai_gold_ekstraksi.py, PRAREGISTRASI_gold_v3.md", "Makro per dokumen; simulasi: bias < 0,1 pp, cakupan CI 88-90%."),
    ("D3", "D", "Buat dan push tag gold-v3-prereg", "Selesai", "Anda", "-", "refs/tags/gold-v3-prereg -> f70fac9", "Push tag dari sesi Claude diblokir (403); dibuat dari komputer Anda."),
    ("D4", "D", "Unggah PRAREGISTRASI_gold_v3.md ke OSF/Zenodo", "Belum", "Anda", "Tinggi", "tautan registrasi", "Cap waktu di luar repo."),
    ("D5", "D", "Cek SHA-256 gold_ekstraksi_v3.xlsx sebelum diisi", "Belum", "Anda", "Tinggi", "680afeff...2038", ""),
    ("D6", "D", "Uji coba 10-15 butir, perjelas petunjuk bila perlu", "Belum", "Anda", "Tinggi", "Riwayat petunjuk", "Bila aturan diubah: catat versi, nilai ulang butir uji coba."),
    ("D7", "D", "Penilaian penuh penilai pertama (360 + 119 butir)", "Belum", "Anda", "Tinggi", "gold_ekstraksi_v3 terisi", "~5-6 jam, boleh dicicil."),
    ("D8", "D", "Cari penilai kedua yang naif dan nilai file _penilai2", "Belum", "Penilai kedua", "Tinggi", "gold_ekstraksi_v3_penilai2 terisi", "153 + 30 butir; belum pernah melihat kode/laporan."),
    ("D9", "D", "Hitung skor, analisis galat, laporan RQ1", "Belum", "Claude", "Tinggi", "hasil_*.md", "Setelah D7 (dan D8)."),
    ("E1", "E", "Usulan kode otomatis seluruh nama unik", "Selesai", "Claude", "-", "pemetaan_kode.csv.gz", ""),
    ("E2", "E", "Desain gold set pemetaan kode (bertingkat ICD/LOINC/Lokal)", "Belum", "Claude", "Tinggi", "", "Disiplin sama dengan gold ekstraksi: held-out, pra-registrasi."),
    ("E3", "E", "Penilaian kode oleh PMIK (ICD-9-CM) dan analis lab (LOINC)", "Belum", "PMIK / Analis lab", "Tinggi", "", "Butuh ketersediaan ahli."),
    ("E4", "E", "Bandingkan baseline: TF-IDF, e5, e5+kamus, reranker LLM, fine-tuning", "Belum", "Claude", "Sedang", "", "Reranker LLM hanya dinilai dengan gold manusia (bukan silver)."),
    ("F1", "F", "Analisis variasi awal (nama persis)", "Selesai", "Claude", "-", "LAPORAN_variasi_awal.md", "Label 'awal, jangan dikutip'."),
    ("F2", "F", "Kelompok layanan = nama + judul tabel (kategori_asli), diberi versi", "Belum", "Claude", "Tinggi", "", "Didahulukan dari IHK (mengubah semua angka)."),
    ("F3", "F", "Penyesuaian IHK kesehatan BPS ke tahun dasar", "Belum", "Claude", "Sedang", "", ""),
    ("F4", "F", "Kovariat RS: kelas RS, BLUD, jumlah TT, wilayah", "Belum", "Anda / Claude", "Sedang", "", "Sumber: RS Online/SIRS Kemenkes, BPS."),
    ("F5", "F", "Model campuran log-harga", "Belum", "Claude", "Sedang", "", "Efek acak layanan & RS; efek tetap tahun, kelas, tipe RS, wilayah, BHP."),
    ("G1", "G", "Bangun graf untuk 505 peraturan", "Belum", "Claude", "Rendah", "", "Setelah kelompok layanan dan kode tervalidasi."),
    ("G2", "G", "Gold set pasangan layanan antar-RS untuk RQ4", "Belum", "Claude / PMIK", "Rendah", "", ""),
    ("H1", "H", "Baca penuh rujukan inti per tema", "Belum", "Anda", "Sedang", "literatur/", ""),
    ("H2", "H", "Draf paper 1 (dataset + akurasi ekstraksi)", "Belum", "Anda / Claude", "Sedang", "", "Setelah D9."),
    ("I1", "I", "Datasheet + kamus data + lisensi + DOI", "Belum", "Anda / Claude", "Sedang", "", "Putuskan juga apakah tabel LOINC ikut dirilis."),
    ("J1", "J", "Parser Permenkes -> Excel (mulai dari satu PDF contoh)", "Belum", "Anda / Claude", "Rendah", "", "Berguna untuk pembanding tarif JKN."),
]

ANGKA = [
    ("Peraturan / file PDF", "505 / 514", "dokumen.csv", ""),
    ("Rumah sakit / provinsi", "342-343 / 34", "rumah_sakit.csv", ""),
    ("Baris tarif", "479.733", "tarif.csv.gz @ cd71555", "SHA-256 febb4601...ddfa"),
    ("Harga cocok dengan teks baris PDF", "99,9% (451 tidak cocok)", "verifikasi_harga.csv", "Konsistensi teks, bukan akurasi."),
    ("Baris bertanda qc_masalah", "~14,9%", "tarif.csv.gz", ""),
    ("Cek visual 40 baris (v10): salah tak bertanda", "3-4 dari 40", "pilot/eval/cek_manual_40_v10.csv", "Bias optimistis: tidak untuk dikutip."),
    ("Nama layanan unik", "169.803", "pemetaan_kode.csv.gz", "Nama di >= 2 RS mencakup 42,5% baris."),
    ("Perutean kode (nama unik)", "ICD-9-CM 77% / LOINC 12% / Lokal 11%", "pemetaan_kode.csv.gz", "Heuristik per kategori."),
    ("Keyakinan usulan kode", "tinggi 22.454 / sedang 49.609 / rendah 78.792", "pemetaan_kode.csv.gz", "Belum divalidasi."),
    ("Gold set v3: dokumen / butir", "60 dok; 327 presisi + 33 kontrol; 119 cakupan", "PRAREGISTRASI_gold_v3.md", "Penilai 2: 120 + 33 + 30."),
    ("Gold set v3: pool cadangan 'sesudah'", "199 dokumen", "pool_cadangan_sesudah.txt", "Tidak boleh dibuka per dokumen."),
    ("Simulasi estimator utama (makro)", "bias < 0,1 pp; cakupan CI 88-90%", "simulasi_estimator_gold.py", "Kish ~30 dokumen efektif."),
    ("Variasi tarif awal", "826 grup; median p90/p10 4,36", "LAPORAN_variasi_awal.md", "Nama persis; harga nominal."),
    ("Kenaikan tarif antar-versi", "median 3,1%/tahun (63 RS)", "perubahan_versi.csv", "Bias seleksi: RS dengan >= 2 versi."),
]

RIWAYAT = [
    ("2026-11-18", "29b06f2..21eb259", "Pilot Rembang & Cimacan: tabel standar, graf, penjelajah graf, usulan kode ICD-9-CM/LOINC"),
    ("2026-11-19", "0b01a44..ca8c28d", "Konverter banyak dokumen; data BPK (4 batch); status BHP; graf 9 dokumen; variasi awal pilot"),
    ("2026-11-19", "b41aac9", "Uji parser skala besar pada 514 buku tarif"),
    ("2026-11-20", "6426e5e", "Dataset tarif standar BPK: 505 peraturan, 343 RS, 437.499 baris"),
    ("2026-11-20", "64d1690", "Verifikasi harga terhadap baris PDF: 99,89% cocok"),
    ("2026-11-20", "bab93d2..33984dc", "Pemetaan kode skala dataset BPK"),
    ("2026-11-20", "588acb0", "Cek visual pertama: 13 dari 40 salah tak bertanda"),
    ("2026-11-20", "b84b6cc..d9d407b", "OCR ulang halaman scan (RapidOCR) + pemilihan teks berbasis kosakata"),
    ("2026-11-20", "fcab50f..ad20895", "Putaran perbaikan parser 4-10, cek visual v4-v10"),
    ("2026-11-23", "2bc9f24", "literatur/CLAUDE.md: peta literatur dan matriks metode"),
    ("2026-11-23", "c604eb6..cb968f4", "Putaran 11-12: nomor baris OCR, S1/S2/S3/O2, lanjutan nama; parser dibekukan"),
    ("2026-11-23", "cd71555", "Rantai final: 479.733 baris"),
    ("2026-11-23", "664f297", "Gold set v1 (kemudian digantikan)"),
    ("2026-11-23", "6da0ef6", "Analisis variasi tarif awal (826 grup, 330 RS)"),
    ("2026-11-23", "7f160dc", "Gold set v2 (kemudian digantikan: kontrol bisa ditebak)"),
    ("2026-11-23", "cf898e3", "Gold set v3: kontrol buta, bobot cakupan sisi PDF, file penilai kedua"),
    ("2026-11-23", "f70fac9 (tag gold-v3-prereg)", "Pra-registrasi: estimator makro utama, aturan dikunci, pool cadangan, hash data"),
]

SARAN = [
    # no, saran, mengapa, cara, keluaran, RQ, prioritas, upaya
    (1, "Selesaikan gold set v3 dan laporkan RQ1",
     "Semua klaim mutu dataset bergantung pada angka ini; desain sudah dikunci.",
     "Uji coba 10-15 butir -> penilaian penuh -> penilai kedua -> skrip skor. Laporkan per strata + gabungan, CI apa adanya.",
     "Akurasi presisi & cakupan dengan CI; tabel per strata; ketelitian penilai.", "RQ1", "Tinggi", "5-6 jam penilai 1 + 2-3 jam penilai 2"),
    (2, "Taksonomi galat dan nilai flag QC sebagai detektor galat",
     "Menunjukkan bagian pipeline mana yang lemah dan apakah flag qc_masalah benar-benar berguna bagi pengguna data.",
     "Kodekan setiap galat gold (nama terpotong, kelas salah, komponen salah, digit, baris hilang); hitung presisi/recall flag_qc terhadap galat.",
     "Tabel jenis galat x strata; sensitivitas/spesifisitas flag QC.", "RQ1", "Tinggi", "1-2 hari setelah no. 1"),
    (3, "Gold set pemetaan kode dengan validasi ahli",
     "Pemetaan saat ini usulan otomatis; tanpa gold manusia tidak ada klaim RQ2.",
     "Sampel bertingkat nama unik (ICD-9-CM / LOINC / Lokal, frekuensi tinggi vs rendah); PMIK & analis lab menilai buta; pra-registrasi seperti gold ekstraksi; ukur juga 'tidak ada padanan'.",
     "hit@k dengan CI; proporsi tanpa padanan; kesepakatan ahli.", "RQ2", "Tinggi", "2-4 minggu (tergantung ahli)"),
    (4, "Bandingkan metode pemetaan lintas bahasa",
     "Kontribusi metodologis: seberapa jauh embedding multilingual, kamus istilah, LLM, dan fine-tuning membantu.",
     "Di atas gold no. 3: TF-IDF, e5 (query/passage), e5+kamus, reranker LLM, fine-tuning ringan; uji signifikansi berpasangan.",
     "Tabel perbandingan metode; analisis kesalahan.", "RQ2", "Sedang", "1-2 minggu"),
    (5, "Definisikan 'layanan setara' sebelum membandingkan harga",
     "Kasus 'Thorax' Rp 38.500 vs Rp 3,5 juta: nama pendek tanpa judul tabel menggabungkan rontgen dan CT.",
     "Kelompok = nama + judul tabel (kategori_asli), lalu sinonim lewat kode tervalidasi; beri versi.",
     "Definisi kelompok yang terdokumentasi; ukuran grup baru.", "RQ3", "Tinggi", "3-5 hari"),
    (6, "Model variasi tarif dengan kovariat RS dan waktu",
     "Rasio p90/p10 mentah mencampur beda waktu, kelas, dan wilayah.",
     "IHK kesehatan BPS; gabung kelas RS/BLUD/jumlah TT (RS Online/SIRS Kemenkes); model campuran log-harga dengan efek acak layanan dan RS.",
     "Dekomposisi variasi (antar-RS vs antar-wilayah vs waktu); faktor yang berasosiasi.", "RQ3", "Sedang", "2-3 minggu"),
    (7, "Bandingkan tarif RSUD dengan tarif JKN (INA-CBG / Permenkes)",
     "Pertanyaan kebijakan: seberapa jauh tarif umum RSUD berbeda dari tarif JKN untuk layanan serupa.",
     "Selesaikan parser Permenkes; petakan layanan RSUD ke grup/tarif JKN yang sebanding (hati-hati: paket CBG vs tarif per tindakan).",
     "Rasio tarif RSUD/JKN per jenis layanan dan kelas RS.", "Perluasan RQ3", "Sedang", "3-4 minggu"),
    (8, "Dinamika tarif dari waktu ke waktu",
     "Data punya urutan versi per RS (2001-2026).",
     "Panel RS dengan >= 2 versi; kenaikan riil setelah IHK; laporkan bias seleksi (RS yang memperbarui vs tidak).",
     "Laju kenaikan riil dan faktor penyerta.", "RQ3", "Rendah", "1-2 minggu"),
    (9, "Knowledge graph penuh dan uji manfaat graf untuk pencocokan",
     "RQ4 belum diuji; graf baru pilot 9 dokumen.",
     "Bangun graf 505 peraturan setelah no. 5 & 3; gold pasangan layanan antar-RS; bandingkan pencocokan nama/embedding vs embedding + fitur graf.",
     "Hasil RQ4; graf terbuka.", "RQ4", "Rendah", "3-4 minggu"),
    (10, "Rilis dataset sebagai resource",
      "Nilai utama proyek: dataset terbuka yang bisa ditelusuri ke halaman PDF.",
      "Datasheet for datasets, kamus data, lisensi data, versi + DOI (Zenodo), pernyataan batasan dan akurasi dari gold set; perhatikan lisensi LOINC.",
      "Dataset berversi dengan DOI; paper resource (mis. Scientific Data / Data in Brief, kandidat).", "Resource", "Sedang", "1-2 minggu setelah no. 1"),
    (11, "Uji generalisasi parser pada dokumen baru",
      "Bila parser diubah, perlu bukti perbaikan pada dokumen yang belum pernah dilihat.",
      "Ambil sampel baru dari 199 dokumen pool cadangan; ukur dengan prosedur yang sama; laporkan 'sebelum vs sesudah'.",
      "Akurasi sesudah perbaikan.", "RQ1", "Rendah (bila parser diubah)", "1 minggu + penilaian"),
]

RISIKO = [
    ("Penilai kedua yang naif tidak tersedia", "Ketelitian penilai dan kesepakatan tidak bisa diukur dengan bersih",
     "Cari mahasiswa/rekan di luar proyek; bila tidak ada, laporkan sebagai batasan."),
    ("PMIK / analis lab terlambat", "RQ2 tertunda", "Mulai dengan subset kecil; desain gold kode disiapkan lebih dulu."),
    ("CI terlalu sempit (Kish ~30 dokumen)", "Klaim presisi berlebihan", "Sajikan CI sebagai perkiraan kasar; laporkan per strata."),
    ("Paparan sampel (30/60 dokumen v3 pernah di v1/v2)", "Penilai pertama bisa terpengaruh",
     "Dilaporkan; uji sensitivitas tanpa 11 butir yang sama; penilai kedua naif."),
    ("Harga nominal lintas 25 tahun", "Variasi tercampur inflasi", "IHK kesehatan BPS; model dengan efek tahun."),
    ("Nama sama untuk layanan berbeda", "Variasi semu", "Kelompok nama + judul tabel; kode tervalidasi."),
    ("Lisensi LOINC", "Rilis data terhambat", "Rilis kode saja sesuai ketentuan; jangan sertakan tabel LOINC; sertakan pemberitahuan hak cipta."),
    ("Perubahan parser setelah evaluasi", "Hasil v3 tidak lagi mewakili data", "v3 = 'sebelum'; 'sesudah' dari pool cadangan."),
]

# ---------------------------------------------------------------------------------------------------------------
HEAD = PatternFill("solid", fgColor="1F4E78")
HFONT = Font(bold=True, color="FFFFFF")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
STATUS_COLORS = {"Selesai": "C6EFCE", "Berjalan": "FFEB9C", "Belum": "F2F2F2", "Rencana": "DDEBF7", "Terblokir": "FFC7CE"}


def table(ws, head, rows, widths, start=1):
    for j, h in enumerate(head, 1):
        c = ws.cell(start, j, h)
        c.fill, c.font, c.alignment, c.border = HEAD, HFONT, WRAP, BOX
    for i, r in enumerate(rows, start + 1):
        for j, v in enumerate(r, 1):
            c = ws.cell(i, j, v)
            c.alignment, c.border = WRAP, BOX
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(start + 1, 1)
    ws.auto_filter.ref = f"A{start}:{get_column_letter(len(head))}{start + len(rows)}"


def color_status(ws, col, first, last):
    for k, v in STATUS_COLORS.items():
        ws.conditional_formatting.add(f"{col}{first}:{col}{last}",
                                      CellIsRule(operator="beginsWith" if False else "equal", formula=[f'"{k}"'],
                                                 fill=PatternFill("solid", fgColor=v)))


def main():
    wb = Workbook()
    ws = wb.active
    ws.title = "Ringkasan"
    ws["A1"] = "Progress proyek: Dataset & graf tarif RSUD Indonesia dari peraturan daerah"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Status per {TANGGAL}. Sumber: repo branch claude/bts-i2c-2026-ieee-17zfxo, tag gold-v3-prereg (f70fac9)."
    total = round(sum(t[3] for t in TAHAPAN[:9]) / 9)
    ws["A3"] = f"Kemajuan rata-rata tahap A-I (bobot sama): {total}%"
    ws["A3"].font = Font(bold=True)
    table(ws, ["Tahap", "Tujuan / RQ", "Status", "% selesai", "Bukti", "Catatan"], TAHAPAN, [34, 14, 26, 10, 44, 80], start=5)
    for i in range(6, 6 + len(TAHAPAN)):
        ws[f"D{i}"].number_format = '0"%"'
    from openpyxl.formatting.rule import DataBarRule
    ws.conditional_formatting.add(f"D6:D{5 + len(TAHAPAN)}", DataBarRule(start_type="num", start_value=0, end_type="num",
                                                                          end_value=100, color="5B9BD5"))
    r = 7 + len(TAHAPAN)
    ws.cell(r, 1, "Tiga langkah berikut").font = Font(bold=True, size=12)
    nxt = ["1. Anda: unggah pra-registrasi ke OSF/Zenodo, cek hash xlsx, lalu uji coba 10-15 butir gold set v3.",
           "2. Anda + penilai kedua: penilaian penuh gold set v3 (penilai kedua sebaiknya orang di luar proyek).",
           "3. Claude (paralel, tidak menyentuh gold set): kelompok layanan nama + judul tabel, lalu IHK; siapkan desain gold set pemetaan kode untuk PMIK/analis lab."]
    for k, t in enumerate(nxt, r + 1):
        ws.cell(k, 1, t)
    ws.freeze_panes = None

    w2 = wb.create_sheet("Tugas")
    table(w2, ["ID", "Tahap", "Tugas", "Status", "PIC", "Prioritas", "Keluaran / bukti", "Catatan"], TUGAS,
          [6, 7, 58, 12, 18, 10, 40, 60])
    dv = DataValidation(type="list", formula1='"Selesai,Berjalan,Belum,Rencana,Terblokir"', allow_blank=False)
    w2.add_data_validation(dv)
    dv.add(f"D2:D{len(TUGAS) + 1}")
    color_status(w2, "D", 2, len(TUGAS) + 1)

    w3 = wb.create_sheet("Angka_kunci")
    table(w3, ["Ukuran", "Nilai", "Sumber", "Catatan"], ANGKA, [44, 40, 38, 50])

    w4 = wb.create_sheet("Riwayat")
    table(w4, ["Tanggal", "Commit", "Ringkasan"], RIWAYAT, [12, 26, 100])

    w5 = wb.create_sheet("Saran_lanjutan")
    table(w5, ["No", "Saran", "Mengapa", "Cara", "Keluaran", "RQ", "Prioritas", "Perkiraan upaya"], SARAN,
          [5, 34, 46, 60, 40, 12, 12, 22])

    w6 = wb.create_sheet("Risiko")
    table(w6, ["Risiko", "Dampak", "Mitigasi"], RISIKO, [40, 40, 70])

    out = os.path.join(HERE, "PROGRESS_proyek.xlsx")
    wb.save(out)
    print("->", out)


if __name__ == "__main__":
    main()
