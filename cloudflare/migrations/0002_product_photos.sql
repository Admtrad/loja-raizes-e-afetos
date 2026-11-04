ALTER TABLE products ADD COLUMN images TEXT NOT NULL DEFAULT '[]';
CREATE TABLE store_settings (
  id INTEGER PRIMARY KEY CHECK(id=1),
  photo_limit INTEGER NOT NULL CHECK(photo_limit BETWEEN 1 AND 20)
);
INSERT INTO store_settings VALUES (1,4);

CREATE TRIGGER product_photo_limit_insert BEFORE INSERT ON products
WHEN json_array_length(NEW.images) > (SELECT photo_limit FROM store_settings WHERE id=1)
BEGIN
  SELECT RAISE(ABORT,'Limite de fotos por produto excedido.');
END;

CREATE TRIGGER product_photo_limit_update BEFORE UPDATE OF images ON products
WHEN json_array_length(NEW.images) > (SELECT photo_limit FROM store_settings WHERE id=1)
BEGIN
  SELECT RAISE(ABORT,'Limite de fotos por produto excedido.');
END;

CREATE TRIGGER store_photo_limit_update BEFORE UPDATE OF photo_limit ON store_settings
WHEN EXISTS (SELECT 1 FROM products WHERE json_array_length(images)>NEW.photo_limit)
BEGIN
  SELECT RAISE(ABORT,'Retire as fotos excedentes dos produtos antes de reduzir o limite.');
END;
