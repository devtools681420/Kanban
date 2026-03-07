import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from streamlit_cookies_controller import CookieController
from datetime import datetime, timedelta
import hashlib, random, string, requests, json, time, uuid
from streamlit.components.v1 import html as _html

st.set_page_config(
    page_title="PMJA Scrum",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── COOKIE SESSION ────────────────────────────────────────────────────
_cc = CookieController()
COOKIE_NAME          = "pmja_session"
SESSION_EXPIRY_HOURS = 8

def save_session(user_id, username, expiry_hours=SESSION_EXPIRY_HOURS):
    expiry = datetime.now() + timedelta(hours=expiry_hours)
    _cc.set(COOKIE_NAME, {
        "user_id":  str(user_id),
        "username": username,
        "expiry":   expiry.isoformat(),
        "token":    str(uuid.uuid4()),
    })
    st.session_state.logged_in   = True
    st.session_state.session_uid = str(user_id)
    st.session_state.session_usr = username
    st.session_state.session_exp = expiry

def load_session():
    # 1) session_state ainda ativo (mesma aba sem recarregar)
    if st.session_state.get("logged_in") and st.session_state.get("session_exp"):
        if datetime.now() < st.session_state.session_exp:
            return {
                "user_id":  st.session_state.session_uid,
                "username": st.session_state.session_usr,
            }
        clear_session()
        return None
    # 2) cookie do browser (após F5 ou nova aba no mesmo browser)
    try:
        c = _cc.get(COOKIE_NAME)
        if not c:
            return None
        expiry = datetime.fromisoformat(c["expiry"])
        if datetime.now() >= expiry:
            _cc.remove(COOKIE_NAME)
            return None
        st.session_state.logged_in   = True
        st.session_state.session_uid = c["user_id"]
        st.session_state.session_usr = c["username"]
        st.session_state.session_exp = expiry
        return {"user_id": c["user_id"], "username": c["username"]}
    except Exception:
        return None

def clear_session():
    try:
        _cc.remove(COOKIE_NAME)
    except Exception:
        pass
    st.session_state.update(
        logged_in=False, user_data=None,
        session_uid=None, session_usr=None, session_exp=None,
    )

# ── EMAIL ─────────────────────────────────────────────────────────────
try:
    BREVO_API_KEY      = st.secrets.get("BREVO_API_KEY", "")
    EMAIL_FROM_NAME    = st.secrets.get("EMAIL_FROM_NAME", "PMJA Sistema")
    EMAIL_FROM_ADDRESS = st.secrets.get("EMAIL_FROM_ADDRESS", "")
    if not BREVO_API_KEY or not EMAIL_FROM_ADDRESS:
        st.error("Configure as credenciais do Brevo"); st.stop()
except Exception as exc:
    st.error(f"Erro: {exc}"); st.stop()

# ── DB ────────────────────────────────────────────────────────────────
conn = st.connection("gsheets", type=GSheetsConnection)

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def generate_code():
    return "".join(random.choices(string.digits, k=6))

def send_verification_email(email, code, username):
    try:
        body = (
            "<div style='font-family:sans-serif;max-width:420px;margin:0 auto;"
            "padding:32px;background:#f8fafc;border-radius:12px;'>"
            "<p style='font-size:10px;color:#94a3b8;margin:0 0 4px;'>PMJA · Scrum</p>"
            "<h2 style='color:#0f172a;font-size:18px;font-weight:600;margin:0 0 18px;'>"
            "Código de verificação</h2>"
            "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:10px;"
            "padding:22px;text-align:center;margin-bottom:18px;'>"
            f"<span style='font-size:30px;font-weight:700;letter-spacing:.22em;color:#0075be;'>{code}</span>"
            "</div>"
            "<p style='color:#94a3b8;font-size:12px;margin:0;'>Válido por 5 minutos.</p></div>"
        )
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "content-type": "application/json"},
            data=json.dumps({
                "sender": {"name": EMAIL_FROM_NAME, "email": EMAIL_FROM_ADDRESS},
                "to": [{"email": email}],
                "subject": "Código – PMJA",
                "htmlContent": body,
            }),
        )
        return r.status_code in [200, 201]
    except Exception:
        return False

COLS = [
    "id", "username", "email", "password", "full_name", "created_at",
    "last_login", "email_verified", "verification_code", "code_expiry", "image_url",
]

