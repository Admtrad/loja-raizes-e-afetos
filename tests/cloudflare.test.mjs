import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import worker from '../cloudflare/worker.js';

function setup() {
  const sql = new DatabaseSync(':memory:');
  sql.exec('PRAGMA foreign_keys=ON');
  sql.exec(readFileSync(new URL('../cloudflare/migrations/0001_store.sql', import.meta.url), 'utf8'));
  const prepare = query => ({bind(...args) {
    const stmt = sql.prepare(query);
    return {
      async first() { return stmt.get(...args) || null; },
      async all() { return {results: stmt.all(...args)}; },
      async run() {
        try { const r = stmt.run(...args); return {meta: {changes: Number(r.changes)}}; }
        catch (error) { throw Error('D1_ERROR: ' + error.message); }
      },
    };
  }});
  sql.exec(readFileSync(new URL('../cloudflare/migrations/0002_product_photos.sql', import.meta.url), 'utf8'));
  const images = new Map();
  const env = {
    ADMIN_PASSWORD: 'senha-local-somente-para-testes',
    DB: {prepare, async batch(queries) {
      sql.exec('BEGIN');
      try { const results = []; for (const q of queries) results.push(await q.run()); sql.exec('COMMIT'); return results; }
      catch (error) { sql.exec('ROLLBACK'); throw Error('D1_ERROR: ' + error.message); }
    }},
    ASSETS: {async fetch() { return new Response('<html>loja</html>'); }},
    PHOTOS: {async put(key, value) { images.set(key, value); }, async get(key) { return images.has(key) ? {body: images.get(key)} : null; }},
  };
  let cookie = '';
  async function request(path, data, options = {}) {
    const headers = {'Origin': 'https://loja.example', 'CF-Connecting-IP': options.ip || '192.0.2.1', ...options.headers};
    if (cookie && options.auth !== false) headers.Cookie = cookie;
    const r = await worker.fetch(new Request('https://loja.example' + path, {method: data === undefined ? 'GET' : 'POST', headers, body: data === undefined ? undefined : JSON.stringify(data)}), env);
    return r;
  }
  async function login() {
    const r = await request('/api/login', {password: env.ADMIN_PASSWORD});
    assert.equal(r.status, 200); cookie = r.headers.get('Set-Cookie').split(';')[0];
    assert.match(r.headers.get('Set-Cookie'), /Secure/); assert.match(r.headers.get('Set-Cookie'), /HttpOnly/);
  }
  async function product(individual = false) {
    const r = await request('/api/admin/products', {name: 'Planta teste', category: 'Interior', scientific: '', price: 2500, cost: 1000, stock: 3, active: true, individual});
    assert.equal(r.status, 200, await r.text());
    if (individual) {
      const unit = await request('/api/admin/specimens', {product_id: 1, code: 'MON-001', image: 'https://example.com/plant.jpg', available: true});
      assert.equal(unit.status, 200);
    }
  }
  const payload = sid => ({name: 'Teste', phone: 'Contato teste', delivery: 'Retirada na loja', address: '', items: [{id: 1, quantity: 1, price: 1, ...(sid ? {specimen_id: sid} : {})}]});
  return {sql, env, request, login, product, payload};
}

