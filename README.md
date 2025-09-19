# Simulador REFIS – Anápolis

Aplicação **Streamlit** para simular negociações de débitos municipais (REFIS) com regras específicas por **natureza do débito, perfil (PF/MEI ou PJ), opção de pagamento (à vista/parcelado), entrada opcional e limites de parcelas.**
Permite **agrupar débitos** por natureza, consolidar o melhor cenário **“OU” (à vista vs. parcelado) para itens e grupos**, e exportar **PDF/HTM**L e **CSV**.

## ✨ Principais recursos

- **Cadastro** rápido **de débitos** (descrição, exercício, natureza, valores).

- **Cálculo automático**:

    - Base de desconto por natureza.

    - Percentuais de desconto por faixas de parcelas.

    - Parcela mínima por perfil.

    - Tratamento de **entrada** (valor fixo ou percentual).

- **Agrupamento de débitos** por Empresa + Natureza com simulação unificada.

- **Consolidação “OU”**: compara **à vista vs. parcelado** e destaca a melhor opção:

    - Para **itens** (mesmo débito).

    - Para **grupos** (mesmo conjunto de taxas/anos).

- Exportação:

    - **PDF** (via WeasyPrint, opcional) e **HTML**.

    - **CSV** de itens e grupos.

    - **Salvar/Carregar** todo o estado em **JSON**.

- Interface refinada (CSS) e métricas em cards.

## 📦 Requisitos

- **Python 3.10**

- Sistema operacional: Windows, macOS ou Linux

- Navegador moderno (Chrome/Edge/Firefox)

- (Opcional) **WeasyPrint** para geração de PDF

### Dependências principais

- ``streamlit``

- ``pandas``

- ``weasyprint`` *(opcional: apenas se quiser PDF nativo; HTML sempre disponível)*

## 🚀 Instalação

**1. Clone** este repositório ou copie os arquivos do projeto.

**2.** (Recomendado) Crie um **ambiente virtual**:

```bash
python -m venv .venv
#Windows
.venv\Scripts\activate
#macOS/Linux
source .venv/bin/activate
```

**3. Instale as dependências:**

 ```bash
pip install -U pip
pip install streamlit pandas
# PDF opcional:
pip install weasyprint 
```
> ⚠️ No Windows, o WeasyPrint pode requerer componentes extras (GTK/cairo/pango).
Se não quiser lidar com isso agora, **use apenas o HTML** e imprima para PDF pelo navegador.

## ▶️ Como executar

Na raiz do projeto, rode:

```bash
streamlit run simulador_REFIS.py
```

O navegador abrirá automaticamente (ou acesse o link exibido no terminal).

## 🧭 Uso rápido

**1. Sidebar:**

   - Defina **Empresa** e **Perfil** (PF/MEI ou PJ).

   - Escolha a **Visão**: “Somente esta empresa” ou “Todas as empresas”.

   - Botão 🧹 **Limpar tudo** zera o estado (itens e grupos).

**2. Aba *Simulador*:**

   - Preencha **descrição, exercício, natureza** e **opção** (à vista/parcelado).

   - Informe **principal, encargos** e **correção**.

   - Se parcelado, opcionalmente adicione **entrada** (valor R$ ou %).

   - Clique **Atualizar prévia** para ver o cálculo ou ➕ **Adicionar débito** para salvar.

   - Gerencie itens (excluir selecionados / limpar).

**3. Aba *Grupos*:**

   - Selecione a **natureza** e marque os **itens** a negociar juntos (mesma empresa/perfil).

   - Defina **opção** e **parcelas** do grupo (e **entrada** opcional).

   - Salve o grupo (💾 **Salvar grupo de negociação**).

**4. Aba *Consolidações (OU)*:**

   - **Itens:** mostra, por débito, qual opção tem **menor Valor REFIS**.

   - **Grupos:** compara grupos de **mesmo conjunto de taxas**; exibe o melhor cenário.

**5. Aba *Exportar/Salvar*:**

   - **Gerar PDF/HTML** do relatório para o cliente.

   - **Baixar CSV** de itens e grupos.

   - **Salvar tudo (JSON)** e **Carregar** posteriormente para continuar de onde parou.

## 🧮 Regras de cálculo (resumo)

