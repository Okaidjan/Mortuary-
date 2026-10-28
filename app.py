"""Mortuary Tracking System - deposits, releases, serial IDs, audit trail, efficiency dashboard.

Run:   python app.py create-admin     (once, creates first admin)
       python app.py                   (starts server on http://127.0.0.1:5000)
"""
import csv
import getpass
import io
import os
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("MORTUARY_DB", os.path.join(BASE, "instance", "mortuary.db"))
FACILITY_CODE = os.environ.get("FACILITY_CODE", "MOR")      # e.g. KBTH, KATH, KORLE
FACILITY_NAME = os.environ.get("FACILITY_NAME", "Mortuary Tracking System")
  CAPACITY = int(os.environ.get("CAPACITY", "100000"))        # number of storage slots
OVERDUE_DAYS = int(os.environ.get("OVERDUE_DAYS", "30"))     # flag bodies stored longer than this
MAX_FAILED = 5
LOCK_MINUTES = 15
SESSION_MINUTES = 15
ROLES = ("admin", "attendant", "viewer")
CASE_TYPES = ("Natural death", "Accident / RTA", "Police / coroner case", "Unidentified", "Other")
ID_TYPES = ("Ghana Card", "Voter ID", "Passport", "Driver's licence", "Police / official ID", "Other")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until TEXT);
CREATE TABLE IF NOT EXISTS bodies(
  id INTEGER PRIMARY KEY, serial_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  sex TEXT, age TEXT, case_type TEXT, date_of_death TEXT, source TEXT,
  next_of_kin TEXT, kin_phone TEXT, slot TEXT, notes TEXT,
  status TEXT NOT NULL DEFAULT 'IN_STORE',
  deposited_at TEXT NOT NULL, deposited_by TEXT NOT NULL,
  released_at TEXT, released_by TEXT, released_to TEXT, collector_relationship TEXT,
  collector_id_type TEXT, collector_id_no TEXT, collector_phone TEXT, release_doc_no TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_body_per_slot ON bodies(slot)
  WHERE status='IN_STORE' AND slot IS NOT NULL AND slot != '';
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, user TEXT, action TEXT NOT NULL,
  serial_id TEXT, detail TEXT, ip TEXT);
