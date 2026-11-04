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
        if "Driver Name" in d.columns:
            d["Motorista_Limpo"] = d["Driver Name"].apply(
                lambda v: re.sub(r"^\([A-Za-z0-9_]+\s+(LOC|INT)\)\s*", "", _txt(v)).strip() or "Não Atribuído"
            )
        else:
            d["Motorista_Limpo"] = "Não Atribuído"
    else:
        d["Motorista_Limpo"] = d["Motorista_Limpo"].apply(lambda v: _txt(v) or "Não Atribuído")
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
# RELAÇÃO DE MOTORISTAS POR BACKLOG
# ==========================================
def construir_relacao_motoristas_backlog(df_in, incluir_nao_atribuido=False):
    """Constrói tabela consolidada de motoristas distribuída por faixas de backlog."""
    if df_in is None or df_in.empty:
        return pd.DataFrame()

    df_m = df_in if incluir_nao_atribuido else df_in[df_in["Motorista_Limpo"] != "Não Atribuído"]
    if df_m.empty:
        return pd.DataFrame()

    col_crit = f"Críticos (≥{LIMIAR_CRITICO}d)"
    linhas = []
    for mot, grp in df_m.groupby("Motorista_Limpo"):
        total_m = len(grp)
        base_m = _txt(grp["Base"].iloc[0]) if "Base" in grp.columns else ""
        eq_m = _txt(grp["Equipe"].iloc[0]) if "Equipe" in grp.columns else "—"
        vc_fx = grp["Faixa_Backlog"].value_counts()

        f_0_1 = int(vc_fx.get("🟢 0–1 dia", 0))
        f_2 = int(vc_fx.get("🟡 2 dias", 0))
        f_3 = int(vc_fx.get("🟠 3 dias", 0))
        f_4_5 = int(vc_fx.get("🔴 4–5 dias", 0))
        f_6_10 = int(vc_fx.get("🟣 6–10 dias", 0))
        f_10p = int(vc_fx.get("⚫ +10 dias", 0))

        crit_m = int((grp["Backlog_Dias"] >= LIMIAR_CRITICO).sum())
        pct_crit = round((crit_m / total_m * 100), 1) if total_m > 0 else 0.0
        medio_m = round(float(grp["Backlog_Dias"].mean()), 1) if total_m > 0 else 0.0
        max_m = int(grp["Backlog_Dias"].max()) if total_m > 0 else 0
        oc_m = int(grp["Tem_Ocorrencia"].sum())
        reinc_m = int((grp["Tentativas"] >= 2).sum())
        val_m = round(float(grp["Valor_Declarado"].sum()), 2)

        if crit_m > 0:
            sit = f"🔴 {crit_m} crítico(s) (máx {max_m}d)"
        elif max_m >= 2:
            sit = f"🟡 Atenção (máx {max_m}d)"
        else:
            sit = "🟢 Regular (0–1d)"

        linhas.append({
            "Base": base_m,
            "Equipe": eq_m,
            "Motorista": mot,
            "Total": total_m,
            "🟢 0–1d": f_0_1,
            "🟡 2d": f_2,
            "🟠 3d": f_3,
            "🔴 4–5d": f_4_5,
            "🟣 6–10d": f_6_10,
            "⚫ +10d": f_10p,
            col_crit: crit_m,
            "% Crítico": pct_crit,
            "Médio (d)": medio_m,
            "Máx (d)": max_m,
            "Ocorrências": oc_m,
            "Reincidentes": reinc_m,
            "Valor (R$)": val_m,
            "Situação": sit,
        })

    return pd.DataFrame(linhas)


