"""Loja Raízes e Afetos — servidor local, Python 3.11+, sem dependências."""
import os, json, sqlite3, secrets, hashlib, hmac, time, re, base64, binascii
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('STORE_DB', str(ROOT / 'data/store.sqlite3')))
SESSIONS = {}
PASSWORD = os.environ.get('ADMIN_PASSWORD', '')

class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def connect():
    db = sqlite3.connect(DB, factory=Connection)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, scientific TEXT NOT NULL DEFAULT '', category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', care TEXT NOT NULL DEFAULT '', price INTEGER NOT NULL CHECK(price>=0), cost INTEGER NOT NULL DEFAULT 0 CHECK(cost>=0), stock INTEGER NOT NULL CHECK(stock>=0), image TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), total INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'Recebido', payment TEXT NOT NULL DEFAULT 'Pendente', delivery TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS items(order_id INTEGER REFERENCES orders(id), product_id INTEGER REFERENCES products(id), name TEXT, quantity INTEGER, price INTEGER);
        CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), quantity INTEGER NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS specimens(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), code TEXT NOT NULL UNIQUE, notes TEXT NOT NULL DEFAULT '', image TEXT NOT NULL, available INTEGER NOT NULL DEFAULT 1);
        ''')
        if 'individual' not in [r['name'] for r in db.execute('PRAGMA table_info(products)')]:
            db.execute('ALTER TABLE products ADD COLUMN individual INTEGER NOT NULL DEFAULT 0')
        if 'specimen_id' not in [r['name'] for r in db.execute('PRAGMA table_info(items)')]:
            db.execute('ALTER TABLE items ADD COLUMN specimen_id INTEGER REFERENCES specimens(id)')
        if 'images' not in [r['name'] for r in db.execute('PRAGMA table_info(products)')]:
            migration = ROOT / 'cloudflare/migrations/0002_product_photos.sql'
            db.executescript('BEGIN IMMEDIATE;\n' + migration.read_text(encoding='utf-8') + '\nCOMMIT;')
        for category in ['Interior', 'Exterior', 'Suculentas', 'Vasos e acessórios']:
            db.execute('INSERT OR IGNORE INTO categories(name) VALUES (?)', (category,))

def create_order(payload):
    name = str(payload.get('name', '')).strip()
    phone = str(payload.get('phone', '')).strip()
    address = str(payload.get('address', '')).strip()
    delivery = payload.get('delivery')
    if not name or not phone or delivery not in ['Retirada na loja', 'Entrega a combinar'] or (delivery == 'Entrega a combinar' and not address):
        raise ValueError('Preencha nome, contato e endereço para entrega.')
    quantities = {}
    for item in payload.get('items', []):
        pid, qty = int(item['id']), int(item['quantity'])
        sid = int(item['specimen_id']) if item.get('specimen_id') else None
        if qty < 1 or qty > 999: raise ValueError('Quantidade inválida.')
        key = (pid, sid)
        quantities[key] = quantities.get(key, 0) + qty
    if not quantities: raise ValueError('O carrinho está vazio.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        rows, total = [], 0
        for (pid, sid), qty in quantities.items():
            p = db.execute('SELECT * FROM products WHERE id=? AND active=1', (pid,)).fetchone()
            if not p: raise ValueError('Produto indisponível.')
            specimen = None
            if p['individual']:
                specimen = db.execute('SELECT * FROM specimens WHERE id=? AND product_id=? AND available=1', (sid,pid)).fetchone()
                if not specimen or qty != 1: raise ValueError('Escolha um exemplar disponível.')
            elif sid or p['stock'] < qty: raise ValueError('Estoque insuficiente.')
            rows.append((p, qty, specimen)); total += p['price'] * qty
        customer = db.execute('INSERT INTO customers(name,phone,address) VALUES (?,?,?)', (name[:150], phone[:40], address[:500])).lastrowid
        oid = db.execute('INSERT INTO orders(customer_id,total,delivery) VALUES (?,?,?)', (customer,total,delivery)).lastrowid
        for p, qty, specimen in rows:
            title = p['name'] + (' · Exemplar ' + specimen['code'] if specimen else '')
            db.execute('INSERT INTO items(order_id,product_id,name,quantity,price,specimen_id) VALUES (?,?,?,?,?,?)', (oid,p['id'],title,qty,p['price'],specimen['id'] if specimen else None))
            if specimen: db.execute('UPDATE specimens SET available=0 WHERE id=?', (specimen['id'],))
            else: db.execute('UPDATE products SET stock=stock-? WHERE id=?', (qty,p['id']))
            db.execute('INSERT INTO movements(product_id,quantity,reason) VALUES (?,?,?)', (p['id'],-qty,f'Pedido #{oid}'))
    return {'id':oid, 'total':total}

def photo_url(value):
    return not value or value.startswith('https://') or bool(re.fullmatch(r'/uploads/[a-f0-9]{32}\.jpg', value))

def product_rows(db, admin=False):
    fields = '*' if admin else 'id,name,scientific,category,description,care,price,stock,image,individual,images'
    rows = [dict(r) for r in db.execute('SELECT '+fields+' FROM products'+('' if admin else ' WHERE active=1'))]
    for p in rows:
        p['images'] = json.loads(p['images']) or ([p['image']] if p['image'] else [])
        p['specimens'] = [dict(r) for r in db.execute('SELECT * FROM specimens WHERE product_id=?'+('' if admin else ' AND available=1'), (p['id'],))]
        if p['individual']: p['stock'] = sum(s['available'] for s in p['specimens'])
    return rows

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers(); self.wfile.write(body)

    def authorized(self):
        cookie = SimpleCookie(self.headers.get('Cookie',''))
        token = cookie.get('session')
        return token and SESSIONS.get(token.value, 0) > time.time()

    def do_GET(self):
        route = self.path.split('?')[0]
        if re.fullmatch(r'/uploads/[a-f0-9]{32}\.jpg', route):
            file = DB.parent / 'uploads' / route.rsplit('/',1)[1]
            if not file.is_file(): return self.respond(404, {'error':'Foto não encontrada.'})
            self.send_response(200); self.send_header('Content-Type','image/jpeg'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(file.read_bytes()); return
        if route.startswith('/api/admin/') and not self.authorized(): return self.respond(401, {'error':'Entre no painel.'})
        with connect() as db:
            if route == '/api/products': return self.respond(200,product_rows(db))
            if route == '/api/admin/settings': return self.respond(200,dict(db.execute('SELECT photo_limit FROM store_settings WHERE id=1').fetchone()))
            if route == '/api/admin/products': return self.respond(200,product_rows(db, True))
            if route == '/api/categories': return self.respond(200,[dict(r) for r in db.execute('SELECT * FROM categories')])
            tables = {'/api/admin/products':'SELECT * FROM products', '/api/admin/customers':'SELECT * FROM customers ORDER BY id DESC', '/api/admin/orders':'SELECT o.*,c.name,c.phone,c.address FROM orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.id DESC', '/api/admin/movements':'SELECT m.*,p.name FROM movements m JOIN products p ON p.id=m.product_id ORDER BY m.id DESC'}
            if route in tables:
                rows = [dict(r) for r in db.execute(tables[route])]
                if route.endswith('/orders'):
                    for row in rows: row['items'] = [dict(r) for r in db.execute('SELECT * FROM items WHERE order_id=?',(row['id'],))]
                return self.respond(200,rows)
        files = {'/':'index.html','/admin':'admin.html','/app.js':'app.js','/style.css':'style.css','/admin.js':'admin.js'}
        if route not in files: return self.respond(404,{'error':'Página não encontrada.'})
        file = ROOT / 'public' / files[route]
        self.send_response(200)
        self.send_header('Content-Type', {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}[file.suffix])
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' https:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers(); self.wfile.write(file.read_bytes())

    def do_POST(self):
        if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host',''):
            return self.respond(403,{'error':'Origem não autorizada.'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if size > (8000000 if self.path == '/api/admin/upload' else 64000): raise ValueError('Requisição muito grande.')
            p = json.loads(self.rfile.read(size))
            if self.path == '/api/login':
                if not PASSWORD or not hmac.compare_digest(hashlib.sha256(str(p.get('password','')).encode()).digest(),hashlib.sha256(PASSWORD.encode()).digest()):
                    time.sleep(1)
                    return self.respond(401,{'error':'Senha inválida.'})
                token=secrets.token_urlsafe(32); SESSIONS[token]=time.time()+28800
                return self.respond(200,{'ok':True},f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
            if self.path == '/api/logout':
                cookie=SimpleCookie(self.headers.get('Cookie',''))
                if cookie.get('session'): SESSIONS.pop(cookie['session'].value,None)
                return self.respond(200,{'ok':True},'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if self.path == '/api/orders': return self.respond(201,create_order(p))
            if not self.authorized(): return self.respond(401,{'error':'Entre no painel.'})
            if self.path == '/api/admin/upload':
                raw = base64.b64decode(p['data'], validate=True)
                if len(raw)>5000000 or not raw.startswith(b'\xff\xd8\xff') or not raw.endswith(b'\xff\xd9'): raise ValueError('Envie uma foto JPEG de até 5 MB.')
                folder=DB.parent/'uploads'; folder.mkdir(parents=True,exist_ok=True)
                filename=secrets.token_hex(16)+'.jpg'; (folder/filename).write_bytes(raw)
                return self.respond(201,{'url':'/uploads/'+filename})
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if self.path == '/api/admin/specimens':
                    pid=int(p['product_id']); code=str(p['code']).strip()[:80]; image=str(p['image'])
                    product=db.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                    if not product or not product['individual'] or not code or not image or not photo_url(image): raise ValueError('Informe código e foto real do exemplar.')
                    available=int(bool(p.get('available',True)))
                    if p.get('id'):
                        old=db.execute('SELECT * FROM specimens WHERE id=? AND product_id=?',(int(p['id']),pid)).fetchone()
                        if not old: raise ValueError('Exemplar não encontrado.')
                        if db.execute("SELECT 1 FROM items i JOIN orders o ON o.id=i.order_id WHERE i.specimen_id=? AND o.status!='Cancelado'",(old['id'],)).fetchone(): raise ValueError('Exemplar vinculado a pedido não pode ser alterado.')
                        db.execute('UPDATE specimens SET code=?,notes=?,image=?,available=? WHERE id=?',(code,str(p.get('notes',''))[:1000],image,available,old['id']))
                        delta=available-old['available']
                    else:
                        db.execute('INSERT INTO specimens(product_id,code,notes,image,available) VALUES (?,?,?,?,?)',(pid,code,str(p.get('notes',''))[:1000],image,available)); delta=available
                    if delta: db.execute('INSERT INTO movements(product_id,quantity,reason) VALUES (?,?,?)',(pid,delta,'Exemplar '+code))
                elif self.path == '/api/admin/categories':
                    name = str(p.get('name','')).strip()[:80]
                    if not name: raise ValueError('Informe o nome da categoria.')
                    db.execute('INSERT INTO categories(name) VALUES (?)',(name,))
                elif self.path == '/api/admin/settings':
                    limit = p.get('photo_limit')
                    if type(limit) is not int or not 1 <= limit <= 20:
                        raise ValueError('Informe um limite inteiro entre 1 e 20.')
                    db.execute('UPDATE store_settings SET photo_limit=? WHERE id=1', (limit,))
                elif self.path == '/api/admin/products':
                    name, category = str(p.get('name','')).strip(),str(p.get('category',''))
                    price,cost,stock = int(p['price']),int(p['cost']),int(p['stock'])
                    images = p.get('images', [p['image']] if p.get('image') else [])
                    if not isinstance(images, list) or len(images)>20 or any(
                        not isinstance(url, str) or not url.strip() or len(url)>2048 or not photo_url(url.strip()) for url in images
                    ):
                        raise ValueError('Informe até 20 fotos válidas.')
                    images = [url.strip() for url in images]
                    image = images[0] if images else ''
                    if not name or min(price,cost,stock)<0 or not photo_url(image): raise ValueError('Confira os dados e a foto.')
                    if not db.execute('SELECT 1 FROM categories WHERE name=?',(category,)).fetchone(): raise ValueError('Categoria inválida.')
                    values=(name[:150],str(p.get('scientific',''))[:150],category,str(p.get('description',''))[:2000],str(p.get('care',''))[:2000],price,cost,stock,image,int(bool(p.get('active',True))),json.dumps(images))
                    if p.get('id'):
                        old=db.execute('SELECT * FROM products WHERE id=?',(int(p['id']),)).fetchone()
                        if not old: raise ValueError('Produto não encontrado.')
                        if old['individual'] != int(bool(p.get('individual',False))): raise ValueError('O tipo de estoque não pode ser alterado após o cadastro. Cadastre outro produto.')
                        if old['individual']: values=values[:7]+(0,)+values[8:]
                        db.execute('UPDATE products SET name=?,scientific=?,category=?,description=?,care=?,price=?,cost=?,stock=?,image=?,active=?,images=? WHERE id=?',values+(int(p['id']),))
                        pid=int(p['id']); delta=0 if old['individual'] else stock-old['stock']
                    else:
                        pid=db.execute('INSERT INTO products(name,scientific,category,description,care,price,cost,stock,image,active,images) VALUES (?,?,?,?,?,?,?,?,?,?,?)',values).lastrowid; delta=stock
                        if p.get('individual'):
                            db.execute('UPDATE products SET individual=1,stock=0 WHERE id=?',(pid,)); delta=0
                    if delta: db.execute('INSERT INTO movements(product_id,quantity,reason) VALUES (?,?,?)',(pid,delta,'Cadastro / ajuste manual'))
                elif self.path == '/api/admin/orders':
                    status,payment=p.get('status'),p.get('payment')
                    if status not in ['Recebido','Em preparação','Enviado','Entregue','Cancelado'] or payment not in ['Pendente','Pago','Reembolsado']: raise ValueError('Situação inválida.')
                    order=db.execute('SELECT * FROM orders WHERE id=?',(p['id'],)).fetchone()
                    if not order: raise ValueError('Pedido não encontrado.')
                    if order['status']=='Cancelado' and status!='Cancelado': raise ValueError('Pedido cancelado não pode ser reaberto.')
                    if status=='Cancelado' and order['status']!='Cancelado':
                        for item in db.execute('SELECT * FROM items WHERE order_id=?',(p['id'],)).fetchall():
                            if item['specimen_id']: db.execute('UPDATE specimens SET available=1 WHERE id=?',(item['specimen_id'],))
                            else: db.execute('UPDATE products SET stock=stock+? WHERE id=?',(item['quantity'],item['product_id']))
                            db.execute('INSERT INTO movements(product_id,quantity,reason) VALUES (?,?,?)',(item['product_id'],item['quantity'],f"Cancelamento #{p['id']}"))
                    db.execute('UPDATE orders SET status=?,payment=? WHERE id=?',(status,payment,p['id']))
                else: return self.respond(404,{'error':'Rota não encontrada.'})
            return self.respond(200,{'ok':True})
        except sqlite3.IntegrityError as error:
            message = str(error)
            if message in ('Limite de fotos por produto excedido.', 'Retire as fotos excedentes dos produtos antes de reduzir o limite.'):
                return self.respond(409, {'error':message})
            self.respond(400, {'error':'Dados inválidos ou duplicados. Confira os campos.'})
        except (ValueError,KeyError,TypeError,binascii.Error) as error: self.respond(400,{'error':str(error) if isinstance(error,ValueError) else 'Dados inválidos ou duplicados. Confira os campos.'})

if __name__ == '__main__':
    if len(PASSWORD)<12: raise SystemExit('Defina ADMIN_PASSWORD com pelo menos 12 caracteres antes de iniciar.')
    initialize()
    print('Loja: http://127.0.0.1:8000 | Gestão: http://127.0.0.1:8000/admin')
    ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
