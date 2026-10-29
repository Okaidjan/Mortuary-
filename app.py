import os, sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, g, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "mortuary-pro-2026-secure-key-ghana")
DATABASE = "mortuary.db"

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(ex):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS bodies (
        id INTEGER PRIMARY KEY, tag_no TEXT UNIQUE, full_name TEXT, sex TEXT,
        age TEXT, case_type TEXT, deposited_by TEXT, hospital TEXT,
        status TEXT DEFAULT 'Deposited', date_in TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY, action TEXT, user TEXT, timestamp TEXT)""")
    
    cur = db.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
            ('admin', generate_password_hash('admin123'), 'admin'))
    
    cur = db.execute("SELECT * FROM users WHERE username='staff'")
    if not cur.fetchone():
        db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
            ('staff', generate_password_hash('staff123'), 'staff'))
    db.commit()

def log_action(action):
    db = get_db()
    db.execute("INSERT INTO audit (action,user,timestamp) VALUES (?,?,?)",
        (action, session.get('username','system'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()

# --- AUTO TAG GENERATOR ---
def generate_tag_no():
    db = get_db()
    year = datetime.now().year
    prefix = f"MOH-{year}-"
    cur = db.execute("SELECT tag_no FROM bodies WHERE tag_no LIKE ? ORDER BY id DESC LIMIT 1", (f"{prefix}%",))
    row = cur.fetchone()
    if row and row['tag_no']:
        try:
            last_num = int(row['tag_no'].split('-')[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    return f"{prefix}{new_num:04d}"

# --- MANIFEST ---
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Ministry of Health - Mortuary Tracking",
        "short_name": "MOH Mortuary",
        "description": "Republic of Ghana Ministry of Health",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0a0a",
        "theme_color": "#0a0a0a",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@app.route('/icon-192.png')
def icon192():
    try:
        return send_from_directory('.', 'icon-192.png')
    except:
        return "", 204

@app.route('/icon-512.png')
def icon512():
    try:
        return send_from_directory('.', 'icon-512.png')
    except:
        return "", 204

@app.before_request
def before_request():
    try:
        init_db()
    except:
        pass

# --- ADD YOUR OTHER ROUTES BELOW HERE (login, deposit, records etc) ---
# Make sure deposit route has: tag_no = generate_tag_no()
