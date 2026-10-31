import os, csv, io, uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, url_for, flash, render_template_string, make_response, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "ghana-mortuary-2026-super-secure-final-v4-1")
database_url = os.environ.get("DATABASE_URL", "sqlite:///mortuary.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["WTF_CSRF_TIME_LIMIT"] = None

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
    sex = db.Column(db.String(20))
    age = db.Column(db.String(20))
    next_of_kin = db.Column(db.String(150))
    contact = db.Column(db.String(50))
    place_of_death = db.Column(db.String(150))
    cause_of_death = db.Column(db.String(200))
    storage_id = db.Column(db.String(30))
    date_received = db.Column(db.DateTime, default=datetime.utcnow)
    date_released = db.Column(db.DateTime)
    status = db.Column(db.String(30), default="In Mortuary")
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(80))

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    hospital_code = db.Column(db.String(20))
    action = db.Column(db.String(200), nullable=False)
    record_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(60))

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facility_name = db.Column(db.String(150), default="Ghana National Mortuary System")

@login_manager.user_loader
def load_user(user_id):
    try:
        u = db.session.get(User, int(user_id))
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

def log_action(action, record_id=None):
    try:
        e = AuditLog(username=current_user.username if current_user.is_authenticated else "System", hospital_code=getattr(current_user,'hospital_code','ALL'), action=action, record_id=record_id, ip_address=request.remote_addr)
        db.session.add(e); db.session.commit()
    except: db.session.rollback()

