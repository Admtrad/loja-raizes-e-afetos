const $=s=>document.querySelector(s), money=n=>(n/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'}),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let photoLimit=4;
let tab='products',rows=[],categories=[];
async function api(path,payload){const r=await fetch('/api/'+path,payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{});const data=await r.json();if(!r.ok){if(r.status===401){$('#workspace').hidden=true;$('#login').hidden=false}throw Error(data.error)}return data}
function table(heads,body){return `<div class="panel table-wrap"><table><thead><tr>${heads.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${body||`<tr><td colspan="${heads.length}">Nenhum registro ainda.</td></tr>`}</tbody></table></div>`}
function productForm(p={}){return `<form id="productForm" class="panel"><h2>${p.id?'Editar produto':'Cadastrar produto'}</h2><input name="id" type="hidden" value="${p.id||''}"><div class="form-grid">${[['name','Nome popular',p.name||''],['scientific','Nome científico',p.scientific||'']].map(([key,label,value])=>`<label>${label}<input name="${key}" value="${esc(value)}" ${key==='name'?'required':''} maxlength="150"></label>`).join('')}<label>Categoria<select name="category">${categories.map(c=>`<option ${p.category===c.name?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><div class="wide">${productPhotoFields(p)}</div><label>Controle de estoque<select name="individual" ${p.id?'disabled':''}><option value="0" ${!p.individual?'selected':''}>Quantidade (unidades equivalentes)</option><option value="1" ${p.individual?'selected':''}>Exemplares identificados individualmente</option></select></label><label>Preço de venda (R$)<input name="price" type="number" min="0" step="0.01" required value="${((p.price||0)/100).toFixed(2)}"></label><label>Custo (R$)<input name="cost" type="number" min="0" step="0.01" required value="${((p.cost||0)/100).toFixed(2)}"></label><label>Estoque (unidades)<input name="stock" ${p.individual?'readonly':''} type="number" min="0" step="1" required value="${p.stock||0}"></label><label>Disponibilidade<select name="active"><option value="1" ${p.active!==0?'selected':''}>Visível na loja</option><option value="0" ${p.active===0?'selected':''}>Oculto</option></select></label><label class="wide">Descrição, tamanho e vaso incluído<textarea name="description" maxlength="2000">${esc(p.description||'')}</textarea></label><label class="wide">Luz, rega, ambiente e informações para tutores de animais<textarea name="care" maxlength="2000">${esc(p.care||'')}</textarea></label></div><button type="submit">Salvar produto</button> <button type="button" data-reset="1" class="outline">Limpar</button><p data-save-status role="status" aria-live="polite"></p></form>${p.individual?specimenPanel(p):''}` }
async function render(){try{categories=await api('categories');const data=await api('admin/'+tab);if(tab==='settings'){photoLimit=data.photo_limit;$('#content').innerHTML=settingsForm()}else{rows=data;if(tab==='products')photoLimit=(await api('admin/settings')).photo_limit;}$('#workspace').hidden=false;$('#login').hidden=true;$('#logout').hidden=false;document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('outline',b.dataset.tab!==tab));if(tab==='products')$('#content').innerHTML='<div id="editor">'+productForm()+'</div>'+table(['Produto','Categoria','Preço','Estoque','Situação',''],rows.map(p=>`<tr><td>${esc(p.name)}</td><td>${esc(p.category)}</td><td>${money(p.price)}</td><td>${p.stock}</td><td>${p.active?'Visível':'Oculto'}</td><td><button class="outline" data-edit="${p.id}">Editar</button></td></tr>`).join(''));if(tab==='categories')$('#content').innerHTML='<form id="categoryForm" class="panel"><h2>Nova categoria</h2><label>Nome<input name="name" required maxlength="80"></label><button>Cadastrar</button></form>'+table(['Categoria'],categories.map(c=>`<tr><td>${esc(c.name)}</td></tr>`).join(''));if(tab==='customers')$('#content').innerHTML=table(['Nome','Contato','Endereço'],rows.map(c=>`<tr><td>${esc(c.name)}</td><td>${esc(c.phone)}</td><td>${esc(c.address)}</td></tr>`).join(''));if(tab==='movements')$('#content').innerHTML=table(['Data (UTC)','Produto','Quantidade','Motivo'],rows.map(m=>`<tr><td>${esc(m.created)}</td><td>${esc(m.name)}</td><td>${m.quantity>0?'+':''}${m.quantity}</td><td>${esc(m.reason)}</td></tr>`).join(''));if(tab==='orders')$('#content').innerHTML=rows.map(o=>`<form class="panel orderForm" data-id="${o.id}"><h2>Pedido #${o.id} · ${money(o.total)}</h2><p>${esc(o.name)} · ${esc(o.phone)}<br>${esc(o.delivery)} · ${esc(o.address)}</p><p>${o.items.map(i=>`${i.quantity} × ${esc(i.name)} (${money(i.price)})`).join('<br>')}</p><div class="form-grid"><label>Andamento<select name="status">${['Recebido','Em preparação','Enviado','Entregue','Cancelado'].map(s=>`<option ${s===o.status?'selected':''}>${s}</option>`).join('')}</select></label><label>Pagamento<select name="payment">${['Pendente','Pago','Reembolsado'].map(s=>`<option ${s===o.payment?'selected':''}>${s}</option>`).join('')}</select></label></div><button>Atualizar pedido</button><p class="muted">Cancelar devolve o estoque automaticamente. Reembolso precisa ser feito no meio de pagamento utilizado.</p></form>`).join('')||'<p class="panel">Os primeiros pedidos aparecerão aqui.</p>'}catch(e){if(!$('#login').hidden)$('#loginMessage').textContent='';else $('#message').textContent=e.message}}
$('#login').onsubmit=async e=>{e.preventDefault();try{await api('login',Object.fromEntries(new FormData(e.target)));e.target.reset();await render()}catch(err){$('#loginMessage').textContent=err.message}};
$('#logout').onclick=async()=>{await api('logout',{});$('#workspace').hidden=true;$('#login').hidden=false;$('#logout').hidden=true};
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.tab){tab=b.dataset.tab;$('#message').textContent='';render()}if(b.dataset.edit){$('#editor').innerHTML=productForm(rows.find(p=>p.id===+b.dataset.edit));window.scrollTo({top:0,behavior:'smooth'})}if(b.dataset.reset)$('#editor').innerHTML=productForm()});
$('#content').addEventListener('invalid', event => {
  const field = event.target;
  const status = field.form?.querySelector('[data-save-status]');
  if (!status) return;
  const label = field.labels?.[0]?.textContent.trim() || 'Campo obrigatório';
  status.textContent = `${label}. ${field.validationMessage}`;
}, true);

