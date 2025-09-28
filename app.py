#!/usr/bin/env python3
import os
from datetime import datetime, date, timedelta
from functools import wraps
from collections import defaultdict, OrderedDict

from flask import Flask, render_template_string, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------------------------------------------------------------
# Config (two separate databases: users & stock)
# ----------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-in-prod")

USERS_DB_URL = os.environ.get("USERS_DATABASE_URL", "sqlite:///users.db")
STOCK_DB_URL = os.environ.get("STOCK_DATABASE_URL", "sqlite:///stock.db")

# Primary DB points to users
app.config["SQLALCHEMY_DATABASE_URI"] = USERS_DB_URL
app.config["SQLALCHEMY_BINDS"] = {
    "users": USERS_DB_URL,
    "stock": STOCK_DB_URL,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------
class User(db.Model):
    __bind_key__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="user")  # "user" or "admin"
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class Item(db.Model):
    __bind_key__ = "stock"
    id = db.Column(db.Integer, primary_key=True)
    finis_code = db.Column(db.String(64), nullable=False, index=True)
    full_code = db.Column(db.String(128), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    created_by_id = db.Column(db.Integer, nullable=False, index=True)
    updated_by_id = db.Column(db.Integer, nullable=True, index=True)

class Movement(db.Model):
    __bind_key__ = "stock"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False, index=True)
    direction = db.Column(db.String(3), nullable=False)  # 'IN' or 'OUT'
    qty = db.Column(db.Integer, nullable=False)  # positive integer
    when = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    note = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)  # who recorded it

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or u.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper

def username_of(user_id: int) -> str:
    if not user_id:
        return ""
    u = db.session.get(User, user_id)
    return u.username if u else f"utente#{user_id}"

def can_edit(item, user):
    return user.role == "admin" or item.created_by_id == user.id

# ----------------------------------------------------------------------------
# Templates
# ----------------------------------------------------------------------------
layout = """
<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Stock App</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  </head>
  <body class="bg-light">
    <nav class="navbar navbar-expand-lg bg-body-tertiary border-bottom mb-3">
      <div class="container-fluid">
        <a class="navbar-brand" href="{{ url_for('dashboard') }}">Stock</a>
        <div class="d-flex">
          {% if cu %}
            <span class="navbar-text me-3">Ciao, {{ cu.username }} ({{ cu.role }})</span>
            <a class="btn btn-outline-secondary btn-sm me-2" href="{{ url_for('add_item') }}">+ Aggiungi</a>
            {% if cu.role == 'admin' %}
              <a class="btn btn-outline-primary btn-sm me-2" href="{{ url_for('users') }}">Utenti</a>
              <a class="btn btn-outline-primary btn-sm me-2" href="{{ url_for('stock_lookup') }}">Verifica Stock</a>
              <a class="btn btn-outline-primary btn-sm me-2" href="{{ url_for('stats') }}">Statistiche</a>
            {% endif %}
            <a class="btn btn-danger btn-sm" href="{{ url_for('logout') }}">Logout</a>
          {% endif %}
        </div>
      </div>
    </nav>
    <main class="container">
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          <div class="alert alert-info">{{ messages|join(' ') }}</div>
        {% endif %}
      {% endwith %}
      {{ content|safe }}
    </main>
  </body>
</html>
"""

login_tpl = """
<div class="row justify-content-center">
  <div class="col-md-4">
    <div class="card shadow">
      <div class="card-body">
        <h5 class="card-title mb-3">Accedi</h5>
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Username</label>
            <input name="username" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Password</label>
            <input name="password" type="password" class="form-control" required>
          </div>
          <button class="btn btn-primary w-100">Login</button>
        </form>
      </div>
    </div>
  </div>
</div>
"""

