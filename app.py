7import os
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
import re

app = Flask(__name__)

# SECURITY 1: Secret key from environment
secret = os.environ.get('SECRET_KEY')
if not secret:
    raise RuntimeError("SECRET_KEY not set in environment!")
app.config['SECRET_KEY'] = secret

# SECURITY 2: Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///mortuary.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SECURITY 3: Hardened session cookies
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# MODELS
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

class Deceased(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer)
    date_admitted = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def log_action(action):
    try:
        log = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass

def sanitize_input(text):
    if not text:
        return ""
    return re.sub(r'[<>"\']', '', text.strip())[:200]

# ROUTES
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per 15 minutes")
def login():
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username'))
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and user.locked_until and user.locked_until > datetime.utcnow():
            flash('Account locked. Try again after 15 minutes.')
            return render_template('login.html')

        if user and check_password_hash(user.password_hash, password):
            user.failed_attempts = 0
            user.locked_until = None
            db.session.commit()
            login_user(user)
            session.permanent = True
            log_action(f"Login success: {username}")
            return redirect(url_for('dashboard'))
        else:
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                db.session.commit()
            flash('Invalid username or password')
            log_action(f"Failed login: {username}")

    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    deceased_list = Deceased.query.all()
    return render_template('dashboard.html', deceased=deceased_list)

@app.route('/logout')
@login_required
def logout():
    log_action(f"Logout: {current_user.username}")
    logout_user()
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password_hash=generate_password_hash('MOH-KBTH-2026!')
        )
        db.session.add(admin)
    else:
        admin.password_hash = generate_password_hash('MOH-KBTH-2026!')
        admin.failed_attempts = 0
        admin.locked_until = None
    db.session.commit()

if __name__ == '__main__':
    app.run()
