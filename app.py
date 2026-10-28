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
@app.route('/reset-admin')
def reset_admin():
    db=get_db()
    db.execute("DELETE FROM users WHERE username='admin'")
    db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)", ('admin', generate_password_hash('admin123'), 'admin'))
    db.commit()
    return "Admin reset! Login: admin / admin123 - <a href='/login'>Click to login</a>"
@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_database', None)
    if db: db.close()

def current_user():
    uid = request.cookies.get('user_id')
    if not uid: return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrap(*a, **kw):
        if not current_user(): return redirect('/login')
        return f(*a, **kw)
    return wrap

BASE_HTML = """
<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mortuary</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#1f2937">
<link rel="apple-touch-icon" href="/icon-192.png">
<script>if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js')}</script>
<style>
body{font-family:Arial;background:#f3f4f6;margin:0}
.nav{background:#1f2937;color:white;padding:12px;display:flex;gap:15px;flex-wrap:wrap}
.nav a{color:white;text-decoration:none;font-weight:bold}
.container{padding:15px;max-width:900px;margin:auto}
.card{background:white;padding:15px;border-radius:8px;box-shadow:0 2px 5px rgba(0,0,0,0.1);margin-bottom:15px}
input,select,button{padding:10px;margin:5px 0;width:100%;box-sizing:border-box}
button{background:#1f2937;color:white;border:none;border-radius:5px;cursor:pointer}
table{width:100%;border-collapse:collapse}
th,td{border:1px solid #ddd;padding:8px;text-align:left}
th{background:#1f2937;color:white}
</style></head><body>
<div class="nav">
<a href="/">Home</a>
<a href="/deposit">Deposit</a>
<a href="/overdue">Overdue</a>
<a href="/users">Users</a>
<a href="/my-account">My Account</a>
<a href="/logout">Logout</a>
</div>
<div class="container">{{content|safe}}</div>
</body></html>
"""

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=request.form['username']; p=request.form['password']
        db=get_db(); user=db.execute("SELECT * FROM users WHERE username=?",(u,)).fetchone()
        if user and check_password_hash(user['password'], p):
            resp=redirect('/')
            resp.set_cookie('user_id', str(user['id']), max_age=86400*30)
            return resp
        return render_template_string(BASE_HTML, content="<div class='card'><h3>Login Failed</h3><a href='/login'>Try again</a></div>")
    return render_template_string(BASE_HTML, content="""
    <div class='card'><h2>Login - Mortuary System</h2>
    <form method='post'><input name='username' placeholder='Username' required>
    <input name='password' type='password' placeholder='Password' required>
    <button>Login</button></form>
    <p>Default: admin / admin123</p></div>""")

@app.route('/logout')
def logout():
    r=redirect('/login'); r.delete_cookie('user_id'); return r

@app.route('/')
@login_required
def home():
    db=get_db()
    count=db.execute("SELECT COUNT(*) as c FROM bodies WHERE status='deposited'").fetchone()['c']
    rows=db.execute("SELECT * FROM bodies WHERE status='deposited' ORDER BY id DESC").fetchall()
    html=f"<div class='card'><h3>Capacity: {count} / {MAX_CAPACITY}</h3><p>Available: {MAX_CAPACITY-count}</p></div>"
    html+="<div class='card'><h3>Deposited Bodies</h3><table><tr><th>ID</th><th>Name</th><th>Age</th><th>Date</th></tr>"
    for r in rows:
        html+=f"<tr><td>{r['id']}</td><td>{r['name']}</td><td>{r['age']}</td><td>{r['date_deposited']}</td></tr>"
    html+="</table></div>"
    return render_template_string(BASE_HTML, content=html)

