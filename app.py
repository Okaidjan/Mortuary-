import os, csv, io, uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, url_for, flash, render_template_string, make_response, abort, session, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "ghana-mortuary-v4-pro-national-2026")
database_url = os.environ.get("DATABASE_URL", "sqlite:///mortuary.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["WTF_CSRF_TIME_LIMIT"] = None

ADMISSION = 100
DAILY = 50

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

class Hospital(db.Model):
    code = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    region = db.Column(db.String(100))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="admin")
    hospital_code = db.Column(db.String(20), default="KB-001")
    active = db.Column(db.Boolean, default=True)
    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

class Deceased(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tag_number = db.Column(db.String(50), unique=True, nullable=False)
    hospital_code = db.Column(db.String(20), default="KB-001")
    full_name = db.Column(db.String(150), nullable=False)
    age = db.Column(db.String(20))
    gender = db.Column(db.String(20))
    cause = db.Column(db.String(200))
    storage_id = db.Column(db.String(30))
    status = db.Column(db.String(30), default="Deposited")
    kin_name = db.Column(db.String(150))
    kin_phone = db.Column(db.String(50))
    kin_rel = db.Column(db.String(50))
    kin_id = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    released_at = db.Column(db.DateTime)
    released_to = db.Column(db.String(150))
    released_doc = db.Column(db.String(100))
    death_cert = db.Column(db.String(100))
    police_case = db.Column(db.String(10), default="No")
    embalming = db.Column(db.String(10), default="No")
    refrigeration = db.Column(db.String(10), default="Yes")
    total_fee = db.Column(db.Float, default=150)
    paid_amount = db.Column(db.Float, default=0)
    balance = db.Column(db.Float, default=150)
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(80))

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tag_id = db.Column(db.String(50))
    amount = db.Column(db.Float)
    time = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.Column(db.String(80))

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    hospital_code = db.Column(db.String(20))
    action = db.Column(db.String(200))
    tag_id = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facility_name = db.Column(db.String(150), default="Ghana National Mortuary System")

@login_manager.user_loader
def load_user(uid):
    try:
        u = db.session.get(User, int(uid))
        if u and u.active: return u
    except: pass
    return None

def roles_required(*roles):
    def deco(f):
        @wraps(f)
        @login_required
        def w(*a, **kw):
            if current_user.role not in roles: abort(403)
            return f(*a, **kw)
        return w
    return deco

def generate_tag(hcode): return f"{hcode}-{datetime.utcnow().year}-{uuid.uuid4().hex[:4].upper()}"
def free_storage(hcode):
    used = [r.storage_id for r in Deceased.query.filter_by(hospital_code=hcode).filter(Deceased.status!="Released").all() if r.storage_id]
    for i in range(1,100001):
        sid = f"F{(i//100)+1:02d}-S{(i%100)+1:03d}"
        if sid not in used: return sid
    return "F99-S999"

def calc_fee(created):
    if not created: created = datetime.utcnow()
    days = (datetime.utcnow() - created).days
    if days < 1: days = 1
    return days, ADMISSION + DAILY*days

def get_facility_name():
    if current_user.is_authenticated:
        h = db.session.get(Hospital, current_user.hospital_code)
        if h: return h.name
        if current_user.hospital_code=="ALL": return "Ghana National Mortuary System - Super Admin"
    s = db.session.get(Settings,1)
    return s.facility_name if s else "Mortuary System"

