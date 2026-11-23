# Pemberitahuan LOINC

Folder ini memuat sebagian file LOINC **versi 2.83** (Regenstrief Institute) yang dipakai untuk usulan kode laboratorium:
`LoincTable/Loinc.csv`, `LoincTable/MapTo.csv`, `AccessoryFiles/LoincUniversalLabOrdersValueSet/`,
`AccessoryFiles/PanelsAndForms/`.

Repo ini private. Sebelum dataset, kode, atau repo dipublikasikan:
1. Cantumkan pemberitahuan hak cipta LOINC berikut (cocokkan teks dan tahunnya dengan file lisensi di paket unduhan
   LOINC 2.83, karena teks ini disalin dari format umum lisensi LOINC, bukan dari file lisensi paket ini):

   > This material contains content from LOINC (http://loinc.org). LOINC is copyright © 1995-[tahun], Regenstrief
   > Institute, Inc. and the Logical Observation Identifiers Names and Codes (LOINC) Committee and is available at no cost
   > under the license at http://loinc.org/license. LOINC® is a registered United States trademark of Regenstrief
   > Institute, Inc.

2. Untuk setiap istilah yang kolom `EXTERNAL_COPYRIGHT_NOTICE`-nya terisi (terutama di PanelsAndForms):
   cantumkan juga pemberitahuan pihak ketiga itu, **atau** keluarkan baris tersebut dari bahan yang dipublikasikan.
3. Catat versi LOINC (2.83) di dataset dan paper agar pemetaan bisa diulang.
4. Pertimbangkan untuk tidak menyertakan tabel LOINC sendiri di repo publik; cukup tulis cara mengunduhnya dari loinc.org.
