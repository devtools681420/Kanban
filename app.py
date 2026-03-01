# INSTRUÇÕES:
# 1. Substitua o conteúdo completo do seu app.py por este arquivo
# 2. Renomeie o arquivo para app.py
# 3. Execute: streamlit run app.py

# Este arquivo usa uma abordagem simples com arquivo pickle para persistir a sessão

import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, timedelta
import hashlib
import random
import string
import requests
import json
import time
import pickle
from pathlib import Path
import streamlit.components.v1 as components

# ==================== CONFIGURAÇÕES ====================
st.set_page_config(
    page_title="PMJA Scrum",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== SESSÃO COM ARQUIVO ====================
SESSION_FILE = Path(".streamlit/session.pkl")

def save_session(user_id, username, expiry_hours=2):
    """Salva sessão em arquivo"""
    expiry = datetime.now() + timedelta(hours=expiry_hours)
    session = {
        'user_id': user_id,
        'username': username,
        'expiry': expiry
    }
    SESSION_FILE.parent.mkdir(exist_ok=True)
    with open(SESSION_FILE, 'wb') as f:
        pickle.dump(session, f)
    st.session_state.logged_in = True

def load_session():
    """Carrega sessão do arquivo"""
    if not SESSION_FILE.exists():
        return None
    try:
        with open(SESSION_FILE, 'rb') as f:
            session = pickle.load(f)
        if datetime.now() < session['expiry']:
            return session
        SESSION_FILE.unlink()
    except:
        pass
    return None

def clear_session():
    """Limpa sessão"""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    st.session_state.logged_in = False
    st.session_state.user_data = None

# ==================== BREVO ====================
try:
    BREVO_API_KEY = st.secrets.get("BREVO_API_KEY", "")
    EMAIL_FROM_NAME = st.secrets.get("EMAIL_FROM_NAME", "PMJA Sistema")
    EMAIL_FROM_ADDRESS = st.secrets.get("EMAIL_FROM_ADDRESS", "")
    DEV_EMAIL = st.secrets.get("DEV_EMAIL", "")
    
    if not BREVO_API_KEY or not EMAIL_FROM_ADDRESS:
        st.error("⚠️ Configure as credenciais do Brevo")
        st.stop()
except Exception as e:
    st.error(f"❌ Erro: {e}")
    st.stop()

# ==================== CSS FULLSCREEN ====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    * {font-family: 'Inter', sans-serif !important;}
    
    #MainMenu, footer, header, .stDeployButton, [data-testid="stToolbar"], 
    div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}
    
    /* FORÇAR PADDING ZERO - SELETORES ULTRA ESPECÍFICOS */
    section.main > div {padding-top: 0rem !important;}
    section.main > div:has(> div.block-container) {padding-top: 0rem !important;}
    div.block-container {padding-top: 0rem !important; padding-bottom: 1rem !important;}
    section[data-testid="stMain"] {padding-top: 0px !important;}
    section[data-testid="stMain"] > div:first-child {padding-top: 0px !important;}
    
    /* Garantir que elementos filhos também não tenham padding */
    [data-testid="stVerticalBlock"] {gap: 0.5rem !important;}
    [data-testid="stVerticalBlock"]:first-child {padding-top: 0rem !important;}
    
    /* CENTRALIZAR CONTEÚDO */
    .block-container {
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        min-height: 100vh !important;
        max-width: 100% !important;
        margin: 0 auto !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
    }
    
    /* Background gradient */
    section[data-testid="stMain"] {
        background: linear-gradient(135deg, #f5f7fa 0%, #e8eef3 100%) !important;
    }
    
    /* Card styling para formulários */
    [data-testid="stForm"] {
        background: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }
    
    /* Estilizar inputs */
    .stTextInput input {
        border-radius: 8px !important;
        border: 1px solid #e4e4e7 !important;
        padding: 0.75rem !important;
    }
    
    .stTextInput input:focus {
        border-color: #18181b !important;
        box-shadow: 0 0 0 3px rgba(24,24,27,0.1) !important;
    }

    
    h3 {
        font-size: 24px !important;
        margin-bottom: 1rem !important;
        font-weight: 600 !important;
        color: #09090b !important;
    }
    
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        padding: 0.5rem 1rem !important;
        width: 100% !important;
        height: 40px !important;
    }
    
    .stButton > button[kind="primary"] {
        background: #18181b !important;
        color: #fafafa !important;
    }
    
    .user-card {
        background: #ffffff;
        padding: 1.5rem;
        border-radius: 8px;
        border: 1px solid #e4e4e7;
        margin-bottom: 1rem;
    }
    
    .user-avatar {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        background: linear-gradient(135deg, #18181b 0%, #27272a 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        color: #fafafa;
        font-size: 20px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# JavaScript para forçar scroll ao topo
components.html("""
<script>
    window.parent.document.querySelector('section.main').scrollTo(0, 0);
    window.parent.scrollTo(0, 0);
</script>
""", height=0)

# ==================== CONEXÃO ====================
conn = st.connection("gsheets", type=GSheetsConnection)

# ==================== FUNÇÕES ====================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(email, code, username):
    try:
        html = f"""<div style="text-align:center;padding:40px;"><h1>Código: {code}</h1></div>"""
        payload = {
            "sender": {"name": EMAIL_FROM_NAME, "email": EMAIL_FROM_ADDRESS},
            "to": [{"email": email}],
            "subject": "Código de Verificação - PMJA",
            "htmlContent": html
        }
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "content-type": "application/json"},
            data=json.dumps(payload)
        )
        return response.status_code in [200, 201]
    except:
        return False