def page_template(content, title="MTS"):
    return render_template_string("""
    <!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }}</title>
    <style>body{margin:0;font-family:-apple-system,sans-serif;background:#f4f6f9} .nav{background:#0f172a;color:#fff;padding:10px 12px;display:flex;gap:8px;flex-wrap:wrap;font-size:13px;align-items:center} .nav a{color:#94a3b8;text-decoration:none;padding:5px 9px;border-radius:6px} .nav a.active{background:#1e293b;color:#38bdf8} .card{background:#fff;margin:12px;padding:16px;border-radius:12px;box-shadow:0 1px 2px rgba(0,0,0,.06)} input,select,textarea{width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid #cbd5e1;box-sizing:border-box} button{padding:10px 14px;border:none;border-radius:8px;font-weight:700;cursor:pointer} .btn{background:#0ea5e9;color:#fff} .badge{padding:2px 8px;border-radius:999px;font-size:11px} .deposited{background:#dcfce7;color:#166534} .released{background:#fee2e2;color:#991b1b} .alert{background:#fef3c7;border:1px solid #fcd34d;padding:10px;border-radius:8px;margin:12px} table{width:100%;border-collapse:collapse;background:#fff} th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left} th{background:#e9f1f5} .flash{padding:10px;background:#fff1c9;margin:8px 0;border-radius:5px}</style></head>
    <body><div class="nav"><b style="color:#fff">{{ facility_name }}</b> {% if current_user.is_authenticated %}<a href="{{ url_for('dashboard') }}">Dashboard</a> <a href="{{ url_for('admission') }}">+Deposit</a> <a href="{{ url_for('records') }}">Records</a> <a href="{{ url_for('hospitals') }}">Hospitals</a> <a href="{{ url_for('users') }}">Users</a> <a href="{{ url_for('audit') }}">Audit</a> <form method="POST" action="{{ url_for('logout') }}" style="display:inline;margin-left:auto"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button style="background:#334155;color:#fff">Logout ({{ current_user.username }})</button></form>{% endif %}</div>
    <main>{% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}{{ content|safe }}</main></body></html>
    """, content=content, title=title, facility_name=get_facility_name())

@app.route("/", methods=["GET","POST"])
@app.route("/login", methods=["GET","POST"])
@csrf.exempt
def login():
    if current_user.is_authenticated: return redirect(url_for("dashboard"))
    if request.method=="POST":
        hcode = request.form.get("hospital_code","").strip().upper()
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        user = User.query.filter_by(username=username).first()
        if user and user.active and user.check_password(password):
            if user.hospital_code=="ALL" or user.hospital_code==hcode or (hcode=="ALL" and user.role=="admin"):
                login_user(user); return redirect(url_for("dashboard"))
            else: flash("Hospital mismatch. Your hospital: "+user.hospital_code)
        else: flash("Invalid credentials")
    # NO CREDENTIALS SHOWN - SECURE
    return page_template("""
    <div class="card" style="max-width:380px;margin:60px auto;text-align:center"><h2>Mortuary System</h2><p style="color:#64748b;font-size:13px">Secure Login - One Link Ghana</p>
    <form method="POST" style="text-align:left"><label>Hospital Code *</label><input name="hospital_code" placeholder="e.g. KB-001 or ALL" required style="text-transform:uppercase"><label>Username</label><input name="username" placeholder="Username" required><label>Password</label><input type="password" name="password" placeholder="Password" required><button class="btn" style="width:100%;margin-top:10px">Login</button></form></div>
    """, "Login")

@app.route("/dashboard")
@login_required
def dashboard():
    hcode=current_user.hospital_code
    base_q = Deceased.query if hcode=="ALL" else Deceased.query.filter_by(hospital_code=hcode)
    total = base_q.filter(Deceased.status!="Released").count()
    dep_today = base_q.filter(db.func.date(Deceased.created_at)==datetime.utcnow().date()).count()
    revenue = db.session.query(db.func.coalesce(db.func.sum(Deceased.paid_amount),0)).filter(Deceased.hospital_code==hcode).scalar() if hcode!="ALL" else db.session.query(db.func.coalesce(db.func.sum(Deceased.paid_amount),0)).scalar()
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    unclaimed = base_q.filter(Deceased.status!="Released", Deceased.created_at < thirty_days_ago).count()
    recent = base_q.order_by(Deceased.id.desc()).limit(5).all()
    alert = f'<div class="alert">⚠️ {unclaimed} bodies unclaimed >30 days — action needed!</div>' if unclaimed>0 else ''
    recent_rows="".join([f"<tr><td><a href='/record/{b.id}'><b>{b.tag_number}</b></a></td><td>{b.full_name}</td><td>{b.storage_id}</td><td><span class='badge {b.status.lower()}'>{b.status}</span></td></tr>" for b in recent])
    return page_template(f"""
    {alert}<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:12px"><div class="card"><b style="font-size:22px">{total} / 100000</b><br><small>{'All Ghana' if hcode=='ALL' else hcode} In Storage</small></div><div class="card"><b style="font-size:22px">{dep_today}</b><br><small>Today Deposited</small></div><div class="card"><b style="font-size:22px">GHS {revenue}</b><br><small>Revenue</small></div></div>
    <div class="card"><h3>Recent Deposits - {hcode}</h3><table><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th></tr>{recent_rows}</table></div>
    """, "Dashboard")

