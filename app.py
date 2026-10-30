from flask import Flask, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'moh-kbth-2026-final-secure'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mortuary.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

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

def layout(title, body):
    uname = current_user.username if current_user.is_authenticated else ''
    return f"""
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
    body{{font-family:sans-serif;margin:0;background:#f5f5f5}}
    .header{{background:#004d40;color:white;padding:15px}}
    .container{{padding:15px;max-width:1000px;margin:auto}}
    .card{{background:white;padding:15px;margin:10px 0;border-radius:8px}}
    input,select{{width:100%;padding:10px;margin:5px 0}}
    button,.btn{{padding:10px 15px;background:#004d40;color:white;border:none;border-radius:5px;text-decoration:none;display:inline-block}}
    table{{width:100%;border-collapse:collapse;background:white}} th,td{{padding:8px;border:1px solid #ddd;font-size:13px}}
    </style></head><body>
    <div class="header"><b>Korle-Bu Mortuary</b> 
    <span style="float:right"><a href='/dashboard' style='color:white'>Dashboard</a> | <a href='/add' style='color:white'>Add</a> | <a href='/logout' style='color:white'>Logout {uname}</a></span></div>
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
        msg='<div style="color:red;padding:10px">Invalid login</div>'
    body=f"{msg}<div class='card' style='max-width:400px;margin:40px auto'><h2>MOH Login</h2><form method='POST'><input name='username' value='admin' required><input name='password' type='password' required><button style='width:100%'>Login</button></form><p><small>admin / MOH-KBTH-2026!</small></p></div>"
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
        rows+=f"<tr><td>{i.tag_number}</td><td>{i.name}</td><td>{i.age}</td><td>{i.gender}</td><td>{i.date_admitted.strftime('%Y-%m-%d')}</td><td>{i.location or '-'}</td><td>{i.status}</td><td><a href='/edit/{i.id}'>Edit</a> | <a href='/delete/{i.id}'>Del</a></td></tr>"
    body=f"""
    <div class='card'><h3>Total: {len(items)} / 100000 | Expired: {len(expired)}</h3>
    <form method='GET'><input name='q' placeholder='Search name or tag...' value='{q}'><button>Search</button> <a href='/dashboard' class='btn'>Clear</a></form></div>
    <div class='card'><table><tr><th>Tag</th><th>Name</th><th>Age</th><th>Gender</th><th>Admitted</th><th>Location</th><th>Status</th><th>Action</th></tr>{rows if rows else '<tr><td colspan=8>No records - Click Add</td></tr>'}</table></div>
    """
    return layout("Dashboard", body)

@app.route('/add', methods=['GET','POST'])
@login_required
def add():
    if request.method=='POST':
        try:
            d=Deceased(tag_number=request.form['tag_number'].strip().upper(), name=request.form['name'].strip(), age=int(request.form['age'] or 0), gender=request.form['gender'], date_of_death=request.form['date_of_death'], cause_of_death=request.form['cause_of_death'], relatives_contact=request.form['relatives_contact'], location=request.form['location'], status=request.form['status'])
            db.session.add(d)
            db.session.commit()
            return redirect(url_for('dashboard'))
        except Exception as e:
            body=f"<div style='color:red'>Error: {e} - Tag must be unique</div><a href='/add'>Back</a>"
            return layout("Add", body)
    body="""
    <div class='card'><h3>Add Deceased Record</h3>
    <form method='POST'>
    <input name='tag_number' placeholder='Tag Number e.g. KBTH-2026-001' required>
    <input name='name' placeholder='Full Name' required>
    <input name='age' type='number' placeholder='Age'>
    <select name='gender'><option>Male</option><option>Female</option><option>Other</option></select>
    <input name='date_of_death' type='date'>
    <input name='cause_of_death' placeholder='Cause of Death'>
    <input name='relatives_contact' placeholder='Relatives Contact'>
    <input name='location' placeholder='Storage Location e.g. Fridge A3'>
    <select name='status'><option>In Storage</option><option>Released</option><option>Pending</option></select>
    <button type='submit'>Save Record</button>
    </form></div>
    """
    return layout("Add", body)

@app.route('/edit/<int:id>', methods=['GET','POST'])
@login_required
def edit(id):
    item=Deceased.query.get_or_404(id)
    if request.method=='POST':
        item.name=request.form['name']
        item.age=int(request.form['age'] or 0)
        item.status=request.form['status']
        item.location=request.form['location']
        item.relatives_contact=request.form['relatives_contact']
        db.session.commit()
        return redirect(url_for('dashboard'))
    body=f"""
    <div class='card'><h3>Edit {item.tag_number}</h3>
    <form method='POST'>
    <input name='name' value='{item.name}' required>
    <input name='age' type='number' value='{item.age}'>
    <input name='location' value='{item.location or ""}' placeholder='Location'>
    <input name='relatives_contact' value='{item.relatives_contact or ""}' placeholder='Contact'>
    <select name='status'><option>In Storage</option><option>Released</option><option>Pending</option></select>
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

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    admin=User.query.filter_by(username='admin').first()
    if not admin:
        admin=User(username='admin', password_hash=generate_password_hash('MOH-KBTH-2026!'))
        db.session.add(admin)
        db.session.commit()
    else:
        admin.password_hash=generate_password_hash('MOH-KBTH-2026!')
        db.session.commit()

if __name__=='__main__':
    app.run()
