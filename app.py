from flask import Flask, request, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import csv, io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mortuary-pro-pwa-2026-final'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mortuary.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

CAPACITY = 100000

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='admin')

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_name = db.Column(db.String(200), default='Mortuary Tracking System')

class Deceased(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tag_number = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    date_of_death = db.Column(db.String(20))
    date_admitted = db.Column(db.DateTime, default=datetime.utcnow)
    date_released = db.Column(db.DateTime, nullable=True)
    cause_of_death = db.Column(db.String(200))
    relatives_contact = db.Column(db.String(100))
    status = db.Column(db.String(20), default='In Storage')
    location = db.Column(db.String(50))

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200))
    tag_number = db.Column(db.String(50))
    user = db.Column(db.String(80))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_hospital_name():
    s = Settings.query.first()
    return s.hospital_name if s else 'Mortuary Tracking System'

def generate_tag():
    year = datetime.utcnow().year
    count = Deceased.query.count() + 1
    return f"MORT-{year}-{count:05d}"

def log_action(action, tag=""):
    try:
        l = AuditLog(action=action, tag_number=tag, user=current_user.username if current_user.is_authenticated else 'system')
        db.session.add(l)
        db.session.commit()
    except:
        pass

def layout(title, body):
    h_name = get_hospital_name()
    uname = current_user.username if current_user.is_authenticated else ''
    return f"""
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#111827">
    <link rel="icon" href="https://cdn-icons-png.flaticon.com/512/2966/2966327.png">
    <script>if('serviceWorker' in navigator){{navigator.serviceWorker.register('/static/sw.js').then(()=>console.log('PWA Ready'));}}</script>
    <style>
    body{{font-family:system-ui,sans-serif;margin:0;background:#f8f9fa;color:#333}}
    .header{{background:#111827;color:white;padding:12px 15px;display:flex;justify-content:space-between;flex-wrap:wrap}}
    .header a{{color:#9ca3af;text-decoration:none;margin:0 6px;font-size:13px}}
    .header a.active{{color:white;font-weight:bold;border-bottom:2px solid #10b981}}
    .container{{padding:15px;max-width:1100px;margin:auto}}
    .grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
    @media(max-width:700px){{.grid3{{grid-template-columns:1fr}}}}
    .card{{background:white;padding:15px;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);margin-bottom:12px}}
    .stat-num{{font-size:28px;font-weight:bold}}
    .chart{{display:flex;align-items:end;gap:4px;height:80px;margin-top:10px}}
    .bar{{flex:1;background:#e5e7eb;border-radius:3px;min-width:20px}}
    .bar-dep{{background:#10b981}} .bar-rel{{background:#f59e0b}}
    input,select{{width:100%;padding:10px;margin:5px 0;box-sizing:border-box;border:1px solid #ddd;border-radius:6px}}
    button,.btn{{padding:9px 14px;background:#111827;color:white;border:none;border-radius:6px;text-decoration:none;display:inline-block;cursor:pointer;font-size:13px}}
    .btn-green{{background:#059669}} .btn-amber{{background:#d97706}}
    table{{width:100%;border-collapse:collapse;background:white}} th,td{{padding:8px;border:1px solid #e5e7eb;font-size:13px;text-align:left}} th{{background:#f9fafb}}
    </style></head><body>
    <div class="header">
    <div><b>{h_name}</b></div>
    <div>
    <a href='/dashboard' class='{"active" if title=="Dashboard" else ""}'>Dashboard</a>
    <a href='/records' class='{"active" if title=="Records" else ""}'>Records</a>
    <a href='/deposit' class='{"active" if title=="Deposit" else ""}'>+ Deposit</a>
    <a href='/audit' class='{"active" if title=="Audit" else ""}'>Audit log</a>
    <a href='/users' class='{"active" if title=="Users" else ""}'>Users</a>
    <a href='/export'>Export CSV</a>
    <a href='/settings'>Settings</a>
    <span style="margin-left:10px">{uname} | <a href='/logout'>Logout</a></span>
    </div></div>
    <div class="container">{body}</div></body></html>
    """

