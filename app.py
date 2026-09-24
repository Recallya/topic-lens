"""Flask connects the browser UI to the crawler, database, and analytics."""
import csv
import io
import re
import secrets
import threading
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from analytics import analyze, demo_articles, matches_topic, parse_date
from crawler import Crawler, SOURCES, validate_url
from storage import initialize, read_articles, save_articles, topics


def create_app(database=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
    app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1"]
    path = Path(database) if database else Path(__file__).parent / "data" / "topics.sqlite3"
    initialize(path)
    csrf = secrets.token_urlsafe(32)
    jobs, job_lock = {}, threading.Lock()

    @app.before_request
    def check_write_request():
        if request.method == "POST" and request.headers.get("X-TopicLens-Token") != csrf:
            return jsonify(error="Sesi halaman berubah. Muat ulang halaman lalu coba lagi."), 403

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ValueError)
    def bad_input(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error="File maksimal 5 MB." if error.code == 413 else error.description), error.code

    def topic_value(value):
        if not isinstance(value, str) or not 2 <= len(value.strip()) <= 80 or not re.search(r"\w", value):
            raise ValueError("Topik harus berisi 2–80 karakter.")
        return " ".join(value.split())

    @app.get("/")
    def index():
        return render_template("index.html", csrf=csrf)

    @app.get("/api/config")
    def config():
        return jsonify(topics=topics(path), sources=SOURCES)

    @app.get("/api/analysis")
    def analysis():
        topic = topic_value(request.args.get("topic", "Teknologi"))
        granularity = request.args.get("granularity", "monthly")
        if granularity not in ("yearly", "monthly", "daily", "hours"):
            raise ValueError("Periode tidak valid.")
        demo = request.args.get("demo") == "1"
        result = analyze(demo_articles(topic) if demo else read_articles(path, topic), granularity)
        result.update(topic=topic, demo=demo, granularity=granularity)
        return jsonify(result)

    @app.post("/api/crawl")
    def crawl():
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValueError("Permintaan tidak valid.")
        topic = topic_value(payload.get("topic"))
        selected = payload.get("sources", [])
        if not isinstance(selected, list) or any(not isinstance(s, str) or s not in SOURCES for s in selected):
            raise ValueError("Sumber tidak valid.")
        custom = payload.get("urls", [])
        if not isinstance(custom, list) or len(custom) > 3 or any(not isinstance(u, str) for u in custom):
            raise ValueError("Gunakan maksimal tiga URL tambahan.")
        urls = [SOURCES[key]["url"] for key in selected] + [validate_url(u, resolve=False) for u in custom if u.strip()]
        if not urls:
            raise ValueError("Pilih minimal satu sumber atau masukkan URL.")
        try:
            limit = int(payload.get("limit", 40))
        except (TypeError, ValueError):
            raise ValueError("Batas artikel harus berupa angka.")
        if not 5 <= limit <= 100:
            raise ValueError("Batas artikel harus antara 5 dan 100.")
        with job_lock:
            if any(job["state"] == "running" for job in jobs.values()):
                return jsonify(error="Masih ada crawling yang berjalan. Tunggu sampai selesai."), 409
            jobs.clear()
            job_id = secrets.token_hex(12)
            jobs[job_id] = {"state": "running", "message": "Menyiapkan crawler…", "topic": topic}

        def work():
            try:
                def progress(message):
                    jobs[job_id]["message"] = message
                articles, warnings, checked = Crawler().crawl(urls, topic, limit, progress)
                added = save_articles(path, topic, articles)
                jobs[job_id].update(state="done", message=f"Selesai · {checked} diperiksa, {len(articles)} cocok, {added} artikel baru.",
                                    added=added, matched=len(articles), checked=checked, warnings=warnings)
            except Exception:
                app.logger.exception("Crawl failed")
                jobs[job_id].update(state="error", message="Crawling gagal. Periksa koneksi dan coba lagi.")
        threading.Thread(target=work, daemon=True).start()
        return jsonify(id=job_id), 202

    @app.get("/api/jobs/<job_id>")
    def job(job_id):
        if job_id not in jobs:
            return jsonify(error="Proses tidak ditemukan; server mungkin sudah dimulai ulang."), 404
        return jsonify(jobs[job_id])

    @app.post("/api/import")
    def import_archive():
        topic = topic_value(request.form.get("topic"))
        uploaded = request.files.get("file")
        if not uploaded:
            raise ValueError("Pilih file CSV terlebih dahulu.")
        try:
            content = uploaded.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("Simpan CSV dengan encoding UTF-8.")
        reader = csv.DictReader(io.StringIO(content))
        required = {"title", "text", "url", "published_at"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("Kolom wajib: title,text,url,published_at. Kolom source opsional.")
        articles, skipped, invalid = [], 0, 0
        try:
            for index, row in enumerate(reader):
                if index >= 10000:
                    raise ValueError("Maksimal 10.000 baris per impor.")
                title, text = row.get("title") or "", row.get("text") or ""
                if not matches_topic(topic, title + " " + text):
                    skipped += 1
                    continue
                try:
                    url = validate_url(row.get("url") or "", resolve=False)
                    date, precision = parse_date(row.get("published_at"))
                    if not date:
                        raise ValueError("Tanggal tidak valid")
                except ValueError:
                    invalid += 1
                    continue
                articles.append({"title": title[:500], "text": text[:40000], "url": url,
                                 "published_at": date, "date_precision": precision,
                                 "source": (row.get("source") or urlsplit(url).hostname)[:200]})
        except csv.Error:
            raise ValueError("Format CSV tidak dapat dibaca.")
        added = save_articles(path, topic, articles)
        return jsonify(added=added, skipped=skipped, invalid=invalid, duplicates=len(articles)-added,
                       message=f"Impor selesai · {added} baru, {len(articles)-added} duplikat, {skipped} tidak cocok, {invalid} tidak valid.")

    return app
