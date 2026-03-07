import streamlit as st, pandas as pd, hashlib, requests, uuid
from streamlit_gsheets import GSheetsConnection
from streamlit_cookies_controller import CookieController
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components

# ── TIMEZONE BRASÍLIA ──
def now_brt():
    return datetime.now(ZoneInfo("America/Sao_Paulo"))

# ── COOKIE SESSION ────────────────────────────────────────────────────
_cc                  = CookieController()
COOKIE_NAME          = "pmja_session"
SESSION_EXPIRY_HOURS = 2

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
    # 1) session_state ainda ativo
    if st.session_state.get("logged_in") and st.session_state.get("session_exp"):
        if datetime.now() < st.session_state.session_exp:
            return {
                "user_id":  st.session_state.session_uid,
                "username": st.session_state.session_usr,
            }
        clear_session()
        return None
    # 2) cookie do browser
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

def session_mins():
    exp = st.session_state.get("session_exp")
    if exp:
        return max(0, int((exp - datetime.now()).total_seconds() // 60))
    return 0

# ── EMAIL: TAREFA CRIADA ──────────────────────────────────────────────
def send_task_created_email(task_row):
    def clean(v, fb=""):
        s = str(v or "").strip()
        return fb if s in ("", "__", "nan", "None") else s
    try:
        api_key      = st.secrets["BREVO_API_KEY"]
        from_name    = st.secrets.get("EMAIL_FROM_NAME", "PMJA - Kanban")
        from_address = st.secrets["EMAIL_FROM_ADDRESS"]
    except Exception as e:
        st.warning(f"Secrets não configurados: {e}"); return

    to_email     = clean(task_row.get("email_responsible"))
    to_name      = clean(task_row.get("responsible"), "Responsável")
    if not to_email:
        st.warning("Email do responsável não encontrado na tarefa."); return
    author_name  = clean(task_row.get("user_full_name"), clean(task_row.get("user", from_name)))
    author_email = clean(task_row.get("user_email"), from_address)
    title        = clean(task_row.get("title"), "(sem título)")
    desc         = clean(task_row.get("description"))
    deadline     = clean(task_row.get("deadline"))
    priority     = clean(task_row.get("priority"))
    now          = now_brt().strftime("%d/%m/%Y às %H:%M")
    desc_block   = f'<p style="margin:0 0 4px;font-size:12px;color:#6b7280;">📝 {desc}</p>' if desc else ""

    html = f"""<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1d4ed8;padding:24px 28px;"><h2 style="margin:0;color:#fff;font-size:18px;">📋 Nova Tarefa Atribuída</h2></div>
  <div style="padding:24px 28px;background:#fff;">
    <p style="margin:0 0 12px;color:#374151;font-size:14px;">Olá, <strong>{to_name.split()[0]}</strong>!</p>
    <p style="margin:0 0 16px;color:#374151;font-size:14px;">Uma nova tarefa foi criada e atribuída a você por <strong>{author_name}</strong>.</p>
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:16px;margin-bottom:16px;">
      <p style="margin:0 0 8px;font-size:13px;color:#111827;"><strong>📋 {title}</strong></p>
      {desc_block}
      <p style="margin:0 0 4px;font-size:12px;color:#6b7280;">📅 Prazo: {deadline}</p>
      <p style="margin:0;font-size:12px;color:#6b7280;">⚡ Prioridade: {priority}</p>
    </div>
    <p style="margin:0;font-size:12px;color:#9ca3af;">Criado em {now}</p>
  </div>
  <div style="background:#f9fafb;padding:12px 28px;border-top:1px solid #e5e7eb;">
    <p style="margin:0;font-size:11px;color:#9ca3af;">PMJA — Sistema de Gestão de Materiais</p>
  </div>
</div>"""
    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "content-type": "application/json"},
            json={"sender": {"name": from_name, "email": from_address},
                  "to": [{"email": to_email, "name": to_name}],
                  "replyTo": {"email": author_email, "name": author_name},
                  "subject": f"📋 Nova tarefa: {title}", "htmlContent": html},
            timeout=15,
        )
        if r.status_code not in (200, 201): st.warning(f"Brevo erro {r.status_code}: {r.text}")
        else: st.toast("📧 Email enviado ao responsável!", icon="✅")
    except Exception as e:
        st.warning(f"Falha ao enviar email: {e}")


