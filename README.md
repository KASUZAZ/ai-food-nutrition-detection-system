# AI-Based Food Nutrition Detection System

Sistem ini menggunakan inferens AI sebenar. ESP32-CAM mengambil gambar makanan dan menghantar JPEG kepada model CLIP pada laptop. ESP32 kedua membaca berat daripada load cell, menerima keputusan AI, mengira kalori, dan memaparkan hasil pada LCD serta dashboard WiFi.

```text
Jumlah kalori = berat makanan (g) x kalori per gram
```

## Aliran Sistem

```mermaid
flowchart LR
  A["Makanan"] --> B["ESP32-CAM"]
  B -->|"JPEG melalui WiFi"| C["Real AI server + CLIP"]
  C -->|"Nama, kcal/g, confidence"| D["ESP32 penimbang"]
  E["Load cell + HX711"] -->|"Berat gram"| D
  D --> F["LCD 16x2"]
  D --> G["Web dashboard / Blynk"]
```

Tiada `DEMO_MODE` atau keputusan makanan palsu dalam kod semasa. Jika keyakinan AI terlalu rendah, server menolak keputusan dan ESP32 mengekalkan bacaan makanan terakhir.

## Fail Utama

```text
arduino/esp32_cam_detection_sender/esp32_cam_detection_sender.ino
arduino/esp32_scale_nutrition/esp32_scale_nutrition.ino
tools/real_ai_server.py
data/food_calories.csv
requirements-ai.txt
START_SETUP.cmd
START_AI_SERVER.cmd
CONFIGURE_DEVICE.cmd
```

## 1. Sediakan AI Server Pada Laptop

Laptop, ESP32-CAM, dan ESP32 penimbang mesti menggunakan rangkaian WiFi yang sama.

### Laptop Baharu (Windows 10/11)

1. Download repository sebagai ZIP daripada GitHub dan extract seluruh folder ke laluan pendek, contohnya `C:\AI-Food-Nutrition-System`.
2. Double-click `START_SETUP.cmd`.
3. Setup akan memasang Python 3.12, environment AI, PyTorch/Transformers, model AI, Arduino CLI, ESP32 core, library `HX711`, dan `LiquidCrystal I2C` jika belum ada.
4. Masukkan WiFi, password WiFi, IP laptop, dan IP ESP32 scale apabila wizard meminta. Nilai ini disimpan dalam fail `secrets.h` pada laptop pengguna sahaja dan tidak akan masuk GitHub.
5. Upload ESP32 scale dahulu. Selepas Serial Monitor menunjukkan Scale IP, double-click `CONFIGURE_DEVICE.cmd` untuk memasukkan IP sebenar sebelum upload ESP32-CAM.

Setiap kali mahu guna sistem, double-click:

```text
START_AI_SERVER.cmd
```

Kali pertama setup boleh mengambil masa kerana model AI dan ESP32 toolchain dimuat turun. Benarkan Python melalui Windows Firewall pada rangkaian Private jika diminta.

### Apa Yang Setup Automatik Buat

| Bahagian | Automatik | Perlu pengguna buat sendiri |
| --- | --- | --- |
| Perisian laptop | Python 3.12, AI packages, model AI, Arduino CLI, ESP32 core dan library | Sambungan internet diperlukan |
| Konfigurasi | Jana `secrets.h` tempatan untuk WiFi/IP | Masukkan WiFi dan IP sebenar apabila ditanya |
| Hardware | Sediakan toolchain untuk compile/upload | Wiring, sambung USB/FTDI, upload board dan kalibrasi load cell |
| Penggunaan harian | `START_AI_SERVER.cmd` hidupkan server AI | Hidupkan ESP32, letak makanan dan tunggu `LOCK` |

### Pemasangan Manual

Jika skrip PowerShell tidak boleh digunakan, jalankan arahan ini dari folder projek:

```powershell
py -3.12 -m venv C:\food-ai-venv
C:\food-ai-venv\Scripts\python.exe -m pip install --upgrade pip
C:\food-ai-venv\Scripts\python.exe -m pip install -r requirements-ai.txt
C:\food-ai-venv\Scripts\python.exe tools\real_ai_server.py
```

Laluan pendek `C:\food-ai-venv` digunakan kerana PyTorch mempunyai nama fail dalaman yang panjang dan boleh melepasi had laluan Windows jika venv diletakkan di dalam folder projek OneDrive ini.

Kali pertama sahaja, model `openai/clip-vit-base-patch32` akan dimuat turun. Selepas keluar mesej `AI ready`, semak:

