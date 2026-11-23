# CLAUDE.md: Pencarian Literatur & Penentuan Metode
## Proyek: Dataset dan Graf Tarif RSUD Indonesia dari Peraturan Daerah

File ini adalah konteks kerja untuk sesi Claude yang membantu **mencari jurnal sejenis**, **menyusun tinjauan pustaka**,
dan **menimbang pilihan metode** untuk tulisan ilmiah dari proyek ini. Jalankan Claude dari folder `literatur/`
supaya file ini terbaca otomatis. Kode dan data ada di `../pilot/`.

---

## 1. Ringkasan proyek (angka per 2026-11-23, dari `../pilot/out/dataset/`)

**Masalah.** Tarif layanan RSUD ditetapkan lewat Perda/Perbup/Perwali/Pergub (dan PMK untuk RS vertikal), lalu
dipublikasikan sebagai PDF. Tata letak tabelnya berbeda-beda, banyak berupa hasil scan, dan setiap daerah memakai istilah,
kelas, dan komponen tarif sendiri. Akibatnya tarif antar-RS tidak bisa dibandingkan secara sistematis. Belum ada dataset
terbuka dan terstruktur untuk tarif RSUD Indonesia.

**Yang sudah dibangun:**
| Komponen | Isi |
|---|---|
| Sumber | 514 file PDF / 505 peraturan dari JDIH BPK (peraturan.bpk.go.id), tahun 2001–2026 |
| Cakupan | 342–343 RS, 34 provinsi |
| Dataset | 479.733 baris tarif dalam format panjang (1 baris = nama layanan × kelas × varian × komponen × harga), dengan halaman dan teks baris PDF sumber untuk setiap baris |
| Ekstraksi | Parser berbasis tata letak (pdfplumber: posisi kata, judul kolom bertumpuk, lanjutan nama antar baris), OCR ulang (RapidOCR) untuk halaman scan yang lapisan teksnya rusak, aturan kosakata untuk memilih teks OCR atau teks asli |
| Kontrol mutu | Setiap harga diverifikasi ulang terhadap baris PDF sumber (99,9% cocok; 451 baris tidak cocok ditandai). Flag masalah per baris (`qc_masalah`, sekitar 14% baris). Cek visual 40 baris acak per putaran (v3: 13 salah tak tertandai → v10: 3–4), **tetapi angka ini bias optimistis**: parser diperbaiki dari galat sampel-sampel itu dan pemeriksanya AI yang sama. Angka yang boleh dikutip harus dari gold set held-out (lihat §5a) |
| Konteks | Status peraturan (berlaku/diubah/dicabut dari relasi BPK), urutan versi per RS, status BHP (termasuk/tidak termasuk bahan habis pakai) dari pasal peraturan, wilayah Kemendagri |
| Pemetaan kode | 169.803 nama layanan unik (perutean heuristik per kategori: ICD-9-CM 77%, LOINC 12%, Lokal 11% nama unik; proporsi "tidak ada padanan" yang sebenarnya belum diketahui sampai ada gold set) → usulan kode: ICD-9-CM Vol. 3 (prosedur, 3.882 kode CMS v32), LOINC (Universal Lab Orders, 1.519 tes), atau "Lokal" (akomodasi, visite, administrasi). Skor = 0,7 × kosinus multilingual-e5-small + 0,3 × kosinus TF-IDF karakter, atas nama ditambah terjemahan istilah medis ID→EN. **Masih usulan dan belum divalidasi PMIK.** Evaluasi silver kecil: ICD-9-CM hit@1 ≈ 0,33, hit@5 ≈ 0,47–0,57; LOINC hit@1 0,6–1,0, hit@5 0,8–1,0 |
| Graf | Model property graph (NetworkX/GraphML) baru diuji pada pilot 9 dokumen: Dokumen–BERLAKU_UNTUK→RS, Dokumen–TARIF{kelas,komponen,BHP,harga}→Layanan, Layanan→Golongan, Layanan→Kategori, Layanan–USULAN_KODE→Kode, Layanan–SAMA_NAMA/SAMA_DENGAN→Layanan. Belum dibangun untuk 505 peraturan |

**Temuan awal yang perlu diposisikan terhadap literatur:**
- Variasi nama sangat besar: 169.803 nama unik, dan nama yang muncul di ≥2 RS hanya mencakup 42,5% baris.
- Tarif per kelas, varian (reguler/eksekutif, elektif/cito), dan komponen (jasa sarana/pelayanan, BHP) harus dinormalkan
  sebelum harga bisa dibandingkan.
