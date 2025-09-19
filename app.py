# app_streamlit_refis.py — Simulador REFIS (Anápolis)
# Compacto + OU Itens + OU Grupos + Persistência + Fix Arrow/Parcelas + Campos lado a lado
import streamlit as st, pandas as pd, json
from dataclasses import dataclass, asdict
from typing import List, Dict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime

# -------- WeasyPrint (PDF) --------
WEASYPRINT_OK = WEASYPRINT_VER = WEASYPRINT_ERR = ""
try:
    import weasyprint  # type: ignore
    from weasyprint import HTML  # type: ignore
    WEASYPRINT_OK = True
    WEASYPRINT_VER = getattr(weasyprint, "__version__", "")
except Exception as e:
    WEASYPRINT_OK = False
    WEASYPRINT_ERR = repr(e)

# -------- Tema e Estilo --------
st.set_page_config(page_title="Simulador REFIS – Anápolis", page_icon="💸", layout="wide")

# Tema personalizado
st.markdown("""
<style>
    /* Cores principais */
    :root {
        --primary: #1e40af;
        --secondary: #3b82f6;
        --success: #059669;
        --danger: #dc2626;
        --warning: #d97706;
        --background: #f8fafc;
    }
    
    /* Layout base */
    .stApp {
        background-color: var(--background);
    }
    
    /* Cards e containers */
    [data-testid="stVerticalBlock"] {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    
    /* Botões mais modernos */
    .stButton > button {
        width: 100%;
        border-radius: 0.375rem;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
    }
    
    /* Métricas mais compactas */
    [data-testid="metric-container"] {
        padding: 0.5rem;
        border-radius: 0.375rem;
        background: #f1f5f9;
    }
    
    /* Tabelas mais modernas */
    [data-testid="stDataFrame"] > div > div > table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        overflow: hidden;
    }
    
    [data-testid="stDataFrame"] > div > div > table thead tr th {
        background: #f8fafc;
        padding: 12px 16px;
        font-weight: 600;
        color: #1e40af;
        border-bottom: 2px solid #e2e8f0;
        white-space: nowrap;
    }
    
    [data-testid="stDataFrame"] > div > div > table tbody tr td {
        padding: 12px 16px;
        border-bottom: 1px solid #e2e8f0;
    }
    
    [data-testid="stDataFrame"] > div > div > table tbody tr:nth-child(even) {
        background: #f8fafc;
    }
    
    /* Cards de resumo */
    .refis-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
        border: 1px solid #e2e8f0;
    }
    
    /* Tags de status */
    .status-tag {
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 500;
    }
    .status-success { background: #dcfce7; color: #059669; }
    .status-warning { background: #fef3c7; color: #d97706; }
    .status-info { background: #dbeafe; color: #2563eb; }
    
    /* Tooltips mais visíveis */
    [data-baseweb="tooltip"] {
        background: #1e293b !important;
        border-radius: 6px !important;
        padding: 8px 12px !important;
    }
    
    /* Badges para números */
    .number-badge {
        background: #eef2ff;
        color: #1e40af;
        padding: 2px 8px;
        border-radius: 6px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# -------- Helpers --------
brl = lambda v: (f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if v is not None else "—"

def to_decimal(v) -> Decimal:
    if isinstance(v, (int, float)): s = str(v)
    elif isinstance(v, Decimal):    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:                            s = str(v).strip().replace(".", "").replace(",", ".")
    return Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def currency_input(label: str, key: str, default: float = 0.0, container=None) -> float:
    place = container if container is not None else st
    if key not in st.session_state:
        st.session_state[key] = f"{default:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    raw = place.text_input(label, value=st.session_state[key], key=f"{key}_raw")
    try:
        val = to_decimal(raw)
        st.session_state[key] = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return float(val)
    except (InvalidOperation, ValueError):
        place.warning(f"Valor inválido em “{label}”. Use apenas números, ponto/vírgula.")
        return 0.0

def coerce_int64(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df

def stringify_mixed(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Força cols para string, útil quando há números e '—' misturados (compat Arrow)."""
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(lambda x: "—" if (pd.isna(x) or x == "—") else str(x))
    return df

def stringify_complex_objects_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Evita listas/dicts em st.dataframe convertendo para JSON curto."""
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == "object":
            sample = df[c].dropna().head(20)
            if sample.apply(lambda x: isinstance(x, (list, dict, set, tuple))).any():
                df[c] = df[c].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict, set, tuple)) else ("" if pd.isna(x) else x))
    return df

NATUREZAS = [
    "IPTU/Taxas de Imóveis/Propriedades",
    "ISSQN",
    "Multas formais/de ofício",
    "Multas PROCON/Meio Ambiente/Posturas/Vig.Sanitária/Obras",
    "Taxa de Inscrição Municipal (CNPJ/CPF)",
]
PERFIS = ["PF/MEI", "PJ"]
OPCOES = ["À vista", "Parcelado"]

def desconto_percent(natureza, opcao, parcelas):
    if natureza in ("IPTU/Taxas de Imóveis/Propriedades", "Taxa de Inscrição Municipal (CNPJ/CPF)"):
        if opcao == "À vista": return 1.00
        if 2 <= parcelas <= 6:   return 0.95
        if 7 <= parcelas <= 20:  return 0.90
        if 21 <= parcelas <= 40: return 0.80
        if 41 <= parcelas <= 60: return 0.70
        return 0.0
    if natureza == "ISSQN":
        if opcao == "À vista": return 1.00
        if 2 <= parcelas <= 6:   return 0.90
        if 7 <= parcelas <= 16:  return 0.80
        return 0.0
    if natureza in ["Multas formais/de ofício", "Multas PROCON/Meio Ambiente/Posturas/Vig.Sanitária/Obras"]:
        return 0.50 if opcao == "À vista" else 0.0
    return 0.0

def parcela_minima(perfil): return 152.50 if perfil == "PF/MEI" else 457.50
def limites_parcelas(natureza):
    if natureza in ("IPTU/Taxas de Imóveis/Propriedades", "Taxa de Inscrição Municipal (CNPJ/CPF)"): return (1, 60)
    if natureza == "ISSQN": return (1, 16)
    return (1, 1)  # Multas: só à vista

def base_desconto(natureza, principal, encargos, correcao):
    if natureza in ["Multas formais/de ofício", "Multas PROCON/Meio Ambiente/Posturas/Vig.Sanitária/Obras"]:
        return max(principal, 0.0) + max(encargos, 0.0)
    return max(encargos, 0.0)  # Correção nunca entra na base

def ou_key_item(emp, perfil, natureza, desc, exerc, principal) -> str:
    return f"{emp}|{perfil}|{natureza}|{desc}|{int(exerc)}|{float(principal):.2f}"

def item_signature(desc: str, exerc: int, principal: float) -> str:
    return f"{int(exerc)}|{desc.strip()}|{float(principal):.2f}"

def ou_key_group(emp: str, perfil: str, natureza: str, itens_df: pd.DataFrame) -> str:
    sigs = sorted(item_signature(r["Descricao"], int(r["Exercicio"]), float(r["Principal"])) for _, r in itens_df.iterrows())
    return f"{emp}|{perfil}|{natureza}|[{';'.join(sigs)}]"

def calc_refis(perfil, natureza, opcao, parcelas, principal, encargos, correcao, entrada_tipo="none", entrada_val=0.0):
    pmin = parcela_minima(perfil)
    min_vista = 305 if perfil == "PF/MEI" else 915
    alerta = ""
    valor_atual = float(to_decimal(principal) + to_decimal(encargos) + to_decimal(correcao))

    if valor_atual < min_vista and opcao == "Parcelado":
        alerta = "Somente à vista pelo valor mínimo"
    if natureza in ["Multas formais/de ofício", "Multas PROCON/Meio Ambiente/Posturas/Vig.Sanitária/Obras"] and opcao == "Parcelado":
        alerta = "Multas: somente à vista"

    minp, maxp = limites_parcelas(natureza)
    if opcao == "Parcelado" and not (minp <= parcelas <= maxp and parcelas >= 2):
        if natureza == "ISSQN" and parcelas > 16: alerta = "ISSQN: máximo 16 parcelas"
        elif natureza in ("IPTU/Taxas de Imóveis/Propriedades", "Taxa de Inscrição Municipal (CNPJ/CPF)") and parcelas > 60: alerta = "Taxas/IPTU: máximo 60 parcelas"
        elif parcelas < 2: alerta = "Mínimo de 2 parcelas"

    pct = desconto_percent(natureza, opcao, parcelas)
    base = float(to_decimal(base_desconto(natureza, principal, encargos, correcao)))
    desconto_rs = float(to_decimal(Decimal(str(base)) * Decimal(str(pct))))
    valor_refis = float(to_decimal(Decimal(str(valor_atual)) - Decimal(str(desconto_rs))))

    entrada_abs = primeira = demais = valor_parcela = 0.0
    if opcao == "Parcelado" and parcelas > 0:
        if entrada_tipo == "valor":
            entrada_abs = max(0.0, min(float(to_decimal(entrada_val)), valor_refis))
        elif entrada_tipo == "percent":
            p = max(0.0, min(100.0, float(entrada_val)))
            entrada_abs = float(to_decimal(Decimal(str(valor_refis)) * Decimal(str(p/100.0))))
        if entrada_abs > 0 and parcelas >= 2:
            # Entrada SUBSTITUI a 1ª parcela: restante é dividido nas demais (parcelas-1)
            restante = float(to_decimal(Decimal(str(valor_refis)) - Decimal(str(entrada_abs))))
            demais = float(to_decimal(Decimal(str(restante)) / Decimal(str(parcelas - 1))))
            primeira = float(to_decimal(Decimal(str(entrada_abs))))
            if demais < pmin and not alerta:
                alerta = "Parcela (exceto entrada) abaixo do mínimo"
            if primeira < pmin and not alerta:
                alerta = "Entrada abaixo do mínimo"
        else:
            valor_parcela = float(to_decimal(Decimal(str(valor_refis)) / Decimal(str(parcelas))))
            primeira = demais = valor_parcela
            if valor_parcela < pmin and not alerta: alerta = "Parcela abaixo do mínimo"

    return dict(pmin=pmin, valor_atual=valor_atual, pct=pct, base=base, desconto_rs=desconto_rs,
                valor_refis=valor_refis, alerta=alerta, entrada_abs=entrada_abs,
                primeira=primeira, demais=demais, valor_parcela=valor_parcela)

# -------- Modelos --------
@dataclass
class Item:
    UID:int; Empresa:str; Perfil:str; Descricao:str; Exercicio:int; Natureza:str; Opcao:str; Parcelas:int
    Principal:float; Encargos:float; Correcao:float; ValorAtual:float; DescontoPct:float; BaseDesconto:float
    DescontoRS:float; ValorRefis:float; ParcelaMinima:float; Alerta:str; ValorParcela:float
    EntradaValor:float; PrimeiraParcela:float; DemaisParcelas:float; OUKey:str

@dataclass
class Grupo:
    GroupID:int; Empresa:str; Perfil:str; Natureza:str; Opcao:str; Parcelas:int; Itens:List[int]
    Principal:float; Encargos:float; Correcao:float; ValorAtual:float; DescontoPct:float; BaseDesconto:float
    DescontoRS:float; ValorRefis:float; ParcelaMinima:float; Alerta:str; PrimeiraParcela:float; DemaisParcelas:float
    OUKeyGroup:str

def simular_item(uid, emp, perfil, desc, exerc, natureza, opcao, parcelas, principal, encargos, correcao,
                 entrada_tipo="none", entrada_val=0.0) -> Item:
    r = calc_refis(perfil, natureza, opcao, parcelas, principal, encargos, correcao, entrada_tipo, entrada_val)
    return Item(
        uid, emp, perfil, desc, int(exerc), natureza, opcao, int(parcelas),
        float(to_decimal(principal)), float(to_decimal(encargos)), float(to_decimal(correcao)),
        r["valor_atual"], r["pct"], r["base"], r["desconto_rs"], r["valor_refis"], r["pmin"], r["alerta"], r["valor_parcela"],
        r["entrada_abs"], r["primeira"], r["demais"], ou_key_item(emp, perfil, natureza, desc, exerc, principal)
    )

def simular_grupo(group_id, itens: List[Item], natureza, opcao, parcelas, entrada_tipo="none", entrada_val=0.0) -> Grupo:
    emp, perfil = itens[0].Empresa, itens[0].Perfil
    principal = float(sum(to_decimal(i.Principal) for i in itens))
    encargos  = float(sum(to_decimal(i.Encargos)  for i in itens))
    correcao  = float(sum(to_decimal(i.Correcao)  for i in itens))
    r = calc_refis(perfil, natureza, opcao, parcelas, principal, encargos, correcao, entrada_tipo, entrada_val)
    tmp_df = pd.DataFrame([{"Descricao":i.Descricao,"Exercicio":i.Exercicio,"Principal":i.Principal} for i in itens])
    keyg = ou_key_group(emp, perfil, natureza, tmp_df)
    return Grupo(
        group_id, emp, perfil, natureza, opcao, int(parcelas), [i.UID for i in itens],
        principal, encargos, correcao, r["valor_atual"], r["pct"], r["base"], r["desconto_rs"],
        r["valor_refis"], r["pmin"], r["alerta"], r["primeira"], r["demais"], keyg
    )

# -------- Estado --------
for k, v in dict(rows=[], uid=1, grupos=[], gid=1).items():
    st.session_state.setdefault(k, v)

# -------- Definições de Colunas --------
expected_cols = [
    "UID","Empresa","Perfil","Descricao","Exercicio","Natureza","Opcao","Parcelas","Principal","Encargos",
    "Correcao","ValorAtual","DescontoPct","BaseDesconto","DescontoRS","ValorRefis","ParcelaMinima",
    "EntradaValor","PrimeiraParcela","DemaisParcelas","ValorParcela","Alerta","OUKey"
]

# -------- Preparação dos DataFrames --------
# DataFrame de itens
rows = st.session_state.get("rows", [])
df_all = pd.DataFrame(rows) if rows else pd.DataFrame(columns=expected_cols)
for c in expected_cols:
    if c not in df_all.columns: df_all[c] = pd.NA

# Fix: garantir dtypes numéricos
df_all = coerce_int64(df_all, ["UID","Exercicio","Parcelas"])
for c in ["Principal","Encargos","Correcao","ValorAtual","BaseDesconto","DescontoRS","ValorRefis",
          "ParcelaMinima","ValorParcela","EntradaValor","PrimeiraParcela","DemaisParcelas","DescontoPct"]:
    if c in df_all.columns:
        df_all[c] = pd.to_numeric(df_all[c], errors="coerce")

# DataFrame de grupos
gr_all = pd.DataFrame(st.session_state.grupos)
if not gr_all.empty:
    gr_all = coerce_int64(gr_all, ["GroupID","Parcelas"])
    for c in ["Principal","Encargos","Correcao","ValorAtual","BaseDesconto","DescontoRS","ValorRefis",
              "ParcelaMinima","PrimeiraParcela","DemaisParcelas","DescontoPct"]:
        if c in gr_all.columns:
            gr_all[c] = pd.to_numeric(gr_all[c], errors="coerce")

# Aplicar filtros conforme visão
try:
    if view_mode == "Somente esta empresa":
        df = df_all[df_all["Empresa"] == emp].copy()
        gr = gr_all[gr_all["Empresa"] == emp].copy() if not gr_all.empty else pd.DataFrame()
    else:
        df = df_all.copy()
        gr = gr_all.copy() if not gr_all.empty else pd.DataFrame()
except Exception:
    df = df_all.copy()
    gr = gr_all.copy() if not gr_all.empty else pd.DataFrame()

# -------- UI Tabs --------
with tab_simulador:
    st.markdown("### Adicionar Débitos")
    # Form de simulação com tooltips
    with st.form("form_item"):
        c1, c2, c3 = st.columns([2,1,1])
        desc = c1.text_input("Descrição do débito", 
                            help="Identifique o débito de forma clara e específica")
        exerc = c2.number_input("Exercício", min_value=2000, max_value=2100, value=2022, step=1,
                              help="Ano do débito")
        natureza = c3.selectbox("Natureza", NATUREZAS, index=4,
                              help="Tipo/categoria do débito - determina regras de desconto")

        c4, c5, c6 = st.columns([1,1,1])
        opcao = c4.radio("Opção", OPCOES, horizontal=True)
        minp, maxp = limites_parcelas(natureza)
        if opcao == "Parcelado":
            parcelas = c5.number_input("Nº de parcelas", min_value=2, max_value=maxp, value=min(12, maxp), step=1)
        else:
            parcelas = 1
            c5.write("Nº de parcelas:"); c5.write("— (à vista)")
        c6.write("Limites:"); c6.write(f"{minp}–{maxp}")

        v1, v2, v3 = st.columns(3)
        principal = currency_input("Principal / Tributo (R$)", "principal_in", 500.0, container=v1)
        encargos  = currency_input("Encargos (Multa + Juros) (R$)", "encargos_in", 120.0, container=v2)
        correcao  = currency_input("Correção (não entra no desconto) (R$)", "correcao_in", 20.0, container=v3)

        entrada_tipo, entrada_val = "none", 0.0
        if opcao == "Parcelado":
            st.markdown("**Entrada (opcional)**")
            use_ent = st.checkbox("Usar entrada", value=False)
            if use_ent:
                e1, e2 = st.columns([1,1])
                ent_choice = e1.radio("Tipo", ["Valor (R$)", "Percentual (%)"], horizontal=True)
                if ent_choice == "Valor (R$)":
                    entrada_tipo = "valor";  entrada_val = currency_input("Entrada (R$)", "entrada_val", 0.0, container=e2)
                else:
                    entrada_tipo = "percent"; entrada_val = e2.number_input("Entrada (%)", 0.00, 100.00, 0.00, 0.01, format="%.2f")

        # Garantir que botões de submit estejam no final do form
        col_btn1, col_btn2 = st.columns(2)
        preview_btn = col_btn1.form_submit_button("Atualizar prévia (Enter)", 
                                                type="secondary", use_container_width=True)
        add = col_btn2.form_submit_button("➕ Adicionar débito", 
                                        type="primary", use_container_width=True)

        # Mostrar prévia apenas se formulário foi submetido
        if preview_btn or add:
            preview = simular_item(0, emp, perfil, desc, exerc, natureza, opcao, int(parcelas),
                                 principal, encargos, correcao, entrada_tipo, entrada_val)
            
            st.divider()
            col1, col2, col3 = st.columns(3)
            
            with col1:
                card_metric(
                    "Valor Original + Encargos",
                    brl(preview.ValorAtual),
                    ("info", "Valor base para cálculo")
                )
            
            with col2:
                desconto_pct = preview.DescontoPct * 100
                status = "success" if desconto_pct >= 90 else "warning" if desconto_pct >= 50 else "info"
                card_metric(
                    "Desconto Total",
                    brl(preview.DescontoRS),
                    (status, f"{desconto_pct:.0f}% de desconto")
                )
                
            with col3:
                economia = preview.ValorAtual - preview.ValorRefis
                card_metric(
                    "Valor Final REFIS",
                    brl(preview.ValorRefis),
                    ("success", f"Economia de {brl(economia)}")
                )

            if preview.Alerta: st.error(preview.Alerta)

    if add:
        item = simular_item(st.session_state.uid, emp, perfil, desc, exerc, natureza, opcao, 
                           int(parcelas), principal, encargos, correcao, entrada_tipo, entrada_val)
        st.session_state.rows.append(asdict(item))
        st.session_state.uid += 1
        st.success("Débito adicionado!")

# -------- Tabela de itens (base) --------
expected_cols = [
    "UID","Empresa","Perfil","Descricao","Exercicio","Natureza","Opcao","Parcelas","Principal","Encargos",
    "Correcao","ValorAtual","DescontoPct","BaseDesconto","DescontoRS","ValorRefis","ParcelaMinima",
    "EntradaValor","PrimeiraParcela","DemaisParcelas","ValorParcela","Alerta","OUKey"
]
rows = st.session_state.get("rows", [])
df_all = pd.DataFrame(rows) if rows else pd.DataFrame(columns=expected_cols)
for c in expected_cols:
    if c not in df_all.columns: df_all[c] = pd.NA

# >>> Fix: garantir dtypes numéricos onde cabem (evita object desnecessário)
df_all = coerce_int64(df_all, ["UID","Exercicio","Parcelas"])
for c in ["Principal","Encargos","Correcao","ValorAtual","BaseDesconto","DescontoRS","ValorRefis",
          "ParcelaMinima","ValorParcela","EntradaValor","PrimeiraParcela","DemaisParcelas","DescontoPct"]:
    if c in df_all.columns:
        df_all[c] = pd.to_numeric(df_all[c], errors="coerce")
# aplicar filtro conforme visão selecionada (sidebar)
try:
    if view_mode == "Somente esta empresa":
        df = df_all[df_all["Empresa"] == emp].copy()
    else:
        df = df_all.copy()
except Exception:
    df = df_all.copy()
header_label = emp if view_mode == "Somente esta empresa" else "Todas as empresas"
st.markdown(f"### 📄 Débitos adicionados – **{header_label}**")
with st.expander("🗑️ Gerenciar débitos"):
    options_del = {int(r.UID): f"#{int(r.UID)} • [{int(r.Exercicio)}] {r.Descricao} ({r.Natureza}) • {r.Opcao} • Atual {brl(float(r.ValorAtual))}"
                   for r in df.itertuples()}
    sel_del = st.multiselect("Selecione débitos para excluir", options=list(options_del.keys()),
                             format_func=lambda k: options_del[k])
    cA, cB, cC = st.columns(3)
    if cA.button("Excluir selecionados", width="stretch"):
        st.session_state.rows = [row for row in st.session_state.rows if not (row["Empresa"]==emp and int(row["UID"]) in set(sel_del))]
        st.rerun()
    if cB.button("🧹 Limpar tudo (todas empresas)", width="stretch"):
        st.session_state.rows = []; st.session_state.grupos = []; st.session_state.uid = 1; st.session_state.gid = 1
        st.rerun()
    if cC.button("Começar em branco (apenas esta empresa)", width="stretch"):
        st.session_state.rows   = [r for r in st.session_state.rows   if r["Empresa"] != emp]
        st.session_state.grupos = [g for g in st.session_state.grupos if g["Empresa"] != emp]
        st.rerun()

# Resumo por opção (itens)
st.markdown("#### 📊 Resumo por opção")
resumo = df.groupby("Opcao").agg(Itens=("Opcao","count"),
                                 Valor_Atual=("ValorAtual","sum"),
                                 Desconto_RS=("DescontoRS","sum"),
                                 Valor_REFIS=("ValorRefis","sum")).reset_index()
res_view = resumo.copy()
for c in ["Valor_Atual","Desconto_RS","Valor_REFIS"]:
    res_view[c] = res_view[c].apply(brl)
st.dataframe(res_view, width="stretch", hide_index=True)

# -------- OU — ITENS --------
st.markdown("## 🔀 Visão consolidada (OU) — Itens (mesmo débito)")
if df.empty:
    st.info("Adicione débitos para ver a consolidação de itens.")
else:
    ou_groups_items: Dict[str, Dict[str, dict]] = {}
    for _, r in df.iterrows():
        key = ou_key_item(r["Empresa"], r["Perfil"], r["Natureza"], r["Descricao"], r["Exercicio"], r["Principal"])
        ou_groups_items.setdefault(key, {"meta": {
            "Empresa": r["Empresa"], "Perfil": r["Perfil"], "Natureza": r["Natureza"], "Descricao": r["Descricao"],
            "Exercício": int(r["Exercicio"]), "Principal": float(r["Principal"]), "Encargos": float(r["Encargos"]),
            "Correcao": float(r["Correcao"])
        }, "avista": None, "parcelado": None})
        pack = {"UID": int(r["UID"]), "ValorRefis": float(r["ValorRefis"]), "Parcelas": int(r["Parcelas"]),
                "Primeira": float(r.get("PrimeiraParcela", 0.0)), "Demais": float(r.get("DemaisParcelas", 0.0))}
        t = "avista" if r["Opcao"] == "À vista" else "parcelado"
        best = ou_groups_items[key][t]
        if (best is None) or (pack["ValorRefis"] < best["ValorRefis"]): ou_groups_items[key][t] = pack

    rows_view = []
    for data in ou_groups_items.values():
        m, av, par = data["meta"], data["avista"], data["parcelado"]
        melhor = ("À vista" if av and (not par or av["ValorRefis"] <= par["ValorRefis"])
                  else (f"Parcelado ({par['Parcelas']}x)" if par else ""))
        rows_view.append({
            "Empresa": m["Empresa"], "Perfil": m["Perfil"], "Natureza": m["Natureza"], "Descrição": m["Descricao"],
            "Exercício": m["Exercício"], "Tributo": m["Principal"], "Encargos": m["Encargos"], "Correção": m["Correcao"],
            "Valor Atual": m["Principal"] + m["Encargos"] + m["Correcao"],
            "À vista (R$)": av["ValorRefis"] if av else None,
            "Parcelado (R$)": par["ValorRefis"] if par else None,
            "Parcelas": par["Parcelas"] if par else "—",
            "1ª parcela": par["Primeira"] if par else None,
            "Demais parcelas": par["Demais"] if par else None,
            "Melhor opção": melhor
        })

    if rows_view:
        view_df = pd.DataFrame(rows_view)
        for c in ["Tributo","Encargos","Correção","Valor Atual","À vista (R$)","Parcelado (R$)","1ª parcela","Demais parcelas"]:
            view_df[c] = view_df[c].apply(lambda x: brl(x) if pd.notnull(x) else "—")
        # >>> Fix: Parcelas como string para evitar mix int/str (Arrow)
        view_df = stringify_mixed(view_df, ["Parcelas"])
        st.dataframe(view_df, width="stretch", hide_index=True)
    else:
        st.info("Ainda não há débitos para consolidar.")

# -------- Negociação em Grupo --------
st.markdown("## 🤝 Negociação em Grupo (mesma Empresa + Natureza)")
if df.empty:
    st.info("Adicione débitos para criar um grupo.")
else:
    f_emp = emp
    nat_options = df["Natureza"].unique().tolist()
    f_nat = st.selectbox("Natureza", nat_options, index=0)
    subset = df[(df["Empresa"] == f_emp) & (df["Natureza"] == f_nat)]
    if subset.empty:
        st.warning("Não há débitos desta natureza para agrupar.")
    else:
        opts = {int(r.UID): f"[{int(r.Exercicio)}] {r.Descricao} — Atual {brl(float(r.ValorAtual))}" for r in subset.itertuples()}
        selected = st.multiselect("Selecione os débitos (anos) a negociar juntos", options=list(opts.keys()),
                                  format_func=lambda k: opts[k])
        if selected:
            g_opcao = st.radio("Opção do GRUPO", OPCOES, horizontal=True, key="grp_opt")
            _, g_maxp = limites_parcelas(f_nat)
            if g_opcao == "Parcelado":
                g_parcelas = st.number_input("Nº de parcelas (grupo)", min_value=2, max_value=g_maxp,
                                             value=min(12, g_maxp), step=1, key="grp_parc")
                st.markdown("**Entrada do grupo (opcional)**")
                use_entry_g = st.checkbox("Usar entrada no grupo", value=False, key="grp_use_entry")
                g_entrada_tipo, g_entrada_val = "none", 0.0
                if use_entry_g:
                    ge1, ge2 = st.columns([1,1])
                    if ge1.radio("Tipo", ["Valor (R$)", "Percentual (%)"], horizontal=True, key="grp_tipo") == "Valor (R$)":
                        g_entrada_tipo = "valor";  g_entrada_val = currency_input("Entrada (R$)", "grp_ent_val", 0.0, container=ge2)
                    else:
                        g_entrada_tipo = "percent"; g_entrada_val = ge2.number_input("Entrada (%)", 0.00, 100.00, 0.00, 0.01, format="%.2f", key="grp_ent_pct")
            else:
                g_parcelas = 1
                st.write("Nº de parcelas (grupo):"); st.write("— (à vista)")
                g_entrada_tipo, g_entrada_val = "none", 0.0

            perfis = subset[subset["UID"].isin(selected)]["Perfil"].unique().tolist()
            if len(perfis) > 1:
                st.error("Os itens selecionados possuem perfis diferentes (PF/MEI e PJ). Separe por perfil.")
            else:
                chosen_df = subset[subset["UID"].isin(selected)].copy()
                chosen: List[Item] = []
                for _, r in chosen_df.iterrows():
                    chosen.append(Item(
                        UID=int(r["UID"]), Empresa=r["Empresa"], Perfil=r["Perfil"], Descricao=r["Descricao"],
                        Exercicio=int(r["Exercicio"]), Natureza=r["Natureza"], Opcao=r["Opcao"], Parcelas=int(r["Parcelas"]),
                        Principal=float(r["Principal"]), Encargos=float(r["Encargos"]), Correcao=float(r["Correcao"]),
                        ValorAtual=float(r["ValorAtual"]), DescontoPct=float(r["DescontoPct"]),
                        BaseDesconto=float(r["BaseDesconto"]), DescontoRS=float(r["DescontoRS"]),
                        ValorRefis=float(r["ValorRefis"]), ParcelaMinima=float(r["ParcelaMinima"]),
                        Alerta=str(r["Alerta"]), ValorParcela=float(r["ValorParcela"]),
                        EntradaValor=float(r.get("EntradaValor", 0.0)),
                        PrimeiraParcela=float(r.get("PrimeiraParcela", 0.0)),
                        DemaisParcelas=float(r.get("DemaisParcelas", 0.0)),
                        OUKey=r["OUKey"]
                    ))
                grp = simular_grupo(st.session_state.gid, chosen, f_nat, g_opcao, int(g_parcelas),
                                    entrada_tipo=g_entrada_tipo, entrada_val=g_entrada_val)

                st.subheader("Resultado do Grupo")
                g1, g2, g3, g4, g5 = st.columns(5)
                g1.metric("Valor Atual (grupo)", brl(grp.ValorAtual))
                g2.metric("Base de Desconto (grupo)", brl(grp.BaseDesconto))
                g3.metric("Desconto %", f"{grp.DescontoPct:.0%}")
                g4.metric("Desconto (R$)", brl(grp.DescontoRS))
                g5.metric("Valor pelo REFIS (grupo)", brl(grp.ValorRefis))
                if grp.Opcao == "Parcelado":
                    a, b = st.columns(2)
                    a.metric("1ª parcela (grupo)", brl(grp.PrimeiraParcela))
                    b.metric("Demais parcelas (grupo)", brl(grp.DemaisParcelas))
                if grp.Alerta: st.error(grp.Alerta)

                if st.button("💾 Salvar grupo de negociação"):
                    st.session_state.grupos.append(asdict(grp))
                    st.session_state.gid += 1
                    st.success("Grupo salvo! Você pode exportar ou consolidar abaixo.")

with tab_grupos:
    st.markdown("### 🤝 Negociação em Grupo")
    
    if df.empty:
        st.info("Adicione débitos na aba Simulador primeiro.")
    else:
        # Criação de grupos
        st.markdown("#### Criar novo grupo")
        if st.button("📦 Agrupar débitos selecionados"):
            if len(df) < 2:
                st.warning("Selecione pelo menos dois débitos para agrupar.")
            else:
                # Agrupar todos os débitos da tabela atual
                all_items = [simular_item(r.UID, r.Empresa, r.Perfil, r.Descricao, r.Exercicio, r.Natureza, r.Opcao, 
                                         r.Parcelas, r.Principal, r.Encargos, r.Correcao) for r in df.itertuples()]
                grupo = simular_grupo(st.session_state.gid, all_items, df.iloc[0].Natureza, "À vista", 1)
                st.session_state.grupos.append(asdict(grupo))
                st.session_state.gid += 1
                st.success("Grupo criado a partir dos débitos selecionados!")

        st.divider()
        # Grupos salvos
        st.markdown("#### Grupos salvos")
        gr_all = pd.DataFrame(st.session_state.grupos)
        if not gr_all.empty:
            # coerções leves
            gr_all = coerce_int64(gr_all, ["GroupID","Parcelas"])
            for c in ["Principal","Encargos","Correcao","ValorAtual","BaseDesconto","DescontoRS","ValorRefis",
                      "ParcelaMinima","PrimeiraParcela","DemaisParcelas","DescontoPct"]:
                if c in gr_all.columns:
                    gr_all[c] = pd.to_numeric(gr_all[c], errors="coerce")
        # aplicar mesmo filtro para grupos quando a visão estiver em "Somente esta empresa"
        try:
            if view_mode == "Somente esta empresa":
                gr = gr_all[gr_all["Empresa"] == emp].copy()
            else:
                gr = gr_all.copy()
        except Exception:
            gr = gr_all.copy()

        if gr.empty:
            st.info("Nenhum grupo salvo ainda para esta empresa.")
        else:
            view = gr.copy()[["GroupID","Empresa","Perfil","Natureza","Opcao","Parcelas",
                              "Principal","Encargos","Correcao","ValorAtual","BaseDesconto",
                              "DescontoPct","DescontoRS","ValorRefis","ParcelaMinima",
                              "PrimeiraParcela","DemaisParcelas","Alerta"]]
            for c in ["Principal","Encargos","Correcao","ValorAtual","BaseDesconto","DescontoRS","ValorRefis",
                      "ParcelaMinima","PrimeiraParcela","DemaisParcelas"]:
                view[c] = view[c].apply(brl)
            view["DescontoPct"] = (gr["DescontoPct"]*100).round(0).astype("Int64").astype(str) + "%"
            # Parcelas aqui é sempre numérica, mas garantimos string para Arrow-consistência
            view = stringify_mixed(view, ["Parcelas"])
            st.dataframe(view, width="stretch", hide_index=True)

            st.markdown("#### 📊 Resumo (empresa atual)")
            r_emp = gr.groupby("Empresa").agg(
                Grupos=("GroupID","count"),
                Valor_Atual=("ValorAtual","sum"),
                Desconto_RS=("DescontoRS","sum"),
                Valor_REFIS=("ValorRefis","sum")
            ).reset_index()
            rv = r_emp.copy()
            for c in ["Valor_Atual","Desconto_RS","Valor_REFIS"]:
                rv[c] = rv[c].apply(brl)
            st.dataframe(rv, width="stretch", hide_index=True)

# -------- OU — GRUPOS --------
st.markdown("## 🔁 Visão consolidada (OU) — Grupos (mesmo conjunto de taxas)")
if gr.empty:
    st.info("Salve pelo menos dois grupos (à vista e parcelado) com o mesmo conjunto de taxas para ver a consolidação.")
else:
    ou_groups_g: Dict[str, Dict[str, dict]] = {}
    for _, r in gr.iterrows():
        keyg = r.get("OUKeyGroup", "")
        if not keyg:
            ids = r.get("Itens", []) or []
            itens_df = df[df["UID"].isin(ids)][["Descricao","Exercicio","Principal"]]
            keyg = ou_key_group(r["Empresa"], r["Perfil"], r["Natureza"], itens_df) if not itens_df.empty else f"{r['Empresa']}|{r['Perfil']}|{r['Natureza']}|[legacy]"
        meta = {"Empresa": r["Empresa"], "Perfil": r["Perfil"], "Natureza": r["Natureza"], "OUKeyGroup": keyg}
        ou_groups_g.setdefault(keyg, {"meta": meta, "avista": None, "parcelado": None})
        pack = {"GroupID": int(r["GroupID"]), "ValorRefis": float(r["ValorRefis"]), "Parcelas": int(r["Parcelas"]),
                "Primeira": float(r.get("PrimeiraParcela", 0.0)), "Demais": float(r.get("DemaisParcelas", 0.0))}
        t = "avista" if r["Opcao"] == "À vista" else "parcelado"
        best = ou_groups_g[keyg][t]
        if (best is None) or (pack["ValorRefis"] < best["ValorRefis"]): ou_groups_g[keyg][t] = pack

    rows_g = []
    for data in ou_groups_g.values():
        m, av, par = data["meta"], data["avista"], data["parcelado"]
        melhor = ("À vista" if av and (not par or av["ValorRefis"] <= par["ValorRefis"])
                  else (f"Parcelado ({par['Parcelas']}x)" if par else "—"))
        rows_g.append({
            "Empresa": m["Empresa"], "Perfil": m["Perfil"], "Natureza": m["Natureza"],
            "Conjunto (hash)": m["OUKeyGroup"][-32:] if len(m["OUKeyGroup"])>32 else m["OUKeyGroup"],
            "À vista (R$)": av["ValorRefis"] if av else None,
            "Parcelado (R$)": par["ValorRefis"] if par else None,
            "Parcelas": par["Parcelas"] if par else "—",
            "1ª parcela": par["Primeira"] if par else None,
            "Demais parcelas": par["Demais"] if par else None,
            "Melhor opção": melhor
        })
    vg = pd.DataFrame(rows_g)
    for c in ["À vista (R$)","Parcelado (R$)","1ª parcela","Demais parcelas"]:
        vg[c] = vg[c].apply(lambda x: brl(x) if pd.notnull(x) else "—")
    # >>> Fix: Parcelas sempre string (evita ArrowTypeError)
    vg = stringify_mixed(vg, ["Parcelas"])
    st.dataframe(stringify_complex_objects_for_display(vg), width="stretch", hide_index=True)

# -------- 💾 Armazenamento externo --------
st.markdown("## 💾 Armazenamento externo")
st.info("Salve seus dados periodicamente para evitar perda.")
c_s1, c_s2, c_s3 = st.columns(3)

bundle = {"version":"1.2","rows":st.session_state.rows,"grupos":st.session_state.grupos,
          "uid":st.session_state.uid,"gid":st.session_state.gid}
json_bytes = json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")
c_s1.download_button("⬇️ Salvar tudo (JSON)", data=json_bytes, file_name="refis_dados.json", mime="application/json", width="stretch")

csv_itens = df_all.to_csv(index=False).encode("utf-8")
csv_grupos = gr_all.to_csv(index=False).encode("utf-8")
c_s2.download_button("⬇️ Itens (CSV)", data=csv_itens, file_name="refis_itens.csv", mime="text/csv", width="stretch")
c_s3.download_button("⬇️ Grupos (CSV)", data=csv_grupos, file_name="refis_grupos.csv", mime="text/csv", width="stretch")

st.markdown("#### Carregar dados (JSON)")
up = st.file_uploader("Selecione um arquivo JSON exportado pelo simulador", type=["json"])
if up is not None:
    try:
        payload = json.loads(up.read().decode("utf-8"))
        rows_in   = payload.get("rows", [])
        grupos_in = payload.get("grupos", [])
        def normalize_rows(rows):
            out=[]
            for r in rows:
                rec = {c: r.get(c, pd.NA) for c in expected_cols}
                out.append(rec)
            return out
        st.session_state.rows   = normalize_rows(rows_in)
        def normalize_grupos(gs):
            out=[]
            for g in gs:
                base = dict(g)
                if "OUKeyGroup" not in base or not base["OUKeyGroup"]:
                    ids = base.get("Itens", []) or []
                    itens_df = pd.DataFrame(st.session_state.rows)
                    subset = itens_df[itens_df["UID"].isin(ids)][["Descricao","Exercicio","Principal"]].copy()
                    base["OUKeyGroup"] = ou_key_group(base["Empresa"], base["Perfil"], base["Natureza"], subset) if not subset.empty else f"{base.get('Empresa','')}|{base.get('Perfil','')}|{base.get('Natureza','')}|[legacy]"
                out.append(base)
            return out
        st.session_state.grupos = normalize_grupos(grupos_in)
        st.session_state.uid = max([int(r["UID"]) for r in st.session_state.rows if pd.notna(r["UID"])], default=0) + 1
        st.session_state.gid = max([int(g.get("GroupID",0)) for g in st.session_state.grupos], default=0) + 1
        st.success("Dados carregados com sucesso! (itens + grupos)")
        st.rerun()
    except Exception as e:
        st.error("Falha ao carregar JSON. Verifique o arquivo.")
        st.code(repr(e))

# -------- Exportação visual (PDF/HTML) --------
def render_html_report(empresa: str, itens_df: pd.DataFrame, grupos_df: pd.DataFrame) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    style = """<style>
        /* Reset e variáveis */
        :root {
            --primary: #1e40af;
            --text: #0f172a;
            --muted: #64748b;
            --border: #e5e7eb;
            --background: #ffffff;
        }
        
        /* Layout base */
        body {
            font-family: system-ui, -apple-system, sans-serif;
            color: var(--text);
            line-height: 1.5;
            margin: 0;
            padding: 2rem;
            background: #f8fafc;
        }
        
        /* Cards modernos */
        .card {
            background: var(--background);
            border-radius: 1rem;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
            padding: 1.5rem;
            margin: 1rem 0;
        }
        
        /* Tabelas melhoradas */
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin: 1rem 0;
        }
        th, td {
            border: 1px solid var(--border);
            padding: 0.75rem;
            font-size: 0.875rem;
        }
        th {
            background: #f8fafc;
            font-weight: 600;
        }
        tr:nth-child(even) {
            background: #f8fafc;
        }
        
        /* Tags e badges */
        .tag {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
            background: #eef2ff;
            color: var(--primary);
        }
        
        /* Cabeçalhos */
        h1, h2, h3 {
            color: var(--primary);
            margin: 0 0 1rem;
        }
        
        /* Helper classes */
        .muted { color: var(--muted); }
        .right { text-align: right; }
        
        /* Print otimizado */
        @media print {
            body { padding: 0; }
            .card { box-shadow: none; border: 1px solid var(--border); }
        }
    </style>"""
    
    def fmt(v): return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    def itens_rows(df):
        if df.empty: return "<tr><td colspan='11' class='muted'>Nenhum débito adicionado.</td></tr>"
        out=[]
        for r in df.itertuples():
            out.append(f"<tr><td>{r.Exercicio}</td><td>{r.Natureza}</td><td>{r.Descricao}</td>"
                       f"<td class='right'>{fmt(r.Principal)}</td><td class='right'>{fmt(r.Encargos)}</td>"
                       f"<td class='right'>{fmt(r.Correcao)}</td><td class='right'>{fmt(r.ValorAtual)}</td>"
                       f"<td>{r.Opcao}</td><td class='right'>{fmt(r.ValorRefis)}</td>"
                       f"<td class='right'>{fmt(getattr(r,'PrimeiraParcela',0)) if r.Opcao=='Parcelado' else '—'}</td>"
                       f"<td class='right'>{fmt(getattr(r,'DemaisParcelas',0)) if r.Opcao=='Parcelado' else '—'}</td></tr>")
        return "".join(out)
    # Consolida grupos por OU -> {meta, avista, parcelado_best, group_ids, item_uids}
    def grupos_rows(gdf, idf):
        if gdf.empty:
            return "<tr><td colspan='12' class='muted'>Nenhum grupo salvo.</td></tr>"
        out = []
        for r in gdf.itertuples():
            keyg = getattr(r, "OUKeyGroup", "") or ""
            if not keyg:
                ids = list(getattr(r, "Itens", []) or [])
                itens_df = idf[idf["UID"].isin(ids)][["Descricao","Exercicio","Principal"]]
                keyg = ou_key_group(r.Empresa, r.Perfil, r.Natureza, itens_df) if not itens_df.empty else f"{r.Empresa}|{r.Perfil}|{r.Natureza}|[legacy]"
            entry = {"ID": int(getattr(r, "GroupID", 0)), "Natureza": r.Natureza, "Opção": getattr(r, "Opcao", ""), 
                      "Parcelas": int(getattr(r, "Parcelas", 1)), "Valor Atual": float(getattr(r, "ValorAtual", 0.0)),
                      "Base desc.": float(getattr(r, "BaseDesconto", 0.0)), "Desc. %": float(getattr(r, "DescontoPct", 0.0))*100,
                      "Desc. (R$)": float(getattr(r, "DescontoRS", 0.0)), "Valor REFIS": float(getattr(r, "ValorRefis", 0.0)),
                      "1ª parcela": float(getattr(r, "PrimeiraParcela", 0.0)), "Demais": float(getattr(r, "DemaisParcelas", 0.0)),
                      "Conjunto": keyg}
            out.append(entry)

        return "".join([f"<tr><td>{g['ID']}</td><td>{g['Natureza']}</td><td>{g['Opção']}</td><td>{g['Parcelas']}</td>"
                         f"<td class='right'>{fmt(g['Valor Atual'])}</td><td class='right'>{fmt(g['Base desc.'])}</td>"
                         f"<td class='right'>{int(round((g['Base desc.']/ (g['Valor Atual'] if g['Valor Atual'] else 1))*0,0)) if False else ''}</td>"
                         f"<td class='right'>{fmt(g['Desc. (R$)'])}</td><td class='right'>{fmt(g['Valor REFIS'])}</td>"
                         f"<td class='right'>{fmt(g['1ª parcela'])}</td><td class='right'>{fmt(g['Demais'])}</td>"
                         f"<td><small>{g['Conjunto'][-32:]}</small></td></tr>" for g in out])
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">{style}
    <title>Simulação REFIS — {empresa}</title></head><body>
    <h1>Simulação REFIS</h1><div class="muted">Empresa: <strong>{empresa}</strong> • Gerado em {now}</div>
    <div class="card"><h2>Débitos simulados <span class="tag">itens</span></h2>
      <table><thead><tr><th>Exercício</th><th>Natureza</th><th>Descrição</th><th>Tributo</th><th>Encargos</th><th>Correção</th><th>Valor Atual</th><th>Opção</th><th>Valor pelo REFIS</th><th>1ª parcela</th><th>Demais</th></tr></thead>
      <tbody>{itens_rows(itens_df)}</tbody></table></div>
    <div class="card"><h2>Negociações em Grupo <span class="tag">grupos</span></h2>
      <table><thead><tr><th>ID</th><th>Natureza</th><th>Opção</th><th>Parcelas</th><th>Valor Atual</th><th>Base desc.</th><th>Desc. %</th><th>Desc. (R$)</th><th>Valor REFIS</th><th>1ª parcela</th><th>Demais</th><th>Conjunto</th></tr></thead>
      <tbody>{grupos_rows(grupos_df, itens_df)}</tbody></table></div>
    <p class="muted">Observação: a “Correção” não integra a base de desconto. Consulte o edital/portal da Prefeitura para regras específicas.</p>
    </body></html>"""

