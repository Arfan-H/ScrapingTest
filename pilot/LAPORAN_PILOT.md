# Laporan Pilot: Graf Tarif RSUD dari Perbup (2 RSUD)

Pilot ini menguji apakah ide "knowledge graph tarif RSUD dari Perda/Perbup" bisa dikerjakan,
sebelum mengumpulkan 20–30 RSUD. Semua angka di bawah berasal dari skrip di `src/`
(jalankan ulang dengan `./run_pilot.sh`).

## 1. Data

| RS | Peraturan | Halaman | Baris tarif | Layanan unik |
|---|---|---|---|---|
| RSUD Cimacan (Cianjur, Jabar) | Perbup Cianjur 3/2025 | 50 | 1.445 | 1.135 |
| RSUD dr. R. Soetrasno (Rembang, Jateng) | Perbup Rembang 16/2023 | 76 | 1.166 berharga + 567 anggota golongan | 1.186 |

Kedua PDF berupa teks, jadi tidak perlu OCR. URL ada di `sumber.csv`.
peraturan.bpk.go.id tidak bisa diunduh otomatis karena dilindungi Cloudflare,
jadi file diambil dari JDIH daerah atau situs RSUD.

## 2. Alur

1. `extract.py`: parser generik berbasis baris. Harga terakhir di baris dianggap total, dan judul tanpa angka dianggap kategori.
2. `golongan_rembang.py`: adapter khusus untuk format golongan tindakan (lihat temuan 2).
3. `normalize.py`: lowercase, memisah kata yang menempel, kamus singkatan, dan 9 kategori standar berbasis aturan.
4. `align.py`: Cimacan → Rembang dengan 4 metode: exact, TF-IDF karakter, e5 multilingual (zero-shot), dan hybrid (TF-IDF + e5 + bonus kategori). Harga sengaja tidak dipakai sebagai fitur.
5. `evaluate.py`: 60 layanan Cimacan diambil acak bertingkat per kategori, lalu dilabel.
6. `build_graph.py`: graf NetworkX (`out/graf_pilot.graphml`, bisa dibuka di Gephi) dan perbandingan harga.

Graf yang terbentuk: 2.321 node Layanan, 9 Golongan, 6 Kelas, 9 Kategori, dan 2 RS.
Edge-nya: TARIF 1.788, MASUK_GOLONGAN 533, TARIF_GOLONGAN 50, dan SAMA_DENGAN 93.

## 3. Hasil

### Kualitas ekstraksi (cek manual 30 baris acak)
26 dari 30 (≈85%) benar nama dan harganya. Kesalahannya:
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

### Perbandingan harga (93 pasangan: 74 exact + 19 label)
Median rasio harga Cimacan/Rembang adalah 3,5×. Untuk laboratorium 5,0×, sedangkan untuk akomodasi sekitar 1×.
Ada 42 pasangan yang selisihnya lebih dari 4×. Detailnya ada di `out/perbandingan_harga.csv`.

## 4. Temuan penting

1. **Selisih harga sebagian besar akibat komponen tarif, bukan harga yang sebenarnya berbeda.**
   Tarif lab Rembang kelas III (misalnya SGOT Rp8.400) hanya terdiri dari jasa sarana + layanan + medis,
   dengan catatan "tidak termasuk BHP". Angka Cimacan tampaknya tarif total. Jadi node atau edge tarif
   wajib punya atribut komponen (termasuk BHP atau tidak, kelas, CITO). Ini sekaligus jadi kontribusi skema.
2. **Format golongan tindakan adalah argumen terkuat untuk graf.** Rembang tidak memberi harga per tindakan.
   Harga ditentukan oleh golongan (Kecil, Kelompok I–III, Khusus) × kelas (III … VIP Utama, One Day Surgery),
   lalu ada daftar anggota golongan. Tabel datar tidak bisa menampungnya tanpa duplikasi,
   sedangkan graf `Layanan → Golongan → Tarif{kelas}` menampungnya dengan alami.
3. **Granularitas berbeda.** Contohnya "Paket Na, K, Cl" (Cimacan) setara dengan 3 item terpisah di Rembang,
   dan "Femur Kiri AP/Lateral" setara dengan "Photo Femur 2 Posisi". Relasi yang dibutuhkan bukan hanya SAMA_DENGAN,
   tapi juga TERDIRI_DARI dan LEBIH_SPESIFIK_DARI.
4. **Sekitar separuh layanan tidak punya padanan** di RS lain (24 dari 47). Model harus bisa menjawab "tidak ada",
   bukan selalu memilih top-1.
5. **Hard negative alami** banyak muncul, misalnya GTT ≠ Gamma GT, Uji Fungsi Berkemih Sedang ≠ Sederhana,
   dan CT Scan ≠ Photo. Ada juga kasus yang hanya bisa diselesaikan dengan pengetahuan domain, misalnya
   "VC (Vries Coop)" = "PA Potong Beku (VC)", yaitu frozen section.
6. **Kategori antar-RS tidak seragam** (misalnya "Pemeriksaan Canggih" vs "Tarif Pemeriksaan Laboratorium"),
   sehingga pemetaan kategori standar perlu dikerjakan serius.

## 5. Kesimpulan & saran

**Ide ini layak dilanjutkan.** Hit@3 hybrid sekitar 0,9 berarti pelabelan semi-otomatis
(sistem mengusulkan kandidat, manusia memilih) akan cepat. Tapi auto-accept penuh belum bisa (precision sekitar 0,55–0,75).

Urutan langkah yang disarankan:
1. Validasi label pilot ini. Kamu dan satu PMIK memeriksa 60 sampel di `out/label_pilot.json`.
2. Kumpulkan 8–10 RSUD lagi dulu, bukan langsung 30, dari 2 provinsi. Sengaja pilih campuran format
   (harga langsung, golongan, dan per kelas) supaya ada parser adapter per format.
3. Tambahkan atribut komponen tarif ke skema (total/komponen, BHP, kelas, CITO) sebelum membandingkan harga.
4. Buat dev/test set terpisah (sekitar 300–500 pasangan) untuk menentukan ambang dan melaporkan hasil.
5. Kontribusi metode yang realistis: hybrid + fitur graf (golongan, kategori, tetangga) + opsi "tidak ada padanan",
   lalu coba fine-tune e5 dengan pasangan hasil label.
6. Framing paper: resource (dataset dan skema graf tarif RSUD) + evaluasi alignment + analisis variasi tarif
   setelah normalisasi komponen.
