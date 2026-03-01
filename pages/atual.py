import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, timedelta
import streamlit.components.v1 as components
import pickle
from pathlib import Path

# Caminho do arquivo onde a sessão do usuário será salva localmente
SESSION_FILE = Path(".streamlit/session.pkl")


def load_session():
    """
    Carrega a sessão salva em disco.
    Verifica se o arquivo existe e se a sessão ainda não expirou.
    Retorna o dicionário de sessão ou None se inválida/expirada.
    """
    if not SESSION_FILE.exists():
        return None
    try:
        with open(SESSION_FILE, 'rb') as f:
            session = pickle.load(f)
        # Verifica se a sessão ainda está dentro do prazo de validade
        if datetime.now() < session['expiry']:
            return session
        # Remove o arquivo se a sessão já expirou
        SESSION_FILE.unlink()
    except:
        pass
    return None


def clear_session():
    """
    Apaga a sessão salva em disco e limpa o estado da sessão no Streamlit.
    Usado no logout ou quando a sessão é inválida.
    """
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    st.session_state.logged_in = False
    st.session_state.user_data = None


def get_user_by_id(user_id):
    """
    Busca um usuário pelo ID na aba 'users_auth' do Google Sheets.
    Retorna um dicionário com os dados do usuário ou None se não encontrado.
    """
    try:
        conn_auth = st.connection("gsheets", type=GSheetsConnection)
        df = conn_auth.read(worksheet="users_auth", ttl=0)
        user = df[df['id'] == user_id]
        if not user.empty:
            return user.iloc[0].to_dict()
        return None
    except:
        return None


def get_session_time_remaining():
    """
    Calcula quantos minutos restam na sessão atual.
    Retorna 0 se não houver sessão válida.
    """
    if SESSION_FILE.exists():
        try:
            session = load_session()
            if session:
                remaining = session['expiry'] - datetime.now()
                return max(0, int(remaining.total_seconds() / 60))
        except:
            pass
    return 0


# ── VERIFICAÇÃO DE AUTENTICAÇÃO ──────────────────────────────────────────────
# Se o usuário não estiver logado no session_state, tenta recuperar a sessão do disco
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    session = load_session()
    if session:
        # Sessão encontrada: busca os dados atualizados do usuário no Google Sheets
        user_data = get_user_by_id(session['user_id'])
        if user_data:
            st.session_state.logged_in = True
            st.session_state.user_data = user_data
        else:
            # Sessão existente mas usuário não encontrado → sessão inválida
            st.set_page_config(layout="centered", initial_sidebar_state="collapsed")
            st.error("⚠️ Sessão inválida.")
            if st.button("← Login", type="primary"):
                clear_session(); st.switch_page("app.py")
            st.stop()
    else:
        # Nenhuma sessão salva → redireciona para o login
        st.set_page_config(layout="centered", initial_sidebar_state="collapsed")
        st.error("⚠️ Faça login primeiro!")
        if st.button("← Login", type="primary"):
            st.switch_page("app.py")
        st.stop()

# Configuração da página em modo wide (após autenticação confirmada)
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# Conexão com o Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)


def calculate_status(deadline_str):
    """
    Calcula o status de uma tarefa com base na data limite informada.
    Retorna: 'Atrasada', 'Curto Prazo' (≤3 dias) ou 'Em dia'.
    """
    try:
        deadline = datetime.strptime(deadline_str, '%d/%m/%Y').date()
        today = datetime.now().date()
        if deadline < today:
            return "Atrasada"
        elif deadline <= today + timedelta(days=3):
            return "Curto Prazo"
        return "Em dia"
    except:
        return "Em dia"


def recalculate_all_status():
    """
    Relê todas as tarefas da planilha e recalcula o status de cada uma
    com base na data limite atual. Salva os dados atualizados.
    """
    try:
        df = conn.read(worksheet="tasks", ttl=0)
        if not df.empty and 'deadline' in df.columns:
            df['status'] = df['deadline'].apply(calculate_status)
            conn.update(worksheet="tasks", data=df)
            return True
    except Exception as e:
        st.error(f"Erro: {e}")
    return False


@st.cache_data(ttl=600)
def load_sheets_data():
    """
    Carrega os dados das abas 'users', 'config' e 'tasks' do Google Sheets.
    Usa cache de 10 minutos (ttl=600) para evitar requisições desnecessárias.
    Retorna: DataFrames dos usuários, configurações e tarefas, além de listas auxiliares.
    """
    try:
        # Lê users_auth como fonte de responsáveis em vez de users
        users_df  = conn.read(worksheet="users_auth", ttl=600)
        config_df = conn.read(worksheet="config", usecols=list(range(2)), ttl=600)
        tasks_df  = conn.read(worksheet="tasks",  ttl=600)

        # Recalcula status das tarefas ao carregar
        if not tasks_df.empty and 'deadline' in tasks_df.columns:
            tasks_df['status'] = tasks_df['deadline'].apply(calculate_status)

        # Usa full_name de users_auth como lista de responsáveis
        users_list      = users_df['full_name'].tolist() if not users_df.empty  else []
        priorities_list = config_df['priority'].tolist() if not config_df.empty else []
        return users_df, config_df, tasks_df, users_list, priorities_list
    except Exception as e:
        st.error(f"Erro: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), [], []


# Carrega os dados das planilhas
users_df, config_df, tasks_df, users_list, priorities_list = load_sheets_data()


def update_sheet(task_data, action='update'):
    """
    Atualiza a planilha de tarefas com base na ação solicitada:
    - 'create': adiciona nova tarefa com ID auto-incrementado
    - 'update': atualiza os campos de uma tarefa existente pelo ID
    - 'delete': remove a tarefa pelo ID
    Limpa o cache após qualquer alteração.
    """
    try:
        current_df = conn.read(worksheet="tasks", ttl=0)
        if action == 'create':
            # Define o próximo ID disponível
            new_id = 1 if current_df.empty else int(current_df['id'].max()) + 1
            task_data['id'] = new_id
            updated_df = pd.concat([current_df, pd.DataFrame([task_data])], ignore_index=True)
        elif action == 'update':
            idx = current_df[current_df['id'] == task_data['id']].index[0]
            for k, v in task_data.items():
                current_df.loc[idx, k] = v
            updated_df = current_df
        elif action == 'delete':
            updated_df = current_df[current_df['id'] != task_data['id']]

        conn.update(worksheet="tasks", data=updated_df)
        load_sheets_data.clear()  # Invalida o cache para forçar releitura
        return True
    except Exception as e:
        st.error(f"Erro: {e}")
        return False


# ── CSS CUSTOMIZADO ──────────────────────────────────────────────────────────
# Oculta elementos padrão do Streamlit e posiciona botões invisíveis no DOM
# (os botões ficam fora da tela mas ainda clicáveis via JavaScript)
# CSS para esconder o menu, o rodapé e o cabeçalho
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif !important; }

