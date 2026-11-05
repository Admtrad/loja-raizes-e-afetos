import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

test('cadastro usa o atributo do formulário mesmo com campo chamado id', async () => {
  const source = readFileSync(new URL('../public/admin.js', import.meta.url), 'utf8');
  const start = source.indexOf("$('#content').addEventListener('submit'");
  const end = source.indexOf('\nrender();', start);
  let submit;
  const status = {};
  const button = {disabled:false};
  const calls = [];
  const fields = [['id',''],['name','Planta'],['price','25.00'],['cost','10.00'],['stock','2'],['active','1'],['individual','0'],['image','https://example.com/foto.jpg']];
  const form = {
    id: {value:''}, // HTMLFormElement named access masks the id property.
    getAttribute: name => name === 'id' ? 'productForm' : null,
    querySelector: selector => selector.includes('button') ? button : status,
  };
  class FormDataStub {
    [Symbol.iterator]() {return fields[Symbol.iterator]();}
    getAll(name) {return fields.filter(([key])=>key===name).map(([,value])=>value);}
  }
  const context = {
    $: selector => selector === '#content' ? {addEventListener: (_,handler)=>{submit=handler;}} : status,
    FormData: FormDataStub,
    api: async (path,payload)=>calls.push({path,payload}),
    render: async ()=>{},
    rows: [],
    tab:'products',
  };
  vm.runInNewContext(source.slice(start,end),context);
  await submit({target:form,preventDefault(){}});
  assert.equal(calls.length,1);
  assert.equal(calls[0].path,'admin/products');
  assert.equal(calls[0].payload.price,2500);
  assert.equal(status.textContent,'Salvo com sucesso.');
});