dashboard_tpl = """
<div class="card shadow">
  <div class="card-body">
    <h5 class="card-title">Archivio pezzi</h5>
    <form class="row g-2 mb-3">
      <div class="col-sm-3">
        <input class="form-control" name="q" placeholder="Cerca codice/descrizione" value="{{ request.args.get('q','') }}">
      </div>
      <div class="col-sm-2">
        <button class="btn btn-outline-secondary w-100">Cerca</button>
      </div>
    </form>
    <div class="table-responsive">
      <table class="table table-sm table-striped align-middle">
        <thead>
          <tr>
            <th>ID</th>
            <th>FINIS</th>
            <th>Codice completo</th>
            <th>Descrizione</th>
            <th>Q.tà</th>
            <th>Creato da</th>
            <th>Creato il</th>
            <th>Aggiornato il</th>
            <th>Aggiornato da</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {% for it in items %}
          <tr>
            <td>{{ it.id }}</td>
            <td><code>{{ it.finis_code }}</code></td>
            <td><code>{{ it.full_code }}</code></td>
            <td>{{ it.description }}</td>
            <td>{{ it.quantity }}</td>
            <td>{{ username_of(it.created_by_id) }}</td>
            <td>{{ it.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
            <td>{{ it.updated_at.strftime('%Y-%m-%d %H:%M') if it.updated_at else '' }}</td>
            <td>{{ username_of(it.updated_by_id) if it.updated_by_id else '' }}</td>
            <td class="text-nowrap">
              {% if cu.role == 'admin' or cu.id == it.created_by_id %}
                <a class="btn btn-sm btn-outline-primary" href="{{ url_for('edit_item', item_id=it.id) }}">Modifica</a>
                <a class="btn btn-sm btn-outline-secondary" href="{{ url_for('add_movement', item_id=it.id) }}">+ Movimento</a>
                <a class="btn btn-sm btn-outline-danger" href="{{ url_for('delete_item', item_id=it.id) }}" onclick="return confirm('Eliminare questo elemento?');">Elimina</a>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
"""

item_form_tpl = """
<div class="row justify-content-center">
  <div class="col-lg-8">
    <div class="card shadow">
      <div class="card-body">
        <h5 class="card-title">{{ 'Modifica' if item else 'Nuovo' }} elemento</h5>
        <form method="post">
          <div class="row g-3">
            <div class="col-sm-4">
              <label class="form-label">Codice FINIS</label>
              <input name="finis_code" class="form-control" value="{{ item.finis_code if item else '' }}" required>
            </div>
            <div class="col-sm-8">
              <label class="form-label">Codice completo</label>
              <input name="full_code" class="form-control" value="{{ item.full_code if item else '' }}" required>
            </div>
            <div class="col-12">
              <label class="form-label">Descrizione</label>
              <textarea name="description" class="form-control" rows="3" required>{{ item.description if item else '' }}</textarea>
            </div>
            <div class="col-sm-3">
              <label class="form-label">Quantità</label>
              <input name="quantity" type="number" step="1" min="0" class="form-control" value="{{ item.quantity if item else 0 }}" required>
            </div>
          </div>
          <div class="mt-3 d-flex gap-2">
            <button class="btn btn-primary">Salva</button>
            <a class="btn btn-secondary" href="{{ url_for('dashboard') }}">Annulla</a>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>
"""

movement_form_tpl = """
<div class="row justify-content-center">
  <div class="col-lg-6">
    <div class="card shadow">
      <div class="card-body">
        <h5 class="card-title">Nuovo movimento per <code>{{ item.full_code }}</code></h5>
        <form method="post">
          <div class="row g-3">
            <div class="col-sm-4">
              <label class="form-label">Direzione</label>
              <select name="direction" class="form-select" required>
                <option value="IN">Ingresso</option>
                <option value="OUT">Uscita</option>
              </select>
            </div>
            <div class="col-sm-4">
              <label class="form-label">Quantità</label>
              <input name="qty" type="number" step="1" min="1" class="form-control" required>
            </div>
            <div class="col-sm-4">
              <label class="form-label">Data</label>
              <input name="when" type="datetime-local" class="form-control" value="{{ default_when }}">
            </div>
            <div class="col-12">
              <label class="form-label">Nota (opzionale)</label>
              <input name="note" class="form-control" placeholder="es. rettifica giacenza, DDT 123, ecc.">
            </div>
          </div>
          <div class="mt-3 d-flex gap-2">
            <button class="btn btn-primary">Registra</button>
            <a class="btn btn-secondary" href="{{ url_for('dashboard') }}">Annulla</a>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>
"""

