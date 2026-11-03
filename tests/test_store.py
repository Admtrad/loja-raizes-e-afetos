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

if __name__=='__main__': unittest.main()
