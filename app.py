import os
import io
import uuid
import zipfile
import tempfile
import threading
import time
import json
from pathlib import Path
from flask import (
    Flask, request, jsonify, send_file,
    render_template, Response, stream_with_context
)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max upload

# In-memory job store  {job_id: {status, progress, files, error}}
jobs: dict = {}
jobs_lock = threading.Lock()

ALLOWED_EXTENSIONS = {
    'pdf', 'pptx', 'ppt', 'docx', 'doc', 'xlsx', 'xls',
    'html', 'htm', 'csv', 'json', 'xml', 'txt',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp',
    'mp3', 'wav', 'ogg', 'm4a',
    'zip', 'epub', 'ipynb', 'msg'
}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def make_markitdown(use_ocr: bool, ollama_host: str, ollama_model: str):
    """Instantiate MarkItDown, optionally with Ollama OCR client."""
    from markitdown import MarkItDown

    if use_ocr:
        try:
            from openai import OpenAI
            base_url = ollama_host.rstrip('/') + '/v1'
            llm_client = OpenAI(base_url=base_url, api_key='ollama')
            # Try new API (enable_plugins kwarg) then fall back to older style
            try:
                md = MarkItDown(llm_client=llm_client, llm_model=ollama_model, enable_plugins=True)
            except TypeError:
                md = MarkItDown(llm_client=llm_client, llm_model=ollama_model)
        except ImportError:
            # openai package not available – fall back to plain conversion
            md = MarkItDown()
    else:
        md = MarkItDown()

    return md


def run_conversion_job(job_id: str, file_data_list: list, use_ocr: bool,
                        ollama_host: str, ollama_model: str):
    """Background thread: convert files and update job state."""
    try:
        md = make_markitdown(use_ocr, ollama_host, ollama_model)
    except Exception as e:
        with jobs_lock:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['error'] = f'Failed to initialise MarkItDown: {str(e)}'
        return

    results = []
    total = len(file_data_list)

    for i, (filename, data) in enumerate(file_data_list):
        with jobs_lock:
            jobs[job_id]['current_file'] = filename
            jobs[job_id]['progress'] = int(i / total * 100)

        try:
            stream = io.BytesIO(data)
            stream.name = filename          # markitdown uses this to detect mime type
            result = md.convert_stream(stream)
            results.append({
                'filename': Path(filename).stem + '.md',
                'original': filename,
                'content': result.text_content,
                'ok': True,
            })
        except Exception as e:
            results.append({
                'filename': Path(filename).stem + '.md',
                'original': filename,
                'content': '',
                'error': str(e),
                'ok': False,
            })

    with jobs_lock:
        jobs[job_id]['status'] = 'done'
        jobs[job_id]['progress'] = 100
        jobs[job_id]['results'] = results


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/convert', methods=['POST'])
def api_convert():
    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No files uploaded'}), 400

    use_ocr = request.form.get('use_ocr', 'false').lower() == 'true'
    ollama_host = request.form.get('ollama_host', 'http://192.168.1.1:30068').strip()
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
        jobs[job_id] = {
            'status': 'running',
            'progress': 0,
            'current_file': '',
            'results': [],
            'error': None,
        }

    t = threading.Thread(
        target=run_conversion_job,
        args=(job_id, file_data_list, use_ocr, ollama_host, ollama_model),
        daemon=True,
    )
    t.start()

    return jsonify({'job_id': job_id})


@app.route('/api/status/<job_id>')
def api_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    # Don't send full results in status poll — just metadata
    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'current_file': job.get('current_file', ''),
        'error': job.get('error'),
        'file_count': len(job.get('results', [])),
    })


@app.route('/api/download/<job_id>')
def api_download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Job not ready'}), 404

    results = job['results']
    successful = [r for r in results if r['ok']]

    if not successful:
        return jsonify({'error': 'No files converted successfully'}), 400

    if len(successful) == 1:
        # Single file → direct .md download
        r = successful[0]
        buf = io.BytesIO(r['content'].encode('utf-8'))
        buf.seek(0)
        return send_file(
            buf,
            mimetype='text/markdown',
            as_attachment=True,
            download_name=r['filename'],
        )
    else:
        # Multiple files → ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for r in successful:
                zf.writestr(r['filename'], r['content'])
        zip_buf.seek(0)
        return send_file(
            zip_buf,
            mimetype='application/zip',
            as_attachment=True,
            download_name='converted.zip',
        )


@app.route('/api/preview/<job_id>/<int:file_index>')
def api_preview(job_id, file_index):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Job not ready'}), 404

    results = job['results']
    if file_index < 0 or file_index >= len(results):
        return jsonify({'error': 'File index out of range'}), 404

    r = results[file_index]
    return jsonify({
        'filename': r['filename'],
        'original': r['original'],
        'content': r.get('content', ''),
        'ok': r['ok'],
        'error': r.get('error'),
    })


@app.route('/api/results/<job_id>')
def api_results(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        return jsonify({'error': 'Job not ready'}), 404
    # Return summary (no content) for the file list
    summary = [{
        'index': i,
        'filename': r['filename'],
        'original': r['original'],
        'ok': r['ok'],
        'error': r.get('error'),
        'size': len(r.get('content', '')),
    } for i, r in enumerate(job['results'])]
    return jsonify({'files': summary})


@app.route('/api/ollama/models')
def api_ollama_models():
    """Probe local Ollama for available vision-capable models."""
    host = request.args.get('host', 'http://192.168.1.1:30068').strip()
    try:
        import urllib.request
        url = host.rstrip('/') + '/api/tags'
        req = urllib.request.Request(url, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        models = [m['name'] for m in data.get('models', [])]
        return jsonify({'models': models, 'ok': True})
    except Exception as e:
        return jsonify({'models': [], 'ok': False, 'error': str(e)})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
