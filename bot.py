import io
from flask import Flask
import threading
import os
import cv2
import numpy as np
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# Token Bot Anda
TOKEN = "8958337405:AAGHn0WHceQBV48dges6i8jHelthYa-c9hk"

# Kamus pertukaran Huruf ke Nombor untuk memudahkan AI membaca
HURUF_KE_NOMBOR = {'A': 0, 'B': 1, 'C': 2, 'D': 3}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mesej = (
        "🤖 <b>Selamat Datang ke Bot OMR Pro!</b>\n\n"
        "Senarai Arahan:\n"
        "1. /bina_omr - Hasilkan kertas jawapan PDF.\n"
        "2. /set_skema - Masukkan skema jawapan anda.\n"
        "3. /semak - Mula menyemak kertas pelajar."
    )
    # Kita tukar parse_mode kepada HTML supaya underscore tidak hilang
    await update.message.reply_text(mesej, parse_mode="HTML")

# ==========================================
# 1. MENU: BINA OMR & SET SKEMA
# ==========================================
async def bina_omr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 OMR 20 Soalan", callback_data='omr_20')],
        [InlineKeyboardButton("📝 OMR 40 Soalan", callback_data='omr_40')],
        [InlineKeyboardButton("📝 OMR 50 Soalan", callback_data='omr_50')]
    ]
    await update.message.reply_text('Sila pilih jenis kertas OMR yang anda mahu hasilkan:', reply_markup=InlineKeyboardMarkup(keyboard))

async def set_skema(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔑 Skema 20 Soalan", callback_data='skema_20')],
        [InlineKeyboardButton("🔑 Skema 40 Soalan", callback_data='skema_40')],
        [InlineKeyboardButton("🔑 Skema 50 Soalan", callback_data='skema_50')]
    ]
    await update.message.reply_text('Pilih jenis skema yang ingin dimasukkan/diedit:', reply_markup=InlineKeyboardMarkup(keyboard))

# ==========================================
# 2. PENGURUS BUTANG (CALLBACK)
# ==========================================
async def butang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # JIKA USER TEKAN BUTANG BINA OMR
    if data.startswith('omr_'):
        jumlah_soalan = int(data.split('_')[1])
        await query.edit_message_text(f"Tengah melukis kertas OMR {jumlah_soalan} soalan. Sabar ya...")
        
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        marker_size = 30
        c.rect(30, height - 60, marker_size, marker_size, fill=1)
        c.rect(width - 60, height - 60, marker_size, marker_size, fill=1)
        c.rect(30, 30, marker_size, marker_size, fill=1)
        c.rect(width - 60, 30, marker_size, marker_size, fill=1)
        
        c.setFont("Helvetica-Bold", 16)
        c.drawString(160, height - 60, f"KERTAS JAWAPAN OMR ({jumlah_soalan} SOALAN)")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 100, "Nama : __________________________________________")
        c.drawString(380, height - 100, "Kelas : _______________")
        
        pilihan = ['A', 'B', 'C', 'D']
        soalan_per_lajur = 20 if jumlah_soalan <= 40 else 25
        y_start = height - 140
        
        for i in range(1, jumlah_soalan + 1):
            if i <= soalan_per_lajur:
                x_pos, y_pos = 90, y_start - ((i - 1) * 26)
            else:
                x_pos, y_pos = 340, y_start - ((i - 1 - soalan_per_lajur) * 26)
                
            c.drawString(x_pos - 30, y_pos - 4, f"{i}.")
            x_bulatan = x_pos
            for jawapan in pilihan:
                c.circle(x_bulatan, y_pos, 11)
                c.drawString(x_bulatan - 4, y_pos - 4, jawapan)
                x_bulatan += 38
                
        c.save()
        buffer.seek(0)
        await query.message.reply_document(document=buffer, filename=f"OMR_{jumlah_soalan}_Soalan.pdf")

    # JIKA USER TEKAN BUTANG SET SKEMA
    elif data.startswith('skema_'):
        jumlah_soalan = data.split('_')[1]
        context.user_data['status'] = f'tunggu_skema_{jumlah_soalan}'
        mesej = (
            f"Sila taip skema jawapan untuk **{jumlah_soalan} soalan** secara berterusan.\n\n"
            f"Contoh: `ABCDABCDABCDABCDABCD...`\n"
            f"Pastikan jumlah huruf tepat {jumlah_soalan}."
        )
        await query.edit_message_text(mesej, parse_mode="Markdown")

