import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd

st.set_page_config(
    page_title="Lâche ton Prono", 
    page_icon="🤾", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = get_supabase()
tz_fr = ZoneInfo("Europe/Paris")

st.title("🤾 Lâche ton Prono 🍻")

res_match = supabase.table("matchs").select("*").eq("statut", "A venir").order("id").limit(1).execute()

if not res_match.data:
    st.info("Aucun match à venir programmé.")
    st.stop()

match = res_match.data[0]
match_id_public, code, adversaire = match["id"], match["code_match"], match["adversaire"]

st.subheader(f"Prochain match : {code} vs {adversaire}")

if match.get("date_match"):
    date_str = match["date_match"].replace("Z", "+00:00")
    date_match = datetime.fromisoformat(date_str).astimezone(tz_fr)
    
    date_limite = (date_match - timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
    
    st.write(f"⏳ **Clôture des pronos :** {date_limite.strftime('%d/%m/%Y à %H:%M')}")
    verrouille = datetime.now(tz_fr) > date_limite
else:
    st.write("⏳ **Clôture des pronos :** Date non fixée")
    verrouille = False

res_joueurs = supabase.table("joueurs").select("nom").order("nom").execute()
liste_joueurs = [j["nom"] for j in res_joueurs.data]

st.divider()

with st.sidebar:
    with st.expander("⚙️ Administration du jeu"):
        mdp = st.text_input("Mot de passe secret :", type="password")
        
        if mdp == st.secrets.get("ADMIN_PASSWORD", ""):
            st.success("🔓 Mode Administrateur activé")
            
            tous_les_matchs = supabase.table("matchs").select("id, code_match, adversaire, statut").order("id").execute().data
            choix_matchs = {f"{m['code_match']} vs {m['adversaire']} ({m['statut']})": m['id'] for m in tous_les_matchs}
            
            nom_match_admin = st.selectbox("Sélectionne le match à traiter :", options=list(choix_matchs.keys()))
            id_match_admin = choix_matchs[nom_match_admin]
            
            st.write("Renseigne les 12 joueurs alignés pour CE match :")
            compo_officielle = st.multiselect("La composition officielle :", options=liste_joueurs)
            
            if st.button("Valider le match et calculer les points", type="primary"):
                if len(compo_officielle) != 12:
                    st.warning(f"⚠️ Tu dois sélectionner exactement 12 joueurs (Tu en as coché {len(compo_officielle)}).")
                else:
                    supabase.table("matchs").update({
                        "compo_officielle": compo_officielle,
                        "statut": "TERMINE"
                    }).eq("id", id_match_admin).execute()
                    
                    pronos = supabase.table("pronostics").select("id, joueurs_choisis").eq("match_id", id_match_admin).execute()
                    
                    for prono in pronos.data:
                        bons_choix = set(prono["joueurs_choisis"]).intersection(set(compo_officielle))
                        points_obtenus = len(bons_choix)
                        
                        if points_obtenus == 12:
                            points_obtenus += 3
                        
                        supabase.table("pronostics").update({
                            "points": points_obtenus
                        }).eq("id", prono["id"]).execute()
                    
                    st.success(f"✅ Match clôturé ! Les points ont été calculés avec succès.")
                    st.rerun() 
        elif mdp:
            st.error("⛔ Mot de passe incorrect.")

# --- CRÉATION DES 3 ONGLETS PRINCIPAUX ---
tab_prono, tab_recap, tab_classement = st.tabs(["📝 Mon prono", "👀 L'équipe", "🏆 Classement"])

with tab_prono:
    if verrouille:
        st.error("⛔ Les pronostics pour ce match sont désormais clôturés.")
    else:
        with st.form("prono_form"):
            nom_pote = st.selectbox("Qui es-tu ?", options=["-- Sélectionne ton nom --"] + liste_joueurs)
            selection = st.multiselect("Sélectionne tes 12 joueurs :", options=liste_joueurs)
            
            submit = st.form_submit_button("Valider mon prono 🚀", type="primary")
            
            if submit:
                if nom_pote == "-- Sélectionne ton nom --":
                    st.warning("⚠️ Tu dois sélectionner ton nom dans la liste.")
                elif len(selection) != 12:
                    st.warning(f"⚠️ Tu dois sélectionner exactement 12 joueurs (Tu en as coché {len(selection)}).")
                else:
                    existant = supabase.table("pronostics").select("id").eq("match_id", match_id_public).eq("nom_pote", nom_pote).execute()
                    if existant.data:
                        id_prono = existant.data[0]["id"]
                        supabase.table("pronostics").update({
                            "joueurs_choisis": selection,
                            "created_at": datetime.now(tz_fr).isoformat()
                        }).eq("id", id_prono).execute()
                        st.success("✅ Ton prono a été mis à jour avec succès !")
                    else:
                        supabase.table("pronostics").insert({
                            "nom_pote": nom_pote, 
                            "match_id": match_id_public, 
                            "joueurs_choisis": selection
                        }).execute()
                        st.success("✅ Ton prono a été enregistré !")
                    st.balloons()

with tab_recap:
    st.write("### Pronos validés pour ce match")
    res_pronos = supabase.table("pronostics").select("nom_pote, joueurs_choisis").eq("match_id", match_id_public).execute()
    
    if res_pronos.data:
        df_recap = pd.DataFrame(res_pronos.data)
        df_recap["Joueurs"] = df_recap["joueurs_choisis"].apply(lambda x: ", ".join(x))
        st.dataframe(df_recap[["nom_pote", "Joueurs"]].rename(columns={"nom_pote": "Pronostiqueur"}), hide_index=True)
    else:
        st.info("Aucun prono déposé pour le moment.")

with tab_classement:
    matchs_termines = supabase.table("matchs").select("id, code_match, adversaire").eq("statut", "TERMINE").order("id").execute().data
    
    options_affichage = ["Classement Général"] + [f"{m['code_match']} vs {m['adversaire']}" for m in matchs_termines]
    choix_vue = st.selectbox("Affichage :", options_affichage)
    
    st.subheader(choix_vue)
    
    if choix_vue == "Classement Général":
        all_pronos = supabase.table("pronostics").select("nom_pote, points").execute()
        if all_pronos.data:
            df_class = pd.DataFrame(all_pronos.data)
            
            df_class["Couronnes 👑"] = df_class["points"].apply(lambda x: 1 if x == 15 else 0)
            
            df_class = df_class.groupby("nom_pote").agg(
                Points=("points", "sum"),
                Couronnes=("Couronnes 👑", "sum")
            ).reset_index()
            
            df_class = df_class.sort_values(by=["Points", "Couronnes"], ascending=[False, False]).reset_index(drop=True)
            df_class.index += 1
            
            df_class_display = df_class.rename(columns={
                "nom_pote": "Joueur", 
                "Couronnes": "Couronnes 👑"
            })
            st.dataframe(df_class_display, use_container_width=True)
        else:
            st.info("Aucun point n'a encore été distribué.")
            
    else:
        match_selectionne = next(m for m in matchs_termines if f"{m['code_match']} vs {m['adversaire']}" == choix_vue)
        id_m = match_selectionne['id']
        
        pronos_journee = supabase.table("pronostics").select("nom_pote, points").eq("match_id", id_m).execute()
        
        if pronos_journee.data:
            df_j = pd.DataFrame(pronos_journee.data)
            df_j = df_j.sort_values(by="points", ascending=False).reset_index(drop=True)
            df_j.index += 1
            
            min_pts = df_j["points"].min()
            
            def attribuer_mention(pts):
                if pts == 15:
                    return "👑 Sans-faute !"
                elif pts == min_pts:
                    return "🍻 Paye ton Pack !"
                else:
                    return ""

            df_j["Mention"] = df_j["points"].apply(attribuer_mention)
            df_j_display = df_j.rename(columns={"nom_pote": "Joueur", "points": "Points"})
            
            def highlight_rows(row):
                if row["Mention"] == "👑 Sans-faute !":
                    return ['background-color: #90EE90; color: #000000; font-weight: bold'] * len(row) # Vert clair
                elif row["Mention"] == "🍻 Paye ton Pack !":
                    return ['background-color: #FFD700; color: #000000; font-weight: bold'] * len(row) # Jaune
                return [''] * len(row)
                
            styled_df = df_j_display.style.apply(highlight_rows, axis=1)
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.info("Aucun prono enregistré pour ce match.")
