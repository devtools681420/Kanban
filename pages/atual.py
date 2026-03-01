import streamlit as st

# 1. Configuração da página (deve ser o primeiro comando Streamlit)
st.set_page_config(page_title="Meu App", layout="wide")

# 2. O "Truque" que o config.toml não faz:
st.markdown("""
    <style>
    /* Remove o cabeçalho, o menu e o rodapé em qualquer tela */
    [data-testid="stHeader"], [data-testid="stToolbar"], footer {
        display: none !important;
    }
    
    /* Faz o conteúdo colar no topo da tela (importante para mobile) */
    .main .block-container {
        padding-top: 0rem;
        padding-bottom: 0rem;
    }
    </style>
    """, unsafe_allow_html=True)

st.write("Visual limpo com sucesso!")