def generate_tag(hcode): return hcode + "-" + datetime.utcnow().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:4].upper()
def free_storage(hcode):
    used = [r.storage_id for r in Deceased.query.filter_by(hospital_code=hcode).filter(Deceased.status != "Released").all() if r.storage_id]
    for i in range(1,100001):
        sid = "F"+str((i//100)+1).zfill(2)+"-S"+str((i%100)+1).zfill(3)
        if sid not in used: return sid
    return "F99-S999"

def get_facility_name():
    if current_user.is_authenticated:
        h = db.session.get(Hospital, current_user.hospital_code)
        if h: return h.name
        if current_user.hospital_code == "ALL": return "Ghana National Mortuary System - Super Admin"
    s = db.session.get(Settings, 1)
    return s.facility_name if s else "Mortuary Management System"

def page_template(content, title="MTS"):
    return render_template_string("""
    <!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }}</title>
    <style>body{font-family:Arial,sans-serif;background:#f2f5f7;margin:0}header{background:#123c58;color:white;padding:18px}nav{background:#e1eaf0;padding:12px;display:flex;gap:12px;flex-wrap:wrap}nav a{color:#123c58;font-weight:bold;text-decoration:none}main{max-width:1100px;margin:22px auto;padding:15px}.card{background:white;padding:20px;margin-bottom:18px;border-radius:9px}input,select,textarea{width:100%;padding:11px;margin:7px 0 14px;border:1px solid #ccd5dc;border-radius:5px;box-sizing:border-box}button,.btn{background:#146c94;color:white;padding:10px 15px;border:0;border-radius:5px}table{width:100%;border-collapse:collapse;background:white}th,td{padding:10px;border-bottom:1px solid #ddd}th{background:#e9f1f5}.flash{padding:10px;background:#fff1c9;margin:8px 0;border-radius:5px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}</style></head>
    <body><header><h2>{{ facility_name }}</h2><small>One Link All Ghana | 0/100000 per Hospital | {{ current_user.hospital_code if current_user.is_authenticated else '' }}</small></header>
    {% if current_user.is_authenticated %}<nav><a href="{{ url_for('dashboard') }}">Dashboard</a><a href="{{ url_for('admission') }}">New Admission</a><a href="{{ url_for('records') }}">Records</a><a href="{{ url_for('audit') }}">Audit</a><a href="{{ url_for('users') }}">Users</a><a href="{{ url_for('hospitals') }}">Hospitals</a><form method="POST" action="{{ url_for('logout') }}" style="display:inline"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button type="submit">Logout ({{ current_user.username }})</button></form></nav>{% endif %}
    <main>{% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}{{ content|safe }}</main></body></html>
    """, content=content, title=title, facility_name=get_facility_name())

@app.route("/", methods=["GET","POST"])
@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("dashboard"))
    if request.method=="POST":
        hcode = request.form.get("hospital_code","").strip().upper()
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        user = User.query.filter_by(username=username).first()
        if user and user.active and user.check_password(password):
            if user.hospital_code=="ALL" or user.hospital_code==hcode or (hcode=="ALL" and user.role=="admin"):
                login_user(user); log_action("Login to "+hcode); return redirect(url_for("dashboard"))
            else: flash("Hospital mismatch. Yours: "+user.hospital_code)
        else: flash("Invalid login")
    return page_template("""
    <div class="card" style="max-width:430px;margin:40px auto"><h2>Ghana National Mortuary</h2><p style="font-size:12px">One link, each hospital 0/100000</p>
    <form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><label>Hospital Code *</label><input name="hospital_code" placeholder="KB-001 or ALL" required style="text-transform:uppercase"><label>Username</label><input name="username" required><label>Password</label><input type="password" name="password" required><button type="submit">Login</button></form>
    <div style="margin-top:14px;font-size:11px"><b>Login:</b><br>ALL / admin / Admin@12345678<br>KB-001 / kb-001 / KB-001@123</div></div>
    """, "Login")

@app.route("/dashboard")
@login_required
def dashboard():
    hcode=current_user.hospital_code
    if hcode=="ALL": total_in=Deceased.query.filter_by(status="In Mortuary").count(); released=Deceased.query.filter_by(status="Released").count(); total_hosp=Hospital.query.count()
    else: total_in=Deceased.query.filter_by(hospital_code=hcode,status="In Mortuary").count(); released=Deceased.query.filter_by(hospital_code=hcode,status="Released").count(); total_hosp=1
    q=Deceased.query; 
    if hcode!="ALL": q=q.filter_by(hospital_code=hcode)
    recent=q.order_by(Deceased.id.desc()).limit(5).all()
    return page_template(render_template_string("""
    <h2>Dashboard - {{ hcode }}</h2><div class="grid"><div class="card"><h3>Currently Stored</h3><h2>{{ total_in }} / 100000</h2></div><div class="card"><h3>Released</h3><h2>{{ released }}</h2></div><div class="card"><h3>Hospitals</h3><h2>{{ total_hosp }}</h2></div></div>
    <div class="card"><table><tr><th>Tag</th><th>Name</th><th>Hosp</th><th>Storage</th><th>Status</th></tr>{% for i in recent %}<tr><td>{{ i.tag_number }}</td><td>{{ i.full_name }}</td><td>{{ i.hospital_code }}</td><td>{{ i.storage_id }}</td><td>{{ i.status }}</td></tr>{% endfor %}</table></div>
    """, total_in=total_in, released=released, total_hosp=total_hosp, recent=recent, hcode=hcode), "Dashboard")

@app.route("/hospitals", methods=["GET","POST"])
@roles_required("admin")
def hospitals():
    if request.method=="POST":
        code=request.form.get("code","").strip().upper(); name=request.form.get("name","").strip(); region=request.form.get("region","").strip()
        if code and name and not Hospital.query.get(code):
            db.session.add(Hospital(code=code,name=name,region=region))
            uname=code.lower()
            if not User.query.filter_by(username=uname).first():
                u=User(username=uname,role='admin',hospital_code=code); u.set_password(code+"@123"); db.session.add(u)
            db.session.commit(); flash("Created "+code)
    all_hosp=Hospital.query.order_by(Hospital.code).all()
    return page_template(render_template_string("""
    <div class="card"><h2>Add Mortuary</h2><form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input name="code" placeholder="KATH-002" required><input name="name" placeholder="Hospital Name" required><input name="region" placeholder="Region"><button>Create 0/100000</button></form></div>
    <div class="card"><table><tr><th>Code</th><th>Name</th><th>Stored</th><th>Login</th></tr>{% for h in hospitals %}<tr><td>{{ h.code }}</td><td>{{ h.name }}</td><td>{{ counts[h.code] }} / 100000</td><td>{{ h.code.lower() }} / {{ h.code }}@123</td></tr>{% endfor %}</table></div>
    """, hospitals=all_hosp, counts={h.code: Deceased.query.filter_by(hospital_code=h.code,status="In Mortuary").count() for h in all_hosp}), "Hospitals")

@app.route("/admission", methods=["GET","POST"])
@roles_required("admin","supervisor","officer")
def admission():
    if current_user.hospital_code=="ALL": flash("Login with specific hospital like KB-001 to admit"); return redirect(url_for("dashboard"))
    if request.method=="POST":
        full_name=request.form.get("full_name","").strip()
        if not full_name: flash("Name required"); return redirect(url_for("admission"))
        tag=generate_tag(current_user.hospital_code); storage=free_storage(current_user.hospital_code)
        d=Deceased(tag_number=tag,hospital_code=current_user.hospital_code,full_name=full_name,sex=request.form.get("sex"),age=request.form.get("age"),next_of_kin=request.form.get("next_of_kin"),contact=request.form.get("contact"),place_of_death=request.form.get("place_of_death"),cause_of_death=request.form.get("cause_of_death"),storage_id=storage,notes=request.form.get("notes"),created_by=current_user.username,status="In Mortuary")
        db.session.add(d); db.session.commit(); flash(f"Saved {tag} {storage} Now {Deceased.query.filter_by(hospital_code=current_user.hospital_code,status='In Mortuary').count()} / 100000"); return redirect(url_for("records"))
    return page_template(render_template_string("""
    <div class="card"><h2>New Admission - {{ hcode }} ({{ cnt }} / 100000)</h2>
    <form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <label>Full Name *</label><input name="full_name" required>
    <label>Sex</label><select name="sex"><option></option><option>Male</option><option>Female</option></select>
    <label>Age</label><input name="age"><label>Next of Kin</label><input name="next_of_kin"><label>Contact</label><input name="contact">
    <label>Place</label><input name="place_of_death"><label>Cause</label><input name="cause_of_death"><label>Notes</label><textarea name="notes"></textarea>
    <button type="submit">Save</button></form></div>
    """, hcode=current_user.hospital_code, cnt=Deceased.query.filter_by(hospital_code=current_user.hospital_code,status='In Mortuary').count()), "Admission")

@app.route("/records")
@login_required
def records():
    search=request.args.get("q","").strip(); hcode=current_user.hospital_code
    q=Deceased.query; 
    if hcode!="ALL": q=q.filter_by(hospital_code=hcode)
    if search: q=q.filter(or_(Deceased.full_name.ilike(f"%{search}%"), Deceased.tag_number.ilike(f"%{search}%")))
    items=q.order_by(Deceased.id.desc
