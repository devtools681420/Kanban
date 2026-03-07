# 📋 PMJA Scrum — Kanban de Gestão de Materiais

Sistema de gerenciamento de tarefas estilo Kanban para a **PMJA · UHE Jaguara · Rifaina SP**, construído com **Streamlit** e integrado ao **Google Sheets** como banco de dados.

---

## 🗂 Estrutura do Projeto

```
Kanban/
├── app.py                    # Página principal (login, cadastro, verificação de e-mail)
├── pages/
│   ├── atual.py              # Quadro Kanban principal (arraste & solte)
│   └── tasks.py              # Página auxiliar de tarefas
├── requirements.txt          # Dependências Python
├── .streamlit/
│   ├── config.toml           # Configurações do Streamlit (tema, servidor)
│   └── secrets.toml          # Credenciais sensíveis (NÃO versionar)
├── uhe_jaguara.jpg           # Imagem de banner
└── vc_redist.x64.exe         # Redistribuível Visual C++ (necessário no Windows)
```

---

## ⚙️ Pré-requisitos

| Requisito | Versão mínima | Observação |
|---|---|---|
| Python | 3.11+ | Recomendado 3.11 ou 3.12 |
| pip | qualquer | Vem junto com o Python |
| Git | qualquer | Para clonar o repositório |
| Conta Google | — | Para o Google Sheets |
| Conta Brevo | — | Para envio de e-mails transacionais |

> **Windows:** Caso encontre erros com pacotes como `pycparser` ou `cryptography`, instale o **Visual C++ Redistributable** incluído no repositório: `vc_redist.x64.exe`.

---

## 🔧 Instalação Passo a Passo

### 1. Clone o repositório

```bash
git clone <URL_DO_REPOSITORIO>
cd Kanban
```

### 2. Crie e ative o ambiente virtual

```bash
# Criar o ambiente virtual
python -m venv .venv

# Ativar no Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Ativar no Windows (CMD)
.venv\Scripts\activate.bat

# Ativar no Linux/macOS
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

> ⚠️ Em caso de erro no Windows com `cryptography` ou `cffi`, primeiro instale o Visual C++ Redistributable:
> ```
> vc_redist.x64.exe
> ```
> Depois repita o comando pip acima.

---

## 🔑 Configuração dos Secrets

O arquivo `.streamlit/secrets.toml` contém todas as credenciais sensíveis. **Nunca faça commit deste arquivo no Git.**

Crie ou edite o arquivo `.streamlit/secrets.toml` com a seguinte estrutura:

```toml
# ── E-mail via Brevo (Sendinblue) ──────────────────────────────────────
BREVO_API_KEY      = "xkeysib-SEU-API-KEY-AQUI"
EMAIL_FROM_NAME    = "PMJA Kanban Warehouse"
EMAIL_FROM_ADDRESS = "seuemail@dominio.com"

