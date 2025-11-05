# Ajuste de Edição de Produtos - Sem Obrigatoriedade de Quantidade

## Problema
Anteriormente, para editar informações de um produto (nome, preço, categoria, descrição, foto), era **obrigatório** adicionar uma quantidade. Isso não era intuitivo para o usuário que apenas queria editar os dados do produto.

## Solução Implementada

### 1. **Validação Frontend (produtos.html)**
- Modificada a lógica de validação do formulário para distinguir entre:
  - **Criar novo produto**: Todos os campos (nome, categoria, preço venda, preço compra, quantidade) são obrigatórios
  - **Editar produto existente**: Campos "quantidade" e "preço de compra" são agora **opcionais**

- A dica de quantidade (`#dica-quantidade`) agora é ocultada automaticamente quando você clica em "Editar", deixando o formulário mais limpo.

### 2. **Backend (app.py)**
- Ajustada a rota `/adicionar_produto` para:
  - Ao criar novo produto: exigir valores válidos para quantidade e preco_compra
  - Ao editar produto: permitir que quantidade e preco_compra sejam vazios (defaults para 0)
  
- Isso garante que edições de dados não causem registros indesejados no estoque

## Fluxo de Uso

### Para EDITAR um produto:
1. Clique no botão ✏️ (editar) do produto
2. O formulário se preenche com os dados atuais
3. Edite apenas os campos que deseja (nome, preço venda, categoria, descrição, foto)
4. **Deixe "Quantidade" em branco** (ou preencha com quantidade E preço de compra para adicionar estoque)
5. Clique em "Salvar Produto"

### Para ADICIONAR ESTOQUE:
1. Clique em ✏️ (editar) do produto
2. O formulário se preenche com os dados atuais
3. Preencha o campo "Quantidade" E "Preço de Compra"
4. Clique em "Salvar Produto"

### Para CRIAR um novo produto:
1. Preencha todos os campos obrigatórios (nome, categoria, preço venda, preço compra, quantidade)
2. Clique em "Salvar Produto"

## Arquivos Modificados
- `app.py` - Linhas ~425-430: Lógica de criação com defaults para quantidade e preco_compra
- `templates/produtos.html` - Validação de formulário + lógica de UI para edição
