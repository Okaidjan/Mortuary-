import os, sqlite3, csv
from io import StringIO
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, session, g, jsonify, send_from_directory, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "mortuary-pro-2026-secure-key-ghana")
DATABASE = "mortuary.db"
CAPACITY = 100000

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
    db.execute("""CREATE TABLE IF NOT EXISTS bodies (
        id INTEGER PRIMARY KEY, tag_no TEXT UNIQUE, full_name TEXT, sex TEXT, age TEXT, 
        case_type TEXT, deposited_by TEXT, hospital TEXT, status TEXT DEFAULT 'Deposited', 
        date_in TIMESTAMP DEFAULT CURRENT_TIMESTAMP, date_out TIMESTAMP)""")
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
    db.execute("INSERT INTO audit (action,user,timestamp) VALUES (?,?,?)",
        (action, session.get('username','system'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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

BASE_HTML = """
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="manifest" href="/manifest.json"><style>
body{margin:0;font-family:Arial;background:#f5f6f7}
.nav{background:#0f2a3c;color:#fff;padding:10px 15px;display:flex;gap:15px;overflow:auto;align-items:center;position:sticky;top:0;z-index:10}
.nav a{color:#cfe8ff;text-decoration:none;font-size:13px;white-space:nowrap}.nav a.active{color:#fff;font-weight:bold;border-bottom:2px solid #4caf50}
.nav b{white-space:nowrap}
.container{padding:15px}
.card{background:#fff;border-radius:10px;padding:15px;box-shadow:0 1px 3px rgba(0,0,0,.1);margin-bottom:12px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat h2{margin:5px 0;font-size:28px}.stat p{margin:0;color:#666;font-size:13px}
.chart-bar{display:flex;gap:4px;align-items:end;height:50px;margin-top:10px}
.bar{flex:1;border-radius:3px}.bar.green{background:#4caf50}.bar.amber{background:#ff9800}
.tag{font-family:monospace;background:#111;color:#0f0;padding:4px 8px;border-radius:4px}
input,select,button{width:100%;padding:10px;margin:6px 0;border:1px solid #ccc;border-radius:6px}
button.primary{background:#0f2a3c;color:#fff;border:0;font-weight:bold}
table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:8px;border-bottom:1px solid #eee;font-size:13px;text-align:left}
</style></head><body>
<div class="nav"><b>Mortuary Tracking System</b> 
<a href="/dashboard" class="{{'active' if page=='dashboard'}}">Dashboard</a>
<a href="/records" class="{{'active' if page=='records'}}">Records</a>
<a href="/deposit" class="{{'active' if page=='deposit'}}">+ Deposit</a>
<a href="/audit" class="{{'active' if page=='audit'}}">Audit log</a>
<a href="/users" class="{{'active' if page=='users'}}">Users</a>
<a href="/export">Export CSV</a>
<span style="margin-left:auto">{{session.get('username')}} | <a href="/logout" style="color:#ff8">Logout</a></span>
</div><div class="container">{{content|safe}}</div>
<script>if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{})}</script>
</body></html>
"""

@app.route('/manifest.json')
def manifest():
    return jsonify({"name":"MOH Mortuary","short_name":"MOH","start_url":"/","display":"standalone","background_color":"#0f2a3c","theme_color":"#0f2a3c","icons":[{"src":"/icon-192.png","sizes":"192x192","type":"image/png"},{"src":"/icon-512.png","sizes":"512x512","type":"image/png"}]})

@app.route('/icon-192.png')
def icon192():
    try: return send_from_directory('.','icon-192.png')
    except: return "",204
@app.route('/icon-512.png')
def icon512():
    try: return send_from_directory('.','icon-512.png')
    except: return "",204
@app.route('/sw.js')
def sw():
    return Response("self.addEventListener('fetch',e=>{})", mimetype='application/javascript')

@app.before_request
def before_request():
    try: init_db()
    except: pass

@app.route('/')
def index():
    if 'username' not in session: return redirect('/login')
    return redirect('/dashboard')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        db=get_db()
        cur=db.execute("SELECT * FROM users WHERE username=?", (request.form['username'],))
        user=cur.fetchone()
        if user and check_password_hash(user['password'], request.form['password']):
            session['username']=user['username']; session['role']=user['role']
            log_action(f"Login {user['username']}")
            return redirect('/dashboard')
        return "Invalid - use admin/admin123"
    return render_template_string('<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{background:#0f2a3c;display:flex;justify-content:center;align-items:center;height:100vh;font-family:Arial}.box{background:#fff;padding:25px;border-radius:10px;width:300px}input,button{width:100%;padding:10px;margin:6px 0}</style></head><body><div class="box"><h3>MOH Mortuary Login</h3><form method="post"><input name="username" placeholder="Username"><input name="password" type="password" placeholder="Password"><button>Login</button></form><p style="font-size:12px">admin/admin123<br>staff/staff123</p></div></body></html>')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect('/login')
    db=get_db()
    total=db.execute("SELECT COUNT(*) c FROM bodies WHERE status='Deposited'").fetchone()['c']
    occupancy= (total/CAPACITY*100) if CAPACITY else 0
    month_start=datetime.now().replace(day=1).strftime("%Y-%m-%d")
    dep_month=db.execute("SELECT COUNT(*) c FROM bodies WHERE date(date_in)>=?",(month_start,)).fetchone()['c']
    rel_month=db.execute("SELECT COUNT(*) c FROM bodies WHERE status='Released' AND date(date_out)>=?",(month_start,)).fetchone()['c']
    
    # Last 14 days
    days=[]
    for i in range(14, -1, -1):
        d=(datetime.now()-timedelta(days=i)).strftime("%Y-%m-%d")
        short=(datetime.now()-timedelta(days=i)).strftime("%m-%d")
        cnt=db.execute("SELECT COUNT(*) c FROM bodies WHERE date(date_in)=?",(d,)).fetchone()['c']
        days.append((short,cnt))
    
    longest=db.execute("SELECT * FROM bodies WHERE status='Deposited' ORDER BY date_in ASC LIMIT 1").fetchone()
    
    content=f"""
    <div class="stats">
        <div class="card stat"><h2>{total} / {CAPACITY}</h2><p>Currently stored ({occupancy:.2f}% occupancy)</p></div>
        <div class="card stat"><h2>{dep_month}</h2><p>Deposited this month</p></div>
        <div class="card stat"><h2>{rel_month}</h2><p>Released this month</p></div>
    </div>
    <div class="card">
        <b>Last 14 days (green=deposited, amber=released)</b>
        <div class="chart-bar">
        {"".join([f'<div style="text-align:center;flex:1"><div class="bar green" style="height:{max(5, d[1]*10)}px"></div><small>{d[0]}</small></div>' for d in days])}
        </div>
    </div>
    <div class="card"><b>Longest in store</b><br>
    {f"<span class='tag'>{longest['tag_no']}</span> {longest['full_name']} - since {longest['date_in']}" if longest else "No bodies in store."}
    </div>
    """
    return render_template_string(BASE_HTML, content=content, page='dashboard')

@app.route('/deposit', methods=['GET','POST'])
def deposit():
    if 'username' not in session: return redirect('/login')
    db=get_db()
    if request.method=='POST':
        tag_no=generate_tag_no()
        db.execute("INSERT INTO bodies (tag_no,full_name,sex,age,case_type,deposited_by,hospital) VALUES (?,?,?,?,?,?,?)",
            (tag_no, request.form['full_name'], request.form['sex'], request.form['age'], request.form['case_type'], request.form['deposited_by'], request.form['hospital']))
        db.commit()
        log_action(f"Deposited {tag_no} - {request.form['full_name']}")
        return redirect('/records')
    tag=generate_tag_no()
    content=f"""
    <div class="card" style="max-width:500px;margin:auto">
    <h3>Deposit Body</h3><div style="background:#111;color:#0f0;padding:8px;text-align:center;border-radius:6px">Next Tag: {tag}</div>
    <form method="post">
    <input name="full_name" placeholder="Full Name" required>
    <select name="sex"><option>Male</option><option>Female</option></select>
    <input name="age" placeholder="Age">
    <input name="case_type" placeholder="Case Type">
    <input name="deposited_by" placeholder="Deposited By">
    <input name="hospital" placeholder="Hospital / Ward">
    <button class="primary">Deposit</button></form></div>
    """
    return render_template_string(BASE_HTML, content=content, page='deposit')

@app.route('/records')
def records():
    if 'username' not in session: return redirect('/login')
    db=get_db()
    rows=db.execute("SELECT * FROM bodies ORDER BY id DESC").fetchall()
    rows_html="".join([f"<tr><td><span class='tag'>{r['tag_no']}</span></td><td>{r['full_name']}</td><td>{r['sex']}</td><td>{r['status']}</td><td>{r['date_in']}</td><td><a href='/release/{r['id']}'>Release</a></td></tr>" for r in rows])
    content=f"<div class='card'><table><tr><th>Tag</th><th>Name</th><th>Sex</th><th>Status</th><th>Date In</th><th>Action</th></tr>{rows_html}</table></div>"
    return render_template_string(BASE_HTML, content=content, page='records')

@app.route('/release/<int:bid>')
def release(bid):
    if 'username' not in session: return redirect('/login')
    db=get_db()
    db.execute("UPDATE bodies SET status='Released', date_out=? WHERE id=?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bid))
    db.commit()
    log_action(f"Released body ID {bid}")
    return redirect('/records')

@app.route('/audit')
def audit():
    if 'username' not in session: return redirect('/login')
    db=get_db()
    rows=db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100").fetchall()
    html="".join([f"<tr><td>{r['timestamp']}</td><td>{r['user']}</td><td>{r['action']}</td></tr>" for r in rows])
    content=f"<div class='card'><table><tr><th>Time</th><th>User</th><th>Action</th></tr>{html}</table></div>"
    return render_template_string(BASE_HTML, content=content, page='audit')

@app.route('/users')
def users():
    if 'username' not in session: return redirect('/login')
    db=get_db()
    rows=db.execute("SELECT * FROM users").fetchall()
    html="".join([f"<tr><td>{r['username']}</td><td>{r['role']}</td></tr>" for r in rows])
    content=f"<div class='card'><table><tr><th>Username</th><th>Role</th></tr>{html}</table></div>"
    return render_template_string(BASE_HTML, content=content, page='users')

@app.route('/export')
def export():
    if 'username' not in session: return redirect('/login')
    db=get_db()
    rows=db.execute("SELECT * FROM bodies").fetchall()
    si=StringIO()
    cw=csv.writer(si)
    cw.writerow(['tag_no','full_name','sex','age','case_type','status','date_in'])
    for r in rows: cw.writerow([r['tag_no'],r['full_name'],r['sex'],r['age'],r['case_type'],r['status'],r['date_in']])
    output=si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=mortuary.csv"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__=='__main__':
    app.run(debug=True)
