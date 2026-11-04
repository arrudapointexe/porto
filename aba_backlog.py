"""
Aba "📊 Status por Backlog" — módulo compartilhado entre monitor_expedicao.py e monitor_itr.py.

Cruza o tempo parado na base (coluna 'Backlog time(Station)', com fallback para 'aging')
com a etapa atual do pacote (Last scan type), ocorrências (Last Problem Reason),
tentativas de entrega (OFD Count), equipe (LOC/INT) e valor declarado.
"""
import io
import re
import urllib.parse
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# DICIONÁRIOS / CONSTANTES
# ==========================================
ETAPA_ROTA = "🚚 Em Rota"

MAPA_ETAPA = {
    "OUT FOR DELIVERY": ETAPA_ROTA,
    "INVENTORY SCAN": "📋 Inventariado (Piso)",
    "CONSOLIDATE(BAG)": "🎒 Consolidado (Saca)",
    "OFFLOADING": "📤 Descarregado",
    "ARRIVE": "📥 Chegada na Base",
    "RECEIVE": "📦 Recebido",
    "RETURN": "↩️ Devolução",
}

CORES_ETAPA = {
    ETAPA_ROTA: "#38bdf8",
    "📋 Inventariado (Piso)": "#f97316",
    "🎒 Consolidado (Saca)": "#a855f7",
    "📤 Descarregado": "#eab308",
    "📥 Chegada na Base": "#22c55e",
    "📦 Recebido": "#14b8a6",
    "↩️ Devolução": "#ef4444",
    "❔ Sem Scan": "#64748b",
}

# (rótulo, mínimo, máximo, cor)
FAIXAS = [
    ("🟢 0–1 dia", 0, 1, "#22c55e"),
    ("🟡 2 dias", 2, 2, "#eab308"),
    ("🟠 3 dias", 3, 3, "#f97316"),
    ("🔴 4–5 dias", 4, 5, "#ef4444"),
    ("🟣 6–10 dias", 6, 10, "#a855f7"),
    ("⚫ +10 dias", 11, 10 ** 9, "#64748b"),
]
ORDEM_FAIXAS = [f[0] for f in FAIXAS]
CORES_FAIXA = {f[0]: f[3] for f in FAIXAS}
LIMIAR_CRITICO = 4  # dias

SEM_OCORRENCIA = "Sem ocorrência"

MAPA_MOTIVO = {
    "not arrived": "Não chegou fisicamente",
    "unprepared package": "Pacote não preparado (FM)",
    "client cannot be contacted": "Cliente sem contato",
    "change of delivery time": "Reagendado (horário)",
    "local fechado": "Local fechado",
    "arrived at the wrong station": "Chegou na base errada",
    "refuse to accept": "Recusado pelo cliente",
    "change of pick-up time": "Coleta reagendada",
    "fm/wrong address": "Endereço errado (FM)",
    "logistics partial pick up due to capacity": "Coleta parcial (capacidade)",
    "change of delivery address": "Mudança de endereço",
    "client absent": "Cliente ausente",
    "wrong address(insufficient address details)": "Endereço insuficiente",
    "multiple waybills": "Múltiplas waybills",
}

MAPA_TIPO_PROBLEMA = {
    "first mile": "First Mile (coleta)",
    "a parcel that has been sent but not received.": "Enviado e não recebido",
    "undelivered": "Não entregue",
    "reschedule": "Reagendamento",
    "operation": "Operacional",
    "other": "Outros",
}


# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
def _txt(v):
    s = str(v).strip() if v is not None else ""
    return "" if s.lower() in ("nan", "none", "nat") else s


def _faixa(dias):
    for rot, mn, mx, _ in FAIXAS:
        if mn <= dias <= mx:
            return rot
    return ORDEM_FAIXAS[-1]


def _brl(v):
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _num(serie):
    return pd.to_numeric(serie.astype(str).str.replace(",", ".", regex=False).str.strip(), errors="coerce")


def _traduzir(valor, mapa, vazio):
    s = _txt(valor)
    if not s:
        return vazio
    return mapa.get(s.lower(), s)