# ── EMAIL: TAREFA FINALIZADA ──────────────────────────────────────────
def send_task_done_email(task_row):
    def clean(v, fb=""):
        s = str(v or "").strip()
        return fb if s in ("", "__", "nan", "None") else s
    try:
        api_key      = st.secrets["BREVO_API_KEY"]
        from_name    = st.secrets.get("EMAIL_FROM_NAME", "PMJA - Kanban")
        from_address = st.secrets["EMAIL_FROM_ADDRESS"]
    except Exception as e:
        st.warning(f"Secrets não configurados: {e}"); return

    to_email   = clean(task_row.get("user_email"))
    to_name    = clean(task_row.get("user_full_name"), clean(task_row.get("user", "Usuário")))
    if not to_email:
        st.warning("Email do autor não encontrado na tarefa."); return
    resp_name  = clean(task_row.get("responsible"), from_name)
    resp_email = clean(task_row.get("email_responsible"), from_address)
    title      = clean(task_row.get("title"), "(sem título)")
    deadline   = clean(task_row.get("deadline"))
    priority   = clean(task_row.get("priority"))
    now        = now_brt().strftime("%d/%m/%Y às %H:%M")

    html = f"""<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#059669;padding:24px 28px;"><h2 style="margin:0;color:#fff;font-size:18px;">✅ Tarefa Finalizada</h2></div>
  <div style="padding:24px 28px;background:#fff;">
    <p style="margin:0 0 12px;color:#374151;font-size:14px;">Olá, <strong>{to_name}</strong>!</p>
    <p style="margin:0 0 16px;color:#374151;font-size:14px;">A tarefa que você criou foi marcada como <strong style="color:#059669;">Finalizada</strong>.</p>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin-bottom:16px;">
      <p style="margin:0 0 8px;font-size:13px;color:#111827;"><strong>📋 {title}</strong></p>
      <p style="margin:0 0 4px;font-size:12px;color:#6b7280;">📅 Prazo: {deadline}</p>
      <p style="margin:0 0 4px;font-size:12px;color:#6b7280;">⚡ Prioridade: {priority}</p>
      <p style="margin:0;font-size:12px;color:#6b7280;">👤 Responsável: {resp_name}</p>
    </div>
    <p style="margin:0;font-size:12px;color:#9ca3af;">Finalizado em {now}</p>
  </div>
  <div style="background:#f9fafb;padding:12px 28px;border-top:1px solid #e5e7eb;">
    <p style="margin:0;font-size:11px;color:#9ca3af;">PMJA — Sistema de Gestão de Materiais</p>
  </div>
</div>"""
    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "content-type": "application/json"},
            json={"sender": {"name": from_name, "email": from_address},
                  "to": [{"email": to_email, "name": to_name}],
                  "replyTo": {"email": resp_email, "name": resp_name},
                  "subject": f"✅ Tarefa finalizada: {title}", "htmlContent": html},
            timeout=15,
        )
        if r.status_code not in (200, 201): st.warning(f"Brevo erro {r.status_code}: {r.text}")
        else: st.toast("📧 Email enviado ao autor!", icon="✅")
    except Exception as e:
        st.warning(f"Falha ao enviar email: {e}")


# ── AUTH ──────────────────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    s = load_session()
    if not s:
        st.set_page_config(layout="centered", initial_sidebar_state="collapsed")
        st.error("⚠️ Faça login primeiro!")
        if st.button("← Login", key="go_back"):
            st.switch_page("app.py")
        st.stop()

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")
conn = st.connection("gsheets", type=GSheetsConnection)

def calc_status(d):
    try:
        dl = datetime.strptime(d, '%d/%m/%Y').date()
        t  = now_brt().date()
        return "Atrasada" if dl < t else "Curto Prazo" if dl <= t + timedelta(days=3) else "Em dia"
    except:
        return "Em dia"

def recalc():
    try:
        df = conn.read(worksheet="tasks", ttl=0)
        if df.empty: return True
        for i in df.index:
            row_num  = i + 2
            resp_id  = df.loc[i, 'responsible_id'] if 'responsible_id' in df.columns else ''
            user_id  = df.loc[i, 'user_id']        if 'user_id'        in df.columns else ''
            formulas = make_formulas(row_num, resp_id, user_id)
            for k, val in formulas.items():
                df.loc[i, k] = val
          
        conn.update(worksheet="tasks", data=df)
        load_data.clear()
        return True
    except Exception as e:
        st.error(e)
    return False

@st.cache_data(ttl=600)
def load_data():
    try:
        u = conn.read(worksheet="users_auth", ttl=600)
        c = conn.read(worksheet="config", usecols=list(range(2)), ttl=600)
        t = conn.read(worksheet="tasks", ttl=600)
        if not t.empty and 'deadline' in t.columns:
            t['status'] = t['deadline'].apply(calc_status)
        return u, c, t, (u['full_name'].tolist() if not u.empty else []), (c['priority'].tolist() if not c.empty else [])
    except Exception as e:
        st.error(e); return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), [], []

users_df, config_df, tasks_df, users_list, prio_list = load_data()


# ── FÓRMULAS DINÂMICAS ────────────────────────────────────────────────
def make_formulas(row_num, responsible_id, user_id):
    return {
        'responsible':       f'=SEERRO(PROCX(D{row_num};users_auth!A:A;users_auth!E:E;"");"")' ,
        'url_responsible':   f'=SEERRO(PROCX(D{row_num};users_auth!A:A;users_auth!K:K;"");"")' ,
        'email_responsible': f'=SEERRO(PROCX(D{row_num};users_auth!A:A;users_auth!C:C;"");"")' ,
        'user_full_name':    f'=SEERRO(PROCX(N{row_num};users_auth!A:A;users_auth!E:E;"");"")' ,
        'user_email':        f'=SEERRO(PROCX(N{row_num};users_auth!A:A;users_auth!C:C;"");"")' ,
        'user_image':        f'=SEERRO(PROCX(N{row_num};users_auth!A:A;users_auth!K:K;"");"")' ,
        'status':            f'=SE(G{row_num}="";"";SE(G{row_num}<HOJE();"Atrasada";SE(G{row_num}<=HOJE()+3;"Curto Prazo";"Em dia")))',
    }