# ── Conexão com Google Sheets ───────────────────────────────────────────
[connections.gsheets]
spreadsheet  = "https://docs.google.com/spreadsheets/d/SEU_ID_DA_PLANILHA/edit"
worksheet    = "users_work"
type         = "service_account"
project_id   = "seu-projeto-gcp"
private_key_id = "seu-private-key-id"
private_key  = """-----BEGIN PRIVATE KEY-----
SUA_CHAVE_PRIVADA_AQUI
-----END PRIVATE KEY-----"""
client_email = "sua-service-account@seu-projeto.iam.gserviceaccount.com"
client_id    = "seu-client-id"
auth_uri     = "https://accounts.google.com/o/oauth2/auth"
token_uri    = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/SUA-SERVICE-ACCOUNT"
universe_domain = "googleapis.com"
```

---

## ☁️ Configuração do Google Sheets

### 1. Criar o projeto no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um novo projeto
3. Ative as APIs:
   - **Google Sheets API**
   - **Google Drive API**

### 2. Criar a Service Account

1. Vá em **IAM e Administrador → Contas de serviço**
2. Clique em **Criar conta de serviço**
3. Gere uma chave JSON (baixe o arquivo)
4. Copie os campos do JSON para o `secrets.toml`

### 3. Criar a Planilha Google Sheets

Crie uma planilha com as seguintes abas (worksheets):

#### Aba `users_auth` — Usuários do sistema
| Coluna | Tipo | Descrição |
|---|---|---|
| id | Número | ID único auto-incrementado |
| username | Texto | Nome de usuário (login) |
| email | Texto | E-mail do usuário |
| password | Texto | Senha em SHA-256 |
| full_name | Texto | Nome completo |
| created_at | Texto | Data de criação `DD/MM/YYYY HH:MM:SS` |
| last_login | Texto | Último login |
| email_verified | Texto | `true` ou `false` |
| verification_code | Texto | Código de 6 dígitos para verificação |
| code_expiry | Texto | Validade do código |
| image_url | Texto | URL da foto de perfil |

#### Aba `tasks` — Tarefas do Kanban
| Coluna | Tipo | Descrição |
|---|---|---|
| id | Número | ID único da tarefa |
| title | Texto | Título da tarefa |
| description | Texto | Descrição |
| responsible_id | Número | ID do responsável (FK → users_auth.id) |
| responsible | Fórmula | Nome do responsável (via PROCX) |
| priority | Texto | Prioridade (ex: Alta, Média, Baixa) |
| deadline | Texto | Prazo `DD/MM/YYYY` |
| status | Fórmula | Calculado: Atrasada / Curto Prazo / Em dia |
| url_responsible | Fórmula | URL da foto do responsável |
| email_responsible | Fórmula | E-mail do responsável |
| created | Texto | Data de criação |
| user | Texto | Nome do criador |
| my_task | Texto | Coluna do Kanban: `A Fazer` / `Em Andamento` / `Paralizada` / `Finalizada` |
| user_id | Número | ID do criador |
| user_full_name | Fórmula | Nome completo do criador |
| user_email | Fórmula | E-mail do criador |
| user_image | Fórmula | Foto do criador |
| updated_at | Texto | Data da última atualização |

#### Aba `config` — Configurações
| Coluna | Descrição |
|---|---|
| priority | Lista de prioridades disponíveis (ex: Alta, Média, Baixa) |

### 4. Compartilhar a planilha com a Service Account

Copie o `client_email` da service account (ex: `xxx@projeto.iam.gserviceaccount.com`) e compartilhe a planilha com ela como **Editor**.

---

## 📧 Configuração do Brevo (e-mails)

1. Crie uma conta gratuita em [brevo.com](https://www.brevo.com)
2. Vá em **Configurações → Chaves de API**
3. Gere uma nova chave e coloque em `BREVO_API_KEY` no `secrets.toml`
4. Configure um remetente verificado e coloque o e-mail em `EMAIL_FROM_ADDRESS`

O sistema envia e-mails automáticos para:
- ✅ **Verificação de cadastro** (código de 6 dígitos, válido por 5 minutos)
- 📋 **Nova tarefa atribuída** (notifica o responsável)
- ✅ **Tarefa finalizada** (notifica o criador da tarefa)

---

## ▶️ Executando o Projeto

Com o ambiente virtual ativado e os secrets configurados:

```bash
streamlit run app.py
```

O app abrirá automaticamente no navegador em:
```
http://localhost:8501
```

### Opções úteis de execução

```bash
# Rodar em porta específica
streamlit run app.py --server.port 8502

# Rodar sem abrir o navegador automaticamente
streamlit run app.py --server.headless true