users_tpl = """
<div class="card shadow">
  <div class="card-body">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="card-title">Gestione utenti</h5>
      <a class="btn btn-sm btn-primary" href="{{ url_for('create_user') }}">+ Nuovo utente</a>
    </div>
    <table class="table table-sm table-striped align-middle">
      <thead><tr><th>ID</th><th>Username</th><th>Ruolo</th><th>Stato</th><th></th></tr></thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td>{{ u.id }}</td>
          <td>{{ u.username }}</td>
          <td>{{ u.role }}</td>
          <td>{% if u.is_active %}<span class="badge bg-success">attivo</span>{% else %}<span class="badge bg-secondary">bloccato</span>{% endif %}</td>
          <td class="text-nowrap">
            <a class="btn btn-sm btn-outline-primary" href="{{ url_for('edit_user', user_id=u.id) }}">Modifica</a>
            {% if u.id != cu.id %}
              {% if u.is_active %}
                <a class="btn btn-sm btn-outline-warning" href="{{ url_for('block_user', user_id=u.id) }}" onclick="return confirm('Bloccare l\\'utente?');">Blocca</a>
              {% else %}
                <a class="btn btn-sm btn-outline-success" href="{{ url_for('unblock_user', user_id=u.id) }}">Sblocca</a>
              {% endif %}
              <a class="btn btn-sm btn-outline-danger" href="{{ url_for('delete_user', user_id=u.id) }}" onclick="return confirm('Eliminare utente?');">Elimina</a>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
"""

user_form_tpl = """
<div class="row justify-content-center">
  <div class="col-md-6">
    <div class="card shadow">
      <div class="card-body">
        <h5 class="card-title">{{ 'Modifica' if user else 'Nuovo' }} utente</h5>
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Username</label>
            <input name="username" class="form-control" value="{{ user.username if user else '' }}" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Password {{ '(lascia vuoto per non cambiare)' if user else '' }}</label>
            <input name="password" type="password" class="form-control" {{ '' if user else 'required' }}>
          </div>
          <div class="mb-3">
            <label class="form-label">Ruolo</label>
            <select name="role" class="form-select">
              <option value="user" {{ 'selected' if user and user.role=='user' else '' }}>utilizzatore</option>
              <option value="admin" {{ 'selected' if user and user.role=='admin' else '' }}>admin</option>
            </select>
          </div>
          <div class="d-flex gap-2">
            <button class="btn btn-primary">Salva</button>
            <a class="btn btn-secondary" href="{{ url_for('users') }}">Annulla</a>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>
"""

