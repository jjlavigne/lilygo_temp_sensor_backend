"""
Device admin — a small web UI for managing the devices table.

Grafana can only read. This is the piece that writes: add a device, change its
limits, rename it, retire it. Deliberately narrow -- it touches `devices` and
nothing else, so there is no way to damage telemetry from here.

TEMPERATURES ARE ENTERED IN FAHRENHEIT AND STORED IN CELSIUS.
Everyone reads Fahrenheit on the dashboard, so a form that accepted Celsius
would invite someone to type 34 meaning "34 F" and store 34 C = 93 F -- a
freezer that never alarms. Conversion happens at the boundary, once, here.

ACCESS SCOPING is built in but open by default. Every user has a scope_company:
  NULL          -> sees and edits every company (today's setting for everyone)
  'Plymouth'    -> sees and edits only Plymouth
Restricting someone later is a single UPDATE, not a code change.
"""
import os
from functools import wraps

import psycopg2
import psycopg2.extras
from flask import (Flask, flash, redirect, render_template, request, session,
                   url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-env")

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "fleet_data"),
    user=os.getenv("DB_USER", "admin"),
    password=os.getenv("DB_PASSWORD", "password123"),
)

CARGO_TYPES = ["fresh poultry", "chilled produce", "frozen goods", "dairy", "other"]


# --- temperature conversion, done once, at the edge ---------------------------
def f_to_c(f):
    return (float(f) - 32.0) * 5.0 / 9.0


def c_to_f(c):
    return float(c) * 9.0 / 5.0 + 32.0


def connect():
    return psycopg2.connect(cursor_factory=psycopg2.extras.RealDictCursor, **DB)


def query(sql, params=(), one=False, write=False):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        if write:
            return None
        rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows


