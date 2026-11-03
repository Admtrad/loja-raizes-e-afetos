# Loja Raízes e Afetos

Repositório: https://github.com/Admtrad/loja-raizes-e-afetos

Primeira versão local de uma loja de plantas ornamentais. Python 3.11 ou superior, sem pacotes adicionais.

## Executar no Windows

Abra o PowerShell nesta pasta e execute:

```powershell
$env:ADMIN_PASSWORD = Read-Host 'Crie uma senha administrativa (mínimo 12 caracteres)'
python server.py
```

Abra http://127.0.0.1:8000 para a loja e http://127.0.0.1:8000/admin para a gestão. A senha fica na sessão do PowerShell; informe-a novamente ao reiniciar. O servidor aceita conexões apenas deste computador. Use `Ctrl+C` para parar.

## Primeiro uso

1. Entre na gestão com a senha definida ao iniciar.
2. Cadastre categorias e produtos reais: preço, custo, estoque, descrição, tamanho, vaso incluído, cuidados e foto HTTPS opcional.
3. Abra a loja e teste uma compra. Não há produtos ou clientes fictícios pré-cadastrados.
4. Acompanhe pedidos, registre o pagamento após conferi-lo e atualize a preparação/entrega.

O catálogo oferece busca, categorias, detalhes e sacola. O pedido registra os dados de contato, modalidade de recebimento e endereço. O servidor calcula os totais usando os preços do banco e reserva o estoque na mesma transação. Cancelar devolve o estoque uma única vez. Produtos podem ser ocultados sem apagar o histórico. O painel também mostra clientes e movimentações de estoque. Variações de tamanho/vaso devem ser cadastradas como produtos distintos nesta versão.

## Dados e limites desta versão

### Produtos com exemplares únicos

No cadastro de um novo produto, selecione **Exemplares identificados individualmente** em **Controle de estoque**. Salve o produto e clique em **Editar** na lista para abrir a seção **Exemplares**. Cadastre um código único (por exemplo, MON-001), características e a foto real de cada unidade. O preço, a categoria e a descrição continuam no produto principal. O estoque passa a ser calculado pelos exemplares disponíveis. O tipo de controle fica fixo após criar o produto para preservar o histórico; os produtos anteriores continuam com estoque por quantidade.

A foto do produto principal é identificada como foto padronizada. Na loja, **Escolher exemplar** mostra as fotos reais e o código de cada unidade disponível; o código também aparece na sacola e no pedido. Colocar na sacola não reserva a planta: a reserva acontece ao registrar o pedido. Dois clientes não podem comprar a mesma unidade. Cancelar libera exatamente o exemplar escolhido, uma única vez.

O cadastro oferece **Tirar foto** e **Escolher da galeria**, tanto para a foto padronizada quanto para a foto real. No computador, esses controles podem abrir o seletor de arquivos; a abertura direta da câmera depende do navegador/celular. A imagem é redimensionada para até 1.600 pixels e convertida para JPEG antes do envio. Arquivos incompatíveis (incluindo alguns HEIC) precisam ser convertidos para JPEG/PNG. As fotos ficam em `data/uploads`, fora do GitHub, e devem acompanhar o backup do banco. Fotos enviadas sem salvar o cadastro podem permanecer sem vínculo.

O layout se adapta a celular e desktop, mas o endereço `127.0.0.1` só funciona no computador que executa a aplicação. Para usar no celular, será necessário disponibilizar a loja em hospedagem HTTPS; esta atualização não abre acesso à rede nem publica o painel. Banco e fotos precisam de armazenamento persistente na hospedagem.

Os registros ficam em `data/store.sqlite3`, fora do Git. GitHub guarda o código, não sincroniza o banco de clientes e pedidos. Para backup, pare o servidor e copie a pasta `data` para armazenamento privado. Para restaurar, pare o servidor e substitua essa pasta pela cópia. Não envie banco de dados, senhas ou dados de clientes ao repositório.

Esta versão é local, com um único acesso administrativo. Não a exponha diretamente à internet. Uma operação pública exige hospedagem com HTTPS, banco persistente com backups, proteção contra abuso, recuperação de acesso, configuração das regiões/taxas de entrega e revisão das informações comerciais e de privacidade. Ainda não existem cobrança online, notificações, frete calculado ou login de clientes. Pagamento e entrega são combinados manualmente; o site informa isso antes de registrar o pedido. Alterar o pagamento para "Reembolsado" registra o controle e não transfere dinheiro.

Fotos precisam ser próprias ou licenciadas. Preencha os cuidados, inclusive informações sobre animais, com conteúdo verificado para cada espécie.

## Colocar no GitHub

1. Crie no GitHub um repositório **privado** chamado `loja-raizes-e-afetos`, sem adicionar README, licença ou `.gitignore` pelo site.
2. No terminal desta pasta, confira os arquivos com `git status` e execute (substitua `SEU-USUARIO`):

```powershell
git add .gitignore README.md server.py public tests
git commit -m "Cria primeira versão da loja Raízes e Afetos"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/loja-raizes-e-afetos.git
git push -u origin main
```

Se o Git solicitar sua identidade, configure `git config user.name "Seu Nome"` e `git config user.email "Seu email ou email privado do GitHub"` nesta pasta. A autenticação do push deve acontecer pelo gerenciador de credenciais do Git, sem colocar tokens nos arquivos.

Nos demais computadores, use `git clone` com a URL do repositório e siga as instruções de execução. Para atualizar, use `git pull`; para salvar novas alterações, revise `git diff`, faça `git add`, `git commit` e `git push`. Cada cópia local terá seu próprio banco; compartilhar uma única loja em vários dispositivos requer hospedagem da aplicação.

```powershell
git clone https://github.com/Admtrad/loja-raizes-e-afetos.git
cd loja-raizes-e-afetos
```

Em um repositório privado, autentique o Git com uma conta que tenha acesso. Antes de trabalhar em outro computador, envie as alterações do computador atual com `git push`; no outro, execute `git pull --ff-only` antes de editar.

## Verificação

```powershell
python -m unittest discover -s tests -v
node --check public/app.js
node --check public/admin.js
```

Os testes cobrem recálculo de preço, redução e devolução de estoque, rejeição de pedidos sem estoque e privacidade das rotas administrativas.
