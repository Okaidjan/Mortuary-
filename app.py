import sqlite3, os, random, csv, io
from flask import Flask, request, redirect, session, Response
from datetime import datetime

app = Flask(__name__)
app.secret_key = "mortuary-secure-v4"
DB = "mortuary.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS bodies (id TEXT PRIMARY KEY, name TEXT, age TEXT, gender TEXT, cause TEXT, storage_id TEXT, status TEXT, kin_name TEXT, kin_phone TEXT, kin_rel TEXT, kin_id TEXT, created_at TEXT, released_at TEXT, released_to TEXT, released_doc TEXT, death_cert TEXT, police_case TEXT, notes TEXT, total_fee REAL, paid_amount REAL, balance REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, tag_id TEXT, amount REAL, time TEXT, user TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, user TEXT, action TEXT, tag_id TEXT, details TEXT)")
    cur = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    if not cur:
        conn.execute("INSERT INTO users VALUES ('admin','admin123','Admin')")
    conn.commit()
    conn.close()

init_db()

def free_storage():
    c = get_db()
    used = [r[0] for r in c.execute("SELECT storage_id FROM bodies WHERE status!='Released'").fetchall()]
    c.close()
    for i in range(1, 100000):
        f = "F" + str((i//100)+1).zfill(2) + "-S" + str((i%100)+1).zfill(3)
        if f not in used:
            return f
    return "F99-S999"

def base_page(body):
    u = session.get('user','')
    return "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{margin:0;font-family:sans-serif;background:#f4f6f9}.nav{background:#0f172a;color:#fff;padding:10px;display:flex;gap:8px;flex-wrap:wrap;font-size:13px}.nav a{color:#94a3b8;text-decoration:none;padding:5px}.card{background:#fff;margin:12px;padding:16px;border-radius:10px}input,select,textarea{width:100%;padding:10px;margin:6px 0;border:1px solid #cbd5e1;border-radius:8px;box-sizing:border-box}button{padding:10px 14px;border:none;border-radius:8px;font-weight:700}.btn{background:#0ea5e9;color:#fff}table{width:100%;font-size:13px;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #eee}</style></head><body><div class='nav'><b>MORTUARY</b> <a href='/'>Dashboard</a> <a href='/records'>Records</a> <a href='/deposit'>+Deposit</a> <a href='/audit'>Audit</a> <a href='/users'>Users</a> <a href='/export/csv'>Export</a> <a href='/logout' style='margin-left:auto'>Logout " + u + "</a></div>" + body + "</body></html>"

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        c = get_db()
        u = c.execute("SELECT * FROM users WHERE username=? AND password=?", (request.form['username'], request.form['password'])).fetchone()
        c.close()
        if u:
            session['user'] = u['username']
            return redirect('/')
        return base_page("<div class='card' style='max-width:360px;margin:80px auto;text-align:center'><h3 style='color:red'>Invalid login</h3><a href='/login'>Try again</a></div>")
    return base_page("<div class='card' style='max-width:360px;margin:80px auto'><h2 style='text-align:center'>Mortuary Login</h2><form method='POST'><input name='username' placeholder='Username' required><input name='password' type='password' placeholder='Password' required><button class='btn' style='width:100%'>Login</button></form></div>")

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def dash():
    if 'user' not in session:
        return redirect('/login')
    c = get_db()
    total = c.execute("SELECT COUNT(*) FROM bodies WHERE status!='Released'").fetchone()[0]
    revenue = c.execute("SELECT COALESCE(SUM(paid_amount),0) FROM bodies").fetchone()[0]
    c.close()
    return base_page("<div class='card'><h3>Dashboard</h3><p><b>" + str(total) + " / 100000</b> in storage</p><p>Revenue: GHS " + str(revenue) + "</p><p style='color:green'>System Live - Secure Login (no credentials shown)</p><a href='/deposit'><button class='btn'>+ Deposit</button></a> <a href='/records'><button>Records</button></a></div>")

@app.route('/records')
def records():
    if 'user' not in session:
        return redirect('/login')
    q = request.args.get('q','')
    c = get_db()
    if q:
        bodies = c.execute("SELECT * FROM bodies WHERE id LIKE ? OR name LIKE ? ORDER BY created_at DESC", ('%'+q+'%','%'+q+'%')).fetchall()
    else:
        bodies = c.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 200").fetchall()
    c.close()
    rows = ""
    for b in bodies:
        rows += "<tr><td><a href='/body/" + b['id'] + "'>" + b['id'] + "</a></td><td>" + (b['name'] or '') + "</td><td>" + (b['storage_id'] or '') + "</td><td>" + (b['status'] or '') + "</td></tr>"
    return base_page("<div class='card'><form method='GET'><input name='q' value='" + q + "' placeholder='Search Tag or Name'><button class='btn'>Search</button></form></div><div class='card'><table><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th></tr>" + rows + "</table></div>")

@app.route('/deposit')
def deposit():
    if 'user' not in session:
        return redirect('/login')
    return base_page("<div class='card'><h3>Deposit Body</h3><form method='POST' action='/add'><input name='name' placeholder='Deceased Name *' required><input name='age' placeholder='Age'><select name='gender'><option>Male</option><option>Female</option></select><input name='cause' placeholder='Cause of Death'><input name='death_cert' placeholder='Death Certificate No'><label><input type='checkbox' name='police_case' style='width:auto'> Police Case</label><textarea name='notes' placeholder='Notes'></textarea><hr><input name='kin_name' placeholder='Kin Name'><input name='kin_phone' placeholder='Kin Phone'><input name='kin_rel' placeholder='Relationship'><input name='kin_id' placeholder='Ghana Card ID'><button class='btn' style='width:100%'>Deposit + QR</button></form></div>")

@app.route('/add', methods=['POST'])
def add_body():
    if 'user' not in session:
        return redirect('/login')
    tag = "MTY-" + str(datetime.now().year) + "-" + str(random.randint(1000,9999))
    storage = free_storage()
    conn = get_db()
    conn.execute("INSERT INTO bodies (id,name,age,gender,cause,storage_id,status,kin_name,kin_phone,kin_rel,kin_id,created_at,death_cert,police_case,notes,total_fee,paid_amount,balance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (tag, request.form.get('name'), request.form.get('age'), request.form.get('gender'), request.form.get('cause'), storage, 'Deposited', request.form.get('kin_name'), request.form.get('kin_phone'), request.form.get('kin_rel'), request.form.get('kin_id'), datetime.now().strftime('%Y-%m-%d %H:%M'), request.form.get('death_cert'), 'Yes' if request.form.get('police_case') else 'No', request.form.get('notes'), 150, 0, 150))
    conn.commit()
    conn.close()
    return redirect('/body/' + tag)

@app.route('/body/<bid>')
def body_detail(bid):
    if 'user' not in session:
        return redirect('/login')
    c = get_db()
    b = c.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    pays = c.execute("SELECT * FROM payments WHERE tag_id=? ORDER BY id DESC", (bid,)).fetchall()
    c.close()
    if not b:
        return base_page("<div class='card'>Not Found</div>"), 404
    pay_rows = ""
    for p in pays:
        pay_rows += "<tr><td>" + p['time'] + "</td><td>GHS " + str(p['amount']) + "</td><td>" + p['user'] + "</td></tr>"
    if pay_rows == "":
        pay_rows = "<tr><td colspan=3>No payments</td></tr>"
    if b['status'] == 'Released':
        release_html = "<div class='card' style='background:#f0fdf4'><h3 style='color:green'>Released</h3><p>To: " + (b['released_to'] or '') + "<br>Doc: " + (b['released_doc'] or '') + "<br>Date: " + (b['released_at'] or '') + "</p></div>"
    else:
        release_html = "<div class='card' style='border:2px solid #fecaca'><h4>Release Body</h4><form method='POST' action='/release/" + bid + "'><input name='collector_name' placeholder='Collector Name *' required><input name='doc_number' placeholder='Ghana Card *' required><input name='confirm' placeholder='Type " + bid + " to confirm *' required><button style='background:#dc2626;color:#fff;width:100%'>RELEASE NOW</button></form></div>"
    return base_page("<div class='card'><h3>" + (b['name'] or '') + " - " + b['id'] + "</h3><p>Storage: " + (b['storage_id'] or '') + " | Status: " + (b['status'] or '') + "<br>Cause: " + (b['cause'] or '') + " | Death Cert: " + (b['death_cert'] or '') + "<br>Kin: " + (b['kin_name'] or '') + " - " + (b['kin_phone'] or '') + "<br>Fee: GHS " + str(b['total_fee']) + " Paid " + str(b['paid_amount']) + " Bal " + str(b['balance']) + "</p><div style='text-align:center'><img src='https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=" + bid + "'><br><br><a href='/print/tag/" + bid + "' target='_blank'><button>Print QR Tag</button></a> <a href='/receipt/" + bid + "' target='_blank'><button>Receipt</button></a> <a href='/edit/" + bid + "'><button>Edit</button></a></div></div><div class='card'><h4>Payments</h4><form method='POST' action='/pay/" + bid + "' style='display:flex;gap:8px'><input name='amount' type='number' placeholder='Amount' required><button class='btn' style='background:#16a34a'>Pay</button></form><table><tr><th>Date</th><th>Amount</th><th>By</th></tr>" + pay_rows + "</table></div>" + release_html)

@app.route('/edit/<bid>', methods=['GET','POST'])
def edit_body(bid):
    if 'user' not in session:
        return redirect('/login')
    c = get_db()
    b = c.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    if not b:
        c.close()
        return "Not Found", 404
    if request.method == 'POST':
        c.execute("UPDATE bodies SET name=?, age=?, gender=?, cause=?, kin_name=?, kin_phone=?, death_cert=?, notes=? WHERE id=?", (request.form.get('name'), request.form.get('age'), request.form.get('gender'), request.form.get('cause'), request.form.get('kin_name'), request.form.get('kin_phone'), request.form.get('death_cert'), request.form.get('notes'), bid))
        c.commit()
        c.close()
        return redirect('/body/' + bid)
    c.close()
    return base_page("<div class='card'><h3>Edit " + bid + "</h3><form method='POST'><input name='name' value='" + (b['name'] or '') + "' required><input name='age' value='" + (b['age'] or '') + "'><input name='gender' value='" + (b['gender'] or '') + "'><input name='cause' value='" + (b['cause'] or '') + "'><input name='death_cert' value='" + (b['death_cert'] or '') + "'><input name='kin_name' value='" + (b['kin_name'] or '') + "'><input name='kin_phone' value='" + (b['kin_phone'] or '') + "'><textarea name='notes'>" + (b['notes'] or '') + "</textarea><button class='btn' style='width:100%'>Save</button></form></div>")

@app.route('/pay/<bid>', methods=['POST'])
def pay(bid):
    if 'user' not in session:
        return redirect('/login')
    c = get_db()
    b = c.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    if b:
        amt = float(request.form.get('amount',0) or 0)
        new_paid = (b['paid_amount'] or 0) + amt
        new_bal = (b['total_fee'] or 0) - new_paid
        c.execute("UPDATE bodies SET paid_amount=?, balance=? WHERE id=?", (new_paid, new_bal, bid))
        c.execute("INSERT INTO payments (tag_id,amount,time,user) VALUES (?,?,?,?)", (bid, amt, datetime.now().strftime('%Y-%m-%d %H:%M'), session['user']))
        c.commit()
    c.close()
    return redirect('/body/' + bid)

@app.route('/release/<bid>', methods=['POST'])
def release(bid):
    if 'user' not in session:
        return redirect('/login')
    if request.form.get('confirm','').strip() != bid:
        return base_page("<div class='card'><p>Confirm failed. Type " + bid + "</p><a href='/body/" + bid + "'>Back</a></div>")
    c = get_db()
    c.execute("UPDATE bodies SET status='Released', released_at=?, released_to=?, released_doc=? WHERE id=?", (datetime.now().strftime('%Y-%m-%d %H:%M'), request.form.get('collector_name'), request.form.get('doc_number'), bid))
    c.commit()
    c.close()
    return redirect('/body/' + bid)

@app.route('/audit')
def audit():
    if 'user' not in session:
        return redirect('/login')
    c = get_db()
    rows = c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200").fetchall()
    c.close()
    html = ""
    for r in rows:
        html += "<tr><td>" + r['time'] + "</td><td>" + r['user'] + "</td><td>" + r['action'] + "</td><td>" + (r['tag_id'] or '') + "</td></tr>"
    return base_page("<div class='card'><h3>Audit</h3><table><tr><th>Time</th><th>User</th><th>Action</th><th>Tag</th></tr>" + html + "</table></div>")

@app.route('/users', methods=['GET','POST'])
def users():
    if 'user' not in session:
        return redirect('/login')
    c = get_db()
    if request.method == 'POST':
        try:
            c.execute("INSERT INTO users VALUES (?,?,?)", (request.form.get('username'), request.form.get('password'), 'Staff'))
            c.commit()
        except:
            pass
    us = c.execute("SELECT * FROM users").fetchall()
    c.close()
    rows = ""
    for u in us:
        rows += "<tr><td>" + u['username'] + "</td><td>" + u['role'] + "</td></tr>"
    return base_page("<div class='card'><h3>Add Staff</h3><form method='POST'><input name='username' placeholder='Username' required><input name='password' placeholder='Password' required><button class='btn'>Add</button></form></div><div class='card'><table><tr><th>User</th><th>Role</th></tr>" + rows + "</table></div>")

@app.route('/export/csv')
def export_csv():
    if 'user' not in session:
        return redirect('/login')
    c = get_db()
    rows = c.execute("SELECT * FROM bodies ORDER BY created_at DESC").fetchall()
    c.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Tag','Name','Storage','Status','Kin','Phone','Fee','Paid','Balance'])
    for r in rows:
        cw.writerow([r['id'],r['name'],r['storage_id'],r['status'],r['kin_name'],r['kin_phone'],r['total_fee'],r['paid_amount'],r['balance']])
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=mortuary.csv"})

@app.route('/receipt/<bid>')
def receipt(bid):
    c = get_db()
    b = c.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetch
