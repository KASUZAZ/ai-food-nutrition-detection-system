from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "Panduan_Pemasangan_AI_Food_Nutrition_System.pdf"
PHOTO = ROOT / "assets" / "pdf" / "system-overview.png"

PAGE_W, PAGE_H = A4
MARGIN = 1.55 * cm
INK = colors.HexColor("#17212B")
MUTED = colors.HexColor("#5D6B76")
GREEN = colors.HexColor("#087A5A")
GREEN_LIGHT = colors.HexColor("#E8F5EF")
TEAL = colors.HexColor("#0C8E99")
YELLOW = colors.HexColor("#F2B233")
YELLOW_LIGHT = colors.HexColor("#FFF4D8")
RED = colors.HexColor("#B73A3A")
RED_LIGHT = colors.HexColor("#FBE9E9")
LINE = colors.HexColor("#D6DEE3")
PALE = colors.HexColor("#F5F7F8")


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "GuideTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=32,
            textColor=INK,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "GuideSubtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=12,
            leading=17,
            textColor=MUTED,
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "GuideH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=25,
            textColor=INK,
            spaceBefore=0,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "GuideH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=GREEN,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "GuideBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.8,
            leading=14,
            textColor=INK,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "GuideSmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=MUTED,
        ),
        "code": ParagraphStyle(
            "GuideCode",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.7,
            leading=10,
            textColor=INK,
            backColor=PALE,
            borderColor=LINE,
            borderWidth=0.4,
            borderPadding=7,
            spaceBefore=3,
            spaceAfter=8,
        ),
        "step": ParagraphStyle(
            "GuideStep",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=INK,
            leftIndent=21,
            firstLineIndent=-21,
            spaceAfter=6,
        ),
        "cover_note": ParagraphStyle(
            "CoverNote",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=GREEN,
        ),
    }


S = styles()


class Box(Flowable):
    def __init__(self, title, text, color=GREEN, fill=GREEN_LIGHT, width=17.5 * cm):
        super().__init__()
        self.title = title
        self.text = text
        self.color = color
        self.fill = fill
        self.width = width
        title_p = Paragraph(f"<b>{title}</b>", S["body"])
        text_p = Paragraph(text, S["body"])
        self.parts = [title_p, text_p]
        self.height = sum(p.wrap(width - 18, 1000)[1] for p in self.parts) + 17

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        self.height = sum(p.wrap(self.width - 18, 1000)[1] for p in self.parts) + 17
        return self.width, self.height

    def draw(self):
        self.canv.setFillColor(self.fill)
        self.canv.setStrokeColor(self.color)
        self.canv.roundRect(0, 0, self.width, self.height, 5, fill=1, stroke=1)
        y = self.height - 9
        for part in self.parts:
            _, h = part.wrap(self.width - 18, 1000)
            y -= h
            part.drawOn(self.canv, 9, y)


class NumberedStep(Flowable):
    def __init__(self, number, title, text, width=17.5 * cm):
        super().__init__()
        self.number = str(number)
        self.title = title
        self.text = text
        self.width = width
        self.paragraph = Paragraph(f"<b>{title}</b><br/>{text}", S["body"])
        self.height = 42

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        _, h = self.paragraph.wrap(self.width - 42, 1000)
        self.height = max(34, h + 12)
        return self.width, self.height

    def draw(self):
        self.canv.setFillColor(GREEN)
        self.canv.circle(14, self.height - 16, 12, fill=1, stroke=0)
        self.canv.setFillColor(colors.white)
        self.canv.setFont("Helvetica-Bold", 10)
        self.canv.drawCentredString(14, self.height - 19.5, self.number)
        self.canv.setStrokeColor(LINE)
        self.canv.line(33, 2, 33, self.height - 2)
        self.paragraph.drawOn(self.canv, 43, 7)


