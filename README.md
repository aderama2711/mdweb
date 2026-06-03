# MarkItDown Web

Flask web wrapper untuk [microsoft/markitdown](https://github.com/microsoft/markitdown).  
Konversi PDF, DOCX, PPTX, XLSX, HTML, gambar, audio, dan lainnya ke Markdown — langsung dari browser.

## Fitur

- **Drag & drop** multi-file upload
- **Konversi batch** — unduh satu file atau semua sebagai ZIP
- **Preview inline** per file di UI
- **OCR via Ollama lokal** (opsional) — ekstrak teks dari gambar dalam dokumen
- Tidak ada data yang dikirim ke cloud — semua berjalan lokal

## Format yang Didukung

PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, HTML/HTM, CSV, JSON, XML, TXT,  
JPG/PNG/GIF/BMP/WEBP, MP3/WAV/OGG/M4A, ZIP, EPUB, IPYNB, MSG

---

## Setup

### 1. Clone & install dependencies

```bash
git clone <repo>
cd markitdown-web

# Buat virtual environment (disarankan)
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 2. Jalankan server

```bash
python app.py
```

Buka browser: `http://localhost:5000`

---

## OCR dengan Ollama (Opsional)

OCR menggunakan plugin `markitdown-ocr` yang memanggil vision model via Ollama.

### Install Ollama

```bash
# Download dari https://ollama.com
# Lalu pull vision model:
ollama pull llava
# atau
ollama pull moondream
# atau
ollama pull minicpm-v
```

### Aktifkan di UI

1. Klik toggle **"OCR via Ollama"**
2. Isi host (default: `http://localhost:11434`)
3. Klik **"Detect Models"** untuk auto-detect model yang tersedia
4. Pilih model dari list atau ketik manual
5. Upload file dan klik **Convert**

> **Catatan**: OCR hanya bekerja untuk gambar yang tertanam di dalam dokumen (PDF, DOCX, PPTX, XLSX). Untuk file gambar biasa (JPG/PNG), markitdown sudah menghandle via llm_client tanpa plugin.

---

## Konfigurasi

Edit `app.py` untuk menyesuaikan:

```python
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # Ukuran upload max (default: 100MB)
```

Jalankan di port berbeda:

```bash
python app.py  # edit port di baris terakhir: port=5000
```

Atau dengan gunicorn untuk production:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `markitdown not found` | `pip install 'markitdown[all]'` |
| OCR tidak bekerja | Pastikan Ollama berjalan: `ollama serve` |
| Model tidak terdeteksi | Cek host Ollama, coba `curl http://localhost:11434/api/tags` |
| File terlalu besar | Naikkan `MAX_CONTENT_LENGTH` di `app.py` |
| Audio/video conversion gagal | Install ffmpeg: `sudo apt install ffmpeg` |
