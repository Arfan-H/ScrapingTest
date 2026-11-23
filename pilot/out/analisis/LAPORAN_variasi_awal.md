# Laporan variasi tarif awal antar-RSUD

Dibuat oleh `pilot/src/analisis_variasi.py` (MIN_RS=10). Data: `pilot/out/dataset/tarif.csv.gz` (479.733 baris, parser dibekukan di cb968f4).

**Status: deskriptif, awal.** Harga nominal (belum disesuaikan inflasi), nama dicocokkan persis (sinonim belum digabung), akurasi ekstraksi belum diukur dengan gold set. Jangan dikutip sebagai temuan akhir sebelum gold set dinilai.

## 1. Penyaringan

| langkah | baris tersisa |
|---|---|
| semua baris | 479.733 |
| tanpa PMK (RS pusat) | 462.153 |
| dokumen versi terbaru per RS | 340.188 |
| tanpa tanda masalah, harga terverifikasi | 288.365 |
| komponen total, tanpa varian, kelas standar | 267.411 |
| tanpa nama generik | 265.828 |

Setelah penyaringan: 330 RS, 171.006 kombinasi nama x kelas. Yang dimiliki >= 10 RS: **826 grup** (17.561 harga RS). Sebaran tahun dokumen: 2002-2026, median 2021.

## 2. Besar variasi

Rasio p90/p10 (harga RS di persentil 90 dibagi persentil 10) per grup: median **4,36**, kuartil 3,04-6,74. 76% grup punya rasio >= 3; 41% >= 5. Median koefisien variasi 0,65.

### Per kategori

| kategori | grup | median RS/grup | median p90/p10 | median CV | % grup p90/p10 >= 3 |
|---|---|---|---|---|---|
| Gigi | 13 | 14,00 | 7,29 | 0,78 | 100,0 |
| Mata/THT/Kulit | 27 | 14,00 | 6,01 | 0,73 | 100,0 |
| Akomodasi & Visite | 13 | 13,00 | 5,32 | 0,72 | 84,6 |
| Tindakan Lain | 444 | 15,00 | 5,07 | 0,72 | 82,0 |
| Kebidanan | 12 | 14,00 | 4,74 | 0,69 | 91,7 |
| Rawat Jalan & Darurat | 12 | 17,00 | 4,34 | 0,68 | 75,0 |
| Rehab Medik | 40 | 12,50 | 3,53 | 0,55 | 75,0 |
| Laboratorium | 201 | 17,00 | 3,52 | 0,54 | 65,2 |
| Radiologi | 64 | 15,00 | 3,07 | 0,46 | 53,1 |

### 25 layanan yang paling banyak RS-nya

