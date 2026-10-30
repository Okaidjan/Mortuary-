import re
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'moh-kbth-ultra-secure-2026-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mortuary.db'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

class Deceased(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_deposited = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(200))
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_action(action):
    try:
        log = AuditLog(user_id=current_user.id if current_user.is_authenticated else None, action=action, ip_address=request.remote_addr)
        db.session.add(log); db.session.commit()
    except: pass

def sanitize_input(text):
    if not text: return ""
    return re.sub(r"[^a-zA-Z0-9@.\- ]", "", text.strip())[:100]

@app.route('/')
def index():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/login', methods=['GET','POST'])
@limiter.limit("5 per 15 minutes")
def login():
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username'))
        password = request.form.get('password','')
        user = User.query.filter_by(username=username).first()
        if user and user.locked_until and user.locked_until > datetime.utcnow():
            flash('Account locked. Try again after 15 minutes.')
            return render_template('login.html')
        if user and check_password_hash(user.password_hash, password):
            user.failed_attempts = 0; user.locked_until = None; db.session.commit()
            login_user(user); log_action(f"Login success: {username}")
            return redirect(url_for('dashboard'))
        else:
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= 5: user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                db.session.commit()
            flash('Invalid username or password'); log_action(f"Failed login: {username}")
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    deceased_list = Deceased.query.all()
    return render_template('dashboard.html', deceased_list=deceased_list)

@app.route('/logout')
@login_required
def logout():
    log_action(f"Logout: {current_user.username}"); logout_user(); return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', password_hash=generate_password_hash('MOH-KBTH-2026!'))
        db.session.add(admin)
    else:
        admin.password_hash = generate_password_hash('MOH-KBTH-2026!')
        admin.failed_attempts = 0; admin.locked_until = None
    db.session.commit()

if __name__ == '__main__': app.run()