@app.route('/deposit', methods=['GET','POST'])
@login_required
def deposit():
    if request.method=='POST':
        db=get_db()
        cnt=db.execute("SELECT COUNT(*) as c FROM bodies WHERE status='deposited'").fetchone()['c']
        if cnt>=MAX_CAPACITY:
            return render_template_string(BASE_HTML, content="<div class='card'><h3>Mortuary Full! Max 100000 reached</h3></div>")
        db.execute("INSERT INTO bodies (name,age,gender,date_deposited,deposited_by) VALUES (?,?,?,?,?)",
                   (request.form['name'], request.form['age'], request.form['gender'],
                    datetime.now().strftime("%Y-%m-%d %H:%M"), current_user()['username']))
        db.commit(); return redirect('/')
    return render_template_string(BASE_HTML, content="""
    <div class='card'><h3>Deposit Body</h3><form method='post'>
    <input name='name' placeholder='Full Name' required>
    <input name='age' type='number' placeholder='Age' required>
    <select name='gender'><option>Male</option><option>Female</option></select>
    <button>Deposit</button></form></div>""")

@app.route('/overdue')
@login_required
def overdue():
    db=get_db()
    rows=db.execute("SELECT * FROM bodies WHERE status='deposited'").fetchall()
    html="<div class='card'><h3>Overdue Check (> 6 months)</h3><table><tr><th>ID</th><th>Name</th><th>Date</th></tr>"
    for r in rows:
        try:
            d=datetime.strptime(r['date_deposited'], "%Y-%m-%d %H:%M")
            if datetime.now()-d > timedelta(days=180):
                html+=f"<tr><td>{r['id']}</td><td>{r['name']}</td><td>{r['date_deposited']}</td></tr>"
        except: pass
    html+="</table></div>"
    return render_template_string(BASE_HTML, content=html)

@app.route('/users', methods=['GET','POST'])
@login_required
def users():
    db=get_db(); me=current_user()
    if me['role']!='admin':
        return render_template_string(BASE_HTML, content="<div class='card'><h3>Only Admin can manage users</h3></div>")
    if request.method=='POST':
        if 'new_username' in request.form:
            try:
                db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
                           (request.form['new_username'], generate_password_hash(request.form['new_password']), request.form['role']))
                db.commit()
            except: pass
        return redirect('/users')
    users=db.execute("SELECT * FROM users").fetchall()
    html="<div class='card'><h3>Create User (e.g. Tamale)</h3><form method='post'>"
    html+="<input name='new_username' placeholder='Username e.g. tamale' required>"
    html+="<input name='new_password' placeholder='Password' required>"
    html+="<select name='role'><option value='user'>User</option><option value='admin'>Admin</option></select>"
    html+="<button>Create User</button></form></div><div class='card'><table><tr><th>ID</th><th>Username</th><th>Role</th></tr>"
    for u in users: html+=f"<tr><td>{u['id']}</td><td>{u['username']}</td><td>{u['role']}</td></tr>"
    html+="</table></div>"
    return render_template_string(BASE_HTML, content=html)

@app.route('/my-account', methods=['GET','POST'])
@login_required
def my_account():
    db=get_db(); me=current_user(); msg=""
    if request.method=='POST':
        if 'new_username' in request.form:
            if check_password_hash(me['password'], request.form['current_password']):
                try:
                    db.execute("UPDATE users SET username=? WHERE id=?",(request.form['new_username'], me['id'])); db.commit()
                    msg="Username updated!"
                except: msg="Username exists!"
            else: msg="Wrong current password!"
        if 'new_pass' in request.form:
            if check_password_hash(me['password'], request.form['current_password2']):
                db.execute("UPDATE users SET password=? WHERE id=?",(generate_password_hash(request.form['new_pass']), me['id'])); db.commit()
                msg="Password updated!"
            else: msg="Wrong current password!"
    return render_template_string(BASE_HTML, content=f"""
    <div class='card'><h2>My Account - {me['username']} ({me['role']})</h2><p style='color:green'>{msg}</p></div>
    <div class='card'><h3>Change Username</h3><form method='post'>
    <input name='new_username' placeholder='New Username' required>
    <input name='current_password' type='password' placeholder='Current Password' required>
    <button>Update Username</button></form></div>
    <div class='card'><h3>Change Password</h3><form method='post'>
    <input name='current_password2' type='password' placeholder='Current Password' required>
    <input name='new_pass' type='password' placeholder='New Password' required>
    <button>Update Password</button></form></div>""")

init_db()
if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))