def _acao_sugerida(row):
    motivo = row["_motivo_raw"].lower()
    tipo = row["_tipo_raw"].lower()
    bk = row["Backlog_Dias"]
    em_rota = row["Etapa"] == ETAPA_ROTA

    if bk >= 6:
        return "🚨 Escalar (backlog crítico)"
    if "not arrived" in motivo or "sent but not received" in tipo:
        return "🔎 Acarear / localizar físico"
    if "wrong station" in motivo:
        return "🔀 Transferir p/ base correta"
    if "contacted" in motivo or "absent" in motivo:
        return "📱 Fazer ativo com cliente"
    if "address" in motivo:
        return "📍 Validar endereço"
    if "refuse" in motivo:
        return "↩️ Tratar recusa / devolução"
    if row["Fora_Rota"]:
        return "🧭 Fora de abrangência"
    if row["Tentativas"] >= 2:
        return "🔁 Reincidente — priorizar"
    if em_rota and bk >= 2:
        return "📞 Cobrar baixa do motorista"
    if not em_rota and bk >= 2:
        return "🚚 Priorizar roteirização"
    if "unprepared" in motivo:
        return "📦 Aguardando preparo (FM)"
    return "✅ Acompanhar"


def _equipe(row):
    reg = _txt(row.get("Regiao_Motorista", ""))
    if reg:
        return reg
    nome = _txt(row.get("Driver Name", "")).upper()
    if re.search(r"\bINT\b", nome):
        return "INT"
    if re.search(r"\bLOC\b", nome):
        return "LOC"
    tipo_loc = _txt(row.get("Tipo_Localidade", ""))
    if "Interior" in tipo_loc:
        return "INT"
    if tipo_loc:
        return "LOC"
    return "—"


def preparar_backlog(df_in):
    """Enriquece o dataframe com as colunas usadas na aba de backlog."""
    d = df_in.copy()

    if "Backlog time(Station)" in d.columns:
        bk = _num(d["Backlog time(Station)"])
    else:
        bk = pd.Series(float("nan"), index=d.index)
    ag = _num(d["aging"]) if "aging" in d.columns else pd.Series(0, index=d.index)
    d["Backlog_Dias"] = bk.fillna(ag).fillna(0).clip(lower=0).astype(int)
    d["Faixa_Backlog"] = d["Backlog_Dias"].apply(_faixa)

    scan = d["Last scan type"] if "Last scan type" in d.columns else pd.Series("", index=d.index)
    d["Etapa"] = scan.apply(lambda s: MAPA_ETAPA.get(_txt(s).upper(), _txt(s) or "❔ Sem Scan"))

    d["_motivo_raw"] = d["Last Problem Reason"].apply(_txt) if "Last Problem Reason" in d.columns else ""
    d["_tipo_raw"] = d["Last Problem Type"].apply(_txt) if "Last Problem Type" in d.columns else ""
    d["Ocorrencia"] = d["_motivo_raw"].apply(lambda v: _traduzir(v, MAPA_MOTIVO, SEM_OCORRENCIA))
    d["Tipo_Ocorrencia"] = d["_tipo_raw"].apply(lambda v: _traduzir(v, MAPA_TIPO_PROBLEMA, "—"))
    d["Tem_Ocorrencia"] = d["Ocorrencia"] != SEM_OCORRENCIA

    d["Tentativas"] = _num(d["OFD Count"]).fillna(0).astype(int) if "OFD Count" in d.columns else 0
    d["Valor_Declarado"] = _num(d["Uploaded Declared Value"]).fillna(0.0) if "Uploaded Declared Value" in d.columns else 0.0

    if "abrangencia" in d.columns:
        d["Fora_Rota"] = d["abrangencia"].astype(str).str.strip().isin(["0", "0.0"])
    else:
        d["Fora_Rota"] = False

    d["Equipe"] = d.apply(_equipe, axis=1)

    if "Motorista_Limpo" not in d.columns:
        d["Motorista_Limpo"] = "Não Atribuído"
    if "Destination City" not in d.columns:
        d["Destination City"] = ""
    if "Bairro_Display" not in d.columns:
        d["Bairro_Display"] = ""
    if "is_rota" not in d.columns:
        d["is_rota"] = d["Etapa"] == ETAPA_ROTA

    d["Acao_Sugerida"] = d.apply(_acao_sugerida, axis=1)
    d["Prioridade"] = (
        d["Backlog_Dias"] * 10
        + d["Tem_Ocorrencia"].astype(int) * 5
        + d["Tentativas"] * 3
        + d["Fora_Rota"].astype(int) * 2
    )
    d["Waybill No"] = d["Waybill No"].astype(str) if "Waybill No" in d.columns else ""
    return d