@app.route("/admission", methods=["GET","POST"])
@roles_required("admin","supervisor","officer")
def admission():
    if current_user.hospital_code=="ALL": flash("Login with specific hospital like KB-001 to deposit"); return redirect(url_for("dashboard"))
    if request.method=="POST":
        tag=generate_tag(current_user.hospital_code); storage=free_storage(current_user.hospital_code)
        d=Deceased(tag_number=tag, hospital_code=current_user.hospital_code, full_name=request.form.get("name"), age=request.form.get("age"), gender=request.form.get("gender"), cause=request.form.get("cause"), death_cert=request.form.get("death_cert"), police_case="Yes" if request.form.get("police_case") else "No", embalming="Yes" if request.form.get("embalming") else "No", refrigeration="Yes" if request.form.get("refrigeration") else "No", kin_name=request.form.get("kin_name"), kin_phone=request.form.get("kin_phone"), kin_rel=request.form.get("kin_rel"), kin_id=request.form.get("kin_id"), storage_id=storage, notes=request.form.get("notes"), status="Deposited", total_fee=ADMISSION+DAILY, paid_amount=0, balance=ADMISSION+DAILY, created_by=current_user.username)
        db.session.add(d); db.session.commit(); flash(f"Deposited {tag} {storage}"); return redirect(url_for("record_detail", record_id=d.id))
    cnt=Deceased.query.filter_by(hospital_code=current_user.hospital_code, status="Deposited").count()
    return page_template(render_template_string("""
    <div class="card"><h3>Deposit Body - {{ hcode }} ({{ cnt }} / 100000)</h3><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input name="name" placeholder="Deceased Full Name *" required><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><input name="age" placeholder="Age"><select name="gender"><option>Male</option><option>Female</option><option>Other</option></select></div>
    <input name="cause" placeholder="Cause of Death"><input name="death_cert" placeholder="Death Certificate No."><div style="display:flex;gap:12px;font-size:13px"><label><input type="checkbox" name="police_case" style="width:auto"> Police Case</label><label><input type="checkbox" name="embalming" style="width:auto"> Embalming</label><label><input type="checkbox" name="refrigeration" checked style="width:auto"> Refrigeration</label></div><textarea name="notes" placeholder="Notes"></textarea><hr><h4>Next of Kin</h4><input name="kin_name" placeholder="Kin Name"><input name="kin_phone" placeholder="Kin Phone"><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><input name="kin_rel" placeholder="Relationship"><input name="kin_id" placeholder="Ghana Card ID"></div><button class="btn" style="width:100%;margin-top:10px">Deposit + Generate QR</button></form></div>
    """, hcode=current_user.hospital_code, cnt=cnt), "Deposit")

