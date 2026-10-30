from flask import Flask, render_template, request, redirect, session, Response
import sqlite3, os, random, csv, io
from datetime import datetime, timedelta
import requests

app = Flask(__name__)
app.secret_key = "mortuary-pro-v4-final-2026"
CAPACITY = 100000
DB = "mortuary.db"
DAILY_FEE = 50
ADMISSION_FEE = 100
HOSPITALS = ["Korle Bu", "Komfo Anokye", "Tamale Teaching", "Cape Coast", "Accra Regional"]

def send_real_sms(phone, message):
    cid = os.environ.get("HUBTEL_CLIENT_ID")
    sec = os.environ.get("HUBTEL_CLIENT_SECRET")
    sender = os.environ.get("HUBTEL_SENDER", "Mortuary")
    if not cid or not sec or not phone:
        return f"SIMULATED (Add Hubtel keys in Render) → {phone}"
    try:
        if phone.startswith("0"):
            phone = "+233" + phone[1:]
        elif not phone.startswith("+"):
            phone = "+233" + phone
        url = f"https://smsc.hubtel.com/v1/messages/send?clientsecret={sec}&clientid={cid}&from={sender}&to={phone}&content={message}"
        r = requests.get(url, timeout=10)
        return f"REAL SMS to {phone} → {r.status_code}"
    except Exception as e:
        return f"SMS Failed: {e}"

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
    conn.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY, hospital TEXT, username TEXT, password TEXT
    )''')
    cur = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    if not cur:
        conn.execute("INSERT INTO settings (id,hospital,username,password) VALUES (1,?,?,?)",
                     ("Korle Bu", "admin", "admin123"))
    conn.commit()
    conn.close()
init_db()

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
        if f not in used:
            return f
    return "F99-S999"

def calc_fees(created_str):
    try:
        created = datetime.strptime(created_str, '%Y-%m-%d %H:%M')
    except:
        try:
            created = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
        except:
            created = datetime.now()
    days = (datetime.now() - created).days
    if days < 1:
        days = 1
    total = ADMISSION_FEE + (DAILY_FEE * days)
    return days, total

@app.route('/login', methods=['GET','POST'])
def login():
    s = get_settings()
    if request.method == 'POST':
        if request.form['username']==s['username'] and request.form['password']==s['password']:
            session['user']=s['username']
            session['hospital']=s['hospital']
            return redirect('/')
        else:
            return render_template('login.html', error="Wrong username or password")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/settings', methods=['GET','POST'])
def settings():
    if 'user' not in session:
        return redirect('/login')
    conn = get_db()
    cur = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    if request.method == 'POST':
        new_hosp = request.form.get('hospital','Korle Bu')
        new_user = request.form.get('username','admin')
        new_pass = request.form.get('password','')
        if not new_pass:
            new_pass = cur['password']
        conn.execute("UPDATE settings SET hospital=?, username=?, password=? WHERE id=1",
                     (new_hosp, new_user, new_pass))
        conn.commit()
        session['hospital']=new_hosp
        session['user']=new_user
        conn.close()
        return redirect('/')
    conn.close()
    return render_template('settings.html', s=cur, hospitals=HOSPITALS)

@app.route('/')
def dashboard():
    if 'user' not in session:
        return redirect('/login')
    q = request.args.get('q','').strip()
    conn = get_db()
    if q:
        bodies = conn.execute("SELECT * FROM bodies WHERE id LIKE ? OR name LIKE ? OR kin_phone LIKE ? ORDER BY created_at DESC LIMIT 200",
                              (f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
    else:
        bodies = conn.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 200").fetchall()
    for b in bodies:
        if b['status'] != 'Released':
            days, total = calc_fees(b['created_at'])
            bal = total - (b['paid_amount'] or 0)
            conn.execute("UPDATE bodies SET total_fee=?, balance=? WHERE id=?", (total, bal, b['id']))
    conn.commit()
    if q:
        bodies = conn.execute("SELECT * FROM bodies WHERE id LIKE ? OR name LIKE ? OR kin_phone LIKE ? ORDER BY created_at DESC LIMIT 200",
                              (f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
    else:
        bodies = conn.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 200").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM bodies WHERE status!='Released'").fetchone()[0]
    deposited = conn.execute("SELECT COUNT(*) FROM bodies WHERE date(created_at)=date('now')").fetchone()[0]
    released = conn.execute("SELECT COUNT(*) FROM bodies WHERE date(released_at)=date('now')").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(paid_amount),0) FROM bodies").fetchone()[0]
    conn.close()
    storage_available = CAPACITY - total
    return render_template('dashboard.html', bodies=bodies, total=total, capacity=CAPACITY,
        deposited=deposited, released=released, total_revenue=total_revenue,
        current_hospital=session.get('hospital','Korle Bu'), storage_available=storage_available, q=q,
        DAILY_FEE=DAILY_FEE, ADMISSION_FEE=ADMISSION_FEE)

@app.route('/add', methods=['POST'])
def add_body():
    if 'user' not in session:
        return redirect('/login')
    tag = f"MTY-{datetime.now().year}-{random.randint(1000,9999)}"
    storage = get_free_storage()
    kin_phone = request.form.get('kin_phone','')
    msg = f"Body of {request.form.get('name','')} deposited at {session.get('hospital')} Storage {storage} Tag {tag}. Fee GHS {ADMISSION_FEE}+{DAILY_FEE}/day."
    sms_status = send_real_sms(kin_phone, msg)
    conn = get_db()
    conn.execute("INSERT INTO bodies (id,name,age,gender,cause_of_death,storage_id,hospital,status,kin_name,kin_phone,kin_relationship,kin_id_number,created_at,total_fee,paid_amount,balance,sms_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tag, request.form['name'], request.form.get('age',''), request.form.get('gender','Male'), request.form.get('cause',''),
         storage, session.get('hospital','Korle Bu'), 'Deposited',
         request.form.get('kin_name',''), kin_phone, request.form.get('kin_rel',''), request.form.get('kin_id',''),
         datetime.now().strftime('%Y-%m-%d %H:%M'), ADMISSION_FEE+DAILY_FEE, 0.0, ADMISSION_FEE+DAILY_FEE, sms_status))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/body/<bid>')
def body_detail(bid):
    if 'user' not in session:
        return redirect('/login')
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    if b and b['status']!='Released':
        days, total = calc_fees(b['created_at'])
        bal = total - (b['paid_amount'] or 0)
        conn.execute("UPDATE bodies SET total_fee=?, balance=? WHERE id=?", (total, bal, bid))
        conn.commit()
        b = conn.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    conn.close()
    if not b:
        return "Not found", 404
    days, _ = calc_fees(b['created_at'])
    return render_template('body_detail.html', b=b, days_stored=days, DAILY_FEE=DAILY_FEE, ADMISSION_FEE=ADMISSION_FEE)

@app.route('/pay/<bid>', methods=['POST'])
def pay(bid):
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    if b:
        amt = float(request.form.get('amount',0))
        new_paid = (b['paid_amount'] or 0) + amt
        new_bal = (b['total_fee'] or 0) - new_paid
        conn.execute("UPDATE bodies SET paid_amount=?, balance=? WHERE id=?", (new_paid, new_bal, bid))
        conn.commit()
    conn.close()
    return redirect(f'/body/{bid}')

@app.route('/release/<bid>', methods=['POST'])
def release(bid):
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    if b and request.form.get('serial_confirm')==bid:
        conn.execute("UPDATE bodies SET status='Released', released_at=?, released_to=?, released_doc=? WHERE id=?",
            (datetime.now().strftime('%Y-%m-%d %H:%M'), request.form.get('collector_name',''), request.form.get('doc_number',''), bid))
        conn.commit()
    conn.close()
    return redirect(f'/body/{bid}')

@app.route('/receipt/<bid>')
def receipt(bid):
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    conn.close()
    return render_template('receipt.html', b=b)

@app.route('/export/excel')
def export_excel():
    if 'user' not in session:
        return redirect('/login')
    conn = get_db()
    rows = conn.execute("SELECT * FROM bodies ORDER BY created_at DESC").fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Tag','Name','Age','Gender','Storage','Hospital','Status','Kin Name','Kin Phone','Created','Days','Total Fee GHS','Paid','Balance'])
    for r in rows:
        days, _ = calc_fees(r['created_at'])
        cw.writerow([r['id'], r['name'], r['age'], r['gender'], r['storage_id'], r['hospital'], r['status'], r['kin_name'], r['kin_phone'], r['created_at'], days, r['total_fee'], r['paid_amount'], r['balance']])
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=mortuary_export.csv"})

@app.route('/print/tag/<bid>')
def print_tag(bid):
    return f"<body style='font-family:monospace;text-align:center'><h1>{bid}</h1><img src='https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={bid}'><br><button onclick='window.print()'>Print Tag</button></body>"

if __name__ == '__main__':
    app.run(debug=True)