def ensure_schema():
    """Additive only. Never drops or alters existing columns."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                username      VARCHAR(50) PRIMARY KEY,
                password_hash TEXT NOT NULL,
                -- NULL means every company. A company name restricts them to it.
                scope_company VARCHAR(50),
                created_at    TIMESTAMP NOT NULL DEFAULT now()
            );
        """)
        # Retiring a device hides it without destroying its history.
        cur.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;")

        # Seed the first account from the environment so there is a way in.
        user = os.getenv("ADMIN_USER", "admin")
        pw = os.getenv("ADMIN_PASSWORD", "fleet2026")
        cur.execute("SELECT 1 FROM admin_users WHERE username = %s", (user,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO admin_users (username, password_hash, scope_company) VALUES (%s, %s, NULL)",
                (user, generate_password_hash(pw)))
            print(f"Created admin user '{user}' with full access to all companies.")


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "username" not in session:
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return wrapper


def scope():
    """The company this user is limited to, or None for all."""
    return session.get("scope_company")


def scope_clause(alias="d"):
    """Reused by every query. Today it is a no-op; it is what makes
    per-company restriction a data change rather than a code change."""
    s = scope()
    if s is None:
        return "TRUE", ()
    return f"{alias}.company = %s", (s,)


def can_edit(company):
    s = scope()
    return s is None or s == company


# --- routes -------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        row = query("SELECT * FROM admin_users WHERE username = %s", (u,), one=True)
        if row and check_password_hash(row["password_hash"], p):
            session["username"] = row["username"]
            session["scope_company"] = row["scope_company"]
            return redirect(request.args.get("next") or url_for("index"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    where, params = scope_clause()
    show_retired = request.args.get("retired") == "1"
    active = "" if show_retired else "AND d.is_active"
    devices = query(f"""
        SELECT d.device_id, d.display_name, d.company, d.site, d.cargo,
               d.temp_min_c, d.temp_max_c, d.expected_interval_s,
               d.is_simulated, d.is_active,
               t.recorded_at AS last_seen,
               t.temperature_c AS last_temp_c
        FROM devices d
        LEFT JOIN LATERAL (
            SELECT recorded_at, temperature_c FROM telemetry
            WHERE device_id = d.device_id ORDER BY recorded_at DESC LIMIT 1
        ) t ON true
        WHERE {where} {active}
        ORDER BY d.company, COALESCE(d.display_name, d.device_id)
    """, params)
    for d in devices:
        d["temp_min_f"] = c_to_f(d["temp_min_c"])
        d["temp_max_f"] = c_to_f(d["temp_max_c"])
        d["last_temp_f"] = c_to_f(d["last_temp_c"]) if d["last_temp_c"] is not None else None
    return render_template("list.html", devices=devices, show_retired=show_retired,
                           scope=scope())


def _validate(form, existing_id=None):
    """Returns (cleaned dict, list of errors). Fahrenheit in, Celsius out."""
    e = []
    device_id = form.get("device_id", "").strip()
    if not existing_id:
        if not device_id:
            e.append("Device ID is required.")
        elif " " in device_id:
            e.append("Device ID cannot contain spaces.")
        elif query("SELECT 1 FROM devices WHERE device_id = %s", (device_id,), one=True):
            e.append(f"Device ID '{device_id}' already exists.")

    company = form.get("company", "").strip()
    site = form.get("site", "").strip()
    if not company:
        e.append("Company is required.")
    if not site:
        e.append("Site is required.")
    if not can_edit(company):
        e.append("You do not have access to that company.")

    try:
        tmin_f = float(form.get("temp_min_f", ""))
        tmax_f = float(form.get("temp_max_f", ""))
        if tmin_f >= tmax_f:
            e.append("Minimum temperature must be below the maximum.")
    except ValueError:
        e.append("Temperatures must be numbers.")
        tmin_f = tmax_f = 0.0

    try:
        interval = int(form.get("expected_interval_s", ""))
        if interval < 1:
            e.append("Reporting interval must be at least 1 second.")
    except ValueError:
        e.append("Reporting interval must be a whole number of seconds.")
        interval = 300

    return dict(
        device_id=device_id or existing_id,
        display_name=(form.get("display_name", "").strip() or None),
        company=company, site=site,
        cargo=form.get("cargo", "").strip() or None,
        # THE CONVERSION. Entered in F, stored in C.
        temp_min_c=f_to_c(tmin_f), temp_max_c=f_to_c(tmax_f),
        expected_interval_s=interval,
    ), e


@app.route("/device/new", methods=["GET", "POST"])
@login_required
def new_device():
    if request.method == "POST":
        data, errors = _validate(request.form)
        if errors:
            for m in errors:
                flash(m, "error")
            return render_template("form.html", d=request.form, mode="new",
                                   cargo_types=CARGO_TYPES, companies=_companies())
        query("""INSERT INTO devices
                 (device_id, display_name, company, site, cargo,
                  temp_min_c, temp_max_c, expected_interval_s, is_simulated, is_active)
                 VALUES (%(device_id)s, %(display_name)s, %(company)s, %(site)s, %(cargo)s,
                         %(temp_min_c)s, %(temp_max_c)s, %(expected_interval_s)s, FALSE, TRUE)""",
              data, write=True)
        flash(f"Added {data['display_name'] or data['device_id']}.", "ok")
        return redirect(url_for("index"))
    return render_template("form.html", d={"expected_interval_s": 300}, mode="new",
                           cargo_types=CARGO_TYPES, companies=_companies())


@app.route("/device/<device_id>/edit", methods=["GET", "POST"])
@login_required
def edit_device(device_id):
    row = query("SELECT * FROM devices WHERE device_id = %s", (device_id,), one=True)
    if not row or not can_edit(row["company"]):
        flash("Device not found.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        data, errors = _validate(request.form, existing_id=device_id)
        if errors:
            for m in errors:
                flash(m, "error")
            return render_template("form.html", d=request.form, mode="edit",
                                   device_id=device_id, cargo_types=CARGO_TYPES,
                                   companies=_companies())
        query("""UPDATE devices SET display_name=%(display_name)s, company=%(company)s,
                 site=%(site)s, cargo=%(cargo)s, temp_min_c=%(temp_min_c)s,
                 temp_max_c=%(temp_max_c)s, expected_interval_s=%(expected_interval_s)s
                 WHERE device_id=%(device_id)s""", data, write=True)
        flash(f"Updated {data['display_name'] or device_id}.", "ok")
        return redirect(url_for("index"))

    row["temp_min_f"] = round(c_to_f(row["temp_min_c"]), 1)
    row["temp_max_f"] = round(c_to_f(row["temp_max_c"]), 1)
    return render_template("form.html", d=row, mode="edit", device_id=device_id,
                           cargo_types=CARGO_TYPES, companies=_companies())


@app.route("/device/<device_id>/retire", methods=["POST"])
@login_required
def retire(device_id):
    row = query("SELECT company, is_active FROM devices WHERE device_id=%s", (device_id,), one=True)
    if not row or not can_edit(row["company"]):
        flash("Device not found.", "error")
        return redirect(url_for("index"))
    new_state = not row["is_active"]
    query("UPDATE devices SET is_active=%s WHERE device_id=%s", (new_state, device_id), write=True)
    flash(f"{'Restored' if new_state else 'Retired'} {device_id}. "
          f"{'' if new_state else 'Its history is kept.'}", "ok")
    return redirect(url_for("index", retired="1" if not new_state else None))


def _companies():
    where, params = scope_clause()
    return [r["company"] for r in
            query(f"SELECT DISTINCT company FROM devices d WHERE {where} ORDER BY 1", params)]


@app.route("/health")
def health():
    try:
        query("SELECT 1")
        return {"status": "ok"}, 200
    except Exception as ex:
        return {"status": "error", "detail": str(ex)}, 503


if __name__ == "__main__":
    ensure_schema()
    app.run(host="0.0.0.0", port=8080)
