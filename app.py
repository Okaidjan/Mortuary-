import os
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

# --- SECURITY 1: STRONG SECRET KEY ---
# MUST set in Render Env, no weak fallback
secret = os.environ.get('SECRET_KEY')
if not secret:
    raise RuntimeError("SECRET_KEY not set in environment! Set strong key in Render Dashboard")
app.config['SECRET_KEY'] = secret

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///mortuary.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# SECURITY: Session harden
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

FACILITY_CODE = os.environ.get('FACILITY_CODE', 'MOH')
FACILITY_NAME = os.environ.get('FACILITY_NAME', 'General Hospital Mortuary')
CAPACITY = int(os.environ.get('CAPACITY', 100))
OVERDUE_DAYS = int(os.environ.get('OVERDUE_DAYS', 30))

# SECURITY 2: CSRF + Rate Limiter
csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.session_protection = "strong"

# MODELS
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='admin')
    failed_attempts = db.Column(db.Integer, default=0)
    last_failed = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Body(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    serial_id = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer)
    sex = db.Column(db.String(10))
    date_of_death = db.Column(db.String(20))
    cause_of_death = db.Column(db.String(200))
    next_of_kin = db.Column(db.String(120))
    kin_phone = db.Column(db.String(30))
    tag_number = db.Column(db.String(50))
    slot_number = db.Column(db.Integer)
    status = db.Column(db.String(20), default='In Mortuary')
    date_admitted = db.Column(db.DateTime, default=datetime.utcnow)
    date_released = db.Column(db.DateTime, nullable=True)
    released_to = db.Column(db.String(120), nullable=True)
    released_to_id = db.Column(db.String(80), nullable=True)
    registered_by = db.Column(db.String(80))
    facility_code = db.Column(db.String(20), default=FACILITY_CODE)

# SECURITY 3: Audit Log
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(80))
    action = db.Column(db.String(200))
    details = db.Column(db.String(300))
    ip = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    facility_code = db.Column(db.String(20), default=FACILITY_CODE)

def log_action(action, details=""):
    try:
        log = AuditLog(
            user=current_user.username if current_user.is_authenticated else "SYSTEM",
            action=action,
            details=details,
            ip=request.remote_addr,
            facility_code=FACILITY_CODE
        )
        db.session.add(log)
        db.session.commit()
    except:
        pass

def sanitize_input(text, max_len=120):
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r'[<>"\'`;]', '', text)  # Remove XSS chars
    return text[:max_len]

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

@app.before_request
def make_session_permanent():
    app.permanent_session_lifetime = timedelta(minutes=30)

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username'), 80)
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        
        # Brute force check
        if user and user.failed_attempts >= 5 and user.last_failed and datetime.utcnow() < user.last_failed + timedelta(minutes=15):
            flash('Account locked for 15 minutes due to failed attempts', 'danger')
            log_action("LOGIN_BLOCKED", f"Blocked user {username} from {request.remote_addr}")
            return render_template('login.html')
        
        if user and check_password_hash(user.password, password):
            user.failed_attempts = 0
            db.session.commit()
            login_user(user, duration=timedelta(minutes=30))
            log_action("LOGIN_SUCCESS", f"User {username} logged in")
            return redirect(url_for('dashboard'))
        else:
            if user:
                user.failed_attempts += 1
                user.last_failed = datetime.utcnow()
                db.session.commit()
            log_action("LOGIN_FAILED", f"Failed login for {username} from {request.remote_addr}")
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    log_action("LOGOUT", f"User {current_user.username} logged out")
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    total = Body.query.filter_by(facility_code=FACILITY_CODE).count()
    in_mortuary = Body.query.filter_by(facility_code=FACILITY_CODE, status='In Mortuary').count()
    released = Body.query.filter_by(facility_code=FACILITY_CODE, status='Released').count()
    available = CAPACITY - in_mortuary
    overdue_date = datetime.utcnow() - timedelta(days=OVERDUE_DAYS)
    overdue = Body.query.filter(Body.facility_code==FACILITY_CODE, Body.status=='In Mortuary', Body.date_admitted < overdue_date).count()
    recent = Body.query.filter_by(facility_code=FACILITY_CODE).order_by(Body.date_admitted.desc()).limit(10).all()
    return render_template('dashboard.html', total=total, in_mortuary=in_mortuary, released=released, available=available, capacity=CAPACITY, overdue=overdue, recent=recent, facility_name=FACILITY_NAME, facility_code=FACILITY_CODE)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_body():
    if request.method == 'POST':
        count = Body.query.filter_by(facility_code=FACILITY_CODE).count() + 1
        year = datetime.utcnow().year
        serial_id = f"{FACILITY_CODE}-{year}-{count:06d}"
        used_slots = [b.slot_number for b in Body.query.filter_by(facility_code=FACILITY_CODE, status='In Mortuary').all() if b.slot_number]
        free_slot = None
        for i in range(1, CAPACITY+1):
            if i not in used_slots:
                free_slot = i
                break
        if not free_slot:
            
