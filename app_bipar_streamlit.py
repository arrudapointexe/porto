import streamlit as st
import pandas as pd
from datetime import datetime
import io


st.set_page_config(page_title="Expedição Bipar", layout="wide")


def ensure_state():
    if 'scans' not in st.session_state:
        st.session_state.scans = {}
    if 'play' not in st.session_state:
        st.session_state.play = None


ensure_state()


ROUTES = ["STB", "ITR", "ROÇA", "FRANCISMAR"]


def add_scan(route: str, code: str):
    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    st.session_state.scans.setdefault(route, []).append({'code': code, 'ts': now})


def render_audio_player(play_flag: str):
    # Small WebAudio tone generator; plays once then client-side only
    html = f"""
    <script>
    function playTone(freq, duration){
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = 'sine';
      o.frequency.value = freq;
      o.connect(g);
      g.connect(ctx.destination);
      o.start();
      g.gain.setValueAtTime(0.0001, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.5, ctx.currentTime + 0.01);
      setTimeout(()=>{{ g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.02); o.stop(); ctx.close(); }}, duration);
    }
    const play = "{play_flag}";
    if(play === 'success'){{ playTone(880,200); }}
    else if(play === 'error'){{ playTone(220,400); }}
    </script>
    """
    st.components.v1.html(html, height=0)


def expedition_tab():
    st.header("Expedição")
    route = st.selectbox("Rota", ROUTES, index=0)

    with st.form(key='scan_form', clear_on_submit=True):
        scan_val = st.text_input('Aproxime o leitor e pressione Enter', key='scan_input', placeholder='Bip aqui...')
        submitted = st.form_submit_button('Enter')

    if submitted:
        code = scan_val.strip()
        if not code:
            st.warning("Nenhum código informado")
        else:
            scans_for_route = st.session_state.scans.setdefault(route, [])
            exists = any(item['code'] == code for item in scans_for_route)
            if exists:
                st.error(f"Código {code} já foi bipado nesta rota")
                st.session_state.play = 'error'
            else:
                add_scan(route, code)
                st.success(f"Bip registrado: {code}")
                st.session_state.play = 'success'

    # show recent items for selected route
    st.subheader(f"Últimos bips - {route}")
    records = st.session_state.scans.get(route, [])
    if records:
        df = pd.DataFrame(records).sort_values('ts', ascending=False)
        st.table(df.head(50))
    else:
        st.info("Nenhum bip registrado ainda nesta rota")

    if st.session_state.play:
        render_audio_player(st.session_state.play)
        st.session_state.play = None


def analysts_tab():
    st.header("Analistas")
    all_routes = ["Todas"] + ROUTES
    route = st.selectbox("Filtrar rota", all_routes, index=0)

    # build DataFrame
    rows = []
    for r, items in st.session_state.scans.items():
        for it in items:
            rows.append({'route': r, 'code': it['code'], 'ts': it['ts']})

    if rows:
        df = pd.DataFrame(rows).sort_values(['route','ts'])
        if route != "Todas":
            df = df[df['route'] == route]

        st.subheader("Bips registrados")
        st.dataframe(df)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(label='Exportar CSV', data=csv, file_name='bips_export.csv', mime='text/csv')

        # xlsx
        towrite = io.BytesIO()
        with pd.ExcelWriter(towrite, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='bips')
        towrite.seek(0)
        st.download_button(label='Exportar XLSX', data=towrite, file_name='bips_export.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        st.info('Nenhum registro disponível para exportação')


def main():
    st.title('App de Expedição Bipar')
    tabs = st.tabs(["Expedição", "Analistas"])
    with tabs[0]:
        expedition_tab()
    with tabs[1]:
        analysts_tab()


if __name__ == '__main__':
    main()
