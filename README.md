# Topic Lens — proyek Python untuk eksplorasi topik

Repository private: [Recallya/topic-lens](https://github.com/Recallya/topic-lens).

Dashboard lokal berbahasa Indonesia untuk memilih topik, crawling RSS/HTML, membuat word cloud, dan melihat jumlah artikel selama lima tahun terakhir. Gunakan **Yearly**, **Monthly**, **Daily**, atau **Last 5 hours**. Backend memakai Python + Flask, penyimpanan memakai SQLite, dan UI memakai HTML/CSS/JavaScript tanpa CDN.

## 1. Jalankan aplikasi

Di PowerShell, masuk ke folder proyek:

```powershell
cd C:\Users\Administrator\Documents\Python\HTML\self-project
.\.venv\Scripts\python.exe main.py
```

Buka **http://127.0.0.1:5000**. Hentikan server dengan `Ctrl+C`.

Jika port tersebut dipakai aplikasi lain:

```powershell
.\.venv\Scripts\python.exe main.py --port 5001
```

Pada komputer baru, setelah memasang Python (disarankan 3.11 atau lebih baru) dan Git, buat lingkungan sendiri:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Versi yang diuji di komputer ini dicatat dalam `requirements-lock.txt`. Untuk mereplikasi dependensi tersebut, gunakan `-r requirements-lock.txt`. Proyek ini telah diuji pada Python 3.9 yang tersedia di komputer ini.

`.venv` memisahkan paket proyek ini dari proyek lain. Menjalankan Python melalui path tersebut tidak memerlukan aktivasi atau perubahan execution policy PowerShell.

## 2. Coba alurnya

1. Halaman awal menampilkan **Mode demo** dengan label **Data simulasi**. Angka dan kata dibuat untuk mencoba UI, bukan informasi tren nyata. Data demo tidak pernah disimpan ke database.
2. Pilih topik yang tersedia atau ketik topik sendiri. Klik **Lihat analisis topik**. Topik yang pernah disimpan akan muncul dalam daftar.
3. Pilih sumber ANTARA atau BBC, atau masukkan maksimal tiga URL RSS/HTML. Klik **Mulai crawling**. Koneksi internet diperlukan.
4. Setelah selesai, UI otomatis beralih ke hasil nyata. Kegagalan sumber, hasil kosong, dan jumlah duplikat diberi informasi. Hasil tersimpan di `data/topics.sqlite3`.
5. Ganti periode untuk mengubah grafik, word cloud, daftar kata, dan artikel secara bersamaan.
6. Untuk riwayat lama, impor arsip CSV bertanggal melalui bagian **Lengkapi riwayat 5 tahun**.

Pencocokan topik bersifat literal: setiap kata pada topik harus ditemukan sebagai kata utuh dalam judul atau teks. Contoh `energi bersih` cocok dengan artikel yang memuat kedua kata itu. Ini belum mencakup sinonim atau klasifikasi semantik.

## 3. Pahami apa yang diukur

**Trending di aplikasi ini berarti puncak jumlah artikel dalam sampel yang terkumpul, bukan indeks popularitas seluruh internet atau Google Trends.** Banyaknya sumber, batas crawling, dan kelengkapan arsip memengaruhi hasil.

| Tampilan | Rentang | Pengelompokan |
| --- | --- | --- |
| Yearly | Lima tahun berjalan sampai saat ini | Tahun kalender |
| Monthly | Lima tahun berjalan sampai saat ini | Bulan kalender |
| Daily | Lima tahun berjalan sampai saat ini | Hari kalender |
| Last 5 hours | Tepat lima jam sebelum permintaan analisis | Interval 10 menit |

Semua label waktu memakai WIB. Lima tahun berjalan dapat menyentuh enam label tahun kalender karena tahun pertama dan terakhir parsial. Hal yang sama berlaku untuk batas bulan, hari, dan interval 10 menit.

- Grafik memakai **tanggal terbit**, bukan waktu crawling. Waktu crawling disimpan terpisah.
- Interval tanpa artikel ditandai **belum ada data**, bukan angka nol yang mengklaim tidak ada pembahasan. Garis tidak disambungkan melewati interval kosong.
- Artikel tanpa tanggal terbit tetap disimpan, tetapi tidak masuk visualisasi berbasis periode.
- Tanggal tanpa jam hanya masuk Yearly/Monthly/Daily. Timestamp tanpa zona waktu dianggap WIB; sebaiknya selalu sertakan `+07:00` atau `Z`.
- Artikel masa depan dan di luar rentang tidak masuk perhitungan.
- Word cloud menghitung kata dari judul dan teks/ringkasan pada periode aktif, menghapus kata umum Indonesia/Inggris. Belum ada stemming atau analisis sentimen.
- URL yang sama dalam topik yang sama disimpan sekali. Duplikasi antar-URL atau sindikasi belum disatukan.

**RSS terbaru tidak menyediakan arsip lima tahun secara otomatis.** UI mendukung analisis lima tahun, tetapi data nyata untuk rentang itu harus berasal dari arsip yang Anda impor atau kumpulkan. Belum ada konektor arsip berbayar/Google Trends pada versi ini. API Google Trends resmi memiliki jalur akses alpha dan dokumentasi sumber tersendiri: [Google Trends API](https://developers.google.com/search/apis/trends).

## 4. Impor data historis

CSV UTF-8 harus memiliki kolom `title,text,url,published_at`; `source` opsional. Maksimal 5 MB dan 10.000 baris per impor. Contoh **format saja**, bukan data nyata:

```csv
title,text,url,published_at,source
"Riset energi bersih","Inovasi energi untuk industri",https://example.com/artikel-1,2023-04-15T09:30:00+07:00,Arsip saya
"Kebijakan energi","Pengembangan energi terbarukan",https://example.com/artikel-2,2024-06-20,Arsip saya
```

Impor memakai topik yang tertulis pada input topik. Baris yang tidak cocok, tanggal/URL yang tidak valid, serta duplikat dilaporkan. Gunakan URL asli untuk artikel nyata. File hanya diproses secara lokal; aplikasi tidak mengunduh URL dalam CSV.

## 5. Belajar struktur proyek

```text
self-project/
  main.py              # Titik masuk: menjalankan server lokal
  app.py               # Route HTTP dan penghubung komponen
  crawler.py           # Mengambil RSS/HTML dan tanggal publikasi
  storage.py           # Menyimpan/membaca artikel di SQLite
  analytics.py         # Filter waktu, agregasi, frekuensi kata
  templates/index.html # Struktur tampilan
  static/style.css     # Warna, layout, tampilan responsif
  static/app.js        # Interaksi UI, grafik SVG, word cloud
  tests/test_project.py
  requirements.txt
  requirements-lock.txt
  data/                # Dibuat otomatis dan diabaikan Git
```

Alur datanya:

```text
Browser → POST /api/crawl → Crawler → SQLite
Browser → GET /api/analysis → Filter + hitung → JSON → Grafik + word cloud
```

`GET` membaca data. `POST` meminta pekerjaan atau mengimpor data. JSON adalah format pertukaran data antara Python dan JavaScript. Crawling berjalan di thread terpisah agar UI tetap bisa meminta status proses. SQLite menyimpan data sebagai satu file, tanpa server database tambahan.

Latihan bertahap:

1. Ubah warna `--teal` pada `static/style.css`, lalu muat ulang browser.
2. Tambahkan topik pilihan di `templates/index.html`.
3. Tambahkan kata umum ke `STOPWORDS` pada `analytics.py` dan bandingkan word cloud.
4. Baca `analyze()` untuk memahami mengapa data difilter **sebelum** dihitung per interval.

## 6. Jalankan pemeriksaan

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Tes tidak membutuhkan internet. Tes mencakup batas lima tahun/lima jam, WIB, tanggal kosong, RSS/Atom/HTML, filter topik, deduplikasi, impor, endpoint UI, dan pemisahan demo dari database.

## 7. Simpan ke Git dan publish source

Repository memakai branch `main` dan remote `origin` ke `Recallya/topic-lens`. Identitas commit lokal memakai akun Recallya dengan email noreply GitHub. Jika Anda menggunakan akun berbeda pada salinan proyek sendiri, ganti identitas contoh berikut:

```powershell
git config user.name "Nama Anda"
git config user.email "EMAIL_COMMIT_ANDA"
git status
git add .
git diff --cached
git commit -m "Build Topic Lens Python dashboard"
```

`git add` menyiapkan perubahan; `git diff --cached` menampilkan perubahan yang akan disimpan; `git commit` menyimpan snapshot lokal. `.venv`, `.env`, dan `data/` diabaikan oleh `.gitignore`.

Remote proyek ini sudah terhubung. Untuk mengunggah commit berikutnya:

```powershell
git push
```

Pembaruan berikutnya: edit → jalankan/tes → `git add` → `git commit` → `git push`.

**Push menerbitkan source code ke repository private, bukan menjalankan aplikasi online.** Server ini sengaja berjalan di `127.0.0.1` untuk pembelajaran lokal. Deployment publik memerlukan WSGI server, autentikasi, antrean job persisten, serta pengamanan egress/DNS lebih lanjut. Aplikasi belum di-deploy ke hosting.

## Batas crawler

- Mengikuti `robots.txt`, memakai user-agent `TopicLensBot/1.0`, dan jeda minimal satu detik per origin (lebih lama bila crawl-delay meminta).
- Jika robots tidak bisa dibaca, crawling sumber itu dilewati. Respons 404/410 robots diperlakukan sebagai tidak adanya aturan.
- RSS/Atom dianalisis dari judul dan isi/ringkasan feed. Halaman HTML mengambil paragraf artikel/main dan tautan satu tingkat pada domain yang sama, sesuai batas jumlah artikel.
- Tidak menjalankan JavaScript situs, menembus login/paywall, atau menjamin kelengkapan berita.
- Ada batas ukuran respons 2 MB, timeout HTTP, dan validasi alamat publik/redirect. Aplikasi ini untuk penggunaan lokal tepercaya, bukan layanan crawler publik.
- Crawling hanya berjalan saat tombol ditekan. Tidak ada scheduler; tampilan 5 jam bukan streaming otomatis. Muat ulang analisis untuk memperbarui batas waktunya.

Jika sumber tidak mengizinkan crawling, gunakan sumber lain atau arsip yang berhak Anda akses. Jika hasil kosong, periksa kata topik, isi feed terkini, periode, dan pesan hasil proses.

Pada sesi pengembangan ini, tes unit dan server lokal berhasil, tetapi uji RSS langsung terkendala `ProxyError` pada jaringan lingkungan kerja. Jadi pengambilan berita langsung belum terverifikasi end-to-end di jaringan ini. Mode demo dan impor lokal tetap bisa digunakan. Untuk menguji koneksi sumber setelah jaringan/proxy tersedia, jalankan `.\.venv\Scripts\python.exe -u tools/smoke_crawl.py`.
