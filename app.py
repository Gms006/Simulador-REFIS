# simulador_REFIS.py — Simulador REFIS (Anápolis)
# Versão compacta, sem perder funcionalidades
import streamlit as st, pandas as pd, json
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime

# ---------------- PDF (WeasyPrint opcional) ----------------
WEASYPRINT_OK = WEASYPRINT_VER = WEASYPRINT_ERR = ""
try:
    import weasyprint  # type: ignore
    from weasyprint import HTML  # type: ignore
    WEASYPRINT_OK = True
    WEASYPRINT_VER = getattr(weasyprint, "__version__", "")
except Exception as e:
    WEASYPRINT_OK = False
    WEASYPRINT_ERR = repr(e)

# ---------------- Config + Tema ----------------
st.set_page_config("Simulador REFIS – Anápolis", "💸", layout="wide")
st.markdown("""
<style>
:root{--primary:#1e40af;--secondary:#3b82f6;--success:#059669;--danger:#dc2626;--warning:#d97706;--bg:#f8fafc;}
.stApp{background:var(--bg)}
[data-testid="stVerticalBlock"]{background:#fff;padding:1rem;border-radius:.5rem;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:1rem}
.stButton>button{width:100%;border-radius:.375rem;transition:.2s}
.stButton>button:hover{transform:translateY(-1px)}
[data-testid="metric-container"]{padding:.5rem;border-radius:.375rem;background:#f1f5f9}
[data-testid="stDataFrame"] table{width:100%;border-collapse:separate;border-spacing:0;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden}
[data-testid="stDataFrame"] thead th{background:#f8fafc;padding:12px 16px;font-weight:600;color:#1e40af;border-bottom:2px solid #e2e8f0;white-space:nowrap}
[data-testid="stDataFrame"] tbody td{padding:12px 16px;border-bottom:1px solid #e2e8f0}
[data-testid="stDataFrame"] tbody tr:nth-child(even){background:#f8fafc}
.refis-card{background:#fff;padding:1.5rem;border-radius:12px;box-shadow:0 4px 6px -1px rgba(0,0,0,.1);margin-bottom:1rem;border:1px solid #e2e8f0}
.status-tag{display:inline-flex;align-items:center;padding:4px 12px;border-radius:9999px;font-size:12px;font-weight:500}
.status-success{background:#dcfce7;color:#059669}.status-warning{background:#fef3c7;color:#d97706}.status-info{background:#dbeafe;color:#2563eb}
.number-badge{background:#eef2ff;color:#1e40af;padding:2px 8px;border-radius:6px;font-weight:500}
</style>
""", unsafe_allow_html=True)

# ---------------- Helpers ----------------
brl = lambda v: (f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) if v is not None else "—"

def to_decimal(v) -> Decimal:
    if isinstance(v,(int,float)): s=str(v)
    elif isinstance(v,Decimal): return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else: s=str(v).strip().replace(".","").replace(",",".")
    return Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def currency_input(label:str, key:str, default:float=0.0, container=None) -> float:
    place = container if container is not None else st
    if key not in st.session_state:
        st.session_state[key] = f"{default:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    raw = place.text_input(label, value=st.session_state[key], key=f"{key}_raw")
    try:
        val = to_decimal(raw)
        st.session_state[key] = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return float(val)
    except (InvalidOperation, ValueError):
        place.warning(f"Valor inválido em “{label}”. Use apenas números.")
        return 0.0

