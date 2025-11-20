"""
Aplikasi Pendataan Mahasiswa - Single-file Flask App
Fitur:
- Login dengan 3 hak akses: admin, dosen, mahasiswa
- Data pribadi mahasiswa
- Kelas (mata kuliah), jadwal, nilai
- Tampilan interaktif memakai Bootstrap 5 (CDN)

Cara pakai:
1. Pasang dependensi: pip install flask
2. Jalankan: python Aplikasi_Pendataan_Mahasiswa.py
3. Buka browser: http://127.0.0.1:5000

Akun awal:
- Admin: username=admin password=admin123
- Dosen: username=dosen1 password=dosen123
- Mahasiswa: username=mahasiswa1 password=mahasiswa123

Catatan keamanan: ini contoh belajar. Jangan gunakan password plaintext di produksi.
"""

from flask import Flask, render_template_string, request, redirect, url_for, session, flash, g
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

DB_PATH = 'mahasiswa.db'
app = Flask(__name__)
app.secret_key = 'ganti_dengan_rahasia_yang_kuat'

# -----------------
# Database helpers
# -----------------

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid

# -----------------
# Init DB
# -----------------

def init_db():
    if os.path.exists(DB_PATH):
        return
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    # users: id, username, password_hash, role, full_name
    c.execute('''CREATE TABLE users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE,
                 password_hash TEXT,
                 role TEXT,
                 full_name TEXT
                 )''')
    # mahasiswa: id->users.id, nim, alamat, phone
    c.execute('''CREATE TABLE mahasiswa (
                 id INTEGER PRIMARY KEY,
                 nim TEXT,
                 alamat TEXT,
                 phone TEXT
                 )''')
    # dosen: id->users.id, nidn
    c.execute('''CREATE TABLE dosen (
                 id INTEGER PRIMARY KEY,
                 nidn TEXT
                 )''')
    # mata_kuliah: id, kode, nama, sks
    c.execute('''CREATE TABLE mata_kuliah (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 kode TEXT,
                 nama TEXT,
                 sks INTEGER
                 )''')
    # kelas: id, nama, mata_kuliah_id, dosen_id
    c.execute('''CREATE TABLE kelas (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 nama TEXT,
                 mata_kuliah_id INTEGER,
                 dosen_id INTEGER,
                 FOREIGN KEY(mata_kuliah_id) REFERENCES mata_kuliah(id),
                 FOREIGN KEY(dosen_id) REFERENCES dosen(id)
                 )''')
    # jadwal: id, kelas_id, hari, jam
    c.execute('''CREATE TABLE jadwal (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 kelas_id INTEGER,
                 hari TEXT,
                 jam TEXT,
                 FOREIGN KEY(kelas_id) REFERENCES kelas(id)
                 )''')
    # enroll: id, mahasiswa_id, kelas_id
    c.execute('''CREATE TABLE enroll (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 mahasiswa_id INTEGER,
                 kelas_id INTEGER,
                 FOREIGN KEY(mahasiswa_id) REFERENCES mahasiswa(id),
                 FOREIGN KEY(kelas_id) REFERENCES kelas(id)
                 )''')
    # nilai: id, enroll_id, nilai_angka
    c.execute('''CREATE TABLE nilai (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 enroll_id INTEGER,
                 nilai_angka REAL,
                 FOREIGN KEY(enroll_id) REFERENCES enroll(id)
                 )''')

    # seed users
    from werkzeug.security import generate_password_hash
    admin_pw = generate_password_hash('admin123')
    dosen_pw = generate_password_hash('dosen123')
    mhs_pw = generate_password_hash('mahasiswa123')

    c.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
              ('admin', admin_pw, 'admin', 'Administrator'))
    c.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
              ('dosen1', dosen_pw, 'dosen', 'Dr. Dosen Satu'))
    c.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
              ('mahasiswa1', mhs_pw, 'mahasiswa', 'Budi Mahasiswa'))

    # link mahasiswa and dosen
    admin_id = c.execute("SELECT id FROM users WHERE username=?", ('admin',)).fetchone()[0]
    dosen_id = c.execute("SELECT id FROM users WHERE username=?", ('dosen1',)).fetchone()[0]
    mhs_id = c.execute("SELECT id FROM users WHERE username=?", ('mahasiswa1',)).fetchone()[0]

    c.execute("INSERT INTO dosen (id, nidn) VALUES (?,?)", (dosen_id, 'NIDN12345'))
    c.execute("INSERT INTO mahasiswa (id, nim, alamat, phone) VALUES (?,?,?,?)", (mhs_id, '20231001', 'Jl. Merdeka 1', '081234567890'))

    # seed mata kuliah, kelas, jadwal, enroll
    c.execute("INSERT INTO mata_kuliah (kode, nama, sks) VALUES (?,?,?)", ('JARKOM101', 'Jaringan Komputer', 3))
    mk_id = c.lastrowid
    c.execute("INSERT INTO kelas (nama, mata_kuliah_id, dosen_id) VALUES (?,?,?)", ('Jarkom - Pagi', mk_id, dosen_id))
    kelas_id = c.lastrowid
    c.execute("INSERT INTO jadwal (kelas_id, hari, jam) VALUES (?,?,?)", (kelas_id, 'Senin', '08:00-10:00'))
    c.execute("INSERT INTO enroll (mahasiswa_id, kelas_id) VALUES (?,?)", (mhs_id, kelas_id))
    enroll_id = c.lastrowid
    c.execute("INSERT INTO nilai (enroll_id, nilai_angka) VALUES (?,?)", (enroll_id, 85.0))

    db.commit()
    db.close()