- Format golongan tindakan (harga per golongan × kelas, lalu daftar anggota golongan) lebih alami dimodelkan sebagai graf.
- Kategori standar yang masih kasar: 55% **baris** jatuh ke "Tindakan Lain" (ini porsi kategori, bukan porsi layanan tanpa kode).
  Ini kelemahan untuk menentukan sistem kode.
- Hit@1 ICD-9-CM ≈ 0,33 berasal dari n=14–15 (≈5 benar), jadi tidak bisa dipakai menyimpulkan penyebab apa pun.

---

## 2. Tujuan penelitian (rumusan kerja; pilih dan pertajam)

1. **Resource:** menyediakan dataset terbuka tarif RSUD Indonesia yang dapat ditelusuri ke sumbernya (halaman dan baris PDF),
   lengkap dengan skema dan dokumentasi mutu.
2. **Metode ekstraksi:** pipeline ekstraksi tabel tarif dari PDF regulasi heterogen (teks dan scan) dengan verifikasi
   otomatis dan pengukuran galat.
3. **Normalisasi semantik:** pemetaan nama layanan berbahasa Indonesia ke terminologi standar (ICD-9-CM, LOINC) secara
   lintas bahasa, sebagai kandidat yang divalidasi manusia (human-in-the-loop).
4. **Analisis:** variasi tarif layanan setara antar-RS, wilayah, kelas, dan waktu setelah normalisasi komponen dan BHP.
5. **Representasi:** knowledge graph yang menghubungkan regulasi, RS, layanan, kode standar, dan harga.

**Pertanyaan penelitian kandidat:**
- RQ1: Seberapa akurat ekstraksi otomatis tarif dari PDF regulasi daerah, dan galat apa yang dominan?
- RQ2: Seberapa baik model embedding multilingual memetakan nama layanan berbahasa Indonesia ke ICD-9-CM dan LOINC
  dibanding baseline leksikal, LLM, dan fine-tuning?
- RQ3: Seberapa besar variasi tarif layanan setara antar-RSUD setelah normalisasi, dan faktor apa yang berasosiasi dengannya
  (kelas RS, wilayah, tahun, status BLUD, BHP)?
- RQ4: Apakah representasi graf (golongan, kategori, tetangga) memperbaiki pencocokan layanan antar-RS?

---

## 3. Peta literatur: tema, kata kunci, dan titik awal

Untuk setiap tema: (a) mengapa relevan, (b) kata kunci, (c) contoh string pencarian, (d) rujukan titik awal yang
**sudah dicek ada** (lihat aturan §7), dan (e) celah yang mungkin diisi proyek ini.

### Tema A: Variasi dan transparansi harga rumah sakit (internasional)
- **Relevansi:** kerangka analisis variasi harga, ukuran variasi (rasio persentil 90/10, koefisien variasi), dan masalah
  data chargemaster yang tidak memakai kode standar. Masalah yang terakhir ini sama dengan kasus kita.
- **Kata kunci:** hospital price variation; price transparency; chargemaster; shoppable services; negotiated rates;
  within-hospital variation; price dispersion.
- **String:** `("hospital price*" OR chargemaster) AND (variation OR dispersion OR transparency)`
- **Titik awal:**
  - Cooper, Craig, Gaynor, Van Reenen (2019). *The Price Ain't Right? Hospital Prices and Health Spending on the Privately
    Insured.* QJE 134(1). NBER WP 21815: https://www.nber.org/papers/w21815
  - Arvisais-Anhalt dkk. Studi 11 chargemaster dalam satu pasar lokal (155.576 item). Kode dan terminologi yang tidak standar
    menghambat perbandingan otomatis. https://www.thieme-connect.com/products/ejournals/html/10.1055/s-0041-1729168
  - Haque dkk. *Transparency, Accessibility, and Variability of US Hospital Price Data* (kepatuhan file machine-readable).
    https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8122228/
  - Studi JMIR Formative Research 2021 tentang sampel file DRG chargemaster. https://formative.jmir.org/2021/8/e26887
  - Studi Medical Care: 14 prosedur di 1.599 RS, rasio markup p90/p10. https://pubmed.ncbi.nlm.nih.gov/35948351/
