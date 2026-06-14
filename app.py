from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'prisgen-ladyc-velvet-2026-xK9#mP2')

# ── Database ──────────────────────────────────────────────────────────────────
raw_db_url = os.environ.get('DATABASE_URL', 'sqlite:///prisgen.db')
if raw_db_url.startswith('postgres://'):
    raw_db_url = raw_db_url.replace('postgres://', 'postgresql+pg8000://', 1)
elif raw_db_url.startswith('postgresql://'):
    raw_db_url = raw_db_url.replace('postgresql://', 'postgresql+pg8000://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

db = SQLAlchemy(app)

# ── Models ────────────────────────────────────────────────────────────────────
class Product(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), nullable=False)
    price       = db.Column(db.Float, nullable=False)
    category    = db.Column(db.String(60), default='General')
    desc        = db.Column(db.Text, default='')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    visible     = db.Column(db.Boolean, default=True)
    image1        = db.Column(db.String(500), nullable=True)
    image2        = db.Column(db.String(500), nullable=True)
    image3        = db.Column(db.String(500), nullable=True)
    image4        = db.Column(db.String(500), nullable=True)
    stock         = db.Column(db.Integer, nullable=True)      # None = unlimited
    limited_stock = db.Column(db.Boolean, default=False)      # manual toggle

