-- Banco novo para a implantação Cloudflare. Não altera o banco Python local.
CREATE TABLE categories(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, scientific TEXT NOT NULL DEFAULT '', category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', care TEXT NOT NULL DEFAULT '', price INTEGER NOT NULL CHECK(price>=0), cost INTEGER NOT NULL DEFAULT 0 CHECK(cost>=0), stock INTEGER NOT NULL CHECK(stock>=0), image TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, individual INTEGER NOT NULL DEFAULT 0);
CREATE TABLE specimens(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), code TEXT NOT NULL UNIQUE, notes TEXT NOT NULL DEFAULT '', image TEXT NOT NULL, available INTEGER NOT NULL DEFAULT 1);
CREATE TABLE customers(id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL);
CREATE TABLE orders(id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), total INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Recebido', payment TEXT NOT NULL DEFAULT 'Pendente', delivery TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE items(order_id TEXT REFERENCES orders(id), product_id INTEGER REFERENCES products(id), name TEXT, quantity INTEGER NOT NULL CHECK(quantity>0), price INTEGER, specimen_id INTEGER REFERENCES specimens(id));
CREATE TABLE movements(id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), quantity INTEGER NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE sessions(token TEXT PRIMARY KEY, expires INTEGER NOT NULL);
CREATE TABLE rate_limits(key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE INDEX specimens_product ON specimens(product_id,available);
CREATE INDEX items_order ON items(order_id);
CREATE INDEX items_specimen ON items(specimen_id);
CREATE INDEX sessions_expiry ON sessions(expires);
CREATE INDEX rate_expiry ON rate_limits(expires);

-- D1 batch é transacional. Os triggers validam e reservam cada unidade
-- dentro do mesmo batch do pedido, evitando concorrência na leitura do estoque.
CREATE TRIGGER validate_item BEFORE INSERT ON items BEGIN
  SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM products WHERE id=NEW.product_id AND active=1) THEN RAISE(ABORT,'Produto indisponível.') END;
  SELECT CASE WHEN NEW.price!=(SELECT price FROM products WHERE id=NEW.product_id) THEN RAISE(ABORT,'O preço mudou. Atualize a loja.') END;
  SELECT CASE WHEN (SELECT individual FROM products WHERE id=NEW.product_id)=0 AND (NEW.specimen_id IS NOT NULL OR (SELECT stock FROM products WHERE id=NEW.product_id)<NEW.quantity) THEN RAISE(ABORT,'Estoque insuficiente.') END;
  SELECT CASE WHEN (SELECT individual FROM products WHERE id=NEW.product_id)=1 AND (NEW.quantity!=1 OR NOT EXISTS(SELECT 1 FROM specimens WHERE id=NEW.specimen_id AND product_id=NEW.product_id AND available=1)) THEN RAISE(ABORT,'Exemplar indisponível.') END;
END;
CREATE TRIGGER reserve_item AFTER INSERT ON items BEGIN
  UPDATE products SET stock=stock-NEW.quantity WHERE id=NEW.product_id AND individual=0;
  UPDATE specimens SET available=0 WHERE id=NEW.specimen_id;
  UPDATE orders SET total=total+NEW.price*NEW.quantity WHERE id=NEW.order_id;
  INSERT INTO movements(product_id,quantity,reason) VALUES (NEW.product_id,-NEW.quantity,'Pedido #'||NEW.order_id);
END;
CREATE TRIGGER prevent_reopen BEFORE UPDATE OF status ON orders WHEN OLD.status='Cancelado' AND NEW.status!='Cancelado' BEGIN
  SELECT RAISE(ABORT,'Pedido cancelado não pode ser reaberto.');
END;
CREATE TRIGGER cancel_order AFTER UPDATE OF status ON orders WHEN NEW.status='Cancelado' AND OLD.status!='Cancelado' BEGIN
  UPDATE products SET stock=stock+(SELECT COALESCE(SUM(i.quantity),0) FROM items i WHERE i.order_id=NEW.id AND i.product_id=products.id AND i.specimen_id IS NULL) WHERE individual=0 AND id IN (SELECT product_id FROM items WHERE order_id=NEW.id);
  UPDATE specimens SET available=1 WHERE id IN (SELECT specimen_id FROM items WHERE order_id=NEW.id);
  INSERT INTO movements(product_id,quantity,reason) SELECT product_id,quantity,'Cancelamento #'||NEW.id FROM items WHERE order_id=NEW.id;
END;
INSERT INTO categories(name) VALUES ('Interior'),('Exterior'),('Suculentas'),('Vasos e acessórios');