"""

app = Flask(__name__)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _secret():
    p = os.path.join(os.path.dirname(DB_PATH), "secret.key")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(p, 0o600)
    return open(p).read().strip()


app.secret_key = _secret()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("HTTPS", "0") == "1",  # set HTTPS=1 behind TLS
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=SESSION_MINUTES))


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")  # Ghana = UTC+0


def parse(ts):
    return datetime.strptime(ts, "%Y-%m-%d %H:%M")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d:
        d.close()


def init_db():
    c = sqlite3.connect(DB_PATH)
    c.executescript(SCHEMA)
    c.commit()
    c.close()


def log(action, serial=None, detail=""):
    db().execute("INSERT INTO audit(ts,user,action,serial_id,detail,ip) VALUES(?,?,?,?,?,?)",
                 (now(), session.get("user"), action, serial, detail, request.remote_addr))


# ---------- security ----------
def csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf"] = csrf


@app.before_request
def protect():
    session.permanent = True  # sliding 15-min inactivity timeout
    if request.method == "POST":
        if not secrets.compare_digest(request.form.get("csrf", ""), session.get("csrf", "x")):
            abort(400, "Invalid form token. Reload the page and try again.")


@app.after_request
def headers(r):
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Cache-Control"] = "no-store"
    r.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    return r


def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrap(*a, **kw):
            if "user" not in session:
                return redirect(url_for("login"))
            if roles and session.get("role") not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrap
    return deco


def valid_password(p):
    return len(p) >= 10 and any(c.isdigit() for c in p) and any(c.isalpha() for c in p)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip().lower()
        pw = request.form.get("password", "")
        row = db().execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        msg = "Invalid username or password."
        if row and row["locked_until"] and parse(row["locked_until"]) > datetime.now(timezone.utc).replace(tzinfo=None):
            msg = f"Account locked. Try again after {row['locked_until']} UTC or ask an admin."
        elif row and row["active"] and check_password_hash(row["password_hash"], pw):
            db().execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=?", (row["id"],))
            session.clear()
            session.update(user=row["username"], role=row["role"], name=row["full_name"])
            log("LOGIN")
            db().commit()
            return redirect(url_for("dashboard"))
        else:
            if row:
                n = row["failed_attempts"] + 1
                lock = None
                if n >= MAX_FAILED:
                    lock = (datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M")
                    n = 0
                db().execute("UPDATE users SET failed_attempts=?, locked_until=? WHERE id=?", (n, lock, row["id"]))
            session["user"] = None
            session.pop("user")
            log("LOGIN_FAILED", detail=f"username={u[:40]}")
            db().commit()
        flash(msg, "err")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required()
def logout():
    log("LOGOUT")
    db().commit()
    session.clear()
    return redirect(url_for("login"))


# ---------- dashboard ----------
@app.route("/")
@login_required()
def dashboard():
    d = db()
    stored = d.execute("SELECT * FROM bodies WHERE status='IN_STORE' ORDER BY deposited_at").fetchall()
    released = d.execute("SELECT deposited_at, released_at FROM bodies WHERE status='RELEASED'").fetchall()
    stays = sorted((parse(r["released_at"]) - parse(r["deposited_at"])).total_seconds() / 86400 for r in released)
    avg = sum(stays) / len(stays) if stays else 0
    med = stays[len(stays) // 2] if stays else 0
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=OVERDUE_DAYS)
    overdue = [r for r in stored if parse(r["deposited_at"]) <= cutoff]
    days = [(datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    dep = {r[0]: r[1] for r in d.execute("SELECT substr(deposited_at,1,10), COUNT(*) FROM bodies GROUP BY 1")}
    rel = {r[0]: r[1] for r in d.execute("SELECT substr(released_at,1,10), COUNT(*) FROM bodies WHERE released_at IS NOT NULL GROUP BY 1")}
    series = [(x[5:], dep.get(x, 0), rel.get(x, 0)) for x in days]
    peak = max([1] + [max(a, b) for _, a, b in series])
    m = datetime.now(timezone.utc).strftime("%Y-%m")
    month_in = d.execute("SELECT COUNT(*) FROM bodies WHERE deposited_at LIKE ?", (m + "%",)).fetchone()[0]
    month_out = d.execute("SELECT COUNT(*) FROM bodies WHERE released_at LIKE ?", (m + "%",)).fetchone()[0]
    total = d.execute("SELECT COUNT(*) FROM bodies").fetchone()[0]
    by_case = d.execute("SELECT case_type, COUNT(*) c FROM bodies GROUP BY 1 ORDER BY c DESC").fetchall()
    oldest = [(r, int((datetime.now(timezone.utc).replace(tzinfo=None) - parse(r["deposited_at"])).total_seconds() // 86400)) for r in stored[:8]]
    return render_template("dashboard.html", stored=len(stored), capacity=CAPACITY,
                           occ=round(100 * len(stored) / CAPACITY) if CAPACITY else 0, avg=avg, med=med,
                           overdue=overdue, overdue_days=OVERDUE_DAYS, series=series, peak=peak,
                           month_in=month_in, month_out=month_out, total=total, by_case=by_case,
                           released_n=len(stays), oldest=oldest)


# ---------- deposit ----------
def next_serial():
    year = datetime.now(timezone.utc).strftime("%Y")
    prefix = f"{FACILITY_CODE}-{year}-"
    n = db().execute("SELECT COUNT(*) FROM bodies WHERE serial_id LIKE ?", (prefix + "%",)).fetchone()[0]
    return f"{prefix}{n + 1:06d}"


@app.route("/deposit", methods=["GET", "POST"])
@login_required("admin", "attendant")
def deposit():
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in
             ("name", "sex", "age", "case_type", "date_of_death", "source", "next_of_kin", "kin_phone", "slot", "notes")}
        if f["case_type"] not in CASE_TYPES:
            f["case_type"] = "Other"
        if not f["name"]:
            f["name"] = "UNIDENTIFIED"
        if not f["source"]:
            flash("Source (hospital ward, police station, family, etc.) is required.", "err")
            return render_template("deposit.html", f=f, case_types=CASE_TYPES)
        try:
            serial = next_serial()
            db().execute(
                """INSERT INTO bodies(serial_id,name,sex,age,case_type,date_of_death,source,next_of_kin,kin_phone,slot,notes,
                   deposited_at,deposited_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (serial, f["name"], f["sex"], f["age"], f["case_type"], f["date_of_death"], f["source"],
                 f["next_of_kin"], f["kin_phone"], f["slot"], f["notes"], now(), session["user"]))
            log("DEPOSIT", serial, f"name={f['name']}; slot={f['slot']}; source={f['source']}")
            db().commit()
        except sqlite3.IntegrityError:
            db().rollback()
            flash(f"Storage slot '{f['slot']}' is already occupied.", "err")
            return render_template("deposit.html", f=f, case_types=CASE_TYPES)
        flash(f"Deposited. Serial ID: {serial}", "ok")
        return redirect(url_for("body", serial=serial))
    return render_template("deposit.html", f={}, case_types=CASE_TYPES)