def init_users_sheet():
    try:
        df = conn.read(worksheet="users_auth", ttl=0)
        if not df.empty:
            required_cols = ['id', 'username', 'email', 'password', 'full_name',
                           'created_at', 'last_login', 'email_verified', 
                           'verification_code', 'code_expiry', 'image_url']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = ''
            
            if 'email_verified' in df.columns:
                df['email_verified'] = df['email_verified'].astype(str).str.strip().str.lower().replace('nan', 'false')
            
            for col in ['verification_code', 'code_expiry', 'image_url']:
                if col in df.columns:
                    df[col] = df[col].fillna('').astype(str).replace('nan', '').replace('None', '')
        return df
    except:
        return pd.DataFrame(columns=['id', 'username', 'email', 'password', 'full_name',
            'created_at', 'last_login', 'email_verified', 'verification_code', 'code_expiry', 'image_url'])

def get_user_by_id(user_id):
    df = init_users_sheet()
    user = df[df['id'] == user_id]
    return user.iloc[0].to_dict() if not user.empty else None

def login_user(username, password):
    df = init_users_sheet()
    if df.empty:
        return False, "❌ Nenhum usuário cadastrado"
    user = df[df['username'] == username]
    if user.empty:
        return False, "❌ Usuário não encontrado"
    if user.iloc[0]['password'] != hash_password(password):
        return False, "❌ Senha incorreta"
    
    email_verified = str(user.iloc[0]['email_verified']).strip().lower()
    
    if email_verified not in ['true', '1', 'yes', '1.0']:
        return False, "📧 Email não verificado"
    
    return True, user.iloc[0].to_dict()