# Rodar acessível na rede local (outros dispositivos)
streamlit run app.py --server.address 0.0.0.0
```

---

## 🖥️ Funcionalidades

### 🔐 Autenticação
- **Cadastro** com verificação de e-mail (código OTP)
- **Login** com username e senha (SHA-256)
- **Sessão persistente** via cookies do browser (expira em 8 horas)
- **Reenvio de código** de verificação
- **Edição de perfil** (nome, foto, senha)

### 📋 Quadro Kanban
- **4 colunas**: A Fazer → Em Andamento → Paralizada → Finalizada
- **Drag & Drop** de cards entre colunas
- **Filtros** por título, prioridade, status de prazo e responsável
- **Criação e edição** de tarefas via modal
- **Exclusão** de tarefas com confirmação
- **Indicadores de prazo**: Em dia / Curto Prazo / Atrasada
- **Notificação por e-mail** ao criar ou finalizar tarefa
- **Responsivo** (mobile e desktop)

---

## 🎨 Configurações do Streamlit

O arquivo `.streamlit/config.toml` define:

```toml
[theme]
primaryColor = "#0075be"        # Cor principal (azul PMJA)

[client]
showSidebarNavigation = false   # Esconde navegação lateral automática

[browser]
gatherUsageStats = false        # Não envia estatísticas para a Streamlit

[server]
headless = true                 # Ideal para servidores / produção
```

---

## 🐛 Solução de Problemas

| Problema | Solução |
|---|---|
| `ModuleNotFoundError` | Certifique-se de que o `.venv` está ativado e rodou `pip install -r requirements.txt` |
| `Error connecting to Google Sheets` | Verifique o `secrets.toml` e se a Service Account tem acesso à planilha |
| `Configure as credenciais do Brevo` | Preencha `BREVO_API_KEY` e `EMAIL_FROM_ADDRESS` no `secrets.toml` |
| Erro de `cryptography` no Windows | Instale o `vc_redist.x64.exe` incluído no repositório |
| `st.set_page_config()` error | O `pages/atual.py` chama `set_page_config` em condição; garanta que é a primeira chamada Streamlit |
| Sessão expira muito rápido | Ajuste `SESSION_EXPIRY_HOURS` em `app.py` e `pages/atual.py` |
| Dados desatualizados no Kanban | Clique em **⚙ → ↺ Atualizar** na barra superior do Kanban |

---

## 📦 Principais Dependências

| Pacote | Versão | Função |
|---|---|---|
| `streamlit` | 1.54.0 | Framework de UI |
| `st-gsheets-connection` | 0.1.0 | Conexão com Google Sheets |
| `streamlit-cookies-controller` | 0.0.4 | Gerenciamento de sessão via cookies |
| `pandas` | 2.3.3 | Manipulação de dados |
| `google-auth` | 2.48.0 | Autenticação Google |
| `gspread` | 5.12.4 | API do Google Sheets |
| `requests` | 2.32.5 | Chamadas HTTP (Brevo API) |
| `cryptography` | 46.0.5 | Suporte a chaves RSA |
| `pyarrow` | 23.0.1 | Serialização de dados |

---

## 👤 Fluxo de Uso

```
1. Acesse http://localhost:8501
2. Cadastre uma conta → verifique o e-mail com o código OTP
3. Faça login → será redirecionado ao Quadro Kanban
4. Crie tarefas clicando em "+ Nova tarefa"
5. Arraste os cards entre as colunas para atualizar o status
6. Use os filtros na barra superior para encontrar tarefas
7. Ao mover uma tarefa para "Finalizada", o criador recebe um e-mail
```

---

## 🔒 Segurança

- Senhas armazenadas com **SHA-256** (sem texto puro)
- Sessões controladas por **cookies HTTPOnly** com expiração configurável
- Credenciais sensíveis em `secrets.toml` (**nunca versionar**)
- Verificação de e-mail obrigatória para ativação da conta
- Campos de planilha com fórmulas `SEERRO/PROCX` protegidas contra células vazias

---

## 📄 Licença

Uso interno PMJA — UHE Jaguara · Rifaina SP.