# -----------------
# Auth helpers
# -----------------

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Akses ditolak: hak akses diperlukan: %s' % role)
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# -----------------
# Templates (simple, inline for single-file)
# -----------------

base_html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title or 'Aplikasi Mahasiswa' }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { padding-top: 70px; }
      .card-glow { box-shadow: 0 6px 18px rgba(0,0,0,0.08); border-radius: 12px; }
    </style>
  </head>
  <body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary fixed-top">
      <div class="container-fluid">
        <a class="navbar-brand" href="{{ url_for('index') }}">SI-Mahasiswa</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navBar" aria-controls="navBar" aria-expanded="false" aria-label="Toggle navigation">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navBar">
          <ul class="navbar-nav me-auto mb-2 mb-lg-0">
            {% if session.get('user_id') %}
              {% if session.get('role') == 'admin' %}
                <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Admin</a></li>
              {% elif session.get('role') == 'dosen' %}
                <li class="nav-item"><a class="nav-link" href="{{ url_for('dosen_dashboard') }}">Dosen</a></li>
              {% else %}
                <li class="nav-item"><a class="nav-link" href="{{ url_for('mhs_dashboard') }}">Mahasiswa</a></li>
              {% endif %}
            {% endif %}
          </ul>
          <ul class="navbar-nav">
            {% if session.get('user_id') %}
              <li class="nav-item"><a class="nav-link">{{ session.get('full_name') }} ({{ session.get('role') }})</a></li>
              <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">Logout</a></li>
            {% else %}
              <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">Login</a></li>
            {% endif %}
          </ul>
        </div>
      </div>
    </nav>

    <div class="container">
      {% with messages = get_flashed_messages() %}
        {% if messages %}
          {% for m in messages %}
            <div class="alert alert-warning">{{ m }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}
      {{ body | safe }}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