test('painel privado, sessão Secure e preços internos ocultos', async () => {
  const s = setup();
  assert.equal((await s.request('/api/admin/customers')).status, 401);
  await s.login(); await s.product();
  const p = (await (await s.request('/api/products')).json())[0];
  assert.equal(p.price, 2500); assert.equal(p.cost, undefined);
  await s.request('/api/logout', {});
  assert.equal((await s.request('/api/admin/customers')).status, 401);
  s.sql.close();
});
test('pedido calcula preço no servidor e rejeita estoque insuficiente sem registros parciais', async () => {
  const s = setup(); await s.login(); await s.product();
  const order = await (await s.request('/api/orders', s.payload())).json(); assert.equal(order.total, 2500);
  const p = s.payload(); p.items[0].quantity = 4;
  assert.equal((await s.request('/api/orders', p)).status, 409);
  assert.equal(s.sql.prepare('SELECT COUNT(*) AS n FROM orders').get().n, 1);
  assert.equal(s.sql.prepare('SELECT COUNT(*) AS n FROM customers').get().n, 1);
  assert.equal(s.sql.prepare('SELECT stock FROM products').get().stock, 2);
  s.sql.close();
});
test('exemplar não pode ser vendido duas vezes e cancelamento devolve uma vez', async () => {
  const s = setup(); await s.login(); await s.product(true);
  const order = await (await s.request('/api/orders', s.payload(1))).json(); assert.equal(order.total, 2500);
  assert.equal((await s.request('/api/orders', s.payload(1))).status, 409);
  for (let i = 0; i < 2; i++) assert.equal((await s.request('/api/admin/orders', {id: order.id, status: 'Cancelado', payment: 'Pendente'})).status, 200);
  assert.equal(s.sql.prepare('SELECT available FROM specimens').get().available, 1);
  assert.equal(s.sql.prepare('SELECT COUNT(*) AS n FROM movements WHERE reason LIKE ?').get('Cancelamento%').n, 1);
  assert.equal((await s.request('/api/admin/orders', {id: order.id, status: 'Recebido', payment: 'Pendente'})).status, 409);
  s.sql.close();
});
test('duas linhas do mesmo exemplar abortam o pedido inteiro', async () => {
  const s = setup(); await s.login(); await s.product(true);
  const p = s.payload(1); p.items.push({...p.items[0]});
  assert.equal((await s.request('/api/orders', p)).status, 400);
  assert.equal(s.sql.prepare('SELECT COUNT(*) AS n FROM orders').get().n, 0);
  s.sql.close();
});
test('foto autenticada vai para R2 e é entregue com MIME seguro', async () => {
  const s = setup();
  assert.equal((await s.request('/api/admin/upload', {data: ''})).status, 401);
  await s.login();
  assert.equal((await s.request('/api/admin/upload', {data: btoa('<svg>bad</svg>')})).status, 400);
  const uploaded = await s.request('/api/admin/upload', {data: btoa('\xff\xd8\xff\x00\xff\xd9')});
  assert.equal(uploaded.status, 201);
  const {url} = await uploaded.json();
  const image = await s.request(url); assert.equal(image.status, 200); assert.equal(image.headers.get('Content-Type'), 'image/jpeg');
  assert.equal((await s.request('/uploads/../../server.py')).status, 404);
  s.sql.close();
});
test('galeria preserva capa antiga e respeita o limite configurado', async () => {
  const s = setup();
  await s.login();
  await s.product();
  s.sql.exec("UPDATE products SET image='https://example.com/antiga.jpg' WHERE id=1");
  const catalog = async () => (await (await s.request('/api/products')).json())[0];
  assert.deepEqual((await catalog()).images, ['https://example.com/antiga.jpg']);
  const images = Array.from({length: 5}, (_, i) => `https://example.com/${i}.jpg`);
  const product = {id: 1, name: 'Planta', category: 'Interior', price: 2500, cost: 1000, stock: 3, active: true, images};
  assert.equal((await s.request('/api/admin/products', product)).status, 409);
  assert.equal((await s.request('/api/admin/settings', {photo_limit: 5})).status, 200);
  assert.equal((await s.request('/api/admin/products', product)).status, 200);
  assert.deepEqual((await catalog()).images, images);
  assert.equal((await catalog()).image, images[0]);
  assert.equal((await s.request('/api/admin/settings', {photo_limit: 4})).status, 409);
  s.sql.close();
});

test('limite de login e validação de origem', async () => {
  const s = setup();
  assert.equal((await s.request('/api/login', {}, {headers: {Origin: 'https://outro.example'}})).status, 403);
  for (let i = 0; i < 10; i++) assert.equal((await s.request('/api/login', {password: 'errada'})).status, 401);
  assert.equal((await s.request('/api/login', {password: s.env.ADMIN_PASSWORD})).status, 429);
  s.sql.close();
});
