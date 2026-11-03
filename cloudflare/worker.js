const security = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'same-origin',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' https:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
  'Strict-Transport-Security': 'max-age=31536000',
};
const statuses = ['Recebido', 'Em preparação', 'Enviado', 'Entregue', 'Cancelado'];
const payments = ['Pendente', 'Pago', 'Reembolsado'];
class InputError extends Error {}
const text = (value, max = 2000) => String(value ?? '').trim().slice(0, max);
function integer(value, min = 0, max = 100000000) {
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < min || n > max) throw new InputError('Número inválido.');
  return n;
}
function photo(value, required = false) {
  const url = text(value, 2048);
  if ((!url && required) || (url && !/^https:\/\/[^\s]+$/.test(url) && !/^\/uploads\/[a-f0-9]{32}\.jpg$/.test(url))) throw new InputError('Informe uma foto válida.');
  return url;
}
function response(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {status, headers: {...security, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra}});
}
async function hash(value) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))].map(b => b.toString(16).padStart(2, '0')).join('');
}
const statement = (db, sql, ...params) => db.prepare(sql).bind(...params);
async function all(db, sql, ...params) { return (await statement(db, sql, ...params).all()).results; }
async function authorized(request, env) {
  const token = /(?:^|;\s*)session=([a-f0-9]{64})(?:;|$)/.exec(request.headers.get('Cookie') || '')?.[1];
  return token && await statement(env.DB, 'SELECT 1 FROM sessions WHERE token=? AND expires>?', await hash(token), Date.now()).first();
}
async function rateLimit(request, env, kind, limit) {
  const now = Date.now(), window = 15 * 60 * 1000;
  const key = kind + ':' + await hash((request.headers.get('CF-Connecting-IP') || 'local') + ':' + Math.floor(now / window));
  const result = await statement(env.DB, 'INSERT INTO rate_limits(key,count,expires) VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1 RETURNING count', key, now + window).first();
  return result.count <= limit;
}
async function products(env, admin) {
  const fields = admin ? '*' : 'id,name,scientific,category,description,care,price,stock,image,individual';
  const rows = await all(env.DB, `SELECT ${fields} FROM products${admin ? '' : ' WHERE active=1'}`);
  const units = await all(env.DB, `SELECT s.* FROM specimens s JOIN products p ON p.id=s.product_id${admin ? '' : ' WHERE s.available=1 AND p.active=1'}`);
  for (const p of rows) {
    p.specimens = units.filter(s => s.product_id === p.id);
    if (p.individual) p.stock = p.specimens.reduce((sum, s) => sum + s.available, 0);
  }
  return rows;
}
async function createOrder(env, p) {
  const name = text(p.name, 150), phone = text(p.phone, 40), address = text(p.address, 500);
  if (!name || !phone || !['Retirada na loja', 'Entrega a combinar'].includes(p.delivery) || (p.delivery === 'Entrega a combinar' && !address)) throw new InputError('Preencha nome, contato e endereço para entrega.');
  if (!Array.isArray(p.items) || !p.items.length || p.items.length > 40) throw new InputError('Selecione de 1 a 40 itens.');
  const lines = new Map();
  for (const item of p.items) {
    const id = integer(item.id, 1), sid = item.specimen_id ? integer(item.specimen_id, 1) : null;
    const quantity = integer(item.quantity, 1, 999), key = `${id}:${sid}`;
    const line = lines.get(key) || {id, sid, quantity: 0};
    line.quantity += quantity;
    lines.set(key, line);
  }
  const id = crypto.randomUUID(), customer = crypto.randomUUID();
  const queries = [statement(env.DB, 'INSERT INTO customers(id,name,phone,address) VALUES (?,?,?,?)', customer, name, phone, address), statement(env.DB, 'INSERT INTO orders(id,customer_id,delivery) VALUES (?,?,?)', id, customer, p.delivery)];
  for (const line of lines.values()) {
    const product = await statement(env.DB, 'SELECT * FROM products WHERE id=? AND active=1', line.id).first();
    if (!product) throw new InputError('Produto indisponível. Atualize a loja.');
    const unit = line.sid ? await statement(env.DB, 'SELECT code FROM specimens WHERE id=? AND product_id=?', line.sid, line.id).first() : null;
    if (product.individual && (!unit || line.quantity !== 1)) throw new InputError('Selecione um exemplar por unidade.');
    const title = product.name + (unit ? ' · Exemplar ' + unit.code : '');
    queries.push(statement(env.DB, 'INSERT INTO items(order_id,product_id,name,quantity,price,specimen_id) VALUES (?,?,?,?,?,?)', id, line.id, title, line.quantity, product.price, line.sid));
  }
  // SQL triggers validate current price/availability and reserve stock atomically.
  await env.DB.batch(queries);
  return statement(env.DB, 'SELECT id,total FROM orders WHERE id=?', id).first();
}
async function saveProduct(env, p) {
  const name = text(p.name, 150), category = text(p.category, 80), individual = p.individual ? 1 : 0;
  if (!name || !await statement(env.DB, 'SELECT 1 FROM categories WHERE name=?', category).first()) throw new InputError('Informe nome e categoria.');
  const price = integer(p.price), cost = integer(p.cost), stock = individual ? 0 : integer(p.stock);
  const values = [name, text(p.scientific, 150), category, text(p.description), text(p.care), price, cost, stock, photo(p.image), p.active ? 1 : 0];
  if (p.id) {
    const id = integer(p.id, 1), old = await statement(env.DB, 'SELECT * FROM products WHERE id=?', id).first();
    if (!old || old.individual !== individual) throw new InputError('O tipo de estoque não pode ser alterado após o cadastro.');
    await env.DB.batch([
      statement(env.DB, "INSERT INTO movements(product_id,quantity,reason) SELECT id,?-stock,'Ajuste manual' FROM products WHERE id=? AND individual=0 AND stock!=?", stock, id, stock),
      statement(env.DB, 'UPDATE products SET name=?,scientific=?,category=?,description=?,care=?,price=?,cost=?,stock=?,image=?,active=? WHERE id=?', ...values, id),
    ]);
  } else {
    // last_insert_rowid is local to the batch; insert movement immediately.
    await env.DB.batch([
      statement(env.DB, 'INSERT INTO products(name,scientific,category,description,care,price,cost,stock,image,active,individual) VALUES (?,?,?,?,?,?,?,?,?,?,?)', ...values, individual),
      statement(env.DB, "INSERT INTO movements(product_id,quantity,reason) SELECT id,stock,'Cadastro' FROM products WHERE id=last_insert_rowid() AND stock>0"),
    ]);
  }
}
async function saveSpecimen(env, p) {
  const pid = integer(p.product_id, 1), code = text(p.code, 80), image = photo(p.image, true), notes = text(p.notes, 1000), available = p.available ? 1 : 0;
  if (!code || !await statement(env.DB, 'SELECT 1 FROM products WHERE id=? AND individual=1', pid).first()) throw new InputError('Informe um código e produto com estoque por exemplar.');
  if (p.id) {
    const id = integer(p.id, 1);
    // Guard in SQL prevents changes if a concurrent order reserved this unit.
    const guard = "id=? AND product_id=? AND NOT EXISTS(SELECT 1 FROM items i JOIN orders o ON o.id=i.order_id WHERE i.specimen_id=specimens.id AND o.status!='Cancelado')";
    const result = await env.DB.batch([
      statement(env.DB, `INSERT INTO movements(product_id,quantity,reason) SELECT product_id,?-available,'Exemplar '||code FROM specimens WHERE ${guard} AND available!=?`, available, id, pid, available),
      statement(env.DB, `UPDATE specimens SET code=?,notes=?,image=?,available=? WHERE ${guard}`, code, notes, image, available, id, pid),
    ]);
    if (!result[1].meta.changes) throw new InputError('Exemplar não encontrado ou vinculado a um pedido.');
  } else {
    await env.DB.batch([
      statement(env.DB, 'INSERT INTO specimens(product_id,code,notes,image,available) VALUES (?,?,?,?,?)', pid, code, notes, image, available),
      statement(env.DB, "INSERT INTO movements(product_id,quantity,reason) SELECT ?,1,? WHERE ?=1", pid, 'Exemplar ' + code, available),
    ]);
  }
}
async function dispatch(request, env) {
  const url = new URL(request.url), path = url.pathname;
  if (request.method === 'GET' && /^\/uploads\/[a-f0-9]{32}\.jpg$/.test(path)) {
    const image = await env.PHOTOS.get(path.slice('/uploads/'.length));
    if (!image) return response({error: 'Foto não encontrada.'}, 404);
    return new Response(image.body, {headers: {...security, 'Content-Type': 'image/jpeg', 'Cache-Control': 'public, max-age=86400'}});
  }
  if (!path.startsWith('/api/')) {
    if (request.method !== 'GET' && request.method !== 'HEAD') return response({error: 'Método não permitido.'}, 405);
    if (!['/', '/admin', '/admin.html', '/index.html', '/app.js', '/admin.js', '/style.css'].includes(path)) return response({error: 'Página não encontrada.'}, 404);
    const assetUrl = new URL(request.url);
    if (path === '/') assetUrl.pathname = '/index.html';
    if (path === '/admin') assetUrl.pathname = '/admin.html';
    const result = await env.ASSETS.fetch(new Request(assetUrl, request));
    const headers = new Headers(result.headers);
    for (const [key, value] of Object.entries(security)) headers.set(key, value);
    headers.set('Cache-Control', 'no-cache');
    return new Response(result.body, {status: result.status, headers});
  }
  if (!env.DB) return response({error: 'Banco não configurado.'}, 503);
  if (path.startsWith('/api/admin/') && !await authorized(request, env)) return response({error: 'Entre no painel.'}, 401);
  if (request.method === 'GET') {
    if (path === '/api/products') return response(await products(env, false));
    if (path === '/api/admin/products') return response(await products(env, true));
    if (path === '/api/categories') return response(await all(env.DB, 'SELECT * FROM categories'));
    if (path === '/api/admin/customers') return response(await all(env.DB, 'SELECT * FROM customers ORDER BY rowid DESC'));
    if (path === '/api/admin/movements') return response(await all(env.DB, 'SELECT m.*,p.name FROM movements m JOIN products p ON p.id=m.product_id ORDER BY m.id DESC'));
    if (path === '/api/admin/orders') {
      const orders = await all(env.DB, 'SELECT o.*,c.name,c.phone,c.address FROM orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.created DESC,o.rowid DESC');
      const items = await all(env.DB, 'SELECT * FROM items');
      for (const order of orders) order.items = items.filter(i => i.order_id === order.id);
      return response(orders);
    }
    return response({error: 'Rota não encontrada.'}, 404);
  }
  if (request.method !== 'POST') return response({error: 'Método não permitido.'}, 405);
  if (request.headers.get('Origin') !== url.origin) return response({error: 'Origem não autorizada.'}, 403);
  const max = path === '/api/admin/upload' ? 8000000 : 64000;
  if (Number(request.headers.get('Content-Length') || 0) > max) return response({error: 'Arquivo ou requisição muito grande.'}, 413);
  // Bound the streamed body too; Content-Length is not trusted.
  const reader = request.body?.getReader();
  let chunks = [], size = 0;
  if (!reader) throw new InputError('Requisição vazia.');
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    size += value.length;
    if (size > max) { await reader.cancel(); return response({error: 'Requisição muito grande.'}, 413); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  let p;
  try { p = JSON.parse(new TextDecoder().decode(bytes)); } catch { throw new InputError('Dados inválidos.'); }
  if (!p || Array.isArray(p) || typeof p !== 'object') throw new InputError('Dados inválidos.');
  if (path === '/api/login') {
    if (!env.ADMIN_PASSWORD || env.ADMIN_PASSWORD.length < 16) return response({error: 'Acesso administrativo ainda não configurado.'}, 503);
    if (!await rateLimit(request, env, 'login', 10)) return response({error: 'Muitas tentativas. Aguarde 15 minutos.'}, 429);
    const a = await hash(text(p.password, 256)), b = await hash(env.ADMIN_PASSWORD);
    let difference = 0; for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
    if (difference) return response({error: 'Senha inválida.'}, 401);
    const token = [...crypto.getRandomValues(new Uint8Array(32))].map(b => b.toString(16).padStart(2, '0')).join('');
    await env.DB.batch([
      statement(env.DB, 'DELETE FROM sessions WHERE expires<?', Date.now()),
      statement(env.DB, 'DELETE FROM rate_limits WHERE expires<?', Date.now()),
      statement(env.DB, 'INSERT INTO sessions(token,expires) VALUES (?,?)', await hash(token), Date.now() + 28800000),
    ]);
    const secure = url.protocol === 'https:' ? '; Secure' : '';
    return response({ok: true}, 200, {'Set-Cookie': `session=${token}; HttpOnly; SameSite=Strict${secure}; Path=/; Max-Age=28800`});
  }
  if (path === '/api/logout') {
    const token = /(?:^|;\s*)session=([a-f0-9]{64})(?:;|$)/.exec(request.headers.get('Cookie') || '')?.[1];
    if (token) await statement(env.DB, 'DELETE FROM sessions WHERE token=?', await hash(token)).run();
    return response({ok: true}, 200, {'Set-Cookie': 'session=; HttpOnly; SameSite=Strict; Secure; Path=/; Max-Age=0'});
  }
  if (path === '/api/orders') {
    if (!await rateLimit(request, env, 'order', 15)) return response({error: 'Muitos pedidos. Aguarde 15 minutos.'}, 429);
    return response(await createOrder(env, p), 201);
  }
  if (!path.startsWith('/api/admin/')) return response({error: 'Rota não encontrada.'}, 404);
  if (path === '/api/admin/upload') {
    if (!env.PHOTOS) return response({error: 'Armazenamento de fotos não configurado.'}, 503);
    if (typeof p.data !== 'string') throw new InputError('Foto inválida.');
    let data; try { data = Uint8Array.from(atob(p.data), c => c.charCodeAt(0)); } catch { throw new InputError('Foto inválida.'); }
    if (data.length > 5000000 || data.length < 4 || data[0] !== 255 || data[1] !== 216 || data[2] !== 255 || data.at(-2) !== 255 || data.at(-1) !== 217) throw new InputError('Envie uma foto JPEG de até 5 MB.');
    const key = crypto.randomUUID().replaceAll('-', '') + '.jpg';
    await env.PHOTOS.put(key, data, {httpMetadata: {contentType: 'image/jpeg'}});
    return response({url: '/uploads/' + key}, 201);
  }
  if (path === '/api/admin/products') await saveProduct(env, p);
  else if (path === '/api/admin/specimens') await saveSpecimen(env, p);
  else if (path === '/api/admin/categories') {
    const name = text(p.name, 80); if (!name) throw new InputError('Informe o nome.');
    await statement(env.DB, 'INSERT INTO categories(name) VALUES (?)', name).run();
  } else if (path === '/api/admin/orders') {
    if (!statuses.includes(p.status) || !payments.includes(p.payment)) throw new InputError('Situação inválida.');
    const result = await statement(env.DB, 'UPDATE orders SET status=?,payment=? WHERE id=?', p.status, p.payment, text(p.id, 36)).run();
    if (!result.meta.changes) throw new InputError('Pedido não encontrado.');
  } else return response({error: 'Rota não encontrada.'}, 404);
  return response({ok: true});
}
export default {
  async fetch(request, env) {
    try { return await dispatch(request, env); }
    catch (error) {
      if (error instanceof InputError) return response({error: error.message}, 400);
      // Never disclose SQL, credentials or customer information in responses/logs.
      if (/D1_ERROR.*(?:Estoque insuficiente|Exemplar indisponível|preço mudou|Produto indisponível|Pedido cancelado|UNIQUE constraint)/s.test(String(error))) return response({error: 'Registro duplicado, pedido cancelado ou item indisponível. Atualize a página e confira os dados.'}, 409);
      return response({error: 'Não foi possível concluir. Tente novamente ou contate a equipe.'}, 500);
    }
  },
};