st.markdown("### 📤 Exportar simulação (PDF/HTML)")
colx, _ = st.columns(2)
if colx.button("Gerar PDF/HTML p/ cliente", width="stretch"):
    itens_out, grupos_out = df.copy(), gr.copy()
    html = render_html_report(emp, itens_out, grupos_out)

    pdf_bytes = pdf_error = None
    if WEASYPRINT_OK:
        try: pdf_bytes = HTML(string=html, base_url=".").write_pdf()
        except Exception as e: pdf_error = repr(e); pdf_bytes = None

    if pdf_bytes:
        st.download_button("⬇️ Baixar PDF", data=pdf_bytes,
                           file_name=f"Simulacao_REFIS_{emp.replace(' ','_')}.pdf",
                           mime="application/pdf", width="stretch")
    else:
        if WEASYPRINT_OK and pdf_error:
            st.error("Falha ao gerar PDF com WeasyPrint:"); st.code(pdf_error, language="bash")
    st.download_button("⬇️ Baixar HTML (imprimir em PDF)", data=html.encode("utf-8"),
                       file_name=f"Simulacao_REFIS_{emp.replace(' ','_')}.html",
                       mime="text/html", width="stretch")

# -------- Armazenamento externo --------
st.markdown("## 💾 Armazenamento externo")
st.info("Salve seus dados periodicamente para evitar perda.")
c_s1, c_s2, c_s3 = st.columns(3)

