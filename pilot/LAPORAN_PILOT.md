# Laporan Pilot: Graf Tarif RSUD dari Perbup (2 RSUD)

Pilot ini menguji apakah ide "knowledge graph tarif RSUD dari Perda/Perbup" bisa dikerjakan,
sebelum mengumpulkan 20–30 RSUD. Semua angka di bawah berasal dari skrip di `src/`
(jalankan ulang dengan `./run_pilot.sh`).

## 1. Data

| RS | Peraturan | Halaman | Baris tarif | Layanan unik |
|---|---|---|---|---|
| RSUD Kelas C Kab. Cianjur, Jabar (termasuk RSUD Cimacan) | Perbup Cianjur 3/2025 | 50 | 1.445 | 1.135 |
| RSUD dr. R. Soetrasno (Rembang, Jateng) | Perbup Rembang 16/2023 | 76 | 1.166 berharga + 567 anggota golongan | 1.186 |

Kedua PDF berupa teks, jadi tidak perlu OCR. URL ada di `sumber.csv`.
peraturan.bpk.go.id tidak bisa diunduh otomatis karena dilindungi Cloudflare,
jadi file diambil dari JDIH daerah atau situs RSUD.

## 2. Alur

1. `extract.py`: parser generik berbasis baris. Harga terakhir di baris dianggap total, dan judul tanpa angka dianggap kategori.
2. `golongan_rembang.py`: adapter khusus untuk format golongan tindakan (lihat temuan 2).
3. `normalize.py`: lowercase, memisah kata yang menempel, kamus singkatan, dan 9 kategori standar berbasis aturan.
4. `align.py`: Cianjur → Rembang dengan 4 metode: exact, TF-IDF karakter, e5 multilingual (zero-shot), dan hybrid (TF-IDF + e5 + bonus kategori). Harga sengaja tidak dipakai sebagai fitur.
5. `evaluate.py`: 60 layanan Cianjur diambil acak bertingkat per kategori, lalu dilabel.
6. `build_graph.py`: graf NetworkX (`out/graf_pilot.graphml`, bisa dibuka di Gephi) dan perbandingan harga.

Graf (versi 2) dibangun langsung dari tabel standar oleh `build_graph.py`. Tarif menempel pada Dokumen,
dan Dokumen → BERLAKU_UNTUK → RumahSakit, karena satu Perbup bisa berlaku untuk beberapa RS.
Node: 2.322 Layanan (1.128 Cianjur, 1.194 Rembang), 10 Golongan (9 bertarif, plus One Day Surgery tanpa matriks),
9 Kategori, 2 Dokumen, 2 RS. Edge: TARIF 2.497, KATEGORI 2.322, MASUK_GOLONGAN 567, SAMA_DENGAN 84,
TARIF_GOLONGAN 49, BERLAKU_UNTUK 2. Baris berflag nama_terpotong dan duplikat tidak dimasukkan.

## 3. Hasil

### Kualitas ekstraksi (cek manual 30 baris acak)
26 dari 30 (87%) benar nama dan harganya. Kesalahannya:
- Fragmen tanpa konteks, misalnya "Sedang", "Utama", atau "Kelas II", yang nama induknya ada di baris lain.
- Satu harga ambigu (".152.000").

### Alignment (47 query yang bisa dievaluasi: 23 punya padanan, 24 tidak)

| Metode | Hit@1 | Hit@3 | Precision* | Recall* | F1* |
|---|---|---|---|---|---|
| M1 exact | 0,17 | 0,17 | 1,00 | 0,17 | 0,30 |
| M2 TF-IDF karakter | 0,65 | 0,83 | 0,58 | 0,61 | 0,60 |
| M3 e5 zero-shot | 0,61 | 0,78 | 0,75 | 0,39 | 0,51 |
| M4 hybrid | **0,70** | **0,91** | 0,54 | 0,61 | 0,57 |

\* Ambang dipilih di sampel yang sama, jadi angkanya optimistis.
Dari 60 sampel, 12 berlabel "ragu" dan 1 rusak akibat ekstraksi.

**Peringatan:** label dibuat oleh asisten AI (silver), belum divalidasi manusia,
dan jumlahnya kecil (interval kepercayaan lebar, sekitar ±0,2). Anggap ini indikasi, bukan hasil.

### Perbandingan harga (versi 2, `src/compare_v2.py`)
Ada 84 pasangan (66 nama identik + 18 lewat label). Ringkasan memakai 69 pasangan yang status BHP-nya sama
di kedua dokumen dan tidak punya harga ganda. Rembang dibandingkan pada kelas III.

Median rasio Cianjur/Rembang kelas III adalah 4,4×. Per kategori: laboratorium 5,6× (41 pasangan),
radiologi 2,8×, mata/THT/kulit 2,9×, akomodasi 0,8×. Detail ada di `out/perbandingan_harga_v2.csv`.

## 4. Temuan penting