$('#content').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.target;
  const formId = form.getAttribute('id');
  const button = form.querySelector('button[type="submit"]') || form.querySelector('button');
  const status = form.querySelector('[data-save-status]') || $('#message');
  if (button.disabled) return;
  button.disabled = true;
  status.textContent = 'Salvando…';
  try {
    const fields = new FormData(form);
    const product = Object.fromEntries(fields);
    if (formId === 'productForm') {
      product.images = fields.getAll('image').map(value => value.trim()).filter(Boolean);
      delete product.image;
      product.price = Math.round(Number(product.price) * 100);
      product.cost = Math.round(Number(product.cost) * 100);
      product.stock = Number(product.stock);
      product.active = product.active === '1';
      product.individual = product.id ? Boolean(rows.find(row => row.id === Number(product.id))?.individual) : product.individual === '1';
      await api('admin/products', product);
    } else if (formId === 'specimenForm') {
      product.product_id = Number(product.product_id);
      product.available = product.available === '1';
      await api('admin/specimens', product);
    } else if (formId === 'settingsForm') {
      await api('admin/settings', {photo_limit:Number(product.photo_limit)});
    } else if (formId === 'categoryForm') {
      await api('admin/categories', product);
    } else if (form.classList.contains('orderForm')) {
      product.id = form.dataset.id;
      await api('admin/orders', product);
    } else {
      throw new Error('Formulário desconhecido.');
    }
    const edited = Number(product.product_id || product.id || 0);
    await render();
    if (tab === 'products' && edited && rows.some(row => row.id === edited)) {
      $('#editor').innerHTML = productForm(rows.find(row => row.id === edited));
    }
    const feedback = $('#productForm [data-save-status]') || $('#message');
    feedback.textContent = 'Salvo com sucesso.';
  } catch (error) {
    const feedback = $('#workspace').hidden ? $('#loginMessage') : status;
    feedback.textContent = `Falha ao salvar. ${error.message}`;
  } finally {
    button.disabled = false;
  }
});
render();