/* Oculta todos os elementos nativos do Streamlit — inclusive botão de deploy em produção */
#MainMenu,
footer,
header,
.stDeployButton,
[data-testid="stToolbar"],
[data-testid="stToolbarActions"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
button[kind="header"],
button[title="Deploy"],
button[aria-label="Deploy"],
.stAppDeployButton,
section[data-testid="stSidebar"],
div[class*="deployButton"],
div[class*="toolbar"],
iframe[title="streamlit_analytics"] { display: none !important; }

/* Remove qualquer margem/padding gerado pelo header oculto */
[data-testid="stAppViewContainer"] > section:first-child { padding-top: 0 !important; }

.block-container { padding: 0 !important; max-width: 100% !important; }
.element-container { margin: 0 !important; padding: 0 !important; }
.stMarkdown { margin: 0 !important; }

/* Botões ocultos visualmente mas presentes no DOM e clicáveis via JS */
.stButton > button {
    position: fixed !important;
    left: -9999px !important;
    top: 0 !important;
    width: 1px !important;
    height: 1px !important;
    opacity: 0 !important;
    pointer-events: all !important;
    font-size: 1px !important;
    color: transparent !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    overflow: hidden !important;
    white-space: nowrap !important;
}
[data-testid="stHorizontalBlock"] {
    gap: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    height: 0 !important;
    overflow: visible !important;
    position: relative !important;
}

/* O iframe ocupa toda a tela */
iframe {
    position: fixed !important;
    top: 0 !important; left: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    height: 100dvh !important;
    border: none !important;
    z-index: 9999 !important;
}

.main, [data-testid="stAppViewContainer"] { background: #fff !important; }

/* Diálogos nativos do Streamlit ficam acima do iframe */
div[data-testid="stDialog"] {
    z-index: 99999 !important;
    position: fixed !important;
}
/* Restaura estilos normais dos botões dentro de diálogos */
div[data-testid="stDialog"] .stButton > button {
    font-size: 13px !important;
    color: #374151 !important;
    background: #fff !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06) !important;
    padding: 6px 14px !important;
    height: 34px !important;
    width: auto !important;
    min-height: 34px !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    pointer-events: all !important;
    position: relative !important;
    left: auto !important;
    top: auto !important;
    opacity: 1 !important;
    font-size: 13px !important;
    color: #374151 !important;
}
div[data-testid="stDialog"] .stButton > button[kind="primary"] {
    background: #1d4ed8 !important;
    border-color: #1d4ed8 !important;
    color: white !important;
}
div[data-testid="stDialog"] [data-testid="stHorizontalBlock"] {
    height: auto !important;
    overflow: visible !important;
    gap: 8px !important;
}
</style>
""", unsafe_allow_html=True)


# ── ESTADO DA SESSÃO ─────────────────────────────────────────────────────────
# Inicializa variáveis de estado caso ainda não existam
for key, val in [
    ('dialog_action', None),    # Ação do diálogo atual: 'create', 'edit', 'delete', 'edit_user' ou None
    ('dialog_task_id', None),   # ID da tarefa sendo editada/excluída
    ('last_button_clicked', None),
    ('show_menu', False)        # Controla a exibição do menu de opções
]:
    if key not in st.session_state:
        st.session_state[key] = val


# ── LEITURA DE AÇÕES VIA QUERY PARAMS ────────────────────────────────────────
# O iframe HTML se comunica com o Streamlit alterando os query params da URL pai.
# Aqui lemos essas ações e atualizamos o session_state conforme necessário.
qp = st.query_params
iframe_action      = qp.get("action", "")
iframe_task_id     = qp.get("task_id", "")
iframe_task_status = qp.get("task_status", "")

if iframe_action == "create" and st.session_state.dialog_action != "create":
    # Abre o diálogo de criação de tarefa
    st.session_state.dialog_action = "create"
    st.session_state.dialog_task_id = None
    st.session_state.show_menu = False
    st.query_params.clear()
    st.rerun()

elif iframe_action == "menu":
    # Alterna a exibição do menu de opções
    st.session_state.show_menu = not st.session_state.show_menu
    st.query_params.clear()
    st.rerun()

elif iframe_action == "recalc":
    # Recalcula o status de todas as tarefas e limpa o cache
    if recalculate_all_status():
        load_sheets_data.clear()
        st.session_state.show_menu = False
    st.query_params.clear()
    st.rerun()

elif iframe_action == "edit_user":
    # Abre o diálogo de edição do perfil do usuário logado
    st.session_state.dialog_action = "edit_user"
    st.session_state.show_menu = False
    st.query_params.clear()
    st.rerun()

elif iframe_action == "logout":
    # Faz logout: limpa a sessão e redireciona para a tela de login
    clear_session()
    st.query_params.clear()
    st.switch_page("app.py")

elif iframe_action == "edit" and iframe_task_id:
    # Abre o diálogo de edição para a tarefa informada
    st.session_state.dialog_action = "edit"
    st.session_state.dialog_task_id = int(iframe_task_id)
    st.query_params.clear()
    st.rerun()

elif iframe_action == "delete" and iframe_task_id:
    # Abre o diálogo de exclusão para a tarefa informada
    st.session_state.dialog_action = "delete"
    st.session_state.dialog_task_id = int(iframe_task_id)
    st.query_params.clear()
    st.rerun()

elif iframe_action == "move" and iframe_task_id and iframe_task_status:
    # Move a tarefa para outra coluna do kanban (altera o campo 'my_task')
    try:
        df2 = conn.read(worksheet="tasks", ttl=0)
        tid = int(iframe_task_id)
        mask = df2['id'] == tid
        if mask.any():
            df2.loc[df2[mask].index[0], 'my_task'] = iframe_task_status
            conn.update(worksheet="tasks", data=df2)
            load_sheets_data.clear()
    except Exception as e:
        st.error(f"Erro: {e}")
    st.query_params.clear()
    st.rerun()


# ── DADOS DO USUÁRIO LOGADO ───────────────────────────────────────────────────
user           = st.session_state.user_data      # Dicionário com dados do usuário autenticado
image_url      = user.get('image_url', '')        # URL da foto de perfil
time_remaining = get_session_time_remaining()     # Minutos restantes na sessão


# ── ORDENAÇÃO DAS TAREFAS ─────────────────────────────────────────────────────
# Ordena as tarefas pela data de criação (mais recentes primeiro)
filtered_df = tasks_df.copy()
if not filtered_df.empty:
    filtered_df['_c'] = pd.to_datetime(filtered_df['created'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    filtered_df = filtered_df.sort_values('_c', ascending=False).drop(columns=['_c'])


# ── LISTAS PARA FILTROS ───────────────────────────────────────────────────────
# Prioridades únicas extraídas das tarefas existentes
all_priorities = (
    sorted(set(tasks_df['priority'].dropna().tolist()))
    if not tasks_df.empty and 'priority' in tasks_df.columns
    else priorities_list
)
# Status possíveis (fixos)
all_statuses = ['Atrasada', 'Curto Prazo', 'Em dia']


# ── DIÁLOGO DE GERENCIAMENTO DE TAREFAS ──────────────────────────────────────
@st.dialog("Criar / Editar Tarefa")
def manage_task_dialog():
    """
    Exibe o diálogo modal para criar, editar ou excluir uma tarefa.
    A ação e o ID da tarefa são lidos do session_state.
    """
    action  = st.session_state.dialog_action
    task_id = st.session_state.dialog_task_id

    if action not in ['create', 'edit', 'delete', 'edit_user']:
        st.session_state.dialog_action = None
        st.rerun()
        return

    if action == 'create':
        # ── Formulário de criação de nova tarefa ──
        with st.form("task_form", clear_on_submit=True):
            title       = st.text_input("Título *")
            description = st.text_area("Descrição")
            c1, c2 = st.columns(2)
            with c1:
                # Selectbox de responsável agora usa full_name de users_auth
                responsible = st.selectbox("Responsável *", users_list)
            with c2:
                priority = st.selectbox("Prioridade", priorities_list)
            deadline = st.date_input("Data Limite", format="DD/MM/YYYY")

            if st.form_submit_button("Criar", type="primary"):
                if title and responsible:
                    # Busca os dados completos do responsável em users_auth por full_name
                    ur = users_df[users_df['full_name'] == responsible].iloc[0]
                    td = {
                        'title':              title,
                        'description':        description,
                        'responsible':        responsible,
                        'priority':           priority,
                        'deadline':           deadline.strftime('%d/%m/%Y'),
                        'status':             calculate_status(deadline.strftime('%d/%m/%Y')),
                        # Pega imagem e email do responsável direto de users_auth
                        'url_responsible':    ur.get('image_url', ''),
                        'email_responsible':  ur.get('email', ''),
                        'created':            datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                        # Dados do user_auth logado que criou a tarefa
                        'user':               user.get('username', ''),
                        'user_id':            user.get('id', ''),
                        'user_full_name':     user.get('full_name', ''),
                        'user_email':         user.get('email', ''),
                        'user_image':         user.get('image_url', ''),
                        'my_task':            'A Fazer'
                    }
                    if update_sheet(td, 'create'):
                        st.success("Criada!")
                        st.session_state.dialog_action = None
                        st.rerun()
                else:
                    st.error("Preencha os campos obrigatórios")

    elif action == 'edit':
        # ── Formulário de edição de tarefa existente ──
        task = tasks_df[tasks_df['id'] == task_id].iloc[0]
        with st.form("edit_form"):
            title       = st.text_input("Título *",  value=task['title'])
            description = st.text_area("Descrição",  value=task['description'])
            c1, c2 = st.columns(2)
            with c1:
                # users_list agora contém full_name de users_auth
                ri = users_list.index(task['responsible']) if task['responsible'] in users_list else 0
                responsible = st.selectbox("Responsável *", users_list, index=ri)
            with c2:
                pi = priorities_list.index(task['priority']) if task['priority'] in priorities_list else 0
                priority = st.selectbox("Prioridade", priorities_list, index=pi)
            deadline = st.date_input(
                "Data Limite",
                value=datetime.strptime(task['deadline'], '%d/%m/%Y').date(),
                format="DD/MM/YYYY"
            )
            b1, b2 = st.columns(2)
            with b1: save   = st.form_submit_button("Salvar",   type="primary", use_container_width=True)
            with b2: cancel = st.form_submit_button("Cancelar", use_container_width=True)

            if cancel:
                st.session_state.dialog_action = None
                st.rerun()
            if save and title and responsible:
                # Busca responsável por full_name na tabela users_auth
                ur = users_df[users_df['full_name'] == responsible].iloc[0]
                td = {
                    'id':                 task_id,
                    'title':              title,
                    'description':        description,
                    'responsible':        responsible,
                    'priority':           priority,
                    'deadline':           deadline.strftime('%d/%m/%Y'),
                    'status':             calculate_status(deadline.strftime('%d/%m/%Y')),
                    # Imagem e email do responsável vindos de users_auth
                    'url_responsible':    ur.get('image_url', ''),
                    'email_responsible':  ur.get('email', '')
                }
                if update_sheet(td, 'update'):
                    st.success("Atualizado!")
                    st.session_state.dialog_action = None
                    st.rerun()

    elif action == 'edit_user':
        # ── Formulário de edição do perfil do usuário logado ──
        st.markdown("##### Editar Perfil")
        with st.form("edit_user_form"):
            full_name = st.text_input("Nome completo", value=user.get('full_name', ''))
            email     = st.text_input("E-mail", value=user.get('email', ''), disabled=True,
                                      help="O e-mail não pode ser alterado.")
            image_url_input = st.text_input("URL da foto de perfil", value=user.get('image_url', ''))

            # Prévia da foto se URL preenchida
            preview_url = image_url_input.strip() if image_url_input else user.get('image_url', '')
            if preview_url:
                st.image(preview_url, width=60, caption="Prévia")

            new_password    = st.text_input("Nova senha (deixe vazio para não alterar)",
                                            type="password", placeholder="••••••••")
            confirm_password = st.text_input("Confirmar nova senha",
                                             type="password", placeholder="••••••••")

            b1, b2 = st.columns(2)
            with b1: save   = st.form_submit_button("Salvar", type="primary", use_container_width=True)
            with b2: cancel = st.form_submit_button("Cancelar", use_container_width=True)

            if cancel:
                st.session_state.dialog_action = None
                st.rerun()

            if save:
                if new_password and new_password != confirm_password:
                    st.error("As senhas não coincidem.")
                elif not full_name.strip():
                    st.error("O nome completo é obrigatório.")
                else:
                    try:
                        import hashlib
                        df_auth = conn.read(worksheet="users_auth", ttl=0)
                        uid = user.get('id')
                        mask = df_auth['id'] == uid
                        if mask.any():
                            idx = df_auth[mask].index[0]
                            df_auth.loc[idx, 'full_name'] = full_name.strip()
                            df_auth.loc[idx, 'image_url'] = image_url_input.strip()
                            if new_password:
                                # Hash SHA-256 da nova senha
                                hashed = hashlib.sha256(new_password.encode()).hexdigest()
                                df_auth.loc[idx, 'password'] = hashed
                            conn.update(worksheet="users_auth", data=df_auth)
                            # Atualiza o session_state com os novos dados
                            st.session_state.user_data['full_name'] = full_name.strip()
                            st.session_state.user_data['image_url'] = image_url_input.strip()
                            load_sheets_data.clear()
                            st.success("Perfil atualizado!")
                            st.session_state.dialog_action = None
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

    elif action == 'delete':
        # ── Confirmação de exclusão ──
        task = tasks_df[tasks_df['id'] == task_id].iloc[0]
        st.warning(f"Excluir **{task['title']}**?")
        st.caption("Esta ação não pode ser desfeita.")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("✓ Sim, excluir", type="primary", use_container_width=True, key="k_del_yes"):
                if update_sheet({'id': task_id}, 'delete'):
                    st.success("Excluída!")
                    st.session_state.dialog_action = None
                    st.rerun()
        with b2:
            if st.button("✗ Cancelar", use_container_width=True, key="k_del_no"):
                st.session_state.dialog_action = None
                st.rerun()


# Exibe o diálogo se houver uma ação pendente
if st.session_state.dialog_action in ['create', 'edit', 'delete', 'edit_user']:
    manage_task_dialog()


# ── FUNÇÕES AUXILIARES DO BOARD HTML ─────────────────────────────────────────

def pbadge(priority):
    """
    Gera o HTML do badge de prioridade com cor correspondente.
    Alta/Crítica → vermelho | Média/Normal → amarelo | demais → verde
    """
    p = str(priority).lower()
    if 'alta' in p or 'crítica' in p or 'critica' in p or 'high' in p:
        return f'<span class="badge b-high">{priority}</span>'
    elif 'média' in p or 'media' in p or 'medium' in p or 'normal' in p:
        return f'<span class="badge b-med">{priority}</span>'
    return f'<span class="badge b-low">{priority}</span>'


def sbadge(status):
    """
    Gera o HTML do badge de status com cor correspondente.
    Atrasada → vermelho | Curto Prazo → laranja | Em dia → verde
    """
    if   status == 'Atrasada':    return f'<span class="badge b-late">{status}</span>'
    elif status == 'Curto Prazo': return f'<span class="badge b-soon">{status}</span>'
    return f'<span class="badge b-ok">{status}</span>'


def create_board(df, user_data, img_url, time_rem, show_menu, priorities, statuses, responsibles):
    """
    Gera o HTML completo do board kanban com:
    - Barra superior (topbar) com filtros, botões e avatar do usuário
    - Quatro colunas de tarefas (A Fazer, Em Andamento, Paralizada, Finalizada)
    - Drag & drop entre colunas
    - Filtros client-side por texto, prioridade e status
    - Comunicação com Streamlit via query params na URL pai
    """

    # Converte DataFrame em lista de dicionários para facilitar iteração
    tasks = df.to_dict('records') if isinstance(df, pd.DataFrame) else df

    # Definição das colunas do kanban com cores de destaque
    cols_map = {
        'A Fazer':      ('#1d4ed8', '#dbeafe', '#eff6ff'),   # azul
        'Em Andamento': ('#059669', '#d1fae5', '#f0fdf4'),   # verde
        'Paralizada':   ('#b45309', '#fef3c7', '#fffbeb'),   # amarelo/laranja
        'Finalizada':   ('#dc2626', '#fee2e2', '#fef2f2'),   # vermelho
    }

    # Agrupa tarefas por coluna
    by_st  = {k: [t for t in tasks if t.get('my_task') == k] for k in cols_map}
    total  = len(tasks)
    counts = {k: len(v) for k, v in by_st.items()}
    # Percentual de cada coluna em relação ao total (usado na barra de progresso)
    pcts   = {k: (counts[k]/total*100) if total else 0 for k in counts}

    # Avatar do usuário logado: foto ou iniciais
    if img_url and img_url.strip():
        av = f'<img src="{img_url}" style="width:22px;height:22px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(0,0,0,0.1);">'
    else:
        av = f'<div style="width:22px;height:22px;border-radius:50%;background:#1d4ed8;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff;">{user_data["full_name"][0].upper()}</div>'

    # Indicador de tempo restante de sessão (exibido ao lado do nome do usuário)
    timer = f'<span style="font-size:9px;color:#9ca3af;margin-left:3px;">⏱{time_rem}m</span>' if time_rem else ''

    # Menu de opções (recalcular status / sair) — exibido apenas quando show_menu=True
    menu_html = f'''<div class="tb-menu" id="tbMenu">
        <div class="menu-item" onclick="sendAction(\'recalc\')">↺ Recalcular status</div>
        <div class="menu-item" onclick="sendAction(\'edit_user\')">✎ Editar perfil</div>
        <div class="menu-item menu-danger" onclick="sendAction(\'logout\')">Sair</div>
    </div>''' if show_menu else ''

    # Opções do select de prioridade para o filtro da topbar
    prio_opts = '<option value="">Todas prioridades</option>'
    for p in priorities:
        prio_opts += f'<option value="{p}">{p}</option>'

    # Opções do select de status para o filtro da topbar
    status_opts = '<option value="">Todos status</option>'
    for s in statuses:
        status_opts += f'<option value="{s}">{s}</option>'

    # Opções do select de responsável para o filtro da topbar
    resp_opts = '<option value="">Todos responsáveis</option>'
    for r in responsibles:
        resp_opts += f'<option value="{str(r).lower()}">{r}</option>'

    def render(task_list):
        """
        Gera o HTML de todos os cards de uma coluna do kanban.
        Cada card exibe título, descrição, badges, data limite e responsável.
        """
        h = ""
        for t in task_list:
            tid  = int(t['id'])
            desc = str(t.get('description','') or '').strip()
            # Exibe bloco de descrição apenas se houver conteúdo
            dh   = f'<div class="card-desc">{desc}</div>' if desc else ''

            # Avatar do responsável: foto ou iniciais
            img  = str(t.get('url_responsible','') or '').strip()
            name = str(t.get('responsible','') or '')
            fn   = name.split()[0] if name else ''  # Primeiro nome
            if img:
                ava = f'<img src="{img}" alt="" onerror="this.style.display=\'none\'">'
            else:
                ini = ''.join([w[0].upper() for w in name.split()[:2]]) or '?'
                ava = f'<div class="av-fb">{ini}</div>'

            # Valores usados nos atributos data-* para filtragem client-side
            prio_val  = str(t.get('priority', '') or '')
            stat_val  = str(t.get('status', '') or '')
            title_val = str(t.get('title', '') or '')
            desc_val  = str(t.get('description', '') or '')

            h += f'''<div class="card" draggable="true"
  data-id="{tid}"
  data-status="{t["my_task"]}"
  data-priority="{prio_val}"
  data-stat="{stat_val}"
  data-title="{title_val.lower()}"
  data-desc="{desc_val.lower()}"
  data-responsible="{name.lower()}">
  <div class="card-acts">
    <button class="act" onclick="event.stopPropagation();sendAction('edit',{tid})" title="Editar">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4z"/></svg>
    </button>
    <button class="act act-d" onclick="event.stopPropagation();sendAction('delete',{tid})" title="Excluir">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6M9 6V4h6v2"/></svg>
    </button>
  </div>
  <div class="card-title">{t["title"]}</div>
  {dh}
  <div class="card-badges">{sbadge(t["status"])} {pbadge(t["priority"])}</div>
  <div class="card-foot">
    <span class="card-date">📅 {t["deadline"]}</span>
    <div class="card-user">{ava}<span>{fn}</span></div>
  </div>
</div>'''
        return h

    # ── Gera HTML de cada coluna ──
    cols_html = ""
    for key, (accent, zone_bg, hdr_bg) in cols_map.items():
        cols_html += f'''<div class="col" data-col="{key}">
    <div class="col-hdr" style="border-top:3px solid {accent};background:{hdr_bg};">
      <div class="col-hdr-row">
        <span class="col-title" style="color:{accent};">{key.upper()}</span>
        <span class="col-cnt" id="cnt-{key.replace(' ','-')}" style="background:{accent};">{counts[key]}</span>
      </div>
      <div class="prog-track"><div class="prog-fill" id="prog-{key.replace(' ','-')}" style="width:{pcts[key]:.1f}%;background:{accent};"></div></div>
    </div>
    <div class="drop-zone" data-status="{key}" style="background:{zone_bg};">{render(by_st[key])}</div>
  </div>'''

    # ── HTML completo do board ──
    return f'''<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* Reset e fonte base */
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Inter',sans-serif;}}
::-webkit-scrollbar{{width:4px;}}
::-webkit-scrollbar-thumb{{background:rgba(0,0,0,0.14);border-radius:10px;}}
html,body{{height:100%;overflow:hidden;background:#fff;}}
@media (max-width:600px){{
  html,body{{overflow:auto;height:auto;min-height:100%;}}
}}

/* ── TOPBAR ── */
.topbar{{
  display:flex;align-items:center;height:44px;
  background:#fff;border-bottom:1px solid rgba(0,0,0,0.07);
  padding:0 14px;gap:8px;
  position:fixed;top:0;left:0;right:0;z-index:100;
}}
.tb-logo{{height:26px;display:block;flex-shrink:0;}}
.tb-sep{{color:#e5e7eb;font-size:14px;flex-shrink:0;}}
.tb-title{{font-size:12px;font-weight:600;color:#111827;flex-shrink:0;}}
.tb-sub{{font-size:10px;color:#9ca3af;flex-shrink:0;}}

/* Grupo de filtros na topbar — desktop */
.tb-filters{{
  display:flex;align-items:center;gap:6px;
  margin-left:auto;
  flex-shrink:1;
  min-width:0;
}}

/* Campo de busca por texto */
.tb-search{{
  position:relative;display:flex;align-items:center;flex-shrink:1;
}}
.tb-search svg{{
  position:absolute;left:7px;pointer-events:none;
  color:#9ca3af;flex-shrink:0;
}}
.tb-search input{{
  height:26px;
  padding:0 8px 0 26px;
  border:1px solid rgba(0,0,0,0.1);
  border-radius:6px;
  background:#f9fafb;
  font-size:11px;
  color:#374151;
  outline:none;
  width:140px;
  transition:border-color 0.15s,width 0.2s,background 0.15s;
}}
.tb-search input:focus{{
  border-color:#1d4ed8;
  background:#fff;
  width:180px;
}}
.tb-search input::placeholder{{color:#9ca3af;}}

/* Select de filtro */
.tb-select{{
  height:26px;
  padding:0 22px 0 8px;
  border:1px solid rgba(0,0,0,0.1);
  border-radius:6px;
  background:#f9fafb url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E") no-repeat right 6px center;
  -webkit-appearance:none;appearance:none;
  font-size:11px;color:#374151;
  outline:none;cursor:pointer;
  transition:border-color 0.15s,background-color 0.15s;
  max-width:120px;
  flex-shrink:1;
}}
.tb-select:focus{{border-color:#1d4ed8;background-color:#fff;}}
.tb-select.active,.tb-search input.active{{
  border-color:#1d4ed8;background-color:#eff6ff;color:#1d4ed8;font-weight:500;
}}

/* Botão limpar filtros */
.tb-clear{{
  display:none;align-items:center;justify-content:center;
  height:22px;width:22px;border-radius:5px;
  border:1px solid rgba(0,0,0,0.1);
  background:#fff;color:#6b7280;
  cursor:pointer;font-size:11px;font-weight:600;flex-shrink:0;transition:all 0.13s;
}}
.tb-clear:hover{{background:#fef2f2;color:#dc2626;border-color:#fecaca;}}
.tb-clear.visible{{display:flex;}}

/* Botão de filtros mobile (hamburguer de filtros) */
.tb-filter-toggle{{
  display:none;align-items:center;justify-content:center;
  height:26px;width:26px;border-radius:6px;
  border:1px solid rgba(0,0,0,0.1);background:#f9fafb;
  color:#374151;cursor:pointer;flex-shrink:0;transition:all 0.13s;
}}
.tb-filter-toggle:hover{{background:#f3f4f6;}}
.tb-filter-toggle.active{{background:#eff6ff;border-color:#1d4ed8;color:#1d4ed8;}}

/* Gaveta de filtros mobile */
.filter-drawer{{
  display:none;
  position:fixed;top:44px;left:0;right:0;z-index:90;
  background:#fff;border-bottom:1px solid rgba(0,0,0,0.08);
  padding:10px 14px;gap:8px;
  flex-wrap:wrap;align-items:center;
  box-shadow:0 4px 12px rgba(0,0,0,0.06);
}}
.filter-drawer.open{{display:flex;}}
.filter-drawer .tb-search{{flex:1;min-width:140px;}}
.filter-drawer .tb-search input{{width:100%;}}
.filter-drawer .tb-select{{flex:1;min-width:100px;max-width:none;}}
.filter-drawer .tb-clear{{margin-left:auto;}}

/* Botões de ação na topbar */
.tb-actions{{display:flex;align-items:center;gap:4px;flex-shrink:0;margin-left:8px;}}
.tb-btn{{
  display:flex;align-items:center;gap:4px;height:26px;padding:0 9px;
  border-radius:6px;border:1px solid rgba(0,0,0,0.1);
  background:#f9fafb;color:#374151;font-size:11px;font-weight:500;
  cursor:pointer;transition:all 0.13s;white-space:nowrap;
}}
.tb-btn:hover{{background:#f3f4f6;border-color:rgba(0,0,0,0.16);}}
.tb-btn.primary{{background:#1d4ed8;border-color:#1d4ed8;color:#fff;}}
.tb-btn.primary:hover{{background:#1e40af;}}

/* Avatar e nome do usuário logado */
.tb-user{{display:flex;align-items:center;gap:5px;margin-left:6px;flex-shrink:0;}}
.tb-uname{{font-size:10px;font-weight:600;color:#374151;}}

/* Menu dropdown de configurações */
.tb-menu{{
  position:fixed;top:46px;right:14px;background:#fff;
  border:1px solid rgba(0,0,0,0.1);border-radius:8px;
  box-shadow:0 8px 24px rgba(0,0,0,0.1);
  z-index:200;min-width:160px;overflow:hidden;
}}
.menu-item{{padding:8px 14px;font-size:11px;color:#374151;cursor:pointer;}}
.menu-item:hover{{background:#f3f4f6;}}
.menu-item.menu-danger{{color:#dc2626;}}
.menu-item.menu-danger:hover{{background:#fef2f2;}}

/* ── BOARD / COLUNAS — desktop ── */
.board{{
  display:flex;gap:8px;
  height:calc(100vh - 44px);
  padding:8px;margin-top:44px;
  overflow-x:auto;
}}
.col{{
  flex:1;min-width:220px;
  display:flex;flex-direction:column;
  border:1px solid rgba(0,0,0,0.07);border-radius:12px;
  overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);
}}
.col-hdr{{padding:10px 12px 8px;flex-shrink:0;border-bottom:1px solid rgba(0,0,0,0.05);}}
.col-hdr-row{{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;}}
.col-title{{font-size:10px;font-weight:700;letter-spacing:0.7px;text-transform:uppercase;}}
.col-cnt{{font-size:10px;font-weight:700;color:#fff;padding:1px 7px;border-radius:20px;transition:all 0.2s;}}
.prog-track{{width:100%;height:2px;background:rgba(0,0,0,0.07);border-radius:10px;overflow:hidden;}}
.prog-fill{{height:100%;border-radius:10px;opacity:0.6;transition:width 0.3s ease;}}

/* Zona de soltar cards */
.drop-zone{{
  flex:1;overflow-y:auto;overflow-x:hidden;
  padding:6px;display:flex;flex-direction:column;gap:6px;min-height:60px;
}}
.drop-zone.over{{filter:brightness(0.94);outline:2px dashed rgba(0,0,0,0.18);border-radius:8px;}}

/* ── CARDS ── */
.card{{
  background:rgba(255,255,255,0.8);border:1px solid rgba(255,255,255,0.95);
  border-radius:8px;padding:9px 10px;cursor:grab;position:relative;
  transition:box-shadow 0.14s,transform 0.14s,background 0.14s,opacity 0.2s;
  flex-shrink:0;backdrop-filter:blur(4px);
}}
.card:hover{{background:#fff;box-shadow:0 3px 12px rgba(0,0,0,0.1);transform:translateY(-1px);}}
.card:hover .card-acts{{opacity:1;pointer-events:all;}}
.card:active{{cursor:grabbing;}}
.card.dragging{{opacity:0.35;}}
.card.hidden{{display:none;}}

/* Botões de ação do card */
.card-acts{{
  position:absolute;top:7px;right:7px;display:flex;gap:3px;
  opacity:0;pointer-events:none;transition:opacity 0.13s;
}}
/* Em touch: botões sempre visíveis */
@media (hover:none) {{
  .card-acts{{opacity:1;pointer-events:all;}}
}}
.act{{
  width:20px;height:20px;border-radius:5px;
  border:1px solid rgba(0,0,0,0.09);background:rgba(255,255,255,0.9);
  color:#6b7280;cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:all 0.12s;
}}
.act:hover{{background:#f3f4f6;color:#111827;}}
.act-d:hover{{background:#fef2f2 !important;color:#dc2626 !important;}}
.card-title{{font-size:12px;font-weight:600;color:#111827;line-height:1.4;margin-bottom:4px;padding-right:48px;word-break:break-word;}}
.card-desc{{font-size:10.5px;color:#6b7280;line-height:1.45;margin-bottom:6px;word-break:break-word;white-space:pre-wrap;}}
.card-badges{{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:7px;}}

/* ── BADGES ── */
.badge{{display:inline-flex;align-items:center;font-size:9px;font-weight:600;padding:2px 6px;border-radius:4px;text-transform:uppercase;letter-spacing:0.3px;border:1px solid transparent;line-height:1.4;}}
.b-high{{background:#fef2f2;color:#dc2626;border-color:#fecaca;}}
.b-med{{background:#fffbeb;color:#d97706;border-color:#fde68a;}}
.b-low{{background:#f0fdf4;color:#16a34a;border-color:#bbf7d0;}}
.b-late{{background:#fef2f2;color:#b91c1c;border-color:#fecaca;}}
.b-soon{{background:#fff7ed;color:#c2410c;border-color:#fed7aa;}}
.b-ok{{background:#f0fdf4;color:#15803d;border-color:#bbf7d0;}}

/* Rodapé do card */
.card-foot{{display:flex;align-items:center;justify-content:space-between;gap:6px;flex-wrap:wrap;}}
.card-date{{font-size:9.5px;color:#9ca3af;}}
.card-user{{display:flex;align-items:center;gap:4px;flex-shrink:0;}}
.card-user img{{width:18px;height:18px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(0,0,0,0.09);}}
.av-fb{{width:18px;height:18px;border-radius:50%;background:#e5e7eb;color:#374151;font-size:8px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;}}
.card-user span{{font-size:10px;color:#6b7280;font-weight:500;}}

/* Toast */
.toast{{position:fixed;bottom:12px;right:12px;background:#111827;color:#f9fafb;padding:7px 14px;border-radius:7px;font-size:11px;font-weight:500;display:none;z-index:9999;}}

/* ── RESPONSIVO — tablet (≤900px): scroll horizontal no board ── */
@media (max-width:900px){{
  .tb-sub{{display:none;}}
  .tb-filters{{display:none;}}
  .tb-filter-toggle{{display:flex;}}
  .tb-uname{{display:none;}}
  .board{{
    gap:6px;padding:6px;
    margin-top:44px;
    overflow-x:auto;
    overflow-y:hidden;
  }}
  .col{{min-width:260px;}}
}}

/* ── RESPONSIVO — mobile (≤600px): board em coluna, topbar compacta ── */
@media (max-width:600px){{
  .topbar{{padding:0 10px;gap:6px;height:48px;}}
  .tb-logo{{height:22px;}}
  .tb-title{{display:none;}}
  .tb-actions .tb-btn:not(.primary) span{{display:none;}}
  .board{{
    flex-direction:column;
    height:auto !important;
    min-height:calc(100vh - 48px);
    overflow:visible !important;
    padding:6px;
    margin-top:48px;
    gap:6px;
  }}
  .col{{
    min-width:0 !important;
    width:100% !important;
    flex:none !important;
    height:auto !important;
    overflow:visible !important;
  }}
  .drop-zone{{
    max-height:260px;
    overflow-y:auto;
  }}
  .filter-drawer{{top:48px;}}
  .tb-menu{{right:10px;}}
  .card{{padding:10px 11px;}}
  .card-title{{font-size:13px;}}
}}
</style></head><body>

<!-- ── TOPBAR ── -->
<div class="topbar">
  <img class="tb-logo" src="https://companieslogo.com/img/orig/AZ2.F-d26946db.png?t=1720244490" alt="AZ">
  <span class="tb-sep">·</span>
  <span class="tb-title">PMJA</span>
  <span class="tb-sep" style="margin:0 2px;">·</span>
  <span class="tb-sub">SCRUM Gestão de Materiais</span>

  <!-- Filtros: busca, prioridade, status e botão limpar -->
  <div class="tb-filters">
    <div class="tb-search">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" id="filterSearch" placeholder="Buscar título ou descrição…" oninput="applyFilters()">
    </div>
    <select class="tb-select" id="filterPriority" onchange="applyFilters()">
      {prio_opts}
    </select>
    <select class="tb-select" id="filterStatus" onchange="applyFilters()">
      {status_opts}
    </select>
    <select class="tb-select" id="filterResponsible" onchange="applyFilters()">
      {resp_opts}
    </select>
    <button class="tb-clear" id="btnClear" title="Limpar filtros" onclick="clearFilters()">✕</button>
  </div>

  <!-- Botão toggle de filtros (visível apenas em mobile/tablet) -->
  <button class="tb-filter-toggle" id="btnFilterToggle" onclick="toggleFilterDrawer()" title="Filtros">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="11" y1="18" x2="13" y2="18"/></svg>
  </button>

  <!-- Botões de ação: nova tarefa e menu de configurações -->
  <div class="tb-actions">
    <button class="tb-btn primary" onclick="sendAction('create')">+ Nova tarefa</button>
    <button class="tb-btn" onclick="sendAction('menu')" style="padding:0 8px;">⚙</button>
  </div>

  <!-- Avatar e nome do usuário logado -->
  <div class="tb-user">{av}<span class="tb-uname">{user_data['username']}{timer}</span></div>
</div>

{menu_html}

<!-- Gaveta de filtros mobile/tablet -->
<div class="filter-drawer" id="filterDrawer">
  <div class="tb-search">
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    <input type="text" id="filterSearchM" placeholder="Buscar…" oninput="applyFilters()">
  </div>
  <select class="tb-select" id="filterPriorityM" onchange="applyFilters()">
    {prio_opts}
  </select>
  <select class="tb-select" id="filterStatusM" onchange="applyFilters()">
    {status_opts}
  </select>
  <select class="tb-select" id="filterResponsibleM" onchange="applyFilters()">
    {resp_opts}
  </select>
  <button class="tb-clear" id="btnClearM" title="Limpar" onclick="clearFilters()">✕</button>
</div>

<div class="toast" id="toast">Salvando…</div>
<div class="board">{cols_html}</div>

<script>
/**
 * sendAction — comunica com o Streamlit via query params na URL pai.
 * O iframe não pode chamar funções Python diretamente, então altera a URL
 * para que o Streamlit leia a ação ao reexecutar.
 *
 * @param {{string}} action     - Ação a executar (create, edit, delete, move, menu, recalc, logout)
 * @param {{number}} taskId     - ID da tarefa (opcional)
 * @param {{string}} taskStatus - Novo status/coluna da tarefa (opcional, usado no move)
 */
function sendAction(action, taskId, taskStatus) {{
  try {{
    const url = new URL(window.parent.location.href);
    url.searchParams.set('action', action);
    if (taskId)     url.searchParams.set('task_id', taskId);
    if (taskStatus) url.searchParams.set('task_status', taskStatus);
    // Atualiza a URL sem recarregar a página
    window.parent.history.replaceState(null, '', url.toString());

    // Dispara popstate para o Streamlit detectar a mudança de URL
    window.parent.dispatchEvent(new PopStateEvent('popstate', {{ state: null }}));

    // Tenta forçar rerun via postMessage (mecanismo alternativo)
    window.parent.postMessage({{type: 'streamlit:setComponentValue', value: action}}, '*');
  }} catch(e) {{
    console.warn('sendAction error:', e);
  }}

  // Fallback final: recarrega a página com os query params após 150ms
  setTimeout(() => {{
    try {{
      const url = new URL(window.parent.location.href);
      if (url.searchParams.get('action') === action) {{
        window.parent.location.href = url.toString();
      }}
    }} catch(e2) {{}}
  }}, 150);
}}

/**
 * move — atalho para mover uma tarefa entre colunas.
 * Exibe o toast de feedback e chama sendAction com a ação 'move'.
 */
function move(id, status) {{
  const t = document.getElementById('toast');
  t.style.display='block'; t.textContent='Salvando…';
  sendAction('move', id, status);
  setTimeout(()=>{{ t.textContent='✓ Salvo!'; setTimeout(()=>t.style.display='none',1000); }},400);
}}

/* ── FILTRAGEM CLIENT-SIDE ── */

/**
 * applyFilters — aplica os filtros de busca, prioridade e status
 * diretamente no DOM sem recarregar a página.
 * Atualiza contadores e barras de progresso de cada coluna.
 */
function getVal(id){{ const el=document.getElementById(id); return el?(el.value||'').toLowerCase().trim():''; }}

function applyFilters() {{
  // Lê filtros do desktop e da gaveta mobile (usa o que tiver valor)
  const search      = getVal('filterSearch')      || getVal('filterSearchM');
  const priority    = getVal('filterPriority')    || getVal('filterPriorityM');
  const status      = getVal('filterStatus')      || getVal('filterStatusM');
  const responsible = getVal('filterResponsible') || getVal('filterResponsibleM');

  const hasFilter = search || priority || status || responsible;

  // Desktop
  document.getElementById('btnClear').classList.toggle('visible', hasFilter);
  document.getElementById('filterSearch').classList.toggle('active', !!search);
  document.getElementById('filterPriority').classList.toggle('active', !!priority);
  document.getElementById('filterStatus').classList.toggle('active', !!status);
  document.getElementById('filterResponsible').classList.toggle('active', !!responsible);
  // Mobile
  document.getElementById('btnClearM').classList.toggle('visible', hasFilter);
  document.getElementById('filterSearchM').classList.toggle('active', !!search);
  document.getElementById('filterPriorityM').classList.toggle('active', !!priority);
  document.getElementById('filterStatusM').classList.toggle('active', !!status);
  document.getElementById('filterResponsibleM').classList.toggle('active', !!responsible);

  // Filtra cada card individualmente
  const cards = document.querySelectorAll('.card');
  cards.forEach(card => {{
    const titleMatch  = !search      || card.dataset.title.includes(search) || card.dataset.desc.includes(search);
    const prioMatch   = !priority    || card.dataset.priority.toLowerCase() === priority;
    const statusMatch = !status      || card.dataset.stat.toLowerCase()     === status;
    const respMatch   = !responsible || card.dataset.responsible.toLowerCase() === responsible;
    card.classList.toggle('hidden', !(titleMatch && prioMatch && statusMatch && respMatch));
  }});

  // Atualiza contadores e barras de progresso por coluna
  const total = cards.length;
  document.querySelectorAll('.col').forEach(col => {{
    const colCards = col.querySelectorAll('.card:not(.hidden)');
    const count    = colCards.length;
    const cntEl    = col.querySelector('.col-cnt');
    const progEl   = col.querySelector('.prog-fill');
    if (cntEl)  cntEl.textContent = count;
    if (progEl) progEl.style.width = total ? (count/total*100).toFixed(1)+'%' : '0%';
  }});
}}

/**
 * clearFilters — limpa todos os campos de filtro e reaplica (mostra tudo).
 */
function clearFilters() {{
  ['filterSearch','filterPriority','filterStatus','filterResponsible',
   'filterSearchM','filterPriorityM','filterStatusM','filterResponsibleM']
    .forEach(id=>{{ const el=document.getElementById(id); if(el) el.value=''; }});
  applyFilters();
}}

/* ── RESIZE DINÂMICO ── */
function fixBoardHeight() {{
  const topbar = document.querySelector('.topbar');
  const drawer = document.getElementById('filterDrawer');
  const board  = document.querySelector('.board');
  if (!board) return;
  const topH   = topbar ? topbar.offsetHeight : 44;
  const drawH  = (drawer && drawer.classList.contains('open')) ? drawer.offsetHeight : 0;
  const offset = topH + drawH;
  if (window.innerWidth <= 600) {{
    board.style.height = 'auto';
    board.style.marginTop = offset + 'px';
  }} else {{
    board.style.height = 'calc(100vh - ' + offset + 'px)';
    board.style.marginTop = offset + 'px';
  }}
}}
window.addEventListener('resize', fixBoardHeight);
document.addEventListener('DOMContentLoaded', fixBoardHeight);

/* ── TOGGLE GAVETA DE FILTROS (MOBILE) ── */
function toggleFilterDrawer() {{
  const drawer = document.getElementById('filterDrawer');
  const btn    = document.getElementById('btnFilterToggle');
  const open   = drawer.classList.toggle('open');
  btn.classList.toggle('active', open);
  fixBoardHeight();
}}

/* ── DRAG & DROP ── */

let draggedCard; // Referência ao card sendo arrastado

// Início do drag: marca o card como "dragging"
document.addEventListener('dragstart', e => {{
  if (e.target.classList.contains('card')) {{
    draggedCard = e.target;
    setTimeout(()=>e.target.classList.add('dragging'),0);
    e.dataTransfer.effectAllowed='move';
  }}
}});

// Fim do drag: remove a marcação visual
document.addEventListener('dragend', e => {{
  if (e.target.classList.contains('card')) e.target.classList.remove('dragging');
}});

// Configura as zonas de drop em cada coluna
document.querySelectorAll('.drop-zone').forEach(zone => {{
  // Permite soltar o card na zona
  zone.addEventListener('dragover',  e=>{{ e.preventDefault(); zone.classList.add('over'); }});
  // Remove destaque quando o card sai da zona
  zone.addEventListener('dragleave', e=>{{ if(!zone.contains(e.relatedTarget)) zone.classList.remove('over'); }});
  // Ao soltar: move o card visualmente e salva no servidor
  zone.addEventListener('drop', e=>{{
    e.preventDefault(); zone.classList.remove('over');
    if (draggedCard) {{
      const id  = draggedCard.getAttribute('data-id');
      const old = draggedCard.getAttribute('data-status');
      const nw  = zone.getAttribute('data-status');
      if (old!==nw) {{  // Só move se a coluna for diferente
        draggedCard.setAttribute('data-status', nw);
        zone.appendChild(draggedCard);
        move(id, nw);  // Persiste a mudança no Google Sheets
      }}
    }}
  }});
}});
</script>
</body></html>'''


# ── RENDERIZAÇÃO DO BOARD ─────────────────────────────────────────────────────
# O CSS do Streamlit injeta position:fixed no iframe para que ele ocupe
# a tela inteira independente da altura real do conteúdo.
# height=800 é um valor mínimo — o CSS sobrescreve para 100vh.
components.html(
    create_board(
        filtered_df, user, image_url, time_remaining,
        st.session_state.show_menu, all_priorities, all_statuses, users_list
    ),
    height=800, scrolling=False
)