@app.route("/records")
@login_required
def records():
    search=request.args.get("q","").strip(); status=request.args.get("status","")
    hcode=current_user.hospital_code; q=Deceased.query; 
    if hcode!="ALL": q=q.filter_by(hospital_code=hcode)
    if search: q=q.filter(or_(Deceased.full_name.ilike(f"%{search}%"), Deceased.tag_number.ilike(f"%{search}%"), Deceased.kin_phone.ilike(f"%{search}%")))
    if status: q=q.filter_by(status=status)
    items=q.order_by(Deceased.id.desc()).limit(300).all()
    return page_template(render_template_string("""
    <div class="card"><form method="GET" style="display:flex;gap:6px;flex-wrap:wrap"><input name="q" value="{{ search }}" placeholder="Search Tag/Name/Phone" style="flex:1;margin:0"><select name="status" style="width:auto;margin:0"><option value="">All Status</option><option value="Deposited" {% if status=='Deposited' %}selected{% endif %}>Deposited</option><option value="Released" {% if status=='Released' %}selected{% endif %}>Released</option></select><button class="btn">Filter</button></form></div>
    <div class="card"><h3>{{ items|length }} Records - {{ hcode }}</h3><table><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th><th>Balance</th></tr>{% for b in items %}<tr><td><a href="{{ url_for('record_detail', record_id=b.id) }}"><b>{{ b.tag_number }}</b></a></td><td>{{ b.full_name }}<br><small>{{ b.age }}/{{ b.gender }}</small></td><td>{{ b.storage_id }}</td><td><span class="badge {{ b.status.lower() }}">{{ b.status }}</span></td><td>GHS {{ b.balance or 0 }}</td></tr>{% endfor %}</table></div>
    """, items=items, search=search, status=status, hcode=hcode), "Records")

@app.route("/record/<int:record_id>")
@login_required
def record_detail(record_id):
    b=db.get_or_404(Deceased, record_id)
    if current_user.hospital_code!="ALL" and b.hospital_code!=current_user.hospital_code: abort(403)
    days, fee = calc_fee(b.created_at)
    if fee != b.total_fee:
        b.total_fee=fee; b.balance=fee-(b.paid_amount or 0); db.session.commit()
    pays=Payment.query.filter_by(tag_id=b.tag_number).order_by(Payment.id.desc()).all()
    pay_rows="".join([f"<tr><td>{p.time.strftime('%Y-%m-%d %H:%M')}</td><td>GHS {p.amount}</td><td>{p.user}</td></tr>" for p in pays]) or "<tr><td colspan=3>No payments yet</td></tr>"
    if b.status=="Released":
        release_section = f'<div class="card" style="background:#f0fdf4;border:1px solid #bbf7d0"><h3 style="color:#166534">✅ Released</h3><p>To: <b>{b.released_to}</b><br>Doc: {b.released_doc}<br>Date: {b.released_at}</p><a href="/receipt/{b.id}" target="_blank"><button>View Final Receipt</button></a></div>'
    else:
        release_section = f'<div class="card" style="border:2px solid #fecaca"><h4>Release Body</h4><form method="POST" action="/record/{b.id}/release"><input type="hidden" name="csrf_token" value="{csrf_token()}"><input name="collector_name" placeholder="Collector Full Name *" required><input name="doc_number" placeholder="Collector Ghana Card *" required><input name="confirm" placeholder="Type {b.tag_number} to confirm *" required><button style="background:#dc2626;color:#fff;width:100%;margin-top:6px">RELEASE NOW</button></form></div>'
    return page_template(render_template_string(f"""
    <div class="card"><div style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><div><h3>{b.full_name} <small>{b.tag_number}</small></h3><p><b>Storage:</b> {b.storage_id} <a href="/record/{b.id}/move" style="font-size:11px">[Move]</a><br><b>Status:</b> <span class="badge {b.status.lower()}">{b.status}</span><br><b>Age/Gender:</b> {b.age}/{b.gender}<br><b>Cause:</b> {b.cause}<br><b>Death Cert:</b> {b.death_cert}<br><b>Police:</b> {b.police_case} | <b>Embalming:</b> {b.embalming} | <b>Fridge:</b> {b.refrigeration}<br><b>Kin:</b> {b.kin_name} ({b.kin_rel}) — {b.kin_phone} ID:{b.kin_id}<br><b>Admitted:</b> {b.created_at} — <b>{days} days</b><br><b>Notes:</b> {b.notes or "-"}<br><b>Fee:</b> GHS {b.total_fee} (Paid {b.paid_amount or 0} | Bal {b.balance or 0})</p><a href="/record/{b.id}/edit"><button>Edit Info</button></a></div><div style="text-align:center"><img src="https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={b.tag_number}" style="border:8px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.2)"><br><br><a href="/print/tag/{b.id}" target="_blank"><button>Print QR Tag</button></a> <a href="/receipt/{b.id}" target="_blank"><button>Receipt</button></a></div></div></div>
    <div class="card"><h4>Payments</h4><form method="POST" action="/record/{b.id}/pay" style="display:flex;gap:8px"><input type="hidden" name="csrf_token" value="{csrf_token()}"><input name="amount" type="number" step="0.01" placeholder="Amount GHS" required><button class="btn" style="background:#16a34a">Add Payment</button></form><table style="margin-top:10px"><tr><th>Date</th><th>Amount</th><th>By</th></tr>{pay_rows}</table></div>{release_section}
    """), "Body")