def gerar_texto_motoristas_backlog_wpp(df_rel, contexto="", divisao="TODOS", modo="completo"):
    """Gera mensagem formatada com a relação de motoristas por backlog para WhatsApp."""
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    col_crit = f"Críticos (≥{LIMIAR_CRITICO}d)"
    titulo_base = contexto if contexto else "Todas as Bases"

    if df_rel is None or df_rel.empty:
        return f"📊 *RELAÇÃO DE MOTORISTAS POR BACKLOG — {titulo_base.upper()}*\n_Nenhum motorista encontrado no filtro atual._"

    df_w = df_rel.copy()
    if modo == "criticos":
        df_w = df_w[df_w[col_crit] > 0]

    if divisao == "LOC":
        df_w = df_w[df_w["Equipe"] == "LOC"]
        sufixo = " — LOC (LOCAL)"
    elif divisao == "INT":
        df_w = df_w[df_w["Equipe"] == "INT"]
        sufixo = " — INT (INTERIOR)"
    else:
        sufixo = ""

    if df_w.empty:
        return f"📊 *RELAÇÃO DE MOTORISTAS POR BACKLOG — {titulo_base.upper()}{sufixo}*\n_Nenhum motorista para os critérios selecionados._"

    total_mots = len(df_w)
    total_pcts = int(df_w["Total"].sum())
    total_crit = int(df_w[col_crit].sum())
    multi_b = df_w["Base"].nunique() > 1

    def _formatar_bloco(df_bloco):
        itens = []
        for _, r in df_bloco.iterrows():
            ic = "🔴" if r[col_crit] > 0 else ("🟡" if r["Máx (d)"] >= 2 else "🟢")
            tag_b = f"[{r['Base']}] " if multi_b and r["Base"] else ""
            if modo == "simplificado":
                crit_s = f" | 🔴 {int(r[col_crit])} crít." if r[col_crit] > 0 else ""
                itens.append(f"{ic} {tag_b}*{r['Motorista']}* — *{int(r['Total'])} pct*{crit_s} (máx {int(r['Máx (d)'])}d)")
            else:
                partes_fx = []
                for col_fx, emoji_fx in [
                    ("🟢 0–1d", "🟢0-1d:"),
                    ("🟡 2d", "🟡2d:"),
                    ("🟠 3d", "🟠3d:"),
                    ("🔴 4–5d", "🔴4-5d:"),
                    ("🟣 6–10d", "🟣6-10d:"),
                    ("⚫ +10d", "⚫+10d:"),
                ]:
                    val_fx = int(r.get(col_fx, 0))
                    if val_fx > 0:
                        partes_fx.append(f"{emoji_fx}{val_fx}")
                fx_str = f" ({' | '.join(partes_fx)})" if partes_fx else ""
                itens.append(
                    f"{ic} {tag_b}*{r['Motorista']}* — *{int(r['Total'])} pct*{fx_str} | médio {r['Médio (d)']:.1f}d | máx {int(r['Máx (d)'])}d"
                )
        return "\n".join(itens)

    linhas = [
        f"👨‍✈️ *RELAÇÃO DE MOTORISTAS POR BACKLOG — {titulo_base.upper()}{sufixo}*",
        f"🗓️ _Atualizado em {agora}_",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"👨‍✈️ *Motoristas:* {total_mots} | 📦 *Pacotes:* {total_pcts} | 🔴 *Críticos (≥{LIMIAR_CRITICO}d):* {total_crit}",
        "",
    ]

    if divisao == "SEPARADO":
        df_loc = df_w[df_w["Equipe"] == "LOC"]
        df_int = df_w[df_w["Equipe"] == "INT"]
        df_out = df_w[~df_w["Equipe"].isin(["LOC", "INT"])]
        if not df_loc.empty:
            linhas.append(f"🏙️ *EQUIPE LOC (LOCAL) — {len(df_loc)} mot. / {int(df_loc['Total'].sum())} pct:*")
            linhas.append(_formatar_bloco(df_loc))
            linhas.append("")
        if not df_int.empty:
            linhas.append(f"🏞️ *EQUIPE INT (INTERIOR) — {len(df_int)} mot. / {int(df_int['Total'].sum())} pct:*")
            linhas.append(_formatar_bloco(df_int))
            linhas.append("")
        if not df_out.empty:
            linhas.append(f"📦 *OUTROS / PISO — {int(df_out['Total'].sum())} pct:*")
            linhas.append(_formatar_bloco(df_out))
            linhas.append("")
    else:
        linhas.append(_formatar_bloco(df_w))
        linhas.append("")

    linhas += [
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ *Favor priorizar a baixa dos pacotes com maior backlog!*",
    ]
    return "\n".join(linhas)


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

        fd1, fd2, fd3, fd4, fd5 = st.columns([3, 3, 1.5, 1.5, 2.5])
        with fd1:
            df_opcoes_mot = df[df["Base"].isin(f_bases)] if f_bases else df
            mots_disp = sorted(
                [m for m in df_opcoes_mot["Motorista_Limpo"].dropna().unique().tolist() if m and m != "Não Atribuído"]
            )
            if "Não Atribuído" in set(df_opcoes_mot["Motorista_Limpo"]):
                mots_disp.append("Não Atribuído")
            f_mots = st.multiselect("👨‍✈️ Motorista (vazio = todos):", mots_disp, key=k("f_mot"))
        with fd2:
            ocs_disp = df["Ocorrencia"].value_counts().index.tolist()
            f_ocs = st.multiselect("⚠️ Ocorrência (vazio = todas):", ocs_disp, key=k("f_oc"))
        with fd3:
            equipes_disp = ["Todas"] + sorted([e for e in df["Equipe"].unique().tolist() if e])
            f_equipe = st.selectbox("👥 Equipe:", equipes_disp, key=k("f_equipe"))
        with fd4:
            f_min = st.number_input("⏱️ Backlog mín. (d):", min_value=0, value=0, step=1, key=k("f_min"))
        with fd5:
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
    if f_mots:
        dfv = dfv[dfv["Motorista_Limpo"].isin(f_mots)]
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

    # ---------------- RELAÇÃO DE MOTORISTAS POR BACKLOG ----------------
    st.markdown("<hr style='border-color: #1e293b; margin: 22px 0 16px 0;'>", unsafe_allow_html=True)
    st.markdown("#### 👨‍✈️ Relação de Motoristas por Backlog")
    st.caption(
        "Visão consolidada de quantos pacotes cada motorista possui em cada faixa de backlog, "
        "com gráfico pronto para o grupo, planilha Excel, gerador de texto para WhatsApp e detalhamento por entregador."
    )

    col_crit_nome = f"Críticos (≥{LIMIAR_CRITICO}d)"
    cm1, cm2, cm3, cm4 = st.columns([3, 2, 3, 2])
    with cm1:
        escopo_mot = st.selectbox(
            "👤 Escopo:",
            ["👨‍✈️ Apenas Motoristas Atribuídos", "📦 Incluir Não Atribuído (Piso)"],
            key=k("mot_escopo"),
        )
    with cm2:
        eq_mot = st.selectbox(
            "👥 Equipe:",
            ["Todas", "🏙️ LOC (Local)", "🏞️ INT (Interior)"],
            key=k("mot_eq"),
        )
    with cm3:
        ordem_mot = st.selectbox(
            "📊 Ordenar motoristas por:",
            [
                f"🔴 Mais Críticos (≥ {LIMIAR_CRITICO}d)",
                "📦 Maior Volume Total",
                "🔥 Maior Backlog Máximo (dias)",
                "⏱️ Maior Backlog Médio (dias)",
                "⚠️ Mais Ocorrências",
                "🔤 Ordem Alfabética",
            ],
            key=k("mot_ordem"),
        )
    with cm4:
        qtd_graf_mot = st.selectbox(
            "📈 Exibir no gráfico:",
            ["Top 15", "Top 25", "Top 40", "Todos"],
            index=1,
            key=k("mot_qtd_graf"),
        )

    incluir_na = ("Incluir Não Atribuído" in escopo_mot) or ("Não Atribuído" in f_mots)
    df_rel_mot = construir_relacao_motoristas_backlog(dfv, incluir_nao_atribuido=incluir_na)

    if not df_rel_mot.empty and eq_mot != "Todas":
        alvo_eq = "LOC" if "LOC" in eq_mot else "INT"
        df_rel_mot = df_rel_mot[df_rel_mot["Equipe"] == alvo_eq].copy()

    if df_rel_mot.empty:
        st.info("Nenhum motorista atribuído encontrado para os filtros atuais. Altere o escopo para 'Incluir Não Atribuído (Piso)' se desejar ver os pacotes sem motorista.")
    else:
        if ordem_mot.startswith("🔴"):
            df_rel_mot = df_rel_mot.sort_values([col_crit_nome, "Máx (d)", "Total"], ascending=[False, False, False])
        elif ordem_mot.startswith("📦"):
            df_rel_mot = df_rel_mot.sort_values(["Total", col_crit_nome, "Máx (d)"], ascending=[False, False, False])
        elif ordem_mot.startswith("🔥"):
            df_rel_mot = df_rel_mot.sort_values(["Máx (d)", col_crit_nome, "Total"], ascending=[False, False, False])
        elif ordem_mot.startswith("⏱️"):
            df_rel_mot = df_rel_mot.sort_values(["Médio (d)", "Máx (d)", "Total"], ascending=[False, False, False])
        elif ordem_mot.startswith("⚠️"):
            df_rel_mot = df_rel_mot.sort_values(["Ocorrências", col_crit_nome, "Total"], ascending=[False, False, False])
        else:
            df_rel_mot = df_rel_mot.sort_values("Motorista", ascending=True)

        df_rel_mot = df_rel_mot.reset_index(drop=True)

        # Gráfico Horizontal Empilhado de Motoristas por Faixa de Backlog
        df_graf_m = df_rel_mot.copy()
        if qtd_graf_mot == "Top 15":
            df_graf_m = df_graf_m.head(15)
        elif qtd_graf_mot == "Top 25":
            df_graf_m = df_graf_m.head(25)
        elif qtd_graf_mot == "Top 40":
            df_graf_m = df_graf_m.head(40)
        df_graf_m = df_graf_m.iloc[::-1]

        altura_m = max(300, min(1500, len(df_graf_m) * 28 + 80))
        fig_m = go.Figure()
        mapa_cols_faixa = [
            ("🟢 0–1d", "🟢 0–1 dia", "#22c55e"),
            ("🟡 2d", "🟡 2 dias", "#eab308"),
            ("🟠 3d", "🟠 3 dias", "#f97316"),
            ("🔴 4–5d", "🔴 4–5 dias", "#ef4444"),
            ("🟣 6–10d", "🟣 6–10 dias", "#a855f7"),
            ("⚫ +10d", "⚫ +10 dias", "#64748b"),
        ]
        for col_curta, nome_legenda, cor_barra in mapa_cols_faixa:
            if col_curta in df_graf_m.columns and df_graf_m[col_curta].sum() > 0:
                fig_m.add_trace(go.Bar(
                    y=df_graf_m["Motorista"],
                    x=df_graf_m[col_curta],
                    name=nome_legenda,
                    orientation="h",
                    marker_color=cor_barra,
                    text=df_graf_m[col_curta].apply(lambda v: str(int(v)) if v > 0 else ""),
                    textposition="inside",
                    insidetextanchor="middle",
                ))
        fig_m.update_layout(barmode="stack")
        st.plotly_chart(
            _layout(fig_m, altura_m),
            use_container_width=True,
            key=k("g_mot_backlog"),
            config={
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": f"motoristas_backlog_{(contexto or 'geral').replace(' ', '_')}",
                    "height": altura_m,
                    "width": 950,
                    "scale": 2,
                }
            },
        )
        st.caption("📸 **Dica:** Passe o mouse sobre o gráfico e clique no ícone da câmera 📷 no canto superior direito para baixar a imagem em alta resolução para o grupo.")

        # Tabela Consolidada da Relação de Motoristas por Backlog
        cols_mot_exibir = [
            c for c in [
                "Base", "Equipe", "Motorista", "Total",
                "🟢 0–1d", "🟡 2d", "🟠 3d", "🔴 4–5d", "🟣 6–10d", "⚫ +10d",
                col_crit_nome, "% Crítico", "Médio (d)", "Máx (d)",
                "Ocorrências", "Reincidentes", "Valor (R$)", "Situação"
            ]
            if c in df_rel_mot.columns and (c != "Base" or multi_base)
        ]
        df_rel_view = df_rel_mot[cols_mot_exibir]

        st.dataframe(
            df_rel_view,
            hide_index=True,
            use_container_width=True,
            height=min(560, 42 + 35 * len(df_rel_view)),
            column_config={
                "% Crítico": st.column_config.ProgressColumn("% Crítico", min_value=0, max_value=100, format="%.0f%%"),
                "Médio (d)": st.column_config.NumberColumn("Médio (d)", format="%.1f"),
                "Máx (d)": st.column_config.NumberColumn("Máx (d)", format="%d d"),
                "Valor (R$)": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
            },
        )

        cb_dl1, cb_dl2 = st.columns([4, 6])
        with cb_dl1:
            st.download_button(
                label="📥 Baixar Relação de Motoristas (Excel)",
                data=_excel_bytes(df_rel_view),
                file_name=f"relacao_motoristas_backlog_{(contexto or 'geral').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=k("dl_rel_mot"),
            )
        with cb_dl2:
            st.markdown(
                f"<div style='padding-top: 8px; color: #94a3b8; font-size: 0.9rem;'>"
                f"👨‍✈️ <b>{len(df_rel_view)}</b> motoristas listados | "
                f"📦 <b>{int(df_rel_view['Total'].sum())}</b> pacotes | "
                f"🔴 <b>{int(df_rel_view[col_crit_nome].sum())}</b> críticos (≥{LIMIAR_CRITICO}d)"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Gerador de WhatsApp específico para a Relação de Motoristas por Backlog
        with st.expander("📢 Copiar Relação de Motoristas por Backlog para o WhatsApp", expanded=False):
            wm1, wm2 = st.columns(2)
            with wm1:
                div_wpp_m = st.radio(
                    "Divisão de Equipe:",
                    [
                        "🏢 Todos os Motoristas",
                        "🏙️ Apenas LOC (Local)",
                        "🏞️ Apenas INT (Interior)",
                        "📑 Separar em Blocos (LOC + INT)",
                    ],
                    horizontal=True,
                    key=k("wpp_mot_div"),
                )
            with wm2:
                modo_wpp_m = st.radio(
                    "Formato da Linha:",
                    [
                        "Completo (Total + Faixas + Máx)",
                        "Simplificado (Nome + Total + Críticos)",
                        f"🔴 Apenas com Críticos (≥ {LIMIAR_CRITICO}d)",
                    ],
                    horizontal=True,
                    key=k("wpp_mot_modo"),
                )

            cod_div = "TODOS"
            if "Apenas LOC" in div_wpp_m:
                cod_div = "LOC"
            elif "Apenas INT" in div_wpp_m:
                cod_div = "INT"
            elif "Separar em Blocos" in div_wpp_m:
                cod_div = "SEPARADO"

            cod_modo = "completo"
            if "Simplificado" in modo_wpp_m:
                cod_modo = "simplificado"
            elif "Apenas com Críticos" in modo_wpp_m:
                cod_modo = "criticos"

            txt_mot_wpp = gerar_texto_motoristas_backlog_wpp(
                df_rel_mot, contexto=contexto or "Todas as Bases", divisao=cod_div, modo=cod_modo
            )
            st.code(txt_mot_wpp, language="text")
            bm1, bm2 = st.columns([3, 7])
            with bm1:
                st.link_button(
                    "📲 Enviar Relação no WhatsApp",
                    f"https://api.whatsapp.com/send?text={urllib.parse.quote(txt_mot_wpp)}",
                )
            with bm2:
                st.caption("💡 Dica: Use 'Separar em Blocos (LOC + INT)' ou 'Apenas LOC / INT' para enviar direto no grupo correspondente.")

        # Detalhamento de pacotes por motorista (Drill-down)
        with st.expander(f"🔍 Detalhar Pacotes por Motorista ({len(df_rel_mot)} motoristas)", expanded=False):
            lista_mots_sel = df_rel_mot["Motorista"].tolist()
            mot_escolhido = st.selectbox(
                "Selecione o motorista para inspecionar os pacotes:",
                lista_mots_sel,
                key=k("mot_drill_sel"),
            )
            if mot_escolhido:
                df_pac_mot = dfv[dfv["Motorista_Limpo"] == mot_escolhido].sort_values(
                    ["Backlog_Dias", "Prioridade"], ascending=[False, False]
                )
                cols_pac_mot = {
                    "Base": "Base",
                    "Waybill No": "Waybill",
                    "Backlog_Dias": "Backlog (d)",
                    "Faixa_Backlog": "Faixa",
                    "Etapa": "Etapa",
                    "Ocorrencia": "Ocorrência",
                    "Tentativas": "Tentativas",
                    "Acao_Sugerida": "Ação Sugerida",
                    "Destination City": "Cidade",
                    "Bairro_Display": "Bairro",
                    "Endereco_Display": "Endereço",
                    "Data_Display": "Entrada",
                }
                cols_pm_ok = [c for c in cols_pac_mot if c in df_pac_mot.columns]
                st.dataframe(
                    df_pac_mot[cols_pm_ok].rename(columns=cols_pac_mot),
                    hide_index=True,
                    use_container_width=True,
                )

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