bundle = {"version":"1.2","rows":st.session_state.rows,"grupos":st.session_state.grupos,
          "uid":st.session_state.uid,"gid":st.session_state.gid}
json_bytes = json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")
c_s1.download_button("⬇️ Salvar tudo (JSON)", data=json_bytes, file_name="refis_dados.json", mime="application/json", width="stretch")

csv_itens = df_all.to_csv(index=False).encode("utf-8")
csv_grupos = gr_all.to_csv(index=False).encode("utf-8")
c_s2.download_button("⬇️ Itens (CSV)", data=csv_itens, file_name="refis_itens.csv", mime="text/csv", width="stretch")
c_s3.download_button("⬇️ Grupos (CSV)", data=csv_grupos, file_name="refis_grupos.csv", mime="text/csv", width="stretch")

st.markdown("#### Carregar dados (JSON)")
up = st.file_uploader("Selecione um arquivo JSON exportado pelo simulador", type=["json"])
if up is not None:
    try:
        payload = json.loads(up.read().decode("utf-8"))
        rows_in   = payload.get("rows", [])
        grupos_in = payload.get("grupos", [])
        def normalize_rows(rows):
            out=[]
            for r in rows:
                rec = {c: r.get(c, pd.NA) for c in expected_cols}
                out.append(rec)
            return out
        st.session_state.rows   = normalize_rows(rows_in)
        def normalize_grupos(gs):
            out=[]
            for g in gs:
                base = dict(g)
                if "OUKeyGroup" not in base or not base["OUKeyGroup"]:
                    ids = base.get("Itens", []) or []
                    itens_df = pd.DataFrame(st.session_state.rows)
                    subset = itens_df[itens_df["UID"].isin(ids)][["Descricao","Exercicio","Principal"]].copy()
                    base["OUKeyGroup"] = ou_key_group(base["Empresa"], base["Perfil"], base["Natureza"], subset) if not subset.empty else f"{base.get('Empresa','')}|{base.get('Perfil','')}|{base.get('Natureza','')}|[legacy]"
                out.append(base)
            return out
        st.session_state.grupos = normalize_grupos(grupos_in)
        st.session_state.uid = max([int(r["UID"]) for r in st.session_state.rows if pd.notna(r["UID"])], default=0) + 1
        st.session_state.gid = max([int(g.get("GroupID",0)) for g in st.session_state.grupos], default=0) + 1
        st.success("Dados carregados com sucesso! (itens + grupos)")
        st.rerun()
    except Exception as e:
        st.error("Falha ao carregar JSON. Verifique o arquivo.")
        st.code(repr(e))
