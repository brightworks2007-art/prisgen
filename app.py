from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'prisgen-ladyc-velvet-2026-xK9#mP2')

# ── Database ──────────────────────────────────────────────────────────────────
# Render provides DATABASE_URL as postgres:// but SQLAlchemy needs postgresql://
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
    # Up to 4 image URLs
    image1      = db.Column(db.String(500), nullable=True)
    image2      = db.Column(db.String(500), nullable=True)
    image3      = db.Column(db.String(500), nullable=True)
    image4      = db.Column(db.String(500), nullable=True)

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
    return {
        'id': p.id, 'name': p.name, 'price': p.price,
        'category': p.category, 'desc': p.desc,
        'visible': p.visible,
        'is_new': (datetime.utcnow() - p.created_at).days < 14,
        'images': images,
        'image': p.image1 or ''
    }

# ── Public routes ─────────────────────────────────────────────────────────────
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
    ip = get_ip(); error = None
    if is_admin():
        return redirect(url_for('index'))
    if request.method == 'POST':
        if is_blocked(ip):
            log_event('Blocked IP tried Lady C login', success=False)
            return render_template('login.html',
                                   error='Too many failed attempts. Try again in 30 minutes.')
        entered = request.form.get('password', '').strip()
        if entered == get_password():
            session.clear()
            session['is_admin']  = True
            session['admin_ip']  = ip
            session.permanent    = True
            clear_attempts(ip)
            log_event('Lady C login successful')
            return redirect(url_for('index'))
        else:
            record_failed_attempt(ip)
            window    = datetime.utcnow() - timedelta(minutes=30)
            remaining = 5 - LoginAttempt.query.filter(
                LoginAttempt.ip == ip,
                LoginAttempt.timestamp >= window).count()
            log_event('Failed Lady C login attempt', success=False)
            error = f'Incorrect passphrase. {remaining} attempt(s) remaining.'
    return render_template('login.html', error=error)

@app.route('/exitlady')
def exitlady():
    log_event('Lady C logged out')
    session.clear()
    return redirect(url_for('index'))

# ── Admin: Products API ───────────────────────────────────────────────────────
@app.route('/admin/add', methods=['POST'])
def add_product():
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    if not data or not data.get('name') or not data.get('price'):
        return jsonify({'error': 'Name and price are required'}), 400
    p = Product(
        name     = data['name'].strip(),
        price    = float(data['price']),
        image1   = data.get('image1') or None,
        image2   = data.get('image2') or None,
        image3   = data.get('image3') or None,
        image4   = data.get('image4') or None,
        category = data.get('category', 'Italian Slides & Flats').strip(),
        desc     = data.get('desc', '').strip()
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
    if data.get('name'):    p.name     = data['name'].strip()
    if data.get('price'):   p.price    = float(data['price'])
    if data.get('category'): p.category = data['category'].strip()
    if 'desc'   in data:    p.desc     = data['desc'].strip()
    if 'image1' in data:    p.image1   = data['image1'] or None
    if 'image2' in data:    p.image2   = data['image2'] or None
    if 'image3' in data:    p.image3   = data['image3'] or None
    if 'image4' in data:    p.image4   = data['image4'] or None
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
    product      = Product.query.get_or_404(pid)
    # Related: same category, visible, exclude current
    related      = Product.query.filter(
        Product.category == product.category,
        Product.visible  == True,
        Product.id       != pid
    ).order_by(Product.id.desc()).limit(4).all()
    whatsapp     = os.environ.get('WHATSAPP_NUMBER', '2348023905056')
    return render_template('product.html',
                           product=product,
                           related=related,
                           whatsapp=whatsapp,
                           now=datetime.utcnow())

# ── Activity vault ────────────────────────────────────────────────────────────
@app.route('/lady/vault')
def vault():
    if not is_admin():
        return redirect(url_for('lady'))
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(100).all()
    total_products = Product.query.count()
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
