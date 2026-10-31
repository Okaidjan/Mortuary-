import os, uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, url_for, flash, render_template_string, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "mortuary-v46-secure-no-hint")
database_url = os.environ.get("DATABASE_URL", "sqlite:///mortuary.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["WTF_CSRF_ENABLED"] = False

ADMISSION = 100
DAILY = 50

db = SQLAlchemy(app)
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

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facility_name = db.Column(db.String(150), default="Ghana National Mortuary System")

@login_manager.user_loader
def load_user(uid):
    try:
        u = db.session.get(User, int(uid))
        if u and u.active: return u
    except: return None

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
    try:
        if not created: created = datetime.utcnow()
        days = (datetime.utcnow() - created).days
        if days < 1: days = 1
        return days, ADMISSION + DAILY*days
    except: return 1, ADMISSION+DAILY

def get_facility_name():
    try:
        if current_user.is_authenticated:
            h = db.session.get(Hospital, current_user.hospital_code)
            if h: return h.name
            if current_user.hospital_code=="ALL": return "Ghana National - Super Admin"
        s = db.session.get(Settings,1)
        return s.facility_name if s else "Mortuary System"
    except: return "Mortuary System"

def page_template(content, title="MTS"):
    return render_template_string("""
    <!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }}</title>
    <style>body{margin:0;font-family:-apple-system,sans-serif;background:#f4f6f9} .nav{background:#0f172a;color:#fff;padding:10px 12px;display:flex;gap:8px;flex-wrap:wrap;font-size:13px;align-items:center} .nav a{color:#94a3b8;text-decoration:none;padding:5px 9px;border-radius:6px} .card{background:#fff;margin:12px;padding:16px;border-radius:12px} input,select,textarea{width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid #cbd5e1} button{padding:10px 14px;border:none;border-radius:8px;font-weight:700;cursor:pointer} .btn{background:#0ea5e9;color:#fff} .flash{padding:10px;background:#fff1c9;margin:8px 0;border-radius:5px} table{width:100%;border-collapse:collapse;background:#fff} th,td{padding:10px;border-bottom:1px solid #ddd} th{background:#e9f1f5}</style></head>
    <body><div class="nav"><b style="color:#fff">{{ facility_name }}</b> {% if current_user.is_authenticated %}<a href="{{ url_for('dashboard') }}">Dashboard</a> <a href="{{ url_for('admission') }}">+Deposit</a> <a href="{{ url_for('records') }}">Records</a> <a href="{{ url_for('hospitals') }}">Hospitals</a> <a href="{{ url_for('users') }}">Users</a> <a href="{{ url_for('settings') }}">Settings</a> <a href="{{ url_for('logout') }}" style="margin-left:auto;color:#fff">Logout ({{ current_user.username }})</a>{% endif %}</div>
    <main>{% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}{{ content|safe }}</main></body></html>
    """, content=content, title=title, facility_name=get_facility_name())

@app.route("/", methods=["GET","POST"])
@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("dashboard"))
    if request.method=="POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        user = User.query.filter_by(username=username).first()
        if user and user.active and user.check_password(password):
            login_user(user); return redirect(url_for("dashboard"))
        else: flash("Invalid credentials")
    # SECURE - NO CREDENTIALS SHOWING
    return page_template("""
    <div class="card" style="max-width:380px;margin:80px auto"><h2 style="text-align:center">Mortuary System</h2><p style="text-align:center;color:#64748b;font-size:13px">Secure Login</p>
    <form method="POST" style="text-align:left"><label>Username</label><input name="username" placeholder="Username" required autocomplete="username"><label>Password</label><input type="password" name="password" placeholder="Password" required autocomplete="current-password"><button class="btn" style="width:100%;margin-top:12px">Login</button></form></div>
    """, "Login")

