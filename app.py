from flask import Flask, request, redirect, session, Response
import sqlite3, os, random, csv, io
from datetime import datetime

app = Flask(__name__)
app.secret_key = "mortuary-final-2026"
DB = "mortuary.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS bodies (id TEXT PRIMARY KEY, name TEXT, age TEXT, gender TEXT, storage_id TEXT, status TEXT, kin_name TEXT, kin_phone TEXT, created_at TEXT, released_at TEXT, released_to TEXT, total_fee REAL, paid_amount REAL, balance REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)")
    cur = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    if not cur:
        conn.execute("INSERT INTO users VALUES ('admin','admin123','Admin')")
    conn.commit()
    conn.close()
init_db()

def log_page(title, body):
    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{margin:0;font-family:sans-serif;background:#f1f5f9}} .nav{{background:#1e293b;color:#fff;padding:12px;display:flex;gap:12px;flex-wrap:wrap}} .nav a{{color:#38bdf8;text-decoration:none}} .card{{background:#fff;margin:14px;padding:16px;border-radius:10px}} input,select{{width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid #cbd5e1;box-sizing:border-box}} button{{padding:10px 14px;background:#0ea5e9;border:none;border-radius:8px;color:#fff;font-weight:bold}}</style></head><body>
<div class="nav"><b>MORTUARY</b> <a href="/">Dashboard</a> <a href="/records">Records</a> <a href="/deposit">+Deposit</a> <a href="/logout">Logout</a></div>
{body}</body></html>"""

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        conn=get_db(); u=conn.execute("SELECT * FROM users WHERE username=? AND password=?",(request.form['username'],request.form['password'])).fetchone(); conn.close()
        if u: session['user']=u['username']; return redirect('/')
        return log_page("Login", '<div class="card"><h3>Wrong login</h3><a href="/login">Try again</a></div>')
    return log_page("Login", '<div class="card" style="max-width:360px;margin:40px auto"><h2>Login</h2><form method="POST"><input name="username" placeholder="Username" value="admin" required><input name="password" type="password" placeholder="Password" value="admin123" required><button>Login</button></form><p style="font-size:12px;color:#64748b">admin / admin123</p></div>')

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/')
def dash():
    if 'user' not in session: return redirect('/login')
    conn=get_db(); total=conn.execute("SELECT COUNT(*) FROM bodies WHERE status!='Released'").fetchone()[0]; conn.close()
    return log_page("Dashboard", f'<div class="card"><h3>Dashboard</h3><b>{total} / 100000 currently stored</b><p style="color:green">System LIVE! No more 500 error!</p><p><a href="/deposit"><button>+ Deposit New Body</button></a></p></div>')

@app.route('/records')
def records():
    if 'user' not in session: return redirect('/login')
    q=request.args.get('q',''); conn=get_db()
    bodies=conn.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 100").fetchall(); conn.close()
    rows="".join([f"<tr><td><a href='/body/{b['id']}'>{b['id']}</a></td><td>{b['name']}</td><td>{b['storage_id']}</td><td>{b['status']}</td></tr>" for b in bodies])
    return log_page("Records", f'<div class="card"><h3>Records</h3><table style="width:100%;font-size:13px"><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th></tr>{rows}</table></div>')

@app.route('/deposit')
def deposit():
    if 'user' not in session: return redirect('/login')
    return log_page("Deposit", '<div class="card"><h3>Add Body</h3><form method="POST" action="/add"><input name="name" placeholder="Deceased Name *" required><input name="age" placeholder="Age"><select name="gender"><option>Male</option><option>Female</option></select><input name="cause" placeholder="Cause of Death"><hr><input name="kin_name" placeholder="Kin Name"><input name="kin_phone" placeholder="Kin Phone"><button>Deposit + Generate Tag</button></form></div>')

@app.route('/add', methods=['POST'])
def add_body():
    tag=f"MTY-{datetime.now().year}-{random.randint(1000,9999)}"; storage=f"F{random.randint(1,10):02d}-S{random.randint(1,100):03d}"
    conn=get_db(); conn.execute("INSERT INTO bodies (id,name,age,gender,storage_id,status,kin_name,kin_phone,created_at,total_fee,paid_amount,balance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(tag,request.form.get('name'),request.form.get('age'),request.form.get('gender'),storage,'Deposited',request.form.get('kin_name'),request.form.get('kin_phone'),datetime.now().strftime('%Y-%m-%d %H:%M'),150,0,150)); conn.commit(); conn.close()
    return redirect(f'/body/{tag}')

@app.route('/body/<bid>')
def body_detail(bid):
    conn=get_db(); b=conn.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone(); conn.close()
    if not b: return "Not found"
    return log_page("Body", f'<div class="card"><h3>{b["name"]} - {b["id"]}</h3><p>Storage: {b["storage_id"]} | Status: {b["status"]} | Fee: GHS {b["total_fee"]} Paid {b["paid_amount"]} Bal {b["balance"]}</p><div style="text-align:center"><img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={b["id"]}"><br><br><button onclick="window.print()">Print QR Tag</button></div></div><div class="card"><form method="POST" action="/release/{b["id"]}"><input name="collector_name" placeholder="Collector Name" required><button style="background:#dc2626">RELEASE NOW</button></form></div>')

@app.route('/release/<bid>', methods=['POST'])
def release(bid):
    conn=get_db(); conn.execute("UPDATE bodies SET status='Released', released_to=? WHERE id=?",(request.form.get('collector_name'),bid)); conn.commit(); conn.close(); return redirect(f'/body/{bid}')

if __name__=='__main__':
    port=int(os.environ.get("PORT",10000)); app.run(host="0.0.0.0", port=port)
