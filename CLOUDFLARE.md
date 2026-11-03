# Hospedar a loja na Cloudflare

Publicação inicial realizada em 03/11/2026:

- Loja: https://loja-raizes-e-afetos.loja-raizes-e-afetos.workers.dev
- Painel: https://loja-raizes-e-afetos.loja-raizes-e-afetos.workers.dev/admin
- D1 `raizes-afetos-db` e R2 privado `raizes-afetos-fotos` criados e vinculados.
- Senha administrativa armazenada como segredo `ADMIN_PASSWORD`, sem valor neste repositório.

O subdomínio workers.dev é independente do domínio e do sistema anterior. Os dados locais não foram importados.

Na verificação imediatamente após a primeira publicação, o endpoint retornou falha de negociação TLS (`ERR_SSL_VERSION_OR_CIPHER_MISMATCH`). A implantação foi confirmada pela API, mas o acesso HTTPS externo ainda precisa ser verificado após a ativação do endereço/certificado. Não desative a validação HTTPS nem altere as configurações do domínio existente para contornar essa pendência.

Use a conta Cloudflare existente. Este projeto cria recursos exclusivos: Worker `loja-raizes-e-afetos`, D1 `raizes-afetos-db` e bucket R2 privado `raizes-afetos-fotos`. Nenhuma zona DNS ou aplicação existente precisa ser alterada. As franquias e cobranças podem ser compartilhadas com outros projetos da conta.

## Antes de publicar

- Entre em https://dash.cloudflare.com e selecione a conta correta.
- Mantenha o plano Workers Free. Não é necessário comprar domínio; a primeira publicação usa `workers.dev` e HTTPS.
- Em **Storage & databases → R2**, confira se o R2 já está ativo. A ativação exige checkout e pode solicitar meio de pagamento. O titular deve revisar e aceitar pessoalmente essa etapa. Há cobrança se o consumo ultrapassar a franquia; não há promessa de custo zero ilimitado.
- Não crie tokens de API nem envie senhas pelo chat. A autenticação da ferramenta oficial Wrangler usa o navegador.

## Configuração pelo terminal

Nesta pasta, com Node.js instalado:

```powershell
npm ci
npx wrangler login --scopes account:read user:read workers:write workers_scripts:write d1:write
npx wrangler whoami
```

Confirme a conta antes de criar qualquer recurso. Se houver múltiplas contas, adicione `account_id` ao `wrangler.jsonc` com o ID da conta escolhida.

```powershell
npx wrangler d1 create raizes-afetos-db
```

Copie o `database_id` retornado para o binding `DB` em `wrangler.jsonc`, substituindo o UUID de zeros. Não reutilize o banco de outro sistema.

```powershell
npx wrangler r2 bucket create raizes-afetos-fotos
npm run db:remote
npx wrangler secret put ADMIN_PASSWORD
```

Informe diretamente no terminal uma senha exclusiva com pelo menos 16 caracteres. Não reutilize a senha local já compartilhada no chat. O segredo será guardado na Cloudflare e não no GitHub. Se a ferramenta precisar criar o Worker antes do segredo, ela solicitará a criação do Worker com o nome deste projeto; sem senha, o painel permanece bloqueado.

```powershell
npm run deploy
```

Abra a URL HTTPS retornada. `/admin` é o painel. Teste catálogo, cadastro, envio de foto do celular, pedido e cancelamento. A abertura da câmera depende do dispositivo; a galeria funciona como alternativa. O bucket não precisa ficar público: somente o Worker entrega as fotos pelo endereço `/uploads/…`.

## Teste local da versão Cloudflare

O servidor Python local continua disponível e independente. Para testar o Worker:

```powershell
npm run db:local
# Crie .dev.vars localmente com ADMIN_PASSWORD="uma-senha-local-de-teste-com-16-caracteres"
npm run dev
```

`.dev.vars`, `.wrangler`, banco e fotos não entram no Git. `wrangler dev` usa armazenamento local por padrão; não habilite bindings remotos durante testes. Os testes Node exigem Node 22.13+ com `node:sqlite`:

```powershell
npm run check
npm run test:cloudflare
```

## Dados existentes e backups

O D1 começa vazio, com as categorias iniciais. Os dados do SQLite Python e fotos locais **não são migrados automaticamente**; a migração deve ser planejada antes de operar nos dois ambientes para evitar divergências. Não publique o arquivo SQLite no GitHub.

Para exportar o banco remoto:

```powershell
New-Item -ItemType Directory -Force backups
npx wrangler d1 export DB --remote --output backups/loja.sql
```

Guarde uma cópia privada fora do computador. Esse arquivo contém dados de clientes e não inclui as imagens. Faça também backup dos objetos R2; as fotos são imutáveis e os nomes originais devem ser preservados para restauração. O D1 oferece Time Travel, sujeito à retenção do plano; isso não substitui backup das fotos. Confira regularmente uso de Workers, D1 e R2 e as opções de alertas na conta.

## Segurança incluída

HTTPS na hospedagem, cookie HttpOnly/Secure/SameSite, expiração de sessão em 8 horas, token de sessão armazenado como hash, verificação de origem nos POSTs, limite de login (10 por IP/15 min) e de pedidos (15 por IP/15 min), limite de tamanho de upload e cabeçalhos de segurança. Preços e estoque são validados no servidor e a reserva acontece em batch transacional no D1.

É uma proteção inicial para loja pequena, sem pagamento online, e não uma auditoria de segurança completa. Pedidos anônimos ainda podem ser usados para reservar estoque indevidamente; acompanhe pedidos pendentes e cancele os inválidos. Anti-bot com Turnstile e contas individuais de equipe podem ser adicionados conforme o uso. O painel tem um único acesso administrativo.

Referências oficiais: https://developers.cloudflare.com/d1/get-started/ · https://developers.cloudflare.com/r2/get-started/ · https://developers.cloudflare.com/workers/wrangler/commands/ · https://developers.cloudflare.com/r2/pricing/
