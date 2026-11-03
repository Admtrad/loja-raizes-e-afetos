"""Loja Raízes e Afetos — servidor local, Python 3.11+, sem dependências."""
import os, json, sqlite3, secrets, hashlib, hmac, time
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
        ''')
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
        if qty < 1 or qty > 999: raise ValueError('Quantidade inválida.')
        quantities[pid] = quantities.get(pid, 0) + qty
    if not quantities: raise ValueError('O carrinho está vazio.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        rows, total = [], 0
        for pid, qty in quantities.items():
            p = db.execute('SELECT * FROM products WHERE id=? AND active=1', (pid,)).fetchone()
            if not p or p['stock'] < qty: raise ValueError('Um produto está indisponível ou sem estoque suficiente.')
            rows.append((p, qty)); total += p['price'] * qty
        customer = db.execute('INSERT INTO customers(name,phone,address) VALUES (?,?,?)', (name[:150], phone[:40], address[:500])).lastrowid
        oid = db.execute('INSERT INTO orders(customer_id,total,delivery) VALUES (?,?,?)', (customer,total,delivery)).lastrowid
        for p, qty in rows:
            db.execute('INSERT INTO items VALUES (?,?,?,?,?)', (oid,p['id'],p['name'],qty,p['price']))
            db.execute('UPDATE products SET stock=stock-? WHERE id=?', (qty,p['id']))
            db.execute('INSERT INTO movements(product_id,quantity,reason) VALUES (?,?,?)', (p['id'],-qty,f'Pedido #{oid}'))
    return {'id':oid, 'total':total}

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
        if route.startswith('/api/admin/') and not self.authorized(): return self.respond(401, {'error':'Entre no painel.'})
        with connect() as db:
            if route == '/api/products': return self.respond(200,[dict(r) for r in db.execute('SELECT id,name,scientific,category,description,care,price,stock,image FROM products WHERE active=1')])
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
            if size > 64000: raise ValueError('Requisição muito grande.')
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
            with connect() as db:
                if self.path == '/api/admin/categories':
                    name = str(p.get('name','')).strip()[:80]
                    if not name: raise ValueError('Informe o nome da categoria.')
                    db.execute('INSERT INTO categories(name) VALUES (?)',(name,))
                elif self.path == '/api/admin/products':
                    name, category = str(p.get('name','')).strip(),str(p.get('category',''))
                    price,cost,stock = int(p['price']),int(p['cost']),int(p['stock'])
                    image=str(p.get('image','')).strip()
                    if not name or min(price,cost,stock)<0 or (image and not image.startswith('https://')): raise ValueError('Confira os dados do produto e use uma foto HTTPS.')
                    if not db.execute('SELECT 1 FROM categories WHERE name=?',(category,)).fetchone(): raise ValueError('Categoria inválida.')
                    values=(name[:150],str(p.get('scientific',''))[:150],category,str(p.get('description',''))[:2000],str(p.get('care',''))[:2000],price,cost,stock,image,int(bool(p.get('active',True))))
                    if p.get('id'):
                        old=db.execute('SELECT stock FROM products WHERE id=?',(int(p['id']),)).fetchone()
                        if not old: raise ValueError('Produto não encontrado.')
                        db.execute('UPDATE products SET name=?,scientific=?,category=?,description=?,care=?,price=?,cost=?,stock=?,image=?,active=? WHERE id=?',values+(int(p['id']),))
                        pid=int(p['id']); delta=stock-old['stock']
                    else:
                        pid=db.execute('INSERT INTO products(name,scientific,category,description,care,price,cost,stock,image,active) VALUES (?,?,?,?,?,?,?,?,?,?)',values).lastrowid; delta=stock
                    if delta: db.execute('INSERT INTO movements(product_id,quantity,reason) VALUES (?,?,?)',(pid,delta,'Cadastro / ajuste manual'))
                elif self.path == '/api/admin/orders':
                    status,payment=p.get('status'),p.get('payment')
                    if status not in ['Recebido','Em preparação','Enviado','Entregue','Cancelado'] or payment not in ['Pendente','Pago','Reembolsado']: raise ValueError('Situação inválida.')
                    order=db.execute('SELECT * FROM orders WHERE id=?',(p['id'],)).fetchone()
                    if not order: raise ValueError('Pedido não encontrado.')
                    if order['status']=='Cancelado' and status!='Cancelado': raise ValueError('Pedido cancelado não pode ser reaberto.')
                    if status=='Cancelado' and order['status']!='Cancelado':
                        for item in db.execute('SELECT * FROM items WHERE order_id=?',(p['id'],)).fetchall():
                            db.execute('UPDATE products SET stock=stock+? WHERE id=?',(item['quantity'],item['product_id']))
                            db.execute('INSERT INTO movements(product_id,quantity,reason) VALUES (?,?,?)',(item['product_id'],item['quantity'],f"Cancelamento #{p['id']}"))
                    db.execute('UPDATE orders SET status=?,payment=? WHERE id=?',(status,payment,p['id']))
                else: return self.respond(404,{'error':'Rota não encontrada.'})
            return self.respond(200,{'ok':True})
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError): self.respond(400,{'error':'Dados inválidos, duplicados ou estoque insuficiente. Confira os campos.'})

if __name__ == '__main__':
    if len(PASSWORD)<12: raise SystemExit('Defina ADMIN_PASSWORD com pelo menos 12 caracteres antes de iniciar.')
    initialize()
    print('Loja: http://127.0.0.1:8000 | Gestão: http://127.0.0.1:8000/admin')
    ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