stock_lookup_tpl = """
<div class="card shadow">
  <div class="card-body">
    <h5 class="card-title">Verifica disponibilità per codice</h5>
    <form class="row g-2 mb-3" method="get">
      <div class="col-sm-4">
        <input name="code" class="form-control" placeholder="FINIS o codice completo" value="{{ request.args.get('code','') }}">
      </div>
      <div class="col-sm-4">
        <div class="input-group">
          <label class="input-group-text" for="user_id">Utente</label>
          <select class="form-select" id="user_id" name="user_id">
            <option value="">Tutti</option>
            {% for u in users_list %}
              <option value="{{ u.id }}" {% if selected_user_id == u.id %}selected{% endif %}>{{ u.username }} ({{ u.role }})</option>
            {% endfor %}
          </select>
        </div>
      </div>
      <div class="col-sm-2">
        <button class="btn btn-outline-secondary w-100">Cerca</button>
      </div>
    </form>

    {% if code or selected_user_id %}
      {% if rows %}
      <p class="mb-3"><strong>Totale quantità (tutte le righe):</strong> {{ total_qty }}</p>

      <!-- Raggruppato per FINIS e Utente -->
      <h6 class="mt-3">Raggruppato per FINIS e Utente</h6>
      <div class="table-responsive mb-3">
        <table class="table table-sm table-striped align-middle">
          <thead><tr><th>FINIS</th><th>Utente</th><th>Totale quantità</th></tr></thead>
          <tbody>
            {% for g in grouped_by_user %}
              <tr>
                <td><code>{{ g.finis_code }}</code></td>
                <td>{{ username_of(g.user_id) }}</td>
                <td>{{ g.qty }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>

      <!-- Totali per FINIS -->
      <h6 class="mt-3">Totale per FINIS ({{ 'utente selezionato' if selected_user_id else 'tutti gli utenti' }})</h6>
      <div class="table-responsive mb-4">
        <table class="table table-sm table-striped align-middle">
          <thead><tr><th>FINIS</th><th>Totale quantità</th></tr></thead>
          <tbody>
            {% for ft in finis_totals %}
              <tr>
                <td><code>{{ ft.finis_code }}</code></td>
                <td>{{ ft.qty }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>

      <!-- Dettaglio righe -->
      <details>
        <summary class="mb-2">Dettaglio righe (per codice completo)</summary>
        <div class="table-responsive">
          <table class="table table-sm table-striped align-middle">
            <thead><tr><th>Utente</th><th>FINIS</th><th>Codice completo</th><th>Descrizione</th><th>Quantità</th></tr></thead>
            <tbody>
              {% for r in rows %}
                <tr>
                  <td>{{ username_of(r.created_by_id) }}</td>
                  <td><code>{{ r.finis_code }}</code></td>
                  <td><code>{{ r.full_code }}</code></td>
                  <td>{{ r.description }}</td>
                  <td>{{ r.quantity }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </details>
      {% else %}
        <div class="alert alert-warning">Nessun risultato per i filtri impostati.</div>
      {% endif %}
    {% endif %}
  </div>
</div>
"""