- **Celah:** hampir semuanya berasal dari AS, dengan data yang sudah semi-terstruktur. Belum ada padanan untuk negara
  berkembang yang sumbernya regulasi PDF berbahasa non-Inggris.

### Tema B: Tarif rumah sakit di Indonesia (kebijakan dan empiris)
- **Relevansi:** konteks regulasi (retribusi daerah, BLUD, pola tarif nasional), hubungan tarif RS dengan INA-CBG dan unit
  cost, serta posisi kebaruan dataset.
- **Kata kunci (ID):** tarif RSUD; retribusi pelayanan kesehatan; pola tarif rumah sakit; unit cost; INA-CBG selisih tarif;
  BLUD tarif; Permenkes 85/2015; activity based costing rumah sakit.
- **Kata kunci (EN):** Indonesia hospital tariff; INA-CBG; JKN hospital payment; public hospital pricing Indonesia.
- **Database:** SINTA, Garuda (garuda.kemdikbud.go.id), Google Scholar, repositori UGM/UI/UNHAS, Neliti, jurnal JKKI,
  Jurnal Ekonomi Kesehatan Indonesia, Jurnal Administrasi Kesehatan Indonesia, BMC Health Services Research,
  Health Policy and Planning.
- **Titik awal (studi kasus satu RS; kontras dengan cakupan nasional kita):**
  - RSUD Kolonodale: selisih tarif RS dan INA-CBG pada pasien BPJS (JKKI 2019). https://jurnal.ugm.ac.id/jkki/article/download/37767/24782
  - RSUD Labuang Baji: unit cost hemodialisa dengan ABC vs INA-CBG. https://repository.unhas.ac.id/51805/2/K011211265-1-2.pdf
  - Tesis UGM tentang tarif riil vs INA-CBG (SC, rawat inap):
    https://etd.repository.ugm.ac.id/home/detail_pencarian_downloadfiles/583984 ,
    https://etd.repository.ugm.ac.id/penelitian/detail/245205
- **Regulasi yang perlu dibaca (cek nomor dan status berlaku):** Permenkes 85/2015 tentang Pola Tarif Nasional RS;
  UU 28/2009 tentang PDRD dan penggantinya UU 1/2022 tentang HKPD; regulasi BLUD (Permendagri 79/2018);
  regulasi tarif INA-CBG terbaru.
- **Celah:** studi Indonesia umumnya satu RS dan satu layanan (SC, HD), membandingkan tarif dengan INA-CBG atau unit cost.
  Belum ditemukan studi perbandingan tarif antar-RSUD skala nasional dari regulasi. Pencarian 2026-11 belum menemukannya,
  tetapi ini perlu dipastikan dengan pencarian sistematis.

### Tema C: Ekstraksi tabel dari PDF dan dokumen hasil scan
- **Relevansi:** pembanding untuk pipeline ekstraksi (aturan berbasis tata letak vs model deteksi struktur tabel vs LLM
  multimodal) dan metrik evaluasinya.
- **Kata kunci:** table extraction; table structure recognition; document layout analysis; OCR post-correction;
  end-to-end PDF parsing benchmark; GriTS; TEDS; historical/government document digitization.
- **Titik awal:**
  - Smock, Pesala, Abraham. *PubTables-1M: Towards comprehensive table extraction from unstructured documents* (CVPR 2022;
    Table Transformer). https://arxiv.org/abs/2110.00061
  - Benchmark ekstraksi tabel end-to-end dari PDF (2025): https://arxiv.org/pdf/2511.16134v1
  - Evaluasi parser PDF dengan evaluasi semantik LLM (2026): https://arxiv.org/html/2603.18652v1
- **Celah:** benchmark umumnya artikel ilmiah atau laporan keuangan berbahasa Inggris. Dokumen pemerintah hasil scan
  berbahasa Indonesia dengan tabel multi-halaman, judul kelas bertumpuk, dan sel nama multi-baris belum terwakili.
  Peluang kontribusi: set uji beranotasi.

### Tema D: Pemetaan terminologi dan entity linking lintas bahasa
- **Relevansi:** inti RQ2, yaitu memetakan nama layanan lokal berbahasa Indonesia ke ICD-9-CM dan LOINC.
- **Kata kunci:** biomedical entity linking; concept normalization; cross-lingual entity linking; LOINC mapping;
  procedure code mapping; terminology mapping; retrieval-based matching; SapBERT; multilingual embeddings; LLM coding.
