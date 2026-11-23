# Pra-registrasi: evaluasi akurasi ekstraksi tarif RSUD (gold set v3)

Tanggal: 2026-11-23. Ditetapkan SEBELUM penilaian manusia dimulai. Tag git: `gold-v3-prereg` (pesan tag memuat commit
dan hash yang sama dengan dokumen ini). Dokumen ini juga diunggah ke layanan pencatat waktu di luar repo (OSF
Registrations / Zenodo) agar waktunya dapat dibuktikan.

## 1. Data dan alat yang dibekukan
| objek | identitas |
|---|---|
| Parser (`pilot/src/to_standard.py`) | commit `cb968f4`; dibekukan, tidak diubah sebelum penilaian selesai |
| Dataset tarif (`pilot/out/dataset/tarif.csv.gz`) | commit `cd71555`; SHA-256 `febb4601665beee661aefe0070b5b7b4ea861a7a72e86aa4a71aafb543e6ddfa` |
| File penilai pertama (kosong) `gold_ekstraksi_v3.xlsx` | SHA-256 `680afeff8ab572a2b6f5ec99b403b34c8354c38d21ea06bdea2e7bfc6ead2038` |
| File penilai kedua (kosong) `gold_ekstraksi_v3_penilai2.xlsx` | SHA-256 `d402304e78d3b3041108ddfbebc9da890bc8d5113dde8d00cd083150f8007cc7` |
| Skrip skor `pilot/eval/nilai_gold_ekstraksi.py` | SHA-256 `912dc9e5074adb83d2c00db1ca9e1aabc0891021ddef0502080e34ec9f85b1d5` |
| Skrip pembuat sampel `pilot/eval/buat_gold_ekstraksi.py` | SHA-256 `e21764a9675027dc6614de2bb3e4f49872ad8a01bf4741ee20b34b0d15198f7c` |
| Petunjuk penilai (versi 1) `PETUNJUK_gold_ekstraksi.md` | SHA-256 `e5c7942c586e71127a624a7af6a233bdaae8419f55f722b1d3175e61b3905d08` |
| Daftar pool cadangan `pool_cadangan_sesudah.txt` (199 dokumen) | SHA-256 `c167c875796c04678525b62efffcffc1fd496750811eff3bc3e1dd269898e029` |

## 2. Sampel
- Populasi: 305 dokumen peraturan "eligible" (>= 20 baris tarif, tidak tersentuh saat pengembangan parser; 181+4 dokumen
  dikecualikan, lihat `dokumen_dikecualikan.csv`).
- 60 dokumen, bertingkat sumber teks x bentuk tabel, alokasi sama rata (strata kecil diambil semua):
  ocr_ulang/golongan 3/3, ocr_ulang/satu_harga 16/40, teks_pdf/golongan 15/45, teks_pdf/per_kelas 11/11,
  teks_pdf/satu_harga 15/206. Strata ocr_ulang/per_kelas tidak punya dokumen eligible.
- Presisi (data -> PDF): 327 butir asli + 33 butir kontrol (nilai sengaja diubah), 6 butir per dokumen.
- Cakupan (baris PDF -> data): 119 butir; 2 halaman acak per dokumen dari halaman berkandidat dalam rentang halaman
  ber-data, 1 baris kandidat (angka >= 1.000) per halaman.
- Penilai kedua: 120 butir presisi acak + 33 butir kontrol + 30 butir cakupan, ID dan urutan sendiri.
- Paparan: 30 dari 60 dokumen v3 pernah muncul di file draf v1/v2 yang sempat dibuka; 11 butir presisi barisnya sama
  persis dengan butir v1/v2. Dilaporkan, dan diuji sebagai sensitivitas.

## 3. Keputusan yang dikunci
1. Parser dibekukan di `cb968f4`. Dev dan test DIGABUNG (60 dokumen); pembagian dev/test di manifest tidak dipakai.
2. ANGKA UTAMA = akurasi makro per dokumen (rata-rata akurasi dokumen di dalam strata, digabung dengan bobot jumlah
   dokumen eligible per strata). Target inferensi: dokumen peraturan baru. CI 95% = bootstrap persentil, dokumen
   diambil ulang di dalam strata (2000 ulangan).
3. Hasil per strata dilaporkan sejajar dengan angka gabungan; strata dengan < 3 dokumen ber-isian ditandai tidak andal.
4. Pendamping: (a) sensus + koreksi populasi terhingga (klaim tentang dataset ini); (b) akurasi berbobot baris;
   (c) makro dengan bobot seluruh 505 dokumen.
5. "Tidak bisa dinilai" dan isian kosong dikeluarkan per kolom; jumlahnya dilaporkan per kolom; skenario terburuk
   (tidak bisa dinilai = salah) dilaporkan.
6. "Semua kolom benar": salah bila >= 1 kolom "Tidak"; benar bila keempat kolom (nama, kelas, varian/komponen, harga)
   "Ya"; dikeluarkan hanya bila tidak ada "Tidak" tetapi ada kolom yang tidak dinilai.
7. Cakupan = recall di dalam rentang halaman ber-data untuk harga >= 1.000 (bukan recall seluruh dokumen); hanya
   baris yang dinilai "memuat tarif".
8. Butir kontrol tidak ikut akurasi; ketelitian penilai dilaporkan per penilai dengan CI Wilson. Penilai pertama
   tidak buta terhadap desain kontrol. Porsi kontrol di file penilai kedua (~22%) lebih tinggi dari file pertama
   (~9%), jadi angka keduanya tidak setara langsung.
9. Kesepakatan antar-penilai hanya pada butir presisi yang sama: % sama, kappa Cohen, Gwet AC1.
10. Bila parser diubah setelah penilaian, hasil v3 menjadi pengukuran "sebelum". Pengukuran "sesudah" memakai sampel
    baru dari 199 dokumen pool cadangan (`pool_cadangan_sesudah.txt`), yang tidak boleh dibuka per dokumen atau
    dipakai untuk debugging sebelum itu (pemrosesan agregat seluruh dataset tetap boleh).
11. Uji coba: 10-15 butir pertama dinilai dulu; bila petunjuk diperjelas, perubahan dicatat dengan versi di
    petunjuk dan butir uji coba dinilai ulang.

## 4. Sifat estimator (simulasi dengan kebenaran diketahui, `pilot/eval/simulasi_estimator_gold.py`, 400 ulangan)
| galat antar-dokumen | estimator | bias | cakupan CI 95% | lebar CI |
|---|---|---|---|---|
| sedang (kappa 20) | makro (UTAMA) | +0,09 pp | 90% | 8,4 pp |
| kuat (kappa 4) | makro (UTAMA) | -0,03 pp | 88% | 10,1 pp |
| sedang (kappa 20) | berbobot baris | +0,27 pp | 86% | 10,1 pp |
| kuat (kappa 4) | berbobot baris | -0,26 pp | 87% | 12,4 pp |

Jumlah dokumen efektif makro lintas strata (Kish) ~30. CI cenderung terlalu sempit (cakupan ~86-92%, bukan 95%) dan
akan disajikan sebagai perkiraan kasar.