stats_tpl = """
<div class="card shadow">
  <div class="card-body">
    <h5 class="card-title">Statistiche movimenti</h5>
    <form class="row g-2 mb-3" method="get">
      <div class="col-sm-3">
        <label class="form-label">Dal</label>
        <input type="date" class="form-control" name="start" value="{{ start_str }}">
      </div>
      <div class="col-sm-3">
        <label class="form-label">Al</label>
        <input type="date" class="form-control" name="end" value="{{ end_str }}">
      </div>
      <div class="col-sm-3">
        <label class="form-label">FINIS (opzionale)</label>
        <input class="form-control" name="finis" value="{{ request.args.get('finis','') }}">
      </div>
      <div class="col-sm-3">
        <label class="form-label">Utente (opzionale)</label>
        <select class="form-select" name="user_id">
          <option value="">Tutti</option>
          {% for u in users_list %}
            <option value="{{ u.id }}" {% if selected_user_id == u.id %}selected{% endif %}>{{ u.username }} ({{ u.role }})</option>
          {% endfor %}
        </select>
      </div>
      <div class="col-sm-2 mt-2">
        <button class="btn btn-outline-secondary w-100" style="margin-top: 30px;">Filtra</button>
      </div>
    </form>

    <div class="row text-center mb-3">
      <div class="col-md-3">
        <div class="p-3 border rounded bg-white">
          <div class="small text-muted">Totale IN</div>
          <div class="fs-4">{{ kpi_in }}</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="p-3 border rounded bg-white">
          <div class="small text-muted">Totale OUT</div>
          <div class="fs-4">{{ kpi_out }}</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="p-3 border rounded bg-white">
          <div class="small text-muted">Saldo (IN-OUT)</div>
          <div class="fs-4">{{ kpi_net }}</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="p-3 border rounded bg-white">
          <div class="small text-muted">Stock corrente (per filtro)</div>
          <div class="fs-4">{{ kpi_stock_current }}</div>
        </div>
      </div>
    </div>

    <div class="mb-4 bg-white p-3 border rounded">
      <h6>Ingressi/Uscite per giorno</h6>
      <div style="height: 320px;">
        <canvas id="barInOut" style="width:100%;height:100%;"></canvas>
      </div>
    </div>

    <div class="mb-4 bg-white p-3 border rounded">
      <h6>Stock nel tempo</h6>
      <div style="height: 320px;">
        <canvas id="lineStock" style="width:100%;height:100%;"></canvas>
      </div>
    </div>

    {% if movements %}
    <details>
      <summary>Dettaglio movimenti ({{ movements|length }})</summary>
      <div class="table-responsive mt-2">
        <table class="table table-sm table-striped align-middle">
          <thead><tr><th>Data</th><th>Utente</th><th>FINIS</th><th>Codice</th><th>Dir</th><th>Q.tà</th><th>Nota</th></tr></thead>
          <tbody>
            {% for m in movements %}
              <tr>
                <td>{{ m.when.strftime('%Y-%m-%d %H:%M') }}</td>
                <td>{{ username_of(m.user_id) }}</td>
                <td><code>{{ m.finis_code }}</code></td>
                <td><code>{{ m.full_code }}</code></td>
                <td>{{ m.direction }}</td>
                <td>{{ m.qty }}</td>
                <td>{{ m.note or '' }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </details>
    {% endif %}
  </div>
</div>

<script>
const labels = {{ labels|tojson }};
const dataIn = {{ series_in|tojson }};
const dataOut = {{ series_out|tojson }};
const dataStock = {{ series_stock|tojson }};

new Chart(document.getElementById('barInOut'), {
  type: 'bar',
  data: { labels, datasets: [
    { label: 'IN', data: dataIn },
    { label: 'OUT', data: dataOut }
  ]},
  options: {
    responsive: true,
    maintainAspectRatio: false,
    resizeDelay: 150,
    scales: { x: { ticks: { autoSkip: true, maxTicksLimit: 15 } } }
  }
});

new Chart(document.getElementById('lineStock'), {
  type: 'line',
  data: { labels, datasets: [
    { label: 'Stock', data: dataStock }
  ]},
  options: {
    responsive: true,
    maintainAspectRatio: false,
    resizeDelay: 150,
    scales: { x: { ticks: { autoSkip: true, maxTicksLimit: 15 } } }
  }
});
</script>
"""

def render_page(tpl_string, **ctx):
    """Render inner template with full context and then apply layout."""
    cu = current_user()
    inner = render_template_string(
        tpl_string,
        cu=cu,
        username_of=username_of,
        **ctx
    )
    return render_template_string(
        layout,
        content=inner,
        cu=cu,
        username_of=username_of,
        **ctx
    )

# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["username"].strip()).first()
        if u and u.check_password(request.form["password"]):
            if not u.is_active:
                flash("Account bloccato. Contatta un amministratore.")
            else:
                session["user_id"] = u.id
                flash("Login eseguito.")
                return redirect(request.args.get("next") or url_for("dashboard"))
        else:
            flash("Credenziali non valide.")
    return render_page(login_tpl)

@app.route("/logout")
def logout():
    session.clear()
    flash("Logout eseguito.")
    return redirect(url_for("login"))

# ----------------------------------------------------------------------------
# Dashboard & CRUD (stock DB)
# ----------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    cu = current_user()
    q = request.args.get("q","").strip()
    base_q = Item.query
    if cu.role != "admin":
        base_q = base_q.filter_by(created_by_id=cu.id)
    if q:
        like = f"%{q}%"
        base_q = base_q.filter(db.or_(Item.finis_code.ilike(like),
                                      Item.full_code.ilike(like),
                                      Item.description.ilike(like)))
    items = base_q.order_by(Item.updated_at.desc()).limit(500).all()
    return render_page(dashboard_tpl, items=items)

