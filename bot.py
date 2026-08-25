import os
import io
import threading
import asyncio
import numpy as np
import cv2
from flask import Flask, request, jsonify, render_template_string

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)

# --- TETAPAN UTAMA ---
TOKEN = "GANTI_TOKEN_BOT_ANDA_DI_SINI"
DOMAIN_URL = "https://omr-checkers.onrender.com"  # Ganti dengan URL Cloud Server anda (Render/Koyeb)

# Globals untuk Flask & Telegram
bot_loop = None
bot_app = None

# --- HTML KAMERA WEB APP (INLINE) ---
HTML_CAMERA = """
<!DOCTYPE html>
<html lang="ms">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OMR Camera Scanner</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background-color: #000; font-family: sans-serif; text-align: center; color: white; overflow: hidden; }
        .camera-container { position: relative; width: 100vw; height: 80vh; background: black; }
        video { width: 100%; height: 100%; object-fit: cover; }
        
        /* Grid Overlay ala ZipGrade */
        .overlay {
            position: absolute; top: 10%; left: 8%; width: 84%; height: 80%;
            border: 2px dashed rgba(0, 255, 0, 0.7);
            box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5);
            pointer-events: none;
        }
        .corner { position: absolute; width: 35px; height: 35px; border: 4px solid #00FF00; }
        .tl { top: -2px; left: -2px; border-right: none; border-bottom: none; }
        .tr { top: -2px; right: -2px; border-left: none; border-bottom: none; }
        .bl { bottom: -2px; left: -2px; border-right: none; border-top: none; }
        .br { bottom: -2px; right: -2px; border-left: none; border-top: none; }

        .btn-container { height: 20vh; display: flex; align-items: center; justify-content: center; }
        button {
            background-color: #28a745; color: white; border: none;
            padding: 16px 45px; font-size: 18px; font-weight: bold;
            border-radius: 50px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        }
        button:active { transform: scale(0.95); }
    </style>
</head>
<body>
    <div class="camera-container">
        <video id="webcam" autoplay playsinline></video>
        <div class="overlay">
            <div class="corner tl"></div>
            <div class="corner tr"></div>
            <div class="corner bl"></div>
            <div class="corner br"></div>
        </div>
    </div>
    
    <div class="btn-container">
        <button id="snap-btn" onclick="captureAndSend()">📸 TANGKAP & SEMAK</button>
    </div>

    <canvas id="canvas" style="display:none;"></canvas>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();

        const video = document.getElementById('webcam');
        const canvas = document.getElementById('canvas');

        navigator.mediaDevices.getUserMedia({
            video: { facingMode: { exact: "environment" } }
        }).catch(() => {
            return navigator.mediaDevices.getUserMedia({ video: true });
        }).then(stream => {
            video.srcObject = stream;
        });

        function captureAndSend() {
            const btn = document.getElementById('snap-btn');
            btn.innerText = "⏳ Sedang Menanda...";
            btn.disabled = true;

            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const context = canvas.getContext('2d');
            context.drawImage(video, 0, 0, canvas.width, canvas.height);

            canvas.toBlob(blob => {
                const formData = new FormData();
                formData.append('file', blob, 'omr_capture.jpg');
                formData.append('user_id', tg.initDataUnsafe.user ? tg.initDataUnsafe.user.id : '');

                fetch('/upload_omr', {
                    method: 'POST',
                    body: formData
                }).then(res => res.json()).then(data => {
                    tg.close();
                }).catch(err => {
                    alert("Ralat menghantar gambar: " + err);
                    btn.disabled = false;
                    btn.innerText = "📸 TANGKAP & SEMAK";
                });
            }, 'image/jpeg', 0.95);
        }
    </script>
</body>
</html>
"""

# --- PELAYAN WEB FLASK ---
app_web = Flask(__name__)

@app_web.route('/')
def index():
    return "Bot OMR Checkers Sedang Aktif 24 Jam!"

@app_web.route('/camera')
def camera_page():
    return render_template_string(HTML_CAMERA)

