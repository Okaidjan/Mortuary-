from flask import Flask, request, redirect, session, Response
import sqlite3, os, random, csv, io
from datetime import datetime

app = Flask(__name__)
app.secret_key = "mortuary-full-2026"
DB = "mortuary.db"
ADMISSION = 100
DAILY = 50

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS bodies (id TEXT PRIMARY KEY, name TEXT, age TEXT, gender TEXT, cause TEXT, storage_id TEXT, hospital TEXT, status TEXT, kin_name TEXT, kin_phone TEXT, kin_rel TEXT, kin_id TEXT, created_at TEXT, released_at TEXT, released_to TEXT, released_doc TEXT, total_fee REAL, paid_amount REAL, balance REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, hospital TEXT, username TEXT, password TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, user TEXT, action TEXT, tag_id TEXT, details TEXT)")
    if not conn.execute("SELECT * FROM users WHERE username='admin'").fetchone():
        conn.execute("INSERT INTO users VALUES ('admin','admin123','Admin')")
    if not conn.execute("SELECT * FROM settings WHERE id=1").fetchone():
        conn.execute("INSERT INTO settings VALUES (1,'Korle Bu Teaching Hospital','admin','admin123')")
    conn.commit()
    conn.close()
init_db()

def log_audit(user, action, tag, details):
    try:
        c=get_db(); c.execute("INSERT INTO audit (time,user,action,tag_id,details) VALUES (?,?,?,?,?)",(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),user,action,tag,details)); c.commit(); c.close()
    except: pass

def get_settings():
    c=get_db(); s=c.execute("SELECT * FROM settings WHERE id=1").fetchone(); c.close(); return s

def free_storage():
    c=get_db(); used=[r[0] for r in c.execute("SELECT storage_id FROM bodies WHERE status!='Released'").fetchall()]; c.close()
    for i in range(1,100000):
        f=f"F{(i//100)+1:02d}-S{(i%100)+1:03d}"
        if f not in used: return f
    return "F99-S999"

def calc_fee(created_str):
    try: dt=datetime.strptime(created_str, '%Y-%m-%d %H:%M')
    except: dt=datetime.now()
    days=(datetime.now()-dt).days
    if days<1: days=1
    return days, ADMISSION + DAILY*days

def page(title, body):
    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
body{{margin:0;font-family:-apple-system,sans-serif;background:#f1f5f9}} 
.nav{{background:#0f172a;color:#fff;padding:10px 12px;display:flex;gap:10px;flex-wrap:wrap;font-size:13px;align-items:center}} 
.nav a{{color:#94a3b8;text-decoration:none;padding:4px 8px;border-radius:6px}} .nav a.active{{background:#1e293b;color:#38bdf8}}
.card{{background:#fff;margin:12px;padding:16px;border-radius:12px;box-shadow:0 1px 2px rgba(0,0,0,.06)}} 
input,select{{width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid #cbd5e1;box-sizing:border-box}} 
button{{padding:10px 14px;border:none;border-radius:8px;font-weight:700;cursor:pointer}} .btn{{background:#0ea5e9;color:#fff}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left}}
.badge{{padding:2px 8px;border-radius:999px;font-size:11px}} .deposited{{background:#dcfce7;color:#166534}} .released{{background:#fee2e2;color:#991b1b}}
</style></head><body>
<div class="nav"><b style="color:#fff">🏥 MORTUARY</b> <a href="/" class="active">Dashboard</a> <a href="/records">Records</a> <a href="/deposit">+Deposit</a> <a href="/audit">Audit</a> <a href="/users">Users</a> <a href="/export/csv">Export</a> <a href="/settings">Settings</a> <a href="/logout" style="margin-left:auto">{session.get('user','')} • Logout</a></div>
{body}</body></html>"""

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        c=get_db(); u=c.execute("SELECT * FROM users WHERE username=? AND password=?",(request.form['username'],request.form['password'])).fetchone(); c.close()
        if u:
            session['user']=u['username']; session['hospital']=get_settings()['hospital']; log_audit(u['username'],"LOGIN","",""); return redirect('/')
        return page("Login", '<div class="card" style="max-width:360px;margin:60px auto"><h3 style="color:red">Wrong login</h3><a href="/login">Try again</a></div>')
    return page("Login", '<div class="card" style="max-width:360px;margin:60px auto"><h2>Login</h2><form method="POST"><input name="username" placeholder="Username" value="admin" required><input name="password" type="password" placeholder="Password" value="admin123" required><button class="btn" style="width:100%">Login</button></form><p style="font-size:11px;color:#64748b;margin-top:10px">Default: admin / admin123</p></div>')

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/')
def dash():
    if 'user' not in session: return redirect('/login')
    c=get_db()
    total=c.execute("SELECT COUNT(*) FROM bodies WHERE status!='Released'").fetchone()[0]
    dep_today=c.execute("SELECT COUNT(*) FROM bodies WHERE date(created_at)=date('now')").fetchone()[0]
    rel_today=c.execute("SELECT COUNT(*) FROM bodies WHERE status='Released' AND date(released_at)=date('now')").fetchone()[0]
    revenue=c.execute("SELECT COALESCE(SUM(paid_amount),0) FROM bodies").fetchone()[0]
    c.close()
    return page("Dashboard", f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:12px"><div class="card"><b style="font-size:22px">{total} / 100000</b><br><small>Currently stored</small></div><div class="card"><b style="font-size:22px">{dep_today}</b><br><small>Deposited today</small></div><div class="card"><b style="font-size:22px">{rel_today}</b><br><small>Released today</small></div></div><div class="card"><h3>Revenue: GHS {revenue}</h3><p style="color:green">System LIVE ✅ Fees: GHS {ADMISSION} admission + GHS {DAILY}/day</p><a href="/deposit"><button class="btn">+ Deposit New Body</button></a> <a href="/records"><button>View Records</button></a></div>')

@app.route('/records')
def records():
    if 'user' not in session: return redirect('/login')
    q=request.args.get('q','').strip()
    c=get_db()
    if q:
        bodies=c.execute("SELECT * FROM bodies WHERE id LIKE ? OR name LIKE ? OR kin_phone LIKE ? ORDER BY created_at DESC",(f'%{q}%',f'%{q}%',f'%{q}%')).fetchall()
    else:
        bodies=c.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 200").fetchall()
    c.close()
    rows="".join([f"<tr><td><a href='/body/{b['id']}'><b>{b['id']}</b></a></td><td>{b['name']}</td><td>{b['storage_id']}</td><td><span class='badge {b['status'].lower()}'>{b['status']}</span></
