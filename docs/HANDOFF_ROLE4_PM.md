# Handoff Visualisasi Role 4 untuk PM

Role 4 sudah menghasilkan peta interaktif, tiga grafik, dan tiga notebook mandiri. Prioritas sebelum presentasi adalah memperjelas pesan utama setiap visual dan memastikan semua file bisa dipakai di perangkat presentasi. Tinjauan ini mengacu pada commit `ba2593e`.

## Yang sudah baik dan yang perlu diperbaiki

| Visual | Yang sudah baik | Yang perlu diperbaiki |
| --- | --- | --- |
| [Peta interaktif](../figures/city_magnets_map.html) | Peta bisa dibuka offline. Batas kota dan kabupaten membantu orientasi. Pengguna bisa memilih periode, melihat cakupan data, dan mengeklik kotak 500 m untuk membaca rinciannya. | Pada 1–15 Februari, hanya 1.628 dari 5.715 kotak yang punya data cukup untuk dibandingkan. Tampilkan angka ini saat menjelaskan hasil. Jalan utama belum tersedia, sehingga orientasi saat memperbesar peta masih terbatas. |
| [Grafik hari kerja dan akhir pekan](../figures/weekday_weekend_ratio.png) | Keempat periode memakai skala yang sama. Kotak yang berisi kampus cenderung punya porsi perangkat lebih tinggi pada hari kerja di keempat periode. Garis menunjukkan ketidakpastian perkiraan. | Grafik cukup padat untuk ukuran slide. Sorot contoh kampus, jelaskan bahwa 1,0 berarti kedua porsi sama, dan pastikan garis ketidakpastian tetap terlihat. |
| [Grafik Natal dan Tahun Baru](../figures/nataru_timeseries.png) | Tiap kategori fasilitas punya panel sendiri. Panel bawah menunjukkan cakupan data harian. Pergantian sampel pada 1 Januari ditandai. | Ganti kata “normal” dengan “hari pembanding yang jatuh pada hari yang sama dalam seminggu.” Biarkan nilai 1 Januari kosong. Jelaskan perubahan yang terlihat tanpa menyimpulkan bahwa liburan menyebabkannya. |
| [Heatmap kapanewon](../figures/kapanewon_diurnal_heatmap.png) | Perbandingan jam puncak sudah konkret. Pada Desember, Gamping bergeser dari pukul 12.00 ke 11.00, Banguntapan dari 19.00 ke 14.00, dan Kasihan tetap pukul 20.00 saat akhir pekan. | Beri ruang lebih besar untuk panel kiri pada slide. Panel kanan menunjukkan jumlah sinyal per perangkat. Sebutkan bulan yang dipilih saat menjelaskan hasil. |

## Prioritas sebelum presentasi

1. **PM dan Role 4.** Cek visual pada ukuran slide yang akan dipakai. Minta satu anggota tim menjelaskan temuan utama dari masing-masing visual tanpa diberi petunjuk. Perbaiki judul, label, atau keterangan yang masih membingungkan.
2. **Role 4.** Unduh HTML peta dari GitHub dan uji offline di laptop presentasi. Cek pergantian periode, cakupan hari kerja dan akhir pekan, panel detail kotak, serta label lokasi.
3. **Role 4.** Jalankan ketiga notebook di Google Colab dengan **Runtime → Run all**. Ketiganya sudah berhasil di Jupyter lokal. Jalankan ulang di Colab dan cocokkan grafiknya dengan file PNG yang akan dipakai.
4. **PM dan Role 4.** Catat periode yang akan dipakai di slide. Peta yang tersedia terbuka pada 1–15 Februari 2022. Heatmap yang tersedia memakai Desember 2021.

## Penyempurnaan setelah pengecekan

Tambahkan jalan utama jika tersedia data jalan yang bisa disertakan secara offline dan sumbernya bisa dicantumkan. Cek kembali label saat peta diperbesar dan tata letak pada layar kecil. Jika tim sering memperbarui grafik, dokumentasikan langkah memperbarui data dan gambar yang tersimpan di notebook.

Handoff ini siap ditutup ketika tim bisa menjelaskan satu hasil dari tiap visual, ketiga notebook berhasil di Colab, dan peta berjalan offline di laptop presentasi. Penyempurnaan ini berada dalam lingkup Role 4 dan memakai tabel hasil dari pipeline yang sudah digabungkan.

Panduan teknis dan perintah untuk membuat ulang visual tersedia di [handoff teknis Role 4](HANDOFF_ROLE4.md).