| layanan | kelas | RS | prov | p10 | median | p90 | p90/p10 | tahun med. |
|---|---|---|---|---|---|---|---|---|
| EKG | Non-kelas | 123 | 30 | 30.000 | 65.000 | 106.000 | 3,53 | 2020 |
| Albumin | Non-kelas | 118 | 31 | 15.350 | 30.000 | 48.880 | 3,18 | 2021 |
| Asam Urat | Non-kelas | 114 | 30 | 19.000 | 32.250 | 50.000 | 2,63 | 2021 |
| SGOT | Non-kelas | 109 | 27 | 15.400 | 30.000 | 50.000 | 3,25 | 2021 |
| Ureum | Non-kelas | 109 | 31 | 14.900 | 30.000 | 47.220 | 3,17 | 2021 |
| Nebulizer | Non-kelas | 108 | 26 | 25.000 | 44.000 | 97.900 | 3,92 | 2021 |
| SGPT | Non-kelas | 101 | 26 | 15.500 | 32.000 | 50.000 | 3,23 | 2021 |
| Trigliserida | Non-kelas | 100 | 29 | 24.379 | 36.550 | 60.000 | 2,46 | 2021 |
| Bilirubin total | Non-kelas | 98 | 30 | 16.750 | 34.700 | 52.430 | 3,13 | 2021 |
| Protein Total | Non-kelas | 87 | 28 | 15.000 | 32.000 | 52.400 | 3,49 | 2020 |
| Golongan Darah | Non-kelas | 85 | 29 | 8.240 | 20.000 | 35.000 | 4,25 | 2020 |
| Widal | Non-kelas | 84 | 27 | 23.300 | 45.000 | 77.500 | 3,33 | 2021 |
| Globulin | Non-kelas | 83 | 28 | 18.500 | 30.000 | 50.000 | 2,70 | 2021 |
| Biopsi | Non-kelas | 76 | 28 | 45.000 | 150.000 | 900.250 | 20,01 | 2020 |
| VDRL | Non-kelas | 76 | 27 | 22.500 | 49.750 | 87.000 | 3,87 | 2021 |
| Gamma GT | Non-kelas | 74 | 27 | 25.600 | 45.000 | 83.500 | 3,26 | 2021 |
| Spirometri | Non-kelas | 70 | 24 | 50.000 | 150.000 | 352.500 | 7,05 | 2021 |
| Retikulosit | Non-kelas | 69 | 26 | 8.000 | 30.000 | 68.640 | 8,58 | 2021 |
| EEG | Non-kelas | 68 | 22 | 89.250 | 250.000 | 513.500 | 5,75 | 2020 |
| LDH | Non-kelas | 67 | 24 | 40.000 | 72.000 | 165.700 | 4,14 | 2021 |
| ASTO | Non-kelas | 64 | 23 | 27.900 | 50.000 | 80.000 | 2,87 | 2020 |
| Kreatinin | Non-kelas | 64 | 23 | 16.450 | 32.000 | 51.400 | 3,12 | 2021 |
| Analisa sperma | Non-kelas | 62 | 25 | 40.000 | 92.400 | 200.000 | 5,00 | 2020 |
| Bilirubin Direk | Non-kelas | 62 | 22 | 15.000 | 32.500 | 54.700 | 3,65 | 2021 |
| TSH | Non-kelas | 62 | 24 | 90.000 | 152.300 | 249.750 | 2,77 | 2021 |

### Variasi terlebar (grup >= 20 RS)

Variasi sangat lebar sering menandakan nama yang sama dipakai untuk layanan yang berbeda cakupannya (mis. paket vs satuan, per hari vs per tindakan) atau kesalahan ekstraksi; perlu dicek sebelum ditafsirkan.

| layanan | kelas | RS | min | median | maks | p90/p10 | % ganda dlm RS |
|---|---|---|---|---|---|---|---|
| Rawat jalan | Non-kelas | 25 | 2.500 | 23.000 | 7.000.000 | 82,50 | 16,0 |
| hidrotubasi | Non-kelas | 22 | 25.000 | 275.000 | 3.411.000 | 56,03 | 13,6 |
| Dokter | Non-kelas | 22 | 10.000 | 325.000 | 4.262.500 | 33,25 | 54,5 |
| Doppler | Non-kelas | 20 | 7.500 | 30.000 | 400.000 | 30,43 | 10,0 |
| Abdomen | Non-kelas | 20 | 20.000 | 142.500 | 2.700.000 | 29,09 | 25,0 |
| Thorax | Non-kelas | 49 | 38.500 | 120.000 | 3.500.000 | 28,61 | 26,5 |
| Parasintesis | Non-kelas | 20 | 30.000 | 162.500 | 2.310.000 | 25,96 | 15,0 |
| Tindik Telinga | Non-kelas | 29 | 14.450 | 50.000 | 700.000 | 25,00 | 13,8 |
| Amputasi Jari | Non-kelas | 22 | 98.000 | 221.000 | 8.586.500 | 24,63 | 0,0 |
| Orbita | Non-kelas | 30 | 42.500 | 168.250 | 1.995.000 | 22,70 | 30,0 |
| Pemasangan WSD | Non-kelas | 25 | 68.000 | 637.750 | 6.800.000 | 22,55 | 32,0 |
| Mastoid | Non-kelas | 40 | 12.000 | 160.000 | 6.438.000 | 21,63 | 15,0 |
| Pelvis | Non-kelas | 52 | 30.000 | 111.100 | 12.000.000 | 21,00 | 17,3 |
| Pemasangan CPAP | Non-kelas | 21 | 50.000 | 170.833 | 2.000.000 | 20,50 | 0,0 |
| Biopsi | Non-kelas | 76 | 5.000 | 150.000 | 5.742.083 | 20,01 | 30,3 |