# ---------- records ----------
@app.route("/bodies")
@login_required()
def bodies():
    q = request.args.get("q", "").strip()
    st = request.args.get("status", "")
    sql, args = "SELECT * FROM bodies WHERE 1=1", []
    if q:
        sql += " AND (serial_id LIKE ? OR name LIKE ? OR slot LIKE ? OR next_of_kin LIKE ?)"
        args += [f"%{q}%"] * 4
    if st in ("IN_STORE", "RELEASED"):
        sql += " AND status=?"
        args.append(st)
    rows = db().execute(sql + " ORDER BY id DESC LIMIT 300", args).fetchall()
    return render_template("bodies.html", rows=rows, q=q, st=st)


@app.route("/body/<serial>")
@login_required()
def body(serial):
    r = db().execute("SELECT * FROM bodies WHERE serial_id=?", (serial,)).fetchone()
    if not r:
        abort(404)
    trail = db().execute("SELECT * FROM audit WHERE serial_id=? ORDER BY id", (serial,)).fetchall()
    log("VIEW", serial)
    db().commit()
    return render_template("body.html", r=r, trail=trail)


@app.route("/release/<serial>", methods=["GET", "POST"])
@login_required("admin", "attendant")
def release(serial):
    r = db().execute("SELECT * FROM bodies WHERE serial_id=?", (serial,)).fetchone()
    if not r:
        abort(404)
    if r["status"] != "IN_STORE":
        flash("This body has already been released.", "err")
        return redirect(url_for("body", serial=serial))
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in
             ("released_to", "relationship", "id_type", "id_no", "phone", "doc_no")}
        confirm = request.form.get("confirm_serial", "").strip().upper()
        missing = [k for k in ("released_to", "relationship", "id_no", "doc_no") if not f[k]]
        if missing:
            flash("Collector name, relationship, ID number and release document number are required.", "err")
        elif confirm != serial.upper():
            flash("Serial ID confirmation does not match the body tag. Check the tag and retype it.", "err")
        else:
            cur = db().execute(
                """UPDATE bodies SET status='RELEASED', released_at=?, released_by=?, released_to=?, collector_relationship=?,
                   collector_id_type=?, collector_id_no=?, collector_phone=?, release_doc_no=?, slot=NULL
                   WHERE serial_id=? AND status='IN_STORE'""",
                (now(), session["user"], f["released_to"], f["relationship"], f["id_type"], f["id_no"],
                 f["phone"], f["doc_no"], serial))
            if cur.rowcount == 1:
                log("RELEASE", serial, f"to={f['released_to']}; id={f['id_type']} {f['id_no']}; doc={f['doc_no']}")
                db().commit()
                flash("Body released and recorded.", "ok")
                return redirect(url_for("body", serial=serial))
            db().rollback()
            flash("Body was already released.", "err")
        return render_template("release.html", r=r, f=f, id_types=ID_TYPES)
    return render_template("release.html", r=r, f={}, id_types=ID_TYPES)


# ---------- admin ----------
@app.route("/audit")
@login_required("admin")
def audit():
    rows = db().execute("SELECT * FROM audit ORDER BY id DESC LIMIT 500").fetchall()
    return render_template("audit.html", rows=rows)


