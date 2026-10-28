import os
import sqlite3
import base64
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, g, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mortuary-secret-2024-pwa')
DATABASE = 'mortuary.db'
MAX_CAPACITY = 100000

# --- PWA: Minimal valid icons (1x1 dark) ---
ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
ICON_BYTES = base64.b64decode(ICON_B64)

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Mortuary Management",
        "short_name": "Mortuary",
        "description": "Mortuary Management System - Republic of Ghana",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1f2937",
        "theme_color": "#1f2937",
        "orientation": "portrait",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@app.route('/sw.js')
def sw():
    js = "self.addEventListener('install', e=>self.skipWaiting());self.addEventListener('activate', e=>self.clients.claim());"
    return Response(js, mimetype='application/javascript')

@app.route('/icon-192.png')
def icon192():
    return Response(ICON_BYTES, mimetype='image/png')

@app.route('/icon-512.png')
def icon512():
    return Response(ICON_BYTES, mimetype='image/png')

# --- DB ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user')''')
        db.execute('''CREATE TABLE IF NOT EXISTS bodies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, age INTEGER, gender TEXT,
            date_deposited TEXT, deposited_by TEXT,
            status TEXT DEFAULT 'deposited')''')
        cur = db.execute("SELECT * FROM users WHERE username='admin'")
        if not cur.fetchone():
            db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
                       ('admin', generate_password_hash('admin123'), 'admin'))
        db.commit()

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_database', None)
    if db: db.close()

def current_user():
    uid = request.cookies.get('user_id')