@app.route('/')
def index():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    msg=""
    if request.method=='POST':
        u=request.form.get('username','').strip()
        p=request.form.get('password','')
        user=User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password_hash, p):
            login_user(user)
            log_action(f"Login", "")
            return redirect(url_for('dashboard'))
        msg='<div style="background:#fee2e2;color:#dc2626;padding:10px;border-radius:6px">Invalid login</div>'
    body=f"""{msg}<div class='card' style='max-width:400px;margin:60px auto'>
    <h2>{get_hospital_name()} - Login</h2>
    <form method='POST'><input name='username' placeholder='Username' required><input name='password' type='password' placeholder='Password' required><button style='width:100%;margin-top:10px'>Login</button></form>
    </div>"""
    return layout("Login", body)

@app.route('/dashboard')
@login_required
def dashboard():
    total = Deceased.query.filter_by(status='In Storage').count()
    occ = (total / CAPACITY * 100) if CAPACITY else 0
    now = datetime.utcnow()
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    dep_month = Deceased.query.filter(Deceased.date_admitted >= first_day).count()
    rel_month = Deceased.query.filter(Deceased.date_released != None, Deceased.date_released >= first_day).count()
    days = []
    for i in range(13, -1, -1):
        d = now - timedelta(days=i)
        day_start = d.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = d.replace(hour=23, minute=59, second=59)
        dep = Deceased.query.filter(Deceased.date_admitted >= day_start, Deceased.date_admitted <= day_end).count()
        rel = Deceased.query.filter(Deceased.date_released != None, Deceased.date_released >= day_start, Deceased.date_released <= day_end).count()
        days.append((d.strftime("%m-%d"), dep, rel))
    max_val = max([max(dep, rel) for _, dep, rel in days] + [1])
    chart_html = '<div class="chart">'
    for date_str, dep, rel in days:
        dep_h = int((dep / max_val) * 70) if max_val else 2
        rel_h = int((rel / max_val) * 70) if max_val else 2
        chart_html += f'<div style="flex:1;text-align:center"><div style="display:flex;gap:2px;justify-content:center;align-items:end;height:70px"><div class="bar bar-dep" style="height:{dep_h}px;width:8px" title="{dep} deposited"></div><div class="bar bar-rel" style="height:{rel_h}px;width:8px" title="{rel} released"></div></div><div style="font-size:10px;margin-top:4px">{date_str}</div></div>'
    chart_html += '</div>'
    longest = Deceased.query.filter_by(status='In Storage').order_by(Deceased.date_admitted.asc()).first()
    longest_html = "No bodies in store." if not longest else f"<b>{longest.tag_number} - {longest.name}</b> - {(now - longest.date_admitted).days} days - Location: {longest.location or '-'}"
    body = f"""
    <div class="grid3">
    <div class="card"><div class="stat-num">{total} / {CAPACITY}</div><div style="font-size:12px;color:#6b7280">Currently stored ({occ:.2f}% occupancy)</div></div>
    <div class="card"><div class="stat-num">{dep_month}</div><div style="font-size:12px;color:#6b7280">Deposited this month</div></div>
    <div class="card"><div class="stat-num">{rel_month}</div><div style="font-size:12px;color:#6b7280">Released this month</div></div>
    </div>
    <div class="card"><b>Last 14 days (green=deposited, amber=released)</b>{chart_html}</div>
    <div class="card"><b>Longest in store</b><div style="margin-top:8px;font-size:13px">{longest_html}</div></div>
    """
    return layout("Dashboard", body)

