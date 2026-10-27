# Mortuary Tracking System

Tracks every body deposited and released, with a unique serial ID, secure staff login, a full audit trail and an efficiency dashboard.

## Run it
```
pip install -r requirements.txt
python app.py create-admin     # once: creates the first admin (password typed privately)
python app.py                  # open http://127.0.0.1:5000
```
Settings (environment variables): `FACILITY_CODE` (serial prefix, e.g. KBTH), `FACILITY_NAME`, `CAPACITY` (number of slots), `OVERDUE_DAYS` (default 30), `HOST`, `PORT`, `HTTPS=1` (when served over TLS).

## How it works
- **Serial ID**: `<FACILITY_CODE>-<YEAR>-<6 digits>`, e.g. `KBTH-2026-000123`. Generated on deposit, printed as a tag, retyped at release to confirm the right body.
- **Deposit**: name (or UNIDENTIFIED), case type, source, next of kin, storage slot. One body per slot.
- **Release**: collector name, relationship, ID type and number, release document number (burial permit, death certificate or police release), serial confirmation. A body cannot be released twice.
- **Dashboard**: occupancy, deposits and releases this month, average and median stay, bodies over the overdue limit, 14-day in/out chart, longest-stored list.
- **Audit log**: every login, failed login, view, deposit, release, export and user change, with time, user and IP.

## Security
- Passwords hashed; 10+ characters with letters and numbers required.
- Account locks for 15 minutes after 5 failed logins; admin can unlock.
- 15-minute inactivity timeout, CSRF protection on every form, security headers.
- Roles: `admin` (everything), `attendant` (deposit, release, view), `viewer` (view only).
- Records are never deleted, only marked released.

## Before real use
- Serve behind HTTPS (e.g. nginx) and set `HTTPS=1`; use a production server such as `gunicorn app:app`.
- Back up `instance/mortuary.db` daily and keep it off the same machine.
- Times are stored in UTC, which equals Ghana time.
- Personal data of the deceased and collectors is sensitive. Check the facility's obligations under Ghana's Data Protection Act, 2012 (Act 843) and your hospital's policies before going live.