```text
http://127.0.0.1:5000/health
http://127.0.0.1:5000/
```

Dashboard AI memaparkan gambar sebenar terakhir, makanan yang dikesan, confidence, dan status diterima atau ditolak.

Cari IPv4 laptop dengan:

```powershell
ipconfig
```

Gunakan IPv4 adapter WiFi, contohnya `192.168.1.10`. Benarkan Python melalui Windows Firewall jika diminta.

## 2. Upload ESP32 Penimbang

Buka:

```text
arduino/esp32_scale_nutrition/esp32_scale_nutrition.ino
```

WiFi akan dijana automatik dalam fail tempatan ini selepas `START_SETUP.cmd`:

```cpp
arduino/esp32_scale_nutrition/secrets.h
```

Jangan upload atau commit `secrets.h` ke GitHub. Ia sudah dikecualikan oleh `.gitignore`.

Sambungan hardware:

| Modul | ESP32 |
| --- | --- |
| HX711 DT | GPIO 19 |
| HX711 SCK | GPIO 18 |
| LCD SDA | GPIO 21 |
| LCD SCL | GPIO 22 |
| Semua GND | GND bersama |

Upload dan catat `Scale IP` daripada Serial Monitor, contohnya `192.168.1.50`.

## 3. Upload ESP32-CAM

Buka:

```text
arduino/esp32_cam_detection_sender/esp32_cam_detection_sender.ino
```

`START_SETUP.cmd` menjana fail tempatan ini untuk WiFi, IP penimbang, dan IP laptop:

```cpp
arduino/esp32_cam_detection_sender/secrets.h
```

Selepas ESP32 scale siap upload, dapatkan Scale IP pada Serial Monitor dan double-click `CONFIGURE_DEVICE.cmd` untuk kemas kini `NUTRITION_SCALE_URL`. Jika alamat IP laptop berubah, jalankan fail yang sama sekali lagi.

Pilih board `AI Thinker ESP32-CAM`, aktifkan PSRAM jika pilihan itu tersedia, kemudian upload. Kod akan mengambil gambar sebenar setiap 12 saat, menyalakan LED flash, meminta inferens AI, dan menghantar keputusan yang sah kepada ESP32 penimbang.

## 4. Operasi Sebenar

1. Jalankan `real_ai_server.py` dan tunggu `AI ready`.
2. Hidupkan ESP32 penimbang dan lakukan tare tanpa makanan.
3. Hidupkan ESP32-CAM.
4. Letakkan satu jenis makanan di tengah pinggan, dengan pencahayaan jelas.
5. Tunggu AI mengesan makanan dan bacaan berat menjadi `LOCK`.
6. LCD akan memaparkan contoh berikut:

```text
Rice      150g
195 kcal LOCK
```

Dashboard ESP32 penimbang boleh dibuka pada `http://<Scale-IP>/`. Endpoint status ialah `http://<Scale-IP>/api/status`, dan tare boleh dibuat melalui `http://<Scale-IP>/api/tare`.

## Kelas Makanan Dan Kalori

Model membandingkan gambar dengan semua nama dalam `data/food_calories.csv`. Tambah atau ubah makanan di situ, kemudian restart server AI. Nilai ialah anggaran kalori per gram, bukan analisis makmal.

Untuk projek akhir, gunakan kelas yang rupa visualnya jelas dan ambil gambar contoh sebenar bagi setiap kelas untuk menguji threshold. Default server menerima keputusan jika confidence sekurang-kurangnya `0.35` dan beza dengan pilihan kedua sekurang-kurangnya `0.08`.

Threshold boleh dilaras tanpa mengubah kod:

```powershell
python tools\real_ai_server.py --confidence 0.30 --margin 0.05
```

## Blynk Pilihan

Dalam sketch penimbang, tukar `ENABLE_BLYNK` kepada `1` dan isi template/token. Virtual pin: `V0` berat, `V1` kalori, `V2` makanan, `V3` status lock, dan `V4` confidence.

## Batasan Jujur

- CLIP menjalankan klasifikasi imej sebenar, tetapi bukan model yang dilatih khas dengan gambar projek ini.
- Satu imej dianggap mempunyai satu makanan utama; makanan bercampur memerlukan object detection atau segmentation.
- Anggaran kalori bergantung pada nilai CSV dan tidak mengukur protein, lemak, atau karbohidrat secara langsung.
- Untuk ketepatan projek yang lebih tinggi, kumpulkan dataset daripada kamera sendiri dan fine-tune model menggunakan kelas makanan sasaran.
