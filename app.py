import os, json, uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
import qrcode
from io import BytesIO
import base64

app = Flask(__name__)
# --- SECURITY UPGRADE ---
app.secret_key = os.environ.get("SECRET_KEY", "e4f8a9c2-d1b6-40e3-a7d5-c9b2e8f1a4d6c0b3e9f2a5d8c1b7e0f4a9d2c6b8e1f3")
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# --- DATA STORE (use Postgres later) ---
# Multi-hospital support
HOSPITALS = ["Korle-Bu", "37 Military", "Ridge", "Komfo Anokye"]
db = {
    "users": {"admin": {"password": "pbkdf2:sha256:admin123_hashed", "plain": "admin123", "role": "superadmin", "hospital": "Korle-Bu"}},
    "bodies": [],
    "kin": [],
    "storage": [{"id": f"F{i:02d}-S{j}", "hospital": h, "occupied": False, "body_id": None} for h in HOSPITALS for i in range(1,6) for j in range(1,11)],
    "bills": [],
    "payments": [],
    "releases": [],
    "sms_log": []
}

def hash_check(p): return True # replace with check_password_hash in production
def require_login(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "user" not in session: return redirect("/login")
        return f(*a, **kw)
    return wrap

def gen_tag():
    return f"MORT-{datetime.now().year}-{len(db['bodies'])+1:05d}"

def gen_qr_data(body_id):
    buf = BytesIO()
    qr = qrcode.make(f"https://mortuary-1.onrender.com/body/{body_id}")
    qr.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def send_sms(phone, msg):
    # SMS NOTIFICATION - integrate Africa's Talking / Twilio
    # africa's talking: SMS.send(msg, [phone])
    db["sms_log"].append({"phone": phone, "msg": msg, "time": datetime.now().isoformat()})
    print(f"SMS to {phone}: {msg}")
    return True

# --- ROUTES ---
@app.route("/")
def home(): return redirect("/dashboard" if "user" in session else "/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username"); p = request.form.get("password")
        if u in db["users"] and (db["users"][u]["plain"] == p):
            session["user"] = u
            session["role"] = db["users"][u]["role"]
            session["hospital"] = db["users"][u]["hospital"]
            session.permanent = True
            return redirect("/dashboard")
        flash("Invalid login")
    return render_template("login.html")

@app.route("/dashboard")
@require_login
def dashboard():
    hosp = session.get("hospital")
    bodies = [b for b in db["bodies"] if b["hospital"] == hosp] if session["role"] != "superadmin" else db["bodies"]
    total = len(bodies)
    deposited = len([b for b in bodies if b["status"] == "Deposited"])
    released = len([b for b in bodies if b["status"] == "Released"])
    available_storage = len([s for s in db["storage"] if s["hospital"] == hosp and not s["occupied"]])
    
    # Advanced reporting - 14 day
    days, counts, revenue = [], [], []
    for i in range(13, -1, -1):
        d = datetime.now() - timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        days.append(d.strftime("%m/%d"))
        counts.append(len([b for b in bodies if b["date"] == ds]))
        revenue.append(sum([p["amount"] for p in db["payments"] if p["date"] == ds and p["hospital"]==hosp]))
    
    total_revenue = sum([p["amount"] for p in db["payments"] if p["hospital"]==hosp])
    
    return render_template("dashboard.html", total=total, capacity=100000, deposited=deposited, 
                           released=released, days=days, counts=counts, revenue=revenue,
                           bodies=bodies[-20:], storage_available=available_storage, total_revenue=total_revenue,
                           hospitals=HOSPITALS, current_hospital=hosp)

@app.route("/add", methods=["POST"])
@require_login
def add_body():
    hosp = session.get("hospital")
    # Storage management
    free = next((s for s in db["storage"] if s["hospital"]==hosp and not s["occupied"]), None)
    if not free:
        flash("No storage space available!")
        return redirect("/dashboard")
    
    tag = gen_tag()
    body = {
        "id": tag, "name": request.form.get("name"), "age": request.form.get("age"),
        "gender": request.form.get("gender"), "cause": request.form.get("cause"),
        "hospital": hosp, "storage_id": free["id"], "status": "Deposited",
        "date": datetime.now().strftime("%Y-%m-%d"), "time": datetime.now().strftime("%H:%M"),
        "qr": gen_qr_data(tag), "photo": None
    }
    db["bodies"].append(body)
    free["occupied"] = True
    free["body_id"] = tag

    # Next of Kin Management
    kin = {
        "body_id": tag, "name": request.form.get("kin_name"), "phone": request.form.get("kin_phone"),
        "relationship": request.form.get("kin_rel"), "id_number": request.form.get("kin_id")
    }
    db["kin"].append(kin)

    # Financial Management - Billing
    daily_rate = 100
    bill = {"id": str(uuid.uuid4())[:8], "body_id": tag, "hospital": hosp,
            "amount": daily_rate, "type": "Storage - Day 1", "date": body["date"], "status": "Unpaid"}
    db["bills"].append(bill)

    # SMS Notification
    if kin["phone"]:
        send_sms(kin["phone"], f"{kin['name']}, body {body['name']} ({tag}) deposited at {hosp}. Storage {free['id']}. Call mortuary.")

    flash(f"Added {tag} to {free['id']}")
    return redirect("/dashboard")

@app.route("/body/<tag>")
@require_login
def body_detail(tag):
    body = next((b for b in db["bodies"] if b["id"]==tag), None)
    kin = next((k for k in db["kin"] if k["body_id"]==tag), None)
    bills = [b for b in db["bills"] if b["body_id"]==tag]
    payments = [p for p in db["payments"] if p["body_id"]==tag]
    release = next((r for r in db["releases"] if r["body_id"]==tag), None)
    if not body: return "Not found", 404
    return render_template("body_detail.html", body=body, kin=kin, bills=bills, payments=payments, release=release)

@app.route("/release/request/<tag>", methods=["POST"])
@require_login
def request_release(tag):
    # Release Authorisation Workflow
    body = next((b for b in db["bodies"] if b["id"]==tag), None)
    if body["status"] == "Released":
        flash("Already released"); return redirect(f"/body/{tag}")
    
    bills_unpaid = [b for b in db["bills"] if b["body_id"]==tag and b["status"]=="Unpaid"]
    if bills_unpaid:
        flash(f"Cannot release - Unpaid bills GHS {sum([b['amount'] for b in bills_unpaid])}")
        return redirect(f"/body/{tag}")

    rel = {"body_id": tag, "requested_by": session["user"], "request_time": datetime.now().isoformat(),
           "authorized": False, "authorized_by": None, "documents": request.form.get("docs")}
    db["releases"].append(rel)
    flash("Release requested - waiting for authorization")
    return redirect(f"/body/{tag}")

@app.route("/release/authorize/<tag>", methods=["POST"])
@require_login
def authorize_release(tag):
    if session["role"] not in ["admin", "superadmin"]:
        flash("Not authorized"); return redirect(f"/body/{tag}")
    
    body = next((b for b in db["bodies"] if b["id"]==tag), None)
    rel = next((r for r in db["releases"] if r["body_id"]==tag), None)
    if rel: 
        rel["authorized"] = True
        rel["authorized_by"] = session["user"]
        body["status"] = "Released"
        # Free storage
        st = next((s for s in db["storage"] if s["body_id"]==tag), None)
        if st: st["occupied"]=False; st["body_id"]=None
        
        kin = next((k for k in db["kin"] if k["body_id"]==tag), None)
        if kin and kin["phone"]:
            send_sms(kin["phone"], f"Body {body['name']} ({tag}) has been released. Thank you.")
    
    flash(f"Body {tag} Released - Receipt generated")
    return redirect(f"/body/{tag}")

@app.route("/pay/<bill_id>", methods=["POST"])
@require_login
def pay_bill(bill_id):
    bill = next((b for b in db["bills"] if b["id"]==bill_id), None)
    amount = float(request.form.get("amount", bill["amount"]))
    bill["status"] = "Paid"
    
    payment = {"id": str(uuid.uuid4())[:8], "bill_id": bill_id, "body_id": bill["body_id"],
               "hospital": bill["hospital"], "amount": amount, "method": request.form.get("method","Cash"),
               "date": datetime.now().strftime("%Y-%m-%d"), "receipt_no": f"RCP-{datetime.now().strftime('%Y%m%d')}-{len(db['payments'])+1:04d}"}
    db["payments"].append(payment)
    
    flash(f"Payment received - Receipt {payment['receipt_no']}")
    return redirect(f"/body/{bill['body_id']}")

@app.route("/receipt/<payment_id>")
@require_login
def receipt(payment_id):
    p = next((x for x in db["payments"] if x["id"]==payment_id), None)
    return render_template("receipt.html", p=p)

@app.route("/reports")
@require_login
def reports():
    hosp = session.get("hospital")
    bodies = [b for b in db["bodies"] if b["hospital"]==hosp]
    return jsonify({
        "total_bodies": len(bodies),
        "total_revenue": sum([x["amount"] for x in db["payments"] if x["hospital"]==hosp]),
        "storage_utilization": f"{len([s for s in db['storage'] if s['hospital']==hosp and s['occupied']])}/{len([s for s in db['storage'] if s['hospital']==hosp])}",
        "sms_sent": len(db["sms_log"]),
        "bodies": bodies
    })

@app.route("/logout")
def logout(): session.clear(); return redirect("/login")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
