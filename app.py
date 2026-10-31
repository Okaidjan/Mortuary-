import os, uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, url_for, flash, render_template_string, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "ghana-mortuary-v4-3-force-rebuild")
database_url = os.environ.get("DATABASE_URL", "sqlite:///mortuary.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
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
    try:
        if current_user.is_authenticated:
            h = db.session.get(Hospital, current_user.hospital_code)
            if h: return h.name
            if current_user.hospital_code=="ALL": return "Ghana National Mortuary System - Super Admin"
        s = db.session.get(Settings,1)
        return s.facility_name if s and s.facility_name else "Ghana National Mortuary System"
    except:
        return "Ghana National Mortuary System"

def page_template(content, title="MTS"):
    return render_template_string("""
    <!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }}</title>
    <style>body{margin:0;font-family:-apple-system,sans-serif;background:#f4f6f9} .nav{background:#0f172a;color:#fff;padding:10px 12px;display:flex;gap:8px;flex-wrap:wrap;font-size:13px;align-items:center} .nav a{color:#94a3b8;text-decoration:none;padding:5px 9px;border-radius:6px} .card{background:#fff;margin:12px;padding:16px;border-radius:12px;box-shadow:0 1px 2px rgba(0,0,0,.06)} input,select,textarea{width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid #cbd5e1;box-sizing:border-box} button{padding:10px 14px;border:none;border-radius:8px;font-weight:700;cursor:pointer} .btn{background:#0ea5e9;color:#fff} .badge{padding:2px 8px;border-radius:999px;font-size:11px} .deposited{background:#dcfce7;color:#166534} .released{background:#fee2e2;color:#991b1b} .alert{background:#fef3c7;border:1px solid #fcd34d;padding:10px;border-radius:8px;margin:12px} table{width:100%;border-collapse:collapse;background:#fff} th,td{padding:10px;border-bottom:1px solid #ddd} th{background:#e9f1f5} .flash{padding:10px;background:#fff1c9;margin:8px 0;border-radius:5px}</style></head>
    <body><div class="nav"><b style="color:#fff">{{ facility_name }}</b> {% if current_user.is_authenticated %}<a href="{{ url_for('dashboard') }}">Dashboard</a> <a href="{{ url_for('admission') }}">+Deposit</a> <a href="{{ url_for('records') }}">Records</a> <a href="{{ url_for('hospitals') }}">Hospitals</a> <a href="{{ url_for('users') }}">Users</a> <a href="{{ url_for('settings') }}">Settings</a> <form method="POST" action="{{ url_for('logout') }}" style="display:inline;margin-left:auto"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button style="background:#334155;color:#fff">Logout ({{ current_user.username }})</button></form>{% endif %}</div>
    <main>{% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}{{ content|safe }}</main></body></html>
    """, content=content, title=title, facility_name=get_facility_name())

@app.route("/", methods=["GET","POST"])
@app.route("/login", methods=["GET","POST"])
@csrf.exempt
def login():
    if current_user.is_authenticated: return redirect(url_for("dashboard"))
    if request.method=="POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        user = User.query.filter_by(username=username).first()
        if user and user.active and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials")
    return page_template("""
    <div class="card" style="max-width:380px;margin:60px auto;text-align:center"><h2>Mortuary System</h2><p style="color:#64748b;font-size:13px">Secure Login - One Link Ghana - V4.3 Fixed</p>
    <form method="POST" style="text-align:left"><label>Hospital Code (for info)</label><input name="hospital_code" placeholder="ALL or KB-001" style="text-transform:uppercase" value="ALL"><label>Username *</label><input name="username" placeholder="Username" required value="admin"><label>Password *</label><input type="password" name="password" placeholder="Password" required><button class="btn" style="width:100%;margin-top:10px">Login</button></form>
    <p style="font-size:11px;color:#64748b;margin-top:10px">Admin: ALL / admin / Admin@12345678<br>Korle Bu: KB-001 / kb-001 / KB-001@123</p></div>
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
    alert = f'<div class="alert">⚠️ {unclaimed} bodies unclaimed >30 days</div>' if unclaimed>0 else ''
    recent_rows="".join([f"<tr><td><a href='/record/{b.id}'><b>{b.tag_number}</b></a></td><td>{b.full_name}</td><td>{b.storage_id}</td><td>{b.status}</td></tr>" for b in recent])
    return page_template(f"""
    {alert}<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px"><div class="card"><b style="font-size:22px">{total} / 100000</b><br><small>{hcode} In Storage</small></div><div class="card"><b style="font-size:22px">{Hospital.query.count()}</b><br><small>Hospitals</small></div></div>
    <div class="card"><h3>Recent - {hcode}</h3><table><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th></tr>{recent_rows}</table></div>
    """, "Dashboard")

@app.route("/admission", methods=["GET","POST"])
@roles_required("admin","supervisor","officer")
def admission():
    if current_user.hospital_code=="ALL": flash("Super Admin view only. Login as KB-001 to deposit"); return redirect(url_for("dashboard"))
    if request.method=="POST":
        tag=generate_tag(current_user.hospital_code); storage=free_storage(current_user.hospital_code)
        d=Deceased(tag_number=tag, hospital_code=current_user.hospital_code, full_name=request.form.get("name"), age=request.form.get("age"), gender=request.form.get("gender"), cause=request.form.get("cause"), death_cert=request.form.get("death_cert"), police_case="Yes" if request.form.get("police_case") else "No", embalming="Yes" if request.form.get("embalming") else "No", refrigeration="Yes" if request.form.get("refrigeration") else "No", kin_name=request.form.get("kin_name"), kin_phone=request.form.get("kin_phone"), kin_rel=request.form.get("kin_rel"), kin_id=request.form.get("kin_id"), storage_id=storage, notes=request.form.get("notes"), status="Deposited", total_fee=ADMISSION+DAILY, paid_amount=0, balance=ADMISSION+DAILY, created_by=current_user.username)
        db.session.add(d); db.session.commit(); flash(f"Deposited {tag}"); return redirect(url_for("record_detail", record_id=d.id))
    cnt=Deceased.query.filter_by(hospital_code=current_user.hospital_code, status="Deposited").count()
    return page_template(render_template_string("""
    <div class="card"><h3>Deposit Body - {{ hcode }} ({{ cnt }} / 100000)</h3><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input name="name" placeholder="Deceased Full Name *" required><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><input name="age" placeholder="Age"><select name="gender"><option>Male</option><option>Female</option><option>Other</option></select></div>
    <input name="cause" placeholder="Cause"><input name="death_cert" placeholder="Death Certificate No."><div style="display:flex;gap:12px;font-size:13px"><label><input type="checkbox" name="police_case" style="width:auto"> Police Case</label><label><input type="checkbox" name="embalming" style="width:auto"> Embalming</label><label><input type="checkbox" name="refrigeration" checked style="width:auto"> Refrigeration</label></div><textarea name="notes" placeholder="Notes"></textarea><hr><h4>Next of Kin</h4><input name="kin_name" placeholder="Kin Name"><input name="kin_phone" placeholder="Kin Phone"><button class="btn" style="width:100%;margin-top:10px">Deposit</button></form></div>
    """, hcode=current_user.hospital_code, cnt=cnt), "Deposit")

@app.route("/records")
@login_required
def records():
    hcode=current_user.hospital_code; q=Deceased.query if hcode=="ALL" else Deceased.query.filter_by(hospital_code=hcode)
    items=q.order_by(Deceased.id.desc()).limit(200).all()
    return page_template(render_template_string("""
    <div class="card"><h3>{{ items|length }} Records - {{ hcode }}</h3><table><tr><th>Tag</th><th>Name</th><th>Storage</th><th>Status</th></tr>{% for b in items %}<tr><td><a href="{{ url_for('record_detail', record_id=b.id) }}"><b>{{ b.tag_number }}</b></a></td><td>{{ b.full_name }}</td><td>{{ b.storage_id }}</td><td>{{ b.status }}</td></tr>{% endfor %}</table></div>
    """, items=items, hcode=hcode), "Records")

@app.route("/record/<int:record_id>")
@login_required
def record_detail(record_id):
    b=db.get_or_404(Deceased, record_id)
    pays=Payment.query.filter_by(tag_id=b.tag_number).order_by(Payment.id.desc()).all()
    pay_rows="".join([f"<tr><td>{p.time}</td><td>GHS {p.amount}</td></tr>" for p in pays]) or "<tr><td colspan=2>No payments</td></tr>"
    if b.status=="Released":
        release_section = f'<div class="card" style="background:#f0fdf4"><h3 style="color:#166534">✅ Released to {b.released_to}</h3></div>'
    else:
        release_section = f'<div class="card" style="border:2px solid #fecaca"><h4>Release</h4><form method="POST" action="/record/{b.id}/release"><input type="hidden" name="csrf_token" value="{csrf_token()}"><input name="collector_name" placeholder="Collector" required><input name="confirm" placeholder="Type {b.tag_number}" required><button style="background:#dc2626;color:#fff;width:100%">RELEASE NOW</button></form></div>'
    return page_template(f"""
    <div class="card"><h3>{b.full_name} {b.tag_number}</h3><p>Storage: {b.storage_id} | Status: {b.status}<br>Death Cert: {b.death_cert} | Police: {b.police_case}<br>Fee: GHS {b.total_fee}</p><a href="/receipt/{b.id}"><button>Receipt</button></a></div>
    <div class="card"><h4>Payments</h4><form method="POST" action="/record/{b.id}/pay"><input type="hidden" name="csrf_token" value="{csrf_token()}"><input name="amount" type="number" placeholder="Amount" required><button class="btn">Add</button></form><table><tr><th>Date</th><th>Amount</th></tr>{pay_rows}</table></div>{release_section}
    """, "Body")

@app.route("/record/<int:record_id>/pay", methods=["POST"])
def pay(record_id):
    b=db.get_or_404(Deceased, record_id); amt=float(request.form.get("amount",0) or 0); b.paid_amount=(b.paid_amount or 0)+amt; b.balance=(b.total_fee or 0)-b.paid_amount; p=Payment(tag_id=b.tag_number, amount=amt, user=current_user.username); db.session.add(p); db.session.commit(); return redirect(url_for("record_detail", record_id=b.id))

@app.route("/record/<int:record_id>/release", methods=["POST"])
def release_record(record_id):
    b=db.get_or_404(Deceased, record_id)
    if request.form.get("confirm","").strip()!=b.tag_number: flash("Confirm failed"); return redirect(url_for("record_detail", record_id=b.id))
    b.status="Released"; b.released_at=datetime.utcnow(); b.released_to=request.form.get("collector_name"); db.session.commit(); return redirect(url_for("record_detail", record_id=b.id))

@app.route("/receipt/<int:record_id>")
@login_required
def receipt(record_id):
    b=db.get_or_404(Deceased, record_id); return f"<html><body style='text-align:center'>Receipt {b.tag_number} {b.full_name} GHS {b.total_fee} <button onclick='window.print()'>Print</button></body></html>"

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
    return page_template(render_template_string("""<div class="card"><h2>Add Hospital</h2><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input name="code" placeholder="CODE" required><input name="name" placeholder="Name" required><button class="btn">Create</button></form></div><div class="card"><table><tr><th>Code</th><th>Name</th></tr>{% for h in hospitals %}<tr><td>{{ h.code }}</td><td>{{ h.name }}</td></tr>{% endfor %}</table></div>""", hospitals=all_hosp), "Hospitals")

@app.route("/users")
@roles_required("admin")
def users():
    q=User.query
    if current_user.hospital_code!="ALL": q=q.filter_by(hospital_code=current_user.hospital_code)
    return page_template(render_template_string("""<div class="card"><table><tr><th>User</th><th>Hospital</th></tr>{% for u in users %}<tr><td>{{ u.username }}</td><td>{{ u.hospital_code }}</td></tr>{% endfor %}</table></div>""", users=q.all()), "Users")

@app.route("/settings", methods=["GET","POST"])
@roles_required("admin")
def settings():
    s = db.session.get(Settings,1)
    if request.method=="POST":
        if s: s.facility_name = request.form.get("facility_name", s.facility_name)
        else: s = Settings(id=1, facility_name=request.form.get("facility_name","Ghana National Mortuary System")); db.session.add(s)
        new_pass = request.form.get("new_password","").strip()
        if new_pass and len(new_pass)>=8:
            u = User.query.filter_by(username="admin").first()
            if u: u.set_password(new_pass); flash(f"Admin password changed to {new_pass}")
        db.session.commit()
        flash("Settings saved")
        return redirect(url_for("settings"))
    return page_template(render_template_string("""
    <div class="card"><h2>⚙️ Settings</h2><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><label>Facility Name</label><input name="facility_name" value="{{ s.facility_name if s else 'Ghana National Mortuary System' }}"><hr><label>Change Admin Password</label><input name="new_password" type="text" placeholder="New password min 8 chars"><button class="btn" style="width:100%;margin-top:10px">Save</button></form></div>
    <div class="card"><p><b>Logins:</b><br>ALL / admin / Admin@12345678<br>KB-001 / kb-001 / KB-001@123</p></div>
    """, s=s), "Settings")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user(); return redirect(url_for("login"))

@app.route("/health")
def health(): return {"status":"ok","v":"v4-3-force"},200

def seed_ghana():
    with app.app_context():
        # FORCE REBUILD - drop everything and recreate
        print("FORCE REBUILD START...")
        try:
            db.drop_all()
            print("Dropped all")
        except Exception as e:
            print(f"Drop error: {e}")
        try:
            db.create_all()
            print("Created all")
        except Exception as e:
            print(f"Create error: {e}")
            return

        hospitals = [("KB-001","Korle Bu Teaching Hospital","Greater Accra"),("RIDGE-001","Ridge Regional Hospital","Greater Accra"),("KATH-002","Komfo Anokye Teaching Hospital","Ashanti"),("CCTH-003","Cape Coast Teaching Hospital","Central"),("EHTH-004","Ho Teaching Hospital","Volta"),("TTH-005","Tamale Teaching Hospital","Northern"),("BTH-006","Sunyani Teaching Hospital","Bono"),("WRH-007","Effia Nkwanta Hospital","Western"),("ERH-009","Koforidua Regional Hospital","Eastern"),("URH-010","Bolgatanga Regional Hospital","Upper East"),("UWR-011","Wa Regional Hospital","Upper West"),("OTI-015","Dambai Regional Hospital","Oti")]
        for code,name,region in hospitals:
            db.session.add(Hospital(code=code,name=name,region=region))
            uname=code.lower()
            u=User(username=uname,role="admin",hospital_code=code)
            u.set_password(code+"@123")
            db.session.add(u)
        admin=User(username="admin",role="admin",hospital_code="ALL")
        admin.set_password("Admin@12345678")
        db.session.add(admin)
        db.session.add(Settings(id=1, facility_name="Ghana National Mortuary System"))
        try:
            db.session.commit()
            print("SEED V4.3 DONE - ADMIN READY")
        except Exception as e:
            print(f"Seed commit error: {e}")
            db.session.rollback()

seed_ghana()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
