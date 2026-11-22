# 📌 Handoff Balik untuk Akhnaf — Penyelesaian & Finalisasi Role 4 (Visualization)

**Dari:** Altaf (PM / Role 1)  
**Untuk:** Akhnaf (Role 4 — Geospatial Visualization & Interactive Map Lead)  
**Branch:** `main` & `role4/visualization` (sudah disinkronkan penuh)  
**Status:** ✅ **Role 4 100% Selesai & Merged ke `main`** (`40/40 pytest passed`)

---

## 1. TL;DR

Karena keterbatasan token di sesimu sebelumnya, kami sudah mengambil alih dan menuntaskan **seluruh daftar perbaikan di [`docs/HANDOFF_ROLE4_PM.md`](HANDOFF_ROLE4_PM.md)** sekaligus melengkapi permintaan visual **RQ1 Facility Pull** dari [`docs/HANDOFF_ROLE3.md`](HANDOFF_ROLE3.md) (§5).

Semua pekerjaanmu tetap menjadi fondasi utama Role 4 (`src/visualize.py`, `figures/`, dan notebook Colab), dan sekarang sudah dipoles, dilengkapi *unit tests*, dijalankan ulang dengan data Gold asli, serta di-merge ke `main`.

---

## 2. Cara Sinkronisasi Repo Lokalmu (`git pull`)

Sebelum membuka atau mengubah file di laptopmu, jalankan perintah ini di terminal:

```bash
git fetch --all
git checkout main
git pull origin main

# Jika kamu masih ingin berada di branch role4/visualization:
git checkout role4/visualization
git pull origin role4/visualization
```

*(Kedua branch `main` dan `role4/visualization` sudah menunjuk ke commit terbaru yang sama).*

---

## 3. Apa Saja yang Sudah Kita Bantu Selesaikan di Atas Kerjaanmu

### A. Tindak Lanjut Checklist [`docs/HANDOFF_ROLE4_PM.md`](HANDOFF_ROLE4_PM.md)

| Item di `HANDOFF_ROLE4_PM.md` | Masalah Sebelumnya | Solusi yang Sudah Diterapkan | File Terkait |
| :--- | :--- | :--- | :--- |
| **1. Jalan utama di Peta Interaktif** | Jalan utama belum tersedia secara offline sehingga orientasi saat zoom-in terbatas. | Menambahkan geometri jalan utama DIY (`trunk` & `primary` highway dari OSM under ODbL, 62 KB) ke `src/assets/yogyakarta/roads.geojson` yang langsung ter-embed **offline** di HTML, ditambah opsi layer **Street basemap (online)** (CARTO Positron). | [`src/assets/yogyakarta/roads.geojson`](../src/assets/yogyakarta/roads.geojson)<br>[`figures/city_magnets_map.html`](../figures/city_magnets_map.html) |
| **2. Label Landmark di Peta** | Baru ada 4 label landmark (`UGM`, `Prambanan`, `Stasiun Wates`, `RSUD Wonosari`). | Melengkapi menjadi **9 landmark** (seluruh 6 landmark *Week 1 DIY Audit*: **UGM, UNY, RSUP Dr. Sardjito, Pakuwon Mall, Plaza Ambarrukmo, Malioboro Mall** + 3 anchor regional) dengan arah tooltip (`top`/`bottom`/`left`/`right`) yang tidak saling bertumpuk. | [`src/visualize.py`](../src/visualize.py)<br>[`figures/city_magnets_map.html`](../figures/city_magnets_map.html) |
| **3. Grafik Hari Kerja vs. Akhir Pekan (RQ2)** | Grafik cukup padat untuk slide; perlu sorotan pada kampus, penjelasan garis `1.0`, dan legenda garis ketidakpastian. | Menebalkan (*bold* biru) label **Campuses** di sumbu-Y pada keempat panel periode, serta menambahkan kotak legenda di bagian bawah untuk menjelaskan **Bar** (`All eligible cells ≥90%`), **Garis Hitam** (`95% site-cluster bootstrap CI`), **Diamond Putih** (`Single-category cells only`), dan **Garis Putus-putus** (`1.0 = Equal weekday & weekend share`). | [`figures/weekday_weekend_ratio.png`](../figures/weekday_weekend_ratio.png)<br>[`notebooks/weekday_weekend_ratio.ipynb`](../notebooks/weekday_weekend_ratio.ipynb) |
| **4. Grafik Natal & Tahun Baru (RQ3)** | Kata *"normal"* kurang tepat secara metodologis; nilai 1 Januari harus jelas terlihat kosong/di-withhold. | Mengganti kata *"normal"* menjadi ***"matched same-weekday baseline"***, menambahkan label teks langsung **`1 Jan break (withheld)`** pada pita vertikal 1 Januari, menampilkan jumlah *supported cells* di setiap judul panel (mis. `Campuses (69–75 cells)`), dan menambahkan kotak panduan baca (*How to read this chart*) di slot kanan-bawah. | [`figures/nataru_timeseries.png`](../figures/nataru_timeseries.png)<br>[`notebooks/nataru_timeseries.ipynb`](../notebooks/nataru_timeseries.ipynb) |
| **5. Heatmap Kapanewon (RQ4)** | Panel kiri (`Median observed devices`) butuh ruang lebih besar untuk slide dibanding panel kanan (`Median pings per device`). | Mengatur `gridspec_kw={"width_ratios": [1.3, 1.0]}` sehingga panel kiri lebih lebar, memperjelas keterangan `○ = peak hour` di judul panel kiri, dan menandai panel kanan sebagai `(reporting intensity)`. | [`figures/kapanewon_diurnal_heatmap.png`](../figures/kapanewon_diurnal_heatmap.png)<br>[`notebooks/kapanewon_diurnal_heatmap.ipynb`](../notebooks/kapanewon_diurnal_heatmap.ipynb) |