@app.route("/dashboard")
@login_required
def dashboard():
    hcode=current_user.hospital_code
    base_q = Deceased.query if hcode=="ALL" else Deceased.query.filter_by(hospital_code=hcode)
    total = base_q.filter(Deceased.status!="Released").count()
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    unclaimed = base_q.filter(Deceased.status!="Released", Deceased.created_at < thirty_days_ago).count()
    recent = base_q.order_by(Deceased.id.desc()).limit(5).all()
    alert = f'<div class="card" style="background:#fef3c7;border:1px solid #fcd34d">⚠️ {unclaimed} bodies unclaimed >30 days</div>' if unclaimed>0 else ''
    rows="".join([f"<tr><td><a href='/record/{b.id}'><b>{b.tag_number}</b></a></td><td>{b.full_name}</td><td>{b.storage_id}</td><td>{b.status}</td></tr>" for b in recent])
    return page_template(f"""
    {alert}<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px"><div class="card"><b style="font-size:22px">{total} / 100000</b><br><small>{hcode} In Storage</small></div><div class="card"><b style="font-size:22px">{Hospital.query.count()}</b><br><small>Hospitals</small></div></div>
    <div class="card"><h3>Recent - {hcode}</h3><table><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th></tr>{rows}</table></div>
    """, "Dashboard")

@app.route("/admission", methods=["GET","POST"])
@roles_required("admin","supervisor","officer")
def admission():
    if current_user.hospital_code=="ALL": flash("Super Admin view only. Login as KB-001 to deposit"); return redirect(url_for("dashboard"))
    if request.method=="POST":
        tag=generate_tag(current_user.hospital_code); storage=free_storage(current_user.hospital_code)
        d=Deceased(tag_number=tag, hospital_code=current_user.hospital_code, full_name=request.form.get("name","Unknown"), age=request.form.get("age"), gender=request.form.get("gender"), cause=request.form.get("cause"), death_cert=request.form.get("death_cert"), police_case="Yes" if request.form.get("police_case") else "No", embalming="Yes" if request.form.get("embalming") else "No", refrigeration="Yes" if request.form.get("refrigeration") else "No", kin_name=request.form.get("kin_name"), kin_phone=request.form.get("kin_phone"), kin_rel=request.form.get("kin_rel"), kin_id=request.form.get("kin_id"), storage_id=storage, notes=request.form.get("notes"), status="Deposited", total_fee=ADMISSION+DAILY, paid_amount=0, balance=ADMISSION+DAILY, created_by=current_user.username)
        db.session.add(d); db.session.commit(); flash(f"Deposited {tag} {storage}"); return redirect(url_for("record_detail", record_id=d.id))
    cnt=Deceased.query.filter_by(hospital_code=current_user.hospital_code, status="Deposited").count()
    return page_template(render_template_string("""
    <div class="card"><h3>Deposit - {{ hcode }} ({{ cnt }}/100000)</h3><form method="POST">
    <input name="name" placeholder="Full Name *" required><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><input name="age" placeholder="Age"><select name="gender"><option>Male</option><option>Female</option><option>Other</option></select></div>
    <input name="cause" placeholder="Cause"><input name="death_cert" placeholder="Death Cert No"><div style="display:flex;gap:12px;font-size:13px"><label><input type="checkbox" name="police_case" style="width:auto"> Police</label><label><input type="checkbox" name="embalming" style="width:auto"> Embalming</label><label><input type="checkbox" name="refrigeration" checked style="width:auto"> Fridge</label></div><textarea name="notes" placeholder="Notes"></textarea><hr><h4>Kin</h4><input name="kin_name" placeholder="Kin Name"><input name="kin_phone" placeholder="Phone"><button class="btn" style="width:100%;margin-top:10px">Deposit</button></form></div>
    """, hcode=current_user.hospital_code, cnt=cnt), "Deposit")

