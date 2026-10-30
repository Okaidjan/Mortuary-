from flask import Flask, request, redirect, session, Response
import sqlite3, os, random, csv, io
from datetime import datetime

app = Flask(__name__)
app.secret_key = "mortuary-v3-2026-secure"
DB = "mortuary.db"
ADMISSION = 100
DAILY = 50

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS bodies (id TEXT PRIMARY KEY, name TEXT, age TEXT, gender TEXT, cause TEXT, storage_id TEXT, hospital TEXT, status TEXT, kin_name TEXT, kin_phone TEXT, kin_rel TEXT, kin_id TEXT, created_at TEXT, released_at TEXT, released_to TEXT, released_doc TEXT, death_cert TEXT, police_case TEXT, embalming TEXT, refrigeration TEXT, total_fee REAL, paid_amount REAL, balance REAL, notes TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, hospital TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, user TEXT, action TEXT, tag_id TEXT, details TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, tag_id TEXT, amount REAL, time TEXT, user TEXT)")
    if not conn.execute("SELECT * FROM users WHERE username='admin'").fetchone():
        conn.execute("INSERT INTO users VALUES ('admin','admin123','Admin')")
    if not conn.execute("SELECT * FROM settings WHERE id=1").fetchone():
        conn.execute("INSERT INTO settings VALUES (1,'Korle Bu Teaching Hospital')")
    conn.commit()
    conn.close()
init_db()

def log_audit(u,a,t,d):
    try:
        c=get_db()
        c.execute("INSERT INTO audit (time,user,action,tag_id,details) VALUES (?,?,?,?,?)",(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),u,a,t,d))
        c.commit()
        c.close()
    except:
        pass

def free_storage():
    c=get_db()
    used=[r[0] for r in c.execute("SELECT storage_id FROM bodies WHERE status!='Released'").fetchall()]
    c.close()
    for i in range(1,100000):
        f="F{(i//100)+1:02d}-S{(i%100)+1:03d}"
        if f not in used:
            return f
    return "F99-S999"

def calc_fee(created_str):
    try:
        dt=datetime.strptime(created_str, '%Y-%m-%d %H:%M')
    except:
        dt=datetime.now()
    days=(datetime.now()-dt).days
    if days<1:
        days=1
    return days, ADMISSION + DAILY*days

def page(title, body):
    user = session.get('user','')
    html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>"""+title+"""</title>