"""

# -----------------
# Routes: index & auth
# -----------------

@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        if role == 'dosen':
            return redirect(url_for('dosen_dashboard'))
        return redirect(url_for('mhs_dashboard'))
    body = '''
    <div class="row justify-content-center">
      <div class="col-md-8">
        <div class="card card-glow p-4">
          <h3>Selamat datang di Aplikasi Pendataan Mahasiswa</h3>
          <p>Silakan login menggunakan akun yang tersedia. Aplikasi ini contoh pembelajaran untuk SMK TKJ.</p>
          <a class="btn btn-primary" href="/login">Login</a>
        </div>
      </div>
    </div>
    '''
    return render_template_string(base_html, body=body)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = query_db('SELECT * FROM users WHERE username=?', (username,), one=True)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            flash('Login berhasil')
            return redirect(url_for('index'))
        else:
            flash('Login gagal: username atau password salah')
    body = '''
    <div class="row justify-content-center">
      <div class="col-md-6">
        <div class="card card-glow p-4">
          <h4>Login</h4>
          <form method="post">
            <div class="mb-3">
              <label class="form-label">Username</label>
              <input class="form-control" name="username" required>
            </div>
            <div class="mb-3">
              <label class="form-label">Password</label>
              <input type="password" class="form-control" name="password" required>
            </div>
            <button class="btn btn-success">Login</button>
          </form>
          <hr>
          <small>Akun contoh: admin/admin123 | dosen1/dosen123 | mahasiswa1/mahasiswa123</small>
        </div>
      </div>
    </div>
    '''
    return render_template_string(base_html, body=body)

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout')
    return redirect(url_for('index'))

# -----------------
# Admin area
# -----------------

@app.route('/admin')
@login_required(role='admin')
def admin_dashboard():
    # summary counts
    total_mhs = query_db('SELECT COUNT(*) as c FROM mahasiswa', one=True)['c']
    total_dosen = query_db("SELECT COUNT(*) as c FROM dosen", one=True)['c']
    total_mk = query_db('SELECT COUNT(*) as c FROM mata_kuliah', one=True)['c']
    body = f'''
    <div class="row">
      <div class="col-md-12">
        <div class="card card-glow p-3">
          <h4>Dashboard Admin</h4>
          <div class="row text-center mt-3">
            <div class="col-md-4"><div class="p-3 border rounded">Mahasiswa<br><strong>{total_mhs}</strong></div></div>
            <div class="col-md-4"><div class="p-3 border rounded">Dosen<br><strong>{total_dosen}</strong></div></div>
            <div class="col-md-4"><div class="p-3 border rounded">Mata Kuliah<br><strong>{total_mk}</strong></div></div>
          </div>
          <hr>
          <a class="btn btn-primary" href="{url_for('manage_mahasiswa')}">Kelola Mahasiswa</a>
          <a class="btn btn-secondary" href="{url_for('manage_dosen')}">Kelola Dosen</a>
          <a class="btn btn-info" href="{url_for('manage_mata_kuliah')}">Kelola Mata Kuliah</a>
        </div>
      </div>
    </div>
    '''
    return render_template_string(base_html, body=body)

# Manage mahasiswa
@app.route('/admin/mahasiswa')
@login_required(role='admin')
def manage_mahasiswa():
    mhs = query_db('SELECT u.id, u.username, u.full_name, m.nim, m.alamat, m.phone FROM users u JOIN mahasiswa m ON u.id=m.id')
    rows = ''
    for r in mhs:
        rows += f"""
        <tr>
          <td>{r['id']}</td>
          <td>{r['username']}</td>
          <td>{r['full_name']}</td>
          <td>{r['nim']}</td>
          <td>{r['alamat']}</td>
          <td>{r['phone']}</td>
          <td>
            <a class='btn btn-sm btn-warning' href='{url_for('edit_mahasiswa', mhs_id=r['id'])}'>Edit</a>
            <a class='btn btn-sm btn-danger' href='{url_for('delete_mahasiswa', mhs_id=r['id'])}' onclick="return confirm('Hapus?')">Hapus</a>
          </td>
        </tr>
        """
    body = f"""
    <div class='card card-glow p-3'>
      <h4>Daftar Mahasiswa</h4>
      <a class='btn btn-success' href='{url_for('add_mahasiswa')}'>Tambah Mahasiswa</a>
      <table class='table table-striped mt-3'>
        <thead><tr><th>ID</th><th>Username</th><th>Nama</th><th>NIM</th><th>Alamat</th><th>HP</th><th>Aksi</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """
    return render_template_string(base_html, body=body)

@app.route('/admin/mahasiswa/add', methods=['GET', 'POST'])
@login_required(role='admin')
def add_mahasiswa():
    if request.method == 'POST':
        username = request.form['username']
        full_name = request.form['full_name']
        password = request.form['password']
        nim = request.form['nim']
        alamat = request.form['alamat']
        phone = request.form['phone']
        pw_hash = generate_password_hash(password)
        try:
            uid = execute_db('INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)',
                            (username, pw_hash, 'mahasiswa', full_name))
            execute_db('INSERT INTO mahasiswa (id, nim, alamat, phone) VALUES (?,?,?,?)', (uid, nim, alamat, phone))
            flash('Mahasiswa ditambahkan')
            return redirect(url_for('manage_mahasiswa'))
        except Exception as e:
            flash('Gagal menambah: ' + str(e))
    body = '''
    <div class='card p-3'>
      <h4>Tambah Mahasiswa</h4>
      <form method='post'>
        <div class='mb-2'><label>Username</label><input class='form-control' name='username' required></div>
        <div class='mb-2'><label>Password</label><input class='form-control' name='password' required></div>
        <div class='mb-2'><label>Nama Lengkap</label><input class='form-control' name='full_name' required></div>
        <div class='mb-2'><label>NIM</label><input class='form-control' name='nim'></div>
        <div class='mb-2'><label>Alamat</label><input class='form-control' name='alamat'></div>
        <div class='mb-2'><label>HP</label><input class='form-control' name='phone'></div>
        <button class='btn btn-primary'>Simpan</button>
      </form>
    </div>
    '''
    return render_template_string(base_html, body=body)

@app.route('/admin/mahasiswa/edit/<int:mhs_id>', methods=['GET', 'POST'])
@login_required(role='admin')
def edit_mahasiswa(mhs_id):
    user = query_db('SELECT u.*, m.nim, m.alamat, m.phone FROM users u JOIN mahasiswa m ON u.id=m.id WHERE u.id=?', (mhs_id,), one=True)
    if not user:
        flash('Mahasiswa tidak ditemukan')
        return redirect(url_for('manage_mahasiswa'))
    if request.method == 'POST':
        full_name = request.form['full_name']
        nim = request.form['nim']
        alamat = request.form['alamat']
        phone = request.form['phone']
        execute_db('UPDATE users SET full_name=? WHERE id=?', (full_name, mhs_id))
        execute_db('UPDATE mahasiswa SET nim=?, alamat=?, phone=? WHERE id=?', (nim, alamat, phone, mhs_id))
        flash('Data mahasiswa diperbarui')
        return redirect(url_for('manage_mahasiswa'))
    body = f"""
    <div class='card p-3'>
      <h4>Edit Mahasiswa</h4>
      <form method='post'>
        <div class='mb-2'><label>Nama Lengkap</label><input class='form-control' name='full_name' value="{user['full_name']}" required></div>
        <div class='mb-2'><label>NIM</label><input class='form-control' name='nim' value="{user['nim'] or ''}"></div>
        <div class='mb-2'><label>Alamat</label><input class='form-control' name='alamat' value="{user['alamat'] or ''}"></div>
        <div class='mb-2'><label>HP</label><input class='form-control' name='phone' value="{user['phone'] or ''}"></div>
        <button class='btn btn-primary'>Simpan</button>
      </form>
    </div>
    """
    return render_template_string(base_html, body=body)

@app.route('/admin/mahasiswa/delete/<int:mhs_id>')
@login_required(role='admin')
def delete_mahasiswa(mhs_id):
    try:
        execute_db('DELETE FROM nilai WHERE enroll_id IN (SELECT id FROM enroll WHERE mahasiswa_id=?)', (mhs_id,))
        execute_db('DELETE FROM enroll WHERE mahasiswa_id=?', (mhs_id,))
        execute_db('DELETE FROM mahasiswa WHERE id=?', (mhs_id,))
        execute_db('DELETE FROM users WHERE id=?', (mhs_id,))
        flash('Mahasiswa dihapus')
    except Exception as e:
        flash('Gagal hapus: ' + str(e))
    return redirect(url_for('manage_mahasiswa'))

# Manage dosen
@app.route('/admin/dosen')
@login_required(role='admin')
def manage_dosen():
    dsn = query_db('SELECT u.id, u.username, u.full_name, d.nidn FROM users u JOIN dosen d ON u.id=d.id')
    rows = ''
    for r in dsn:
        rows += f"""
        <tr><td>{r['id']}</td><td>{r['username']}</td><td>{r['full_name']}</td><td>{r['nidn']}</td>
        <td><a class='btn btn-sm btn-danger' href='{url_for('delete_dosen', dosen_id=r['id'])}' onclick="return confirm('Hapus?')">Hapus</a></td></tr>
        """
    body = f"""
    <div class='card p-3'>
      <h4>Daftar Dosen</h4>
      <a class='btn btn-success' href='{url_for('add_dosen')}'>Tambah Dosen</a>
      <table class='table table-striped mt-3'><thead><tr><th>ID</th><th>Username</th><th>Nama</th><th>NIDN</th><th>Aksi</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    """
    return render_template_string(base_html, body=body)

@app.route('/admin/dosen/add', methods=['GET', 'POST'])
@login_required(role='admin')
def add_dosen():
    if request.method == 'POST':
        username = request.form['username']
        full_name = request.form['full_name']
        password = request.form['password']
        nidn = request.form['nidn']
        pw_hash = generate_password_hash(password)
        try:
            uid = execute_db('INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)',
                            (username, pw_hash, 'dosen', full_name))
            execute_db('INSERT INTO dosen (id, nidn) VALUES (?,?)', (uid, nidn))
            flash('Dosen ditambahkan')
            return redirect(url_for('manage_dosen'))
        except Exception as e:
            flash('Gagal tambah dosen: ' + str(e))
    body = '''
    <div class='card p-3'>
      <h4>Tambah Dosen</h4>
      <form method='post'>
        <div class='mb-2'><label>Username</label><input class='form-control' name='username' required></div>
        <div class='mb-2'><label>Password</label><input class='form-control' name='password' required></div>
        <div class='mb-2'><label>Nama Lengkap</label><input class='form-control' name='full_name' required></div>
        <div class='mb-2'><label>NIDN</label><input class='form-control' name='nidn'></div>
        <button class='btn btn-primary'>Simpan</button>
      </form>
    </div>
    '''
    return render_template_string(base_html, body=body)

@app.route('/admin/dosen/delete/<int:dosen_id>')
@login_required(role='admin')
def delete_dosen(dosen_id):
    try:
        execute_db('DELETE FROM dosen WHERE id=?', (dosen_id,))
        execute_db('DELETE FROM users WHERE id=?', (dosen_id,))
        flash('Dosen dihapus')
    except Exception as e:
        flash('Gagal hapus dosen: ' + str(e))
    return redirect(url_for('manage_dosen'))

# Manage mata kuliah & kelas
@app.route('/admin/mata_kuliah')
@login_required(role='admin')
def manage_mata_kuliah():
    mks = query_db('SELECT mk.*, k.nama as kelas_nama, u.full_name as dosen_name FROM mata_kuliah mk LEFT JOIN kelas k ON mk.id=k.mata_kuliah_id LEFT JOIN dosen d ON k.dosen_id=d.id LEFT JOIN users u ON d.id=u.id')
    rows = ''
    for r in mks:
        rows += f"""
        <tr><td>{r['id']}</td><td>{r['kode']}</td><td>{r['nama']}</td><td>{r['sks']}</td><td>{r['kelas_nama'] or '-'}</td><td>{r['dosen_name'] or '-'}</td></tr>
        """
    body = f"""
    <div class='card p-3'>
      <h4>Mata Kuliah & Kelas</h4>
      <a class='btn btn-success' href='{url_for('add_mata_kuliah')}'>Tambah Mata Kuliah</a>
      <a class='btn btn-secondary' href='{url_for('manage_kelas')}'>Kelola Kelas</a>
      <table class='table table-striped mt-3'><thead><tr><th>ID</th><th>Kode</th><th>Nama</th><th>SKS</th><th>Kelas</th><th>Dosen</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    """
    return render_template_string(base_html, body=body)

@app.route('/admin/mata_kuliah/add', methods=['GET', 'POST'])
@login_required(role='admin')
def add_mata_kuliah():
    if request.method == 'POST':
        kode = request.form['kode']
        nama = request.form['nama']
        sks = int(request.form.get('sks') or 0)
        execute_db('INSERT INTO mata_kuliah (kode, nama, sks) VALUES (?,?,?)', (kode, nama, sks))
        flash('Mata kuliah ditambahkan')
        return redirect(url_for('manage_mata_kuliah'))
    body = '''
    <div class='card p-3'>
      <h4>Tambah Mata Kuliah</h4>
      <form method='post'>
        <div class='mb-2'><label>Kode</label><input class='form-control' name='kode' required></div>
        <div class='mb-2'><label>Nama</label><input class='form-control' name='nama' required></div>
        <div class='mb-2'><label>SKS</label><input type='number' class='form-control' name='sks' value='3'></div>
        <button class='btn btn-primary'>Simpan</button>
      </form>
    </div>
    '''
    return render_template_string(base_html, body=body)

@app.route('/admin/kelas')
@login_required(role='admin')
def manage_kelas():
    kelas = query_db('SELECT k.*, mk.nama as mk_nama, u.full_name as dosen_name FROM kelas k JOIN mata_kuliah mk ON k.mata_kuliah_id=mk.id LEFT JOIN dosen d ON k.dosen_id=d.id LEFT JOIN users u ON d.id=u.id')
    dosen = query_db('SELECT u.id, u.full_name FROM users u JOIN dosen d ON u.id=d.id')
    mk = query_db('SELECT * FROM mata_kuliah')
    rows = ''
    for r in kelas:
        rows += f"""
        <tr><td>{r['id']}</td><td>{r['nama']}</td><td>{r['mk_nama']}</td><td>{r['dosen_name'] or '-'}</td>
        <td><a class='btn btn-sm btn-primary' href='{url_for('view_kelas', kelas_id=r['id'])}'>Lihat</a></td></tr>
        """
    options_dosen = ''.join([f"<option value='{d['id']}'>{d['full_name']}</option>" for d in dosen])
    options_mk = ''.join([f"<option value='{m['id']}'>{m['nama']}</option>" for m in mk])
    body = f"""
    <div class='card p-3'>
      <h4>Kelola Kelas</h4>
      <form method='post' action='{url_for('add_kelas')}'>
        <div class='row'>
          <div class='col-md-4'><label>Nama Kelas</label><input class='form-control' name='nama' required></div>
          <div class='col-md-4'><label>Mata Kuliah</label><select class='form-control' name='mata_kuliah_id'>{options_mk}</select></div>
          <div class='col-md-4'><label>Dosen</label><select class='form-control' name='dosen_id'>{options_dosen}</select></div>
        </div>
        <button class='btn btn-success mt-2'>Buat Kelas</button>
      </form>
      <hr>
      <table class='table table-striped mt-3'><thead><tr><th>ID</th><th>Nama</th><th>Mata Kuliah</th><th>Dosen</th><th>Aksi</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    """
    return render_template_string(base_html, body=body)

@app.route('/admin/kelas/add', methods=['POST'])
@login_required(role='admin')
def add_kelas():
    nama = request.form['nama']
    mata_kuliah_id = int(request.form['mata_kuliah_id'])
    dosen_id = int(request.form['dosen_id'])
    execute_db('INSERT INTO kelas (nama, mata_kuliah_id, dosen_id) VALUES (?,?,?)', (nama, mata_kuliah_id, dosen_id))
    flash('Kelas dibuat')
    return redirect(url_for('manage_kelas'))

@app.route('/admin/kelas/<int:kelas_id>')
@login_required(role='admin')
def view_kelas(kelas_id):
    k = query_db('SELECT k.*, mk.nama as mk_nama, u.full_name as dosen_name FROM kelas k JOIN mata_kuliah mk ON k.mata_kuliah_id=mk.id LEFT JOIN dosen d ON k.dosen_id=d.id LEFT JOIN users u ON d.id=u.id WHERE k.id=?', (kelas_id,), one=True)
    enrolled = query_db('SELECT e.id, u.full_name, u.username FROM enroll e JOIN mahasiswa m ON e.mahasiswa_id=m.id JOIN users u ON m.id=u.id WHERE e.kelas_id=?', (kelas_id,))
    rows = ''.join([f"<tr><td>{r['id']}</td><td>{r['username']}</td><td>{r['full_name']}</td><td><a class='btn btn-sm btn-danger' href='{url_for('unenroll', enroll_id=r['id'], kelas_id=kelas_id)}'>Unenroll</a></td></tr>" for r in enrolled])
    # simple enroll form for admin
    mhs_opts = ''.join([f"<option value='{m['id']}'>{m['full_name']} ({m['nim']})</option>" for m in query_db('SELECT id, nim, full_name FROM mahasiswa m JOIN users u ON m.id=u.id')])
    body = f"""
    <div class='card p-3'>
      <h4>Detail Kelas: {k['nama']}</h4>
      <p>Mata Kuliah: {k['mk_nama']} | Dosen: {k['dosen_name'] or '-'}</p>
      <form method='post' action='{url_for('enroll_mahasiswa', kelas_id=kelas_id)}'>
        <div class='row'><div class='col-md-8'><select class='form-control' name='mahasiswa_id'>{mhs_opts}</select></div><div class='col-md-4'><button class='btn btn-success'>Enroll Mahasiswa</button></div></div>
      </form>
      <hr>
      <h5>Daftar Mahasiswa</h5>
      <table class='table'><thead><tr><th>ID</th><th>Username</th><th>Nama</th><th>Aksi</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    """
    return render_template_string(base_html, body=body)

@app.route('/admin/kelas/<int:kelas_id>/enroll', methods=['POST'])
@login_required(role='admin')
def enroll_mahasiswa(kelas_id):
    mahasiswa_id = int(request.form['mahasiswa_id'])
    execute_db('INSERT INTO enroll (mahasiswa_id, kelas_id) VALUES (?,?)', (mahasiswa_id, kelas_id))
    flash('Mahasiswa di-enroll ke kelas')
    return redirect(url_for('view_kelas', kelas_id=kelas_id))

@app.route('/admin/kelas/<int:kelas_id>/unenroll/<int:enroll_id>')
@login_required(role='admin')
def unenroll(kelas_id, enroll_id):
    execute_db('DELETE FROM nilai WHERE enroll_id=?', (enroll_id,))
    execute_db('DELETE FROM enroll WHERE id=?', (enroll_id,))
    flash('Mahasiswa dikeluarkan dari kelas')
    return redirect(url_for('view_kelas', kelas_id=kelas_id))

# jadwal
@app.route('/admin/jadwal', methods=['GET','POST'])
@login_required(role='admin')
def manage_jadwal():
    if request.method == 'POST':
        kelas_id = int(request.form['kelas_id'])
        hari = request.form['hari']
        jam = request.form['jam']
        execute_db('INSERT INTO jadwal (kelas_id, hari, jam) VALUES (?,?,?)', (kelas_id, hari, jam))
        flash('Jadwal ditambahkan')
        return redirect(url_for('manage_jadwal'))
    jadwals = query_db('SELECT j.*, k.nama as kelas_nama FROM jadwal j JOIN kelas k ON j.kelas_id=k.id')
    kelas_opts = ''.join([f"<option value='{k['id']}'>{k['nama']}</option>" for k in query_db('SELECT id, nama FROM kelas')])
    rows = ''.join([f"<tr><td>{r['id']}</td><td>{r['kelas_nama']}</td><td>{r['hari']}</td><td>{r['jam']}</td></tr>" for r in jadwals])
    body = f"""
    <div class='card p-3'>
      <h4>Kelola Jadwal</h4>
      <form method='post'>
        <div class='row'><div class='col-md-4'><select class='form-control' name='kelas_id'>{kelas_opts}</select></div>
        <div class='col-md-4'><input class='form-control' name='hari' placeholder='Senin'></div>
        <div class='col-md-4'><input class='form-control' name='jam' placeholder='08:00-10:00'></div></div>
        <button class='btn btn-success mt-2'>Tambah Jadwal</button>
      </form>
      <hr>
      <table class='table'><thead><tr><th>ID</th><th>Kelas</th><th>Hari</th><th>Jam</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    """
    return render_template_string(base_html, body=body)

# -----------------
# Dosen area
# -----------------

@app.route('/dosen')
@login_required(role='dosen')
def dosen_dashboard():
    # list kelas yang dia ampu
    kelas = query_db('SELECT k.*, mk.nama as mk_nama FROM kelas k JOIN mata_kuliah mk ON k.mata_kuliah_id=mk.id WHERE k.dosen_id=?', (session['user_id'],))
    rows = ''.join([f"<li class='list-group-item'><a href='{url_for('dosen_view_kelas', kelas_id=k['id'])}'>{k['nama']} - {k['mk_nama']}</a></li>" for k in kelas])
    body = f"""
    <div class='card p-3'>
      <h4>Dashboard Dosen</h4>
      <ul class='list-group'>{rows}</ul>
    </div>
    """
    return render_template_string(base_html, body=body)

@app.route('/dosen/kelas/<int:kelas_id>')
@login_required(role='dosen')
def dosen_view_kelas(kelas_id):
    k = query_db('SELECT k.*, mk.nama as mk_nama FROM kelas k JOIN mata_kuliah mk ON k.mata_kuliah_id=mk.id WHERE k.id=? AND k.dosen_id=?', (kelas_id, session['user_id']), one=True)
    if not k:
        flash('Kelas tidak ditemukan atau Anda bukan pengampu')
        return redirect(url_for('dosen_dashboard'))
    enrolled = query_db('SELECT e.id, u.full_name, u.username, n.nilai_angka FROM enroll e JOIN mahasiswa m ON e.mahasiswa_id=m.id JOIN users u ON m.id=u.id LEFT JOIN nilai n ON n.enroll_id=e.id WHERE e.kelas_id=?', (kelas_id,))
    rows = ''.join([f"<tr><td>{r['id']}</td><td>{r['username']}</td><td>{r['full_name']}</td><td>{r['nilai_angka'] or '-'}</td><td><a class='btn btn-sm btn-primary' href='{url_for('dosen_set_nilai', enroll_id=r['id'])}'>Set Nilai</a></td></tr>" for r in enrolled])
    body = f"""
    <div class='card p-3'>
      <h4>{k['nama']} - {k['mk_nama']}</h4>
      <table class='table'><thead><tr><th>ID Enroll</th><th>Username</th><th>Nama</th><th>Nilai</th><th>Aksi</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    """
    return render_template_string(base_html, body=body)

@app.route('/dosen/nilai/set/<int:enroll_id>', methods=['GET','POST'])
@login_required(role='dosen')
def dosen_set_nilai(enroll_id):
    # check that this enrollment belongs to a class the dosen teaches
    e = query_db('SELECT e.*, k.dosen_id FROM enroll e JOIN kelas k ON e.kelas_id=k.id WHERE e.id=?', (enroll_id,), one=True)
    if not e or e['dosen_id'] != session['user_id']:
        flash('Akses ditolak')
        return redirect(url_for('dosen_dashboard'))
    if request.method == 'POST':
        nilai = float(request.form['nilai'])
        existing = query_db('SELECT * FROM nilai WHERE enroll_id=?', (enroll_id,), one=True)
        if existing:
            execute_db('UPDATE nilai SET nilai_angka=? WHERE enroll_id=?', (nilai, enroll_id))
        else:
            execute_db('INSERT INTO nilai (enroll_id, nilai_angka) VALUES (?,?)', (enroll_id, nilai))
        flash('Nilai tersimpan')
        return redirect(url_for('dosen_view_kelas', kelas_id=e['kelas_id']))
    body = f"""
    <div class='card p-3'>
      <h4>Set Nilai</h4>
      <form method='post'>
        <div class='mb-2'><label>Nilai</label><input class='form-control' name='nilai' required></div>
        <button class='btn btn-primary'>Simpan</button>
      </form>
    </div>
    """
    return render_template_string(base_html, body=body)

# -----------------
# Mahasiswa area
# -----------------

@app.route('/mahasiswa')
@login_required(role='mahasiswa')
def mhs_dashboard():
    uid = session['user_id']
    user = query_db('SELECT u.*, m.nim, m.alamat, m.phone FROM users u JOIN mahasiswa m ON u.id=m.id WHERE u.id=?', (uid,), one=True)
    # kelas dan nilai
    kelas = query_db('SELECT k.nama as kelas_nama, mk.nama as mk_nama, n.nilai_angka, j.hari, j.jam FROM enroll e JOIN kelas k ON e.kelas_id=k.id JOIN mata_kuliah mk ON k.mata_kuliah_id=mk.id LEFT JOIN nilai n ON n.enroll_id=e.id LEFT JOIN jadwal j ON j.kelas_id=k.id WHERE e.mahasiswa_id=?', (uid,))
    rows = ''.join([f"<tr><td>{r['mk_nama']}</td><td>{r['kelas_nama']}</td><td>{r['hari'] or '-'}</td><td>{r['jam'] or '-'}</td><td>{r['nilai_angka'] or '-'}</td></tr>" for r in kelas])
    body = f"""
    <div class='card p-3'>
      <h4>Profil Mahasiswa</h4>
      <p><strong>{user['full_name']}</strong> ({user['nim']})</p>
      <p>Alamat: {user['alamat']} | HP: {user['phone']}</p>
      <hr>
      <h5>Jadwal & Nilai</h5>
      <table class='table'><thead><tr><th>Mata Kuliah</th><th>Kelas</th><th>Hari</th><th>Jam</th><th>Nilai</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    """
    return render_template_string(base_html, body=body)

# -----------------
# Run app
# -----------------

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