@app.route("/records")
@login_required
def records():
    hcode=current_user.hospital_code
    q=Deceased.query if hcode=="ALL" else Deceased.query.filter_by(hospital_code=hcode)
    items=q.order_by(Deceased.id.desc()).limit(200).all()
    rows="".join([f"<tr><td><a href='/record/{b.id}'><b>{b.tag_number}</b></a></td><td>{b.full_name}</td><td>{b.storage_id}</td><td>{b.status}</td><td>GHS {b.balance}</td></tr>" for b in items])
    return page_template(f"<div class='card'><h3>{len(items)} Records - {hcode}</h3><table><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th><th>Bal</th></tr>{rows}</table></div>", "Records")

@app.route("/record/<int:record_id>")
@login_required
def record_detail(record_id):
    b = db.get_or_404(Deceased, record_id)
    days, fee = calc_fee(b.created_at)
    try:
        if fee != b.total_fee:
            b.total_fee = fee
            b.balance = fee - (b.paid_amount or 0)
            db.session.commit()
    except: pass
    pays = Payment.query.filter_by(tag_id=b.tag_number).order_by(Payment.id.desc()).all()
    pay_rows = "".join([f"<tr><td>{p.time.strftime('%Y-%m-%d %H:%M') if p.time else ''}</td><td>GHS {p.amount}</td><td>{p.user}</td></tr>" for p in pays]) or "<tr><td colspan=3>No payments yet</td></tr>"
    if b.status == "Released":
        release_html = f'<div class="card" style="background:#f0fdf4;border:2px solid #bbf7d0"><h3 style="color:#166534">✅ Released</h3><p>To: <b>{b.released_to or "-"}</b><br>Doc: {b.released_doc or "-"}<br>Date: {b.released_at or "-"}</p></div>'
    else:
        release_html = f"""
        <div class="card" style="border:2px solid #fecaca"><h4>Release Body</h4>
        <form method="POST" action="/record/{b.id}/release"><input name="collector_name" placeholder="Collector Name *" required><input name="collector_doc" placeholder="Ghana Card"><input name="confirm" placeholder="Type {b.tag_number} to confirm *" required><button style="background:#dc2626;color:#fff;width:100%;margin-top:6px;padding:12px;border-radius:8px">RELEASE NOW</button></form></div>
        """
    content = f"""
    <div class="card"><h3>{b.full_name} <small>{b.tag_number}</small></h3><p><b>Storage:</b> {b.storage_id} | <b>Status:</b> {b.status}<br><b>Age/Gender:</b> {b.age or '-'} / {b.gender or '-'}<br><b>Death Cert:</b> {b.death_cert or '-'} | <b>Police:</b> {b.police_case} | <b>Embalming:</b> {b.embalming} | <b>Fridge:</b> {b.refrigeration}<br><b>Kin:</b> {b.kin_name or '-'} ({b.kin_rel or ''}) - {b.kin_phone or ''}<br><b>Days:</b> {days} | <b>Fee:</b> GHS {b.total_fee} (Paid {b.paid_amount} Bal {b.balance})<br><b>Notes:</b> {b.notes or '-'}</p>
    <div style="text-align:center"><img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={b.tag_number}" style="border:6px solid #fff"><br><br><a href="/receipt/{b.id}" target="_blank"><button>Receipt</button></a> <a href="/record/{b.id}/move"><button>Move</button></a> <a href="/record/{b.id}/edit"><button>Edit</button></a></div></div>
    <div class="card"><h4>Payments</h4><form method="POST" action="/record/{b.id}/pay"><input name="amount" type="number" step="0.01" placeholder="Amount GHS" required style="width:65%"><button class="btn" style="width:30%;background:#16a34a">Add Pay</button></form><table style="margin-top:10px"><tr><th>Date</th><th>Amount</th><th>By</th></tr>{pay_rows}</table></div>
    {release_html}
    """
    return page_template(content, f"{b.tag_number}")