- **Parcela mínima:**

    - PF/MEI: **R$ 152,50**

    - PJ: **R$ 457,50**

- **Pagamento à vista – valor mínimo:**

    - PF/MEI: **R$ 305,00**

    - PJ: **R$ 915,00**

- **Limites de parcelas:**

    - IPTU/Taxas/Inscrição Municipal: **1 a 60**

    - ISSQN: **1 a 16**

    - Multas (formais, PROCON, etc.): **somente à vista**

- **Descontos (faixas principais):**

    - **IPTU/Taxas/Inscrição Municipal:**

       - À vista: **100%** sobre a **base**

       - 2–6: **95%** | 7–20: **90%** | 21–40: **80%** | 41–60: **70%**

    - **ISSQN:**

       - À vista: **100%**

       - 2–6: 90% | 7–16: **80%**

    - **Multas formais/PROCON/Meio Ambiente/Posturas/Vig. Sanitária/Obras:**

       - **50% à vista | Parcelado não permitido**

- **Base de desconto:**

    - **Multas: Principal + Encargos**

    - Demais naturezas: **somente Encargos**

    - **Correção não** entra na base.

- **Entrada em parcelado:**

    - Pode ser **valor** (R$) ou **percentual** (%).

    - Se houver entrada, a **1ª parcela = entrada** e as **demais** repartem o restante.

    - Verificações de **parcela mínima** para 1ª e demais.

> **Alertas:** o app mostra mensagens claras quando parcela mínima é violada, quando o débito só pode ser à vista, ou quando o nº de parcelas está fora do limite da natureza.

## 🗂️ Estrutura do projeto
```bash
.
├── simulador_REFIS.py     # App Streamlit (cálculos, UI, exportações)
├── README.md              # Este arquivo
└── (opcional) assets/     # Logos, CSS adicional, etc.
```

## 🛠️ Dicas & Atalhos

- **Enter** dentro do formulário de item = **Atualizar prévia**.

- Use **“Começar em branco (apenas esta empresa)”** para reiniciar a simulação de uma empresa sem perder outras.

- Na aba de grupos, mantenha **perfil** e **natureza** homogêneos para evitar erros.

## 🧾 Exportações

- **HTML:** sempre disponível; pode ser impresso em PDF pelo navegador.

- **PDF (WeasyPrint)** requer dependências gráficas (principalmente no Windows). Se falhar, o app exibirá o erro e oferecerá o **HTML**.

- **CSV:** itens e grupos exportados separadamente.

- **JSON:** salva **todo o estado** (itens, grupos, contadores). Ideal para backup e continuidade.

## ❓FAQ

**1) O PDF não está gerando. E agora?**
Use a exportação **HTML** e imprima via navegador (Ctrl+P). Ou instale corretamente as libs do WeasyPrint para seu sistema.

**2) Os números não batem com o portal.**
Confira: **natureza correta, perfil, nº de parcelas e entrada.** Lembre-se de que **correção não participa** da base de desconto.

**3) Posso editar os percentuais e limites?**
Sim. Estão centralizados nas funções:

- ``desconto_percent(...)``

- ``parcela_minima(...)``

- ``limites_parcelas(...)``

- ``base_desconto(...)``

**4) Tenho vários clientes/empresas.**
Use o campo **Empresa** (sidebar) para filtrar/organizar. A visão **“Todas as empresas”** facilita exportações gerais.

## 🧹 Troubleshooting

- **Parcela abaixo do mínimo:** ajuste o número de parcelas ou a entrada.

- **Grupo com perfis mistos:** separe itens PF/MEI de PJ.

- **WeasyPrint no Windows:** se não quiser instalar dependências, use o **HTML**.

## 🧩 Customização

- **Visual:** CSS está no topo do ``simulador_REFIS.py`` (bloco ``st.markdown(<style>...)``).

- **Relatório:** a função ``render_html_report(...)`` gera o **HTML**; edite para personalizar layout/logomarca.

## 📄 Licença

Este projeto é disponibilizado “como está”. Adapte livremente para seu uso interno.
Se for distribuir, inclua os créditos e revise as regras conforme o edital municipal vigente.

## 👤 Créditos

- **Neto Contabilidade** – concepção funcional e regras.

- **Maria Clara** – direção de produto, testes e validação.

- **Streamlit & comunidade Python** – base tecnológica.
