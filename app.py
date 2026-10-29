import os, sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, g, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "mortuary-pro-2026-secure-key-ghana")
DATABASE = "mortuary.db"

# --- DB ---
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
        status TEXT DEFAULT 'deposited', date_in TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
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

# --- AUTH ---
    


    
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
        init_db()
    except:
        pass





@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        if user and check_password_hash(user['password'], p):
            session['user_id'] = user['id']
            session['username'] = user['username']
            log_action(f"Login: {u}")
            return redirect(url_for('dashboard'))
    return render_template_string("""
    <form method=post style="padding:20px"><h2>Login</h2>
    <input name=username placeholder=Username><br><br>
    <input name=password type=password placeholder=Password><br><br>
    <button>Login</button></form>
    """)

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM bodies").fetchone()[0]
    return render_template_string("""
    <h2>Mortuary Tracking System - Dashboard</h2>
    <p>Total Bodies: {{total}}</p>
    <a href="{{url_for('deposit')}}">+ Deposit Body</a> | <a href="{{url_for('records')}}">Records</a>
    <link rel="manifest" href="/manifest.json">
    """, total=total)

@app.route('/deposit', methods=['GET','POST'])
@login_required
def deposit():
    if request.method == 'POST':
        tag_no = generate_tag_no()  # AUTO GENERATE
        full_name = request.form.get('full_name')
        sex = request.form.get('sex')
        age = request.form.get('age')
        case_type = request.form.get('case_type')
        
        db = get_db()
        db.execute("INSERT INTO bodies (tag_no, full_name, sex, age, case_type, deposited_by, status) VALUES (?,?,?,?,?,?,?)",
                   (tag_no, full_name, sex, age, case_type, session['username'], 'deposited'))
        db.commit()
        log_action(f"Deposited {full_name} - {tag_no}")
        return f"Deposited Successfully! Tag No: {tag_no} <br><a href=/records>View Records</a>"
    
    return render_template_string("""
    <h3>+ Deposit Body</h3>
    <div style="padding:8px; background:#e8f5e9; border-radius:6px; margin-bottom:10px;">
      Tag will be auto-generated (e.g., MOH-2026-0001)
    </div>
    <form method=post>
    <input name=full_name placeholder="Full Name (e.g., Yaa Attaa)" required><br><br>
    <select name=sex><option>Female</option><option>Male</option></select><br><br>
    <input name=age placeholder="Age e.g., 44"><br><br>
    <input name=case_type placeholder="Cause e.g., Natural death"><br><br>
    <button>Deposit</button>
    </form>
    <link rel="manifest" href="/manifest.json">
    """)

@app.route('/records')
@login_required
def records():
    db = get_db()
    bodies = db.execute("SELECT * FROM bodies ORDER BY id DESC").fetchall()
    html = "<h2>Records</h2><table border=1><tr><th>Tag No</th><th>Name</th><th>Sex</th><th>Age</th><th>Status</th></tr>"
    for b in bodies:
        html += f"<tr><td>{b['tag_no']}</td><td>{b['full_name']}</td><td>{b['sex']}</td><td>{b['age']}</td><td>{b['status']}</td></tr>"
    html += "</table>"
    return html

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
