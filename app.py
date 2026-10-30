from flask import Flask, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'moh-general-2026-secure-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mortuary.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_name = db.Column(db.String(200), default='General Hospital Mortuary System')

class Deceased(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tag_number = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    date_of_death = db.Column(db.String(20))
    date_admitted = db.Column(db.DateTime, default=datetime.utcnow)
    cause_of_death = db.Column(db.String(200))
    relatives_contact = db.Column(db.String(100))
    status = db.Column(db.String(20), default='In Storage')
    location = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_hospital_name():
    s = Settings.query.first()
    return s.hospital_name if s else 'General Hospital Mortuary System'

def generate_tag():
    year = datetime.utcnow().year
    count = Deceased.query.count() + 1
    # Format: MORT-2026-0001, MORT-2026-0002 etc - auto increment
    return f"MORT-{year}-{count:05d}"

def layout(title, body):
    h_name = get_hospital_name()
    uname = current_user.username if current_user.is_authenticated else ''
    return f"""
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} - {h_name}</title>
    <style>
    body{{font-family:sans-serif;margin:0;background:#f5f5f5}}
    .header{{background:#004d40;color:white;padding:15px}}
    .container{{padding:15px;max-width:1000px;margin:auto}}
    .card{{background:white;padding:15px;margin:10px 0;border-radius:8px;box-shadow:0 1px 3px #ccc}}
    input,select{{width:100%;padding:10px;margin:5px 0;box-sizing:border-box}}
    button,.btn{{padding:10px 15px;background:#004d40;color:white;border:none;border-radius:5px;text-decoration:none;display:inline-block;cursor:pointer}}
    table{{width:100%;border-collapse:collapse;background:white}} th,td{{padding:8px;border:1px solid #ddd;font-size:13px;text-align:left}}
    .alert{{padding:10px;background:#ffebee;color:#c62828;margin:10px 0;border-radius:5px}}
    .success{{padding:10px;background:#e8f5e9;color:#2e7d32;margin:10px 0;border-radius:5px}}
    </style></head><body>
    <div class="header"><b>{h_name}</b> 
    <span style="float:right;font-size:13px"><a href='/dashboard' style='color:white'>Dashboard</a> | <a href='/add' style='color:white'>Add Body</a> | <a href='/settings' style='color:white'>Settings</a> | <a href='/change-password' style='color:white'>Password</a> | <a href='/logout' style='color:white'>Logout {uname}</a></span></div>
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
            return redirect(url_for('dashboard'))
        msg='<div class="alert">Invalid username or password</div>'
    # NO CREDENTIALS SHOWN HERE - FIXED
    body=f"""{msg}<div class='card' style='max-width:400px;margin:60px auto'>
    <h2>{get_hospital_name()} - Login</h2>
    <form method='POST'>
    <label>Username</label><input name='username' placeholder='Enter username' required>
    <label>Password</label><input name='password' type='password' placeholder='Enter password' required>
    <button style='width:100%;margin-top:10px'>Login</button>
    </form>
    </div>"""
    return layout("Login", body)

@app.route('/dashboard')
@login_required
def dashboard():
    q=request.args.get('q','').strip()
    if q:
        items=Deceased.query.filter((Deceased.name.contains(q)) | (Deceased.tag_number.contains(q))).all()
    else:
        items=Deceased.query.order_by(Deceased.date_admitted.desc()).all()
    expired=[i for i in items if (datetime.utcnow()-i.date_admitted).days>21]
    rows=""
    for i in items:
        rows+=f"<tr><td>{i.tag_number}</td><td>{i.name}</td><td>{i.age or ''}</td><td>{i.gender or ''}</td><td>{i.date_admitted.strftime('%Y-%m-%d')}</td><td>{i.location or '-'}</td><td>{i.status}</td><td><a href='/edit/{i.id}'>Edit</a> | <a href='/delete/{i.id}' onclick=\"return confirm('Delete?')\">Del</a></td></tr>"
    alert = f"<div class='alert'>⚠️ {len(expired)} bodies over 21 days - Action required per MOH policy!</div>" if expired else ""
    body=f"""
    <div class='card'><h3>Total: {len(items)} / 100000 | Expired: {len(expired)}</h3>
    <form method='GET'><input name='q' placeholder='Search by name or auto tag...' value='{q}'><button>Search</button> <a href='/dashboard' class='btn'>Clear</a></form></div>
    {alert}
    <div class='card'><table><tr><th>Auto Tag</th><th>Name</th><th>Age</th><th>Gender</th><th>Admitted</th><th>Location</th><th>Status</th><th>Action</th></tr>{rows if rows else '<tr><td colspan=8>No records yet - Click Add Body (tag auto-generated)</td></tr>'}</table></div>
    """
    return layout("Dashboard", body)

@app.route('/add', methods=['GET','POST'])
@login_required
def add():
    # AUTO GENERATE TAG - user doesn't enter it
    auto_tag = generate_tag()
    if request.method=='POST':
        try:
            # Generate fresh tag at save time to avoid race
            final_tag = generate_tag()
            d=Deceased(tag_number=final_tag, name=request.form['name'].strip(), age=int(request.form['age'] or 0) if request.form['age'] else None, gender=request.form['gender'], date_of_death=request.form['date_of_death'], cause_of_death=request.form['cause_of_death'], relatives_contact=request.form['relatives_contact'], location=request.form['location'], status=request.form['status'])
            db.session.add(d)
            db.session.commit()
            return redirect(url_for('dashboard'))
        except Exception as e:
            body=f"<div class='alert'>Error: {e}</div><a href='/add' class='btn'>Back</a>"
            return layout("Add", body)
    
    body=f"""
    <div class='card'><h3>Add New Body - Tag Auto-Generated</h3>
    <p><b>Next Tag will be: {auto_tag}</b> (auto assigned on save)</p>
    <form method='POST'>
    <label>Full Name *</label><input name='name' placeholder='Full Name' required>
    <label>Age</label><input name='age' type='number' placeholder='Age'>
    <label>Gender</label><select name='gender'><option>Male</option><option>Female</option><option>Other</option></select>
    <label>Date of Death</label><input name='date_of_death' type='date'>
    <label>Cause of Death</label><input name='cause_of_death' placeholder='Cause of Death'>
    <label>Relatives Contact</label><input name='relatives_contact' placeholder='Phone / Contact'>
    <label>Storage Location</label><input name='location' placeholder='e.g. Fridge A3, Shelf 2'>
    <label>Status</label><select name='status'><option>In Storage</option><option>Released</option><option>Pending Release</option></select>
    <button type='submit'>Save - Auto Tag Assigned</button>
    </form></div>
    """
    return layout("Add", body)

@app.route('/edit/<int:id>', methods=['GET','POST'])
@login_required
def edit(id):
    item=Deceased.query.get_or_404(id)
    if request.method=='POST':
        item.name=request.form['name']
        item.age=int(request.form['age'] or 0) if request.form['age'] else None
        item.status=request.form['status']
        item.location=request.form['location']
        item.relatives_contact=request.form['relatives_contact']
        item.cause_of_death=request.form['cause_of_death']
        db.session.commit()
        return redirect(url_for('dashboard'))
    body=f"""
    <div class='card'><h3>Edit {item.tag_number} - {item.name}</h3>
    <p>Tag: <b>{item.tag_number}</b> (cannot be changed)</p>
    <form method='POST'>
    <input name='name' value='{item.name}' required>
    <input name='age' type='number' value='{item.age or ""}'>
    <input name='location' value='{item.location or ""}' placeholder='Location'>
    <input name='relatives_contact' value='{item.relatives_contact or ""}' placeholder='Contact'>
    <input name='cause_of_death' value='{item.cause_of_death or ""}' placeholder='Cause'>
    <select name='status'><option {"selected" if item.status=="In Storage" else ""}>In Storage</option><option>Released</option><option>Pending Release</option></select>
    <button type='submit'>Update</button>
    </form></div>
    """
    return layout("Edit", body)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    item=Deceased.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    s = Settings.query.first()
    if not s:
        s = Settings(hospital_name='General Hospital Mortuary System')
        db.session.add(s)
        db.session.commit()
    msg=""
    if request.method=='POST':
        s.hospital_name = request.form['hospital_name'].strip()
        db.session.commit()
        msg="<div class='success'>Hospital name updated!</div>"
    body=f"""
    {msg}
    <div class='card'><h3>Hospital Settings</h3>
    <p>Set your hospital name - this will appear on header and login page.</p>
    <form method='POST'>
    <label>Hospital Name</label><input name='hospital_name' value="{s.hospital_name}" required placeholder="e.g. Komfo Anokye Teaching Hospital">
    <button type='submit'>Save Hospital Name</button>
    </form></div>
    <div class='card'><p><b>Current Tags format:</b> MORT-YYYY-XXXXX (auto). Example: MORT-2026-00001</p><p>You can change hospital name anytime. Each hospital can set its own.</p></div>
    """
    return layout("Settings", body)

@app.route('/change-password', methods=['GET','POST'])
@login_required
def change_password():
    msg=""
    if request.method=='POST':
        old = request.form['old_password']
        new = request.form['new_password']
        confirm = request.form['confirm_password']
        if not check_password_hash(current_user.password_hash, old):
            msg="<div class='alert'>Old password is incorrect</div>"
        elif new != confirm:
            msg="<div class='alert'>New passwords do not match</div>"
        elif len(new) < 6:
            msg="<div class='alert'>Password must be at least 6 characters</div>"
        else:
            current_user.password_hash = generate_password_hash(new)
            db.session.commit()
            msg="<div class='success'>Password changed successfully! Use new password next login.</div>"
    body=f"""
    {msg}
    <div class='card' style='max-width:500px;margin:auto'><h3>Change Password - {current_user.username}</h3>
    <form method='POST'>
    <label>Old Password</label><input name='old_password' type='password' required>
    <label>New Password</label><input name='new_password' type='password' required>
    <label>Confirm New Password</label><input name='confirm_password' type='password' required>
    <button type='submit' style='width:100%'>Change Password</button>
    </form></div>
    """
    return layout("Change Password", body)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    if not Settings.query.first():
        db.session.add(Settings(hospital_name='General Hospital Mortuary System'))
        db.session.commit()
    admin=User.query.filter_by(username='admin').first()
    if not admin:
        admin=User(username='admin', password_hash=generate_password_hash('MOH-KBTH-2026!'))
        db.session.add(admin)
        db.session.commit()

if __name__=='__main__':
    app.run()