1. **Kelas dan komponen tarif harus dicatat per baris.** Rembang punya tabel kelas III dan kelas II
   untuk lab, radiologi, keperawatan, dan elektromedik. Status BHP juga berbeda antar-bagian.
   Lab di kedua RS sama-sama tidak termasuk BHP, jadi selisih lab (sekitar 5,6×) nyata secara angka.
   Penyebabnya belum bisa disimpulkan: tahun peraturan berbeda (2023 dan 2025), kelas RS Rembang belum dicek,
   dan tarif Cianjur tidak menyebut kelas.
2. **Format golongan tindakan adalah argumen terkuat untuk graf.** Rembang tidak memberi harga per tindakan.
   Harga ditentukan oleh golongan (Kecil, Kelompok I–III, Khusus) × kelas (III … VIP Utama, One Day Surgery),
   lalu ada daftar anggota golongan. Tabel datar tidak bisa menampungnya tanpa duplikasi,
   sedangkan graf `Layanan → Golongan → Tarif{kelas}` menampungnya dengan alami.
3. **Granularitas berbeda.** Contohnya "Paket Na, K, Cl" (Cianjur) setara dengan 3 item terpisah di Rembang,
   dan "Femur Kiri AP/Lateral" setara dengan "Photo Femur 2 Posisi". Relasi yang dibutuhkan bukan hanya SAMA_DENGAN,
   tapi juga TERDIRI_DARI dan LEBIH_SPESIFIK_DARI.
4. **Sekitar separuh layanan tidak punya padanan** di RS lain (24 dari 47). Model harus bisa menjawab "tidak ada",
   bukan selalu memilih top-1.
5. **Hard negative alami** banyak muncul, misalnya GTT ≠ Gamma GT, Uji Fungsi Berkemih Sedang ≠ Sederhana,
   dan CT Scan ≠ Photo. Ada juga kasus yang hanya bisa diselesaikan dengan pengetahuan domain, misalnya
   "VC (Vries Coop)" = "PA Potong Beku (VC)", yaitu frozen section.
6. **Kategori antar-RS tidak seragam** (misalnya "Pemeriksaan Canggih" vs "Tarif Pemeriksaan Laboratorium"),
   sehingga pemetaan kategori standar perlu dikerjakan serius.

## 4b. Koreksi dari versi pertama

- Versi pertama mengambil median tarif kelas III dan kelas II Rembang (misalnya SGOT Rp9.237,5). Sekarang kelas III saja.
- Klaim bahwa selisih lab "semu karena BHP" dicabut, karena lab Cianjur juga tidak termasuk BHP.
- Perbup Cianjur 3/2025 berlaku untuk semua RSUD Kelas C di Kab. Cianjur, bukan khusus RSUD Cimacan.
- Satu sel matriks golongan (non operatif, One Day Surgery) adalah salah baca dan dibuang, jadi tarif golongan menjadi 49 sel.
- Graf dibangun ulang dari tabel standar dengan model Dokumen → BERLAKU_UNTUK → RumahSakit (SAMA_DENGAN 84 edge, bukan 93).

## 4c. Tabel tarif standar

`src/to_standard.py` menghasilkan `out/tarif_standar_pilot.xlsx` (long format, 6 sheet: tarif, rumah_sakit,
dokumen, dokumen_rs, golongan_tarif, pemetaan). Ada 3.178 baris tarif: 2.881 ok, 177 nama_dari_baris_atas, 82 duplikat,
32 nama_terpotong, 22 golongan_tanpa_tarif, 4 harga_ambigu, dan 2 urutan_kelas_aneh. Status BHP terbaca untuk 93% baris.
Sheet `pemetaan` (2.261 nama unik) masih kosong dan siap diisi kode ICD-9-CM, LOINC, atau katalog lokal.

## 5. Kesimpulan & saran

**Ide ini layak dilanjutkan.** Hit@3 hybrid sekitar 0,9 berarti pelabelan semi-otomatis
(sistem mengusulkan kandidat, manusia memilih) akan cepat. Tapi auto-accept penuh belum bisa (precision sekitar 0,55–0,75).

Urutan langkah yang disarankan:
1. Validasi label pilot ini. Kamu dan satu PMIK memeriksa 60 sampel di `out/label_pilot.json`.
2. Kumpulkan 8–10 RSUD lagi dulu, bukan langsung 30, dari 2 provinsi. Sengaja pilih campuran format
   (harga langsung, golongan, dan per kelas) supaya ada parser adapter per format.
3. Petakan item ke ICD-9-CM dan LOINC (isi sheet `pemetaan`), lalu kerjakan pilot lapisan diagnosis untuk DBD, tifoid, dan SC.
4. Buat dev/test set terpisah (sekitar 300–500 pasangan) untuk menentukan ambang dan melaporkan hasil.
5. Kontribusi metode yang realistis: hybrid + fitur graf (golongan, kategori, tetangga) + opsi "tidak ada padanan",
   lalu coba fine-tune e5 dengan pasangan hasil label.
6. Framing paper: resource (dataset dan skema graf tarif RSUD) + evaluasi alignment + analisis variasi tarif
   setelah normalisasi komponen.
