# Petunjuk penilaian gold set ekstraksi (gold_ekstraksi_v1.xlsx)

Tujuan: mengukur seberapa benar data tarif hasil ekstraksi otomatis dibanding PDF aslinya. Hasil penilaian ini
yang nanti dikutip sebagai akurasi di paper. Tidak perlu keahlian medis; cukup teliti membandingkan data dengan gambar PDF.

## Cara menilai satu baris
Setiap baris di sheet "nilai" berisi:
- gambar potongan halaman PDF, dengan garis MERAH di kiri menandai baris PDF yang menjadi sumber data;
- nama, kelas, varian, komponen, dan harga seperti tercatat di data.

Isi kolom kuning:
1. **NAMA benar?** Ya bila nama di data sama dengan nama layanan di PDF untuk baris itu. Salah ketik kecil akibat
   PDF/OCR (mis. "Kateterisasi" tertulis "Kateteri sasi") tetap dianggap Ya. Pilih Tidak bila nama terpotong, tertukar
   dengan baris lain, memuat teks lain (nomor baris, kode, isi kolom lain), atau kehilangan bagian penting
   (mis. "(GA)" vs "(LA)", induk "Operasi Besar -"). Tulis nama yang benar di "nama seharusnya".
2. **KELAS benar?** Ya bila kelas sesuai judul kolom/baris di PDF (III, II, I, VIP, Utama, dst.). "Non-kelas" benar bila
   tarif itu memang tidak dibedakan per kelas. Label seperti "kolom 2/4 (kelas tak terbaca)" dinilai Tidak bila kelasnya
   sebenarnya bisa dibaca di PDF (tulis kelas yang benar), atau Tidak bisa dinilai bila judul kolom tidak tampak di potongan.
3. **VARIAN/KOMPONEN benar?** Varian = pembeda selain kelas (Reguler/Eksekutif, Elektif/Cyto, Tanpa/Dengan Kontras).
   Komponen = "total" (tarif keseluruhan) atau komponen rincian (jasa sarana, jasa pelayanan, dr. operator, dst.).
   Pilih Tidak bila, misalnya, angka itu sebenarnya jasa sarana tetapi tercatat "total".
4. **HARGA benar?** Ya bila angka di data sama dengan angka di PDF untuk nama, kelas, dan komponen itu. Tulis angka yang
   benar bila Tidak.
5. **catatan**: bebas (mis. "harga ini milik baris di bawahnya").

Bila potongan gambar tidak cukup (judul kolom tidak terlihat, gambar kabur), buka PDF aslinya:
`bpk_v3/buku_tarif/teks/<file>` di halaman yang tertera (nama file ada di gold_ekstraksi_v1_manifest.csv),
atau pilih "Tidak bisa dinilai".

## Hal yang sengaja disembunyikan
Tanda masalah dari sistem (flag_qc) dan pembagian dev/test tidak ditampilkan agar penilaian tidak terpengaruh.
Keduanya ada di gold_ekstraksi_v1_manifest.csv.

## Penilai kedua
Bila ada penilai kedua, minta ia menilai baris no 1–60 secara terpisah (tanpa melihat isian penilai pertama) di salinan
file, supaya kesepakatan antar-penilai bisa dihitung.

## Versi
Data diambil dari parser commit cb968f4 (dibekukan). Jangan mengubah kolom selain kolom kuning.