class ActivityLog(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip        = db.Column(db.String(60))
    event     = db.Column(db.String(200))
    success   = db.Column(db.Boolean, default=True)
    device    = db.Column(db.String(200), default='Unknown')
    browser   = db.Column(db.String(200), default='Unknown')

class LoginAttempt(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    ip        = db.Column(db.String(60))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class SelarCounter(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    count   = db.Column(db.Integer, default=0)  # total checkouts ever

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_password():
    try:
        with open('config.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('password='):
                    return line.split('=', 1)[1].strip()
    except FileNotFoundError:
        pass
    return 'LadyC_PRISgen2026'

def get_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

def get_device():
    ua = request.headers.get('User-Agent', '')
    if 'iPhone' in ua:      return 'iPhone'
    elif 'iPad' in ua:      return 'iPad'
    elif 'Android' in ua:
        try:
            start = ua.index('(') + 1
            end   = ua.index(')')
            parts = ua[start:end].split(';')
            return parts[2].strip() if len(parts) > 2 else 'Android Device'
        except: return 'Android Device'
    elif 'Windows' in ua:   return 'Windows PC'
    elif 'Macintosh' in ua: return 'Mac'
    else:                   return 'Unknown Device'

def get_browser():
    ua = request.headers.get('User-Agent', '')
    if 'Chrome' in ua and 'Edg' not in ua and 'OPR' not in ua: return 'Chrome'
    elif 'Firefox' in ua:   return 'Firefox'
    elif 'Safari' in ua and 'Chrome' not in ua: return 'Safari'
    elif 'Edg' in ua:       return 'Edge'
    elif 'OPR' in ua:       return 'Opera'
    else:                   return 'Unknown Browser'

def log_event(event, success=True):
    try:
        db.session.add(ActivityLog(
            ip=get_ip(), event=event, success=success,
            device=get_device(), browser=get_browser()
        ))
        db.session.commit()
    except: pass

def is_admin():
    return session.get('is_admin', False)

def is_blocked(ip):
    window = datetime.utcnow() - timedelta(minutes=30)
    return LoginAttempt.query.filter(
        LoginAttempt.ip == ip,
        LoginAttempt.timestamp >= window
    ).count() >= 5

def record_failed_attempt(ip):
    db.session.add(LoginAttempt(ip=ip))
    db.session.commit()

def clear_attempts(ip):
    LoginAttempt.query.filter_by(ip=ip).delete()
    db.session.commit()

def product_to_dict(p):
    images = [i for i in [p.image1, p.image2, p.image3, p.image4] if i]
    stock  = p.stock if p.stock is not None else None
    return {
        'id': p.id, 'name': p.name, 'price': p.price,
        'category': p.category, 'desc': p.desc,
        'visible': p.visible,
        'is_new':        (datetime.utcnow() - p.created_at).days < 14,
        'images':        images,
        'image':         p.image1 or '',
        'stock':         stock,
        'limited_stock': bool(p.limited_stock),
        'sold_out':      stock is not None and stock <= 0
    }

# ── Abandoned Cart model ──────────────────────────────────────────────────────
class AbandonedCart(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    phone      = db.Column(db.String(30))
    name       = db.Column(db.String(120), default='')
    items_json = db.Column(db.Text)          # JSON string of cart items
    saved_at   = db.Column(db.DateTime, default=datetime.utcnow)
    recovered  = db.Column(db.Boolean, default=False)

@app.route('/save-cart', methods=['POST'])
def save_cart():
    """Called by frontend when user fills phone on cart page."""
    import json
    data  = request.get_json() or {}
    phone = (data.get('phone') or '').strip()
    name  = (data.get('name') or '').strip()
    items = data.get('items', [])
    if not phone or not items:
        return jsonify({'ok': False}), 400
    # Upsert by phone — update if exists, else create
    row = AbandonedCart.query.filter_by(phone=phone, recovered=False).first()
    if row:
        row.items_json = json.dumps(items)
        row.name       = name
        row.saved_at   = datetime.utcnow()
    else:
        row = AbandonedCart(phone=phone, name=name, items_json=json.dumps(items))
        db.session.add(row)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/abandoned-carts')
def abandoned_carts():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    import json
    cutoff = datetime.utcnow() - timedelta(hours=1)
    carts  = AbandonedCart.query.filter(
        AbandonedCart.recovered == False,
        AbandonedCart.saved_at  <= cutoff
    ).order_by(AbandonedCart.saved_at.desc()).all()
    result = []
    for c in carts:
        try:
            items = json.loads(c.items_json or '[]')
        except Exception:
            items = []
        result.append({
            'id':       c.id,
            'phone':    c.phone,
            'name':     c.name,
            'items':    items,
            'saved_at': c.saved_at.strftime('%d %b %Y, %H:%M'),
            'hours_ago': round((datetime.utcnow() - c.saved_at).total_seconds() / 3600, 1)
        })
    return jsonify(result)

@app.route('/admin/mark-recovered/<int:cid>', methods=['POST'])
def mark_recovered(cid):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    row = AbandonedCart.query.get_or_404(cid)
    row.recovered = True
    db.session.commit()
    return jsonify({'ok': True})

# ── Selar routing ─────────────────────────────────────────────────────────────
SELAR_A = 'https://selar.com/m/marcus-bright1'          # Account A
SELAR_B = 'https://selar.com/m/PLACEHOLDER_ACCOUNT_B'   # Account B — swap when ready

@app.route('/selar-route', methods=['POST'])
def selar_route():
    """Increment global counter; first 3 of every 6 → Selar A, next 3 → Selar B."""
    row = SelarCounter.query.get(1)
    if not row:
        row = SelarCounter(id=1, count=0)
        db.session.add(row)
    row.count += 1
    db.session.commit()
    # position within the current block of 6
    slot = ((row.count - 1) % 6)   # 0-5
    url  = SELAR_A if slot < 3 else SELAR_B
    log_event(f'Checkout routed → {"Selar A" if slot < 3 else "Selar B"} (checkout #{row.count})')
    return jsonify({'url': url})


@app.route('/cart')
def cart():
    whatsapp = os.environ.get('WHATSAPP_NUMBER', '2348023905056')
    return render_template('cart.html', whatsapp=whatsapp, is_admin=is_admin())

@app.route('/')
def index():
    products   = Product.query.filter_by(visible=True).order_by(Product.id.desc()).all()
    categories = db.session.query(Product.category).filter_by(visible=True).distinct().all()
    categories = sorted([c[0] for c in categories])
    whatsapp   = os.environ.get('WHATSAPP_NUMBER', '2348023905056')
    return render_template('index.html',
                           products=products,
                           categories=categories,
                           is_admin=is_admin(),
                           whatsapp=whatsapp,
                           now=datetime.utcnow())

# ── Admin: Ghost entrance ─────────────────────────────────────────────────────
@app.route('/lady', methods=['GET', 'POST'])
def lady():
    """Secret URL — visiting it directly grants admin access, no password needed."""
    ip = get_ip()
    session.clear()
    session['is_admin'] = True
    session['admin_ip'] = ip
    session.permanent   = True
    log_event('Lady C accessed via secret URL')
    return redirect(url_for('admin_panel'))

@app.route('/exitlady')
def exitlady():
    log_event('Lady C logged out')
    session.clear()
    return redirect(url_for('index'))

# ── Admin: Panel ──────────────────────────────────────────────────────────────
@app.route('/lady/panel')
def admin_panel():
    if not is_admin():
        return redirect(url_for('lady'))
    return render_template('admin.html',
                           cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME', 'daxerardc'),
                           upload_preset='wi6uf3xc',
                           whatsapp=os.environ.get('WHATSAPP_NUMBER', '2348023905056'))

# ── Admin: Products API ───────────────────────────────────────────────────────
@app.route('/admin/add', methods=['POST'])
def add_product():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    raw_stock = data.get('stock')
    p = Product(
        name          = data['name'].strip(),
        price         = float(data.get('price', 0)),
        image1        = data.get('image1') or None,
        image2        = data.get('image2') or None,
        image3        = data.get('image3') or None,
        image4        = data.get('image4') or None,
        category      = data.get('category', 'Italian Slides & Flats').strip(),
        desc          = data.get('desc', '').strip(),
        stock         = int(raw_stock) if raw_stock not in (None, '', 'null') else None,
        limited_stock = bool(data.get('limited_stock', False))
    )
    db.session.add(p)
    db.session.commit()
    log_event(f'Product listed: {p.name}')
    return jsonify(product_to_dict(p))

@app.route('/admin/edit/<int:pid>', methods=['POST'])
def edit_product(pid):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    p    = Product.query.get_or_404(pid)
    data = request.get_json()
    if data.get('name'):      p.name          = data['name'].strip()
    if 'price'    in data:    p.price         = float(data['price'])
    if data.get('category'):  p.category      = data['category'].strip()
    if 'desc'     in data:    p.desc          = data['desc'].strip()
    if 'image1'   in data:    p.image1        = data['image1'] or None
    if 'image2'   in data:    p.image2        = data['image2'] or None
    if 'image3'   in data:    p.image3        = data['image3'] or None
    if 'image4'   in data:    p.image4        = data['image4'] or None
    if 'stock'    in data:
        raw_s = data['stock']
        p.stock = int(raw_s) if raw_s not in (None, '', 'null') else None
    if 'limited_stock' in data: p.limited_stock = bool(data['limited_stock'])
    db.session.commit()
    log_event(f'Product edited: {p.name}')
    return jsonify(product_to_dict(p))

@app.route('/admin/toggle/<int:pid>', methods=['POST'])
def toggle_product(pid):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    p         = Product.query.get_or_404(pid)
    p.visible = not p.visible
    db.session.commit()
    log_event(f'Product {"shown" if p.visible else "hidden"}: {p.name}')
    return jsonify({'visible': p.visible})

@app.route('/admin/delete/<int:pid>', methods=['DELETE'])
def delete_product(pid):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    p    = Product.query.get_or_404(pid)
    name = p.name
    db.session.delete(p)
    db.session.commit()
    log_event(f'Product removed: {name}')
    return jsonify({'deleted': pid})

@app.route('/admin/products')
def admin_products():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    products = Product.query.order_by(Product.id.desc()).all()
    return jsonify([product_to_dict(p) for p in products])

# ── Product detail page ───────────────────────────────────────────────────────
@app.route('/product/<int:pid>')
def product_detail(pid):
    product  = Product.query.get_or_404(pid)
    related  = Product.query.filter(
        Product.category == product.category,
        Product.visible  == True,
        Product.id       != pid
    ).order_by(Product.id.desc()).limit(4).all()
    whatsapp = os.environ.get('WHATSAPP_NUMBER', '2348023905056')
    return render_template('product.html',
                           product=product,
                           related=related,
                           whatsapp=whatsapp,
                           now=datetime.utcnow(),
                           is_admin=is_admin())

# ── Activity vault ────────────────────────────────────────────────────────────
@app.route('/lady/vault')
def vault():
    if not is_admin():
        return redirect(url_for('lady'))
    logs             = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(100).all()
    total_products   = Product.query.count()
    visible_products = Product.query.filter_by(visible=True).count()
    return render_template('vault.html',
                           logs=logs,
                           total_products=total_products,
                           visible_products=visible_products)

# ── Boot ──────────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
