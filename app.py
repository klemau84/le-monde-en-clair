from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from news_engine import fetch_country, fetch_many


ROOT = Path(__file__).parent
COUNTRIES = pd.read_csv(ROOT / "data" / "countries.csv")

st.set_page_config(page_title="Le Monde en clair", page_icon="🌍", layout="wide")

st.markdown("""
<style>
  .block-container {padding-top: 1.5rem; max-width: 1450px;}
  .hero {padding: 1.15rem 1.35rem; border-radius: 18px; color: white;
         background: linear-gradient(120deg,#172026,#304654); margin-bottom: 1rem;}
  .hero h1 {margin:0; font-size:2.25rem;} .hero p {margin:.35rem 0 0; opacity:.86}
  .news-card {background:white; border:1px solid #ded9cf; border-radius:15px;
              padding:1rem 1.1rem; margin:.65rem 0; box-shadow:0 2px 8px #0000000a;}
  .news-card h3 {font-size:1.1rem; margin:.25rem 0 .4rem; line-height:1.3;}
  .meta {font-size:.82rem;color:#667078}.why {font-size:.92rem;color:#36454f;margin:.55rem 0}
  .tag-major {color:#a82116;font-weight:700}.tag-important {color:#b46500;font-weight:700}
  .tag-watch {color:#35667a;font-weight:700}
  div.stButton > button {border-radius:14px; min-height:54px; font-weight:650;}
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class="hero"><h1>🌍 Le Monde en clair</h1>
<p>Les informations qui comptent, classées, expliquées et reliées à leur source.</p></div>""", unsafe_allow_html=True)


@st.cache_data(ttl=1800, show_spinner=False)
def load_global(days: int) -> pd.DataFrame:
    return fetch_many(COUNTRIES, days=days, per_country=7)


@st.cache_data(ttl=1800, show_spinner=False)
def load_country(country: str, query: str, days: int) -> pd.DataFrame:
    return pd.DataFrame(fetch_country(country, query, days=days, limit=30))


def news_card(row) -> None:
    css = {"Majeur": "tag-major", "Important": "tag-important", "À suivre": "tag-watch"}[row.niveau]
    when = row.date.strftime("%d/%m/%Y à %H:%M") if hasattr(row.date, "strftime") else str(row.date)
    link = row.lien or "#"
    st.markdown(f"""
    <div class="news-card">
      <div class="meta">{row.pays} · {row.categorie} · <span class="{css}">{row.niveau}</span> · impact {row.score}/100</div>
      <h3>{row.titre}</h3>
      <div class="why"><b>Pourquoi c'est important :</b> {row.pourquoi}</div>
      <div class="meta">{row.source} · {when} · <a href="{link}" target="_blank">Lire la source ↗</a></div>
    </div>""", unsafe_allow_html=True)


with st.sidebar:
    st.header("Réglages")
    days = st.segmented_control("Période", options=[1, 3, 7], default=3, format_func=lambda x: f"{x} jour" if x == 1 else f"{x} jours")
    category_filter = st.multiselect("Thèmes", ["Conflits et diplomatie", "Politique", "Économie", "Climat et catastrophes", "Société", "Sciences et technologie", "Autres sujets"])
    min_level = st.select_slider("Importance minimale", options=["Tout", "À suivre", "Important", "Majeur"], value="Important")
    st.caption("Actualisation automatique toutes les 30 minutes. Les notes sont une aide au tri, pas une vérité éditoriale.")

if "selected_country" not in st.session_state:
    st.session_state.selected_country = None

tab_world, tab_country, tab_method = st.tabs(["🗞️ Le monde aujourd'hui", "🏳️ Par pays", "ℹ️ Méthode et sources"])