@app_web.route('/upload_omr', methods=['POST'])
def upload_omr():
    if 'file' not in request.files:
        return jsonify({'error': 'Tiada fail'}), 400
    
    user_id = request.form.get('user_id')
    file = request.files['file']
    image_bytes = file.read()
    
    if bot_app and user_id and bot_loop:
        asyncio.run_coroutine_threadsafe(
            proses_dan_hantar_hasil(int(user_id), image_bytes),
            bot_loop
        )
    return jsonify({'status': 'success'})

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host="0.0.0.0", port=port)

# --- JANA PDF OMR ---
def jana_pdf_omr(jumlah_soalan):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # 4 Marker Bucu Kertas
    c.rect(20, 750, 20, 20, fill=1)
    c.rect(570, 750, 20, 20, fill=1)
    c.rect(20, 30, 20, 20, fill=1)
    c.rect(570, 30, 20, 20, fill=1)
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(180, 755, f"KERTAS JAWAPAN OMR ({jumlah_soalan} SOALAN)")
    
    c.setFont("Helvetica", 10)
    c.drawString(50, 720, "Nama Pelajar: ___________________________________")
    c.drawString(380, 720, "Tarikh: ______________")
    c.line(50, 710, 560, 710)
    
    options = ['A', 'B', 'C', 'D']
    
    def lukis_lajur(start_x, start_y, start_q, count):
        y = start_y
        for q in range(start_q, start_q + count):
            c.drawString(start_x, y, f"{q:02d}.")
            x = start_x + 25
            for opt in options:
                c.circle(x + 5, y + 3, 7, stroke=1, fill=0)
                c.setFont("Helvetica", 7)
                c.drawString(x + 3, y + 1, opt)
                c.setFont("Helvetica", 10)
                x += 22
            y -= 25

    if jumlah_soalan == 20:
        lukis_lajur(160, 660, 1, 10)
        lukis_lajur(360, 660, 11, 10)
    elif jumlah_soalan == 40:
        lukis_lajur(160, 660, 1, 20)
        lukis_lajur(360, 660, 21, 20)
    elif jumlah_soalan == 50:
        lukis_lajur(160, 670, 1, 25)
        lukis_lajur(360, 670, 26, 25)
        
    c.save()
    buffer.seek(0)
    return buffer