def update_sheet(td, action):
    try:
        df = conn.read(worksheet="tasks", ttl=0)
        if action == 'create':
            td['id']    = 1 if df.empty else int(df['id'].max()) + 1
            row_num     = len(df) + 2
            formulas    = make_formulas(row_num, td.get('responsible_id', ''), td.get('user_id', ''))
            new_td = {
                'id': td['id'], 'title': td['title'], 'description': td.get('description', ''),
                'responsible_id': td.get('responsible_id', ''), 'responsible': formulas['responsible'],
                'priority': td['priority'], 'deadline': td['deadline'], 'status': formulas['status'],
                'url_responsible': formulas['url_responsible'], 'email_responsible': formulas['email_responsible'],
                'created': td['created'], 'user': td.get('user', ''), 'my_task': td.get('my_task', 'A Fazer'),
                'user_id': td.get('user_id', ''), 'user_full_name': formulas['user_full_name'],
                'user_email': formulas['user_email'], 'user_image': formulas['user_image'],
                'updated_at': td['updated_at'],
            }
            df = pd.concat([df, pd.DataFrame([new_td])], ignore_index=True)
        elif action == 'update':
            i        = df[df['id'] == td['id']].index[0]
            row_num  = i + 2
            formulas = make_formulas(row_num, td.get('responsible_id', df.loc[i, 'responsible_id']), df.loc[i, 'user_id'])
            df.loc[i, 'title']             = td['title']
            df.loc[i, 'description']       = td.get('description', '')
            df.loc[i, 'responsible_id']    = td.get('responsible_id', df.loc[i, 'responsible_id'])
            df.loc[i, 'responsible']       = formulas['responsible']
            df.loc[i, 'priority']          = td['priority']
            df.loc[i, 'deadline']          = td['deadline']
            df.loc[i, 'status']            = formulas['status']
            df.loc[i, 'url_responsible']   = formulas['url_responsible']
            df.loc[i, 'email_responsible'] = formulas['email_responsible']
            df.loc[i, 'updated_at']        = td['updated_at']
        elif action == 'delete':
            df = df[df['id'] != td['id']]
        conn.update(worksheet="tasks", data=df)
        load_data.clear()
        return True
    except Exception as e:
        st.error(e)
        return False