function settingsForm(){
  return `<form id="settingsForm" class="panel"><h2>Configurações</h2>
    <label>Limite de fotos por produto<input name="photo_limit" type="number" min="1" max="20" required value="${photoLimit}"></label>
    <p class="muted">Escolha de 1 a 20 fotos. Para reduzir o limite, retire primeiro as fotos excedentes dos produtos cadastrados.</p>
    <button>Salvar configurações</button></form>`;
}
function productPhotoFields(product){
  const images=product.images || (product.image ? [product.image] : []);
  const fields=Array.from({length:photoLimit},(_,index)=>`<div>${photoFields(images[index] || '',index===0?'Foto 1 (capa)':`Foto ${index+1}`)}</div>`);
  return `<fieldset class="product-photos"><legend>Fotos do produto (até ${photoLimit})</legend>
    <p class="muted">A primeira foto preenchida será a capa. Para remover uma foto, apague o endereço e salve o produto.</p>
    ${fields.join('')}</fieldset>`;
}
function photoFields(image,label){return `<label>${label}<input name="image" value="${esc(image)}" placeholder="URL HTTPS ou envie uma foto"></label><div class="photo-actions"><label class="upload-button">Tirar foto<input type="file" accept="image/*" capture="environment" data-photo hidden></label><label class="upload-button">Escolher da galeria<input type="file" accept="image/*" data-photo hidden></label></div><p class="muted" data-upload-status role="status"></p><img class="photo-preview" src="${esc(image)}" alt="Prévia da foto" ${image?'':'hidden'}>`}
function specimenPanel(p){return `<section id="specimenPanel" class="panel"><h2>Exemplares de ${esc(p.name)}</h2><p>Cada código identifica uma unidade física. O estoque é a contagem dos exemplares disponíveis.</p><form id="specimenForm"><input type="hidden" name="product_id" value="${p.id}"><input type="hidden" name="id" value=""><label>Código único do exemplar<input name="code" required maxlength="80" placeholder="Ex.: MON-001"></label><label>Características desta unidade<textarea name="notes" maxlength="1000" placeholder="Altura, quantidade de folhas, particularidades…"></textarea></label><div>${photoFields('', 'Foto real do exemplar (obrigatória)')}</div><label>Disponibilidade<select name="available"><option value="1">Disponível</option><option value="0">Indisponível</option></select></label><button>Salvar exemplar</button></form><div class="specimen-grid">${p.specimens.map(s=>`<article class="specimen-card"><img src="${esc(s.image)}" alt="Exemplar ${esc(s.code)}"><strong>${esc(s.code)}</strong><p>${esc(s.notes)}</p><p>${s.available?'Disponível':'Indisponível ou em pedido'}</p><button type="button" class="outline" data-specimen="${s.id}" data-product="${p.id}">Editar exemplar</button></article>`).join('')}</div></section>`}
document.addEventListener('click',e=>{const b=e.target.closest('[data-specimen]');if(!b)return;const p=rows.find(p=>p.id===+b.dataset.product),s=p.specimens.find(s=>s.id===+b.dataset.specimen),f=$('#specimenForm');for(const name of ['id','code','notes','image'])f.elements[name].value=s[name];f.elements.available.value=String(s.available);const img=f.querySelector('.photo-preview');img.src=s.image;img.hidden=false;f.scrollIntoView({behavior:'smooth',block:'start'})});
document.addEventListener('change',async e=>{if(!e.target.matches('[data-photo]')||!e.target.files[0])return;const file=e.target.files[0],container=e.target.closest('.photo-actions').parentElement,status=container.querySelector('[data-upload-status]'),form=e.target.closest('form'),button=form.querySelector('button');container.dataset.uploading='';status.textContent='Preparando foto…';button.disabled=true;try{if(!file.type.startsWith('image/')||file.size>25000000)throw Error('Escolha uma imagem de até 25 MB.');const bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});const scale=Math.min(1,1600/Math.max(bitmap.width,bitmap.height)),canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();const data=canvas.toDataURL('image/jpeg',0.85).split(',')[1];const result=await api('admin/upload',{data});container.querySelector('[name="image"]').value=result.url;const image=container.querySelector('img');image.src=result.url;image.hidden=false;status.textContent='Foto enviada. Salve o cadastro para confirmar.'}catch(err){status.textContent='Não foi possível enviar. '+err.message+' Se necessário, selecione uma imagem JPEG ou PNG.'}finally{delete container.dataset.uploading;button.disabled=Boolean(form.querySelector('[data-uploading]'));e.target.value=''}});