@app.route("/users", methods=["GET", "POST"])
@login_required("admin")
def users():
    if request.method == "POST":
        act = request.form.get("act")
        if act == "add":
            u = request.form.get("username", "").strip().lower()
            n = request.form.get("full_name", "").strip()
            role = request.form.get("role")
            pw = request.form.get("password", "")
            if not (u and n) or role not in ROLES:
                flash("Username, full name and valid role are required.", "err")
            elif not valid_password(pw):
                flash("Password must be 10+ characters with letters and numbers.", "err")
            else:
                try:
                    db().execute("INSERT INTO users(username,full_name,password_hash,role) VALUES(?,?,?,?)",
                                 (u, n, generate_password_hash(pw), role))
                    log("USER_ADD", detail=f"{u} ({role})")
                    db().commit()
                    flash(f"User {u} created.", "ok")
                except sqlite3.IntegrityError:
                    flash("Username already exists.", "err")
        elif act in ("toggle", "unlock"):
            uid = int(request.form.get("uid", 0))
            row = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if row and act == "toggle" and row["username"] != session["user"]:
                db().execute("UPDATE users SET active=1-active WHERE id=?", (uid,))
                log("USER_TOGGLE", detail=row["username"])
            elif row and act == "unlock":
                db().execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=?", (uid,))
                log("USER_UNLOCK", detail=row["username"])
            db().commit()
        return redirect(url_for("users"))
    return render_template("users.html", rows=db().execute("SELECT * FROM users ORDER BY username").fetchall(), roles=ROLES)


@app.route("/export.csv")
@login_required("admin")
def export():
    rows = db().execute("SELECT * FROM bodies ORDER BY id").fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    if rows:
        w.writerow(rows[0].keys())
        for r in rows:
            w.writerow(["'" + str(v) if isinstance(v, str) and v[:1] in "=+-@" else v for v in tuple(r)])
    log("EXPORT_CSV")
    db().commit()
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=mortuary_records.csv"})


# ---------- templates ----------
CSS = """
*{box-sizing:border-box}body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#f4f5f7;color:#1c2330}
nav{background:#14323d;color:#fff;padding:10px 16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
nav a{color:#cfe6ee;text-decoration:none;font-size:14px}nav a:hover{color:#fff}nav b{margin-right:8px}
nav form{margin-left:auto;display:inline}nav button{background:none;border:1px solid #cfe6ee;color:#cfe6ee;border-radius:6px;padding:4px 10px;cursor:pointer}
main{max-width:1000px;margin:18px auto;padding:0 14px}
.card{background:#fff;border-radius:10px;padding:16px;margin-bottom:14px;box-shadow:0 1px 3px #0001}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi{background:#fff;border-radius:10px;padding:14px;box-shadow:0 1px 3px #0001}.kpi b{font-size:26px;display:block}.kpi span{font-size:12px;color:#5b6676}
label{display:block;font-size:13px;margin:10px 0 3px;color:#3a4556}
input,select,textarea{width:100%;padding:9px;border:1px solid #c5ccd6;border-radius:6px;font-size:15px}
button.p,a.btn{background:#0f766e;color:#fff;border:0;border-radius:6px;padding:10px 16px;font-size:15px;cursor:pointer;text-decoration:none;display:inline-block}
button.d{background:#b42318;color:#fff;border:0;border-radius:6px;padding:10px 16px;font-size:15px;cursor:pointer}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid #e5e8ee;vertical-align:top}
.flash{padding:10px 14px;border-radius:8px;margin-bottom:12px}.ok{background:#dcfce7}.err{background:#fee2e2}
.tag{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px}.in{background:#fef3c7}.out{background:#dcfce7}.warn{background:#fee2e2}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:0 14px}@media(max-width:640px){.cols{grid-template-columns:1fr}}
.bars{display:flex;gap:6px;align-items:flex-end;height:120px}.bars div{flex:1;text-align:center;font-size:10px}
.bars i{display:inline-block;width:42%;background:#0f766e}.bars em{display:inline-block;width:42%;background:#f59e0b}
.big{font-size:28px;letter-spacing:1px;font-weight:700}
@media print{nav,.noprint,.flash{display:none}body{background:#fff}.card{box-shadow:none}}
"""

