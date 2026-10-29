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
    db.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS bodies (id INTEGER PRIMARY KEY, tag_no TEXT UNIQUE, full_name TEXT, sex TEXT, age TEXT, case_type TEXT, deposited_by TEXT, hospital TEXT, status TEXT DEFAULT 'Deposited', date_in TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("""CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, action TEXT, user TEXT, timestamp TEXT)""")
    cur = db.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)", ('admin', generate_password_hash('admin123'), 'admin'))
    cur = db.execute("SELECT * FROM users WHERE username='staff'")
    if not cur.fetchone():
        db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)", ('staff', generate_password_hash('staff123'), 'staff'))
    db.commit()

def log_action(action):
    db = get_db()
    db.execute("INSERT INTO audit (action,user,timestamp) VALUES (?,?,?)", (action, session.get('username','system'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()

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

@app.route('/manifest.json')
def manifest():
    return jsonify({"name": "MOH Mortuary", "short_name": "MOH", "start_url": "/", "display": "standalone", "background_color": "#0a0a0a", "theme_color": "#0a0a0a", "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}]})

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

@app.route('/')
def index():
    if 'username' not in session:
        return redirect('/login')
    return redirect('/deposit')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        db = get_db()
        cur = db.execute("SELECT * FROM users WHERE username=?", (request.form['username'],))
        user = cur.fetchone()
        if user and check_password_hash(user['password'], request.form['password']):
            session['username']=user['username']; session['role']=user['role']
            log_action(f"Login {user['username']}")
            return redirect('/deposit')
        return "Invalid login - try admin/admin123"
    return render_template_string('<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="/manifest.json"><style>body{font-family:Arial;background:#111;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh}.box{background:#222;padding:30px;border-radius:10px;width:300px}input,button{width:100%;padding:10px;margin:5px 0}button{background:#0a0;color:#fff;border:0}</style></head><body><div class="box"><h3>MOH Mortuary Login</h3><form method="post"><input name="username" placeholder="Username"><input name="password" type="password" placeholder="Password"><button>Login</button></form><p>admin/admin123<br>staff/staff123</p></div></body></html>')

@app.route('/deposit', methods=['GET','POST'])
def deposit():
    if 'username' not in session:
        return redirect('/login')
    db = get_db()
    if request.method == 'POST':
        tag_no = generate_tag_no()
        db.execute("INSERT INTO bodies (tag_no,full_name,sex,age,case_type,deposited_by,hospital) VALUES (?,?,?,?,?,?,?)", (tag_no, request.form['full_name'], request.form['sex'], request.form['age'], request.form['case_type'], request.form['deposited_by'], request.form['hospital']))
        db.commit()
        log_action(f"Deposited {tag_no} - {request.form['full_name']}")
        return redirect('/records')
    tag = generate_tag_no()
    return render_template_string('<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="/manifest.json"><style>body{font-family:Arial;background:#f4f4f4;padding:20px}.box{background:#fff;padding:20px;max-width:500px;margin:auto;border-radius:10px}input,select,button{width:100%;padding:10px;margin:5px 0}button{background:#0a0;color:#fff;border:0}.tag{background:#111;color:#0f0;padding:10px;text-align:center;font-weight:bold}</style></head><body><div class="box"><h3>Deposit Body</h3><div class="tag">Next Tag: {{tag}}</div><form method="post"><input name="full_name" placeholder="Full Name" required><select name="sex"><option>Male</option><option>Female</option></select><input name="age" placeholder="Age"><input name="case_type" placeholder="Case Type"><input name="deposited_by" placeholder="Deposited By"><input name="hospital" placeholder="Hospital"><button>Deposit</button></form><p><a href="/records">View Records</a> | <a href="/logout">Logout</a></p></div></body></html>', tag=tag)

@app.route('/records')
def records():
    if 'username' not in session:
        return redirect('/login')
    db = get_db()
    cur = db.execute("SELECT * FROM bodies ORDER BY id DESC")
    rows = cur.fetchall()
    html = "<h2>Records</h2><a href='/deposit'>Deposit</a> | <a href='/logout'>Logout</a><table border=1 cellpadding=5><tr><th>Tag</th><th>Name</th><th>Status</th></tr>"
    for r in rows:
        html += f"<tr><td>{r['tag_no']}</td><td>{r['full_name']}</td><td>{r['status']}</td></tr>"
    html += "</table>"
    return html

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)