# ==========================================
# 3. TERIMA TEKS SKEMA DARI USER
# ==========================================
async def terima_teks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = context.user_data.get('status')
    
    # Kalau bot tengah tunggu user masukkan skema
    if status and status.startswith('tunggu_skema_'):
        jenis_skema = int(status.split('_')[2])
        teks_skema = update.message.text.upper().replace(" ", "").strip()
        
        if len(teks_skema) != jenis_skema:
            await update.message.reply_text(f"❌ Ralat! Anda beri {len(teks_skema)} huruf. Saya perlukan tepat {jenis_skema} huruf. Sila taip semula:")
            return
            
        for huruf in teks_skema:
            if huruf not in ['A', 'B', 'C', 'D']:
                await update.message.reply_text("❌ Ralat! Hanya huruf A, B, C, dan D dibenarkan. Sila taip semula:")
                return
                
        # Tukar huruf jadi nombor dan simpan dalam memori user
        skema_list = [HURUF_KE_NOMBOR[h] for h in teks_skema]
        context.user_data[f'skema_{jenis_skema}'] = skema_list
        context.user_data['status'] = None # Reset status
        
        await update.message.reply_text(f"✅ Berjaya! Skema {jenis_skema} soalan telah disimpan.\n\nSkema anda: `{teks_skema}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("Gunakan /start untuk melihat menu arahan.")

# ==========================================
# 4. ARAHAN /semak DAN PROSES GAMBAR
# ==========================================
async def semak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['status'] = 'tunggu_gambar'
    await update.message.reply_text("📸 Sistem semakan diaktifkan! Sila hantar gambar kertas OMR sekarang.")

# --- FUNGSI UNTUK MELURUSKAN GAMBAR (PERSPECTIVE TRANSFORM) ---
def luruskan_gambar(imej):
    kelabu = cv2.cvtColor(imej, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(kelabu, (5, 5), 0)
    hitam_putih = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    # Cari 4 kotak hitam di bucu kertas
    contours, _ = cv2.findContours(hitam_putih, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    calon_marker = []

    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.04 * peri, True)
        (x, y, w, h) = cv2.boundingRect(c)
        nisbah = w / float(h)
        luas = cv2.contourArea(c)

        # Penapis kotak bucu OMR
        if len(approx) == 4 and 0.7 <= nisbah <= 1.3 and luas > 150:
            calon_marker.append(c)

    # Ambil 4 marker terbesar (bucu kertas)
    calon_marker = sorted(calon_marker, key=cv2.contourArea, reverse=True)[:4]

    if len(calon_marker) == 4:
        pts = []
        for c in calon_marker:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
                pts.append([cX, cY])

        pts = np.array(pts, dtype="float32")
        
        # Susun bucu: [Top-Left, Top-Right, Bottom-Right, Bottom-Left]
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]

        # Saiz standard imej lurus
        maxWidth, maxHeight = 600, 850
        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]], dtype="float32")

        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(imej, M, (maxWidth, maxHeight))
        return warped, True
        
    return imej, False