class FlowDiagram(Flowable):
    def __init__(self, width=17.5 * cm):
        super().__init__()
        self.width = width
        self.height = 5.2 * cm

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def _node(self, x, y, w, h, title, sub, fill):
        c = self.canv
        c.setFillColor(fill)
        c.setStrokeColor(GREEN if fill == GREEN_LIGHT else TEAL)
        c.roundRect(x, y, w, h, 7, fill=1, stroke=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(x + w / 2, y + h - 16, title)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.2)
        c.drawCentredString(x + w / 2, y + 12, sub)

    def _arrow(self, x1, y, x2):
        c = self.canv
        c.setStrokeColor(MUTED)
        c.setLineWidth(1.4)
        c.line(x1, y, x2 - 6, y)
        c.setFillColor(MUTED)
        c.setStrokeColor(MUTED)
        c.line(x2 - 9, y + 4, x2 - 4, y)
        c.line(x2 - 9, y - 4, x2 - 4, y)

    def draw(self):
        c = self.canv
        w = (self.width - 54) / 4
        y = 45
        h = 58
        self._node(0, y, w, h, "Makanan", "di atas platform", YELLOW_LIGHT)
        self._node(w + 18, y, w, h, "ESP32-CAM", "ambil gambar JPEG", GREEN_LIGHT)
        self._node(2 * (w + 18), y, w, h, "AI di laptop", "kenal jenis makanan", GREEN_LIGHT)
        self._node(3 * (w + 18), y, w, h, "ESP32 scale", "kira dan papar", GREEN_LIGHT)
        for x in [w, 2 * w + 18, 3 * w + 36]:
            self._arrow(x, y + h / 2, x + 18)
        c.setStrokeColor(TEAL)
        c.setLineWidth(1.5)
        c.line(22, 31, self.width - 22, 31)
        c.setFillColor(TEAL)
        c.setFont("Helvetica-Bold", 8.2)
        c.drawCentredString(self.width / 2, 14, "Load cell + HX711 menghantar berat kepada ESP32 scale")


class WiringDiagram(Flowable):
    def __init__(self, width=17.5 * cm):
        super().__init__()
        self.width = width
        self.height = 9.1 * cm

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def _module(self, x, y, w, h, title, lines, fill):
        c = self.canv
        c.setFillColor(fill)
        c.setStrokeColor(INK)
        c.roundRect(x, y, w, h, 7, fill=1, stroke=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + w / 2, y + h - 17, title)
        c.setFont("Helvetica", 7.5)
        yy = y + h - 31
        for line in lines:
            c.drawString(x + 9, yy, line)
            yy -= 12

    def _line(self, x1, y1, x2, y2, color, label):
        c = self.canv
        c.setStrokeColor(color)
        c.setLineWidth(2)
        c.line(x1, y1, x2, y2)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString((x1 + x2) / 2, (y1 + y2) / 2 + 4, label)

    def draw(self):
        c = self.canv
        esp_x = self.width / 2 - 50
        self._module(esp_x, 82, 100, 125, "ESP32 SCALE", ["GPIO 19 = HX711 DT", "GPIO 18 = HX711 SCK", "GPIO 21 = LCD SDA", "GPIO 22 = LCD SCL", "3.3V dan GND"], GREEN_LIGHT)
        self._module(8, 120, 105, 80, "HX711", ["DT -> GPIO 19", "SCK -> GPIO 18", "VCC -> 3.3V", "GND -> GND"], YELLOW_LIGHT)
        self._module(self.width - 113, 120, 105, 80, "LCD I2C", ["SDA -> GPIO 21", "SCL -> GPIO 22", "VCC -> 3.3V*", "GND -> GND"], colors.HexColor("#E7F1FA"))
        self._module(8, 10, 105, 72, "LOAD CELL", ["Sambung ke terminal", "E+, E-, A+, A-", "pada HX711"], PALE)
        self._line(113, 172, esp_x, 172, TEAL, "DT / SCK")
        self._line(esp_x + 100, 162, self.width - 113, 162, TEAL, "SDA / SCL")
        self._line(60, 82, 60, 120, RED, "4 way cable")
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 7.2)
        c.drawString(8, 0, "* Jika LCD menggunakan pull-up 5V, gunakan level shifter atau modul I2C yang serasi 3.3V.")


