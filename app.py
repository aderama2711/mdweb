import os

# Suppress onnxruntime pthread_setaffinity_np errors in containers/WSL/VMs.
# Must be set before onnxruntime is imported (even transitively via markitdown).
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("ONNXRUNTIME_NUM_INTRA_THREADS", "1")
os.environ.setdefault("ONNXRUNTIME_NUM_INTER_THREADS", "1")

import io
import uuid
import zipfile
import threading
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# ponytail: hardcode via env var, bukan input browser — host Ollama ini
# container-to-container, user browser tidak pernah tahu/perlu tahu nilainya.
OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')

# ponytail: in-memory dict — single process only. Jalankan gunicorn -w 1.
jobs: dict = {}
jobs_lock = threading.Lock()

ALLOWED_EXTENSIONS = {
    'pdf', 'pptx', 'ppt', 'docx', 'doc', 'xlsx', 'xls',
    'html', 'htm', 'csv', 'json', 'xml', 'txt',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp',
    'mp3', 'wav', 'ogg', 'm4a',
    'zip', 'epub', 'ipynb', 'msg',
}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def run_conversion_job(job_id: str, file_data_list: list, use_ocr: bool, ollama_model: str):
    from markitdown import MarkItDown

    try:
        if use_ocr:
            from openai import OpenAI
            client = OpenAI(base_url=OLLAMA_HOST + '/v1', api_key='ollama')
            try:
                md = MarkItDown(llm_client=client, llm_model=ollama_model, enable_plugins=True)
            except TypeError:
                md = MarkItDown(llm_client=client, llm_model=ollama_model)
        else:
            md = MarkItDown()
    except Exception as e:
        with jobs_lock:
            jobs[job_id].update(status='error', error=str(e))
        return

    results = []
    for filename, data in file_data_list:
        with jobs_lock:
            jobs[job_id]['current_file'] = filename
        try:
            stream = io.BytesIO(data)
            stream.name = filename
            result = md.convert_stream(stream)
            results.append({'filename': Path(filename).stem + '.md',
                            'original': filename, 'content': result.text_content, 'ok': True})
        except Exception as e:
            results.append({'filename': Path(filename).stem + '.md',
                            'original': filename, 'content': '', 'error': str(e), 'ok': False})

    with jobs_lock:
        jobs[job_id].update(status='done', progress=100, results=results)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/convert', methods=['POST'])
def api_convert():
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No files uploaded'}), 400

    use_ocr      = request.form.get('use_ocr', 'false').lower() == 'true'
    ollama_model = request.form.get('ollama_model', 'llava').strip()

    file_data_list = []
    for f in files:
        if f and f.filename and allowed_file(f.filename):
            file_data_list.append((f.filename, f.read()))
        elif f and f.filename:
            return jsonify({'error': f'Unsupported file type: {f.filename}'}), 400

    if not file_data_list:
        return jsonify({'error': 'No supported files found'}), 400

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {'status': 'running', 'progress': 0,
                        'current_file': '', 'results': [], 'error': None}

    threading.Thread(target=run_conversion_job, daemon=True,
                     args=(job_id, file_data_list, use_ocr, ollama_model)).start()

    return jsonify({'job_id': job_id})


@app.route('/api/status/<job_id>')
def api_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify({'status': job['status'], 'progress': job['progress'],
                    'current_file': job.get('current_file', ''),
                    'error': job.get('error'),
                    'file_count': len(job.get('results', []))})


@app.route('/api/download/<job_id>')
def api_download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Job not ready'}), 404

    successful = [r for r in job['results'] if r['ok']]
    if not successful:
        return jsonify({'error': 'No files converted successfully'}), 400

    # ponytail: always ZIP — single-file download handled client-side via /api/preview
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for r in successful:
            zf.writestr(r['filename'], r['content'])
    buf.seek(0)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name='converted.zip')


@app.route('/api/preview/<job_id>/<int:file_index>')
def api_preview(job_id, file_index):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Job not ready'}), 404
    results = job['results']
    if not 0 <= file_index < len(results):
        return jsonify({'error': 'File index out of range'}), 404
    r = results[file_index]
    return jsonify({'filename': r['filename'], 'original': r['original'],
                    'content': r.get('content', ''), 'ok': r['ok'], 'error': r.get('error')})


@app.route('/api/results/<job_id>')
def api_results(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Job not ready'}), 404
    return jsonify({'files': [
        {'index': i, 'filename': r['filename'], 'original': r['original'],
         'ok': r['ok'], 'error': r.get('error'), 'size': len(r.get('content', ''))}
        for i, r in enumerate(job['results'])
    ]})


@app.route('/api/ollama/models')
def api_ollama_models():
    # ponytail: pakai OLLAMA_HOST server-side, bukan dari query param —
    # host tidak lagi dikontrol browser.
    try:
        import urllib.request
        with urllib.request.urlopen(OLLAMA_HOST + '/api/tags', timeout=5) as resp:
            data = json.loads(resp.read())
        return jsonify({'models': [m['name'] for m in data.get('models', [])], 'ok': True})
    except Exception as e:
        return jsonify({'models': [], 'ok': False, 'error': str(e)})


if __name__ == '__main__':
    # ponytail: use_reloader=False — reloader spawns second process, jobs dict jadi 404.
    # gunicorn: wajib -w 1 (in-memory state tidak shared antar worker)
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
