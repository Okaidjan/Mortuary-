from flask import Flask, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

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
    return f"""
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
    body{{font-family:sans-serif;margin:0;padding:0;background:#f5f5f5}}
    .header{{background:#004d40;color:white;padding:15px}}
    .container{{padding:15px;max-width:1000px;margin:auto}}
    .card{{background:white;padding:15px;margin:10px 0;border-radius:8px;box-shadow:0 2px 4px #ccc}}
    input,select,textarea{{width:100%;padding:10px;margin:5px 0;box-sizing:border-box}}
    button,.btn{{padding:10px 15px;background:#004d40;color:white;border:none;border-radius:5px;text-decoration:none;display:inline-block}}
    table{{width:100%;border-collapse:collapse;background:white}}
    th,td{{padding:8px;border:1px solid #ddd;font-size:14px;text-align:left}}
    .alert{{padding:10px;background:#ffebee;color:#c62828;margin:10px 0}}
    .success{{padding:10px;background:#e8f5e9;color:#2e7d32;margin:10px 0}}
    </style></head>
    <body>
    <div class="header"><b>Korle-Bu Teaching Hospital Mortuary</b> 
    <span style="float:right"><a href="/dashboard" style="color:white">Dashboard</a> | 
    <a href="/add" style="color:white">Add</a> | <a href="/logout" style="color:white">Logout ({current_user.username if current_user.is_authenticated else ''})</a></span></div>
    <div class="container">{body}</div></body></html>
    """

@app.route('/')
def index():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/login', methods