BASE_T = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{{ fname }}</title><style>{{ css|safe }}</style></head><body>
{% if session.user %}<nav><b>{{ fname }}</b><a href="/">Dashboard</a><a href="/bodies">Records</a>
{% if session.role in ('admin','attendant') %}<a href="/deposit">+ Deposit</a>{% endif %}
{% if session.role=='admin' %}<a href="/audit">Audit log</a><a href="/users">Users</a><a href="/export.csv">Export CSV</a>{% endif %}
<form method=post action="/logout"><input type=hidden name=csrf value="{{ csrf() }}"><span style="font-size:13px;margin-right:8px">{{ session.name }} ({{ session.role }})</span><button>Log out</button></form></nav>{% endif %}
<main>{% for c,m in get_flashed_messages(with_categories=true) %}<div class="flash {{ c }}">{{ m }}</div>{% endfor %}
{% block body %}{% endblock %}</main></body></html>"""

T = {}
T["base.html"] = BASE_T
T["login.html"] = """{% extends 'base.html' %}{% block body %}<div class=card style="max-width:380px;margin:60px auto">
<h2>{{ fname }}</h2><p style="color:#5b6676;font-size:14px">Authorised staff only. All activity is logged.</p>
<form method=post><input type=hidden name=csrf value="{{ csrf() }}">
<label>Username</label><input name=username autocomplete=username required autofocus>
<label>Password</label><input type=password name=password autocomplete=current-password required>
<p><button class=p>Sign in</button></p></form></div>{% endblock %}"""
T["dashboard.html"] = """{% extends 'base.html' %}{% block body %}
<div class=grid>
<div class=kpi><b>{{ stored }} / {{ capacity }}</b><span>Currently stored ({{ occ }}% occupancy)</span></div>
<div class=kpi><b>{{ month_in }}</b><span>Deposited this month</span></div>
<div class=kpi><b>{{ month_out }}</b><span>Released this month</span></div>
<div class=kpi><b>{{ '%.1f'|format(avg) }} days</b><span>Average stay ({{ released_n }} released)</span></div>
<div class=kpi><b>{{ '%.1f'|format(med) }} days</b><span>Median stay</span></div>
<div class=kpi><b style="color:{{ '#b42318' if overdue else '#0f766e' }}">{{ overdue|length }}</b><span>Over {{ overdue_days }} days in store</span></div>
</div>
<div class=card style="margin-top:14px"><b>Last 14 days</b> <span style="font-size:12px;color:#5b6676">(green = deposited, amber = released)</span>
<div class=bars>{% for d,a,b in series %}<div title="{{ d }}: {{ a }} in, {{ b }} out"><i style="height:{{ (a/peak*100)|int }}px"></i><em style="height:{{ (b/peak*100)|int }}px"></em><br>{{ d }}</div>{% endfor %}</div></div>
<div class=cols><div class=card><b>Longest in store</b><table>{% for r,d in oldest %}<tr><td><a href="/body/{{ r.serial_id }}">{{ r.serial_id }}</a><br>{{ r.name }}</td><td>{{ d }} days {% if d>=overdue_days %}<span class="tag warn">overdue</span>{% endif %}</td></tr>{% else %}<tr><td>No bodies in store.</td></tr>{% endfor %}</table></div>
<div class=card><b>By case type ({{ total }} total)</b><table>{% for c in by_case %}<tr><td>{{ c.case_type }}</td><td>{{ c.c }}</td></tr>{% endfor %}</table></div></div>
{% endblock %}"""
T["deposit.html"] = """{% extends 'base.html' %}{% block body %}<div class=card><h2>Deposit a body</h2>
<p style="font-size:13px;color:#5b6676">A unique serial ID is generated on saving. Attach it to the body tag.</p>
<form method=post><input type=hidden name=csrf value="{{ csrf() }}"><div class=cols>
<div><label>Name of deceased (leave blank if unidentified)</label><input name=name value="{{ f.name or '' }}"></div>
<div><label>Case type</label><select name=case_type>{% for c in case_types %}<option {{ 'selected' if f.case_type==c }}>{{ c }}</option>{% endfor %}</select></div>
<div><label>Sex</label><select name=sex><option></option><option {{ 'selected' if f.sex=='Male' }}>Male</option><option {{ 'selected' if f.sex=='Female' }}>Female</option></select></div>
<div><label>Approximate age</label><input name=age value="{{ f.age or '' }}"></div>
<div><label>Date of death</label><input type=date name=date_of_death value="{{ f.date_of_death or '' }}"></div>
<div><label>Brought from (ward / police station / family) *</label><input name=source required value="{{ f.source or '' }}"></div>
<div><label>Next of kin</label><input name=next_of_kin value="{{ f.next_of_kin or '' }}"></div>
<div><label>Next of kin phone</label><input name=kin_phone value="{{ f.kin_phone or '' }}"></div>
<div><label>Storage slot / tray (e.g. A-12)</label><input name=slot value="{{ f.slot or '' }}"></div>
<div><label>Notes (belongings, condition)</label><input name=notes value="{{ f.notes or '' }}"></div></div>
<p><button class=p>Save and generate serial ID</button></p></form></div>{% endblock %}"""
T["bodies.html"] = """{% extends 'base.html' %}{% block body %}<div class=card>
<form method=get style="display:flex;gap:8px;flex-wrap:wrap"><input name=q value="{{ q }}" placeholder="Search serial, name, slot, next of kin" style="flex:1;min-width:200px">
<select name=status style="width:auto"><option value="">All</option><option value=IN_STORE {{ 'selected' if st=='IN_STORE' }}>In store</option><option value=RELEASED {{ 'selected' if st=='RELEASED' }}>Released</option></select><button class=p>Search</button></form></div>
<div class=card style="overflow-x:auto"><table><tr><th>Serial ID</th><th>Name</th><th>Slot</th><th>Deposited</th><th>Status</th></tr>
{% for r in rows %}<tr><td><a href="/body/{{ r.serial_id }}">{{ r.serial_id }}</a></td><td>{{ r.name }}</td><td>{{ r.slot or '-' }}</td><td>{{ r.deposited_at }}</td>
<td><span class="tag {{ 'in' if r.status=='IN_STORE' else 'out' }}">{{ 'In store' if r.status=='IN_STORE' else 'Released' }}</span></td></tr>{% else %}<tr><td colspan=5>No records.</td></tr>{% endfor %}</table></div>{% endblock %}"""
T["body.html"] = """{% extends 'base.html' %}{% block body %}<div class=card>
<div class=big>{{ r.serial_id }}</div><span class="tag {{ 'in' if r.status=='IN_STORE' else 'out' }}">{{ 'In store' if r.status=='IN_STORE' else 'Released' }}</span>
<table style="margin-top:10px">
<tr><th>Name</th><td>{{ r.name }}</td><th>Sex / age</th><td>{{ r.sex or '-' }} / {{ r.age or '-' }}</td></tr>
<tr><th>Case type</th><td>{{ r.case_type }}</td><th>Date of death</th><td>{{ r.date_of_death or '-' }}</td></tr>
<tr><th>Brought from</th><td>{{ r.source }}</td><th>Slot</th><td>{{ r.slot or '-' }}</td></tr>
<tr><th>Next of kin</th><td>{{ r.next_of_kin or '-' }} {{ r.kin_phone or '' }}</td><th>Notes</th><td>{{ r.notes or '-' }}</td></tr>
<tr><th>Deposited</th><td>{{ r.deposited_at }} UTC</td><th>Received by</th><td>{{ r.deposited_by }}</td></tr>
{% if r.status=='RELEASED' %}<tr><th>Released</th><td>{{ r.released_at }} UTC</td><th>Released by</th><td>{{ r.released_by }}</td></tr>
<tr><th>Released to</th><td>{{ r.released_to }} ({{ r.collector_relationship }})</td><th>Collector ID</th><td>{{ r.collector_id_type }} {{ r.collector_id_no }}<br>{{ r.collector_phone or '' }}</td></tr>
<tr><th>Release document</th><td colspan=3>{{ r.release_doc_no }}</td></tr>{% endif %}</table>
<p class=noprint><button class=p onclick="window.print()">Print tag</button>
{% if r.status=='IN_STORE' and session.role in ('admin','attendant') %} <a class=btn style="background:#b42318" href="/release/{{ r.serial_id }}">Release body</a>{% endif %}</p></div>
<div class=card><b>Movement and access history</b><table>{% for t in trail %}<tr><td>{{ t.ts }}</td><td>{{ t.user }}</td><td>{{ t.action }}</td><td>{{ t.detail }}</td></tr>{% endfor %}</table></div>{% endblock %}"""
T["release.html"] = """{% extends 'base.html' %}{% block body %}<div class=card><h2>Release {{ r.serial_id }}</h2>
<p><b>{{ r.name }}</b> - slot {{ r.slot or '-' }} - deposited {{ r.deposited_at }}</p>
<p style="font-size:13px;color:#5b6676">Check the collector's ID and the release document before saving. This cannot be undone.</p>
<form method=post><input type=hidden name=csrf value="{{ csrf() }}"><div class=cols>
<div><label>Collector full name *</label><input name=released_to required value="{{ f.released_to or '' }}"></div>
<div><label>Relationship to deceased *</label><input name=relationship required value="{{ f.relationship or '' }}"></div>
<div><label>ID type</label><select name=id_type>{% for t in id_types %}<option {{ 'selected' if f.id_type==t }}>{{ t }}</option>{% endfor %}</select></div>
<div><label>ID number *</label><input name=id_no required value="{{ f.id_no or '' }}"></div>
<div><label>Collector phone</label><input name=phone value="{{ f.phone or '' }}"></div>
<div><label>Release document no. (burial permit / death cert. / police release) *</label><input name=doc_no required value="{{ f.doc_no or '' }}"></div></div>
<label>Retype serial ID from the body tag to confirm *</label><input name=confirm_serial required autocomplete=off>
<p><button class=d>Confirm release</button></p></form></div>{% endblock %}"""
T["audit.html"] = """{% extends 'base.html' %}{% block body %}<div class=card style="overflow-x:auto"><h2>Audit log (latest 500)</h2><table><tr><th>Time (UTC)</th><th>User</th><th>Action</th><th>Serial</th><th>Detail</th><th>IP</th></tr>
{% for r in rows %}<tr><td>{{ r.ts }}</td><td>{{ r.user or '-' }}</td><td>{{ r.action }}</td><td>{{ r.serial_id or '' }}</td><td>{{ r.detail }}</td><td>{{ r.ip }}</td></tr>{% endfor %}</table></div>{% endblock %}"""
T["users.html"] = """{% extends 'base.html' %}{% block body %}<div class=card><h2>Staff accounts</h2><table><tr><th>User</th><th>Role</th><th>Status</th><th></th></tr>
{% for u in rows %}<tr><td>{{ u.username }}<br><small>{{ u.full_name }}</small></td><td>{{ u.role }}</td><td>{{ 'Active' if u.active else 'Disabled' }}{% if u.locked_until %} (locked until {{ u.locked_until }}){% endif %}</td>
<td><form method=post style="display:flex;gap:6px"><input type=hidden name=csrf value="{{ csrf() }}"><input type=hidden name=uid value="{{ u.id }}">
<button name=act value=toggle>{{ 'Disable' if u.active else 'Enable' }}</button><button name=act value=unlock>Unlock</button></form></td></tr>{% endfor %}</table></div>
<div class=card><h3>Add staff</h3><form method=post><input type=hidden name=csrf value="{{ csrf() }}"><input type=hidden name=act value=add><div class=cols>
<div><label>Username</label><input name=username required></div><div><label>Full name</label><input name=full_name required></div>
<div><label>Role</label><select name=role>{% for r in roles %}<option>{{ r }}</option>{% endfor %}</select></div>
<div><label>Temporary password (10+ chars, letters and numbers)</label><input type=password name=password required autocomplete=new-password></div></div>
<p><button class=p>Create account</button></p></form></div>{% endblock %}"""

app.jinja_loader = DictLoader(T)
app.jinja_env.globals.update(css=CSS, fname=FACILITY_NAME)


def create_admin():
    init_db()
    
init_db()

# Auto-create admin on startup - runs for gunicorn too
try:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT id FROM users WHERE username='admin' LIMIT 1")
    if not cur.fetchone():
        conn.execute("INSERT INTO users(username, full_name, password_hash, role) VALUES(?,?,?,?)", ('admin', 'Admin', generate_password_hash('Admin123'), 'admin'))
        conn.commit()
        print("### AUTO ADMIN CREATED: admin / Admin123 ###")
    conn.close()
except Exception as e:
    print(f"Auto admin check: {e}")

def create_admin():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username='admin'")
    c.execute("INSERT INTO users(username, full_name, password_hash, role) VALUES(?,?,?,?)", ('admin', 'Admin', generate_password_hash('Admin123'), 'admin'))
    conn.commit()
    conn.close()
    print("*** ADMIN CREATED ***")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))

init_db()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-admin":
        init_db()
        create_admin()
    else:
        init_db()
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.execute("SELECT id FROM users LIMIT 1")
            if not cur.fetchone():
                conn.execute("INSERT INTO users(username,full_name,password_hash,role) VALUES(?,?,?,?)",
                    ('admin', 'Admin', generate_password_hash('Admin123'), 'admin'))
                conn.commit()
                print("### AUTO ADMIN CREATED: admin / Admin123 ###")
            conn.close()
        except Exception as e:
            print(f"Auto admin check: {e}")
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
    
       