def register_user(username, email, password, full_name, image_url=''):
    df = init_users_sheet()
    if not df.empty and username in df['username'].values:
        return False, "❌ Usuário já existe", None
    if not df.empty and email in df['email'].values:
        return False, "❌ Email já cadastrado", None
    
    code = generate_code()
    expiry = (datetime.now() + timedelta(minutes=5)).strftime('%d/%m/%Y %H:%M:%S')
    new_id = 1 if df.empty else int(df['id'].max()) + 1
    #/atual
    new_user = {
        'id': str(new_id),
        'username': str(username), 
        'email': str(email),
        'password': hash_password(password), 
        'full_name': str(full_name),
        'created_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'last_login': '', 
        'email_verified': 'false',
        'verification_code': str(code),
        'code_expiry': str(expiry), 
        'image_url': str(image_url).strip() if image_url else ''
    }
    
    updated_df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
    
    for col in ['id', 'username', 'email', 'password', 'full_name', 'created_at', 
                'last_login', 'email_verified', 'verification_code', 'code_expiry', 'image_url']:
        if col not in updated_df.columns:
            updated_df[col] = ''
    
    conn.update(worksheet="users_auth", data=updated_df)
    send_verification_email(email, code, username)
    return True, "✓ Cadastro realizado!", code

def verify_email_code(username, code):
    df = init_users_sheet()
    user = df[df['username'] == username]
    
    if user.empty:
        return False, "❌ Usuário não encontrado"
    
    idx = user.index[0]
    
    stored_code = str(user.iloc[0]['verification_code']).strip().replace(' ', '').replace('.0', '')
    input_code = str(code).strip().replace(' ', '')
    
    if stored_code != input_code:
        if stored_code.lstrip('0') == input_code.lstrip('0'):
            pass
        else:
            return False, "❌ Código incorreto"
    
    df = conn.read(worksheet="users_auth", ttl=0)
    
    df['email_verified'] = df['email_verified'].astype(str)
    df['verification_code'] = df['verification_code'].astype(str)
    df['code_expiry'] = df['code_expiry'].astype(str)
    
    user_idx = df[df['username'] == username].index[0]
    
    df.loc[user_idx, 'email_verified'] = 'true'
    df.loc[user_idx, 'verification_code'] = ''
    df.loc[user_idx, 'code_expiry'] = ''
    
    conn.update(worksheet="users_auth", data=df)
    time.sleep(1)
    
    return True, "✓ Email verificado!"

# ==================== SESSION STATE ====================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_data' not in st.session_state:
    st.session_state.user_data = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'
if 'temp_username' not in st.session_state:
    st.session_state.temp_username = None

# ==================== VERIFICAR SESSÃO ====================
if not st.session_state.logged_in:
    session = load_session()
    if session:
        user_data = get_user_by_id(session['user_id'])
        if user_data:
            st.session_state.logged_in = True
            st.session_state.user_data = user_data
            st.switch_page("pages/atual.py")