@app.route('/records')
@login_required
def records():
    q=request.args.get('q','').strip()
    if q:
        items=Deceased.query.filter((Deceased.name.contains(q)) | (Deceased.tag_number.contains(q))).order_by(Deceased.date_admitted.desc()).all()
    else:
        items=Deceased.query.order_by(Deceased.date_admitted.desc()).all()
    rows=""
    for i in items:
        rel_btn = f"<a href='/release/{i.id}' class='btn btn-amber' onclick=\"return confirm('Release?')\">Release</a>" if i.status=='In Storage' else "Released"
        rows+=f"<tr><td>{i.tag_number}</td><td>{i.name}</td><td>{i.age or ''}</td><td>{i.gender or ''}</td><td>{i.date_admitted.strftime('%Y-%m-%d')}</td><td>{i.location or '-'}</td><td>{i.status}</td><td><a href='/edit/{i.id}'>Edit</a> | {rel_btn} | <a href='/delete/{i.id}' onclick=\"return confirm('Delete?')\">Del</a></td></tr>"
    body=f"""
    <div class="card"><form method='GET'><input name='q' placeholder='Search name or tag...' value='{q}'><button>Search</button> <a href='/records' class='btn'>Clear</a> <a href='/deposit' class='btn btn-green' style='float:right'>+ Deposit New Body</a></form></div>
    <div class="card"><table><tr><th>Auto Tag</th><th>Name</th><th>Age</th><th>Gender</th><th>Admitted</th><th>Location</th><th>Status</th><th>Action</th></tr>{rows if rows else '<tr><td colspan=8>No records - Click + Deposit</td></tr>'}</table></div>
    """
    return layout("Records", body)

@app.route('/deposit', methods=['GET','POST'])
@app.route('/add', methods=['GET','POST'])
@login_required
def deposit():
    auto_tag = generate_tag()
    if request.method=='POST':
        final_tag = generate_tag()
        d=Deceased(tag_number=final_tag, name=request.form['name'].strip(), age=int(request.form['age'] or 0) if request.form['age'] else None, gender=request.form['gender'], date_of_death=request.form['date_of_death'], cause_of_death=request.form['cause_of_death'], relatives_contact=request.form['relatives_contact'], location=request.form['location'], status='In Storage')
        db.session.add(d)
        db.session.commit()
        log_action(f"Deposited body", final_tag)
        return redirect(url_for('records'))
    body=f"""
    <div class='card'><h3>+ Deposit New Body</h3><p>Auto Tag: <b>{auto_tag}</b></p>
    <form method='POST'><input name='name' placeholder='Full Name' required><input name='age' type='number' placeholder='Age'><select name='gender'><option>Male</option><option>Female</option><option>Other</option></select><input name='date_of_death' type='date'><input name='cause_of_death' placeholder='Cause'><input name='relatives_contact' placeholder='Relatives Contact'><input name='location' placeholder='Fridge A3'><button class='btn-green'>Deposit - {auto_tag}</button></form></div>
    """
    return layout("Deposit", body)

@app.route('/release/<int:id>')
@login_required
def release_body(id):
    item=Deceased.query.get_or_404(id)
    item.status='Released'
    item.date_released=datetime.utcnow()
    db.session.commit()
    log_action(f"Released", item.tag_number)
    return redirect(url_for('records'))

@app.route('/edit/<int:id>', methods=['GET','POST'])
@login_required
def edit(id):
    item=Deceased.query.get_or_404(id)
    if request.method=='POST':
        item.name=request.form['name']
        item.age=int(request.form['age'] or 0) if request.form['age'] else None
        item.location=request.form['location']
        item.relatives_contact=request.form['relatives_contact']
        db.session.commit()
        log_action(f"Edited", item.tag_number)
        return redirect(url_for('records'))
    body=f"<div class='card'><h3>Edit {item.tag_number}</h3><form method='POST'><input name='name' value='{item.name}' required><input name='age' type='number' value='{item.age or ''}'><input name='location' value='{item.location or ''}'><input name='relatives_contact' value='{item.relatives_contact or ''}'><button>Update</button></form></div>"
    return layout("Edit", body)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    item=Deceased.query.get_or_404(id)
    tag=item.tag_number
    db.session.delete(item)
    db.session.commit()
    log_action(f"Deleted", tag)
    return redirect(url_for('records'))