@app.route("/items/new", methods=["GET","POST"])
@login_required
def add_item():
    cu = current_user()
    if request.method == "POST":
        quantity = int(request.form["quantity"] or 0)
        item = Item(
            finis_code=request.form["finis_code"].strip(),
            full_code=request.form["full_code"].strip(),
            description=request.form["description"].strip(),
            quantity=quantity,
            created_by_id=cu.id,
            updated_by_id=cu.id,
        )
        db.session.add(item)
        db.session.commit()
        flash("Elemento creato.")
        return redirect(url_for("dashboard"))
    return render_page(item_form_tpl, item=None)

@app.route("/items/<int:item_id>/edit", methods=["GET","POST"])
@login_required
def edit_item(item_id):
    cu = current_user()
    item = db.session.get(Item, item_id)
    if not item:
        abort(404)
    if not can_edit(item, cu):
        abort(403)
    if request.method == "POST":
        item.finis_code = request.form["finis_code"].strip()
        item.full_code = request.form["full_code"].strip()
        item.description = request.form["description"].strip()
        item.quantity = int(request.form["quantity"] or 0)
        item.updated_by_id = cu.id
        db.session.commit()
        flash("Elemento aggiornato.")
        return redirect(url_for("dashboard"))
    return render_page(item_form_tpl, item=item)

@app.route("/items/<int:item_id>/delete")
@login_required
def delete_item(item_id):
    cu = current_user()
    item = db.session.get(Item, item_id)
    if not item:
        abort(404)
    if not can_edit(item, cu):
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash("Elemento eliminato.")
    return redirect(url_for("dashboard"))

# ----------------------------------------------------------------------------
# Movements
# ----------------------------------------------------------------------------
@app.route("/items/<int:item_id>/move", methods=["GET","POST"])
@login_required
def add_movement(item_id):
    cu = current_user()
    item = db.session.get(Item, item_id)
    if not item:
        abort(404)
    if not can_edit(item, cu):
        abort(403)

    if request.method == "POST":
        direction = request.form.get("direction")
        qty = int(request.form.get("qty", "0"))
        when_str = request.form.get("when")  # 'YYYY-MM-DDTHH:MM'
        note = (request.form.get("note") or "").strip()

        if direction not in ("IN", "OUT") or qty <= 0:
            flash("Dati movimento non validi.")
            return redirect(url_for("add_movement", item_id=item.id))

        when_dt = None
        try:
            when_dt = datetime.strptime(when_str, "%Y-%m-%dT%H:%M") if when_str else datetime.utcnow()
        except Exception:
            when_dt = datetime.utcnow()

        mov = Movement(item_id=item.id, direction=direction, qty=qty, when=when_dt, note=note, user_id=cu.id)
        db.session.add(mov)

        # Aggiorna quantità item (coerente con movimenti)
        if direction == "IN":
            item.quantity += qty
        else:
            item.quantity -= qty
            if item.quantity < 0:
                item.quantity = 0  # semplice protezione; opzionale: consentire negativi
        item.updated_by_id = cu.id

        db.session.commit()
        flash("Movimento registrato.")
        return redirect(url_for("dashboard"))

    # default datetime-local value
    default_when = datetime.utcnow().strftime("%Y-%m-%dT%H:%M")
    return render_page(movement_form_tpl, item=item, default_when=default_when)

# ----------------------------------------------------------------------------
# Admin: Users (users DB)
# ----------------------------------------------------------------------------
@app.route("/admin/users")
@admin_required
def users():
    return render_page(users_tpl, users=User.query.order_by(User.id).all())

@app.route("/admin/users/new", methods=["GET","POST"])
@admin_required
def create_user():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form.get("role","user")
        if User.query.filter_by(username=username).first():
            flash("Username già esistente.")
        else:
            u = User(username=username, role=role, is_active=True)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash("Utente creato.")
            return redirect(url_for("users"))
    return render_page(user_form_tpl, user=None)