def coerce_int64(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df

def stringify_mixed(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(lambda x: "—" if (pd.isna(x) or x=="—") else str(x))
    return df

def stringify_complex_objects_for_display(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype=="object":
            sample = df[c].dropna().head(20)
            if sample.apply(lambda x:isinstance(x,(list,dict,set,tuple))).any():
                df[c] = df[c].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x,(list,dict,set,tuple)) else ("" if pd.isna(x) else x))
    return df

def card_metric(title:str, value:str, tag:Tuple[str,str]|None=None):
    cols = st.columns([2,1])
    with cols[0]: st.metric(title, value)
    if tag:
        cls, txt = tag
        color = {"success":"status-success","warning":"status-warning","info":"status-info"}.get(cls,"status-info")
        with cols[1]:
            st.markdown(f"<span class='status-tag {color}'>{txt}</span>", unsafe_allow_html=True)

# ---------------- Regras REFIS ----------------
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
    if natureza in ("IPTU/Taxas de Imóveis/Propriedades","Taxa de Inscrição Municipal (CNPJ/CPF)"):
        if opcao=="À vista": return 1.00
        if 2<=parcelas<=6: return 0.95
        if 7<=parcelas<=20: return 0.90
        if 21<=parcelas<=40: return 0.80
        if 41<=parcelas<=60: return 0.70
        return 0.0
    if natureza=="ISSQN":
        if opcao=="À vista": return 1.00
        if 2<=parcelas<=6: return 0.90
        if 7<=parcelas<=16: return 0.80
        return 0.0
    if natureza in ["Multas formais/de ofício","Multas PROCON/Meio Ambiente/Posturas/Vig.Sanitária/Obras"]:
        return 0.50 if opcao=="À vista" else 0.0
    return 0.0

def parcela_minima(perfil): return 152.50 if perfil=="PF/MEI" else 457.50
def limites_parcelas(natureza):
    if natureza in ("IPTU/Taxas de Imóveis/Propriedades","Taxa de Inscrição Municipal (CNPJ/CPF)"): return (1,60)
    if natureza=="ISSQN": return (1,16)
    return (1,1)

def base_desconto(natureza, principal, encargos, correcao):
    if natureza in ["Multas formais/de ofício","Multas PROCON/Meio Ambiente/Posturas/Vig.Sanitária/Obras"]:
        return max(principal,0.0)+max(encargos,0.0)
    return max(encargos,0.0)

def ou_key_item(emp, perfil, natureza, desc, exerc, principal)->str:
    return f"{emp}|{perfil}|{natureza}|{desc}|{int(exerc)}|{float(principal):.2f}"

def item_signature(desc:str, exerc:int, principal:float)->str:
    return f"{int(exerc)}|{desc.strip()}|{float(principal):.2f}"

def ou_key_group(emp:str, perfil:str, natureza:str, itens_df:pd.DataFrame)->str:
    sigs = sorted(item_signature(r['Descricao'], int(r['Exercicio']), float(r['Principal'])) for _,r in itens_df.iterrows())
    return f"{emp}|{perfil}|{natureza}|[{';'.join(sigs)}]"

def calc_refis(perfil, natureza, opcao, parcelas, principal, encargos, correcao, entrada_tipo="none", entrada_val=0.0):
    pmin = parcela_minima(perfil)
    min_vista = 305 if perfil=="PF/MEI" else 915
    alerta = ""
    valor_atual = float(to_decimal(principal)+to_decimal(encargos)+to_decimal(correcao))
    if valor_atual < min_vista and opcao=="Parcelado": alerta="Somente à vista pelo valor mínimo"
    if natureza in ["Multas formais/de ofício","Multas PROCON/Meio Ambiente/Posturas/Vig.Sanitária/Obras"] and opcao=="Parcelado":
        alerta="Multas: somente à vista"
    minp,maxp = limites_parcelas(natureza)
    if opcao=="Parcelado" and not (minp<=parcelas<=maxp and parcelas>=2):
        if natureza=="ISSQN" and parcelas>16: alerta="ISSQN: máximo 16 parcelas"
        elif natureza in ("IPTU/Taxas de Imóveis/Propriedades","Taxa de Inscrição Municipal (CNPJ/CPF)") and parcelas>60: alerta="Taxas/IPTU: máximo 60 parcelas"
        elif parcelas<2: alerta="Mínimo de 2 parcelas"

    pct = desconto_percent(natureza, opcao, parcelas)
    base = float(to_decimal(base_desconto(natureza, principal, encargos, correcao)))
    desconto_rs = float(to_decimal(Decimal(str(base))*Decimal(str(pct))))
    valor_refis = float(to_decimal(Decimal(str(valor_atual)) - Decimal(str(desconto_rs))))

    entrada_abs = primeira = demais = valor_parcela = 0.0
    if opcao=="Parcelado" and parcelas>0:
        if entrada_tipo=="valor":
            entrada_abs = max(0.0, min(float(to_decimal(entrada_val)), valor_refis))
        elif entrada_tipo=="percent":
            p = max(0.0, min(100.0, float(entrada_val)))
            entrada_abs = float(to_decimal(Decimal(str(valor_refis))*Decimal(str(p/100.0))))
        if entrada_abs>0 and parcelas>=2:
            restante = float(to_decimal(Decimal(str(valor_refis)) - Decimal(str(entrada_abs))))
            demais = float(to_decimal(Decimal(str(restante))/Decimal(str(parcelas-1))))
            primeira = float(to_decimal(Decimal(str(entrada_abs))))
            if demais<pmin and not alerta: alerta="Parcela (exceto entrada) abaixo do mínimo"
            if primeira<pmin and not alerta: alerta="Entrada abaixo do mínimo"
        else:
            valor_parcela = float(to_decimal(Decimal(str(valor_refis))/Decimal(str(parcelas))))
            primeira = demais = valor_parcela
            if valor_parcela<pmin and not alerta: alerta="Parcela abaixo do mínimo"

    return dict(pmin=pmin, valor_atual=valor_atual, pct=pct, base=base, desconto_rs=desconto_rs,
                valor_refis=valor_refis, alerta=alerta, entrada_abs=entrada_abs,
                primeira=primeira, demais=demais, valor_parcela=valor_parcela)

# ---------------- Modelos ----------------
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
    return Item(uid, emp, perfil, desc, int(exerc), natureza, opcao, int(parcelas),
                float(to_decimal(principal)), float(to_decimal(encargos)), float(to_decimal(correcao)),
                r["valor_atual"], r["pct"], r["base"], r["desconto_rs"], r["valor_refis"], r["pmin"], r["alerta"], r["valor_parcela"],
                r["entrada_abs"], r["primeira"], r["demais"], ou_key_item(emp, perfil, natureza, desc, exerc, principal))

def simular_grupo(group_id, itens: List[Item], natureza, opcao, parcelas, entrada_tipo="none", entrada_val=0.0) -> Grupo:
    emp, perfil = itens[0].Empresa, itens[0].Perfil
    principal = float(sum(to_decimal(i.Principal) for i in itens))
    encargos  = float(sum(to_decimal(i.Encargos)  for i in itens))
    correcao  = float(sum(to_decimal(i.Correcao)  for i in itens))
    r = calc_refis(perfil, natureza, opcao, parcelas, principal, encargos, correcao, entrada_tipo, entrada_val)
    tmp_df = pd.DataFrame([{"Descricao":i.Descricao,"Exercicio":i.Exercicio,"Principal":i.Principal} for i in itens])
    keyg = ou_key_group(emp, perfil, natureza, tmp_df)
    return Grupo(group_id, emp, perfil, natureza, opcao, int(parcelas), [i.UID for i in itens],
                 principal, encargos, correcao, r["valor_atual"], r["pct"], r["base"], r["desconto_rs"],
                 r["valor_refis"], r["pmin"], r["alerta"], r["primeira"], r["demais"], keyg)

# ---------------- Estado + DF helpers ----------------
for k, v in dict(rows=[], uid=1, grupos=[], gid=1).items():
    st.session_state.setdefault(k, v)

EXPECTED = ["UID","Empresa","Perfil","Descricao","Exercicio","Natureza","Opcao","Parcelas","Principal","Encargos",
            "Correcao","ValorAtual","DescontoPct","BaseDesconto","DescontoRS","ValorRefis","ParcelaMinima",
            "EntradaValor","PrimeiraParcela","DemaisParcelas","ValorParcela","Alerta","OUKey"]

def build_dataframes(emp:str, view_mode:str) -> Tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    df_all = pd.DataFrame(st.session_state.rows) if st.session_state.rows else pd.DataFrame(columns=EXPECTED)
    for c in EXPECTED:
        if c not in df_all.columns: df_all[c] = pd.NA
    df_all = coerce_int64(df_all, ["UID","Exercicio","Parcelas"])
    for c in ["Principal","Encargos","Correcao","ValorAtual","BaseDesconto","DescontoRS","ValorRefis",
              "ParcelaMinima","ValorParcela","EntradaValor","PrimeiraParcela","DemaisParcelas","DescontoPct"]:
        if c in df_all.columns: df_all[c] = pd.to_numeric(df_all[c], errors="coerce")

    gr_all = pd.DataFrame(st.session_state.grupos)
    if not gr_all.empty:
        gr_all = coerce_int64(gr_all, ["GroupID","Parcelas"])
        for c in ["Principal","Encargos","Correcao","ValorAtual","BaseDesconto","DescontoRS","ValorRefis",
                  "ParcelaMinima","PrimeiraParcela","DemaisParcelas","DescontoPct"]:
            if c in gr_all.columns: gr_all[c] = pd.to_numeric(gr_all[c], errors="coerce")

    if view_mode=="Somente esta empresa":
        df = df_all[df_all["Empresa"]==emp].copy()
        gr = gr_all[gr_all["Empresa"]==emp].copy() if not gr_all.empty else pd.DataFrame()
    else:
        df, gr = df_all.copy(), gr_all.copy()

    return df_all, gr_all, df, gr

# ---------------- Sidebar ----------------
st.sidebar.header("Configuração")
emp = st.sidebar.text_input("Empresa", value=st.session_state.get("empresa_atual","EMPRESA EXEMPLO"))
st.session_state["empresa_atual"] = emp
perfil = st.sidebar.selectbox("Perfil", PERFIS, index=0)
view_mode = st.sidebar.radio("Visão", ["Somente esta empresa","Todas as empresas"], index=0)
st.sidebar.divider()
if st.sidebar.button("🧹 Limpar tudo", width="stretch"):
    st.session_state.update(rows=[], uid=1, grupos=[], gid=1)
    st.success("Estado limpo.")
    st.rerun()

df_all, gr_all, df, gr = build_dataframes(emp, view_mode)

# ---------------- Abas ----------------
tab_simulador, tab_grupos, tab_ou, tab_export = st.tabs(["Simulador","Grupos","Consolidações (OU)","Exportar/Salvar"])

# ================= Aba: Simulador =================
with tab_simulador:
    st.markdown("### Adicionar Débitos")
    with st.form("form_item"):
        c1,c2,c3 = st.columns([2,1,1])
        desc = c1.text_input("Descrição do débito", help="Identifique o débito de forma clara")
        exerc = c2.number_input("Exercício", 2000, 2100, 2022, 1)
        natureza = c3.selectbox("Natureza", NATUREZAS, index=4)

        c4,c5,c6 = st.columns([1,1,1])
        opcao = c4.radio("Opção", OPCOES, horizontal=True)
        minp,maxp = limites_parcelas(natureza)
        if opcao=="Parcelado":
            parcelas = c5.number_input("Nº de parcelas", 2, maxp, min(12,maxp), 1)
        else:
            parcelas = 1; c5.write("Nº de parcelas:\n\n— (à vista)")
        c6.write("Limites:"); c6.write(f"{minp}–{maxp}")

        v1,v2,v3 = st.columns(3)
        principal = currency_input("Principal / Tributo (R$)", "principal_in", 500.0, v1)
        encargos  = currency_input("Encargos (Multa + Juros) (R$)", "encargos_in", 120.0, v2)
        correcao  = currency_input("Correção (não entra no desconto) (R$)", "correcao_in", 20.0, v3)

        entrada_tipo, entrada_val = "none", 0.0
        if opcao=="Parcelado":
            st.markdown("**Entrada (opcional)**")
            if st.checkbox("Usar entrada", value=False):
                ge1, ge2 = st.columns([1,1])
                if ge1.radio("Tipo", ["Valor (R$)","Percentual (%)"], horizontal=True)=="Valor (R$)":
                    entrada_tipo="valor";  entrada_val = currency_input("Entrada (R$)", "entrada_val", 0.0, ge2)
                else:
                    entrada_tipo="percent"; entrada_val = ge2.number_input("Entrada (%)", 0.00, 100.00, 0.00, 0.01, format="%.2f")

        col_prev, col_add = st.columns(2)
        preview_btn = col_prev.form_submit_button("Atualizar prévia (Enter)", type="secondary", width="stretch")
        add_btn     = col_add.form_submit_button("➕ Adicionar débito", type="primary", width="stretch")

        if preview_btn or add_btn:
            preview = simular_item(0, emp, perfil, desc, exerc, natureza, opcao, int(parcelas),
                                   principal, encargos, correcao, entrada_tipo, entrada_val)
            st.divider()
            col1,col2,col3 = st.columns(3)
            with col1: card_metric("Valor Original + Encargos", brl(preview.ValorAtual), ("info","Valor base"))
            with col2:
                pct = preview.DescontoPct*100
                status = "success" if pct>=90 else "warning" if pct>=50 else "info"
                card_metric("Desconto Total", brl(preview.DescontoRS), (status, f"{pct:.0f}% sobre base"))
            with col3:
                economia = preview.ValorAtual - preview.ValorRefis
                card_metric("Valor Final REFIS", brl(preview.ValorRefis), ("success", f"Economia {brl(economia)}"))
            if preview.Alerta: st.error(preview.Alerta)

    if add_btn:
        item = simular_item(st.session_state.uid, emp, perfil, desc, exerc, natureza, opcao, int(parcelas),
                            principal, encargos, correcao, entrada_tipo, entrada_val)
        st.session_state.rows.append(asdict(item))
        st.session_state.uid += 1
        st.success("Débito adicionado!")
        st.rerun()

    # Tabela de itens + gerenciamento
    header = emp if view_mode=="Somente esta empresa" else "Todas as empresas"
    st.markdown(f"### 📄 Débitos adicionados – **{header}**")
    with st.expander("🗑️ Gerenciar débitos"):
        options_del = {int(r.UID): f"#{int(r.UID)} • [{int(r.Exercicio)}] {r.Descricao} ({r.Natureza}) • {r.Opcao} • Atual {brl(float(r.ValorAtual))}"
                       for r in df.itertuples()}
        sel_del = st.multiselect("Selecione débitos para excluir", options=list(options_del.keys()),
                                 format_func=lambda k: options_del[k])
        cA,cB,cC = st.columns(3)
        if cA.button("Excluir selecionados", width="stretch"):
            st.session_state.rows = [row for row in st.session_state.rows if not (row["Empresa"]==emp and int(row["UID"]) in set(sel_del))]
            st.rerun()
        if cB.button("🧹 Limpar tudo (todas empresas)", width="stretch"):
            st.session_state.update(rows=[], grupos=[], uid=1, gid=1); st.rerun()
        if cC.button("Começar em branco (apenas esta empresa)", width="stretch"):
            st.session_state.rows   = [r for r in st.session_state.rows   if r["Empresa"] != emp]
            st.session_state.grupos = [g for g in st.session_state.grupos if g["Empresa"] != emp]
            st.rerun()

    st.markdown("#### 📊 Resumo por opção")
    if not df.empty:
        resumo = df.groupby("Opcao").agg(Itens=("Opcao","count"),
                                         Valor_Atual=("ValorAtual","sum"),
                                         Desconto_RS=("DescontoRS","sum"),
                                         Valor_REFIS=("ValorRefis","sum")).reset_index()
        res_view = resumo.copy()
        for c in ["Valor_Atual","Desconto_RS","Valor_REFIS"]: res_view[c] = res_view[c].apply(brl)
        st.dataframe(res_view, hide_index=True, width="stretch")
    else:
        st.info("Adicione débitos para ver o resumo.")

# ================= Aba: Grupos =================
with tab_grupos:
    st.markdown("### 🤝 Negociação em Grupo (mesma Empresa + Natureza)")
    if df.empty:
        st.info("Adicione débitos na aba Simulador primeiro.")
    else:
        f_nat = st.selectbox("Natureza", df["Natureza"].unique().tolist(), index=0)
        subset = df[(df["Empresa"]==emp) & (df["Natureza"]==f_nat)]
        if subset.empty:
            st.warning("Não há débitos desta natureza para agrupar.")
        else:
            opts = {int(r.UID): f"[{int(r.Exercicio)}] {r.Descricao} — Atual {brl(float(r.ValorAtual))}" for r in subset.itertuples()}
            selected = st.multiselect("Selecione os débitos (anos) a negociar juntos", options=list(opts.keys()),
                                      format_func=lambda k: opts[k])
            if selected:
                g_opcao = st.radio("Opção do GRUPO", OPCOES, horizontal=True, key="grp_opt")
                _, g_maxp = limites_parcelas(f_nat)
                if g_opcao=="Parcelado":
                    g_parcelas = st.number_input("Nº de parcelas (grupo)", 2, g_maxp, min(12,g_maxp), 1, key="grp_parc")
                    st.markdown("**Entrada do grupo (opcional)**")
                    g_entrada_tipo, g_entrada_val = "none", 0.0
                    if st.checkbox("Usar entrada no grupo", value=False, key="grp_use_entry"):
                        ge1, ge2 = st.columns([1,1])
                        if ge1.radio("Tipo", ["Valor (R$)","Percentual (%)"], horizontal=True, key="grp_tipo")=="Valor (R$)":
                            g_entrada_tipo="valor";  g_entrada_val = currency_input("Entrada (R$)", "grp_ent_val", 0.0, ge2)
                        else:
                            g_entrada_tipo="percent"; g_entrada_val = ge2.number_input("Entrada (%)", 0.00, 100.00, 0.00, 0.01, format="%.2f", key="grp_ent_pct")
                else:
                    g_parcelas, g_entrada_tipo, g_entrada_val = 1, "none", 0.0

                perfis = subset[subset["UID"].isin(selected)]["Perfil"].unique().tolist()
                if len(perfis)>1:
                    st.error("Os itens selecionados possuem perfis diferentes (PF/MEI e PJ). Separe por perfil.")
                else:
                    chosen_df = subset[subset["UID"].isin(selected)].copy()
                    chosen = [Item(int(r["UID"]), r["Empresa"], r["Perfil"], r["Descricao"], int(r["Exercicio"]),
                                   r["Natureza"], r["Opcao"], int(r["Parcelas"]), float(r["Principal"]),
                                   float(r["Encargos"]), float(r["Correcao"]), float(r["ValorAtual"]),
                                   float(r["DescontoPct"]), float(r["BaseDesconto"]), float(r["DescontoRS"]),
                                   float(r["ValorRefis"]), float(r["ParcelaMinima"]), str(r["Alerta"]),
                                   float(r["ValorParcela"]), float(r.get("EntradaValor",0.0)),
                                   float(r.get("PrimeiraParcela",0.0)), float(r.get("DemaisParcelas",0.0)), r["OUKey"])
                              for _,r in chosen_df.iterrows()]
                    grp = simular_grupo(st.session_state.gid, chosen, f_nat, g_opcao, int(g_parcelas),
                                        entrada_tipo=g_entrada_tipo, entrada_val=g_entrada_val)

                    st.subheader("Resultado do Grupo")
                    g1,g2,g3,g4,g5 = st.columns(5)
                    g1.metric("Valor Atual (grupo)", brl(grp.ValorAtual))
                    g2.metric("Base de Desconto (grupo)", brl(grp.BaseDesconto))
                    g3.metric("Desconto %", f"{grp.DescontoPct:.0%}")
                    g4.metric("Desconto (R$)", brl(grp.DescontoRS))
                    g5.metric("Valor pelo REFIS (grupo)", brl(grp.ValorRefis))
                    if grp.Opcao=="Parcelado":
                        a,b = st.columns(2)
                        a.metric("1ª parcela (grupo)", brl(grp.PrimeiraParcela))
                        b.metric("Demais parcelas (grupo)", brl(grp.DemaisParcelas))
                    if grp.Alerta: st.error(grp.Alerta)

                    if st.button("💾 Salvar grupo de negociação", width="stretch"):
                        st.session_state.grupos.append(asdict(grp))
                        st.session_state.gid += 1
                        st.success("Grupo salvo!")
                        st.rerun()

    st.divider()
    st.markdown("#### Grupos salvos")
    gr_view = gr.copy()
    if gr_view.empty:
        st.info("Nenhum grupo salvo ainda nesta visão/empresa.")
    else:
        view = gr_view[["GroupID","Empresa","Perfil","Natureza","Opcao","Parcelas",
                        "Principal","Encargos","Correcao","ValorAtual","BaseDesconto",
                        "DescontoPct","DescontoRS","ValorRefis","ParcelaMinima",
                        "PrimeiraParcela","DemaisParcelas","Alerta"]].copy()
        for c in ["Principal","Encargos","Correcao","ValorAtual","BaseDesconto","DescontoRS","ValorRefis",
                  "ParcelaMinima","PrimeiraParcela","DemaisParcelas"]:
            view[c] = view[c].apply(brl)
        view["DescontoPct"] = (gr_view["DescontoPct"]*100).round(0).astype("Int64").astype(str) + "%"
        view = stringify_mixed(view, ["Parcelas"])
        st.dataframe(view, hide_index=True, width="stretch")

        st.markdown("#### 📊 Resumo (empresa atual)")
        r_emp = gr_view.groupby("Empresa").agg(
            Grupos=("GroupID","count"),
            Valor_Atual=("ValorAtual","sum"),
            Desconto_RS=("DescontoRS","sum"),
            Valor_REFIS=("ValorRefis","sum")
        ).reset_index()
        rv = r_emp.copy()
        for c in ["Valor_Atual","Desconto_RS","Valor_REFIS"]: rv[c] = rv[c].apply(brl)
        st.dataframe(rv, hide_index=True, width="stretch")

# ================= Aba: Consolidações (OU) =================
with tab_ou:
    st.markdown("## 🔀 Visão consolidada (OU) — Itens (mesmo débito)")
    if df.empty:
        st.info("Adicione débitos para ver a consolidação de itens.")
    else:
        ou_items: Dict[str, Dict[str, dict]] = {}
        for _, r in df.iterrows():
            key = ou_key_item(r["Empresa"], r["Perfil"], r["Natureza"], r["Descricao"], r["Exercicio"], r["Principal"])
            ou_items.setdefault(key, {"meta":{
                "Empresa":r["Empresa"],"Perfil":r["Perfil"],"Natureza":r["Natureza"],"Descricao":r["Descricao"],
                "Exercício":int(r["Exercicio"]),"Principal":float(r["Principal"]),
                "Encargos":float(r["Encargos"]),"Correcao":float(r["Correcao"])
            },"avista":None,"parcelado":None})
            pack = {"UID":int(r["UID"]),"ValorRefis":float(r["ValorRefis"]), "Parcelas":int(r["Parcelas"]),
                    "Primeira":float(r.get("PrimeiraParcela",0.0)), "Demais":float(r.get("DemaisParcelas",0.0))}
            t = "avista" if r["Opcao"]=="À vista" else "parcelado"
            best = ou_items[key][t]
            if (best is None) or (pack["ValorRefis"]<best["ValorRefis"]): ou_items[key][t] = pack

        rows_view=[]
        for data in ou_items.values():
            m,av,par = data["meta"], data["avista"], data["parcelado"]
            melhor = ("À vista" if av and (not par or av["ValorRefis"]<=par["ValorRefis"])
                      else (f"Parcelado ({par['Parcelas']}x)" if par else ""))
            rows_view.append({
                "Empresa":m["Empresa"],"Perfil":m["Perfil"],"Natureza":m["Natureza"],"Descrição":m["Descricao"],
                "Exercício":m["Exercício"],"Tributo":m["Principal"],"Encargos":m["Encargos"],"Correção":m["Correcao"],
                "Valor Atual":m["Principal"]+m["Encargos"]+m["Correcao"],
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
            view_df = stringify_mixed(view_df, ["Parcelas"])
            st.dataframe(view_df, hide_index=True, width="stretch")
        else:
            st.info("Ainda não há débitos para consolidar.")

    st.markdown("## 🔁 Visão consolidada (OU) — Grupos (mesmo conjunto de taxas)")
    if gr.empty:
        st.info("Salve pelo menos dois grupos (à vista e parcelado) com o mesmo conjunto de taxas para ver a consolidação.")
    else:
        ou_groups: Dict[str, Dict[str, dict]] = {}
        for _, r in gr.iterrows():
            keyg = r.get("OUKeyGroup","")
            if not keyg:
                ids = r.get("Itens",[]) or []
                itens_df = df[df["UID"].isin(ids)][["Descricao","Exercicio","Principal"]]
                keyg = ou_key_group(r["Empresa"], r["Perfil"], r["Natureza"], itens_df) if not itens_df.empty else f"{r['Empresa']}|{r['Perfil']}|{r['Natureza']}|[legacy]"
            meta = {"Empresa":r["Empresa"],"Perfil":r["Perfil"],"Natureza":r["Natureza"],"OUKeyGroup":keyg}
            ou_groups.setdefault(keyg, {"meta":meta,"avista":None,"parcelado":None})
            pack = {"GroupID":int(r["GroupID"]),"ValorRefis":float(r["ValorRefis"]), "Parcelas":int(r["Parcelas"]),
                    "Primeira":float(r.get("PrimeiraParcela",0.0)), "Demais":float(r.get("DemaisParcelas",0.0))}
            t = "avista" if r["Opcao"]=="À vista" else "parcelado"
            best = ou_groups[keyg][t]
            if (best is None) or (pack["ValorRefis"]<best["ValorRefis"]): ou_groups[keyg][t] = pack

        rows_g=[]
        for data in ou_groups.values():
            m,av,par = data["meta"], data["avista"], data["parcelado"]
            melhor = ("À vista" if av and (not par or av["ValorRefis"]<=par["ValorRefis"])
                      else (f"Parcelado ({par['Parcelas']}x)" if par else "—"))
            rows_g.append({
                "Empresa":m["Empresa"],"Perfil":m["Perfil"],"Natureza":m["Natureza"],
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
        vg = stringify_mixed(vg, ["Parcelas"])
        st.dataframe(stringify_complex_objects_for_display(vg), hide_index=True, width="stretch")

# ================= Aba: Exportar/Salvar =================
def render_html_report(empresa: str, itens_df: pd.DataFrame, grupos_df: pd.DataFrame) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    style = """<style>
    :root{--primary:#1e40af;--text:#0f172a;--muted:#64748b;--border:#e5e7eb;--bg:#ffffff}
    body{font-family:system-ui,-apple-system,sans-serif;color:var(--text);line-height:1.5;margin:0;padding:2rem;background:#f8fafc}
    .card{background:var(--bg);border-radius:1rem;box-shadow:0 4px 6px -1px rgba(0,0,0,.1);padding:1.5rem;margin:1rem 0}
    table{width:100%;border-collapse:separate;border-spacing:0;margin:1rem 0}
    th,td{border:1px solid var(--border);padding:.75rem;font-size:.875rem}
    th{background:#f8fafc;font-weight:600} tr:nth-child(even){background:#f8fafc}
    .tag{display:inline-block;padding:.25rem .75rem;border-radius:9999px;font-size:.75rem;font-weight:500;background:#eef2ff;color:var(--primary)}
    h1,h2,h3{color:var(--primary);margin:0 0 1rem}.muted{color:var(--muted)}.right{text-align:right}
    @media print{body{padding:0}.card{box-shadow:none;border:1px solid var(--border)}}
    </style>"""
    fmt = lambda v: f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X",".")
    def itens_rows(df):
        if df.empty: return "<tr><td colspan='11' class='muted'>Nenhum débito adicionado.</td></tr>"
        out=[]
        for r in df.itertuples():
            out.append(
              f"<tr><td>{r.Exercicio}</td><td>{r.Natureza}</td><td>{r.Descricao}</td>"
              f"<td class='right'>{fmt(r.Principal)}</td><td class='right'>{fmt(r.Encargos)}</td>"
              f"<td class='right'>{fmt(r.Correcao)}</td><td class='right'>{fmt(r.ValorAtual)}</td>"
              f"<td>{r.Opcao}</td><td class='right'>{fmt(r.ValorRefis)}</td>"
              f"<td class='right'>{fmt(getattr(r,'PrimeiraParcela',0)) if r.Opcao=='Parcelado' else '—'}</td>"
              f"<td class='right'>{fmt(getattr(r,'DemaisParcelas',0)) if r.Opcao=='Parcelado' else '—'}</td></tr>")
        return "".join(out)
    def grupos_rows(gdf, idf):
        if gdf.empty:
            return "<tr><td colspan='12' class='muted'>Nenhum grupo salvo.</td></tr>"

        def normalize_key(row):
            key = getattr(row, "OUKeyGroup", "") or ""
            if not key:
                ids = list(getattr(row, "Itens", []) or [])
                itens_df = idf[idf["UID"].isin(ids)][["Descricao", "Exercicio", "Principal"]]
                key = ou_key_group(row.Empresa, row.Perfil, row.Natureza, itens_df) if not itens_df.empty else f"{row.Empresa}|{row.Perfil}|{row.Natureza}|[legacy]"
            return key

        def fmt_opt(v):
            return fmt(v) if v is not None and not (isinstance(v, float) and not pd.notna(v)) else "—"

        ou_map: Dict[str, Dict[str, dict]] = {}
        for r in gdf.itertuples():
            key = normalize_key(r)
            meta = {"Empresa": r.Empresa, "Perfil": r.Perfil, "Natureza": r.Natureza, "Key": key}
            ou_map.setdefault(key, {"meta": meta, "avista": None, "parcelado": None})
            raw_gid = getattr(r, "GroupID", pd.NA)
            raw_valor = getattr(r, "ValorRefis", pd.NA)
            raw_parcelas = getattr(r, "Parcelas", pd.NA)
            raw_primeira = getattr(r, "PrimeiraParcela", pd.NA)
            raw_demais = getattr(r, "DemaisParcelas", pd.NA)

            valor_refis = float(raw_valor) if pd.notna(raw_valor) else None
            pack = {
                "GroupID": int(raw_gid) if pd.notna(raw_gid) else None,
                "ValorRefis": valor_refis,
                "_cmp": valor_refis if valor_refis is not None else float("inf"),
                "Parcelas": int(raw_parcelas) if pd.notna(raw_parcelas) else 0,
                "Primeira": float(raw_primeira) if pd.notna(raw_primeira) else None,
                "Demais": float(raw_demais) if pd.notna(raw_demais) else None,
            }
            opt = "avista" if getattr(r, "Opcao", "") == "À vista" else "parcelado"
            best = ou_map[key][opt]
            if (best is None) or (pack["_cmp"] < best.get("_cmp", float("inf"))):
                ou_map[key][opt] = pack

        rows = []
        for data in ou_map.values():
            meta, av, par = data["meta"], data["avista"], data["parcelado"]
            if av is None and par is None:
                continue
            melhor = "—"
            if av and (not par or av.get("_cmp", float("inf")) <= par.get("_cmp", float("inf"))):
                melhor = f"À vista (Grupo #{av['GroupID']})" if av.get("GroupID") else "À vista"
            elif par:
                label_parc = f"Parcelado ({par['Parcelas']}x)" if par.get("Parcelas") else "Parcelado"
                melhor = f"{label_parc} (Grupo #{par['GroupID']})" if par.get("GroupID") else label_parc

            rows.append({
                "Empresa": meta["Empresa"],
                "Perfil": meta["Perfil"],
                "Natureza": meta["Natureza"],
                "Conjunto": meta["Key"][-32:] if len(meta["Key"]) > 32 else meta["Key"],
                "GrupoAvista": av.get("GroupID") if av and av.get("GroupID") is not None else "—",
                "ValorAvista": fmt_opt(av["ValorRefis"]) if av else "—",
                "GrupoParcelado": par.get("GroupID") if par and par.get("GroupID") is not None else "—",
                "ValorParcelado": fmt_opt(par["ValorRefis"]) if par else "—",
                "Parcelas": str(par["Parcelas"]) if par and par.get("Parcelas") else "—",
                "Primeira": fmt_opt(par["Primeira"]) if par and par["Primeira"] is not None else "—",
                "Demais": fmt_opt(par["Demais"]) if par and par["Demais"] is not None else "—",
                "Melhor": melhor
            })

        if not rows:
            return "<tr><td colspan='12' class='muted'>Nenhum grupo salvo.</td></tr>"

        return "".join([
            f"<tr><td>{g['Empresa']}</td><td>{g['Perfil']}</td><td>{g['Natureza']}</td>"
            f"<td>{g['Conjunto']}</td><td>{g['GrupoAvista']}</td><td class='right'>{g['ValorAvista']}</td>"
            f"<td>{g['GrupoParcelado']}</td><td class='right'>{g['ValorParcelado']}</td>"
            f"<td>{g['Parcelas']}</td><td class='right'>{g['Primeira']}</td><td class='right'>{g['Demais']}</td>"
            f"<td>{g['Melhor']}</td></tr>"
            for g in rows
        ])
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">{style}
<title>Simulação REFIS — {empresa}</title></head><body>
<h1>Simulação REFIS</h1><div class="muted">Empresa: <strong>{empresa}</strong> • Gerado em {now}</div>
<div class="card"><h2>Débitos simulados <span class="tag">itens</span></h2>
<table><thead><tr><th>Exercício</th><th>Natureza</th><th>Descrição</th><th>Tributo</th><th>Encargos</th><th>Correção</th><th>Valor Atual</th><th>Opção</th><th>Valor pelo REFIS</th><th>1ª parcela</th><th>Demais</th></tr></thead>
<tbody>{itens_rows(itens_df)}</tbody></table></div>
<div class="card"><h2>Negociações em Grupo <span class="tag">grupos — melhor cenário (OU)</span></h2>
<table><thead><tr><th>Empresa</th><th>Perfil</th><th>Natureza</th><th>Conjunto</th><th>Grupo à vista</th><th>À vista (R$)</th><th>Grupo parcelado</th><th>Parcelado (R$)</th><th>Parcelas</th><th>1ª parcela</th><th>Demais</th><th>Melhor opção</th></tr></thead>
<tbody>{grupos_rows(grupos_df, itens_df)}</tbody></table></div>
<p class="muted">Observação: a “Correção” não integra a base de desconto. Consulte o edital/portal da Prefeitura para regras específicas.</p>
</body></html>"""

with tab_export:
    st.markdown("### 📤 Exportar simulação (PDF/HTML)")
    colx,_ = st.columns(2)
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

    st.divider()
    st.markdown("### 💾 Salvar/Carregar dados")
    bundle = {"version":"1.2","rows":st.session_state.rows,"grupos":st.session_state.grupos,
              "uid":st.session_state.uid,"gid":st.session_state.gid}
    st.download_button("⬇️ Salvar tudo (JSON)", data=json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8"),
                       file_name="refis_dados.json", mime="application/json", width="stretch")
    c1,c2 = st.columns(2)
    c1.download_button("⬇️ Itens (CSV)", data=df_all.to_csv(index=False).encode("utf-8"),
                       file_name="refis_itens.csv", mime="text/csv", width="stretch")
    c2.download_button("⬇️ Grupos (CSV)", data=gr_all.to_csv(index=False).encode("utf-8"),
                       file_name="refis_grupos.csv", mime="text/csv", width="stretch")

    up = st.file_uploader("Carregar dados (JSON exportado pelo simulador)", type=["json"])
    if up is not None:
        try:
            payload = json.loads(up.read().decode("utf-8"))
            rows_in   = payload.get("rows", [])
            grupos_in = payload.get("grupos", [])
            def normalize_rows(rows):
                return [{c: r.get(c, pd.NA) for c in EXPECTED} for r in rows]
            st.session_state.rows = normalize_rows(rows_in)
            def normalize_grupos(gs):
                out=[]
                for g in gs:
                    base = dict(g)
                    if not base.get("OUKeyGroup"):
                        ids = base.get("Itens", []) or []
                        itens_df = pd.DataFrame(st.session_state.rows)
                        subset = itens_df[itens_df["UID"].isin(ids)][["Descricao","Exercicio","Principal"]].copy()
                        base["OUKeyGroup"] = ou_key_group(base.get("Empresa",""), base.get("Perfil",""), base.get("Natureza",""), subset) if not subset.empty else f"{base.get('Empresa','')}|{base.get('Perfil','')}|{base.get('Natureza','')}|[legacy]"
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