- **Titik awal:**
  - Liu dkk. (2021). *Self-Alignment Pretraining for Biomedical Entity Representations* (SapBERT, NAACL 2021), dan versi
    lintas bahasa *Learning Domain-Specialised Representations for Cross-Lingual Biomedical Entity Linking* (ACL 2021).
    Cari di ACL Anthology.
  - Wang dkk. *Multilingual E5 Text Embeddings: A Technical Report* (2024). Model yang dipakai proyek ini.
  - *A Retrieval-Based Approach to Medical Procedure Matching in Romanian* (2025). Kasusnya paling mirip: nama prosedur
    klinik dipetakan ke daftar standar dengan embedding multilingual. https://arxiv.org/abs/2503.20556
  - BGLM: *big data-guided LOINC mapping with multi-language support* (JAMIA Open 2022).
    https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9696745/
  - MAP-CARE (Scientific Reports, 2026): LLM dan ruang embedding multilingual untuk klasifikasi prosedur (EN/DE/FR/IT).
    Verifikasi judul dan DOI sebelum dikutip.
- **Celah:** sumber berbahasa Indonesia, target ICD-9-CM prosedur, nama sangat bising (OCR, singkatan lokal), dan
  sebagian besar layanan tidak punya padanan kode (akomodasi, administrasi). Ini menuntut opsi "tidak ada padanan".

### Tema E: Knowledge graph kesehatan
- **Relevansi:** pembenaran pemakaian graf, pilihan skema (property graph vs RDF/OWL), dan evaluasi.
- **Kata kunci:** healthcare knowledge graph construction; medical ontology; property graph Neo4j; RDF OWL health data;
  price knowledge graph; graph-based entity matching.
- **Titik awal:**
  - *Healthcare Knowledge Graph Construction: State-of-the-art, open issues, and opportunities* (tinjauan sistematis).
    https://arxiv.org/abs/2207.03771 · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10225120/
  - Implementasi KG atas MIMIC-III dengan OWL dan GraphDB (Healthcare, 2023).
    https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10297905/
- **Celah:** KG kesehatan umumnya klinis (penyakit, obat, gen). KG untuk harga dan regulasi layanan hampir tidak ada.

### Tema F: Mutu data, verifikasi, dan human-in-the-loop
- **Relevansi:** cara melaporkan akurasi dataset hasil ekstraksi, desain sampel validasi, kesepakatan antar-anotator,
  dan label silver vs gold.
- **Kata kunci:** data quality assessment; error analysis information extraction; inter-annotator agreement Cohen kappa;
  active learning entity linking; human-in-the-loop coding; datasheets for datasets; dataset documentation.
- **Yang dicari:** standar pelaporan dataset (misalnya *Datasheets for Datasets*, Gebru dkk.), cara menghitung interval
  kepercayaan dari sampel validasi, dan desain sampel bertingkat.

### Tema G: Metodologi perbandingan harga yang adil
- **Relevansi:** menormalkan harga antar-tahun (deflator IHK/inflasi kesehatan BPS), antar-wilayah (indeks kemahalan
  konstruksi atau biaya hidup), kelas perawatan, komponen, dan BHP.
- **Kata kunci:** price index health services; deflating health prices; regional price adjustment; hedonic pricing hospital;
  multilevel model hospital prices.

---

## 4. Kriteria seleksi dan template ekstraksi literatur

**Inklusi:** peer-reviewed atau preprint dengan metode yang jelas; membahas salah satu tema A–G; data atau metode yang dapat
dibandingkan. **Eksklusi:** opini tanpa data; tanpa metode; duplikat versi (ambil versi terbit).

Catat setiap rujukan di `literatur/katalog.csv` dengan kolom:
`id, tema, penulis, tahun, judul, venue, doi_url, negara/bahasa_data, sumber_data, ukuran_data, tugas, metode,
metrik, hasil_utama, keterbatasan, relevansi_untuk_kita (1-3), dipakai_di_bagian, status_verifikasi`

---

## 5. Matriks keputusan metode (yang harus ditentukan penulis)