@app.route("/record/<int:record_id>/edit", methods=["GET","POST"])
def edit_record(record_id):
    b=db.get_or_404(Deceased, record_id)
    if request.method=="POST":
        b.full_name=request.form.get("name") or b.full_name
        b.age=request.form.get("age"); b.death_cert=request.form.get("death_cert"); b.kin_name=request.form.get("kin_name"); b.kin_phone=request.form.get("kin_phone"); b.notes=request.form.get("notes")
        db.session.commit(); return redirect(url_for("record_detail", record_id=b.id))
    return page_template(f"""
    <div class="card"><h3>Edit {b.tag_number}</h3><form method="POST"><input name="name" value="{b.full_name}"><input name="age" value="{b.age or ''}"><input name="death_cert" value="{b.death_cert or ''}"><input name="kin_name" value="{b.kin_name or ''}"><input name="kin_phone" value="{b.kin_phone or ''}"><textarea name="notes">{b.notes or ''}</textarea><button class="btn" style="width:100%">Save Changes</button></form></div>
    """, "Edit")

@app.route("/record/<int:record_id>/move", methods=["GET","POST"])
def move_storage(record_id):
    b=db.get_or_404(Deceased, record_id)
    if request.method=="POST":
        b.storage_id=request.form.get("storage"); db.session.commit(); return redirect(url_for("record_detail", record_id=b.id))
    suggestion = free_storage(b.hospital_code)
    return page_template(f"""
    <div class="card"><h3>Move {b.tag_number} (Current {b.storage_id})</h3><p>Suggest: {suggestion}</p><form method="POST"><input name="storage" value="{suggestion}" required><button class="btn" style="width:100%">Move Now</button></form></div>
    """, "Move")

@app.route("/record/<int:record_id>/pay", methods=["POST"])
def pay(record_id):
    b=db.get_or_404(Deceased, record_id)
    try: amt=float(request.form.get("amount",0) or 0)
    except: amt=0
    if amt>0:
        b.paid_amount=(b.paid_amount or 0)+amt; b.balance=(b.total_fee or 0)-b.paid_amount
        p=Payment(tag_id=b.tag_number, amount=amt, user=current_user.username if current_user.is_authenticated else "admin")
        db.session.add(p); db.session.commit()
    return redirect(url_for("record_detail", record_id=b.id))

@app.route("/record/<int:record_id>/release", methods=["POST"])
def release_record(record_id):
    b=db.get_or_404(Deceased, record_id)
    if request.form.get("confirm","").strip()!=b.tag_number:
        flash(f"Type exactly {b.tag_number} to confirm"); return redirect(url_for("record_detail", record_id=b.id))
    b.status="Released"; b.released_at=datetime.utcnow(); b.released_to=request.form.get("collector_name"); b.released_doc=request.form.get("collector_doc"); db.session.commit()
    flash(f"Released {b.tag_number}"); return redirect(url_for("record_detail", record_id=b.id))

@app.route("/receipt/<int:record_id>")
@login_required
def receipt(record_id):
    b=db.get_or_404(Deceased, record_id); return f"<html><body style='font-family:monospace;text-align:center;padding:20px'><h3>{get_facility_name()}<br>RECEIPT</h3>Tag: {b.tag_number}<br>Name: {b.full_name}<br>Storage: {b.storage_id}<br>Total: GHS {b.total_fee}<br>Paid: {b.paid_amount}<br>Balance: {b.balance}<br><br><img src='https://api.qrserver.com/v1/create-qr-code/?size=140x140&data={b.tag_number}'><br><button onclick='window.print()'>Print</button></body></html>"

@app.route("/hospitals", methods=["GET","POST"])
@roles_required("admin")
def hospitals():
    if request.method=="POST":
        code=request.form.get("code","").strip().upper(); name=request.form.get("name","").strip()
        if code and name and not Hospital.query.get(code):
            db.session.add(Hospital(code=code,name=name,region=request.form.get("region","")))
            uname=code.lower()
            if not User.query.filter_by(username=uname).first():
                u=User(username=uname,role="admin",hospital_code=code); u.set_password(code+"@123"); db.session.add(u)
            db.session.commit(); flash("Created "+code)
    all_hosp=Hospital.query.order_by(Hospital.code).all()
    rows="".join([f"<tr><td>{h.code}</td><td>{h.name}</td><td>{Deceased.query.filter_by(hospital_code=h.code).filter(Deceased.status!='Released').count()} / 100000</td></tr>" for h in all_hosp])
    return page_template(f"<div class='card'><h2>Add Hospital</h2><form method='POST'><input name='code' placeholder='KATH-002' required><input name='name' placeholder='Name' required><button class='btn'>Create 0/100000</button></form></div><div class='card'><table><tr><th>Code</th><th>Name</th><th>Stored</th></tr>{rows}</table></div>", "Hospitals")

