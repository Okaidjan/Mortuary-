from flask import Flask, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'moh-kbth-2026-final'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mortuary.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Deceased(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def login_page(msg=""):
    return f"""
    <html><body style="font-family:sans-serif; padding:40px; max-width:400px; margin:auto">
    <h2>KBTH Mortuary Login</h2>
    <p style="color:red">{msg}</p>
    <form method="POST">
    <input name="username" placeholder="Username" value="admin" style="width:100%;padding:10px;margin:5px 0"><br>
    <input name="password" type="password" placeholder="Password" style="width:100%;padding:10px;margin:5px 0"><br>
    <button type="submit" style="width:100%;padding:10px;background:#004d40;color:white">Login</button>
    </form></body></html>
    """

@app.route('/')
def index():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','')
        user = User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password_hash, p):
            login_user(user)
            return redirect(url_for('dashboard'))
        return login_page("Invalid username or password")
    return login_page()

@app.route('/dashboard')
@login_required
def dashboard():
    items = Deceased.query.all()
    return f"""
    <html><body style="font-family:sans-serif; padding:20px">
    <h2>Korle-Bu Mortuary Dashboard</h2>
    <p>Logged in as {current_user.username} | <a href="/logout">Logout</a></p>
    <h3>Total: {len(items)} / 100000</h3>
    <p>✅ System is LIVE for MOH Ghana</p>
    </body></html>
    """

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', password_hash=generate_password_hash('MOH-KBTH-2026!'))
        db.session.add(admin)
        db.session.commit()
    else:
        admin.password_hash = generate_password_hash('MOH-KBTH-2026!')
        db.session.commit()

if __name__ == '__main__':
    app.run()