@app.route("/record/<int:record_id>/edit", methods=["GET","POST"])
@roles_required("admin","supervisor")
def edit_record(record_id):
    b=db.get_or_404(Deceased, record_id)
    if current_user.hospital_code!="ALL" and b.hospital_code!=current_user.hospital_code: abort(403)
    if request.method=="POST":
        b.full_name=request.form.get("name") or b.full_name; b.age=request.form.get("age"); b.gender=request.form.get("gender"); b.cause=request.form.get("cause"); b.kin_name=request.form.get("kin_name"); b.kin_phone=request.form.get("kin_phone"); b.kin_rel=request.form.get("kin_rel"); b.kin_id=request.form.get("kin_id"); b.death_cert=request.form.get("death_cert"); b.notes=request.form.get("notes"); db.session.commit(); flash("Updated"); return redirect(url_for("record_detail", record_id=b.id))
    return page_template(render_template_string("""
    <div class="card"><h3>Edit {{ b.tag_number }}</h3><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input name="name" value="{{ b.full_name }}" required><input name="age" value="{{ b.age or ''}}"><input name="gender" value="{{ b.gender or ''}}"><input name="cause" value="{{ b.cause or ''}}"><input name="death_cert" value="{{ b.death_cert or ''}}"><input name="kin_name" value="{{ b.kin_name or ''}}"><input name="kin_phone" value="{{ b.kin_phone or ''}}"><input name="kin_rel" value="{{ b.kin_rel or ''}}"><input name="kin_id" value="{{ b.kin_id or ''}}"><textarea name="notes">{{ b.notes or ''}}</textarea><button class="btn" style="width:100%">Save</button></form></div>
    """, b=b), "Edit")

@app.route("/record/<int:record_id>/move", methods=["GET","POST"])
@roles_required("admin","supervisor")
def move_storage(record_id):
    b=db.get_or_404(Deceased, record_id)
    if current_user.hospital_code!="ALL" and b.hospital_code!=current_user.hospital_code: abort(403)
    if request.method=="POST":
        b.storage_id=request.form.get("storage"); db.session.commit(); flash(f"Moved to {b.storage_id}"); return redirect(url_for("record_detail", record_id=b.id))
    return page_template(render_template_string("""
    <div class="card"><h3>Move Storage - {{ b.tag_number }} (Current: {{ b.storage_id }})</h3><p>Suggestion: {{ free_storage(b.hospital_code) }}</p><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input name="storage" required value="{{ free_storage(b.hospital_code) }}"><button class="btn" style="width:100%">Move Now</button></form></div>
    """, b=b), "Move")

@app.route("/record/<int:record_id>/pay", methods=["POST"])
@roles_required("admin","supervisor","officer")
def pay(record_id):
    b=db.get_or_404(Deceased, record_id)
    amt=float(request.form.get("amount",0) or 0); b.paid_amount=(b.paid_amount or 0)+amt; b.balance=(b.total_fee or 0)-b.paid_amount
    p=Payment(tag_id=b.tag_number, amount=amt, user=current_user.username); db.session.add(p); db.session.commit(); return redirect(url_for("record_detail", record_id=b.id))

