# MarkItDown Web

Flask web wrapper untuk [microsoft/markitdown](https://github.com/microsoft/markitdown).  
Konversi PDF, DOCX, PPTX, XLSX, HTML, gambar, audio, dan lainnya ke Markdown — langsung dari browser.

## Fitur

- **Drag & drop** multi-file upload
- **Konversi PDF via Marker** — layout-aware, akurat untuk multi-kolom, tabel, dan equation (LaTeX)
- **Format lain via markitdown** — DOCX, PPTX, XLSX, HTML, dst tetap cepat
- **Konversi batch** — unduh satu file atau semua sebagai ZIP
- **Preview inline** per file di UI
- **OCR via Ollama lokal** (opsional, untuk gambar dalam dokumen non-PDF) — ekstrak teks dari gambar menggunakan vision model
- Tidak ada data yang dikirim ke cloud — semua berjalan lokal

## ⚠ PDF di CPU: Lambat

Marker pakai deep learning model (surya OCR) untuk layout detection. Tanpa GPU NVIDIA:

- **1-5 menit per halaman** — dokumen 20 halaman bisa 20-100 menit
- Model pertama kali download **2-4GB** (sekali saja, di-cache)
- Butuh **8GB+ RAM** untuk dokumen besar

Kalau ini terlalu lambat untuk kebutuhanmu, alternatif:
- Kurangi ke `pymupdf4llm` untuk PDF native/teks-rapi (jauh lebih cepat, kualitas cukup baik untuk PDF tidak kompleks)
- Jalankan di mesin dengan GPU NVIDIA (turun ke hitungan detik)

Format non-PDF (DOCX, PPTX, XLSX, dst) tetap cepat karena tidak lewat Marker.

## Format yang Didukung

PDF (via Marker), DOCX, DOC, PPTX, PPT, XLSX, XLS, HTML/HTM, CSV, JSON, XML, TXT,  
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

Host Ollama di-set lewat environment variable `OLLAMA_HOST`, bukan diketik manual di browser:

```bash
export OLLAMA_HOST=http://localhost:11434
python app.py
```

**Kalau web ini jalan di container dan Ollama di container lain**, isi dengan hostname service Docker-nya:

```bash
# docker-compose.yml
environment:
  - OLLAMA_HOST=http://ollama:11434   # nama service, bukan IP host
```

Atau via `docker run`:

```bash
docker run -e OLLAMA_HOST=http://ollama:11434 --network mdweb ... markitdown-web
```

Lalu di UI:

1. Klik toggle **"OCR via Ollama"**
2. Klik **"Detect Models"** — Flask akan proxy request ke `OLLAMA_HOST`, hasil model muncul di dropdown
3. Pilih model
4. Upload file dan klik **Convert**

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
