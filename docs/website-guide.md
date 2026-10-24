# Semua melalui website

Website utama: `http://<IP-laptop>:5000/`. Pada laptop sendiri buka
`http://127.0.0.1:5000/`. Telefon boleh membuka website yang sama jika berada
pada WiFi yang sama. Laptop dan server mesti sentiasa hidup. Ini website
rangkaian tempatan; belum dihoskan untuk akses internet luar rumah.

## Mula guna

1. Jalankan pemasangan dalam README sekali sahaja.
2. Dalam sketch penimbang, isi WiFi dan `WEBSITE_URL` kepada URL laptop.
3. Dalam sketch kamera, isi WiFi, `SCALE_URL` kepada IP penimbang dan
   `AI_SERVER_URL` kepada `http://<IP-laptop>:5000/classify`.
4. Upload semula **kedua-dua sketch**. Versi lama belum menghantar ID gambar,
   ID hidangan dan status sensor yang diperlukan untuk penyimpanan automatik.
5. Jalankan dari folder projek:

   ```powershell
   .\start_ai_server.ps1 -ScaleUrl "http://192.168.1.50"
   ```

   Tukar IP contoh kepada IP sebenar penimbang. URL ini tidak mengandungi
   `/api/food` atau `/api/status`. Pilihan lain ialah menetapkan
   `$env:FOOD_SCALE_URL` sebelum menjalankan server.
6. Tetapkan dan ulang kata laluan pentadbir (sekurang-kurangnya 8 aksara) pada
   terminal. Ia tidak dipaparkan semasa ditaip. Gunakan kata laluan itu untuk
   membuka akses pentadbir dalam website. Hash kata laluan disimpan dalam database supaya kata laluan yang sama
   digunakan selepas restart. Tiada kata laluan lalai dalam kod.
7. Tunggu `AI ready`, kemudian buka website. Benarkan Python melalui Windows
   Firewall pada rangkaian Private jika Windows meminta.

Automasi tempatan juga boleh menggunakan pemboleh ubah `FOOD_ADMIN_PASSWORD`.
Jangan commit kata laluan ke kod. Untuk menukar kata laluan yang telah
disimpan, tetapkan `FOOD_ADMIN_PASSWORD` ketika memulakan semula server;
selepas itu buang pemboleh ubah tersebut jika tidak diperlukan. Server menyimpan hash PBKDF2 berserta salt dalam database, bukan teks kata laluan.
Sesi pentadbir tiada had masa sepanjang sesi browser. Akses dikunci apabila
anda menekan Kunci akses pentadbir atau server dimulakan semula. Browser juga
boleh membuang cookie sesi apabila ditutup.
Selepas 5 kata laluan salah dalam satu minit, percubaan daripada IP itu
disekat sementara. Website HTTP ini untuk WiFi tempatan yang dipercayai;
akses internet memerlukan HTTPS dan konfigurasi hos berasingan.

## Paparan langsung

- Website membaca status ESP32 setiap kira-kira 1 saat dan memaparkan berat,
  kalori, status stabil, keyakinan AI dan gambar terkini tanpa refresh halaman.
- Gambar kamera diambil setiap 12 saat. `Ambil gambar` meminta gambar baharu;
  kamera mungkin mengambil masa sehingga 60 saat untuk inferens AI.
- Pentadbir boleh menekan `Tare / sifar` selepas pinggan kosong diletakkan.
- Bacaan yang terputus ditandakan luar talian dan tidak digunakan untuk
  menyimpan rekod baharu. Mod web sahaja juga ditandakan dengan jelas.

## Sejarah makanan

Rekod sensor disimpan apabila AI menerima gambar, penimbang stabil dan berat
melebihi 0 g. Gambar dan bacaan mesti mempunyai ID pengesanan dan ID hidangan
yang sepadan. Gambar ditolak atau sensor terputus tidak menghasilkan rekod.
Rekod mengandungi jenis makanan, berat gram, jumlah kalori, waktu dan gambar.

**Satu rekod bagi setiap hidangan:** pengesanan berulang setiap 12 saat tidak
menambah rekod yang sama. Selepas disimpan, perubahan berat hidangan yang sama
tidak menulis semula sejarah. Angkat makanan sehingga bacaan kembali ke sifar
atau tekan tare sebelum hidangan seterusnya. Jika perlu, edit berat/kalori
rekod melalui akses pentadbir.

Waktu automatik ialah waktu bacaan pertama berjaya disimpan, dalam waktu
Malaysia (UTC+08:00). Sistem tidak boleh menentukan waktu seseorang benar-benar
makan; pentadbir boleh membetulkan waktu makan pada borang edit.

Dalam `Sejarah makanan`, pentadbir boleh menambah rekod manual atau mengedit
jenis makanan, berat, jumlah kalori dan waktu makan. Gambar JPG/PNG/WebP boleh
dimuat naik (maksimum 2 MB). Gambar lama dikekalkan jika tiada gambar baharu.
Gunakan penapis tarikh untuk melihat rekod hari tertentu.

## Pangkalan kalori

Pentadbir boleh menambah jenis makanan serta mengubah nama, kalori per 100 g,
dan nota penyediaan. Contoh: nasi putih 130 kcal/100 g bermaksud 1.30 kcal/g.
Formula sensor: `berat (g) × kalori per gram`.

Perubahan digunakan pada pengesanan AI berikutnya tanpa restart. Rekod sejarah
mengekalkan kalori asal supaya perubahan rujukan tidak menukar rekod lama.
CLIP membandingkan gambar dengan nama kelas; menambah nama bukan proses
melatih model dan tidak menjamin makanan itu boleh dikenal pasti tepat.

CSV `data/food_calories.csv` digunakan sebagai data permulaan pada database
baharu sahaja. Selepas itu edit melalui website; perubahan CSV tidak menimpa
data pentadbir yang telah disimpan.

## Simpanan dan sandaran

Semua rekod, gambar dan rujukan kalori disimpan dalam
`data/nutrition.sqlite3`. Data kekal selepas browser atau server ditutup.
Tiada keperluan Blynk atau langganan database.

Untuk sandaran, hentikan server terlebih dahulu dan salin fail SQLite itu ke
lokasi selamat. Jangan jalankan dua server serentak menggunakan database yang
sama. Jika projek berada dalam OneDrive, elakkan membuka database yang sama
pada dua laptop serentak. Fail database diabaikan oleh Git kerana mengandungi
rekod dan gambar peribadi.

## Uji website tanpa hardware / model AI

```powershell
.\start_ai_server.ps1 -WebOnly
```

Atau gunakan Python dengan Pillow sahaja (tanpa PyTorch):

```powershell
python -m pip install "Pillow>=10.4,<12"
python tools\real_ai_server.py --web-only
```

Mod ini membolehkan rekod manual, gambar dan edit rujukan. Tiada bacaan sensor
atau pengesanan AI direka. Untuk menguji kod tanpa hardware sebenar:

```powershell
python -m unittest discover -s tests -v
```
