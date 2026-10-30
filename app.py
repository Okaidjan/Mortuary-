from flask import Flask, render_template, request, redirect, session, Response
import sqlite3, os, random, csv, io
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "mortuary-v6-final-stable-2026"
CAPACITY = 100000
DB = "mortuary.db"
DAILY_FEE = 50
ADMISSION_FEE = 100

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS bodies (
        id TEXT PRIMARY KEY, name TEXT, age TEXT, gender TEXT, cause_of_death TEXT,
        storage_id TEXT, hospital TEXT, status TEXT,
        kin_name TEXT, kin_phone TEXT, kin_relationship TEXT, kin_id_number TEXT,
        created_at TEXT, released_at TEXT, released_to TEXT, released_doc TEXT,
        total_fee REAL, paid_amount REAL, balance REAL, sms_status TEXT
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, hospital TEXT, username TEXT, password TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, user TEXT, action TEXT, tag_id TEXT, details TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT)''')
    cur = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    if not cur:
        conn.execute("INSERT INTO settings (id,hospital,username,password) VALUES (1,'Korle Bu','admin','admin123')")
        conn.execute("INSERT OR IGNORE INTO users (username,password,role) VALUES ('admin','admin123','Admin')")
    conn.commit()
    conn.close()
init_db()

def log_audit(user, action, tag_id, details):
    try:
        conn = get_db()
        conn.execute("INSERT INTO audit (time,user,action,tag_id,details) VALUES (?,?,?,?,?)",
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user, action, tag_id, details))
        conn.commit()
        conn.close()
    except: pass

def get_settings():
    conn = get_db()
    s = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    conn.close()
    return s

def get_free_storage():
    conn = get_db()
    used = [r[0] for r in conn.execute("SELECT storage_id FROM bodies WHERE status!='Released'").fetchall()]
    conn.close()
    for i in range(1, CAPACITY+1):
        f = f"F{(i//100)+1:02d}-S{(i%100)+1:03d}"
        if f not in used: return f
    return "F99-S999"

def calc_fees(created_str):
    try: c = datetime.strptime(created_str, '%Y-%m-%d %H:%M')
    except:
        try: c = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
        except: c = datetime.now()
    d = (datetime.now()-c).days
    if d<1: d=1
    return d, ADMISSION_FEE + (DAILY_FEE*d)

@app.route('/login', methods=['GET','POST'])
def login():
    s = get_settings()
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    if request.method=='POST':
        u = request.form['username']
        p = request.form['password']
        conn = get_db()
        found = conn.execute("SELECT * FROM users WHERE username=? AND password=?",(u,p)).fetchone()
        set_user = conn.execute("SELECT * FROM settings WHERE username=? AND password=?",(u,p)).fetchone()
        conn.close()
        if found or set_user:
            session['user']=u
            session['hospital']=s['hospital']
            log_audit(u,"LOGIN","","")
            return redirect('/')
        return render_template('login.html', error="Wrong login")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def dashboard():
    if 'user' not in session: return redirect('/login')
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM bodies WHERE status!='Released'").fetchone()[0]
    deposited = conn.execute("SELECT COUNT(*) FROM bodies WHERE date(created_at)=date('now')").fetchone()[0]
    released = conn.execute("SELECT COUNT(*) FROM bodies WHERE date(released_at)=date('now')").fetchone()[0]
    conn.close()
    return render_template('dashboard.html', total=total, capacity=CAPACITY, deposited=deposited, released=released)

@app.route('/records')
def records():
    if 'user' not in session: return redirect('/login')
    q = request.args.get('q','').strip()
    conn = get_db()
    if q:
        bodies = conn.execute("SELECT * FROM bodies WHERE id LIKE ? OR name LIKE ? ORDER BY created_at DESC",(f'%{q}%',f'%{q}%')).fetchall()
    else:
        bodies = conn.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 200").fetchall()
    for b in bodies:
        if b['status']!='Released':
            d,total_fee = calc_fees(b['created_at'])
            bal = total_fee - (b['paid_amount'] or 0)
            conn.execute("UPDATE bodies SET total_fee=?, balance=? WHERE id=?",(total_fee,bal,b['id']))
    conn.commit()
    bodies = conn.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 200").fetchall() if not q else conn.execute("SELECT * FROM bodies WHERE id LIKE ? OR name LIKE ? ORDER BY created_at DESC",(f'%{q}%',f'%{q}%')).fetchall()
    conn.close()
    return render_template('records.html', bodies=bodies, q=q, DAILY_FEE=DAILY_FEE, ADMISSION_FEE=ADMISSION_FEE)

@app.route('/deposit', methods=['GET','POST'])
@app.route('/add', methods=['GET','POST'])
def add_body():
    if 'user' not in session: return redirect('/login')
    if request.method=='GET':
        return render_template('deposit.html')
    tag = f"MTY-{datetime.now().year}-{random.randint(1000,9999)}"
    storage = get_free_storage()
    conn = get_db()
    conn.execute("INSERT INTO bodies (id,name,age,gender,cause_of_death,storage_id,hospital,status,kin_name,kin_phone,kin_relationship,kin_id_number,created_at,total_fee,paid_amount,balance,sms_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (tag, request.form.get('name'), request.form.get('age'), request.form.get('gender','Male'), request.form.get('cause'), storage, session.get('hospital','Korle Bu'),'Deposited', request.form.get('kin_name'), request.form.get('kin_phone'), request.form.get('kin_rel'), request.form.get('kin_id'), datetime.now().strftime('%Y-%m-%d %H:%M'), ADMISSION_FEE+DAILY_FEE,0,ADMISSION_FEE+DAILY_FEE,'SIM'))
    conn.commit()
    conn.close()
    log_audit(session['user'],"DEPOSIT",tag,request.form.get('name'))
    return redirect('/records')

@app.route('/body/<bid>')
def body_detail(bid):
    if 'user' not in session: return redirect('/login')
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    if b and b['status']!='Released':
        d,total_fee = calc_fees(b['created_at'])
        bal = total_fee - (b['paid_amount'] or 0)
        conn.execute("UPDATE bodies SET total_fee=?, balance=? WHERE id=?",(total_fee,bal,bid))
        conn.commit()
        b = conn.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    conn.close()
    if not b: return "Not Found",404
    days,_ = calc_fees(b['created_at'])
    return render_template('body_detail.html', b=b, days_stored=days, DAILY_FEE=DAILY_FEE, ADMISSION_FEE=ADMISSION_FEE)

@app.route('/pay/<bid>', methods=['POST'])
def pay(bid):
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    if b:
        amt = float(request.form.get('amount',0))
        new_paid = (b['paid_amount'] or 0)+amt
        new_bal = (b['total_fee'] or 0)-new_paid
        conn.execute("UPDATE bodies SET paid_amount=?, balance=? WHERE id=?",(new_paid,new_bal,bid))
        conn.commit()
    conn.close()
    log_audit(session['user'],"PAYMENT",bid,f"GHS {request.form.get('amount')}")
    return redirect(f'/body/{bid}')

@app.route('/release/<bid>', methods=['POST'])
def release(bid):
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    if b and request.form.get('serial_confirm','').strip()==bid:
        conn.execute("UPDATE bodies SET status='Released', released_at=?, released_to=?, released_doc=? WHERE id=?",(datetime.now().strftime('%Y-%m-%d %H:%M'), request.form.get('collector_name'), request.form.get('doc_number'), bid))
        conn.commit()
        log_audit(session['user'],"RELEASE",bid,f"To {request.form.get('collector_name')}")
    conn.close()
    return redirect(f'/body/{bid}')

@app.route('/audit')
def audit_page():
    if 'user' not in session: return redirect('/login')
    conn = get_db()
    audits = conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200").fetchall()
    conn.close()
    return render_template('audit.html', audits=audits)

@app.route('/users', methods=['GET','POST'])
def users_page():
    if 'user' not in session: return redirect('/login')
    conn = get_db()
    if request.method=='POST':
        try:
            conn.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",(request.form.get('username'),request.form.get('password'),request.form.get('role','Staff')))
            conn.commit()
            log_audit(session['user'],"USER_ADD","",request.form.get('username'))
        except: pass
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return render_template('users.html', users=users)

@app.route('/settings', methods=['GET','POST'])
def settings():
    if 'user' not in session: return redirect('/login')
    conn = get_db()
    cur = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    if request.method=='POST':
        new_hosp = request.form.get('hospital','Korle Bu')
        new_user = request.form.get('username','admin')
        new_pass = request.form.get('password') or cur['password']
        conn.execute("UPDATE settings SET hospital=?, username=?, password=? WHERE id=1",(new_hosp,new_user,new_pass))
        conn.commit()
        session['hospital']=new_hosp
        session['user']=new_user
    conn.close()
    return render_template('settings.html', s=cur)

@app.route('/export/csv')
@app.route('/export/excel')
def export_excel():
    if 'user' not in session: return redirect('/login')
    conn = get_db()
    rows = conn.execute("SELECT * FROM bodies ORDER BY created_at DESC").fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Tag','Name','Age','Gender','Storage','Hospital','Status','Kin Name','Kin Phone','Created','Days','Total','Paid','Balance','Released To'])
    for r in rows:
        days,_ = calc_fees(r['created_at'])
        cw.writerow([r['id'],r['name'],r['age'],r['gender'],r['storage_id'],r['hospital'],r['status'],r['kin_name'],r['kin_phone'],r['created_at'],days,r['total_fee'],r['paid_amount'],r['balance'],r['released_to']])
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=mortuary_export.csv"})

@app.route('/receipt/<bid>')
def receipt(bid):
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    conn.close()
    return render_template('receipt.html', b=b) if b else ("Not Found",404)

@app.route('/print/tag/<bid>')
def print_tag(bid):
    return f"<body style='font-family:monospace;text-align:center'><h1>{bid}</h1><img src='https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={bid}'><br><button onclick='window.print()'>Print</button></body>"

if __name__=='__main__':
    app.run(debug=True)