**Nama pendek kehilangan konteks bagian.** Contoh: 'Thorax' termurah Rp 38.500 (tabel "Pemeriksaan Radiologi"), termahal Rp 3,5 juta (tabel "CT ANGIOGRAPHY" / "CT-SCAN KONTRAS"). Judul tabel tersimpan di kolom `kategori_asli`, tetapi tidak menjadi bagian `nama_norm`, sehingga X-ray dan CT-scan masuk satu grup. Median p90/p10 menurut panjang nama: 1 kata: 4,69 (291 grup, median 16 judul bagian berbeda); 2 kata: 4,37 (381 grup, median 13 judul bagian berbeda); >= 3 kata: 3,63 (154 grup, median 12 judul bagian berbeda). Untuk analisis lanjut, nama pendek perlu digabung dengan judul bagiannya.

### Variasi tersempit (grup >= 20 RS)

| layanan | kelas | RS | p10 | median | p90 | p90/p10 |
|---|---|---|---|---|---|---|
| Kolesterol HDL | Non-kelas | 21 | 40.000 | 57.000 | 70.000 | 1,75 |
| HbA1C | Non-kelas | 23 | 120.400 | 161.500 | 224.000 | 1,86 |
| Pemeriksaan EKG | Non-kelas | 25 | 44.000 | 70.000 | 89.850 | 2,04 |
| Cholesterol Total | Non-kelas | 44 | 22.420 | 35.500 | 46.490 | 2,07 |
| Glukosa | Non-kelas | 30 | 17.310 | 28.500 | 36.400 | 2,10 |
| Darah rutin | Non-kelas | 30 | 39.710 | 52.000 | 85.100 | 2,14 |
| Free T4 | Non-kelas | 20 | 154.600 | 200.000 | 337.000 | 2,18 |
| TSHs | Non-kelas | 33 | 130.880 | 210.000 | 287.800 | 2,20 |
| Elektrolit | Non-kelas | 22 | 109.950 | 150.000 | 247.800 | 2,25 |
| Glukosa Darah Sewaktu | Non-kelas | 23 | 20.000 | 25.000 | 46.600 | 2,33 |

## 3. Faktor yang ikut menjelaskan variasi

- **Tahun dokumen.** Korelasi Spearman harga vs tahun di dalam grup (grup dengan >= 3 tahun berbeda, n=826): median 0,35; 86% grup positif. Sebagian variasi adalah perbedaan waktu, jadi penyesuaian inflasi (IHK kesehatan BPS) diperlukan sebelum menyimpulkan.
- **Kelas perawatan** (harga kelas X / kelas III untuk nama yang sama di RS yang sama): II: median 1,15 (n=10126); I: median 1,34 (n=9365); VIP: median 1,50 (n=7196); VVIP: median 1,38 (n=2324).
- **BHP.** Di grup yang dianalisis, rata-rata 32% harga RS tercatat termasuk BHP, 8% tidak termasuk, sisanya tidak jelas. Harga yang tidak termasuk BHP belum lengkap; ini sumber bias yang harus disebut.
- **Nama ganda dalam satu RS.** Rata-rata 11,1% RS per grup punya lebih dari satu harga untuk nama+kelas yang sama (mis. di bagian berbeda); dipakai mediannya.

## 4. Indeks harga provinsi (awal)

Indeks = rata-rata geometrik (harga RS / median nasional grupnya) per RS, lalu dirata-rata per provinsi. 1,00 = setara median nasional. Provinsi dengan sedikit RS tidak stabil; tahun dokumen belum dikendalikan.