@app.route("/record/<int:record_id>/release", methods=["POST"])
@roles_required("admin","supervisor","officer")
def release_record(record_id):
    b=db.get_or_404(Deceased, record_id)
    if request.form.get("confirm","").strip()!=b.tag_number: flash(f"Type exactly {b.tag_number} to confirm"); return redirect(url_for("record_detail", record_id=b.id))
    b.status="Released"; b.released_at=datetime.utcnow(); b.released_to=request.form.get("collector_name"); b.released_doc=request.form.get("doc_number"); db.session.commit(); flash("Released"); return redirect(url_for("record_detail", record_id=b.id))

@app.route("/receipt/<int:record_id>")
@login_required
def receipt(record_id):
    b=db.get_or_404(Deceased, record_id); s=get_facility_name()
    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Receipt</title><style>body{{font-family:monospace;padding:20px}} .box{{border:2px dashed #000;padding:16px;max-width:400px;margin:auto}} @media print{{button{{display:none}}}}</style></head><body><div class="box"><h3 style="text-align:center">{s}<br>RECEIPT</h3><hr>Tag: {b.tag_number}<br>Name: {b.full_name}<br>Storage: {b.storage_id}<br>Admitted: {b.created_at}<br>Kin: {b.kin_name} {b.kin_phone}<br><hr>Total: GHS {b.total_fee}<br>Paid: GHS {b.paid_amount}<br>Balance: GHS {b.balance}<br><hr><div style="text-align:center"><img src="https://api.qrserver.com/v1/create-qr-code/?size=140x140&data={b.tag_number}"><br><button onclick="window.print()" style="padding:10px;background:#000;color:#fff;border:none;border-radius:6px;margin-top:10px">Print</button></div></div></body></html>"""

@app.route("/print/tag/<int:record_id>")
@login_required
def print_tag(record_id):
    b=db.get_or_404(Deceased, record_id); return f"""<!DOCTYPE html><html><body style="text-align:center;font-family:monospace;padding:30px"><h1>{b.tag_number}</h1><img src="https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={b.tag_number}" style="border:12px solid #000"><h2>{b.full_name}</h2><button onclick="window.print()" style="padding:12px 20px;background:#000;color:#fff;border:none;border-radius:8px">Print Tag</button></body></html>"""

@app.route("/hospitals", methods=["GET","POST"])
@roles_required("admin")
def hospitals():
    if request.method=="POST":
        code=request.form.get("code","").strip().upper(); name=request.form.get("name","").strip()
        if code and name and not Hospital.query.get(code):
            db.session.add(Hospital(code=code,name=name,region=request.form.get("region",""))); uname=code.lower()
            if not User.query.filter_by(username=uname).first():
                u=User(username=uname,role='admin',hospital_code=code); u.set_password(code+"@123"); db.session.add(u)
            db.session.commit(); flash("Created "+code)
    all_hosp=Hospital.query.order_by(Hospital.code).all()
    return page_template(render_template_string("""
    <div class="card"><h2>Add Mortuary</h2><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input name="code" placeholder="KATH-002" required><input name="name" placeholder="Name" required><input name="region" placeholder="Region"><button class="btn">Create 0/100000</button></form></div>
    <div class="card"><table><tr><th>Code</th><th>Name</th><th>Stored</th></tr>{% for h in hospitals %}<tr><td>{{ h.code }}</td><td>{{ h.name }}</td><td>{{ counts[h.code] }} / 100000</td></tr>{% endfor %}</table></div>
    """, hospitals=all_hosp, counts={h.code: Deceased.query.filter_by(hospital_code=h.code, status="Deposited").count() for h in all_hosp}), "Hospitals")

@app.route("/users", methods=["GET","POST"])
@roles_required("admin")
def users():
    if request.method=="POST":
        username=request.form.get("username","").strip(); password=request.form.get("password",""); role=request.form.get("role",""); hcode=request.form.get("hospital_code","").strip().upper() or current_user.hospital_code
        if current_user.hospital_code!="ALL": hcode=current_user.hospital_code
        if username and len(password)>=8 and not User.query.filter_by(username=username).first():
            u=User(username=username,role=role,hospital_code=hcode); u.set_password(password); db.session.add(u); db.session.commit(); flash("User created for "+hcode)
    q=User.query; 
    if current_user.hospital_code!="ALL": q=q.filter_by(hospital_code=current_user.hospital_code)
    return page_template(render_template_string("""
    <div class="card"><h2>Create User {{ current_user.hospital_code }}</h2><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input name="username" placeholder="Username" required><input type="password" name="password" placeholder="Min 8 chars" required><select name="role"><option value="admin">Admin</option><option value="supervisor">Supervisor</option><option value="officer">Officer</option><option value="viewer">Viewer</option></select>{% if current_user.hospital_code=='ALL' %}<input name="hospital_code" placeholder="Hospital Code e.g. KB-001" required>{% endif %}<button class="btn">Create</button></form></div>
    <div class="card"><table><tr><th>User</th><th>Hospital</th><th>Role</th></tr>{% for u in users %}<tr><td>{{ u.username }}</td><td>{{ u.hospital_code }}</td><td>{{ u.role }}</td></tr>{% endfor %}</table></div>
    """, users=q.all()), "Users")

@app.route("/audit")
@roles_required("admin","supervisor")
def audit():
    hcode=current_user.hospital_code; q=AuditLog.query; 
    if hcode!="ALL": q=q.filter_by(hospital_code=hcode)
    logs=q.order_by(AuditLog.timestamp.desc()).limit(300).all()
    return page_template(render_template_string("<div class='card'><h2>Audit {{ hcode }}</h2><table><tr><th>Time</th><th>User</th><th>Action</th><th>Tag</th></tr>{% for l in logs %}<tr><td>{{ l.timestamp }}</td><td>{{ l.username }}</td><td>{{ l.action }}</td><td>{{ l.tag_id }}</td></tr>{% endfor %}</table></div>", logs=logs, hcode=hcode), "Audit")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user(); return redirect(url_for("login"))

@app.route("/health")
def health(): return {"status":"ok","capacity":"0/100000 per hospital","v":"pro-national"},200

def seed_ghana():
    with app.app_context():
        db.create_all()
        hospitals = [("KB-001","Korle Bu Teaching Hospital","Greater Accra"),("RIDGE-001","Ridge Regional Hospital","Greater Accra"),("KATH-002","Komfo Anokye Teaching Hospital","Ashanti"),("CCTH-003","Cape Coast Teaching Hospital","Central"),("EHTH-004","Ho Teaching Hospital","Volta"),("TTH-005","Tamale Teaching Hospital","Northern"),("BTH-006","Sunyani Teaching Hospital","Bono"),("WRH-007","Effia Nkwanta Hospital","Western"),("ERH-009","Koforidua Regional Hospital","Eastern"),("URH-010","Bolgatanga Regional Hospital","Upper East"),("UWR-011","Wa Regional Hospital","Upper West"),("OTI-015","Dambai Regional Hospital","Oti")]
        for code,name,region in hospitals:
            if not Hospital.query.get(code):
                db.session.add(Hospital(code=code,name=name,region=region))
                uname=code.lower()
                if not User.query.filter_by(username=uname).first():
                    u=User(username=uname,role="admin",hospital_code=code); u.set_password(code+"@123"); db.session.add(u)
        if not User.query.filter_by(username="admin").first():
            admin=User(username="admin",role="admin",hospital_code="ALL"); admin.set_password("Admin@12345678"); db.session.add(admin)
        if not db.session.get(Settings,1): db.session.add(Settings(id=1))
        try: db.session.commit(); print("SEED PRO NATIONAL DONE")
        except: db.session.rollback()

seed_ghana()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