def P(text, style="body"):
    return Paragraph(text, S[style])


def bullet(text):
    return P(f"&#8226; {text}", "body")


def page_title(title, kicker):
    return [P(kicker.upper(), "small"), P(title, "h1")]


def table(data, widths, header=True):
    rows = []
    for row in data:
        rows.append([P(str(cell), "small") for cell in row])
    table_obj = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
    for index in range(1 if header else 0, len(rows)):
        if index % 2 == 0:
            commands.append(("BACKGROUND", (0, index), (-1, index), PALE))
    table_obj.setStyle(TableStyle(commands))
    return table_obj


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, PAGE_H - 1.15 * cm, PAGE_W - MARGIN, PAGE_H - 1.15 * cm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(MARGIN, PAGE_H - 0.82 * cm, "AI Food Nutrition Detection System - Panduan Pemasangan")
    canvas.drawRightString(PAGE_W - MARGIN, 0.75 * cm, f"Halaman {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, 1.08 * cm, PAGE_W - MARGIN, 1.08 * cm)
    canvas.restoreState()


def cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#F4F7F6"))
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(GREEN)
    canvas.rect(0, PAGE_H - 1.1 * cm, PAGE_W, 1.1 * cm, fill=1, stroke=0)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawRightString(PAGE_W - MARGIN, 0.8 * cm, "Versi pemasangan praktikal - 2026")
    canvas.restoreState()


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=1.65 * cm,
        bottomMargin=1.45 * cm,
        title="Panduan Pemasangan AI Food Nutrition Detection System",
        author="AI Food Nutrition Detection System",
    )
    story = []

    # Cover
    story += [Spacer(1, 0.35 * cm), P("PANDUAN PEMASANGAN", "cover_note"), P("AI Food Nutrition Detection System", "title"), P("Panduan dari A sampai Z untuk ESP32-CAM, ESP32, load cell, HX711, LCD I2C dan server AI sebenar.", "subtitle")]
    story += [Image(str(PHOTO), width=17.4 * cm, height=11.6 * cm), Spacer(1, 0.35 * cm)]
    story += [Box("Hasil akhir yang anda mahu", "Letak makanan atas platform. Kamera mengambil gambar. Laptop mengenal makanan. ESP32 membaca berat dan LCD memaparkan anggaran kalori.", GREEN, GREEN_LIGHT), Spacer(1, 0.35 * cm)]
    story += [P("Sesuai untuk pelajar, pensyarah dan pengguna yang baru bermula. Ikut langkah mengikut turutan dan jangan sambung kuasa sebelum wiring diperiksa.", "body"), PageBreak()]

    # Quick map
    story += page_title("Sistem ini buat apa?", "1. Gambaran keseluruhan")
    story += [P("Sistem menggunakan dua papan: <b>ESP32-CAM</b> untuk gambar dan <b>ESP32 scale</b> untuk load cell serta LCD. Laptop menjalankan model AI. Ketiga-tiganya mesti berada pada rangkaian WiFi yang sama.")]
    story += [FlowDiagram(), Spacer(1, 0.2 * cm)]
    story += [table([
        ["Komponen", "Tugas mudah"],
        ["ESP32-CAM", "Ambil gambar makanan dan hantar JPEG ke laptop."],
        ["Laptop + AI server", "Kenal makanan, contohnya Banana atau Rice."],
        ["Load cell + HX711", "Tukar berat makanan kepada bacaan gram."],
        ["ESP32 scale + LCD", "Kira kalori dan paparkan keputusan."],
    ], [4.2 * cm, 13.3 * cm]), Spacer(1, 0.25 * cm)]
    story += [Box("Formula yang digunakan", "<b>Kalori = berat (gram) x kalori per gram.</b><br/>Contoh: 150 g nasi x 1.30 kcal/g = 195 kcal.", TEAL, colors.HexColor("#E8F5F7")), PageBreak()]

    # Before beginning
    story += page_title("Sediakan semuanya dahulu", "2. Sebelum mula")
    story += [P("Sediakan semua komponen di atas meja dan pastikan komputer boleh menyambung ke WiFi. Jangan gunakan power bank lemah atau kabel USB longgar ketika upload.")]
    story += [table([
        ["Perlu ada", "Kegunaan"],
        ["1 x ESP32 DevKit", "Papan untuk penimbang, HX711 dan LCD."],
        ["1 x AI Thinker ESP32-CAM", "Papan kamera untuk gambar makanan."],
        ["1 x load cell + HX711", "Mengukur berat makanan."],
        ["1 x LCD I2C 16x2", "Paparan nama makanan, berat dan kalori."],
        ["USB cable + FTDI programmer", "Upload ESP32 biasa dan ESP32-CAM."],
        ["Laptop Windows + WiFi", "Menjalankan AI server."],
        ["Jumper wires dan bekalan 5V stabil", "Sambungan dan kuasa."],
    ], [6.2 * cm, 11.3 * cm]), Spacer(1, 0.25 * cm)]
    story += [Box("Penting sebelum kuasa", "Pastikan <b>semua GND disambung bersama</b>. Sambung atau cabut kabel hanya apabila kuasa USB ditanggalkan.", RED, RED_LIGHT), PageBreak()]

    # Placement
    story += page_title("Susun peralatan seperti ini", "3. Susunan fizikal")
    story += [P("Kamera mesti nampak makanan dengan jelas. Letakkan kamera lebih kurang 25 hingga 40 cm dari pinggan. Pastikan lampu bilik terang dan elakkan tangan menutup makanan ketika kamera mengambil gambar.")]
    story += [Image(str(PHOTO), width=17.4 * cm, height=11.6 * cm), Spacer(1, 0.22 * cm)]
    story += [table([
        ["Bahagian", "Kedudukan yang baik"],
        ["Makanan", "Satu jenis makanan utama, di tengah pinggan/platform."],
        ["ESP32-CAM", "Menghadap makanan. Jangan terlalu dekat sehingga gambar kabur."],
        ["Load cell", "Atas permukaan rata dan stabil. Jangan sentuh platform ketika membaca berat."],
        ["Laptop", "Sambung WiFi yang sama dengan dua ESP32."],
    ], [4.2 * cm, 13.3 * cm]), PageBreak()]

    # Wiring
    story += page_title("Wiring ESP32 penimbang", "4. Sambungan utama")
    story += [P("Gunakan ESP32 DevKit untuk bahagian penimbang. Ikut nombor GPIO di bawah, bukan nombor fizikal pin pada board.")]
    story += [WiringDiagram(), Spacer(1, 0.15 * cm)]
    story += [table([
        ["Dari", "Ke ESP32 scale", "Nota"],
        ["HX711 DT", "GPIO 19", "Data berat."],
        ["HX711 SCK", "GPIO 18", "Clock HX711."],
        ["LCD SDA", "GPIO 21", "Data I2C."],
        ["LCD SCL", "GPIO 22", "Clock I2C."],
        ["HX711/LCD GND", "GND", "Wajib berkongsi GND."],
    ], [4.3 * cm, 4.0 * cm, 9.2 * cm]), Spacer(1, 0.2 * cm)]
    story += [Box("Load cell ke HX711", "Wayar load cell tidak selalu menggunakan warna yang sama. Ikut label pada HX711: <b>E+</b>, <b>E-</b>, <b>A+</b>, <b>A-</b>. Jika berat bergerak songsang atau kosong, periksa datasheet load cell dan sambungan A+/A-.", YELLOW, YELLOW_LIGHT), PageBreak()]

    # ESP CAM upload
    story += page_title("Sediakan ESP32-CAM", "5. Kamera dan upload")
    story += [P("ESP32-CAM memerlukan USB-to-Serial atau FTDI untuk upload. Semasa upload, sambungan GPIO0 ke GND memberitahu board supaya masuk ke mod flash.")]
    story += [table([
        ["FTDI / USB serial", "ESP32-CAM", "Tujuan"],
        ["5V", "5V", "Kuasa. Gunakan sumber 5V stabil."],
        ["GND", "GND", "Ground bersama."],
        ["TX", "U0R / RX0", "Data dari FTDI ke kamera."],
        ["RX", "U0T / TX0", "Data dari kamera ke FTDI."],
        ["GPIO0", "GND", "Sambung hanya semasa upload."],
    ], [5.0 * cm, 4.6 * cm, 7.9 * cm]), Spacer(1, 0.24 * cm)]
    story += [NumberedStep(1, "Sambung FTDI", "Gunakan sambungan jadual di atas. TX dan RX perlu bersilang."), NumberedStep(2, "Masuk mod upload", "Sambung GPIO0 kepada GND, kemudian tekan butang RESET pada ESP32-CAM."), NumberedStep(3, "Upload sketch", "Pilih board AI Thinker ESP32-CAM di Arduino IDE dan tekan Upload."), NumberedStep(4, "Jalankan kamera", "Selepas upload selesai, cabut GPIO0 dari GND dan tekan RESET sekali lagi.")]
    story += [Box("Jika upload gagal", "Cuba baud rate 115200, periksa kabel USB, guna bekalan 5V yang lebih stabil, dan pastikan GPIO0 benar-benar ke GND sebelum tekan RESET.", RED, RED_LIGHT), PageBreak()]

    # Software
    story += page_title("Setup satu klik pada laptop baharu", "6. AI server sebenar")
    story += [P("Panduan ini sesuai untuk Windows 10/11 baharu. Pengguna tidak perlu memasang Python atau Arduino secara manual. Internet diperlukan pada kali pertama sahaja.")]
    story += [NumberedStep(1, "Download dan extract", "Download GitHub ZIP, kemudian extract seluruh folder ke laluan pendek seperti C:\\AI-Food-Nutrition-System."), NumberedStep(2, "Double-click setup", "Double-click START_SETUP.cmd. Jangan tutup tetingkap hitam yang terbuka."), NumberedStep(3, "Biarkan setup bekerja", "Ia memasang Python 3.12, AI packages, model AI, Arduino CLI, ESP32 core, HX711 dan LiquidCrystal I2C."), NumberedStep(4, "Isi konfigurasi", "Masukkan WiFi, password, IP laptop dan Scale IP apabila wizard bertanya. Password disimpan tempatan sahaja."), NumberedStep(5, "Mulakan AI harian", "Selepas setup siap, double-click START_AI_SERVER.cmd dan buka http://127.0.0.1:5000.")]
    story += [P("START_SETUP.cmd", "code"), Box("Jika IP scale belum diketahui", "Upload ESP32 scale dahulu. Baca Scale IP daripada Serial Monitor, kemudian double-click <b>CONFIGURE_DEVICE.cmd</b> dan masukkan IP baharu itu sebelum upload ESP32-CAM.", YELLOW, YELLOW_LIGHT)]
    story += [Box("Penting", "Windows Firewall mungkin bertanya tentang Python. Pilih <b>Allow access</b> pada Private networks supaya ESP32-CAM boleh menghubungi laptop.", YELLOW, YELLOW_LIGHT), PageBreak()]

    # Software config
    story += page_title("Konfigurasi WiFi dan alamat IP", "7. Fail local secrets")
    story += [P("Anda tidak perlu edit sketch untuk WiFi atau IP. START_SETUP.cmd menjana fail <b>secrets.h</b> pada setiap folder sketch. Fail ini hanya berada pada laptop pengguna dan sudah diabaikan oleh Git.")]
    story += [P("ESP32 scale menggunakan:", "h2")]
    story += [P('arduino/esp32_scale_nutrition/secrets.h', "code")]
    story += [P("ESP32-CAM menggunakan:", "h2")]
    story += [P('arduino/esp32_cam_detection_sender/secrets.h', "code")]
    story += [table([
        ["Alamat", "Cara dapatkan"],
        ["IP laptop", "Setup cuba mengesan IPv4 aktif. Semak semula jika laptop menggunakan WiFi/rangkaian lain."],
        ["IP ESP32 scale", "Upload sketch scale, buka Serial Monitor 115200, kemudian cari teks Scale IP."],
        ["Kemas kini IP", "Double-click CONFIGURE_DEVICE.cmd bila IP laptop atau IP scale berubah."],
    ], [4.2 * cm, 13.3 * cm]), Spacer(1, 0.25 * cm)]
    story += [Box("IP boleh berubah", "Alamat IP biasanya diberi oleh router secara automatik. Jika WiFi/router berubah atau laptop reboot, double-click CONFIGURE_DEVICE.cmd dan masukkan nilai baharu. Jangan commit secrets.h ke GitHub.", YELLOW, YELLOW_LIGHT), PageBreak()]

    # Arduino code
    story += page_title("Upload kedua-dua sketch", "8. Arduino IDE")
    story += [P("Pasang Arduino IDE dan ESP32 board support dahulu. Kemudian install library berikut melalui Library Manager: <b>HX711</b> dan <b>LiquidCrystal_I2C</b>.")]
    story += [table([
        ["Board", "Fail untuk dibuka", "Setting utama"],
        ["ESP32 DevKit", "arduino/esp32_scale_nutrition/esp32_scale_nutrition.ino", "Pilih port ESP32 biasa. Serial Monitor 115200."],
        ["AI Thinker ESP32-CAM", "arduino/esp32_cam_detection_sender/esp32_cam_detection_sender.ino", "Pilih AI Thinker ESP32-CAM. Aktifkan PSRAM jika pilihan ada."],
    ], [3.5 * cm, 8.0 * cm, 6.0 * cm]), Spacer(1, 0.22 * cm)]
    story += [NumberedStep(1, "Upload scale dahulu", "Selepas berjaya, lihat LCD dan catat Scale IP pada Serial Monitor."), NumberedStep(2, "Masukkan Scale IP", "Tukar SCALE_URL dalam sketch ESP32-CAM kepada IP itu."), NumberedStep(3, "Upload ESP32-CAM", "Cabut GPIO0 ke GND selepas upload dan reset board."), NumberedStep(4, "Semak serial output", "Kamera perlu menunjukkan WiFi connected dan AI server perlu menerima gambar.")]
    story += [Box("Kalibrasi berat", "Nilai calibration factor awal ialah 183.37. Jika 100 g tidak dibaca sebagai 100 g, laraskan nilai ini sedikit demi sedikit, upload semula, dan uji dengan objek berat diketahui.", TEAL, colors.HexColor("#E8F5F7")), PageBreak()]

    # First run sequence
    story += page_title("Hidupkan sistem dalam urutan ini", "9. Ujian pertama")
    story += [NumberedStep(1, "Jalankan AI server", "Pastikan dashboard laptop dibuka dan status AI ONLINE."), NumberedStep(2, "Hidupkan ESP32 scale", "Tunggu LCD siap. Lakukan tare tanpa makanan menggunakan endpoint /api/tare atau fungsi tare dalam sketch."), NumberedStep(3, "Hidupkan ESP32-CAM", "Kamera menyambung WiFi dan akan mengambil gambar secara berkala."), NumberedStep(4, "Letak satu makanan", "Letak satu jenis makanan atas platform dan jangan sentuh load cell."), NumberedStep(5, "Tunggu status LOCK", "Bacaan berat dikunci apabila stabil. LCD patut memaparkan makanan, gram dan kcal."), NumberedStep(6, "Semak dashboard", "Dashboard laptop patut menunjukkan gambar sebenar, nama makanan dan confidence.")]
    story += [Box("Contoh hasil berjaya", "<b>Banana - 120 g - 107 kcal - LOCK</b><br/>Kiraan: 120 x 0.89 kcal/g. Nilai kalori ialah anggaran daripada dataset makanan.", GREEN, GREEN_LIGHT), PageBreak()]

    # Troubleshoot
    story += page_title("Masalah biasa dan penyelesaian", "10. Troubleshooting")
    story += [table([
        ["Masalah", "Periksa dahulu", "Cara baiki"],
        ["LCD kosong", "SDA/SCL, kuasa dan alamat I2C", "Semak GPIO 21/22. Cuba alamat LCD 0x27 atau 0x3F mengikut modul."],
        ["Berat tidak stabil", "Platform, wiring load cell dan calibration factor", "Letak atas meja rata, jangan sentuh platform, semak sambungan HX711."],
        ["HX711 ERROR", "DT/SCK dan GND", "Semak GPIO 19/18, GND bersama dan kuasa HX711."],
        ["Kamera tidak hantar data", "AI_SERVER_URL dan WiFi", "Pastikan laptop dan kamera WiFi yang sama, server sedang hidup dan firewall dibenarkan."],
        ["AI salah kenal", "Cahaya, jarak dan makanan campur", "Guna satu makanan utama, cahaya terang, kamera tetap. Tambah kelas dalam CSV jika perlu."],
        ["Upload ESP32-CAM gagal", "GPIO0, RESET dan kuasa", "GPIO0 ke GND, tekan RESET, guna 5V stabil dan baud 115200."],
    ], [4.0 * cm, 5.7 * cm, 8.0 * cm]), Spacer(1, 0.25 * cm)]
    story += [Box("Bila minta bantuan", "Sediakan tiga perkara: gambar wiring, gambar Serial Monitor, dan IP laptop/ESP32. Ini biasanya cukup untuk mengesan masalah dengan cepat.", TEAL, colors.HexColor("#E8F5F7")), PageBreak()]

    # Final checklist
    story += page_title("Checklist sebelum pembentangan", "11. Siap untuk digunakan")
    checks = [
        "Laptop, ESP32 scale dan ESP32-CAM berada pada WiFi yang sama.",
        "START_SETUP.cmd telah selesai pada laptop yang digunakan.",
        "AI server hidup dan dashboard boleh dibuka pada port 5000.",
        "AI_SERVER_URL menggunakan IP laptop yang betul.",
        "SCALE_URL menggunakan IP ESP32 scale yang betul.",
        "Load cell telah dikalibrasi dengan berat diketahui.",
        "Kamera menghadap makanan dan pencahayaan mencukupi.",
        "LCD menunjukkan berat, makanan, kalori dan status LOCK.",
        "Makanan uji dipilih daripada kelas dalam data/food_calories.csv.",
    ]
    for item in checks:
        story.append(P(f"&#9744; &nbsp; {item}", "step"))
    story += [Spacer(1, 0.3 * cm), Box("Untuk pembentangan", "Tunjukkan aliran penuh: letak makanan - kamera ambil gambar - dashboard AI tunjuk hasil - LCD kunci berat dan kira kalori. Terangkan bahawa nilai kalori ialah anggaran berdasarkan berat dan data kalori per gram.", GREEN, GREEN_LIGHT), Spacer(1, 0.25 * cm)]
    story += [P("Fail rujukan projek: arduino/esp32_scale_nutrition, arduino/esp32_cam_detection_sender, tools/real_ai_server.py, data/food_calories.csv dan README.md.", "small")]

    doc.build(story, onFirstPage=cover, onLaterPages=header_footer)
    print(OUT)


if __name__ == "__main__":
    build()