with tab_world:
    with st.spinner("Sélection des informations majeures…"):
        global_df = load_global(days or 3)
    if global_df.empty:
        st.warning("Les flux d'actualités sont momentanément indisponibles. Réessayez dans quelques minutes.")
    else:
        if category_filter:
            global_df = global_df[global_df["categorie"].isin(category_filter)]
        thresholds = {"Tout": 0, "À suivre": 1, "Important": 55, "Majeur": 72}
        global_df = global_df[global_df["score"] >= thresholds[min_level]]
        top = global_df.sort_values(["score", "date"], ascending=False).drop_duplicates("titre").head(15)
        c1, c2, c3 = st.columns(3)
        c1.metric("Sujets retenus", len(top))
        c2.metric("Pays représentés", top["pays"].nunique())
        c3.metric("Sujets majeurs", int((top["niveau"] == "Majeur").sum()))
        st.subheader("L'essentiel")
        for row in top.itertuples(index=False):
            news_card(row)

with tab_country:
    st.subheader("Choisissez un pays")
    for region in COUNTRIES["region"].drop_duplicates():
        st.caption(region)
        subset = COUNTRIES[COUNTRIES["region"] == region]
        cols = st.columns(min(5, len(subset)))
        for col, row in zip(cols, subset.itertuples(index=False)):
            if col.button(f"{row.drapeau}  {row.pays}", key=f"country_{row.code}", width="stretch"):
                st.session_state.selected_country = row.code

    code = st.session_state.selected_country
    if code:
        country = COUNTRIES.loc[COUNTRIES["code"] == code].iloc[0]
        st.divider()
        st.subheader(f"{country.drapeau} {country.pays}")
        st.caption(f"Capitale : {country.capitale} · Région : {country.region}")
        with st.spinner(f"Analyse de l'actualité de {country.pays}…"):
            df = load_country(country.pays, country.requete, days or 3)
        if df.empty:
            st.warning("Aucune actualité exploitable n'a été récupérée pour ce pays.")
        else:
            if category_filter:
                df = df[df["categorie"].isin(category_filter)]
            thresholds = {"Tout": 0, "À suivre": 1, "Important": 55, "Majeur": 72}
            df = df[df["score"] >= thresholds[min_level]].sort_values(["score", "date"], ascending=False)
            left, right = st.columns([1.6, 1])
            with left:
                st.markdown("#### Informations prioritaires")
                for row in df.head(8).itertuples(index=False):
                    news_card(row)
            with right:
                st.markdown("#### Répartition des sujets")
                counts = df.groupby("categorie", as_index=False).size().sort_values("size")
                if not counts.empty:
                    fig = px.bar(counts, x="size", y="categorie", orientation="h", color="size", color_continuous_scale=["#b7c4c9", "#E4572E"])
                    fig.update_layout(height=330, margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False, xaxis_title="Nombre", yaxis_title="")
                    st.plotly_chart(fig, width="stretch")
                st.download_button("Exporter les résultats CSV", df.drop(columns=["date"]).to_csv(index=False).encode("utf-8-sig"), f"actualites_{code.lower()}.csv", "text/csv", width="stretch")
    else:
        st.info("Cliquez sur un pays pour afficher sa fiche d'actualité.")

with tab_method:
    st.subheader("Ce que fait réellement l'application")
    st.markdown("""
La V1 interroge des flux d'actualités francophones, puis applique quatre traitements :

1. suppression des titres en double ;
2. classement par récence, portée probable du sujet et fiabilité générale de la source ;
3. catégorisation thématique ;
4. explication courte de l'enjeu potentiel.

**Limite importante :** le score mesure des signaux dans le titre. Il ne remplace pas un jugement humain et ne détermine pas si une information est vraie. Le lien vers la publication d'origine reste toujours accessible.

Les dépêches et médias reconnus reçoivent un bonus modéré. Aucun média n'est traité comme une garantie absolue. La prochaine version pourra regrouper plusieurs articles parlant du même événement et comparer leurs angles.
""")
    st.markdown("#### Pays couverts")
    st.dataframe(COUNTRIES[["drapeau", "pays", "region", "capitale"]], hide_index=True, width="stretch")
    st.caption(f"Version 1.0 · interface générée le {datetime.now().strftime('%d/%m/%Y')}")