<style>
body{margin:0;font-family:-apple-system,sans-serif;background:#f4f6f9}
.nav{background:#0f172a;color:#fff;padding:10px 12px;display:flex;gap:8px;flex-wrap:wrap;font-size:13px;align-items:center}
.nav a{color:#94a3b8;text-decoration:none;padding:5px 9px;border-radius:6px}
.card{background:#fff;margin:12px;padding:16px;border-radius:12px;box-shadow:0 1px 2px rgba(0,0,0,.06)}
input,select,textarea{width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid #cbd5e1;box-sizing:border-box}
button{padding:10px 14px;border:none;border-radius:8px;font-weight:700}
.btn{background:#0ea5e9;color:#fff}
.badge{padding:2px 8px;border-radius:999px;font-size:11px}
.deposited{background:#dcfce7;color:#166534}
.released{background:#fee2e2;color:#991b1b}
.alert{background:#fef3c7;border:1px solid #fcd34d;padding:10px;border-radius:8px;margin:12px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left}
</style></head><body>
<div class="nav"><b style="color:#fff">MORTUARY</b> <a href="/">Dashboard</a> <a href="/records">Records</a> <a href="/deposit">+Deposit</a> <a href="/audit">Audit</a> <a href="/users">Users</a> <a href="/export/csv">Export</a> <a href="/settings">Settings</a> <a href="/logout" style="margin-left:auto">Logout """+user+"""</a></div>
"""+body+"""</body></html>"""
    return html

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        c=get_db()
        u=c.execute("SELECT * FROM users WHERE username=? AND password=?",(request.form['username'],request.form['password'])).fetchone()
        c.close()
        if u:
            session['user']=u['username']
            log_audit(u['username'],"LOGIN","","")
            return redirect('/')
        return page("Login", '<div class="card" style="max-width:360px;margin:80px auto;text-align:center"><h3 style="color:#dc2626">Invalid credentials</h3><a href="/login">Try again</a></div>')
    return page("Login", '<div class="card" style="max-width:360px;margin:80px auto"><h2 style="text-align:center">Mortuary System</h2><p style="text-align:center;color:#64748b;font-size:13px">Secure Login</p><form method="POST"><input name="username" placeholder="Username" required><input name="password" type="password" placeholder="Password" required><button class="btn" style="width:100%;margin-top:8px">Login</button></form></div>')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def dash():
    if 'user' not in session:
        return redirect('/login')
    c=get_db()
    total=c.execute("SELECT COUNT(*) FROM bodies WHERE status!='Released'").fetchone()[0]
    dep_today=c.execute("SELECT COUNT(*) FROM bodies WHERE date(created_at)=date('now')").fetchone()[0]
    revenue=c.execute("SELECT COALESCE(SUM(paid_amount),0) FROM bodies").fetchone()[0]
    unclaimed=c.execute("SELECT COUNT(*) FROM bodies WHERE status!='Released' AND julianday('now')-julianday(created_at)>30").fetchone()[0]
    recent=c.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 5").fetchall()
    c.close()
    alert = ''
    if unclaimed>0:
        alert = '<div class="alert">Warning: '+str(unclaimed)+' bodies unclaimed >30 days</div>'
    recent_rows=""
    for b in recent:
        recent_rows+="<tr><td><a href='/body/"+b['id']+"'>"+b['id']+"</a></td><td>"+(b['name'] or '')+"</td><td>"+(b['storage_id'] or '')+"</td></tr>"
    return page("Dashboard", alert+'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:12px"><div class="card"><b style="font-size:22px">'+str(total)+' / 100k</b><br><small>In storage</small></div><div class="card"><b style="font-size:22px">'+str(dep_today)+'</b><br><small>Today in</small></div><div class="card"><b style="font-size:22px">GHS '+str(revenue)+'</b><br><small>Revenue</small></div></div><div class="card"><h3>Recent Deposits</h3><table><tr><th>Tag</th><th>Name</th><th>Storage</th></tr>'+recent_rows+'</table></div><div class="card"><a href="/deposit"><button class="btn">+ Deposit</button></a> <a href="/records"><button>View All Records</button></a></div>')

@app.route('/records')
def records():
    if 'user' not in session:
        return redirect('/login')
    q=request.args.get('q','').strip()
    status=request.args.get('status','')
    c=get_db()
    query="SELECT * FROM bodies WHERE 1=1"
    params=[]
    if q:
        query+=" AND (id LIKE ? OR name LIKE ? OR kin_phone LIKE ?)"
        params.extend(['%'+q+'%']*3)
    if status:
        query+=" AND status=?"
        params.append(status)
    query+=" ORDER BY created_at DESC LIMIT 300"
    bodies=c.execute(query, params).fetchall()
    c.close()
    rows=""
    for b in bodies:
        rows+="<tr><td><a href='/body/"+b['id']+"'><b>"+b['id']+"</b></a></td><td>"+(b['name'] or '')+"</td><td>"+(b['storage_id'] or '')+"</td><td><span class='badge "+(b['status'] or '').lower()+"'>"+(b['status'] or '')+"</span></td><td>GHS "+str(b['balance'] or 0)+"</td></tr>"
    sel1="selected" if status=="Deposited" else ""
    sel2="selected" if status=="Released" else ""
    return page("Records", '<div class="card"><form method="GET" style="display:flex;gap:6px;flex-wrap:wrap"><input name="q" value="'+q+'" placeholder="Search" style="flex:1;margin:0"><select name="status" style="width:auto;margin:0"><option value="">All</option><option '+sel1+'>Deposited</option><option '+sel2+'>Released</option></select><button class="btn">Filter</button></form></div><div class="card"><h3>'+str(len(bodies))+' Records</h3><table><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th><th>Bal</th></tr>'+rows+'</table></div>')

@app.route('/deposit')
def deposit():
    if 'user' not in session:
        return redirect('/login')
    return page("Deposit", '<div class="card"><h3>Deposit Body</h3><form method="POST" action="/add"><input name="name" placeholder="Deceased Full Name *" required><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><input name="age" placeholder="Age"><select name="gender"><option>Male</option><option>Female</option><option>Other</option></select></div><input name="cause" placeholder="Cause of Death"><input name="death_cert" placeholder="Death Certificate No."><div style="display:flex;gap:12px"><label style="font-size:13px"><input type="checkbox" name="police_case" style="width:auto"> Police Case</label><label style="font-size:13px"><input type="checkbox" name="embalming" style="width:auto"> Embalming</label><label style="font-size:13px"><input type="checkbox" name="refrigeration" checked style="width:auto"> Fridge</label></div><textarea name="notes" placeholder="Additional Notes"></textarea><hr><h4>Next of Kin</h4><input name="kin_name" placeholder="Kin Full Name"><input name="kin_phone" placeholder="Kin Phone"><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><input name="kin_rel" placeholder="Relationship"><input name="kin_id" placeholder="Ghana Card ID"></div><button class="btn" style="width:100%;margin-top:10px">Deposit + Generate QR</button></form></div>')

@app.route('/add', methods=['POST'])
def add_body():
    if 'user' not in session:
        return redirect('/login')
    tag="MTY-"+str(datetime.now().year)+"-"+str(random.randint(1000,9999))
    storage=free_storage()
    conn=get_db()
    conn.execute("INSERT INTO bodies (id,name,age,gender,cause,storage_id,hospital,status,kin_name,kin_phone,kin_rel,kin_id,created_at,death_cert,police_case,embalming,refrigeration,notes,total_fee,paid_amount,balance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(tag,request.form.get('name'),request.form.get('age'),request.form.get('gender'),request.form.get('cause'),storage,'Korle Bu','Deposited',request.form.get('kin_name'),request.form.get('kin_phone'),request.form.get('kin_rel'),request.form.get('kin_id'),datetime.now().strftime('%Y-%m-%d %H:%M'),request.form.get('death_cert'),'Yes' if request.form.get('police_case') else 'No','Yes' if request.form.get('embalming') else 'No','Yes' if request.form.get('refrigeration') else 'No',request.form.get('notes'),ADMISSION+DAILY,0,ADMISSION+DAILY))
    conn.commit()
    conn.close()
    log_audit(session['user'],"DEPOSIT",tag,request.form.get('name'))
    return redirect('/body/'+tag)

@app.route('/body/<bid>')
def body_detail(bid):
    if 'user' not in session:
        return redirect('/login')
    c=get_db()
    b=c.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    pays=c.execute("SELECT * FROM payments WHERE tag_id=? ORDER BY id DESC",(bid,)).fetchall()
    c.close()
    if not b:
        return page("Not Found","<div class='card'>Not Found</div>"),404
    days, fee = calc_fee(b['created_at'])
    c2=get_db()
    if fee!=(b['total_fee'] or 0):
        c2.execute("UPDATE bodies SET total_fee=?, balance=? WHERE id=?",(fee, fee-(b['paid_amount'] or 0), bid))
        c2.commit()
        b=c2.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    c2.close()
    paid=b['paid_amount'] or 0
    bal=b['balance'] or 0
    pay_rows=""
    for p in pays:
        pay_rows+="<tr><td>"+p['time']+"</td><td>GHS "+str(p['amount'])+"</td><td>"+p['user']+"</td></tr>"
    if not pay_rows:
        pay_rows="<tr><td colspan=3>No payments yet</td></tr>"
    if b['status']=='Released':
        release_section = '<div class="card" style="background:#f0fdf4;border:1px solid #bbf7d0"><h3 style="color:#166534">Released</h3><p>To: <b>'+(b['released_to'] or '')+'</b><br>Doc: '+(b['released_doc'] or '')+'<br>Date: '+(b['released_at'] or '')+'</p><a href="/receipt/'+bid+'" target="_blank"><button>Receipt</button></a></div>'
    else:
        release_section = '<div class="card" style="border:2px solid #fecaca"><h4>Release Body</h4><form method="POST" action="/release/'+bid+'"><input name="collector_name" placeholder="Collector Full Name *" required><input name="doc_number" placeholder="Collector Ghana Card *" required><input name="confirm" placeholder="Type '+bid+' to confirm *" required><button style="background:#dc2626;color:#fff;width:100%;margin-top:6px">RELEASE NOW</button></form></div>'
    return page("Body", '<div class="card"><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><div><h3>'+(b['name'] or '')+' <small>'+b['id']+'</small></h3><p><b>Storage:</b> '+(b['storage_id'] or '')+' <a href="/move/'+bid+'">[Move]</a><br><b>Status:</b> <span class="badge '+(b['status'] or '').lower()+'">'+(b['status'] or '')+'</span><br><b>Age/Gender:</b> '+(b['age'] or '')+'/'+(b['gender'] or '')+'<br><b>Cause:</b> '+(b['cause'] or '')+'<br><b>Death Cert:</b> '+(b['death_cert'] or '')+'<br><b>Police:</b> '+(b['police_case'] or '')+' | <b>Embalm:</b> '+(b['embalming'] or '')+'<br><b>Kin:</b> '+(b['kin_name'] or '')+' ('+(b['kin_rel'] or '')+') - '+(b['kin_phone'] or '')+'<br><b>Admitted:</b> '+(b['created_at'] or '')+' - <b>'+str(days)+' days</b><br><b>Fee:</b> GHS '+str(fee)+' Paid '+str(paid)+' Bal '+str(bal)+'</p><a href="/edit/'+bid+'"><button>Edit Info</button></a></div><div style="text-align:center"><img src="https://api.qrserver.com/v1/create-qr-code/?size=220x220&data='+bid+'" style="border:8px solid #fff"><br><br><a href="/print/tag/'+bid+'" target="_blank"><button>Print QR Tag</button></a> <a href="/receipt/'+bid+'" target="_blank"><button>Receipt</button></a></div></div></div><div class="card"><h4>Payments</h4><form method="POST" action="/pay/'+bid+'" style="display:flex;gap:8px"><input name="amount" type="number" step="0.01" placeholder="Amount GHS" required><button class="btn" style="background:#16a34a">Pay</button></form><table style="margin-top:10px"><tr><th>Date</th><th>Amount</th><th>By</th></tr>'+pay_rows+'</table></div>'+release_section)

@app.route('/edit/<bid>', methods=['GET','POST'])
def edit_body(bid):
    if 'user' not in session:
        return redirect('/login')
    c=get_db()
    b=c.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    if not b:
        c.close()
        return "Not Found",404
    if request.method=='POST':
        c.execute("UPDATE bodies SET name=?, age=?, gender=?, cause=?, kin_name=?, kin_phone=?, kin_rel=?, kin_id=?, death_cert=?, notes=? WHERE id=?",(request.form.get('name'),request.form.get('age'),request.form.get('gender'),request.form.get('cause'),request.form.get('kin_name'),request.form.get('kin_phone'),request.form.get('kin_rel'),request.form.get('kin_id'),request.form.get('death_cert'),request.form.get('notes'),bid))
        c.commit()
        log_audit(session['user'],"EDIT",bid,"Edited")
        c.close()
        return redirect('/body/'+bid)
    c.close()
    notes = b['notes'] or ''
    return page("Edit", '<div class="card"><h3>Edit '+bid+'</h3><form method="POST"><input name="name" value="'+(b['name'] or '')+'" required><input name="age" value="'+(b['age'] or '')+'"><input name="gender" value="'+(b['gender'] or '')+'"><input name="cause" value="'+(b['cause'] or '')+'"><input name="death_cert" value="'+(b['death_cert'] or '')+'"><input name="kin_name" value="'+(b
