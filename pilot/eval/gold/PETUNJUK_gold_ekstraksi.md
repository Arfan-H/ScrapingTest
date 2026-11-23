# Petunjuk penilaian gold set ekstraksi (gold_ekstraksi_v2.xlsx)

Tujuan: mengukur seberapa benar dan seberapa lengkap data tarif hasil ekstraksi otomatis dibanding PDF aslinya.
Hasil penilaian ini yang nanti dikutip sebagai akurasi di paper. Tidak perlu keahlian medis; cukup teliti
membandingkan data dengan gambar PDF. Perkiraan waktu: sekitar 5 jam (dua sheet). Boleh dicicil.

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

## Bila gambar tidak cukup
Buka PDF asli: `bpk_v3/buku_tarif/teks/<file>` di halaman yang tertera (nama file ada di manifest), atau pilih
"Tidak bisa dinilai".

## Hal yang sengaja disembunyikan
Tanda masalah dari sistem (flag_qc), pembagian dev/test, strata, dan tanda baris yang sengaja diubah tidak ditampilkan
agar penilaian tidak terpengaruh. Semuanya ada di gold_ekstraksi_v2_manifest.csv dan
gold_ekstraksi_v2_cakupan_manifest.csv. Jangan membuka manifest sebelum penilaian selesai.

## Penilai kedua
Urutan baris sudah diacak lintas dokumen. Bila ada penilai kedua (sebaiknya bukan pengembang proyek), minta ia menilai
"nilai_baris" no 1-60 dan "cek_baris_pdf" no 1-30 secara terpisah di salinan file, tanpa melihat isian penilai pertama.

## Versi
Data diambil dari parser commit cb968f4 (dibekukan). Jangan mengubah kolom selain kolom kuning. Skor dihitung dengan
`python -I pilot/eval/nilai_gold_ekstraksi.py <file_terisi.xlsx> [file_penilai_kedua.xlsx]`.