| provinsi | RS | harga | indeks | RS terendah | RS tertinggi |
|---|---|---|---|---|---|
| Kalimantan Utara | 5 | 134 | 1,72 | 0,82 | 3,51 |
| Bengkulu | 2 | 181 | 1,60 | 1,18 | 2,16 |
| Banten | 4 | 443 | 1,39 | 1,13 | 1,60 |
| Sumatera Selatan | 11 | 1.091 | 1,35 | 1,02 | 2,27 |
| Papua Barat | 5 | 229 | 1,17 | 0,61 | 1,82 |
| Nusa Tenggara Timur | 4 | 145 | 1,14 | 0,93 | 1,43 |
| Riau | 5 | 306 | 1,11 | 0,79 | 2,29 |
| Maluku | 3 | 146 | 1,10 | 0,74 | 1,87 |
| Kalimantan Selatan | 14 | 1.143 | 1,08 | 0,67 | 2,02 |
| Aceh | 3 | 413 | 1,08 | 0,78 | 1,39 |
| Bali | 4 | 172 | 1,08 | 0,36 | 1,94 |
| Kalimantan Timur | 11 | 702 | 1,07 | 0,65 | 1,79 |
| Jawa Timur | 24 | 1.041 | 1,07 | 0,63 | 2,31 |
| Kalimantan Barat | 12 | 740 | 1,04 | 0,45 | 1,66 |
| Sulawesi Selatan | 11 | 776 | 1,02 | 0,52 | 2,27 |
| Gorontalo | 4 | 64 | 1,01 | 0,54 | 1,72 |
| Sulawesi Barat | 6 | 513 | 1,01 | 0,25 | 1,54 |
| Nusa Tenggara Barat | 6 | 516 | 1,00 | 0,52 | 1,57 |
| Daerah Khusus Ibukota Jakarta | 2 | 304 | 0,97 | 0,85 | 1,10 |
| Sulawesi Tengah | 4 | 214 | 0,97 | 0,78 | 1,10 |
| Kalimantan Tengah | 5 | 289 | 0,96 | 0,76 | 1,34 |
| Lampung | 17 | 994 | 0,96 | 0,51 | 2,56 |
| Sulawesi Tenggara | 14 | 477 | 0,92 | 0,37 | 2,40 |
| Sumatera Utara | 9 | 596 | 0,91 | 0,35 | 4,90 |
| Jambi | 4 | 409 | 0,91 | 0,72 | 1,33 |
| Kepulauan Riau | 2 | 119 | 0,83 | 0,47 | 1,45 |
| Jawa Barat | 39 | 2.719 | 0,82 | 0,16 | 3,13 |
| Di Yogyakarta | 3 | 197 | 0,78 | 0,53 | 0,99 |
| Jawa Tengah | 47 | 1.540 | 0,71 | 0,27 | 2,31 |
| Kepulauan Bangka Belitung | 7 | 473 | 0,64 | 0,09 | 1,90 |
| Maluku Utara | 2 | 199 | 0,59 | 0,32 | 1,07 |
| Sumatera Barat | 4 | 276 | 0,59 | 0,37 | 1,10 |

## 5. Perubahan tarif antar-versi di RS yang sama

63 RS punya versi terbaru dan versi sebelumnya dengan nama+kelas yang sama. Median kenaikan per tahun (rata-rata geometrik per RS, disetahunkan): **3,1%**; median porsi layanan yang naik 28%, tetap 56%, turun 2%. Banyak versi baru adalah perubahan sebagian yang mengulang tarif lama tanpa mengubahnya; penurunan besar di satu RS perlu dicek (bisa beda cakupan atau kesalahan ekstraksi).