# ── CSS ───────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*{font-family:'Inter',sans-serif!important}
#MainMenu,footer,header,.stDeployButton,[data-testid="stToolbar"],[data-testid="stToolbarActions"],
[data-testid="stDecoration"],[data-testid="stStatusWidget"],[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],[data-testid="manage-app-button"],[data-testid="stBaseButton-header"],
button[title="Deploy"],button[aria-label="Deploy"],button[aria-label="Share"],button[title="Share"],
.stAppDeployButton,section[data-testid="stSidebar"],div[class*="deployButton"],div[class*="viewerBadge"],
div[class*="StatusWidget"],iframe[title="streamlit_analytics"]{display:none!important}
footer{visibility:hidden!important;height:0!important}
.block-container,.element-container,.stMarkdown{padding:0!important;margin:0!important;max-width:100%!important}
.stButton>button{position:fixed!important;left:-9999px!important;opacity:0!important;pointer-events:all!important;width:1px!important;height:1px!important}
[data-testid="stHorizontalBlock"]{gap:0!important;margin:0!important;padding:0!important;height:0!important;overflow:visible!important;position:relative!important}
iframe{position:fixed!important;top:0!important;left:0!important;width:100vw!important;height:100dvh!important;border:none!important;z-index:9999!important}
@media(max-width:900px){
  iframe{position:relative!important;width:100%!important;height:100dvh!important;overflow:auto!important}
  [data-testid="stAppViewContainer"],[data-testid="stMain"],.main,.block-container{height:100dvh!important;overflow:visible!important;padding:0!important}
}
.main,[data-testid="stAppViewContainer"]{background:#fff!important}
div[data-testid="stDialog"]{z-index:99999!important;position:fixed!important}
div[data-testid="stDialog"] .stButton>button{font-size:13px!important;color:#374151!important;background:#fff!important;border:1px solid rgba(0,0,0,.12)!important;padding:6px 14px!important;height:34px!important;width:auto!important;border-radius:8px!important;cursor:pointer!important;position:relative!important;left:auto!important;top:auto!important;opacity:1!important}
div[data-testid="stDialog"] .stButton>button[kind="primary"]{background:#1d4ed8!important;border-color:#1d4ed8!important;color:#fff!important}
div[data-testid="stDialog"] [data-testid="stHorizontalBlock"]{height:auto!important;overflow:visible!important;gap:8px!important}
</style>""", unsafe_allow_html=True)

# ── STATE ──
for k, v in [('dialog_action', None), ('dialog_task_id', None), ('show_menu', False)]:
    st.session_state.setdefault(k, v)

# ── QUERY PARAMS → ACTIONS ────────────────────────────────────────────
qp = st.query_params
act, tid, tst = qp.get("action", ""), qp.get("task_id", ""), qp.get("task_status", "")

def qclear_rerun(**kw):
    st.session_state.update(**kw); st.query_params.clear(); st.rerun()

if   act == "create" and st.session_state.dialog_action != "create":
    qclear_rerun(dialog_action="create", dialog_task_id=None, show_menu=False)
elif act == "menu":
    qclear_rerun(show_menu=not st.session_state.show_menu)
elif act == "recalc":
    recalc() and load_data.clear()
    qclear_rerun(show_menu=False)
elif act == "edit_user":
    qclear_rerun(dialog_action="edit_user", show_menu=False)
elif act == "logout":
    clear_session(); st.query_params.clear(); st.switch_page("app.py")
elif act == "edit" and tid:
    qclear_rerun(dialog_action="edit", dialog_task_id=int(tid))
elif act == "delete" and tid:
    qclear_rerun(dialog_action="delete", dialog_task_id=int(tid))
elif act == "move" and tid and tst:
    try:
        df2 = conn.read(worksheet="tasks", ttl=0)
        m   = df2['id'] == int(tid)
        if m.any():
            idx2       = df2[m].index[0]
            old_status = df2.loc[idx2, 'my_task']
            df2.loc[idx2, 'my_task']    = tst
            df2.loc[idx2, 'updated_at'] = now_brt().strftime('%d/%m/%Y %H:%M:%S')
            conn.update(worksheet="tasks", data=df2)
            load_data.clear()
            if tst == 'Finalizada' and old_status != 'Finalizada':
                send_task_done_email(df2.loc[idx2].to_dict())
    except Exception as e:
        st.error(e)
    st.query_params.clear(); st.rerun()

if not st.session_state.get("user_data"):
    uid = st.session_state.get("session_uid")
    if uid and not users_df.empty:
        m = users_df['id'].astype(str).str.split('.').str[0] == str(uid).split('.')[0]
        if m.any():
            row = users_df[m].iloc[0]
            st.session_state.user_data = {
                "id":        row.get("id", ""),
                "username":  row.get("username", st.session_state.get("session_usr", "")),
                "full_name": row.get("full_name", ""),
                "email":     row.get("email", ""),
                "image_url": row.get("image_url", ""),
            }
        else:
            clear_session(); st.switch_page("app.py")
    else:
        clear_session(); st.switch_page("app.py")

user = st.session_state.user_data
img_url = user.get('image_url', '')
mins    = session_mins()

# ── SORT TASKS ────────────────────────────────────────────────────────
fdf = tasks_df.copy()
if not fdf.empty:
    fmt = '%d/%m/%Y %H:%M:%S'
    def parse_dt(col):
        if col not in fdf.columns: return pd.Series([pd.NaT] * len(fdf), index=fdf.index)
        return pd.to_datetime(fdf[col].replace('', None).replace('__', None), format=fmt, errors='coerce')
    fdf['_u'] = parse_dt('updated_at'); fdf['_c'] = parse_dt('created')
    fdf['_s'] = fdf['_u'].fillna(fdf['_c'])
    fdf = fdf.sort_values('_s', ascending=False, na_position='last').drop(columns=['_u','_c','_s'], errors='ignore')

all_prio = sorted(set(tasks_df['priority'].dropna())) if not tasks_df.empty and 'priority' in tasks_df.columns else prio_list
all_stat = ['Atrasada', 'Curto Prazo', 'Em dia']

# ── DIALOG ────────────────────────────────────────────────────────────
@st.dialog("Criar / Editar Tarefa")
def dialog():
    a, tid2 = st.session_state.dialog_action, st.session_state.dialog_task_id
    if a not in ['create', 'edit', 'delete', 'edit_user']:
        st.session_state.dialog_action = None; st.rerun(); return

    def done(msg=""):
        if msg: st.success(msg)
        st.session_state.dialog_action = None; st.rerun()

    if a in ('create', 'edit'):
        is_new = a == 'create'
        task   = {} if is_new else tasks_df[tasks_df['id'] == tid2].iloc[0].to_dict()
        with st.form("tf", clear_on_submit=is_new):
            title = st.text_input("Título *", value=task.get('title', ''))
            desc  = st.text_area("Descrição", value=task.get('description', ''))
            c1, c2 = st.columns(2)
            ri = users_list.index(task['responsible']) if not is_new and task.get('responsible') in users_list else 0
            pi = prio_list.index(task['priority'])     if not is_new and task.get('priority')    in prio_list  else 0
            with c1: resp = st.selectbox("Responsável *", users_list, index=ri)
            with c2: prio = st.selectbox("Prioridade",    prio_list,  index=pi)
            dl_val = datetime.strptime(task['deadline'], '%d/%m/%Y').date() if not is_new else now_brt().date()
            dl = st.date_input("Data Limite", value=dl_val, format="DD/MM/YYYY")

            if is_new:
                if st.form_submit_button("Criar", type="primary"):
                    if title and resp:
                        ur     = users_df[users_df['full_name'] == resp].iloc[0]
                        ts_now = now_brt().strftime('%d/%m/%Y %H:%M:%S')
                        td = {
                            'title': title, 'description': desc,
                            'responsible_id': int(ur.get('id', '')),
                            'priority': prio, 'deadline': dl.strftime('%d/%m/%Y'),
                            'created': ts_now, 'updated_at': ts_now,
                            'user': user.get('full_name', ''), 'user_id': user.get('id', ''),
                            'my_task': 'A Fazer',
                            'responsible': resp, 'url_responsible': str(ur.get('image_url', '')),
                            'email_responsible': str(ur.get('email', '')),
                            'user_full_name': user.get('full_name', ''),
                            'user_email': user.get('email', ''), 'user_image': user.get('image_url', ''),
                        }
                        if update_sheet(td, 'create'):
                            send_task_created_email(td); done("Criada!")
                    else:
                        st.error("Preencha os campos obrigatórios")
            else:
                b1, b2 = st.columns(2)
                with b1: save   = st.form_submit_button("Salvar",   type="primary", use_container_width=True)
                with b2: cancel = st.form_submit_button("Cancelar", use_container_width=True)
                if cancel: done()
                if save and title and resp:
                    ur = users_df[users_df['full_name'] == resp].iloc[0]
                    td = {
                        'id': tid2, 'title': title, 'description': desc,
                        'responsible_id': int(ur.get('id', '')),
                        'priority': prio, 'deadline': dl.strftime('%d/%m/%Y'),
                        'updated_at': now_brt().strftime('%d/%m/%Y %H:%M:%S'),
                        'responsible': resp, 'url_responsible': str(ur.get('image_url', '')),
                        'email_responsible': str(ur.get('email', '')),
                    }
                    update_sheet(td, 'update') and done("Atualizado!")

    elif a == 'edit_user':
        with st.form("uf"):
            fn  = st.text_input("Nome completo", value=user.get('full_name', ''))
            st.text_input("E-mail", value=user.get('email', ''), disabled=True)
            img = st.text_input("URL da foto", value=user.get('image_url', ''))
            if img.strip(): st.image(img.strip(), width=60)
            pw  = st.text_input("Nova senha",      type="password", placeholder="deixe vazio para manter")
            pw2 = st.text_input("Confirmar senha", type="password")
            b1, b2 = st.columns(2)
            with b1: save   = st.form_submit_button("Salvar",   type="primary", use_container_width=True)
            with b2: cancel = st.form_submit_button("Cancelar", use_container_width=True)
            if cancel: done()
            if save:
                if pw and pw != pw2: st.error("Senhas não coincidem.")
                elif not fn.strip():  st.error("Nome obrigatório.")
                else:
                    try:
                        df_a = conn.read(worksheet="users_auth", ttl=0)
                        m    = df_a['id'] == user.get('id')
                        if m.any():
                            i = df_a[m].index[0]
                            df_a.loc[i, 'full_name'] = fn.strip()
                            df_a.loc[i, 'image_url'] = img.strip()
                            if pw: df_a.loc[i, 'password'] = hashlib.sha256(pw.encode()).hexdigest()
                            conn.update(worksheet="users_auth", data=df_a)
                            st.session_state.user_data.update(full_name=fn.strip(), image_url=img.strip())
                            load_data.clear(); done("Perfil atualizado!")
                    except Exception as e: st.error(e)

    elif a == 'delete':
        task = tasks_df[tasks_df['id'] == tid2].iloc[0]
        st.warning(f"Excluir **{task['title']}**?"); st.caption("Esta ação não pode ser desfeita.")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("✓ Excluir", type="primary", use_container_width=True, key="ky"):
                update_sheet({'id': tid2}, 'delete') and done("Excluída!")
        with b2:
            if st.button("✗ Cancelar", use_container_width=True, key="kn"): done()

if st.session_state.dialog_action in ['create', 'edit', 'delete', 'edit_user']:
    dialog()

# ── BADGE HELPERS ─────────────────────────────────────────────────────
def pbadge(p):
    p = str(p).lower()
    c = "b-high" if any(x in p for x in ['alta','crítica','critica','high']) else \
        "b-med"  if any(x in p for x in ['média','media','medium','normal']) else "b-low"
    return f'<span class="badge {c}">{p.title()}</span>'

def sbadge(s):
    c = {"Atrasada": "b-late", "Curto Prazo": "b-soon"}.get(s, "b-ok")
    return f'<span class="badge {c}">{s}</span>'

# ── BUILD BOARD HTML ──────────────────────────────────────────────────
def build_board(df, u, img, mins, show_menu, prios, stats, resps):
    tasks = df.to_dict('records') if isinstance(df, pd.DataFrame) else df
    CM = {
        'A Fazer':      ('#1d4ed8','#dbeafe','#eff6ff'),
        'Em Andamento': ('#059669','#d1fae5','#f0fdf4'),
        'Paralizada':   ('#b45309','#fef3c7','#fffbeb'),
        'Finalizada':   ('#dc2626','#fee2e2','#fef2f2'),
    }
    by  = {k: [t for t in tasks if t.get('my_task') == k] for k in CM}
    tot = len(tasks)
    cnt = {k: len(v) for k, v in by.items()}
    pct = {k: (cnt[k] / tot * 100 if tot else 0) for k in cnt}

    av = (f'<img src="{img}" style="width:22px;height:22px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(0,0,0,.1);">'
          if img and img.strip()
          else f'<div style="width:22px;height:22px;border-radius:50%;background:#1d4ed8;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#fff;">{u["full_name"][0].upper()}</div>')
    timer = f'<span style="font-size:9px;color:#9ca3af;margin-left:3px;">⏱{mins}m</span>' if mins else ''
    menu  = (f'<div class="tb-menu">'
             f'<div class="menu-item" onclick="sa(\'recalc\')">↺ Atualizar</div>'
             f'<div class="menu-item" onclick="sa(\'edit_user\')">✎ Editar perfil</div>'
             f'<div class="menu-item menu-danger" onclick="sa(\'logout\')">Sair</div>'
             f'</div>') if show_menu else ''

    def opts(items, placeholder, val_fn=str):
        return f'<option value="">{placeholder}</option>' + ''.join(f'<option value="{val_fn(i)}">{i}</option>' for i in items)

    po = opts(prios, "Todas prioridades")
    so = opts(stats, "Todos status")
    ro = opts(resps, "Todos responsáveis", lambda r: str(r).lower())

    def cards(lst):
        h = ""
        for t in lst:
            tid3 = int(t['id'])
            desc = str(t.get('description', '') or '').strip()
            dh   = f'<div class="cd">{desc}</div>' if desc else ''
            nm   = str(t.get('responsible', '') or '')
            fn   = nm.split()[0] if nm else ''
            im   = str(t.get('url_responsible', '') or '').strip()
            ava  = (f'<img src="{im}" onerror="this.style.display=\'none\'">'
                    if im else f'<div class="av-fb">{"".join(w[0].upper() for w in nm.split()[:2]) or "?"}</div>')
            h += (f'<div class="card" draggable="true" data-id="{tid3}" data-status="{t["my_task"]}"'
                  f' data-priority="{t.get("priority","")}" data-stat="{t.get("status","")}"'
                  f' data-title="{str(t.get("title","")).lower()}" data-desc="{str(t.get("description","")).lower()}"'
                  f' data-responsible="{nm.lower()}">'
                  f'<div class="ca">'
                  f'<button class="act" onclick="event.stopPropagation();sa(\'edit\',{tid3})" title="Editar">'
                  f'<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4z"/></svg></button>'
                  f'<button class="act act-d" onclick="event.stopPropagation();sa(\'delete\',{tid3})" title="Excluir">'
                  f'<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6M9 6V4h6v2"/></svg></button>'
                  f'</div>'
                  f'<div class="ct">{t["title"]}</div>{dh}'
                  f'<div class="cb">{sbadge(t["status"])} {pbadge(t["priority"])}</div>'
                  f'<div class="cf"><span class="cd2">📅 {t["deadline"]}</span>'
                  f'<div class="cu">{ava}<span>{fn}</span></div></div></div>')
        return h

    cols = ""
    for key, (ac, zb, hb) in CM.items():
        slug  = key.replace(' ', '-')
        cols += (f'<div class="col" data-col="{key}">'
                 f'<div class="col-hdr" style="border-top:3px solid {ac};background:{hb};" onclick="toggleCol(this)">'
                 f'<div class="chr"><span class="ct2" style="color:{ac};">{key.upper()}</span>'
                 f'<span class="cc" id="cnt-{slug}" style="background:{ac};">{cnt[key]}</span>'
                 f'<span class="ctg">▶</span></div>'
                 f'<div class="pt"><div class="pf" id="prog-{slug}" style="width:{pct[key]:.1f}%;background:{ac};"></div></div></div>'
                 f'<div class="dz" data-status="{key}" style="background:{zb};">{cards(by[key])}</div></div>')

    return f'''<!DOCTYPE html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Inter',sans-serif}}
::-webkit-scrollbar{{width:4px}}::-webkit-scrollbar-thumb{{background:rgba(0,0,0,.14);border-radius:10px}}
html,body{{height:100%;overflow:hidden;background:#fff}}
@media(max-width:900px){{html,body{{height:auto!important;overflow-x:hidden!important;overflow-y:auto!important;min-height:100%}}}}
.topbar{{display:flex;align-items:center;height:44px;background:#fff;border-bottom:1px solid rgba(0,0,0,.07);padding:0 14px;gap:8px;position:fixed;top:0;left:0;right:0;z-index:100}}
.tbl{{height:26px;flex-shrink:0}}.tbsp{{color:#e5e7eb;font-size:14px;flex-shrink:0}}
.tbt{{font-size:12px;font-weight:600;color:#111827;flex-shrink:0}}.tbs{{font-size:10px;color:#9ca3af;flex-shrink:0}}
.tbf{{display:flex;align-items:center;gap:6px;margin-left:auto;flex-shrink:1;min-width:0}}
.tsr{{position:relative;display:flex;align-items:center;flex-shrink:1}}
.tsr svg{{position:absolute;left:7px;pointer-events:none;color:#9ca3af}}
.tsr input{{height:26px;padding:0 8px 0 26px;border:1px solid rgba(0,0,0,.1);border-radius:6px;background:#f9fafb;font-size:11px;color:#374151;outline:none;width:140px;transition:border-color .15s,width .2s,background .15s}}
.tsr input:focus{{border-color:#1d4ed8;background:#fff;width:180px}}.tsr input::placeholder{{color:#9ca3af}}
.sel{{height:26px;padding:0 22px 0 8px;border:1px solid rgba(0,0,0,.1);border-radius:6px;background:#f9fafb url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E") no-repeat right 6px center;-webkit-appearance:none;appearance:none;font-size:11px;color:#374151;outline:none;cursor:pointer;transition:border-color .15s;max-width:120px;flex-shrink:1}}
.sel:focus{{border-color:#1d4ed8;background-color:#fff}}
.sel.active,.tsr input.active{{border-color:#1d4ed8;background-color:#eff6ff;color:#1d4ed8;font-weight:500}}
.tbcl{{display:none;align-items:center;justify-content:center;height:22px;width:22px;border-radius:5px;border:1px solid rgba(0,0,0,.1);background:#fff;color:#6b7280;cursor:pointer;font-size:11px;font-weight:600;flex-shrink:0;transition:all .13s}}
.tbcl:hover{{background:#fef2f2;color:#dc2626;border-color:#fecaca}}.tbcl.visible{{display:flex}}
.tft{{display:none;align-items:center;justify-content:center;height:26px;width:26px;border-radius:6px;border:1px solid rgba(0,0,0,.1);background:#f9fafb;color:#374151;cursor:pointer;flex-shrink:0;transition:all .13s}}
.tft:hover{{background:#f3f4f6}}.tft.active{{background:#eff6ff;border-color:#1d4ed8;color:#1d4ed8}}
.fdw{{display:none;position:fixed;top:44px;left:0;right:0;z-index:90;background:#fff;border-bottom:1px solid rgba(0,0,0,.08);padding:10px 14px;gap:8px;flex-wrap:wrap;align-items:center;box-shadow:0 4px 12px rgba(0,0,0,.06)}}
.fdw.open{{display:flex}}.fdw .tsr{{flex:1;min-width:140px}}.fdw .tsr input{{width:100%}}.fdw .sel{{flex:1;min-width:100px;max-width:none}}.fdw .tbcl{{margin-left:auto}}
.tba{{display:flex;align-items:center;gap:4px;flex-shrink:0;margin-left:8px}}
.btn{{display:flex;align-items:center;gap:4px;height:26px;padding:0 9px;border-radius:6px;border:1px solid rgba(0,0,0,.1);background:#f9fafb;color:#374151;font-size:11px;font-weight:500;cursor:pointer;transition:all .13s;white-space:nowrap}}
.btn:hover{{background:#f3f4f6;border-color:rgba(0,0,0,.16)}}.btn.pr{{background:#1d4ed8;border-color:#1d4ed8;color:#fff}}.btn.pr:hover{{background:#1e40af}}
.tbu{{display:flex;align-items:center;gap:5px;margin-left:6px;flex-shrink:0}}.tbun{{font-size:10px;font-weight:600;color:#374151}}
.tb-menu{{position:fixed;top:46px;right:14px;background:#fff;border:1px solid rgba(0,0,0,.1);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.1);z-index:200;min-width:160px;overflow:hidden}}
.menu-item{{padding:8px 14px;font-size:11px;color:#374151;cursor:pointer}}.menu-item:hover{{background:#f3f4f6}}
.menu-danger{{color:#dc2626!important}}.menu-danger:hover{{background:#fef2f2!important}}
.board{{display:flex;gap:8px;height:calc(100vh - 44px);padding:8px;margin-top:44px;overflow-x:auto;overflow-y:hidden}}
.col{{flex:1;min-width:220px;display:flex;flex-direction:column;border:1px solid rgba(0,0,0,.07);border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.col-hdr{{padding:10px 12px 8px;flex-shrink:0;border-bottom:1px solid rgba(0,0,0,.05);cursor:default}}
.chr{{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}}
.ct2{{font-size:10px;font-weight:700;letter-spacing:.7px;text-transform:uppercase}}
.cc{{font-size:10px;font-weight:700;color:#fff;padding:1px 7px;border-radius:20px;transition:all .2s}}
.pt{{width:100%;height:2px;background:rgba(0,0,0,.07);border-radius:10px;overflow:hidden}}
.pf{{height:100%;border-radius:10px;opacity:.6;transition:width .3s ease}}
.ctg{{display:none;font-size:12px;color:#9ca3af;transition:transform .2s;margin-left:6px}}
.dz{{flex:1;overflow-y:auto;overflow-x:hidden;padding:6px;display:flex;flex-direction:column;gap:6px;min-height:60px}}
.dz.over{{filter:brightness(.94);outline:2px dashed rgba(0,0,0,.18);border-radius:8px}}
.card{{background:rgba(255,255,255,.8);border:1px solid rgba(255,255,255,.95);border-radius:8px;padding:9px 10px;cursor:grab;position:relative;transition:box-shadow .14s,transform .14s,background .14s,opacity .2s;flex-shrink:0;backdrop-filter:blur(4px)}}
.card:hover{{background:#fff;box-shadow:0 3px 12px rgba(0,0,0,.1);transform:translateY(-1px)}}
.card:hover .ca{{opacity:1;pointer-events:all}}.card:active{{cursor:grabbing}}
.card.dragging{{opacity:.35}}.card.hidden{{display:none}}
.ca{{position:absolute;top:7px;right:7px;display:flex;gap:3px;opacity:0;pointer-events:none;transition:opacity .13s}}
@media(hover:none){{.ca{{opacity:1;pointer-events:all}}}}
.act{{width:20px;height:20px;border-radius:5px;border:1px solid rgba(0,0,0,.09);background:rgba(255,255,255,.9);color:#6b7280;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .12s}}
.act:hover{{background:#f3f4f6;color:#111827}}.act-d:hover{{background:#fef2f2!important;color:#dc2626!important}}
.ct{{font-size:12px;font-weight:600;color:#111827;line-height:1.4;margin-bottom:4px;padding-right:48px;word-break:break-word}}
.cd{{font-size:10.5px;color:#6b7280;line-height:1.45;margin-bottom:6px;word-break:break-word;white-space:pre-wrap}}
.cb{{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:7px}}
.badge{{display:inline-flex;align-items:center;font-size:9px;font-weight:600;padding:2px 6px;border-radius:4px;text-transform:uppercase;letter-spacing:.3px;border:1px solid transparent;line-height:1.4}}
.b-high{{background:#fef2f2;color:#dc2626;border-color:#fecaca}}.b-med{{background:#fffbeb;color:#d97706;border-color:#fde68a}}
.b-low{{background:#f0fdf4;color:#16a34a;border-color:#bbf7d0}}.b-late{{background:#fef2f2;color:#b91c1c;border-color:#fecaca}}
.b-soon{{background:#fff7ed;color:#c2410c;border-color:#fed7aa}}.b-ok{{background:#f0fdf4;color:#15803d;border-color:#bbf7d0}}
.cf{{display:flex;align-items:center;justify-content:space-between;gap:6px;flex-wrap:wrap}}
.cd2{{font-size:9.5px;color:#9ca3af}}.cu{{display:flex;align-items:center;gap:4px;flex-shrink:0}}
.cu img{{width:18px;height:18px;border-radius:50%;object-fit:cover;border:1.5px solid rgba(0,0,0,.09)}}
.av-fb{{width:18px;height:18px;border-radius:50%;background:#e5e7eb;color:#374151;font-size:8px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.cu span{{font-size:10px;color:#6b7280;font-weight:500}}
.toast{{position:fixed;bottom:12px;right:12px;background:#111827;color:#f9fafb;padding:7px 14px;border-radius:7px;font-size:11px;font-weight:500;display:none;z-index:9999}}
@media(max-width:900px){{
  .tbs{{display:none}}.tbf{{display:none}}.tft{{display:flex}}.tbun{{display:none}}
  .board{{gap:6px;padding:6px;margin-top:44px;height:auto!important;overflow-x:auto!important;overflow-y:visible!important;-webkit-overflow-scrolling:touch}}
  .col{{min-width:260px;max-height:calc(100dvh - 60px);flex-shrink:0}}
  .dz{{overflow-y:auto!important;max-height:calc(100dvh - 120px)!important;-webkit-overflow-scrolling:touch}}
}}
@media(max-width:600px){{
  .topbar{{padding:0 10px;gap:6px;height:48px}}.tbl{{height:22px}}.tbt{{display:none}}
  .board{{flex-direction:column!important;height:auto!important;max-height:none!important;overflow:visible!important;padding:6px!important;margin-top:48px!important;gap:6px!important}}
  .col{{flex:none!important;min-width:0!important;width:100%!important;height:auto!important;max-height:none!important;overflow:visible!important;border-radius:10px!important}}
  .col-hdr{{cursor:pointer!important;user-select:none}}.ctg{{display:inline-block!important}}
  .dz{{max-height:none!important;height:auto!important;overflow:visible!important;transition:max-height .3s ease,padding .2s ease}}
  .col.collapsed .dz{{max-height:0!important;overflow:hidden!important;padding:0 6px!important}}
  .col.collapsed .ctg{{transform:rotate(-90deg)}}.fdw{{top:48px}}.tb-menu{{right:10px}}
  .card{{padding:10px 11px}}.ct{{font-size:13px}}.ca{{opacity:1!important;pointer-events:all!important}}
}}
</style></head><body>
<div class="topbar">
  <img class="tbl" src="https://companieslogo.com/img/orig/AZ2.F-d26946db.png?t=1720244490" alt="AZ">
  <span class="tbsp">·</span><span class="tbt">PMJA</span>
  <span class="tbsp" style="margin:0 2px;">·</span><span class="tbs">KANBAN Gestão de Materiais</span>
  <div class="tbf">
    <div class="tsr">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" id="fS" placeholder="Buscar…" oninput="af()">
    </div>
    <select class="sel" id="fP" onchange="af()">{po}</select>
    <select class="sel" id="fSt" onchange="af()">{so}</select>
    <select class="sel" id="fR" onchange="af()">{ro}</select>
    <button class="tbcl" id="bC" onclick="cf()">✕</button>
  </div>
  <button class="tft" id="bFT" onclick="tfd()" title="Filtros">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="11" y1="18" x2="13" y2="18"/></svg>
  </button>
  <div class="tba">
    <button class="btn pr" onclick="sa('create')">+ Nova tarefa</button>
    <button class="btn" onclick="sa('menu')" style="padding:0 8px;">⚙</button>
  </div>
  <div class="tbu">{av}<span class="tbun">{u['username']}{timer}</span></div>
</div>
{menu}
<div class="fdw" id="fdw">
  <div class="tsr">
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    <input type="text" id="fSm" placeholder="Buscar…" oninput="af()">
  </div>
  <select class="sel" id="fPm" onchange="af()">{po}</select>
  <select class="sel" id="fStm" onchange="af()">{so}</select>
  <select class="sel" id="fRm" onchange="af()">{ro}</select>
  <button class="tbcl" id="bCm" onclick="cf()">✕</button>
</div>
<div class="toast" id="toast">Salvando…</div>
<div class="board">{cols}</div>
<script>
function sa(a,id,st){{
  try{{
    const u=new URL(window.parent.location.href);
    u.searchParams.set('action',a);
    if(id) u.searchParams.set('task_id',id);
    if(st) u.searchParams.set('task_status',st);
    window.parent.history.replaceState(null,'',u.toString());
    window.parent.dispatchEvent(new PopStateEvent('popstate',{{state:null}}));
    window.parent.postMessage({{type:'streamlit:setComponentValue',value:a}},'*');
  }}catch(e){{console.warn(e)}}
  setTimeout(()=>{{try{{const u=new URL(window.parent.location.href);if(u.searchParams.get('action')===a)window.parent.location.href=u.toString();}}catch(e2){{}}}},150);
}}
function mv(id,st){{
  const t=document.getElementById('toast');t.style.display='block';t.textContent='Salvando…';
  sa('move',id,st);setTimeout(()=>{{t.textContent='✓ Salvo!';setTimeout(()=>t.style.display='none',1000);}},400);
}}
function gv(id){{const e=document.getElementById(id);return e?(e.value||'').toLowerCase().trim():''}}
function af(){{
  const s=gv('fS')||gv('fSm'),p=gv('fP')||gv('fPm'),st=gv('fSt')||gv('fStm'),r=gv('fR')||gv('fRm');
  const has=s||p||st||r;
  ['bC','bCm'].forEach(id=>document.getElementById(id).classList.toggle('visible',has));
  [['fS',s],['fP',p],['fSt',st],['fR',r],['fSm',s],['fPm',p],['fStm',st],['fRm',r]].forEach(([id,v])=>{{
    const e=document.getElementById(id);if(e)e.classList.toggle('active',!!v);
  }});
  const cards=document.querySelectorAll('.card'),tot=cards.length;
  cards.forEach(c=>{{
    c.classList.toggle('hidden',!(
      (!s||c.dataset.title.includes(s)||c.dataset.desc.includes(s))&&
      (!p||c.dataset.priority.toLowerCase()===p)&&
      (!st||c.dataset.stat.toLowerCase()===st)&&
      (!r||c.dataset.responsible.toLowerCase()===r)
    ));
  }});
  document.querySelectorAll('.col').forEach(col=>{{
    const n=col.querySelectorAll('.card:not(.hidden)').length;
    const ce=col.querySelector('.cc'),pe=col.querySelector('.pf');
    if(ce)ce.textContent=n;if(pe)pe.style.width=tot?(n/tot*100).toFixed(1)+'%':'0%';
  }});
}}
function cf(){{
  ['fS','fP','fSt','fR','fSm','fPm','fStm','fRm'].forEach(id=>{{const e=document.getElementById(id);if(e)e.value='';}});af();
}}
function toggleCol(h){{if(window.innerWidth>600)return;h.closest('.col').classList.toggle('collapsed');}}
function tfd(){{
  const d=document.getElementById('fdw'),b=document.getElementById('bFT');
  b.classList.toggle('active',d.classList.toggle('open'));
}}
let dc;
document.addEventListener('dragstart',e=>{{if(e.target.classList.contains('card')){{dc=e.target;setTimeout(()=>e.target.classList.add('dragging'),0);e.dataTransfer.effectAllowed='move';}}}});
document.addEventListener('dragend',e=>{{if(e.target.classList.contains('card'))e.target.classList.remove('dragging');}});
document.querySelectorAll('.dz').forEach(z=>{{
  z.addEventListener('dragover',e=>{{e.preventDefault();z.classList.add('over');}});
  z.addEventListener('dragleave',e=>{{if(!z.contains(e.relatedTarget))z.classList.remove('over');}});
  z.addEventListener('drop',e=>{{
    e.preventDefault();z.classList.remove('over');
    if(dc){{const id=dc.getAttribute('data-id'),ov=dc.getAttribute('data-status'),nv=z.getAttribute('data-status');
      if(ov!==nv){{dc.setAttribute('data-status',nv);z.appendChild(dc);mv(id,nv);}}}}
  }});
}});
</script></body></html>'''

components.html(
    build_board(fdf, user, img_url, mins, st.session_state.show_menu, all_prio, all_stat, users_list),
    height=4000, scrolling=True
)