| Keputusan | Opsi | Untung | Rugi / risiko | Literatur yang perlu dibandingkan |
|---|---|---|---|---|
| **Ekstraksi tabel** | (1) Aturan tata letak + OCR (sekarang) · (2) Model struktur tabel (Table Transformer) · (3) LLM multimodal per halaman | (1) Dapat ditelusuri, murah, deterministik · (2) Umum · (3) Fleksibel terhadap tata letak baru | (1) Ekor pola panjang, butuh banyak aturan · (2) Perlu fine-tune untuk dokumen ID · (3) Mahal, bisa berhalusinasi angka, perlu verifikasi baris sumber | Tema C |
| **Ukur akurasi ekstraksi** | Cek visual acak (sekarang 40/putaran) · gold set beranotasi (≥300 baris, bertingkat per tipe dokumen) | Gold set memberi angka yang dapat dikutip dengan CI | Butuh waktu anotasi | Tema F |
| **Sistem kode prosedur** | ICD-9-CM Vol. 3 (dipakai INA-CBG untuk prosedur) · ICD-10-PCS · SNOMED CT · katalog lokal (Pola Tarif/KMK) | ICD-9-CM relevan untuk Indonesia (klaim JKN) | v32 CMS ≠ ICD-9-CM 2010 edisi Indonesia; banyak layanan tak berkode | Tema B, D |
| **Tingkat kode** | Kode daun (xx.xx) · kategori 3 digit (xx.x) · 2 digit (xx) | Daun paling spesifik | Akurasi turun di tingkat daun; analisis harga butuh kelompok yang cukup besar | Tema D, G |
| **Metode pemetaan** | Leksikal (TF-IDF) · embedding zero-shot (e5, sekarang) · SapBERT multilingual · fine-tune dengan pasangan PMIK · LLM re-ranker · hibrida | Hibrida + re-ranker biasanya terbaik | LLM mahal dan perlu kontrol halusinasi; fine-tune butuh label | Tema D |
| **"Tidak ada padanan"** | Ambang skor · kelas khusus · LLM verifikasi | Mencegah pemetaan paksa | Ambang perlu dev set terpisah | Tema D |
| **Pencocokan layanan antar-RS** | Nama identik · embedding · embedding + fitur graf | Graf memanfaatkan golongan dan kategori | Perlu evaluasi pasangan berlabel | Tema D, E |
| **Representasi** | Tabel relasional · property graph (Neo4j/NetworkX) · RDF/OWL | Property graph praktis untuk analisis; RDF untuk interoperabilitas | RDF lebih berat | Tema E |
| **Analisis harga** | Deskriptif (p90/p10, CV) · model multilevel (layanan × RS × wilayah × tahun) · hedonik | Multilevel memisahkan sumber variasi | Butuh kovariat RS (kelas RS, BLUD, kapasitas) | Tema A, G |
| **Normalisasi** | Kelas III sebagai acuan · semua kelas dengan efek tetap · deflasi ke tahun dasar | Kelas III paling sebanding antar-RS | Tidak semua RS punya kelas III untuk semua layanan | Tema G |

---

## 5a. Keputusan dan catatan dari diskusi 2026-11-23

- **Parser dibekukan** pada commit `cb968f4` (berkas `pilot/src/to_standard.py`). Perbaikan parser berikutnya hanya dari temuan
  gold set bagian *dev*; akurasi akhir diukur pada bagian *test* yang tidak dipakai memperbaiki.
- **Gold set dipisah per dokumen/RS**, bukan per baris. Dokumen yang pernah disentuh saat pengembangan (181 dokumen:
  sampel cek visual v3–v10 dan dokumen yang ditelusuri saat debugging) dikecualikan; daftarnya di
  `../pilot/eval/gold/dokumen_dikecualikan.csv`.
- **Verifikasi harga 99,9%** hanya mengukur konsistensi harga dengan teks baris (yang bisa berasal dari OCR), bukan kebenaran
  terhadap gambar halaman.
- **Jangan menilai reranker LLM dengan label silver buatan AI** (sirkular).
- **Awalan e5:** kode sekarang memakai `query:` di kedua sisi. Untuk tugas simetris (nama pendek ↔ nama pendek) itu sesuai
  model card; `query:`/`passage:` dijadikan eksperimen, bukan perbaikan bug.
- **LOINC:** repo private; notice dan langkah sebelum publikasi ada di `../Loinc_2.83/NOTICE_LOINC.md`. `Loinc.csv` 2.83
  memuat 7.355 istilah dengan `EXTERNAL_COPYRIGHT_NOTICE`, PanelsAndForms 15.711 baris. Untuk prior kepopuleran tes,
  pakai `COMMON_ORDER_RANK` (tes yang dipesan), bukan `COMMON_TEST_RANK`, sebagai prior kecil yang dibuktikan dengan ablation.
  Universal Lab Orders jangan jadi batas keras; ukur dulu di gold set berapa kode benar yang ada di luar himpunan itu.
