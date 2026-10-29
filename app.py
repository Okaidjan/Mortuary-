import os, sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, g, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mortuary-pro-2026-secure-key-ghana')
DATABASE = 'mortuary.db'

# --- DB ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS users 
    (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS bodies
    (id INTEGER PRIMARY KEY, tag_no TEXT, full_name TEXT, sex TEXT, age TEXT, case_type TEXT,
     deposited_date TEXT, released_date TEXT, deposited_by TEXT, released_by TEXT, hospital TEXT, status TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS audit
    (id INTEGER PRIMARY KEY, action TEXT, user TEXT, timestamp TEXT)''')
    
    cur = db.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
                   ('admin', generate_password_hash('admin123'), 'admin'))
    # Create default hospitals
    for u,p in [('korlebu','korlebu123'), ('tamale','tamale123'), ('accra','accra123')]:
        cur = db.execute("SELECT * FROM users WHERE username=?", (u,))
        if not cur.fetchone():
            db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
                       (u, generate_password_hash(p), 'staff'))
    db.commit()

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- AUTH ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

def log_action(action):
    db = get_db()
    db.execute("INSERT INTO audit (action,user,timestamp) VALUES (?,?,?)",
               (action, session.get('username','system'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()

# --- PWA FILES ---
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Mortuary Tracking System",
        "short_name": "Mortuary",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f2f3c",
        "theme_color": "#0f2f3c",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@app.route('/icon-192.png')
@app.route('/icon-512.png')
def icon():
    # Simple pro icon generated as SVG -> PNG style placeholder (solid color with text)
    # Using 1x1 pixel trick to make Chrome happy, but returns real PNG header
    from PIL import Image
    import io
    size = 192 if '192' in request.path else 512
    img = Image.new('RGB', (size, size), color=(15, 47, 60))
    # We can't draw text without font, so solid is enough for installability
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')

@app.route('/sw.js')
def sw():
    return Response("self.addEventListener('install', e=>self.skipWaiting());self.addEventListener('fetch', e=>e.respondWith(fetch(e.request)));", mimetype='application/javascript')

# --- TEMPLATES ---
BASE_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0f2f3c">
<title>Mortuary Tracking</title>
<style>
body{font-family:system-ui,Arial;margin:0;background:#f3f5f7}
.nav{background:#0f2f3c;color:#fff;padding:14px 20px;display:flex;gap:18px;flex-wrap:wrap}
.nav a{color:#b7d1db;text-decoration:none}.nav a.active{color:#fff;font-weight:600}
.card{background:#fff;border-radius:14px;padding:16px;margin:12px;box-shadow:0 2px 10px rgba(0,0,0,.06)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat h1{margin:0;font-size:28px}
.btn{background:#0f2f3c;color:#fff;border:0;padding:10px 14px;border-radius:8px}
input,select{width:100%;padding:10px;border:1px solid #ccc;border-radius:8px;margin:6px 0}
table{width:100%;border-collapse:collapse}th{background:#0f2f3c;color:#fff;padding:8px}td{padding:8px;border-bottom:1px solid #eee}
.badge{padding:3px 8px;border-radius:20px;font-size:12px}.in{background:#e6f7ed;color:#0a7a33}.out{background:#fff3cd;color:#8a6d00}
</style>
</head>
<body>
<div class="nav">
<a href="/" class="{{'active' if page=='dash'}}">Mortuary Tracking System</a>
<a href="/" class="{{'active' if page=='dash'}}">Dashboard</a>
<a href="/records">Records</a>
<a href="/deposit">+ Deposit</a>
<a href="/audit">Audit log</a>
<a href="/users">Users</a>
<a href="/export">Export CSV</a>
<span style="margin-left:auto">{{session.username}} ({{session.role}}) <a href="/logout" style="color:#fff;border:1px solid #fff;padding:4px 10px;border-radius:20px">Log out</a></span>
</div>
{% block body %}{% endblock %}
<script>if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js')}</script>
</body>
</html>
"""

# --- ROUTES ---
@app.route('/login', methods=['GET','POST'])
def login():
    init_db()
    if request.method=='POST':
        db=get_db()
        u=db.execute("SELECT * FROM users WHERE username=?", (request.form['username'].strip().lower(),)).fetchone()
        if u and check_password_hash(u['password'], request.form['password']):
            session['user_id']=u['id']; session['username']=u['username']; session['role']=u['role']
            log_action(f"Login {u['username']}")
            return redirect('/')
        return render_template_string("<p style='color:red;text-align:center'>Login Failed</p>"+BASE_HTML.replace("{% block body %}{% endblock %}","<div class=card><h3>Login</h3><form method=post><input name=username placeholder=Username><input name=password type=password placeholder=Password><button class=btn>Login</button></form></div>"), page='login')
    return render_template_string(BASE_HTML.replace("{% block body %}{% endblock %}","<div class=card><h3>Login</h3><form method=post><input name=username placeholder=Username><input name=password type=password placeholder=Password><button class=btn>Login</button></form></div>"), page='login')

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/')
@login_required
def dashboard():
    init_db()
    db=get_db()
    total=db.execute("SELECT COUNT(*) FROM bodies WHERE status='in'").fetchone()[0]
    this_month=db.execute("SELECT COUNT(*) FROM bodies WHERE deposited_date LIKE ?", (datetime.now().strftime("%Y-%m-")+"%",)).fetchone()[0]
    released_month=db.execute("SELECT COUNT(*) FROM bodies WHERE released_date LIKE ?", (datetime.now().strftime("%Y-%m-")+"%",)).fetchone()[0]
    overdue=db.execute("SELECT COUNT(*) FROM bodies WHERE status='in' AND julianday('now')-julianday(deposited_date) > 30").fetchone()[0]
    # Last 14 days
    days=[]
    for i in range(14, -1, -1):
        d=(datetime.now()-timedelta(days=i)).strftime("%Y-%m-%d")
        dep=db.execute("SELECT COUNT(*) FROM bodies WHERE deposited_date=?", (d,)).fetchone()[0]
        rel=db.execute("SELECT COUNT(*) FROM bodies WHERE released_date=?", (d,)).fetchone()[0]
        days.append((d[5:], dep, rel))
    longest=db.execute("SELECT * FROM bodies WHERE status='in' ORDER BY deposited_date ASC LIMIT 5").fetchall()
    html=f"""
    <div class=grid>
      <h1>{total} / 100000</h1>Currently stored ({total/1000:.2f}% occupancy)
      <div class="card stat"><h1>{this_month}</h1>Deposited this month</div>
      <div class="card stat"><h1>{released_month}</h1>Released this month</div>
      <div class="card stat"><h1 style="color:{'red' if overdue>0 else 'green'}">{overdue}</h1>Over 30 days in store</div>
    </div>
    <div class=card><b>Last 14 days</b> (green=deposited, amber=released)<br><br>
      <div style="display:flex;gap:4px;align-items:end;height:60px">
      {"".join([f"<div style='flex:1;text-align:center'><div style='background:#2ecc71;height:{d[1]*10+4}px'></div><div style='background:#f1c40f;height:{d[2]*10+4}px;margin-top:2px'></div><small>{d[0]}</small></div>" for d in days])}
      </div>
    </div>
    <div class=card><b>Longest in store</b><br>{"<br>".join([f"{r['full_name']} - {r['tag_no']} - {(datetime.now()-datetime.strptime(r['deposited_date'],'%Y-%m-%d')).days} days" for r in longest]) if longest else "No bodies in store."}</div>
    """
    return render_template_string(BASE_HTML.replace("{% block body %}{% endblock %}", html), page='dash')

@app.route('/users', methods=['GET','POST'])
@login_required
def users():
    db=get_db()
    if request.method=='POST' and session['role']=='admin':
        try:
            db.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
                       (request.form['username'].strip().lower(), generate_password_hash(request.form['password']), request.form['role']))
            db.commit(); log_action(f"Created user {request.form['username']}")
        except: pass
    users=db.execute("SELECT id,username,role FROM users").fetchall()
    rows="".join([f"<tr><td>{u['id']}</td><td>{u['username']}</td><td>{u['role']}</td></tr>" for u in users])
    html=f"""
    <div class=card><h3>Create User (e.g. Tamale)</h3>
    <form method=post><input name=username placeholder="username e.g. korlebu" required>
    <input name=password placeholder="password" required>
    <select name=role><option>staff</option><option>admin</option></select>
    <button class=btn>Create User</button></form></div>
    <div class=card><table><tr><th>ID</th><th>Username</th><th>Role</th></tr>{rows}</table>
    <p><small>Default: korlebu/korlebu123, tamale/tamale123, accra/accra123</small></p></div>
    """
    return render_template_string(BASE_HTML.replace("{% block body %}{% endblock %}", html), page='users')

@app.route('/deposit', methods=['GET','POST'])
@login_required
def deposit():
    if request.method=='POST':
        db=get_db()
        db.execute("INSERT INTO bodies (tag_no,full_name,sex,age,case_type,deposited_date,status,deposited_by,hospital) VALUES (?,?,?,?,?,?,?,?,?)",
                   (request.form['tag'], request.form['name'], request.form['sex'], request.form['age'], request.form['case'], datetime.now().strftime("%Y-%m-%d"), 'in', session['username'], session['username']))
        db.commit(); log_action(f"Deposited {request.form['name']}")
        return redirect('/')
    html="""<div class=card><h3>+ Deposit Body</h3><form method=post>
    <input name=tag placeholder="Tag No" required><input name=name placeholder="Full Name" required>
    <select name=sex><option>Male</option><option>Female</option></select>
    <input name=age placeholder=Age><input name=case placeholder="Case Type e.g. Accident">
    <button class=btn>Deposit</button></form></div>"""
    return render_template_string(BASE_HTML.replace("{% block body %}{% endblock %}", html), page='deposit')

@app.route('/records')
@login_required
def records():
    db=get_db(); q=request.args.get('q','')
    if q:
        rows=db.execute("SELECT * FROM bodies WHERE full_name LIKE ? OR tag_no LIKE ? ORDER BY id DESC", (f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows=db.execute("SELECT * FROM bodies ORDER BY id DESC LIMIT 100").fetchall()
    tr="".join([f"<tr><td>{r['tag_no']}</td><td>{r['full_name']}</td><td>{r['status']}</td><td>{r['deposited_date']}</td><td><a href='/release/{r['id']}'>Release</a></td></tr>" for r in rows])
    html=f"""<div class=card><form><input name=q value="{q}" placeholder="Search name or tag"><button class=btn>Search</button></form></div>
    <div class=card><table><tr><th>Tag</th><th>Name</th><th>Status</th><th>Date</th><th>Action</th></tr>{tr}</table></div>"""
    return render_template_string(BASE_HTML.replace("{% block body %}{% endblock %}", html), page='records')

@app.route('/release/<int:id>')
@login_required
def release(id):
    db=get_db()
    db.execute("UPDATE bodies SET status='out', released_date=?, released_by=? WHERE id=?", (datetime.now().strftime("%Y-%m-%d"), session['username'], id))
    db.commit(); log_action(f"Released body {id}")
    return redirect('/records')

@app.route('/audit')
@login_required
def audit():
    db=get_db(); rows=db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100").fetchall()
    tr="".join([f"<tr><td>{r['timestamp']}</td><td>{r['user']}</td><td>{r['action']}</td></tr>" for r in rows])
    return render_template_string(BASE_HTML.replace("{% block body %}{% endblock %}", f"<div class=card><table><tr><th>Time</th><th>User</th><th>Action</th></tr>{tr}</table></div>"), page='audit')

@app.route('/export')
@login_required
def export():
    db=get_db(); rows=db.execute("SELECT * FROM bodies").fetchall()
    csv="tag_no,full_name,sex,age,case_type,deposited_date,status\n"
    for r in rows: csv+=f"{r['tag_no']},{r['full_name']},{r['sex']},{r['age']},{r['case_type']},{r['deposited_date']},{r['status']}\n"
    return Response(csv, mimetype='text/csv', headers={"Content-Disposition":"attachment;filename=mortuary.csv"})

if __name__=='__main__':
    with app.app_context(): init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000))) 