def _layout(fig, altura):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=30, b=10, l=10, r=10),
        height=altura,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
    )
    return fig


def _card(col, label, valor, sub, cor="text-sky"):
    col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label" style="font-size: 0.8rem;">{label}</div>
            <div class="metric-value {cor}" style="font-size: 1.8rem;">{valor}</div>
            <div class="metric-sub">{sub}</div>
        </div>
    """, unsafe_allow_html=True)


def _excel_bytes(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Backlog")
    return out.getvalue()


# ==========================================
# TEXTO PARA O GRUPO DO WHATSAPP
# ==========================================
def gerar_texto_backlog_whatsapp(dfv, contexto, formato="resumo", top_n=10):
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    total = len(dfv)
    medio = dfv["Backlog_Dias"].mean() if total else 0
    criticos = int((dfv["Backlog_Dias"] >= LIMIAR_CRITICO).sum())
    com_oc = int(dfv["Tem_Ocorrencia"].sum())
    titulo = contexto if contexto else "Todas as Bases"

    linhas = [
        f"📊 *STATUS DO BACKLOG — {titulo.upper()}*",
        f"🗓️ _Atualizado em {agora}_",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📦 *Total em backlog:* {total} pacotes",
        f"⏱️ *Backlog médio:* {medio:.1f} dias",
        f"🔴 *Críticos (≥ {LIMIAR_CRITICO} dias):* {criticos}",
        f"⚠️ *Com ocorrência:* {com_oc}",
        "",
        "*⏳ Por faixa de backlog:*",
    ]
    cont_faixa = dfv["Faixa_Backlog"].value_counts()
    for fx in ORDEM_FAIXAS:
        q = int(cont_faixa.get(fx, 0))
        if q:
            linhas.append(f"{fx}: *{q}*")

    linhas += ["", "*🔄 Por etapa:*"]
    for etapa, q in dfv["Etapa"].value_counts().items():
        crit_e = int(((dfv["Etapa"] == etapa) & (dfv["Backlog_Dias"] >= LIMIAR_CRITICO)).sum())
        extra = f" (🔴 {crit_e} críticos)" if crit_e else ""
        linhas.append(f"{etapa}: *{q}*{extra}")

    ocs = dfv[dfv["Tem_Ocorrencia"]]["Ocorrencia"].value_counts().head(5)
    if not ocs.empty:
        linhas += ["", "*⚠️ Principais ocorrências:*"]
        for oc, q in ocs.items():
            linhas.append(f"• {oc}: *{q}*")

    if formato == "criticos":
        top = dfv.sort_values(["Prioridade", "Backlog_Dias"], ascending=False).head(top_n)
        if not top.empty:
            linhas += ["", f"*🚨 TOP {len(top)} PRIORIDADES:*"]
            for _, r in top.iterrows():
                local = _txt(r.get("Destination City", ""))
                bairro = _txt(r.get("Bairro_Display", ""))
                local_str = f"{local} - {bairro}" if bairro and bairro != local else local
                mot = _txt(r.get("Motorista_Limpo", ""))
                mot_str = f" | 👤 {mot}" if mot and mot != "Não Atribuído" else ""
                oc_str = f" | ⚠️ {r['Ocorrencia']}" if r["Tem_Ocorrencia"] else ""
                linhas.append(
                    f"▪️ *{r['Waybill No']}* | {r['Backlog_Dias']}d | {r['Etapa']}{mot_str}"
                    f" | 📍 {local_str}{oc_str}"
                )

    elif formato == "motorista":
        df_r = dfv[dfv["is_rota"]]
        if not df_r.empty:
            linhas += ["", "*👨‍✈️ BACKLOG EM ROTA POR MOTORISTA:*"]
            grp = df_r.groupby("Motorista_Limpo").agg(
                Qtd=("Waybill No", "count"),
                Medio=("Backlog_Dias", "mean"),
                Max=("Backlog_Dias", "max"),
                Crit=("Backlog_Dias", lambda s: int((s >= LIMIAR_CRITICO).sum())),
            ).sort_values(["Crit", "Max", "Qtd"], ascending=False)
            for mot, r in grp.iterrows():
                ic = "🔴" if r["Crit"] else ("🟠" if r["Max"] >= 2 else "🟢")
                crit_str = f" | 🔴 {int(r['Crit'])} crít." if r["Crit"] else ""
                linhas.append(
                    f"{ic} *{mot}* — {int(r['Qtd'])} pct | médio {r['Medio']:.1f}d | máx {int(r['Max'])}d{crit_str}"
                )
        else:
            linhas += ["", "_Nenhum pacote em rota no filtro atual._"]

    elif formato == "cidade":
        linhas += ["", "*🏘️ BACKLOG POR CIDADE:*"]
        grp = dfv.groupby("Destination City").agg(
            Qtd=("Waybill No", "count"),
            Piso=("is_rota", lambda s: int((~s.astype(bool)).sum())),
            Max=("Backlog_Dias", "max"),
            Crit=("Backlog_Dias", lambda s: int((s >= LIMIAR_CRITICO).sum())),
        ).sort_values(["Qtd"], ascending=False)
        restantes = max(0, len(grp) - 15)
        for cid, r in grp.head(15).iterrows():
            ic = "🔴" if r["Crit"] else "▪️"
            crit_str = f" | 🔴 {int(r['Crit'])} crít." if r["Crit"] else ""
            piso_str = f" (🏢 {int(r['Piso'])} no piso)" if r["Piso"] else ""
            linhas.append(
                f"{ic} *{_txt(cid) or 'Sem cidade'}* — {int(r['Qtd'])} pct{piso_str} | máx {int(r['Max'])}d{crit_str}"
            )
        if restantes:
            linhas.append(f"_... e mais {restantes} cidades com menor volume._")

    linhas += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ *Favor priorizar os pacotes com maior tempo de backlog!*",
    ]
    return "\n".join(linhas)


# ==========================================
# RENDERIZAÇÃO DA ABA
# ==========================================
def render_aba_backlog(df_base, contexto="", key_prefix="bk"):
    k = lambda nome: f"{key_prefix}_{nome}"

    if df_base is None or df_base.empty:
        st.success("🎉 Nenhum pacote em backlog para o filtro selecionado!")
        return

    df = preparar_backlog(df_base)

    st.markdown("#### 📊 Status por Backlog")
    st.caption(
        "Tempo que cada pacote está parado na base (*Backlog time Station*), cruzado com etapa atual, "
        "ocorrências, tentativas de entrega e equipe. Use os filtros para focar no que precisa de ação."
    )

    # ---------------- FILTROS ----------------
    with st.expander("🎛️ Filtros do Backlog", expanded=True):
        multi_base = "Base" in df.columns and df["Base"].nunique() > 1
        if multi_base:
            fc0, fc1, fc2, fc3 = st.columns([2, 3, 3, 2])
            with fc0:
                f_bases = st.multiselect("🏢 Base:", sorted(df["Base"].dropna().unique().tolist()), key=k("f_base"))
        else:
            fc1, fc2, fc3 = st.columns([3, 3, 2])
            f_bases = []

        with fc1:
            etapas_disp = df["Etapa"].value_counts().index.tolist()
            f_etapas = st.multiselect("🔄 Etapa (vazio = todas):", etapas_disp, key=k("f_etapa"))
        with fc2:
            faixas_disp = [f for f in ORDEM_FAIXAS if f in set(df["Faixa_Backlog"])]
            f_faixas = st.multiselect("⏳ Faixa de backlog (vazio = todas):", faixas_disp, key=k("f_faixa"))
        with fc3:
            f_visao = st.selectbox("👁️ Visão:", ["Tudo", "🏢 Só Piso", "🚚 Só Em Rota"], key=k("f_visao"))

        fd1, fd2, fd3, fd4 = st.columns([3, 2, 2, 3])
        with fd1:
            ocs_disp = df["Ocorrencia"].value_counts().index.tolist()
            f_ocs = st.multiselect("⚠️ Ocorrência (vazio = todas):", ocs_disp, key=k("f_oc"))
        with fd2:
            equipes_disp = ["Todas"] + sorted([e for e in df["Equipe"].unique().tolist() if e])
            f_equipe = st.selectbox("👥 Equipe:", equipes_disp, key=k("f_equipe"))
        with fd3:
            f_min = st.number_input("⏱️ Backlog mínimo (dias):", min_value=0, value=0, step=1, key=k("f_min"))
        with fd4:
            f_busca = st.text_input("🔎 Buscar (AWB, motorista, cidade, bairro):", key=k("f_busca"),
                                    placeholder="Ex: 6102..., Centro, João...")

        fe1, fe2, fe3, fe4 = st.columns(4)
        with fe1:
            f_so_oc = st.checkbox("Somente com ocorrência", key=k("f_so_oc"))
        with fe2:
            f_reinc = st.checkbox("Somente reincidentes (≥ 2 tentativas)", key=k("f_reinc"))
        with fe3:
            f_fora = st.checkbox("Somente fora de abrangência", key=k("f_fora"))
        with fe4:
            f_crit = st.checkbox(f"Somente críticos (≥ {LIMIAR_CRITICO} dias)", key=k("f_crit"))

    dfv = df.copy()
    if f_bases:
        dfv = dfv[dfv["Base"].isin(f_bases)]
    if f_etapas:
        dfv = dfv[dfv["Etapa"].isin(f_etapas)]
    if f_faixas:
        dfv = dfv[dfv["Faixa_Backlog"].isin(f_faixas)]
    if f_visao == "🏢 Só Piso":
        dfv = dfv[~dfv["is_rota"].astype(bool)]
    elif f_visao == "🚚 Só Em Rota":
        dfv = dfv[dfv["is_rota"].astype(bool)]
    if f_ocs:
        dfv = dfv[dfv["Ocorrencia"].isin(f_ocs)]
    if f_equipe != "Todas":
        dfv = dfv[dfv["Equipe"] == f_equipe]
    if f_min:
        dfv = dfv[dfv["Backlog_Dias"] >= f_min]
    if f_so_oc:
        dfv = dfv[dfv["Tem_Ocorrencia"]]
    if f_reinc:
        dfv = dfv[dfv["Tentativas"] >= 2]
    if f_fora:
        dfv = dfv[dfv["Fora_Rota"]]
    if f_crit:
        dfv = dfv[dfv["Backlog_Dias"] >= LIMIAR_CRITICO]
    if f_busca:
        termo = f_busca.strip().lower()
        cond = pd.Series(False, index=dfv.index)
        for col in ["Waybill No", "Motorista_Limpo", "Destination City", "Bairro_Display", "Endereco_Display"]:
            if col in dfv.columns:
                cond |= dfv[col].astype(str).str.lower().str.contains(termo, na=False, regex=False)
        dfv = dfv[cond]

    if dfv.empty:
        st.info("Nenhum pacote encontrado com os filtros selecionados.")
        return

    # ---------------- KPIs ----------------
    total_geral = len(df)
    total = len(dfv)
    medio = dfv["Backlog_Dias"].mean()
    mediana = dfv["Backlog_Dias"].median()
    criticos = int((dfv["Backlog_Dias"] >= LIMIAR_CRITICO).sum())
    com_oc = int(dfv["Tem_Ocorrencia"].sum())
    reinc = int((dfv["Tentativas"] >= 2).sum())
    valor = dfv["Valor_Declarado"].sum()
    valor_crit = dfv.loc[dfv["Backlog_Dias"] >= LIMIAR_CRITICO, "Valor_Declarado"].sum()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _card(c1, "📦 Backlog", total, f"{total / total_geral * 100:.0f}% do total ({total_geral})")
    _card(c2, "⏱️ Médio", f"{medio:.1f}d", f"Mediana: {mediana:.0f}d | Máx: {int(dfv['Backlog_Dias'].max())}d", "text-yellow")
    _card(c3, f"🔴 Críticos ≥{LIMIAR_CRITICO}d", criticos, f"{criticos / total * 100:.0f}% do filtro", "text-red")
    _card(c4, "⚠️ Ocorrência", com_oc, f"{com_oc / total * 100:.0f}% com problema", "text-orange")
    _card(c5, "🔁 Reincidentes", reinc, "≥ 2 tentativas de entrega", "text-purple")
    _card(c6, "💰 Valor", _brl(valor).replace("R$ ", "R$&nbsp;"), f"Crítico: {_brl(valor_crit)}", "text-green")

    st.markdown("<div style='margin-bottom: 18px;'></div>", unsafe_allow_html=True)

    # ---------------- GRÁFICOS LINHA 1 ----------------
    g1, g2 = st.columns([6, 4])
    with g1:
        st.markdown("##### ⏳ Backlog por Faixa × Etapa")
        grp = dfv.groupby(["Faixa_Backlog", "Etapa"]).size().reset_index(name="Qtd")
        fig = px.bar(
            grp, x="Faixa_Backlog", y="Qtd", color="Etapa", text="Qtd",
            category_orders={"Faixa_Backlog": ORDEM_FAIXAS},
            color_discrete_map=CORES_ETAPA,
            labels={"Faixa_Backlog": "Faixa", "Qtd": "Pacotes"},
        )
        fig.update_traces(textposition="inside")
        st.plotly_chart(_layout(fig, 340), use_container_width=True, key=k("g_faixa"))

    with g2:
        st.markdown("##### 🔄 Distribuição por Etapa")
        cont_et = dfv["Etapa"].value_counts()
        fig_p = go.Figure(go.Pie(
            labels=cont_et.index, values=cont_et.values, hole=0.55,
            marker=dict(colors=[CORES_ETAPA.get(e, "#94a3b8") for e in cont_et.index]),
            textinfo="value+percent",
        ))
        fig_p.update_layout(annotations=[dict(text=f"<b>{total}</b><br>pacotes", showarrow=False, font=dict(size=16))])
        st.plotly_chart(_layout(fig_p, 340), use_container_width=True, key=k("g_etapa"))

    # ---------------- GRÁFICOS LINHA 2 ----------------
    g3, g4 = st.columns([5, 5])
    with g3:
        st.markdown("##### 🧮 Matriz Etapa × Faixa")
        mat = pd.crosstab(dfv["Etapa"], dfv["Faixa_Backlog"]).reindex(columns=ORDEM_FAIXAS, fill_value=0)
        mat = mat.loc[mat.sum(axis=1).sort_values(ascending=False).index]
        fig_h = px.imshow(
            mat, text_auto=True, aspect="auto",
            color_continuous_scale=[[0, "#0f172a"], [0.35, "#0369a1"], [0.7, "#f97316"], [1, "#ef4444"]],
            labels=dict(x="Faixa", y="Etapa", color="Pacotes"),
        )
        fig_h.update_layout(coloraxis_showscale=False)
        st.plotly_chart(_layout(fig_h, max(260, 55 * len(mat) + 80)), use_container_width=True, key=k("g_matriz"))

    with g4:
        st.markdown("##### 🧭 Plano de Ação Sugerido")
        acoes = dfv["Acao_Sugerida"].value_counts().sort_values()
        fig_a = go.Figure(go.Bar(
            y=acoes.index, x=acoes.values, orientation="h", text=acoes.values,
            marker_color=["#ef4444" if a.startswith("🚨") else "#38bdf8" for a in acoes.index],
        ))
        st.plotly_chart(_layout(fig_a, max(260, 32 * len(acoes) + 80)), use_container_width=True, key=k("g_acao"))

    # ---------------- GRÁFICOS LINHA 3 ----------------
    g5, g6 = st.columns([5, 5])
    with g5:
        st.markdown("##### ⚠️ Principais Ocorrências")
        df_oc = dfv[dfv["Tem_Ocorrencia"]]
        if df_oc.empty:
            st.success("Nenhuma ocorrência registrada no filtro atual. 👏")
        else:
            top_oc = df_oc["Ocorrencia"].value_counts().head(10).index
            grp_oc = df_oc[df_oc["Ocorrencia"].isin(top_oc)].groupby(["Ocorrencia", "Faixa_Backlog"]).size().reset_index(name="Qtd")
            fig_o = px.bar(
                grp_oc, y="Ocorrencia", x="Qtd", color="Faixa_Backlog", orientation="h",
                category_orders={"Faixa_Backlog": ORDEM_FAIXAS, "Ocorrencia": list(top_oc)},
                color_discrete_map=CORES_FAIXA, labels={"Ocorrencia": "", "Qtd": "Pacotes", "Faixa_Backlog": "Faixa"},
            )
            st.plotly_chart(_layout(fig_o, max(280, 34 * len(top_oc) + 90)), use_container_width=True, key=k("g_oc"))

    with g6:
        if multi_base and len(f_bases) != 1:
            st.markdown("##### 🏢 Resumo por Base")
            grp_b = dfv.groupby("Base").agg(
                Pacotes=("Waybill No", "count"),
                Medio=("Backlog_Dias", "mean"),
                Maximo=("Backlog_Dias", "max"),
                Criticos=("Backlog_Dias", lambda s: int((s >= LIMIAR_CRITICO).sum())),
                Ocorrencias=("Tem_Ocorrencia", "sum"),
                Piso=("is_rota", lambda s: int((~s.astype(bool)).sum())),
                Valor=("Valor_Declarado", "sum"),
            ).reset_index()
            grp_b["% Crítico"] = (grp_b["Criticos"] / grp_b["Pacotes"] * 100).round(1)
            grp_b["Medio"] = grp_b["Medio"].round(1)
            st.dataframe(
                grp_b.sort_values("Criticos", ascending=False), hide_index=True, use_container_width=True,
                column_config={
                    "Medio": st.column_config.NumberColumn("Médio (d)", format="%.1f"),
                    "Maximo": st.column_config.NumberColumn("Máx (d)"),
                    "Criticos": st.column_config.NumberColumn(f"Críticos ≥{LIMIAR_CRITICO}d"),
                    "Piso": st.column_config.NumberColumn("No Piso"),
                    "Valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
                    "% Crítico": st.column_config.ProgressColumn("% Crítico", min_value=0, max_value=100, format="%.0f%%"),
                },
            )
        else:
            st.markdown("##### 🏘️ Top Cidades em Backlog")
            grp_c = dfv.groupby(["Destination City", "Faixa_Backlog"]).size().reset_index(name="Qtd")
            top_c = dfv["Destination City"].value_counts().head(12).index
            grp_c = grp_c[grp_c["Destination City"].isin(top_c)]
            fig_c = px.bar(
                grp_c, y="Destination City", x="Qtd", color="Faixa_Backlog", orientation="h",
                category_orders={"Faixa_Backlog": ORDEM_FAIXAS, "Destination City": list(top_c)},
                color_discrete_map=CORES_FAIXA, labels={"Destination City": "", "Qtd": "Pacotes", "Faixa_Backlog": "Faixa"},
            )
            st.plotly_chart(_layout(fig_c, max(280, 30 * len(top_c) + 90)), use_container_width=True, key=k("g_cid"))

    # ---------------- TEXTO WHATSAPP ----------------
    with st.expander("📢 Copiar Status do Backlog para o Grupo do WhatsApp", expanded=False):
        cw1, cw2 = st.columns([7, 3])
        with cw1:
            fmt_sel = st.radio(
                "Formato da mensagem:",
                ["📊 Resumo executivo", "🚨 Resumo + Top prioridades", "👨‍✈️ Por motorista (em rota)", "🏘️ Por cidade"],
                horizontal=True, key=k("wpp_fmt"),
            )
        with cw2:
            top_n = st.number_input("Qtd. de prioridades:", min_value=3, max_value=50, value=10, step=1, key=k("wpp_top"),
                                    disabled="Top prioridades" not in fmt_sel)
        mapa_fmt = {
            "📊 Resumo executivo": "resumo",
            "🚨 Resumo + Top prioridades": "criticos",
            "👨‍✈️ Por motorista (em rota)": "motorista",
            "🏘️ Por cidade": "cidade",
        }
        rotulo_ctx = contexto or "Todas as Bases"
        if f_equipe != "Todas":
            rotulo_ctx += f" — {f_equipe}"
        texto = gerar_texto_backlog_whatsapp(dfv, rotulo_ctx, formato=mapa_fmt[fmt_sel], top_n=int(top_n))
        st.code(texto, language="text")
        bw1, bw2 = st.columns([3, 7])
        with bw1:
            st.link_button("📲 Enviar no WhatsApp", f"https://api.whatsapp.com/send?text={urllib.parse.quote(texto)}")
        with bw2:
            st.caption("💡 A mensagem respeita todos os filtros acima. Use o ícone de cópia no canto do quadro para copiar.")

    # ---------------- LISTA DETALHADA ----------------
    st.markdown("#### 📋 Fila de Pacotes em Backlog")
    lo1, lo2 = st.columns([3, 7])
    with lo1:
        ordem = st.selectbox(
            "Ordenar por:",
            ["🎯 Prioridade (recomendado)", "🔥 Maior backlog", "🌱 Menor backlog", "🔁 Mais tentativas", "💰 Maior valor"],
            key=k("ordem"),
        )
    if ordem.startswith("🎯"):
        dfl = dfv.sort_values(["Prioridade", "Backlog_Dias"], ascending=False)
    elif ordem.startswith("🔥"):
        dfl = dfv.sort_values("Backlog_Dias", ascending=False)
    elif ordem.startswith("🌱"):
        dfl = dfv.sort_values("Backlog_Dias", ascending=True)
    elif ordem.startswith("🔁"):
        dfl = dfv.sort_values(["Tentativas", "Backlog_Dias"], ascending=False)
    else:
        dfl = dfv.sort_values("Valor_Declarado", ascending=False)

    colunas = {
        "Base": "Base",
        "Waybill No": "Waybill",
        "Backlog_Dias": "Backlog (d)",
        "Faixa_Backlog": "Faixa",
        "Etapa": "Etapa",
        "Ocorrencia": "Ocorrência",
        "Tentativas": "Tentativas",
        "Acao_Sugerida": "Ação Sugerida",
        "Motorista_Limpo": "Motorista",
        "Equipe": "Equipe",
        "Destination City": "Cidade",
        "Bairro_Display": "Bairro",
        "Endereco_Display": "Endereço",
        "Valor_Declarado": "Valor (R$)",
        "Data_Display": "Entrada",
    }
    cols_ok = [c for c in colunas if c in dfl.columns]
    df_show = dfl[cols_ok].rename(columns=colunas)
    max_bk = int(max(1, dfv["Backlog_Dias"].max()))

    with lo2:
        st.markdown(f"<div style='padding-top: 32px;'><b>{len(df_show)}</b> pacotes no filtro</div>", unsafe_allow_html=True)

    st.dataframe(
        df_show, hide_index=True, use_container_width=True, height=min(620, 38 + 35 * len(df_show)),
        column_config={
            "Backlog (d)": st.column_config.ProgressColumn("Backlog (d)", min_value=0, max_value=max_bk, format="%d d"),
            "Valor (R$)": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
            "Tentativas": st.column_config.NumberColumn("Tentativas", format="%d"),
        },
    )

    st.download_button(
        label="📥 Baixar Backlog Filtrado (Excel)",
        data=_excel_bytes(df_show),
        file_name=f"backlog_{(contexto or 'geral').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=k("dl"),
    )