@app.route("/admin/users/<int:user_id>/edit", methods=["GET","POST"])
@admin_required
def edit_user(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    if request.method == "POST":
        u.username = request.form["username"].strip()
        role = request.form.get("role","user")
        u.role = role
        pwd = request.form.get("password","").strip()
        if pwd:
            u.set_password(pwd)
        db.session.commit()
        flash("Utente aggiornato.")
        return redirect(url_for("users"))
    return render_page(user_form_tpl, user=u)

@app.route("/admin/users/<int:user_id>/delete")
@admin_required
def delete_user(user_id):
    if user_id == current_user().id:
        flash("Non puoi eliminare te stesso.")
        return redirect(url_for("users"))
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    db.session.delete(u)
    db.session.commit()
    flash("Utente eliminato.")
    return redirect(url_for("users"))

@app.route("/admin/users/<int:user_id>/block")
@admin_required
def block_user(user_id):
    if user_id == current_user().id:
        flash("Non puoi bloccare te stesso.")
        return redirect(url_for("users"))
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    u.is_active = False
    db.session.commit()
    flash("Utente bloccato.")
    return redirect(url_for("users"))

@app.route("/admin/users/<int:user_id>/unblock")
@admin_required
def unblock_user(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    u.is_active = True
    db.session.commit()
    flash("Utente sbloccato.")
    return redirect(url_for("users"))

# ----------------------------------------------------------------------------
# Admin: stock lookup (stock DB) with code/user filters and FINIS groupings
# ----------------------------------------------------------------------------
@app.route("/admin/stock")
@admin_required
def stock_lookup():
    code = request.args.get("code","").strip()
    user_id = request.args.get("user_id", "").strip()
    selected_user_id = int(user_id) if user_id.isdigit() else None

    q = Item.query
    if code:
        like = f"%{code}%"
        q = q.filter(db.or_(Item.finis_code.ilike(like), Item.full_code.ilike(like)))
    if selected_user_id:
        q = q.filter(Item.created_by_id == selected_user_id)

    rows = q.order_by(Item.created_by_id).all()
    total_qty = sum(r.quantity for r in rows)

    by_user = defaultdict(int)   # (finis, user_id) -> qty
    by_finis = defaultdict(int)  # finis -> qty
    for r in rows:
        by_user[(r.finis_code, r.created_by_id)] += r.quantity
        by_finis[r.finis_code] += r.quantity

    grouped_by_user = [
        type("Row", (), {"finis_code": k[0], "user_id": k[1], "qty": v})
        for k, v in by_user.items()
    ]
    grouped_by_user.sort(key=lambda x: (x.finis_code, x.user_id))

    finis_totals = [
        type("Row", (), {"finis_code": k, "qty": v})
        for k, v in by_finis.items()
    ]
    finis_totals.sort(key=lambda x: (-x.qty, x.finis_code))

    users_list = User.query.order_by(User.username).all()
    return render_page(
        stock_lookup_tpl,
        code=code,
        rows=rows,
        total_qty=total_qty,
        grouped_by_user=grouped_by_user,
        finis_totals=finis_totals,
        users_list=users_list,
        selected_user_id=selected_user_id,
    )

# ----------------------------------------------------------------------------
# Stats (admin)
# ----------------------------------------------------------------------------
@app.route("/admin/stats")
@admin_required
def stats():
    # defaults: last 30 days (inclusive)
    today = date.today()
    start_default = today - timedelta(days=29)
    end_default = today

    start_str = request.args.get("start", start_default.isoformat())
    end_str = request.args.get("end", end_default.isoformat())
    finis = (request.args.get("finis") or "").strip()
    user_id = (request.args.get("user_id") or "").strip()
    selected_user_id = int(user_id) if user_id.isdigit() else None

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
    except Exception:
        start_date = start_default
        start_str = start_default.isoformat()
    try:
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
    except Exception:
        end_date = end_default
        end_str = end_default.isoformat()

    # time bounds in datetime
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())  # exclusive

    # Build base query
    q = Movement.query.join(Item, Movement.item_id == Item.id)
    if finis:
        like = f"%{finis}%"
        q = q.filter(Item.finis_code.ilike(like))
    if selected_user_id:
        q = q.filter(Movement.user_id == selected_user_id)

    # For KPIs and charts we need:
    # - Movements within [start_dt, end_dt)
    # - Opening balance (sum IN-OUT before start_dt)
    q_range = q.filter(Movement.when >= start_dt, Movement.when < end_dt)
    q_before = q.filter(Movement.when < start_dt)

    rows_range = q_range.add_columns(Item.finis_code, Item.full_code).order_by(Movement.when).all()
    rows_before = q_before.all()

    # Aggregate daily IN/OUT within range
    days = []
    cur = start_date
    while cur <= end_date:
        days.append(cur)
        cur += timedelta(days=1)

    by_day_in = OrderedDict((d, 0) for d in days)
    by_day_out = OrderedDict((d, 0) for d in days)

    total_in = 0
    total_out = 0
    movements_list = []

    for m, finis_code, full_code in rows_range:
        d = m.when.date()
        if d in by_day_in:
            if m.direction == "IN":
                by_day_in[d] += m.qty
                total_in += m.qty
            else:
                by_day_out[d] += m.qty
                total_out += m.qty
        movements_list.append(type("Row", (), {
            "when": m.when,
            "direction": m.direction,
            "qty": m.qty,
            "note": m.note,
            "user_id": m.user_id,
            "finis_code": finis_code,
            "full_code": full_code
        }))

    # Opening balance from movements before start
    opening = 0
    for m in rows_before:
        opening += m.qty if m.direction == "IN" else -m.qty

    # Stock series = opening + cumulative(net per day)
    labels = [d.isoformat() for d in days]
    series_in = [by_day_in[d] for d in days]
    series_out = [by_day_out[d] for d in days]

    series_stock = []
    running = opening
    for d in days:
        running += by_day_in[d] - by_day_out[d]
        series_stock.append(running)

    kpi_in = total_in
    kpi_out = total_out
    kpi_net = total_in - total_out

    # Stock current = sum(Item.quantity) with same filters (finis & user)
    item_q = Item.query
    if finis:
        item_q = item_q.filter(Item.finis_code.ilike(f"%{finis}%"))
    if selected_user_id:
        item_q = item_q.filter(Item.updated_by_id == selected_user_id)  # or created_by? we use updated_by as "owner of last change"
    kpi_stock_current = sum(i.quantity for i in item_q.all())

    users_list = User.query.order_by(User.username).all()
    return render_page(
        stats_tpl,
        start_str=start_str,
        end_str=end_str,
        users_list=users_list,
        selected_user_id=selected_user_id,
        kpi_in=kpi_in,
        kpi_out=kpi_out,
        kpi_net=kpi_net,
        kpi_stock_current=kpi_stock_current,
        labels=labels,
        series_in=series_in,
        series_out=series_out,
        series_stock=series_stock,
        movements=movements_list,
    )

# ----------------------------------------------------------------------------
# Bootstrap DBs and default admin
# ----------------------------------------------------------------------------
def _ensure_is_active_column():
    try:
        from sqlalchemy import text
        cols = db.session.execute(text("PRAGMA table_info(user)")).fetchall()
        names = [c[1] for c in cols] if cols else []
        if "is_active" not in names:
            db.session.execute(text("ALTER TABLE user ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
            db.session.commit()
            print("[MIGRATION] Aggiunta colonna is_active alla tabella user (DB: users).")
    except Exception as e:
        print("[MIGRATION] Warning:", e)

with app.app_context():
    db.create_all()

    # ensure is_active column if db already existed
    _ensure_is_active_column()

    if User.query.count() == 0:
        admin_user = os.environ.get("ADMIN_USER")
        admin_pass = os.environ.get("ADMIN_PASS")
        if admin_user and admin_pass:
            u = User(username=admin_user, role="admin", is_active=True)
            u.set_password(admin_pass)
            db.session.add(u)
            db.session.commit()
            print(f"[INIT] Creato utente admin '{admin_user}' (DB: users).")
        else:
            u = User(username="admin", role="admin", is_active=True)
            u.set_password("admin")
            db.session.add(u)
            db.session.commit()
            print("[INIT] Creato admin di sviluppo users='admin'/'admin'. Cambiare in produzione!")

# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
