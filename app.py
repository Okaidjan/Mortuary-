import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, session, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mortuary-secret-key-change-me")
BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "mortuary.db"))
FACILITY_NAME = os.environ.get("FACILITY_NAME", "Mortuary Tracking System")
CAPACITY = int(os.environ.get("CAPACITY", "100000"))
OVERDUE_DAYS = int(os.environ.get("OVERDUE_DAYS", "30"))

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS bodies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag TEXT UNIQUE, name TEXT, age TEXT, sex TEXT, date_of_death TEXT, cause_of_death TEXT,
        next_of_kin TEXT, kin_contact TEXT, deposited_by TEXT, date_deposited TEXT,
        status TEXT DEFAULT 'IN', date_released TEXT, released_to TEXT, notes TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, password_hash TEXT, role TEXT DEFAULT 'user', created_at TEXT
    )""")
    cur = db.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()["c"] == 0:
        db.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                   ("admin", generate_password_hash("admin123"), "admin", datetime.now().isoformat()))
    db.commit()
    db.close()
init_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        db.close()
        if not u or u["role"] != "admin":
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

BASE_HTML = """
<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{facility}}</title>
<style>
body{font-family:Arial;margin:0;background:#f5f6fa}.header{background:#2c3e50;color:#fff;padding:12px 15px;display:flex;justify-content:space-between;flex-wrap:wrap}
.header a{color:#fff;text-decoration:none;margin:0 6px}.container{padding:15px;max-width:1100px;margin:auto}
.card{background:#fff;padding:15px;border-radius:8px;box-shadow:0 2px 5px rgba(0,0,0,.1);margin-bottom:15px}
.btn{background:#2c3e50;color:#fff;padding:8px 14px;border:none;border-radius:5px;cursor:pointer;text-decoration:none;display:inline-block}
.btn-danger{background:#e74c3c}.btn-success{background:#27ae60}
input,select,textarea{width:100%;padding:8px;margin:5px 0 12px 0;border:1px solid #ccc;border-radius:4px;box-sizing:border-box}
table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #ddd;font-size:14px}
.flash{padding:10px;border-radius:5px;margin-bottom:10px}.flash-error{background:#f8d7da}.flash-success{background:#d4edda}
</style></head><body>
<div class="header"><div><b>{{facility}}</b> | {{occupied}} / {{capacity}} | {{username}} ({{role}})</div>
<div><a href="/">Home</a> <a href="/deposit">+ Deposit</a> <a href="/overdue">Overdue</a>
{% if role=='admin' %}<a href="/users">Users</a>{% endif %}<a href="/my-account">My Account</a> <a href="/logout">Logout</a></div></div>
<div class="container">{% for c,m in flashes %}<div class="flash flash-{{c}}">{{m}}</div>{% endfor %}{{content|safe}}</div></body></html>
"""

def render_page(content, **ctx):
    db = get_db()
    occ = db.execute("SELECT COUNT(*) as c FROM bodies WHERE status='IN'").fetchone()["c"]
    db.close()
    flashes = session.pop("_flashes", []) if "_flashes" in session else []
    return render_template_string(BASE_HTML, facility=FACILITY_NAME, capacity=CAPACITY, occupied=occ,
        username=session.get("username",""), role=session.get("role",""), flashes=flashes, content=content, **ctx)

def flash_msg(msg, cat="success"):
    session.setdefault("_flashes", []).append((cat, msg))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","")
        db=get_db()
        user=db.execute("SELECT * FROM users WHERE username=?",(u,)).fetchone()
        db.close()
        if user and check_password_hash(user["password_hash"], p):
            session["user_id"]=user["id"]; session["username"]=user["username"]; session["role"]=user["role"]
            return redirect(url_for("index"))
        flash_msg("Invalid login","error")
    db=get_db(); occ=db.execute("SELECT COUNT(*) as c FROM bodies WHERE status='IN'").fetchone()["c"]; db.close()
    flashes=session.pop("_flashes",[]) if "_flashes" in session else []
    html = """
    <h2>Login</h2><div class="card" style="max-width:400px">
    <form method="post"><label>Username</label><input name="username" required>
    <label>Password</label><input type="password" name="password" required>
    <button class="btn">Login</button></form>
    <p style="font-size:12px">Default: admin / admin123</p></div>
    """
    return render_template_string(BASE_HTML, facility=FACILITY_NAME, capacity=CAPACITY, occupied=occ, username="", role="", flashes=flashes, content=html)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    db=get_db()
    q=request.args.get("q","").strip()
    bodies=db.execute("SELECT * FROM bodies WHERE status='IN' ORDER BY id DESC LIMIT 300").fetchall()
    if q:
        bodies=[b for b in bodies if q.lower() in (b["name"] or "").lower() or q.lower() in (b["tag"] or "").lower()]
    db.close()
    rows="".join([f"<tr><td>{b['tag']}</td><td>{b['name']}</td><td>{b['sex']}/{b['age']}</td><td>{(b['date_deposited'] or '')[:10]}</td><td>{b['kin_contact']}</td><td>{b['status']}</td><td><a href=/release/{b['id']} style='padding:4px 8px;background:#27ae60;color:#fff;text-decoration:none;border-radius:4px'>Release</a> <a href=/view/{b['id']} style='padding:4px 8px;background:#2c3e50;color:#fff;text-decoration:none;border-radius:4px'>View</a></td></tr>" for b in bodies])
    content=f"<h3>Current - {len(bodies)} shown</h3><form method=get style='display:flex;gap:6px'><input name=q value='{q}' placeholder='Search name/tag'><button class=btn>Search</button></form><div class=card style='overflow:auto'><table><tr><th>Tag</th><th>Name</th><th>Sex/Age</th><th>Deposited</th><th>Kin Contact</th><th>Status</th><th>Action</th></tr>{rows}</table></div>"
    return render_page(content)

@app.route("/deposit", methods=["GET","POST"])
@login_required
def deposit():
    if request.method=="POST":
        db=get_db()
        occ=db.execute("SELECT COUNT(*) as c FROM bodies WHERE status='IN'").fetchone()["c"]
        if occ>=CAPACITY:
            db.close(); flash_msg(f"Full {occ}/{CAPACITY}","error"); return redirect(url_for("index"))
        tag=request.form.get("tag","").strip() or f"TAG{datetime.now().strftime('%Y%m%d%H%M%S')}"
        try:
            db.execute("INSERT INTO bodies (tag,name,age,sex,date_of_death,cause_of_death,next_of_kin,kin_contact,deposited_by,date_deposited,status,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (tag, request.form.get("name"), request.form.get("age"), request.form.get("sex"), request.form.get("date_of_death"),
                        request.form.get("cause_of_death"), request.form.get("next_of_kin"), request.form.get("kin_contact"),
                        session.get("username"), datetime.now().isoformat(), "IN", request.form.get("notes")))
            db.commit(); flash_msg(f"Deposited {tag}","success")
        except sqlite3.IntegrityError:
            flash_msg("Tag exists","error")
        db.close(); return redirect(url_for("index"))
    content="<h3>Deposit Body</h3><div class=card><form method=post><label>Tag (auto if empty)</label><input name=tag><label>Name *</label><input name=name required><label>Age</label><input name=age><label>Sex</label><select name=sex><option>Male</option><option>Female</option></select><label>Date of Death</label><input type=date name=date_of_death><label>Cause</label><input name=cause_of_death><label>Next of Kin</label><input name=next_of_kin><label>Kin Contact *</label><input name=kin_contact required><label>Notes</label><textarea name=notes></textarea><button class=btn>Deposit</button></form></div>"
    return render_page(content)

@app.route("/release/<int:bid>", methods=["GET","POST"])
@login_required
def release(bid):
    db=get_db(); body=db.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone()
    if not body: db.close(); return redirect(url_for("index"))
    if request.method=="POST":
        db.execute("UPDATE bodies SET status='OUT', date_released=?, released_to=? WHERE id=?",(datetime.now().isoformat(), request.form.get("released_to"), bid))
        db.commit(); db.close(); flash_msg(f"Released {body['tag']}","success"); return redirect(url_for("index"))
    db.close()
    content=f"<h3>Release {body['tag']}</h3><div class=card><form method=post><label>Released To</label><input name=released_to required><button class='btn btn-success'>Confirm</button></form></div>"
    return render_page(content)

@app.route("/view/<int:bid>")
@login_required
def view_body(bid):
    db=get_db(); b=db.execute("SELECT * FROM bodies WHERE id=?",(bid,)).fetchone(); db.close()
    if not b: return redirect(url_for("index"))
    content=f"<div class=card><h3>{b['tag']} - {b['name']}</h3><p>Age/Sex: {b['age']}/{b['sex']}</p><p>Kin: {b['next_of_kin']} - {b['kin_contact']}</p><p>Status: {b['status']}</p><p>Notes: {b['notes']}</p></div>"
    return render_page(content)

@app.route("/overdue")
@login_required
def overdue():
    db=get_db(); cutoff=(datetime.now()-timedelta(days=OVERDUE_DAYS)).isoformat()
    bodies=db.execute("SELECT * FROM bodies WHERE status='IN' AND date_deposited < ?",(cutoff,)).fetchall(); db.close()
    rows="".join([f"<tr><td>{b['tag']}</td><td>{b['name']}</td><td>{(b['date_deposited'] or '')[:10]}</td><td>{b['kin_contact']}</td></tr>" for b in bodies])
    content=f"<h3>Overdue > {OVERDUE_DAYS} days ({len(bodies)})</h3><div class=card><table><tr><th>Tag</th><th>Name</th><th>Deposited</th><th>Contact</th></tr>{rows}</table></div>"
    return render_page(content)

@app.route("/users", methods=["GET","POST"])
@admin_required
def users():
    db=get_db()
    if request.method=="POST":
        act=request.form.get("action")
        if act=="create":
            u=request.form.get("username","").strip(); p=request.form.get("password",""); r=request.form.get("role","user")
            if u and p:
                try:
                    db.execute("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",(u, generate_password_hash(p), r, datetime.now().isoformat()))
                    db.commit(); flash_msg(f"User {u} created","success")
                except: flash_msg("Username exists","error")
        elif act=="reset":
            uid=request.form.get("user_id"); np=request.form.get("new_password")
            if uid and np:
                db.execute("UPDATE users SET password_hash=? WHERE id=?",(generate_password_hash(np), uid)); db.commit(); flash_msg("Password reset","success")
        elif act=="delete":
            uid=request.form.get("user_id")
            if uid and int(uid)!=session["user_id"]:
                db.execute("DELETE FROM users WHERE id=?",(uid,)); db.commit(); flash_msg("Deleted","success")
        elif act=="edit_username":
            uid=request.form.get("user_id"); nu=request.form.get("new_username","").strip()
            if uid and nu:
                try:
                    db.execute("UPDATE users SET username=? WHERE id=?",(nu, uid)); db.commit(); flash_msg(f"Renamed to {nu}","success")
                except: flash_msg("Username taken","error")
    users_list=db.execute("SELECT * FROM users ORDER BY id").fetchall(); db.close()
    rows=""
    for u in users_list:
        rows+=f"<tr><td>{u['id']}</td><td>{u['username']}</td><td>{u['role']}</td><td>"
        rows+=f"<form method=post style='display:inline-flex;gap:3px'><input type=hidden name=action value=edit_username><input type=hidden name=user_id value={u['id']}><input name=new_username placeholder='new name' style='width:90px' required><button class=btn style='padding:3px 6px'>Rename</button></form> "
        rows+=f"<form method=post style='display:inline-flex;gap:3px'><input type=hidden name=action value=reset><input type=hidden name=user_id value={u['id']}><input name=new_password placeholder='new pw' style='width:90px' required><button class='btn btn-success' style='padding:3px 6px'>Reset PW</button></form> "
        rows+=f"<form method=post style='display:inline'><input type=hidden name=action value=delete><input type=hidden name=user_id value={u['id']}><button class='btn btn-danger' style='padding:3px 6px'>Del</button></form></td></tr>"
    content=f"<h3>User Management</h3><div class=card><h4>Create User (e.g. Tamale)</h4><form method=post><input type=hidden name=action value=create><label>Username</label><input name=username required><label>Password</label><input name=password required><label>Role</label><select name=role><option value=user>User</option><option value=admin>Admin</option></select><button class=btn>Create</button></form></div><div class=card style='overflow:auto'><table><tr><th>ID</th><th>Username</th><th>Role</th><th>Actions</th></tr>{rows}</table></div>"
    return render_page(content)

@app.route("/my-account", methods=["GET","POST"])
@login_required
def my_account():
    db=get_db(); user=db.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone()
    if request.method=="POST":
        act=request.form.get("action")
        if act=="change_username":
            nu=request.form.get("new_username","").strip(); cp=request.form.get("current_password","")
            if not check_password_hash(user["password_hash"], cp):
                flash_msg("Current password wrong","error")
            else:
                try:
                    db.execute("UPDATE users SET username=? WHERE id=?",(nu, user["id"])); db.commit(); session["username"]=nu; flash_msg(f"Username changed to {nu}","success")
                except: flash_msg("Username taken","error")
            user=db.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone()
        elif act=="change_password":
            cp=request.form.get("current_password",""); np=request.form.get("new_password",""); cnp=request.form.get("confirm_password","")
            if not check_password_hash(user["password_hash"], cp):
                flash_msg("Current password wrong","error")
            elif np!=cnp:
                flash_msg("New passwords no match","error")
            elif len(np)<4:
                flash_msg("Password too short","error")
            else:
                db.execute("UPDATE users SET password_hash=? WHERE id=?",(generate_password_hash(np), user["id"])); db.commit(); flash_msg("Password changed!","success")
    db.close()
    content=f"""
    <h3>My Account - {user['username']} ({user['role']})</h3>
    <div class=card><h4>Change Username</h4><form method=post><input type=hidden name=action value=change_username>
    <label>New Username</label><input name=new_username value="{user['username']}" required>
    <label>Current Password to Confirm</label><input type=password name=current_password required>
    <button class=btn>Update Username</button></form></div>
    <div class=card><h4>Change Password</h4><form method=post><input type=hidden name=action value=change_password>
    <label>Current Password</label><input type=password name=current_password required>
    <label>New Password</label><input type=password name=new_password required>
    <label>Confirm New Password</label><input type=password name=confirm_password required>
    <button class='btn btn-success'>Update Password</button></form></div>
    """
    return render_page(content)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","10000")))