def init_users_sheet():
    try:
        df = conn.read(worksheet="users_auth", ttl=0)
        if not df.empty:
            for c in COLS:
                if c not in df.columns:
                    df[c] = ""
            df["email_verified"] = (
                df["email_verified"].astype(str).str.strip().str.lower().replace("nan", "false")
            )
            for c in ["verification_code", "code_expiry", "image_url"]:
                df[c] = df[c].fillna("").astype(str).replace("nan", "").replace("None", "")
        return df
    except Exception:
        return pd.DataFrame(columns=COLS)

def get_user_by_id(uid):
    df  = init_users_sheet()
    uid = str(uid)
    u   = df[df["id"].astype(str) == uid]
    return u.iloc[0].to_dict() if not u.empty else None

def login_user(username, password):
    df = init_users_sheet()
    if df.empty:
        return False, "Nenhum usuário cadastrado"
    u = df[df["username"] == username]
    if u.empty:
        return False, "Usuário não encontrado"
    if u.iloc[0]["password"] != hash_password(password):
        return False, "Senha incorreta"
    if str(u.iloc[0]["email_verified"]).strip().lower() not in ["true", "1", "yes", "1.0"]:
        return False, "EMAIL_NOT_VERIFIED"
    return True, u.iloc[0].to_dict()

def register_user(username, email, password, full_name, image_url=""):
    df = init_users_sheet()
    if not df.empty and username in df["username"].values:
        return False, "Usuário já existe", None
    if not df.empty and email in df["email"].values:
        return False, "Email já cadastrado", None
    code   = generate_code()
    expiry = (datetime.now() + timedelta(minutes=5)).strftime("%d/%m/%Y %H:%M:%S")
    new_id = 1 if df.empty else int(df["id"].max()) + 1
    row = {
        "id": str(new_id), "username": str(username), "email": str(email),
        "password": hash_password(password), "full_name": str(full_name),
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "last_login": "",
        "email_verified": "false", "verification_code": str(code),
        "code_expiry": str(expiry),
        "image_url": str(image_url).strip() if image_url else "",
    }
    conn.update(
        worksheet="users_auth",
        data=pd.concat([df, pd.DataFrame([row])], ignore_index=True),
    )
    send_verification_email(email, code, username)
    return True, "Cadastro realizado!", code

def resend_verification_code(username):
    df = init_users_sheet()
    u  = df[df["username"] == username]
    if u.empty:
        return False, "Usuário não encontrado"
    code   = generate_code()
    expiry = (datetime.now() + timedelta(minutes=5)).strftime("%d/%m/%Y %H:%M:%S")
    email  = u.iloc[0]["email"]
    df2    = conn.read(worksheet="users_auth", ttl=0)
    idx    = df2[df2["username"] == username].index[0]
    df2.loc[idx, "verification_code"] = str(code)
    df2.loc[idx, "code_expiry"]       = str(expiry)
    conn.update(worksheet="users_auth", data=df2)
    send_verification_email(email, code, username)
    return True, "Código reenviado!"

def verify_email_code(username, code):
    df = init_users_sheet()
    u  = df[df["username"] == username]
    if u.empty:
        return False, "Usuário não encontrado"
    stored = str(u.iloc[0]["verification_code"]).strip().replace(" ", "").replace(".0", "")
    inp    = str(code).strip().replace(" ", "")
    if stored != inp and stored.lstrip("0") != inp.lstrip("0"):
        return False, "Código incorreto"
    df2 = conn.read(worksheet="users_auth", ttl=0)
    idx = df2[df2["username"] == username].index[0]
    df2.loc[idx, "email_verified"]    = "true"
    df2.loc[idx, "verification_code"] = ""
    df2.loc[idx, "code_expiry"]       = ""
    conn.update(worksheet="users_auth", data=df2)
    time.sleep(1)
    return True, "Email verificado!"