# ==================== INTERFACE ====================
if not st.session_state.logged_in:
    
    if st.session_state.page == 'verify':
        col_img, col_form = st.columns([2, 1])
        
        with col_img:
            st.markdown("""
            <div style="padding: 0;">
                <img src="https://upload.wikimedia.org/wikipedia/commons/9/99/Usina_Hidrel%C3%A9trica_de_Jaguara_%28Rifaina-SP_%284478616135%29.jpg" 
                     style="width: 100%; height: 100vh; object-fit: cover; border-radius: 0;">
            </div>
            """, unsafe_allow_html=True)
        
        with col_form:
            st.markdown('<div style="padding: 3rem 2rem;">', unsafe_allow_html=True)
            st.markdown("### 📧 Verificar Email")
            st.info("💌 Código enviado por email")
        
            with st.form("verify_form"):
                code = st.text_input("Código (6 dígitos)", max_chars=6)
                col1, col2 = st.columns(2)
                with col1:
                    verify = st.form_submit_button("Verificar", type="primary")
                with col2:
                    cancel = st.form_submit_button("Voltar")
                
                if cancel:
                    st.session_state.page = 'login'
                    st.rerun()
                if verify and code:
                    success, msg = verify_email_code(st.session_state.temp_username, code)
                    if success:
                        st.success(msg)
                        time.sleep(1)
                        st.session_state.page = 'login'
                        st.rerun()
                    else:
                        st.error(msg)
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    elif st.session_state.page == 'register':
        col_img, col_form = st.columns([2, 1])
        
        with col_img:
            st.markdown("""
            <div style="padding: 0;">
                <img src="https://s2.glbimg.com/e844-OclDbLw-PWuboUy_wtbhiQ=/512x320/smart/e.glbimg.com/og/ed/f/original/2021/12/01/hidreletrica_jaguara_-_rifaina_sp_SGhwNiF.jpg" 
                     style="width: 100%; height: 100vh; object-fit: cover; border-radius: 0;">
            </div>
            """, unsafe_allow_html=True)
        
        with col_form:
            st.markdown('<div style="padding: 3rem 2rem;">', unsafe_allow_html=True)
            st.markdown("### 📝 Criar Conta")
        
            with st.form("register_form"):
                full_name = st.text_input("Nome Completo")
                email = st.text_input("Email")
                username = st.text_input("Usuário")
                password = st.text_input("Senha", type="password")
                password_confirm = st.text_input("Confirmar Senha", type="password")
                image_url = st.text_input("URL da Foto (opcional)")
                
                col1, col2 = st.columns(2)
                with col1:
                    register = st.form_submit_button("Cadastrar", type="primary")
                with col2:
                    cancel = st.form_submit_button("Voltar")
                
                if cancel:
                    st.session_state.page = 'login'
                    st.rerun()
                if register:
                    if not all([full_name, email, username, password, password_confirm]):
                        st.error("⚠️ Preencha todos os campos obrigatórios")
                    elif len(password) < 6:
                        st.error("⚠️ Senha mínimo 6 caracteres")
                    elif password != password_confirm:
                        st.error("⚠️ Senhas não coincidem")
                    else:
                        success, msg, code = register_user(username, email, password, full_name, image_url)
                        if success:
                            st.success(msg)
                            st.session_state.page = 'verify'
                            st.session_state.temp_username = username
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg)
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    else:  # Login
        col_img, col_form = st.columns([2, 1])
        
        with col_img:
            st.markdown("""
            <div style="padding: 0;">
                <img src="https://drudu6g9smo13.cloudfront.net/wp-content/uploads/2023/08/UHE-Jaguara.jpg" 
                     style="width: 100%; height: 100vh; object-fit: cover; border-radius: 0;">
            </div>
            """, unsafe_allow_html=True)
        
        with col_form:
            st.markdown('<div style="padding: 3rem 2rem;">', unsafe_allow_html=True)
            st.markdown("### 🔐 Login")
            st.caption("PMJA - Scrum Almoxarifado")
            
            with st.form("login_form"):
                username = st.text_input("Usuário")
                password = st.text_input("Senha", type="password")
                login = st.form_submit_button("Entrar", type="primary")
                
                if login:
                    if username and password:
                        success, result = login_user(username, password)
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.user_data = result
                            save_session(result['id'], username, expiry_hours=2)
                            st.success("✓ Login realizado!")
                            time.sleep(0.5)
                            st.switch_page("pages/atual.py")
                        else:
                            st.error(result)
                    else:
                        st.error("⚠️ Preencha todos os campos")
            
            st.divider()
            if st.button("Criar nova conta"):
                st.session_state.page = 'register'
                st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)

else:  # Dashboard
    st.markdown("### ✓ Bem-vindo!")
    user = st.session_state.user_data
    
    st.markdown(f"""
    <div class="user-card">
        <div style="display:flex;gap:12px;align-items:center;">
            <div class="user-avatar">{user['full_name'][0].upper()}</div>
            <div>
                <div style="font-weight:600;">{user['full_name']}</div>
                <div style="font-size:13px;color:#71717a;">{user['email']}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Estender Sessão"):
            save_session(user['id'], user['username'], 2)
            st.success("✓ Sessão estendida por 2 horas!")
    with col2:
        if st.button("🚪 Sair"):
            clear_session()
            st.session_state.page = 'login'
            st.rerun()
    
    st.divider()
    if st.button("📋 Acessar Tarefas", type="primary"):
        st.switch_page("pages/atual.py")