# --- PEMPROSESAN OPENCV ---
def luruskan_gambar(imej):
    kelabu = cv2.cvtColor(imej, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(kelabu, (5, 5), 0)
    hitam_putih = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    contours, _ = cv2.findContours(hitam_putih, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    calon_marker = []

    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.04 * peri, True)
        (x, y, w, h) = cv2.boundingRect(c)
        nisbah = w / float(h)
        luas = cv2.contourArea(c)
        if len(approx) == 4 and 0.7 <= nisbah <= 1.3 and luas > 150:
            calon_marker.append(c)

    calon_marker = sorted(calon_marker, key=cv2.contourArea, reverse=True)[:4]

    if len(calon_marker) == 4:
        pts = []
        for c in calon_marker:
            M = cv2.moments(c)
            if M["m00"] != 0:
                pts.append([int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])])

        pts = np.array(pts, dtype="float32")
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]

        maxWidth, maxHeight = 600, 850
        dst = np.array([[0, 0], [maxWidth - 1, 0], [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
        M = cv2.getPerspectiveTransform(rect, dst)
        return cv2.warpPerspective(imej, M, (maxWidth, maxHeight)), True
        
    return imej, False

def analisa_omr(image_bytes, skema_semasa):
    np_arr = np.frombuffer(image_bytes, np.uint8)
    imej_asal = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    imej, berjaya_lurus = luruskan_gambar(imej_asal)
    kelabu = cv2.cvtColor(imej, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(kelabu, (5, 5), 0)
    ret, hitam_putih = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    
    contours, _ = cv2.findContours(hitam_putih, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    calon_bulatan = []
    for c in contours:
        (x, y, w, h) = cv2.boundingRect(c)
        nisbah = w / float(h)
        luas_kotak = w * h
        if luas_kotak > 0:
            kepadatan = cv2.contourArea(c) / float(luas_kotak)
            if 10 <= w <= 100 and 10 <= h <= 100 and 0.7 <= nisbah <= 1.3 and 0.5 <= kepadatan <= 0.95:
                calon_bulatan.append(c)
                
    bulatan = []
    if len(calon_bulatan) > 0:
        median_w = np.median([cv2.boundingRect(c)[2] for c in calon_bulatan])
        for c in calon_bulatan:
            if (median_w * 0.7) <= cv2.boundingRect(c)[2] <= (median_w * 1.3):
                bulatan.append(c)

    jumlah_bulatan = len(bulatan)
    if jumlah_bulatan not in [80, 160, 200]:
        cv2.drawContours(imej, bulatan, -1, (0, 165, 255), 2)
        _, buffer_imej = cv2.imencode(".jpg", imej)
        msg = f"Ralat: Terjumpa {jumlah_bulatan} bulatan. Sepatutnya 80, 160, atau 200."
        if not berjaya_lurus:
            msg += "\n💡 Pastikan 4 kotak bucu hitam kelihatan jelas pada skrin."
        return buffer_imej, msg, False

    jumlah_soalan = jumlah_bulatan // 4
    mid_x = imej.shape[1] // 2
    lajur_kiri = sorted([c for c in bulatan if cv2.boundingRect(c)[0] < mid_x], key=lambda c: cv2.boundingRect(c)[1])
    lajur_kanan = sorted([c for c in bulatan if cv2.boundingRect(c)[0] >= mid_x], key=lambda c: cv2.boundingRect(c)[1])
    
    bulatan_tersusun = lajur_kiri + lajur_kanan
    betul = 0
    soalan_salah = []
    
    for i in range(0, len(bulatan_tersusun), 4):
        baris = sorted(bulatan_tersusun[i:i+4], key=lambda c: cv2.boundingRect(c)[0])
        pixel_hitam = []
        
        for c in baris:
            mask = np.zeros(kelabu.shape, dtype="uint8")
            cv2.drawContours(mask, [c], -1, 255, -1)
            pixel_hitam.append(cv2.countNonZero(cv2.bitwise_and(hitam_putih, hitam_putih, mask=mask)))
        
        jawapan_pelajar = pixel_hitam.index(max(pixel_hitam))
        soalan_no = i // 4
        
        if skema_semasa and soalan_no < len(skema_semasa) and jawapan_pelajar == skema_semasa[soalan_no]:
            betul += 1
            warna = (0, 255, 0)
        else:
            soalan_salah.append(soalan_no + 1)
            warna = (0, 0, 255)
        
        cv2.drawContours(imej, [baris[jawapan_pelajar]], -1, warna, 3)

    markah = (betul / jumlah_soalan) * 100
    msg = f"📝 **Keputusan Semakan ({jumlah_soalan} Soalan)**\n\nMarkah: {betul}/{jumlah_soalan} ({markah:.0f}%)\n"
    msg += f"Soalan salah: {', '.join(map(str, soalan_salah))}" if soalan_salah else "Tahniah! Semua betul. 🎉"
    
    _, buffer_imej = cv2.imencode(".jpg", imej)
    return buffer_imej, msg, True

# --- BOT TELEGRAM HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mesej = (
        "🤖 <b>Selamat Datang ke Bot OMR Checkers!</b>\n\n"
        "1. /bina_omr - Hasilkan PDF Kertas Jawapan OMR\n"
        "2. /set_skema - Masukkan Skema Jawapan\n"
        "3. /semak - Mula Menyemak (Guna Kamera Grid)"
    )
    await update.message.reply_text(mesej, parse_mode="HTML")

async def bina_omr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("20 Soalan", callback_data='bina_20')],
        [InlineKeyboardButton("40 Soalan", callback_data='bina_40')],
        [InlineKeyboardButton("50 Soalan", callback_data='bina_50')]
    ]
    await update.message.reply_text("Sila pilih jumlah soalan OMR:", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_skema(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Skema 20 Soalan", callback_data='set_20')],
        [InlineKeyboardButton("Skema 40 Soalan", callback_data='set_40')],
        [InlineKeyboardButton("Skema 50 Soalan", callback_data='set_50')]
    ]
    await update.message.reply_text("Pilih jenis skema yang nak ditetapkan:", reply_markup=InlineKeyboardMarkup(keyboard))

async def semak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['status'] = 'tunggu_gambar'
    url_kamera = f"{DOMAIN_URL}/camera"
    
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(text="📷 Buka Kamera OMR (Grid)", web_app=WebAppInfo(url=url_kamera))]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text(
        "Sila tekan butang di bawah untuk membuka Kamera Grid OMR:",
        reply_markup=keyboard
    )

async def butang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith('bina_'):
        jumlah = int(data.split('_')[1])
        pdf_buffer = jana_pdf_omr(jumlah)
        await query.message.reply_document(
            document=pdf_buffer,
            filename=f"OMR_{jumlah}_Soalan.pdf",
            caption=f"Berikut adalah kertas OMR {jumlah} soalan."
        )
    elif data.startswith('set_'):
        jumlah = int(data.split('_')[1])
        context.user_data['temp_set_jumlah'] = jumlah
        context.user_data['status'] = 'tunggu_skema_input'
        await query.message.reply_text(f"Hantar skema {jumlah} soalan (Cth: A B C D A ...):")

async def terima_teks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = context.user_data.get('status')
    if status == 'tunggu_skema_input':
        teks = update.message.text.upper().replace(',', ' ').split()
        peta = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
        skema_num = [peta[x] for x in teks if x in peta]
        
        jumlah = context.user_data.get('temp_set_jumlah')
        if len(skema_num) != jumlah:
            await update.message.reply_text(f"❌ Bilangan skema tidak mencukupi ({len(skema_num)}/{jumlah}). Sila cuba lagi.")
            return
            
        context.user_data[f'skema_{jumlah}'] = skema_num
        context.user_data['status'] = None
        await update.message.reply_text(f"✅ Skema {jumlah} soalan berjaya disimpan!")

async def terima_gambar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = context.user_data.get('status')
    if status != 'tunggu_gambar':
        await update.message.reply_text("⚠️ Sila taip /semak terlebih dahulu sebelum menghantar gambar.")
        return

    await update.message.reply_text("📐 Menganalisis gambar OMR...")
    fail_gambar = await update.message.photo[-1].get_file()
    image_bytes = await fail_gambar.download_as_bytearray()
    
    skema_semasa = context.user_data.get('skema_20') or context.user_data.get('skema_40') or context.user_data.get('skema_50')
    img_buf, msg, _ = analisa_omr(image_bytes, skema_semasa)
    
    await update.message.reply_photo(photo=io.BytesIO(img_buf), caption=msg, parse_mode="Markdown")
    context.user_data['status'] = None

async def proses_dan_hantar_hasil(user_id, image_bytes):
    user_data = bot_app.user_data.get(user_id, {})
    skema_semasa = user_data.get('skema_20') or user_data.get('skema_40') or user_data.get('skema_50')
    img_buf, msg, _ = analisa_omr(image_bytes, skema_semasa)
    await bot_app.bot.send_photo(chat_id=user_id, photo=io.BytesIO(img_buf), caption=msg, parse_mode="Markdown")

async def post_init(application: Application):
    global bot_loop
    bot_loop = asyncio.get_running_loop()

if __name__ == '__main__':
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

    print("Bot OMR Checkers sedang dipasang...")
    bot_app = Application.builder().token(TOKEN).post_init(post_init).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("bina_omr", bina_omr))
    bot_app.add_handler(CommandHandler("set_skema", set_skema))
    bot_app.add_handler(CommandHandler("semak", semak))

    bot_app.add_handler(CallbackQueryHandler(butang_callback))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terima_teks))
    bot_app.add_handler(MessageHandler(filters.PHOTO, terima_gambar))

    print("Bot berjalan secara rasmi!")
    bot_app.run_polling()