---

### B. Tambahan Deliverables Sesuai [`docs/HANDOFF_ROLE3.md`](HANDOFF_ROLE3.md) & Standar Tim

1. **Chart & Notebook Baru untuk RQ1 Facility Pull (`facility_pull.png` & `facility_pull.ipynb`):**
   * Menambahkan fungsi `pull()` di [`src/visualize.py`](../src/visualize.py) yang memvisualisasikan `data/gold/facility_pull.parquet` (median porsi kehadiran hari kerja `%` per kategori di 4 periode utama, 95% *site-cluster bootstrap CI*, titik porsi akhir pekan, dan garis referensi *baseline candidates*).
   * Membuat standalone Google Colab notebook [`notebooks/facility_pull.ipynb`](../notebooks/facility_pull.ipynb) dengan *embedded data snapshot* seperti 3 notebook Colab buatanmu.
2. **Eksekusi Penuh [`notebooks/visuals.ipynb`](../notebooks/visuals.ipynb):**
   * Sebelumnya cell di `visuals.ipynb` masih belum di-run (`outputs: []`). Sekarang sudah dieksekusi penuh terhadap data Silver & Gold asli, lengkap dengan preview ke-5 visual + tabel diagnostik (`matched_comparison`, `coverage_sensitivity`, `event_window`) sehingga langsung tampil saat dibuka di GitHub.
3. **Automated Contract & Guardrail Tests ([`tests/test_role4_visualize.py`](../tests/test_role4_visualize.py)):**
   * Menambahkan **8 unit tests** khusus Role 4 untuk memastikan ke-5 file di `figures/` ter-generate valid, Leaflet & jalan utama ter-embed offline, ke-9 landmark ada di peta, dan ke-4 guardrail statistik Role 3 (tidak mem-plot baris `withheld` sebagai nol, memisahkan 1 Januari, tidak menggabungkan lintas `sampling_period`) terjaga.
   * Total test suite sekarang: **`python -m pytest -q tests/` $\rightarrow$ 40 passed, 0 warnings** (Role 1: 5, Role 2: 7, Role 3: 20, Role 4: 8).
4. **Penyempurnaan [`docs/HANDOFF_ROLE4.md`](HANDOFF_ROLE4.md) & [`README.md`](../README.md):**
   * Melengkapi `HANDOFF_ROLE4.md` dengan tabel pemenuhan spesifikasi brief, panduan interpretasi 5 visual, dan rangkuman angka temuan RQ1–RQ4.
   * Menambahkan status **`Role 4 status: ✅ Complete`** dan bagian **Key Findings & Visual Gallery (RQ1–RQ4)** di halaman depan `README.md`.

---

## 4. Cheat-Sheet Angka & Poin Narasi Bagianmu (Role 4) untuk Video 5 Menit eLOK & Presentasi

Saat kamu membawakan bagian **Visualisasi & Temuan Akhir** (~1,25 menit di video eLOK dan saat presentasi kelas), kamu bisa langsung memakai angka-angka yang sudah terverifikasi di grafikmu ini:

1. **Peta Interaktif 500 m (`figures/city_magnets_map.html`):**
   * Dari **5.715 kotak grid ($500\text{ m} \times 500\text{ m}$)** di DIY, pada periode dengan cakupan terluas (**1–15 Februari 2022**) terdapat **1.628 kotak ($28,5\%$)** yang lolos syarat cakupan publikasi $\ge 90\%$ di hari kerja *dan* akhir pekan.
   * Dari 1.628 kotak tersebut: **829 kotak ($\ge 1,05$, warna teal)** condong ke hari kerja (*weekday-leaning*), **498 kotak ($< 0,95$, warna oranye)** condong ke akhir pekan (*weekend-leaning*), dan **301 kotak ($0,95\text{–}<1,05$)** seimbang.