# ── session state ─────────────────────────────────────────────────────
for k, v in [
    ("logged_in",     False),
    ("user_data",     None),
    ("page",          "login"),
    ("temp_username", None),
    ("msg",           ""),
    ("msg_type",      ""),
    ("_action",       None),
    ("session_uid",   None),
    ("session_usr",   None),
    ("session_exp",   None),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── verifica sessão ativa ─────────────────────────────────────────────
if not st.session_state.logged_in:
    s = load_session()
    if s:
        ud = get_user_by_id(s["user_id"])
        if ud:
            st.session_state.logged_in = True
            st.session_state.user_data = ud
            st.switch_page("pages/atual.py")

# ── process pending action ────────────────────────────────────────────
action = st.session_state.pop("_action", None) if "_action" in st.session_state else None

if action == "go_register":
    st.session_state.page = "register"
    st.session_state.msg  = ""
elif action == "go_login":
    st.session_state.page = "login"
    st.session_state.msg  = ""
elif action == "resend":
    ok, msg = resend_verification_code(st.session_state.temp_username)
    st.session_state.msg      = msg
    st.session_state.msg_type = "success" if ok else "error"
elif action == "logout":
    clear_session()
    st.session_state.page = "login"
elif action == "extend":
    user = st.session_state.user_data
    if user:
        save_session(user["id"], user["username"], SESSION_EXPIRY_HOURS)
        st.session_state.msg      = "Sessão estendida por 2 horas"
        st.session_state.msg_type = "success"

# ── CSS ───────────────────────────────────────────────────────────────
_CSS = """\
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap');

#MainMenu,footer,header,.stDeployButton,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"]{display:none!important}

*,*::before,*::after{box-sizing:border-box!important;font-family:'DM Sans',-apple-system,sans-serif!important}
html,body{height:100%;margin:0;padding:0}

section[data-testid="stMain"],
section[data-testid="stMain"]>div{
  min-height:100vh!important;padding:0!important;background:#f0f4f8!important
}
div.block-container{
  min-height:100vh!important;max-width:100%!important;padding:32px 12px!important;
  margin:0!important;background:#f0f4f8!important;
  display:flex!important;align-items:center!important;justify-content:center!important
}
div.block-container>div[data-testid="stVerticalBlock"]{
  width:100%!important;display:flex!important;flex-direction:column!important;
  align-items:center!important;justify-content:center!important;gap:0!important
}
div[data-testid="stHorizontalBlock"]{
  width:100%!important;display:flex!important;
  justify-content:center!important;align-items:flex-start!important;gap:0!important
}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:first-child,
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:last-child{
  flex:1 1 0!important;min-width:0!important;padding:0!important
}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:nth-child(2){
  flex:0 0 min(460px,calc(100vw - 24px))!important;
  width:min(460px,calc(100vw - 24px))!important;
  max-width:min(460px,calc(100vw - 24px))!important;
  min-width:0!important;padding:0!important;background:#ffffff!important;
  border-radius:20px!important;overflow:hidden!important;
  box-shadow:0 0 0 1px rgba(0,0,0,.06),0 4px 6px rgba(0,0,0,.05),0 24px 60px rgba(0,0,0,.14)!important
}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:nth-child(2)>div[data-testid="stVerticalBlock"]{gap:0!important}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:nth-child(2)>div[data-testid="stVerticalBlock"]>div{padding-left:28px!important;padding-right:28px!important}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:nth-child(2)>div[data-testid="stVerticalBlock"]>div:first-child{padding-left:0!important;padding-right:0!important}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:nth-child(2)>div[data-testid="stVerticalBlock"]>div:nth-child(2){padding-top:22px!important;padding-bottom:4px!important}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:nth-child(2)>div[data-testid="stVerticalBlock"]>div:last-child{padding-bottom:28px!important}
div[data-testid="stForm"]{border:none!important;padding:0!important;background:transparent!important;border-radius:0!important}
div[data-testid="stForm"]>div>div[data-testid="stVerticalBlock"]{gap:0!important;padding:0!important}
div[data-testid="stTextInput"] label{display:block!important;margin-bottom:6px!important}
div[data-testid="stTextInput"] label p{font-size:12px!important;font-weight:600!important;color:#64748b!important;letter-spacing:.025em!important;margin:0!important;line-height:1!important}
div[data-testid="stTextInput"]>div>div>input{height:44px!important;background:#f8fafc!important;border:1.5px solid #e2e8f0!important;border-radius:12px!important;padding:0 14px!important;font-size:14px!important;color:#0f172a!important;width:100%!important;outline:none!important;box-shadow:none!important;transition:border-color .15s,box-shadow .15s,background .15s!important}
div[data-testid="stTextInput"]>div>div>input::placeholder{color:#c8d3dd!important;font-size:13.5px!important}
div[data-testid="stTextInput"]>div>div>input:focus{border-color:#0075be!important;background:#ffffff!important;box-shadow:0 0 0 3px rgba(0,117,190,.13)!important}
div[data-testid="InputInstructions"]{display:none!important}
div[data-testid="stTextInput"]{margin-top:14px!important;margin-bottom:0!important}
div[data-testid="stFormSubmitButton"]{margin-top:22px!important}
div[data-testid="stButton"]>button,div[data-testid="stFormSubmitButton"]>button{font-size:14px!important;font-weight:600!important;height:46px!important;border-radius:12px!important;width:100%!important;cursor:pointer!important;transition:all .18s!important;letter-spacing:.01em!important}
div[data-testid="stFormSubmitButton"]>button[kind="primary"],div[data-testid="stButton"]>button[kind="primary"]{background:#0075be!important;color:#ffffff!important;border:none!important;box-shadow:0 1px 2px rgba(0,0,0,.08),0 4px 14px rgba(0,117,190,.28)!important}
div[data-testid="stFormSubmitButton"]>button[kind="primary"]:hover,div[data-testid="stButton"]>button[kind="primary"]:hover{background:#005fa0!important;box-shadow:0 2px 4px rgba(0,0,0,.1),0 8px 20px rgba(0,117,190,.36)!important;transform:translateY(-1px)!important}
div[data-testid="stFormSubmitButton"]>button[kind="secondary"],div[data-testid="stButton"]>button[kind="secondary"]{background:#ffffff!important;color:#64748b!important;border:1.5px solid #e2e8f0!important;box-shadow:none!important}
div[data-testid="stFormSubmitButton"]>button[kind="secondary"]:hover,div[data-testid="stButton"]>button[kind="secondary"]:hover{background:#f8fafc!important;border-color:#0075be!important;color:#0075be!important}
div[data-testid="stForm"]>div>div[data-testid="stVerticalBlock"]>div[data-testid="stHorizontalBlock"]{gap:12px!important;width:100%!important;margin-top:14px!important;padding:0!important;justify-content:flex-start!important;align-items:flex-start!important}
div[data-testid="stForm"]>div>div[data-testid="stVerticalBlock"]>div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]{flex:1 1 0!important;min-width:0!important;padding:0!important}
div[data-testid="stForm"]>div>div[data-testid="stVerticalBlock"]>div[data-testid="stHorizontalBlock"] div[data-testid="stTextInput"]{margin-top:0!important}
div[data-testid="stButton"]{margin:0!important}
div[data-testid="stAlert"]{font-size:13px!important;border-radius:12px!important;margin-bottom:16px!important;margin-top:4px!important}
</style>
"""
_html(_CSS, height=0)

# ── page state ────────────────────────────────────────────────────────
pg   = "dashboard" if st.session_state.logged_in else st.session_state.page
user = st.session_state.user_data

PHOTOS = {
    "login":     "https://drudu6g9smo13.cloudfront.net/wp-content/uploads/2023/08/UHE-Jaguara.jpg",
    "register":  "https://s2.glbimg.com/e844-OclDbLw-PWuboUy_wtbhiQ=/512x320/smart/e.glbimg.com/og/ed/f/original/2021/12/01/hidreletrica_jaguara_-_rifaina_sp_SGhwNiF.jpg",
    "verify":    "https://upload.wikimedia.org/wikipedia/commons/9/99/Usina_Hidrel%C3%A9trica_de_Jaguara_%28Rifaina-SP_%284478616135%29.jpg",
    "dashboard": "https://drudu6g9smo13.cloudfront.net/wp-content/uploads/2023/08/UHE-Jaguara.jpg",
}
TITLES = {
    "login":     ("Bem-vindo de volta", "ACESSAR CONTA"),
    "register":  ("Criar conta",        "DADOS DE CADASTRO"),
    "verify":    ("Verificar email",    "CÓDIGO DE VERIFICAÇÃO"),
    "dashboard": (
        ("Olá, " + user["full_name"].split()[0]) if user else "Painel",
        "PAINEL",
    ),
}
banner_title, form_label = TITLES.get(pg, TITLES["login"])
photo = PHOTOS.get(pg, PHOTOS["login"])


def flush():
    m, t = st.session_state.msg, st.session_state.msg_type
    st.session_state.msg      = ""
    st.session_state.msg_type = ""
    if not m:
        return
    {"error": st.error, "success": st.success}.get(t, st.info)(m)

def sp(px):
    st.markdown(f"<div style='height:{px}px;line-height:0;font-size:0;'></div>", unsafe_allow_html=True)

def divider():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:12px;margin:18px 0 14px;'>"
        "<div style='flex:1;height:1px;background:#e2e8f0;'></div>"
        "<span style='font-size:11.5px;color:#94a3b8;font-weight:500;'>ou</span>"
        "<div style='flex:1;height:1px;background:#e2e8f0;'></div></div>",
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════
# LAYOUT
# ═════════════════════════════════════════════════════════════════════
_, card, _ = st.columns([1, 1.4, 1])

with card:

    # BANNER
    st.markdown(
        f"<div style='position:relative;width:100%;height:196px;overflow:hidden;'>"
        f"<img src='{photo}' style='position:absolute;inset:0;width:100%;height:100%;"
        "object-fit:cover;object-position:center 40%;filter:brightness(.55) saturate(1.2);'>"
        "<div style='position:absolute;inset:0;background:linear-gradient(180deg,transparent 20%,rgba(15,23,42,.72) 100%);'></div>"
        "<div style='position:absolute;bottom:0;left:0;right:0;padding:0 28px 22px;'>"
        "<div style='font-size:9px;font-weight:700;letter-spacing:.22em;color:rgba(255,255,255,.42);text-transform:uppercase;margin-bottom:7px;line-height:1;'>PMJA · UHE Jaguara · Rifaina SP</div>"
        f"<div style='font-size:23px;font-weight:700;color:#fff;line-height:1.2;letter-spacing:-.2px;text-shadow:0 2px 10px rgba(0,0,0,.3);'>{banner_title}</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    # SECTION LABEL
    st.markdown(
        f"<div style='font-size:9px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:#0075be;line-height:1;'>{form_label}</div>",
        unsafe_allow_html=True,
    )

    # ══════════════════════════════════════════════════════════════
    # LOGIN
    # ══════════════════════════════════════════════════════════════
    if pg == "login":
        flush()
        sp(14)

        with st.form("f_login", border=False):
            st.text_input("Usuário", placeholder="nome_usuario", key="li_u")
            st.text_input("Senha", placeholder="••••••••", type="password", key="li_p")
            sub = st.form_submit_button("Entrar →", type="primary", use_container_width=True)

        if sub:
            u = st.session_state.li_u.strip()
            p = st.session_state.li_p
            if not (u and p):
                st.session_state.msg      = "Preencha todos os campos"
                st.session_state.msg_type = "error"
                st.rerun()
            else:
                ok, result = login_user(u, p)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.user_data = result
                    save_session(result["id"], u, SESSION_EXPIRY_HOURS)
                    st.switch_page("pages/atual.py")
                elif result == "EMAIL_NOT_VERIFIED":
                    resend_verification_code(u)
                    st.session_state.temp_username = u
                    st.session_state.page          = "verify"
                    st.session_state.msg           = "📧 Código reenviado para seu email"
                    st.session_state.msg_type      = "info"
                    st.rerun()
                else:
                    st.session_state.msg      = result
                    st.session_state.msg_type = "error"
                    st.rerun()

        divider()

        if st.button("Criar nova conta →", use_container_width=True, key="go_reg"):
            st.session_state.page = "register"
            st.session_state.msg  = ""
            st.rerun()
        sp(4)

    # ══════════════════════════════════════════════════════════════
    # REGISTER
    # ══════════════════════════════════════════════════════════════
    elif pg == "register":
        flush()
        sp(14)

        with st.form("f_register", border=False):
            st.text_input("Nome completo", placeholder="Seu nome completo", key="rg_n")
            st.text_input("Email", placeholder="seu@email.com", key="rg_e")
            c1, c2 = st.columns(2)
            with c1: st.text_input("Usuário", placeholder="nome_usuario", key="rg_u")
            with c2: st.text_input("URL da foto", placeholder="https://...", key="rg_i")
            c3, c4 = st.columns(2)
            with c3: st.text_input("Senha", placeholder="Mín. 6 caracteres", type="password", key="rg_p")
            with c4: st.text_input("Confirmar senha", placeholder="Repita a senha", type="password", key="rg_p2")
            sub = st.form_submit_button("Cadastrar →", type="primary", use_container_width=True)

        if sub:
            fn  = st.session_state.rg_n.strip()
            em  = st.session_state.rg_e.strip()
            us  = st.session_state.rg_u.strip()
            img = st.session_state.rg_i.strip()
            pw  = st.session_state.rg_p
            pw2 = st.session_state.rg_p2
            if not all([fn, em, us, pw, pw2]):
                st.session_state.msg      = "Preencha todos os campos"
                st.session_state.msg_type = "error"
            elif len(pw) < 6:
                st.session_state.msg      = "Senha mínimo 6 caracteres"
                st.session_state.msg_type = "error"
            elif pw != pw2:
                st.session_state.msg      = "Senhas não coincidem"
                st.session_state.msg_type = "error"
            else:
                ok, msg, _ = register_user(us, em, pw, fn, img)
                if ok:
                    st.session_state.temp_username = us
                    st.session_state.page          = "verify"
                    st.session_state.msg           = "Conta criada! Verifique seu email."
                    st.session_state.msg_type      = "success"
                else:
                    st.session_state.msg      = msg
                    st.session_state.msg_type = "error"
            st.rerun()

        divider()

        if st.button("← Já tenho conta", use_container_width=True, key="go_log"):
            st.session_state.page = "login"
            st.session_state.msg  = ""
            st.rerun()
        sp(4)

    # ══════════════════════════════════════════════════════════════
    # VERIFY
    # ══════════════════════════════════════════════════════════════
    elif pg == "verify":
        flush()
        sp(14)
        st.markdown(
            "<div style='display:flex;align-items:center;gap:10px;"
            "background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;"
            "padding:12px 15px;margin-bottom:16px;'>"
            "<span style='font-size:18px;flex-shrink:0;'>📧</span>"
            "<span style='font-size:13px;color:#1d4ed8;font-weight:500;line-height:1.4;'>"
            "Código enviado por email. Válido por 5 minutos.</span></div>",
            unsafe_allow_html=True,
        )

        with st.form("f_verify", border=False):
            st.text_input("Código de 6 dígitos", placeholder="000000", max_chars=6, key="vf_c")
            sp(8)
            cv1, cv2 = st.columns(2)
            with cv1: confirm = st.form_submit_button("Confirmar", type="primary", use_container_width=True)
            with cv2: go_back = st.form_submit_button("← Voltar", use_container_width=True)

        if confirm:
            ok, msg = verify_email_code(st.session_state.temp_username, st.session_state.vf_c)
            st.session_state.page      = "login" if ok else "verify"
            st.session_state.msg       = msg
            st.session_state.msg_type  = "success" if ok else "error"
            st.rerun()

        if go_back:
            st.session_state.page = "login"
            st.rerun()

        sp(8)
        if st.button("Reenviar código por email", use_container_width=True, key="resend"):
            ok, msg = resend_verification_code(st.session_state.temp_username)
            st.session_state.msg      = msg
            st.session_state.msg_type = "success" if ok else "error"
            st.rerun()
        sp(4)

    # ══════════════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════════════
    else:
        flush()
        uname   = user["full_name"] if user else ""
        uemail  = user["email"]     if user else ""
        initial = uname[0].upper()  if uname else "?"
        sp(14)

        st.markdown(
            "<div style='display:flex;align-items:center;gap:14px;"
            "background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:14px;padding:14px 16px;margin-bottom:18px;'>"
            "<div style='width:44px;height:44px;border-radius:50%;flex-shrink:0;"
            "background:linear-gradient(135deg,#0075be,#38bdf8);display:flex;align-items:center;justify-content:center;"
            f"color:#fff;font-weight:700;font-size:18px;box-shadow:0 2px 8px rgba(0,117,190,.3);'>{initial}</div>"
            f"<div><div style='font-size:14px;font-weight:600;color:#0f172a;'>{uname}</div>"
            f"<div style='font-size:12px;color:#64748b;margin-top:3px;'>{uemail}</div></div></div>",
            unsafe_allow_html=True,
        )

        if st.button("📋 Acessar Tarefas →", type="primary", use_container_width=True, key="tasks"):
            st.switch_page("pages/atual.py")

        sp(10)
        d1, d2 = st.columns(2)
        with d1:
            if st.button("🔄 Estender Sessão", use_container_width=True, key="extend"):
                save_session(user["id"], user["username"], SESSION_EXPIRY_HOURS)
                st.session_state.msg      = "Sessão estendida por 2 horas"
                st.session_state.msg_type = "success"
                st.rerun()
        with d2:
            if st.button("Sair", use_container_width=True, key="logout"):
                clear_session()
                st.session_state.page = "login"
                st.rerun()
        sp(4)

    # FOOTER
    st.markdown(
        "<div style='text-align:center;padding-top:12px;font-size:10px;color:#94a3b8;letter-spacing:.1em;'>"
        "PMJA · UHE Jaguara · Rifaina SP</div>",
        unsafe_allow_html=True,
    )