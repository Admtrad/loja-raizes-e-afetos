import unittest, tempfile, threading, json, urllib.request, urllib.error
from pathlib import Path
import server

class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        server.DB=Path(self.tmp.name)/'test.sqlite3'
        server.PASSWORD='senha-de-teste-comprida'
        server.SESSIONS.clear()
        server.initialize()
        with server.connect() as db:
            db.execute("INSERT INTO products(name,category,price,stock) VALUES ('Planta de teste','Interior',2500,3)")
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,path,data=None,cookie=None):
        headers={'Content-Type':'application/json'}
        if cookie: headers['Cookie']=cookie
        req=urllib.request.Request(self.base+path,json.dumps(data).encode() if data is not None else None,headers)
        return urllib.request.urlopen(req)

    def order(self,quantity=2):
        return {'name':'Cliente teste','phone':'11999990000','address':'','delivery':'Retirada na loja','items':[{'id':1,'quantity':quantity,'price':1}]}

    def test_order_recalculates_and_reserves_stock(self):
        with self.request('/api/orders',self.order()) as r: self.assertEqual(json.load(r)['total'],5000)
        with server.connect() as db: self.assertEqual(db.execute('SELECT stock FROM products').fetchone()[0],1)

    def test_insufficient_stock_rolls_back(self):
        with self.assertRaises(urllib.error.HTTPError) as error: self.request('/api/orders',self.order(4))
        self.assertEqual(error.exception.code,400)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT stock FROM products').fetchone()[0],3)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM customers').fetchone()[0],0)

    def test_admin_routes_private_and_public_hides_cost(self):
        with self.assertRaises(urllib.error.HTTPError) as error: self.request('/api/admin/customers')
        self.assertEqual(error.exception.code,401)
        with self.request('/api/products') as r: self.assertNotIn('cost',json.load(r)[0])

    def test_cancel_restocks_only_once(self):
        with self.request('/api/orders',self.order()) as r: oid=json.load(r)['id']
        with self.request('/api/login',{'password':server.PASSWORD}) as r: cookie=r.headers['Set-Cookie'].split(';')[0]
        for _ in range(2):
            with self.request('/api/admin/orders',{'id':oid,'status':'Cancelado','payment':'Pendente'},cookie): pass
        with server.connect() as db: self.assertEqual(db.execute('SELECT stock FROM products').fetchone()[0],3)

    def test_duplicate_lines_cannot_exceed_stock(self):
        payload=self.order();payload['items']*=2
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/orders',payload)
        with server.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)

    def individual(self):
        with server.connect() as db:
            db.execute('UPDATE products SET individual=1,stock=0 WHERE id=1')
            db.execute("INSERT INTO specimens(product_id,code,image) VALUES (1,'MON-001','https://example.com/one.jpg')")
            db.execute("INSERT INTO specimens(product_id,code,image) VALUES (1,'MON-002','https://example.com/two.jpg')")
        payload=self.order(1);payload['items'][0]['specimen_id']=1
        return payload

    def test_individual_selection_required_and_cannot_sell_twice(self):
        payload=self.individual()
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/orders',self.order(1))
        with self.request('/api/orders',payload) as r: self.assertEqual(json.load(r)['total'],2500)
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/orders',payload)
        with self.request('/api/products') as r:
            p=json.load(r)[0];self.assertEqual(p['stock'],1);self.assertEqual(p['specimens'][0]['code'],'MON-002')

    def test_duplicate_specimen_rejected(self):
        payload=self.individual();payload['items']*=2
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/orders',payload)
        with server.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)

    def test_cancel_individual_restores_exact_specimen_once(self):
        with self.request('/api/orders',self.individual()) as r: oid=json.load(r)['id']
        with self.request('/api/login',{'password':server.PASSWORD}) as r: cookie=r.headers['Set-Cookie'].split(';')[0]
        for _ in range(2):
            with self.request('/api/admin/orders',{'id':oid,'status':'Cancelado','payment':'Pendente'},cookie): pass
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT available FROM specimens WHERE id=1').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT stock FROM products').fetchone()[0],0)

    def test_upload_requires_authentication_and_rejects_non_image(self):
        import base64
        with self.assertRaises(urllib.error.HTTPError) as error: self.request('/api/admin/upload',{'data':'test'})
        self.assertEqual(error.exception.code,401)
        with self.request('/api/login',{'password':server.PASSWORD}) as r: cookie=r.headers['Set-Cookie'].split(';')[0]
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/admin/upload',{'data':base64.b64encode(b'<script>bad</script>').decode()},cookie)

    def test_migration_is_repeatable_and_preserves_products(self):
        server.initialize();server.initialize()
        with server.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM products').fetchone()[0],1)

if __name__=='__main__': unittest.main()
