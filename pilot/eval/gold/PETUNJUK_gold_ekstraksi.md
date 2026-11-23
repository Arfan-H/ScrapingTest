# Petunjuk penilaian gold set ekstraksi v3

File penilai pertama: `gold_ekstraksi_v3.xlsx`. File penilai kedua: `gold_ekstraksi_v3_penilai2.xlsx`.
Versi lama (v1, v2) ada di folder `v1_tidak_dipakai/` dan `v2_tidak_dipakai/`; jangan dipakai.

Tujuan: mengukur seberapa benar dan seberapa lengkap data tarif hasil ekstraksi otomatis dibanding PDF aslinya.
Hasil penilaian ini yang nanti dikutip sebagai akurasi di paper. Tidak perlu keahlian medis; cukup teliti
membandingkan data dengan gambar PDF. Perkiraan waktu penilai pertama: sekitar 5-6 jam (dua sheet). Boleh dicicil.

Ada dua sheet yang dinilai:
- "nilai_baris": dari DATA ke PDF. Apakah isi data untuk satu baris benar?
- "cek_baris_pdf": dari PDF ke DATA. Apakah satu baris tarif di PDF tercatat lengkap di data?

Nilailah apa yang Anda lihat di PDF, bukan apa yang tampak masuk akal. Sebagian baris sengaja dibuat salah untuk
memeriksa ketelitian penilaian, jadi jangan menganggap data pasti benar.

## Sheet "nilai_baris"
Setiap baris berisi gambar potongan halaman PDF (baris sumber diberi kotak MERAH, judul tabel/kolom di atasnya ikut
terlihat) serta nama, kelas, varian, komponen, dan harga seperti tercatat di data. Isi kolom kuning:

1. **NAMA benar?** Ya bila nama di data sama dengan nama layanan di PDF untuk baris itu. Salah ketik kecil akibat
   PDF/OCR (mis. "Kateterisasi" tertulis "Kateteri sasi", spasi hilang) tetap Ya. Pilih Tidak bila nama terpotong,
   tertukar dengan baris lain, memuat teks lain (nomor baris, kode, isi kolom lain), atau kehilangan bagian penting
   (mis. "(GA)" vs "(LA)", induk "Operasi Besar -"). Tulis nama yang benar di "nama seharusnya".
2. **KELAS benar?** Ya bila kelas sesuai judul kolom/tabel di PDF (III, II, I, VIP, Utama, dst.). "Non-kelas" hanya benar
   bila tarif itu memang tidak dibedakan per kelas; bila tabelnya berjudul mis. "KELAS VIP", maka "Non-kelas" = Tidak.
   Label seperti "kolom 2/4 (kelas tak terbaca)" dinilai Tidak bila kelasnya bisa dibaca di PDF (tulis kelas yang benar),
   atau Tidak bisa dinilai bila judul kolom/tabel tidak tampak.
3. **VARIAN/KOMPONEN benar?** Varian = pembeda selain kelas (Reguler/Eksekutif, Elektif/Cyto, Tanpa/Dengan Kontras).
   Komponen = "total" (tarif keseluruhan) atau komponen rincian (jasa sarana, jasa pelayanan, dr. operator, dst.).
   Pilih Tidak bila, misalnya, angka itu sebenarnya jasa sarana tetapi tercatat "total".
4. **HARGA benar?** Ya bila angka di data sama persis dengan angka di PDF untuk nama, kelas, dan komponen itu. Tulis
   angka yang benar bila Tidak.
5. **catatan**: bebas (mis. "harga ini milik baris di bawahnya").

## Sheet "cek_baris_pdf"
Setiap baris berisi gambar potongan PDF dengan satu baris bertanda MERAH yang memuat angka, dan kolom "data yang
berasal dari baris ini" (semua catatan data yang diambil sistem dari baris PDF itu; bisa kosong).

1. **Baris ini memuat TARIF layanan?** Ya bila baris merah berisi harga layanan. Tidak bila angkanya bukan tarif
   (nomor peraturan, tahun, nomor halaman, jumlah, NIP, dsb.). Bila Tidak, kolom berikutnya boleh dikosongkan.
2. **Semua harga di baris ini ada di data dengan benar?**
   - Ya semua: setiap harga di baris merah muncul di data dengan nama dan kelas yang benar.
   - Sebagian: ada harga yang hilang, salah angka, atau tercatat untuk nama/kelas yang salah.
   - Tidak ada: baris tarif ini tidak tercatat sama sekali (kolom data kosong atau isinya baris lain).
   - Tidak bisa dinilai: gambar kabur/terpotong.
   Nama boleh diambil dari baris di atasnya (nama layanan yang panjang sering terbagi dua baris).
3. **harga/nama yang hilang atau salah**: tulis singkat apa yang hilang/salah.

## Mulai dengan uji coba
Nilai 10-15 butir pertama di "nilai_baris" dan 5 butir pertama di "cek_baris_pdf", lalu berhenti dan periksa: apakah
petunjuk cukup jelas (terutama "Non-kelas" dan "varian/komponen"), apakah judul kolom terlihat, dan apakah kotak merah
tepat pada barisnya. Bila aturan perlu diperjelas, tulis perubahannya di bagian "Riwayat petunjuk" di bawah (dengan
tanggal dan nomor versi), lalu nilai ULANG butir uji coba itu dengan aturan yang baru sebelum melanjutkan.

## Bila gambar tidak cukup
Cari ID baris di `gold_ekstraksi_v3_lokasi.csv` (berisi ID, nama file PDF, dan halaman saja), lalu buka
`bpk_v3/buku_tarif/teks/<file>` di halaman itu. Atau pilih "Tidak bisa dinilai".

## Hal yang sengaja disembunyikan
Dokumen asal, tanda masalah dari sistem (flag_qc), pembagian dev/test, strata, dan tanda baris yang sengaja diubah
tidak ditampilkan agar penilaian tidak terpengaruh. Semuanya ada di file `*_manifest.csv` dan `*_strata.csv`.
JANGAN membuka file-file itu, maupun laporan atau ringkasan apa pun tentang isi sampel, sebelum penilaian selesai.

## Penilai kedua
Penilai kedua memakai file sendiri, `gold_ekstraksi_v3_penilai2.xlsx` (153 butir "nilai_baris" = 120 butir biasa +
33 butir kontrol, dan 30 butir "cek_baris_pdf", dengan ID dan urutan sendiri). Idealnya ia belum pernah melihat kode, laporan,
atau file penilai pertama. Ketelitian penilai diukur terutama dari penilai kedua.

## Riwayat petunjuk
- Versi 1 (2026-11-23): versi awal, dikunci di tag git `gold-v3-prereg`.

## Versi
Data diambil dari parser commit cb968f4 (dibekukan). Jangan mengubah kolom selain kolom kuning. Skor dihitung dengan
`python -I pilot/eval/nilai_gold_ekstraksi.py <gold_ekstraksi_v3_terisi.xlsx> [gold_ekstraksi_v3_penilai2_terisi.xlsx]`.
