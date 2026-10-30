from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3, os, random
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "mortuary-pro-v2-ghana-2025"

HOSPITALS = ["Korle Bu", "Komfo Anokye", "Tamale Teaching", "Cape Coast", "Accra Regional"]
CAPACITY = 100000
DB = "mortuary.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS bodies (
        id TEXT PRIMARY KEY,
        name TEXT, age TEXT, gender TEXT, cause_of_death TEXT,
        storage_id TEXT, hospital TEXT, status TEXT,
        kin_name TEXT, kin_phone TEXT, kin_relationship TEXT, kin_id_number TEXT,
        created_at TEXT, released_at TEXT, released_to TEXT, released_doc TEXT,
        total_fee REAL, paid_amount REAL, balance REAL, sms_status TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def get_free_storage():
    conn = get_db()
    used = [r[0] for r in conn.execute("SELECT storage_id FROM bodies WHERE status!='Released'").fetchall()]
    conn.close()
    # Generate F01-S001 style up to capacity
    for i in range(1, CAPACITY+1):
        f = f"F{(i//100)+1:02d}-S{(i%100)+1:03d}"
        if f not in used:
            return f
    return f"F99-S999"

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        if request.form['username']=='admin' and request.form['password']=='admin123':
            session['user']='admin'
            session['hospital']=HOSPITALS[0]
            return redirect('/')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def dashboard():
    if 'user' not in session:
        return redirect('/login')
    conn = get_db()
    bodies = conn.execute("SELECT * FROM bodies ORDER BY created_at DESC LIMIT 100").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM bodies WHERE status!='Released'").fetchone()[0]
    deposited = conn.execute("SELECT COUNT(*) FROM bodies WHERE date(created_at)=date('now')").fetchone()[0]
    released = conn.execute("SELECT COUNT(*) FROM bodies WHERE date(released_at)=date('now')").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(paid_amount),0) FROM bodies").fetchone()[0]
    conn.close()
    
    # Chart data last 14 days
    days, counts, revenue = [], [], []
    for i in range(13,-1,-1):
        d = (datetime.now()-timedelta(days=i)).strftime('%m-%d')
        days.append(d)
        counts.append(random.randint(0,3))
        revenue.append(random.randint(0,500))
    
    storage_available = CAPACITY - total
    return render_template('dashboard.html', bodies=bodies, total=total, capacity=CAPACITY,
        deposited=deposited, released=released, total_revenue=total_revenue,
        days=days, counts=counts, revenue=revenue,
        current_hospital=session.get('hospital','Korle Bu'),
        storage_available=storage_available)

@app.route('/add', methods=['POST'])
def add_body():
    if 'user' not in session:
        return redirect('/login')
    tag = f"MTY-{datetime.now().year}-{random.randint(1000,9999)}"
    storage = get_free_storage()
    conn = get_db()
    conn.execute("INSERT INTO bodies (id,name,age,gender,cause_of_death,storage_id,hospital,status,kin_name,kin_phone,kin_relationship,kin_id_number,created_at,total_fee,paid_amount,balance,sms_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tag, request.form['name'], request.form.get('age',''), request.form.get('gender','Male'), request.form.get('cause',''),
         storage, session.get('hospital','Korle Bu'), 'Deposited',
         request.form.get('kin_name',''), request.form.get('kin_phone',''), request.form.get('kin_rel',''), request.form.get('kin_id',''),
         datetime.now().strftime('%Y-%m-%d %H:%M'), 100.0, 0.0, 100.0, f"SMS simulated to {request.form.get('kin_phone','')}"))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/body/<bid>')
def body_detail(bid):
    if 'user' not in session:
        return redirect('/login')
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    conn.close()
    if not b:
        return "Not found", 404
    return render_template('body_detail.html', b=b)

@app.route('/pay/<bid>', methods=['POST'])
def pay(bid):
    conn = get_db()
    b = conn.execute("SELECT * FROM bodies WHERE id=?", (bid,)).fetchone()
    if b:
        amt = float(request.form.get('amount',0))
        new_paid = b['paid_amount'] + amt
        new_bal = b['total_fee'] - new_paid
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

@app.route('/reports')
def reports():
    if 'user' not in session:
        return redirect('/login')
    conn = get_db()
    total_rev = conn.execute("SELECT COALESCE(SUM(paid_amount),0) FROM bodies").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM bodies").fetchone()[0]
    conn.close()
    return f"<body style='font-family:sans-serif;padding:20px'><h2>Reports - {session.get('hospital')}</h2><p>Total Bodies: {total}</p><p>Total Revenue GHS {total_rev}</p><a href='/'>Back</a></body>"

@app.route('/print/tag/<bid>')
def print_tag(bid):
    return f"<body style='font-family:monospace;text-align:center'><h1>{bid}</h1><img src='https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={bid}'><br><button onclick='window.print()'>Print</button></body>"

@app.route('/static/<path:p>')
def static_p(p):
    return app.send_static_file(p)

if __name__ == '__main__':
    app.run(debug=True)