- **Rujukan dari ulasan lain** (LabBridge, AGASN, GAME arXiv 2502.08547, S-GCN 2105.03701, BioELX 2605.27380, ICD Spanyol
  2605.30529, Peeters & Bizer 2310.11244, NHI Taiwan 2506.00209, PaddleOCR-VL 2510.14528): status *ditemukan, belum dibaca
  penuh*. Baca dan catat di katalog sebelum dikutip.

## 6. Keterbatasan yang wajib diakui di tulisan

- Tarif regulasi ≠ biaya riil atau harga yang dibayar pasien/JKN. Ini daftar tarif resmi, bukan klaim.
- Cakupan bergantung pada ketersediaan PDF di JDIH BPK. Ada RS tanpa peraturan publik, dan ada peraturan tanpa lampiran.
- Kesalahan ekstraksi pada sampel cek visual sekitar 7–10% baris (CI 95% Wilson untuk 3/40: 2,6–19,9%), terutama nama dan
  label kelas pada dokumen OCR dan tata letak khusus; angka ini bias optimistis (lihat §5a). Angka resmi menunggu gold set.
- Pemetaan kode masih usulan otomatis yang belum divalidasi. Label evaluasinya silver (dibuat asisten AI) dan berukuran kecil.
- ICD-9-CM yang dipakai adalah CMS v32, bukan edisi resmi Indonesia.
- Kategori standar masih kasar (55% "Tindakan Lain").

---

## 7. Aturan kerja untuk Claude dalam sesi literatur

1. **Jangan mengarang rujukan.** Setiap rujukan wajib punya URL atau DOI yang dapat dibuka. Bila belum dicek, tandai
   `status_verifikasi = belum` dan jangan dipakai sebagai kutipan.
2. Utamakan publikasi peer-reviewed. Preprint boleh dipakai dengan label "preprint".
3. Cari dua bahasa: kata kunci Indonesia di SINTA/Garuda/repositori universitas, kata kunci Inggris di Scopus, PubMed,
   ACL Anthology, arXiv, dan Google Scholar.
4. Untuk setiap rujukan, ringkas: data, metode, metrik, hasil, keterbatasan, dan **apa bedanya dengan proyek ini**.
5. Saat menimbang metode, kaitkan ke matriks §5 dan sebutkan bukti dari literatur, bukan opini.
6. Angka proyek diambil dari file di `../pilot/out/` dan `../pilot/eval/`, bukan dari ingatan. Bila file berubah,
   perbarui §1.
7. Simpan hasil di `literatur/katalog.csv` dan ringkasan tematik di `literatur/tinjauan.md`.

---

## 8. Glosarium singkat

- **ICD-9-CM Vol. 3:** klasifikasi prosedur. Strukturnya 2 digit (bab/kategori, mis. `89`) → 3 karakter (`89.5`) →
  4 karakter (`89.52` Elektrokardiogram). Daftar CMS v32: 3.882 kode valid (3.661 empat karakter, 221 tiga karakter
  tanpa turunan). Di Indonesia dipakai untuk kode prosedur pada INA-CBG.
- **ICD-10:** klasifikasi **diagnosis** (bukan prosedur). Strukturnya bab → blok → kategori 3 karakter (`A09`) →
  subkategori 4 karakter (`A09.0`). Tarif layanan pada umumnya prosedur atau pemeriksaan, sehingga tidak dipetakan ke ICD-10.
  Pengecualiannya tabel tarif berbasis kelompok INA-CBG (mis. "SEPTIKEMIA (RINGAN)"), yang turunan diagnosis ICD-10.
- **LOINC:** kode pemeriksaan laboratorium dan observasi. Proyek ini memakai Universal Lab Orders Value Set (1.519 tes).
- **BHP:** bahan habis pakai; menentukan apakah tarif sudah mencakup bahan.
- **Jasa sarana / jasa pelayanan:** komponen tarif (fasilitas RS vs tenaga kesehatan).
- **Golongan tindakan:** kelompok tindakan dengan satu tarif per kelas (kecil, sedang, besar, khusus, kelompok I–III).