# --- FUNGSI PROSES GAMBAR DENGAN AUTO-ALIGN ---
async def terima_gambar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = context.user_data.get('status')
    
    if status != 'tunggu_gambar':
        await update.message.reply_text("⚠️ Sila taip /semak terlebih dahulu sebelum menghantar gambar kertas OMR.")
        return
        
    await update.message.reply_text("📐 Meluruskan gambar & menganalisis kertas jawapan...")
    
    try:
        fail_gambar = await update.message.photo[-1].get_file()
        image_bytes = await fail_gambar.download_as_bytearray()
        
        np_arr = np.frombuffer(image_bytes, np.uint8)
        imej_asal = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # 1. Meluruskan gambar secara automatik
        imej, berjaya_lurus = luruskan_gambar(imej_asal)
        
        # 2. Proses imej yang telah diluruskan
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
            is_success, buffer_imej = cv2.imencode(".jpg", imej)
            caption_ralat = f"Ralat: Terjumpa {jumlah_bulatan} bulatan. Sepatutnya 80, 160, atau 200."
            if not berjaya_lurus:
                caption_ralat += "\n💡 *Petua:* Pastikan 4 kotak hitam di bucu kertas kelihatan jelas."
            await update.message.reply_photo(photo=io.BytesIO(buffer_imej), caption=caption_ralat, parse_mode="Markdown")
            return

        jumlah_soalan = jumlah_bulatan // 4
        
        skema_semasa = context.user_data.get(f'skema_{jumlah_soalan}')
        if not skema_semasa:
            await update.message.reply_text(f"❌ Anda belum menetapkan skema untuk {jumlah_soalan} soalan. Sila taip /set_skema dahulu.")
            context.user_data['status'] = None
            return
        
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
            
            if jawapan_pelajar == skema_semasa[soalan_no]:
                betul += 1
                warna = (0, 255, 0)
            else:
                soalan_salah.append(soalan_no + 1)
                warna = (0, 0, 255)
            
            cv2.drawContours(imej, [baris[jawapan_pelajar]], -1, warna, 3)

        markah_peratus = (betul / jumlah_soalan) * 100
        mesej_akhir = f"📝 **Keputusan Semakan ({jumlah_soalan} Soalan)**\n\nMarkah: {betul}/{jumlah_soalan} ({markah_peratus:.0f}%)\n"
        mesej_akhir += f"Soalan salah: {', '.join(map(str, soalan_salah))}" if soalan_salah else "Tahniah! Semua betul. 🎉"
            
        is_success, buffer_imej = cv2.imencode(".jpg", imej)
        await update.message.reply_photo(photo=io.BytesIO(buffer_imej), caption=mesej_akhir, parse_mode="Markdown")
        
        context.user_data['status'] = None
        
    except Exception as e:
        await update.message.reply_text(f"Maaf, ralat berlaku: {e}")
        context.user_data['status'] = None
    status = context.user_data.get('status')
    
    if status != 'tunggu_gambar':
        await update.message.reply_text("⚠️ Sila taip /semak terlebih dahulu sebelum menghantar gambar kertas OMR.")
        return
        
    await update.message.reply_text("Menganalisis kertas jawapan...")
    
    try:
        fail_gambar = await update.message.photo[-1].get_file()
        image_bytes = await fail_gambar.download_as_bytearray()
        
        np_arr = np.frombuffer(image_bytes, np.uint8)
        imej = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
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
                if 10 <= w <= 150 and 10 <= h <= 150 and 0.7 <= nisbah <= 1.3 and 0.5 <= kepadatan <= 0.95:
                    calon_bulatan.append(c)
                    
        bulatan = []
        if len(calon_bulatan) > 0:
            median_w = np.median([cv2.boundingRect(c)[2] for c in calon_bulatan])
            for c in calon_bulatan:
                if (median_w * 0.75) <= cv2.boundingRect(c)[2] <= (median_w * 1.25):
                    bulatan.append(c)

        jumlah_bulatan = len(bulatan)
        if jumlah_bulatan not in [80, 160, 200]:
            cv2.drawContours(imej, bulatan, -1, (0, 165, 255), 2)
            is_success, buffer_imej = cv2.imencode(".jpg", imej)
            await update.message.reply_photo(photo=io.BytesIO(buffer_imej), caption=f"Ralat: Terjumpa {jumlah_bulatan} bulatan. Sepatutnya 80, 160, atau 200.")
            return

        jumlah_soalan = jumlah_bulatan // 4
        
        # Cek sama ada user dah masukkan skema atau belum
        skema_semasa = context.user_data.get(f'skema_{jumlah_soalan}')
        if not skema_semasa:
            await update.message.reply_text(f"❌ Anda belum menetapkan skema untuk {jumlah_soalan} soalan. Sila taip /set_skema dahulu.")
            context.user_data['status'] = None
            return
        
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
            
            # Semak guna skema yang user masukkan tadi
            if jawapan_pelajar == skema_semasa[soalan_no]:
                betul += 1
                warna = (0, 255, 0)
            else:
                soalan_salah.append(soalan_no + 1)
                warna = (0, 0, 255)
            
            cv2.drawContours(imej, [baris[jawapan_pelajar]], -1, warna, 3)

        markah_peratus = (betul / jumlah_soalan) * 100
        mesej_akhir = f"📝 **Keputusan Semakan ({jumlah_soalan} Soalan)**\n\nMarkah: {betul}/{jumlah_soalan} ({markah_peratus:.0f}%)\n"
        mesej_akhir += f"Soalan salah: {', '.join(map(str, soalan_salah))}" if soalan_salah else "Tahniah! Semua betul. 🎉"
            
        is_success, buffer_imej = cv2.imencode(".jpg", imej)
        await update.message.reply_photo(photo=io.BytesIO(buffer_imej), caption=mesej_akhir, parse_mode="Markdown")
        
        # Reset status selepas siap semak
        context.user_data['status'] = None
        
    except Exception as e:
        await update.message.reply_text(f"Maaf, ralat berlaku: {e}")
        context.user_data['status'] = None

app_web = Flask(__name__)
@app_web.route('/')
def index():
    return "Bot OMR Checkers Sedang Aktif 24 Jam!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host="0.0.0.0", port=port)

if __name__ == '__main__':
    # Hidupkan pelayan web di latar belakang
    t = threading.Thread(target=run_web)
    t.start()

    # Hidupkan Bot
    print("Bot sedang dipasang...")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bina_omr", bina_omr))
    app.add_handler(CommandHandler("set_skema", set_skema))
    app.add_handler(CommandHandler("semak", semak))

    app.add_handler(CallbackQueryHandler(butang_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terima_teks))
    app.add_handler(MessageHandler(filters.PHOTO, terima_gambar))

    print("Bot dah berjalan! Sedia menerima arahan.")
    app.run_polling()