2. **RQ1 — Facility Pull (`figures/facility_pull.png`):**
   * Kotak yang memuat fasilitas secara konsisten memiliki median porsi kehadiran hari kerja (*restricted presence share*) lebih tinggi dibanding kotak pembanding tanpa fasilitas terpetakan (*baseline candidates*) di keempat periode utama.
   * **Malls** ($0,103\%\text{–}0,316\%$) dan **Campuses** ($0,067\%\text{–}0,191\%$) selalu menempati posisi teratas di atas *baseline candidates* ($0,023\%\text{–}0,119\%$).
3. **RQ2 — Weekly Rhythm & Hipotesis H1–H3 (`figures/weekday_weekend_ratio.png`):**
   * **H1 (Campuses):** **Terbukti konsisten di 4 dari 4 periode utama** (rasio $> 1,0$), yaitu **$1,291$** (Des 2021), **$1,152$** (1–15 Feb), dan **$1,138$** (16–28 Feb), serta turun mendekati $1,0$ (**$1,022$**) pada **Januari 2022** saat masa libur antar-semester. Hasil ini tetap kokoh pada subset *single-category* (simbol diamond $\diamond$) maupun ambang cakupan $80\% / 90\% / 95\%$.
   * **H2 (Malls, Markets, Tourism):** Menunjukkan pola musiman yang berbeda-beda; pada **Januari 2022** ketiganya berbalik condong ke akhir pekan (**Malls $0,893$**, **Tourism $0,964$**, **Markets $0,969$**). Khusus **Markets**, kotak *single-category* ($\diamond$) jauh lebih dekat ke $1,0$ ($0,98\text{–}1,04$) dibanding kotak *mixed-use*.
   * **H3 (Hospitals):** Condong ke hari kerja ($1,012\text{–}1,290$) karena jadwal poliklinik rawat jalan dan lokasi di pusat kota, namun di bawah kampus pada bulan Februari.
4. **RQ3 — Holiday Shockwave / Nataru (`figures/nataru_timeseries.png`):**
   * Dibandingkan dengan hari yang sama di luar periode libur pada bulan yang sama, kehadiran relatif di kotak **Tourism** naik **$+29\%$ ($1,29\times$)** pada Hari Natal (`25 Des 2021`), lalu turun **$-36\%$ ($0,64\times$)** pada pertengahan minggu (`29 Des 2021`) sebelum pulih menjelang malam Tahun Baru.
   * **1 Januari 2022** dikosongkan (*withheld*) karena cakupan grid turun mendadak dari $27,5\%$ ke $23,9\%$ akibat pergantian sampel hulu (*sample break*), sehingga kita tidak menyimpulkan penurunan perangkat pada 1 Januari sebagai efek liburan.
5. **RQ4 — Diurnal Pulse Kapanewon (`figures/kapanewon_diurnal_heatmap.png`):**
   * Pada Desember 2021, kapanewon pusat kampus/perkotaan mencapai puncak di siang hari pada hari kerja (**Gamping** pukul `12.00 WIB` $\rightarrow$ bergeser ke `11.00 WIB` di akhir pekan; **Depok** pukul `13.00 WIB`).
   * Kapanewon komuter/permukiman mencapai puncak di malam hari pada hari kerja dan bergeser maju ke siang hari saat akhir pekan (**Banguntapan** dari `19.00 WIB` $\rightarrow$ `14.00 WIB`; **Kasihan** tetap di `20.00 WIB`).
   * Panel kanan (`median_pings_per_maid`) adalah diagnostik intensitas sinyal aplikasi (terlihat lebih tinggi di **Seyegan** dan **Pakem**, serta turun serentak pukul `08.00–10.00 WIB`), bukan ukuran jumlah orang.

---

## 5. Checklist Terakhir untuk Akhnaf (Ringan & Tanpa Coding)

- [ ] Jalankan `git pull` di repo lokalmu.
- [ ] Unduh [`figures/city_magnets_map.html`](../figures/city_magnets_map.html) dan buka di browser laptop yang akan dipakai presentasi (uji klik kotak 500 m, ganti layer periode, toggle *Major roads*, dan dropdown *Color by*).
- [ ] Uji buka keempat notebook Colab di `notebooks/` (`facility_pull.ipynb`, `weekday_weekend_ratio.ipynb`, `nataru_timeseries.ipynb`, `kapanewon_diurnal_heatmap.ipynb`) lewat Google Colab (**Runtime → Run all**).