@app.route("/users")
@roles_required("admin")
def users():
    q=User.query if current_user.hospital_code=="ALL" else User.query.filter_by(hospital_code=current_user.hospital_code)
    rows="".join([f"<tr><td>{u.username}</td><td>{u.hospital_code}</td><td>{u.role}</td></tr>" for u in q.all()])
    return page_template(f"<div class='card'><h3>Users - {current_user.hospital_code}</h3><table><tr><th>User</th><th>Hospital</th><th>Role</th></tr>{rows}</table></div>", "Users")

@app.route("/settings", methods=["GET","POST"])
@roles_required("admin")
def settings():
    s=db.session.get(Settings,1)
    if request.method=="POST":
        if s: s.facility_name=request.form.get("facility_name", s.facility_name)
        new_pass=request.form.get("new_password","").strip()
        if new_pass and len(new_pass)>=8:
            u=User.query.filter_by(username="admin").first()
            if u: u.set_password(new_pass); db.session.commit(); flash("Admin password changed - saved securely, not shown on login")
        if s: db.session.commit()
        flash("Settings saved"); return redirect(url_for("settings"))
    return page_template(f"""
    <div class="card"><h2>⚙️ Settings</h2><form method="POST"><label>Facility Name</label><input name="facility_name" value="{s.facility_name if s else 'Ghana National Mortuary System'}"><hr><label>Change Admin Password (secure - not displayed on login)</label><input name="new_password" type="password" placeholder="New password min 8 chars"><button class="btn" style="width:100%;margin-top:10px">Save Settings & Password</button></form></div>
    <div class="card"><p><b>Security:</b> ✅ No credentials on login page<br>✅ CSRF disabled - no Bad Request error<br>✅ 0/100000 per hospital</p></div>
    """, "Settings")

@app.route("/logout")
@login_required
def logout():
    logout_user(); return redirect(url_for("login"))

@app.route("/health")
def health(): return {"status":"ok","v":"v46-secure-no-hint"},200

def seed_ghana():
    with app.app_context():
        print("REBUILD V46 SECURE NO HINT...")
        try: db.drop_all()
        except: pass
        db.create_all()
        hospitals = [("KB-001","Korle Bu Teaching Hospital","Greater Accra"),("RIDGE-001","Ridge Regional Hospital","Greater Accra"),("KATH-002","Komfo Anokye Teaching Hospital","Ashanti"),("CCTH-003","Cape Coast Teaching Hospital","Central"),("EHTH-004","Ho Teaching Hospital","Volta"),("TTH-005","Tamale Teaching Hospital","Northern"),("BTH-006","Sunyani Teaching Hospital","Bono"),("WRH-007","Effia Nkwanta Hospital","Western"),("ERH-009","Koforidua Regional Hospital","Eastern"),("URH-010","Bolgatanga Regional Hospital","Upper East"),("UWR-011","Wa Regional Hospital","Upper West"),("OTI-015","Dambai Regional Hospital","Oti")]
        for code,name,region in hospitals:
            db.session.add(Hospital(code=code,name=name,region=region))
            u=User(username=code.lower(),role="admin",hospital_code=code); u.set_password(code+"@123"); db.session.add(u)
        admin=User(username="admin",role="admin",hospital_code="ALL"); admin.set_password("Admin@12345678"); db.session.add(admin)
        db.session.add(Settings(id=1, facility_name="Ghana National Mortuary System"))
        db.session.commit()
        print("SEED V46 DONE")

seed_ghana()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