@app.route('/audit')
@login_required
def audit():
    logs=AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
    rows="".join([f"<tr><td>{l.timestamp.strftime('%Y-%m-%d %H:%M')}</td><td>{l.user}</td><td>{l.action}</td><td>{l.tag_number}</td></tr>" for l in logs])
    body=f"<div class='card'><h3>Audit Log - Last 200</h3><table><tr><th>Time</th><th>User</th><th>Action</th><th>Tag</th></tr>{rows if rows else '<tr><td colspan=4>No logs</td></tr>'}</table></div>"
    return layout("Audit", body)

@app.route('/users', methods=['GET','POST'])
@login_required
def users_page():
    msg=""
    if request.method=='POST':
        u=request.form['username'].strip()
        p=request.form['password']
        if not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password_hash=generate_password_hash(p)))
            db.session.commit()
            msg=f"<div style='background:#d1fae5;padding:10px'>User {u} created</div>"
    users=User.query.all()
    rows="".join([f"<tr><td>{u.username}</td><td>{u.role}</td><td><a href='/users/delete/{u.id}'>Delete</a></td></tr>" for u in users])
    body=f"{msg}<div class='card'><h3>Users</h3><table><tr><th>Username</th><th>Role</th><th>Action</th></tr>{rows}</table></div><div class='card'><form method='POST'><input name='username' placeholder='New username' required><input name='password' type='password' placeholder='Password' required><button>Add User</button></form><p><a href='/change-password' class='btn'>Change My Password</a></p></div>"
    return layout("Users", body)

@app.route('/users/delete/<int:id>')
@login_required
def delete_user(id):
    if User.query.count() <=1:
        return "Cannot delete last user"
    u=User.query.get_or_404(id)
    if u.username==current_user.username:
        return "Cannot delete yourself"
    db.session.delete(u)
    db.session.commit()
    return redirect(url_for('users_page'))

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    s=Settings.query.first()
    if not s:
        s=Settings(hospital_name='Mortuary Tracking System')
        db.session.add(s)
        db.session.commit()
    msg=""
    if request.method=='POST':
        s.hospital_name=request.form['hospital_name'].strip()
        db.session.commit()
        msg="<div style='background:#d1fae5;padding:10px'>Hospital name updated!</div>"
    body=f"{msg}<div class='card'><h3>Hospital Settings</h3><form method='POST'><input name='hospital_name' value='{s.hospital_name}' required><button>Save</button></form></div>"
    return layout("Settings", body)

@app.route('/change-password', methods=['GET','POST'])
@login_required
def change_password():
    msg=""
    if request.method=='POST':
        old=request.form['old_password']
        new=request.form['new_password']
        confirm=request.form['confirm_password']
        if not check_password_hash(current_user.password_hash, old):
            msg="<div style='background:#fee2e2;padding:10px'>Old password wrong</div>"
        elif new!=confirm:
            msg="<div style='background:#fee2e2;padding:10px'>Passwords don't match</div>"
        else:
            current_user.password_hash=generate_password_hash(new)
            db.session.commit()
            msg="<div style='background:#d1fae5;padding:10px'>Password changed!</div>"
    body=f"{msg}<div class='card' style='max-width:500px'><h3>Change Password - {current_user.username}</h3><form method='POST'><input name='old_password' type='password' placeholder='Old' required><input name='new_password' type='password' placeholder='New' required><input name='confirm_password' type='password' placeholder='Confirm' required><button style='width:100%'>Change Password</button></form></div>"
    return layout("Password", body)

@app.route('/export')
@login_required
def export_csv():
    si=io.StringIO()
    cw=csv.writer(si)
    cw.writerow(['Tag','Name','Age','Gender','Admitted','Released','Location','Status'])
    for d in Deceased.query.all():
        cw.writerow([d.tag_number,d.name,d.age,d.gender,d.date_admitted,d.date_released,d.location,d.status])
    log_action("Exported CSV", "")
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=mortuary_export.csv"})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    if not Settings.query.first():
        db.session.add(Settings(hospital_name='Mortuary Tracking System'))
        db.session.commit()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password_hash=generate_password_hash('MOH-KBTH-2026!'), role='admin'))
        db.session.commit()

if __name__=='__main__':
    app.run()