| RS | lama | baru | layanan sama | rasio median | % naik | naik/thn % |
|---|---|---|---|---|---|---|
| RSUD-SULAWESI-BARAT | 2021 | 2022 | 6.333 | 1,00 | 0,6 | 0,14 |
| RSUD-BARI-KOTA-PALEMBANG | 2021 | 2023 | 2.260 | 1,00 | 0,2 | -0,05 |
| RSUD-RAA-SOEWONDO-KABUPATEN-PATI | 2018 | 2019 | 1.104 | 1,00 | 2,6 | -1,27 |
| RSUD-BANGIL-KABUPATEN-PASURUAN | 2020 | 2021 | 1.001 | 1,07 | 76,8 | 17,63 |
| RSUD-SAMUEL-KRISTIAN-LERIK-KOTA-KUPANG | 2020 | 2023 | 674 | 1,00 | 4,2 | 0,38 |
| RSUD-KUDUNGGA-KABUPATEN-KUTAI-TIMUR | 2020 | 2021 | 654 | 1,00 | 0,8 | -0,31 |
| RSUD-PROF-DR-H-M-ANWAR-MAKKATUTU-KABUPATEN-BANTAENG | 2021 | 2024 | 494 | 1,00 | 6,1 | 0,17 |
| RSUD-PROF-DR-W-Z-JOHANNES-KUPANG-NUSA-TENGGARA-TIMUR | 2021 | 2023 | 492 | 1,00 | 1,8 | -0,33 |
| RSUD-DR-HADRIANUS-SINAGA-PANGURURAN-KABUPATEN-SAMOSIR | 2018 | 2020 | 458 | 1,00 | 3,1 | 0,37 |
| RS-RSUD-SANGATTA-KABUPATEN-KUTAI-TIMUR | 2013 | 2015 | 419 | 1,00 | 11,9 | 1,85 |
| RSJ-LAMPUNG | 2016 | 2017 | 399 | 1,00 | 0,0 | 0,00 |
| RSUD-DAHA-SEJAHTERA-KABUPATEN-HULU-SUNGAI-SELATAN | 2021 | 2023 | 356 | 1,00 | 0,8 | -9,24 |
| RSUD-DAERAH-KHUSUS-IBUKOTA-JAKARTA | 2015 | 2018 | 331 | 1,29 | 80,1 | 10,36 |
| RSUD-KOTABARU-KABUPATEN-KOTA-BARU | 2015 | 2019 | 303 | 1,00 | 2,0 | 0,17 |
| RSUD-CIAWI-KABUPATEN-BOGOR | 2006 | 2008 | 297 | 1,00 | 0,3 | 0,02 |
| RSUD-GRATI-KABUPATEN-PASURUAN | 2018 | 2021 | 294 | 1,00 | 9,5 | -0,05 |
| RS-GIGI-DAN-MULUT-GUSTI-HASAN-AMAN-KALIMANTAN-SELATAN | 2015 | 2016 | 264 | 1,00 | 18,6 | 10,84 |
| RSUD-SULTAN-SURIANSYAH-KOTA-BANJARMASIN | 2021 | 2024 | 246 | 1,20 | 76,4 | 8,12 |
| RSUD-KABUPATEN-KEBUMEN | 2013 | 2022 | 243 | 1,00 | 0,0 | -0,63 |
| RSUD-KOTA-DEPOK | 2016 | 2019 | 219 | 1,09 | 97,7 | 4,81 |

## 6. Langkah berikut

1. Nilai gold set ekstraksi (`pilot/eval/gold/gold_ekstraksi_v1.xlsx`) untuk tahu seberapa besar variasi di atas bisa berasal dari kesalahan ekstraksi.
2. Sesuaikan harga ke tahun dasar dengan IHK (kelompok kesehatan) BPS.
3. Nama pendek (1-2 kata) digabung dengan judul bagian (`kategori_asli`) sebelum dikelompokkan; lalu gabungkan sinonim lewat pemetaan kode yang sudah divalidasi (bukan usulan otomatis).
4. Cek manual grup dengan variasi terlebar (bagian 2) untuk memisahkan beda cakupan layanan vs kesalahan.
5. Model penjelas (mis. regresi log-harga ~ tahun + kelas + provinsi + tipe RS + BHP) setelah langkah 1-3.

## Berkas
- `variasi_grup.csv`: statistik per nama x kelas
- `variasi_kategori.csv`
- `indeks_provinsi.csv`
- `perubahan_versi.csv`

