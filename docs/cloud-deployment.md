# Vercel, laptop dan database

Website: **https://nutritrack-food-nutrition.vercel.app/**

## Pembahagian tugas

| Bahagian | Tugas |
| --- | --- |
| Vercel website + Node API | Paparan langsung, sejarah, editor kalori, login pentadbir |
| Postgres dalam Vercel Storage (Neon) | Rekod makanan, kalori, waktu makan, sesi pentadbir dan barisan arahan |
| Vercel Blob private | Fail gambar; website membaca melalui API gambar |
| Laptop Python | Model CLIP, bacaan ESP32, outbox rekod dan penghubung HTTPS |
| ESP32 penimbang + ESP32-CAM | Berat, gambar, LCD, tare dan capture |

Tiada Supabase digunakan oleh aplikasi ini. Database Neon dan Blob dipautkan
kepada projek `nutritrack-food-nutrition` dalam Vercel Storage.

## Pada laptop yang telah disediakan ini

1. Pasang Python 3.12 64-bit jika belum ada. Dalam folder projek, jalankan sekali:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup_new_laptop.ps1
   ```

2. Sambungkan laptop dan kedua-dua ESP32 kepada WiFi yang sama. Upload kedua-dua
   sketch terkini mengikut README. Kamera masih menghantar JPEG kepada
   `http://IP_LAPTOP:5000/classify`, dan menghantar keputusan kepada IP penimbang.
   **Jangan tukar AI_SERVER_URL kepada Vercel:** model AI berjalan pada laptop.

3. Fail `data/cloud-bridge.local.json` sudah disediakan pada laptop ini. Fail ini
   mengandungi URL website, token peranti dan ID penghubung yang tetap. Ia rahsia
   dan diabaikan oleh Git; jangan masukkan kandungannya dalam screenshot atau repo.

4. Jalankan setiap kali menggunakan sistem:

   ```powershell
   .\start_ai_server.ps1 -ScaleUrl "http://IP_ESP32_PENIMBANG"
   ```

   Ganti IP contoh dengan IP penimbang daripada Serial Monitor. Tunggu `AI ready`
   dan `Cloud bridge started`. Kekalkan terminal dan laptop hidup, elakkan sleep.

5. Buka website Vercel dari telefon atau laptop. Website boleh dibuka melalui
   rangkaian lain; laptop penghubung memerlukan internet untuk menghantar bacaan.
   Akses pentadbir menggunakan kata laluan yang telah ditetapkan untuk website.

6. Tare dengan pinggan kosong, letakkan makanan dan tunggu berat stabil serta AI
   menerima gambar. Rekod disimpan dahulu pada SQLite laptop dan dihantar ke
   Postgres bersama gambar. Pengesanan berulang tidak mencipta hidangan sama.

Pada laptop lain, salin `cloud-bridge.local.json` secara peribadi daripada laptop
ini ke folder `data` projek baharu. Muat turun repo sahaja tidak membawa token
peranti atau database SQLite peribadi. IP laptop baharu dalam sketch kamera dan
`WEBSITE_URL` penimbang perlu dikemas kini. Gunakan satu laptop penghubung aktif
pada satu masa untuk projek ini.

## Cara kemas kini berlaku

- Laptop menghantar heartbeat kira-kira setiap 2 saat; website membaca status
  setiap saat. Gambar baharu tersedia mengikut kitaran kamera/inferens.
- Selepas 10 saat tanpa heartbeat, website menandakan laptop luar talian dan
  menyembunyikan bacaan berat/kalori langsung. Gambar terakhir kekal untuk rujukan.
- Rekod SQLite yang belum diakui cloud dicuba semula. Kunci hidangan unik di
  Postgres mengelakkan rekod berganda jika respons rangkaian terputus.
- Edit rujukan kalori pada website **cloud**. Laptop menerima katalog itu pada
  heartbeat berikutnya dan mengemas kini model tanpa restart.
- Edit sejarah pada website cloud menjadi rekod rasmi cloud. Selepas rekod lokal
  dihantar, edit lokal tidak menulis semula sejarah cloud; ini melindungi pembetulan
  pentadbir daripada ditimpa oleh outbox lama.

## Capture dan Tare dari website online

Website memasukkan arahan ke Postgres. Laptop mengambilnya melalui sambungan
HTTPS keluar dan menghantar arahan kepada ESP32 dalam WiFi yang sama. Status
berjaya/gagal dipulangkan ke website. Capture berjaya bermaksud permintaan gambar
diterima kamera, belum semestinya inferens selesai.

Arahan lama luput selepas 90 saat. Laptop menyimpan jurnal ID arahan supaya tare
tidak diulang selepas heartbeat dicuba semula atau laptop restart. Jika laptop
restart ketika arahan sedang berjalan, ia melaporkan keputusan tidak dapat
disahkan dan tidak mengulang arahan itu secara automatik.

## Kata laluan dan sesi

Password cloud disimpan sebagai hash PBKDF2 dengan salt dalam Postgres. Token sesi
raw tidak disimpan dalam database; hanya hash token. Cookie ialah HttpOnly,
Secure dan SameSite=Strict, tanpa had 30 minit. Logout membatalkan sesi dalam
database. Browser boleh membuang cookie sesi apabila ditutup.

Token peranti berbeza daripada kata laluan pentadbir. ESP32 tidak memerlukan
password cloud atau akses database. Fail `.env.local`, fail `*.local.json`,
database SQLite dan token tidak dimasukkan ke repo. Mengubah password server
lokal tidak mengubah password website cloud.

## Mod lokal sahaja

```powershell
.\start_ai_server.ps1 -ScaleUrl "http://IP_PENIMBANG" -NoCloud
```

Untuk website manual tanpa AI atau sambungan cloud:

```powershell
.\start_ai_server.ps1 -WebOnly -NoCloud
```

## Pembangunan dan deployment

```powershell
npm ci
npm run build
npm run test:cloud
python -m unittest discover -s tests -v
```

Vercel Git integration memaut kepada repo GitHub projek. Push ke branch produksi
`main` akan membina deployment baharu. `vercel.json` menghalakan API kepada
`api/index.mjs`; hanya fail dalam `web` disajikan sebagai aset statik.

`DATABASE_URL`, `DATABASE_URL_UNPOOLED` dan `BLOB_READ_WRITE_TOKEN` disediakan oleh
integrasi Vercel Storage. `NUTRITRACK_DEVICE_TOKEN` ialah Secret Vercel yang
sepadan dengan fail konfigurasi penghubung laptop. Jangan tampal nilai rahsia
ke kod atau commit `.env.local`.

Untuk projek baru sahaja, schema berada dalam `database/schema.sql`. Perintah
`npm run db:setup` memerlukan `.env.local` dan fail hash password peribadi
`data/cloud-credentials.local.json`. Ia tidak menimpa password yang sudah ada.

Pelan database yang dipilih ialah Free. Penggunaan tertakluk kepada kuota Neon,
Vercel Functions dan Blob dalam akaun Vercel; semak dashboard jika penggunaan
meningkat. Sandaran cloud dan kuota berbeza daripada salinan SQLite pada laptop.
