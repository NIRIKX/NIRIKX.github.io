"""
Sitra - Module de capture d'écran réelle pour l'onglet "Optimiser mon site"
Utilise l'API Microlink (gratuite, sans clé obligatoire).
"""

import streamlit as st
import requests as req


# ── SÉLECTEUR CSS PAR CATÉGORIE D'ERREUR ──────────────────────────────────────
SELECTOR_RULES = [
    ("balise <title>",            None),
    ("titre trop court",          None),
    ("titre trop long",           None),
    ("meta description",          None),
    ("balise h1",                 "h1:first-of-type"),
    ("balises h1",                "h1:first-of-type"),
    ("aucun h2",                  "h2:first-of-type, h1:first-of-type"),
    ("attribut alt",              "img:not([alt]):first-of-type, img[alt='']:first-of-type, img:first-of-type"),
    ("images sans dimensions",    "img:first-of-type"),
    ("canonical",                 None),
    ("viewport",                  None),
    ("attribut lang",             None),
    ("balise <nav>",              "nav:first-of-type"),
    ("navigation principale",     "nav:first-of-type"),
    ("navigation surchargée",     "nav:first-of-type"),
    ("bouton d'action",           "button:first-of-type, .btn:first-of-type, .cta:first-of-type"),
    ("information de contact",    "footer"),
    ("formulaire(s) avec des",    "form:first-of-type"),
    ("pied de page",              "footer"),
    ("mentions légales",          "footer"),
    ("paragraphe(s) très long",   "p:first-of-type"),
    ("favicon",                   None),
    ("og:title",                  None),
    ("og:image",                  None),
    ("éléments avec des styles",  None),
    ("https",                     None),
    ("temps de réponse",          None),
    ("page html lourde",          None),
    ("page html assez lourde",    None),
    ("scripts dans le",           None),
]


def get_selector_for_issue(message: str):
    msg_lower = message.lower()
    for fragment, selector in SELECTOR_RULES:
        if fragment in msg_lower:
            return selector
    return None


# ── TEXTES SUR-MESURE PAR TYPE D'ERREUR ───────────────────────────────────────
# Pour chaque type d'erreur détecté par analyzer.py, un texte AVANT et APRÈS
# court, clair, sans jargon, qui dit exactement quoi regarder dans l'image.
ISSUE_TEXTS = {
    "balise <title>": (
        "#dc3545",
        "❌ Votre site n'a pas de titre<br><span style='font-weight:400;opacity:0.9'>👉 Regardez l'onglet du navigateur en haut — il est vide ou générique</span>",
        "✅ Ajoutez un titre clair<br><span style='font-weight:400;opacity:0.9'>Ex : « Boulangerie Martin — Pain artisanal à Lyon »</span>",
        "Le titre s'affiche dans l'onglet du navigateur et dans les résultats Google. Visez 50-60 caractères avec votre activité + ville."
    ),
    "titre trop court": (
        "#ffc107",
        "⚠️ Votre titre est trop court<br><span style='font-weight:400;opacity:0.9'>👉 Regardez l'onglet du navigateur — le titre est trop vague pour Google</span>",
        "✅ Allongez le titre<br><span style='font-weight:400;opacity:0.9'>Ex : « Coiffeur Paris 15 — Salon de coiffure femme et homme »</span>",
        "Un titre trop court n'informe pas assez Google sur votre activité. Ajoutez votre ville et spécialité pour atteindre 50-60 caractères."
    ),
    "titre trop long": (
        "#ffc107",
        "⚠️ Votre titre est trop long<br><span style='font-weight:400;opacity:0.9'>👉 Dans Google, il sera coupé au milieu et se terminera par «...»</span>",
        "✅ Raccourcissez le titre<br><span style='font-weight:400;opacity:0.9'>Gardez l'essentiel en moins de 60 caractères</span>",
        "Google coupe les titres après 60 caractères. Tout ce qui dépasse ne s'affiche pas dans les résultats de recherche."
    ),
    "meta description": (
        "#dc3545",
        "❌ Pas de description pour Google<br><span style='font-weight:400;opacity:0.9'>👉 Dans Google, sous votre lien, il y aura du texte aléatoire peu attrayant</span>",
        "✅ Ajoutez une description accrocheuse<br><span style='font-weight:400;opacity:0.9'>Ex : « Restaurant familial au cœur de Lyon. Menu du jour, pizzas maison. Ouvert 7j/7. »</span>",
        "La description apparaît sous votre lien dans Google. Une bonne description donne envie de cliquer. Visez 120-160 caractères."
    ),
    "balise h1": (
        "#dc3545",
        "❌ Pas de titre principal sur la page<br><span style='font-weight:400;opacity:0.9'>👉 Regardez la page — il n'y a aucun grand titre qui résume l'activité</span>",
        "✅ Ajoutez un grand titre bien visible<br><span style='font-weight:400;opacity:0.9'>Ex : « Plombier urgence Paris — Intervention en 1h »</span>",
        "Le titre H1 est le plus important de la page pour Google. Il doit résumer clairement votre activité en une phrase."
    ),
    "balises h1": (
        "#ffc107",
        "⚠️ Plusieurs grands titres identiques sur la page<br><span style='font-weight:400;opacity:0.9'>👉 Regardez la page — le même grand titre apparaît plusieurs fois, Google est perdu</span>",
        "✅ Gardez un seul grand titre H1<br><span style='font-weight:400;opacity:0.9'>Supprimez les doublons, gardez le plus pertinent</span>",
        "Une page ne doit avoir qu'un seul titre H1. Les doublons perturbent Google qui ne sait pas lequel prendre en compte."
    ),
    "aucun h2": (
        "#ffc107",
        "⚠️ Pas de sous-titres sur la page<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le contenu — tout le texte est au même niveau, sans structure</span>",
        "✅ Ajoutez des sous-titres pour structurer<br><span style='font-weight:400;opacity:0.9'>Ex : « Nos services », « Pourquoi nous choisir », « Contact »</span>",
        "Les sous-titres (H2) aident Google à comprendre les différentes parties de votre page et améliorent la lisibilité pour vos visiteurs."
    ),
    "attribut alt": (
        "#ffc107",
        "⚠️ Des images sans description<br><span style='font-weight:400;opacity:0.9'>👉 Regardez les images — Google voit des photos mais ne sait pas ce qu'elles montrent</span>",
        "✅ Décrivez chaque image en quelques mots<br><span style='font-weight:400;opacity:0.9'>Ex : « Photo de notre salle de restaurant » ou « Notre équipe de plombiers »</span>",
        "Les descriptions d'images (attribut alt) permettent à Google de les indexer et les afficher dans Google Images. C'est aussi utile pour les malvoyants."
    ),
    "images sans dimensions": (
        "#ffc107",
        "⚠️ Des images sans taille définie<br><span style='font-weight:400;opacity:0.9'>👉 La page peut \"sauter\" visuellement au chargement — les images se placent en décalé</span>",
        "✅ Définissez la largeur et hauteur de chaque image<br><span style='font-weight:400;opacity:0.9'>Le navigateur réservera la place avant même que l'image soit chargée</span>",
        "Sans dimensions, le navigateur ne sait pas quelle place réserver pour l'image. Ça crée des sauts visuels désagréables qui font fuir les visiteurs."
    ),
    "canonical": (
        "#ffc107",
        "⚠️ Pas de balise canonical<br><span style='font-weight:400;opacity:0.9'>👉 Google peut voir plusieurs versions de votre page comme des pages différentes</span>",
        "✅ Ajoutez une balise canonical dans le code<br><span style='font-weight:400;opacity:0.9'>Elle dit à Google quelle est la version officielle de votre page</span>",
        "La balise canonical évite que Google pénalise votre site pour du contenu dupliqué (ex: avec/sans www, http/https). Votre CMS peut l'ajouter automatiquement."
    ),
    "viewport": (
        "#dc3545",
        "❌ Le site n'est pas adapté aux mobiles<br><span style='font-weight:400;opacity:0.9'>👉 Sur smartphone, la page apparaîtra toute petite ou mal mise en page</span>",
        "✅ Ajoutez la balise viewport dans le code<br><span style='font-weight:400;opacity:0.9'>Une seule ligne de code qui rend votre site lisible sur tous les écrans</span>",
        "Plus de 60% des internautes naviguent sur mobile. Sans balise viewport, votre site s'affiche comme sur un écran d'ordinateur — illisible sur téléphone."
    ),
    "attribut lang": (
        "#ffc107",
        "⚠️ Google ne sait pas dans quelle langue est votre site<br><span style='font-weight:400;opacity:0.9'>👉 Sans indication de langue, Google peut proposer votre site à des internautes étrangers</span>",
        "✅ Indiquez la langue dans le code<br><span style='font-weight:400;opacity:0.9'>Ex : lang=\"fr\" pour un site en français</span>",
        "L'attribut de langue aide Google à proposer votre site aux bonnes personnes selon leur langue. C'est une ligne à ajouter dans le code HTML."
    ),
    "balise <nav>": (
        "#ffc107",
        "⚠️ Pas de menu de navigation détecté<br><span style='font-weight:400;opacity:0.9'>👉 Regardez en haut de la page — le menu n'est pas structuré correctement pour Google</span>",
        "✅ Structurez votre menu avec une balise nav<br><span style='font-weight:400;opacity:0.9'>Google comprendra mieux la structure de votre site</span>",
        "La balise nav indique à Google où se trouve le menu principal. Sans elle, Google peut mal comprendre la structure de votre site."
    ),
    "navigation surchargée": (
        "#ffc107",
        "⚠️ Trop de liens dans le menu<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le menu en haut — trop de choix noient le visiteur, il ne sait pas où cliquer</span>",
        "✅ Simplifiez le menu à 5-6 liens essentiels<br><span style='font-weight:400;opacity:0.9'>Ex : Accueil · Services · À propos · Contact · Réservation</span>",
        "Un menu surchargé perd les visiteurs. Gardez uniquement les pages les plus importantes et regroupez les autres dans des sous-menus si nécessaire."
    ),
    "bouton d'action": (
        "#dc3545",
        "❌ Pas de bouton d'action visible<br><span style='font-weight:400;opacity:0.9'>👉 Regardez la page — il n'y a aucun bouton clair pour que le visiteur passe à l'action</span>",
        "✅ Ajoutez un bouton bien visible<br><span style='font-weight:400;opacity:0.9'>Ex : « Prendre rendez-vous », « Demander un devis », « Commander »</span>",
        "Un bouton d'action (CTA) guide le visiteur vers ce qu'il doit faire. Sans lui, les visiteurs repartent sans vous contacter. Placez-le bien en vue."
    ),
    "information de contact": (
        "#dc3545",
        "❌ Pas d'informations de contact visibles<br><span style='font-weight:400;opacity:0.9'>👉 Regardez la page — impossible de trouver un numéro, email ou adresse facilement</span>",
        "✅ Affichez vos coordonnées clairement<br><span style='font-weight:400;opacity:0.9'>Téléphone, email et adresse doivent être visibles sans chercher</span>",
        "Si un visiteur ne trouve pas comment vous contacter en quelques secondes, il part chez un concurrent. Mettez vos contacts bien en vue, idéalement en haut de page."
    ),
    "formulaire(s) avec des": (
        "#ffc107",
        "⚠️ Des champs de formulaire sans étiquette<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le formulaire — certains champs n'ont pas de label explicatif à côté</span>",
        "✅ Ajoutez une étiquette à chaque champ<br><span style='font-weight:400;opacity:0.9'>Ex : « Votre nom », « Votre email », « Votre message »</span>",
        "Sans étiquette, les visiteurs ne savent pas quoi écrire dans chaque champ. C'est aussi problématique pour les malvoyants qui utilisent des lecteurs d'écran."
    ),
    "pied de page": (
        "#ffc107",
        "⚠️ Pas de pied de page<br><span style='font-weight:400;opacity:0.9'>👉 Scrollez tout en bas de la page — rien n'y figure, ni contact ni mentions légales</span>",
        "✅ Créez un pied de page avec l'essentiel<br><span style='font-weight:400;opacity:0.9'>Mentions légales, contact, liens utiles, réseaux sociaux</span>",
        "Le pied de page est obligatoire en France (mentions légales) et rassurant pour vos visiteurs. C'est aussi là qu'ils cherchent vos coordonnées."
    ),
    "mentions légales": (
        "#ffc107",
        "⚠️ Pas de mentions légales détectées<br><span style='font-weight:400;opacity:0.9'>👉 Scrollez en bas de la page — il n'y a pas de lien vers les mentions légales</span>",
        "✅ Ajoutez une page Mentions légales<br><span style='font-weight:400;opacity:0.9'>Obligatoire en France — nom de l'entreprise, contact, hébergeur, politique RGPD</span>",
        "Les mentions légales sont obligatoires pour tout site professionnel en France (loi du 21 juin 2004). Leur absence peut entraîner des sanctions."
    ),
    "paragraphe(s) très long": (
        "#ffc107",
        "⚠️ Des paragraphes trop longs<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le texte — de gros blocs de texte sans respiration découragent la lecture</span>",
        "✅ Découpez en paragraphes courts<br><span style='font-weight:400;opacity:0.9'>3-4 lignes maximum par paragraphe, avec des titres pour aérer</span>",
        "Les internautes lisent en diagonale. Des paragraphes courts avec des sous-titres rendent votre contenu bien plus lisible et professionnel."
    ),
    "contenu très court": (
        "#dc3545",
        "❌ Très peu de texte sur la page<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le contenu — il y a trop peu d'informations pour que Google comprenne votre activité</span>",
        "✅ Enrichissez le contenu de votre page<br><span style='font-weight:400;opacity:0.9'>Décrivez vos services, votre histoire, vos avantages — visez 300 mots minimum</span>",
        "Google favorise les pages avec du contenu riche. Moins de 300 mots, c'est insuffisant pour bien se positionner. Décrivez ce que vous faites en détail."
    ),
    "contenu assez court": (
        "#ffc107",
        "⚠️ Pas assez de texte sur la page<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le contenu — il manque des informations pour convaincre Google et vos visiteurs</span>",
        "✅ Ajoutez plus de contenu<br><span style='font-weight:400;opacity:0.9'>Décrivez vos services, votre zone d'intervention, vos tarifs, votre équipe</span>",
        "Plus votre page est riche en informations utiles, mieux Google la comprend et la propose aux internautes. Visez au moins 400-600 mots sur la page d'accueil."
    ),
    "erreurs de langue": (
        "#ffc107",
        "⚠️ Des erreurs de langue détectées<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le texte — certaines formulations peuvent sembler peu professionnelles</span>",
        "✅ Corrigez le texte avec un correcteur<br><span style='font-weight:400;opacity:0.9'>Utilisez Antidote, Grammalecte ou Word pour vérifier l'orthographe et la grammaire</span>",
        "Des fautes d'orthographe ou de grammaire donnent une mauvaise image de votre professionnalisme. Un correcteur gratuit suffit pour les éliminer."
    ),
    "mots très répétés": (
        "#ffc107",
        "⚠️ Des mots répétés trop souvent<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le texte — certains mots reviennent trop souvent et appauvrissent le contenu</span>",
        "✅ Variez le vocabulaire<br><span style='font-weight:400;opacity:0.9'>Utilisez des synonymes et des formulations différentes pour enrichir le texte</span>",
        "La répétition excessive de mots nuit à la qualité perçue du contenu. Google et vos visiteurs apprécient un vocabulaire varié et riche."
    ),
    "mots en majuscules": (
        "#ffc107",
        "⚠️ Trop de mots en majuscules<br><span style='font-weight:400;opacity:0.9'>👉 Regardez le texte — écrire en majuscules donne l'impression de crier sur le visiteur</span>",
        "✅ Passez en minuscules avec majuscule en début<br><span style='font-weight:400;opacity:0.9'>Réservez les majuscules aux titres importants uniquement</span>",
        "Les textes en majuscules sont perçus comme agressifs et peu professionnels. Ils sont aussi plus difficiles à lire. Utilisez-les avec parcimonie."
    ),
    "favicon": (
        "#ffc107",
        "⚠️ Pas d'icône de site (favicon)<br><span style='font-weight:400;opacity:0.9'>👉 Regardez l'onglet du navigateur en haut — il n'y a pas de petite icône à côté du nom</span>",
        "✅ Ajoutez votre logo en icône<br><span style='font-weight:400;opacity:0.9'>Une petite image de 32x32 pixels qui s'affiche dans l'onglet et les favoris</span>",
        "Le favicon renforce l'identité de votre marque. C'est un petit détail qui rend le site plus professionnel et mémorable."
    ),
    "og:title": (
        "#ffc107",
        "⚠️ Partage sur réseaux sociaux non configuré<br><span style='font-weight:400;opacity:0.9'>👉 Si quelqu'un partage votre lien sur Facebook ou WhatsApp, aucune image ni titre ne s'affichera automatiquement</span>",
        "✅ Configurez l'aperçu de partage<br><span style='font-weight:400;opacity:0.9'>Titre, description et image s'afficheront automatiquement quand on partage votre lien</span>",
        "Les balises Open Graph contrôlent comment votre site apparaît quand quelqu'un partage votre lien. Sans elles, l'aperçu est vide et peu attractif."
    ),
    "og:image": (
        "#ffc107",
        "⚠️ Pas d'image de partage configurée<br><span style='font-weight:400;opacity:0.9'>👉 Quand votre lien est partagé sur les réseaux, aucune image ne s'affiche — juste du texte brut</span>",
        "✅ Ajoutez une image de partage<br><span style='font-weight:400;opacity:0.9'>Une belle photo de votre établissement ou de vos produits qui apparaîtra automatiquement</span>",
        "Une image de partage attractive augmente considérablement le taux de clic quand votre lien est partagé sur Facebook, LinkedIn ou WhatsApp."
    ),
    "éléments avec des styles": (
        "#ffc107",
        "⚠️ Le code de mise en forme est dispersé<br><span style='font-weight:400;opacity:0.9'>👉 Ce problème est invisible à l'écran mais alourdit votre site et le rend plus lent à charger</span>",
        "✅ Regroupez les styles dans un fichier CSS<br><span style='font-weight:400;opacity:0.9'>Un site mieux organisé charge plus vite et est plus facile à modifier</span>",
        "Des styles dispersés dans le code HTML alourdissent chaque page. Un fichier CSS centralisé améliore les performances et simplifie la maintenance."
    ),
    "https": (
        "#dc3545",
        "❌ Votre site n'est pas sécurisé<br><span style='font-weight:400;opacity:0.9'>👉 Regardez la barre d'adresse en haut — il y a « http:// » au lieu de « https:// » et un cadenas barré</span>",
        "✅ Activez le certificat SSL (HTTPS)<br><span style='font-weight:400;opacity:0.9'>Un cadenas 🔒 apparaîtra — vos visiteurs auront confiance</span>",
        "Un site non sécurisé affiche une alerte « Non sécurisé » dans les navigateurs. C'est gratuit à corriger (Let's Encrypt) et ça booste votre référencement Google."
    ),
    "temps de réponse": (
        "#dc3545",
        "❌ Votre site charge trop lentement<br><span style='font-weight:400;opacity:0.9'>👉 Votre site met plusieurs secondes à s'afficher — 53% des visiteurs partent avant 3 secondes</span>",
        "✅ Optimisez la vitesse de chargement<br><span style='font-weight:400;opacity:0.9'>Compressez vos images sur tinypng.com et supprimez les plugins inutiles</span>",
        "La vitesse est un critère important pour Google et pour vos visiteurs. Commencez par compresser vos images — c'est souvent la cause principale de lenteur."
    ),
    "page html lourde": (
        "#ffc107",
        "⚠️ Le code de votre page est très lourd<br><span style='font-weight:400;opacity:0.9'>👉 Ce problème est invisible à l'écran mais ralentit le chargement pour vos visiteurs</span>",
        "✅ Allégez le code HTML<br><span style='font-weight:400;opacity:0.9'>Supprimez les scripts inutiles et nettoyez le code en trop</span>",
        "Un code HTML trop lourd ralentit votre site. Vérifiez avec votre développeur ou votre CMS qu'il n'y a pas de code inutile qui alourdit chaque page."
    ),
    "scripts dans le": (
        "#ffc107",
        "⚠️ Des scripts bloquent le chargement<br><span style='font-weight:400;opacity:0.9'>👉 Des fichiers JavaScript chargés trop tôt retardent l'affichage de votre page</span>",
        "✅ Déplacez les scripts en bas de page<br><span style='font-weight:400;opacity:0.9'>La page s'affichera plus vite — les scripts se chargeront après le contenu visible</span>",
        "Les scripts JavaScript dans l'en-tête bloquent l'affichage de la page. En les déplaçant en bas (avant </body>), la page apparaît plus rapidement pour vos visiteurs."
    ),
}


def get_issue_texts(message: str):
    """
    Retourne (badge_color, before_text, after_text, conseil) adapté au message d'erreur.
    Cherche une correspondance dans ISSUE_TEXTS, ou génère un texte générique.
    """
    msg_lower = message.lower()
    for fragment, texts in ISSUE_TEXTS.items():
        if fragment in msg_lower:
            return texts

    # Fallback générique si aucune correspondance
    is_critical = message.strip().startswith("❌")
    badge_color = "#dc3545" if is_critical else "#ffc107"
    clean_msg = message.replace("❌", "").replace("⚠️", "").strip()
    if " — " in clean_msg:
        probleme, explication = clean_msg.split(" — ", 1)
    else:
        probleme, explication = clean_msg, ""
    icon = "❌" if is_critical else "⚠️"
    before_text = f"{icon} {probleme}<br><span style='font-weight:400;opacity:0.9'>{explication}</span>" if explication else f"{icon} {probleme}"
    after_text = f"✅ Point corrigé<br><span style='font-weight:400;opacity:0.9'>{explication}</span>" if explication else "✅ Point corrigé"
    conseil = explication if explication else probleme
    return badge_color, before_text, after_text, conseil


def generic_before_after(message: str):
    """Rétrocompatibilité — utilise maintenant get_issue_texts."""
    return get_issue_texts(message)


# ── RÉCUPÉRATION DE LA CAPTURE (PLEINE PAGE) ─────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_screenshot(url: str):
    return _microlink_screenshot(url, element=None)


@st.cache_data(ttl=3600, show_spinner=False)
def get_screenshot_zone(url: str, selector: str):
    """
    Essaie d'abord Playwright (cadre rouge precis sur l'element).
    Si Playwright echoue, retombe sur Microlink (capture ciblee).
    Si Microlink echoue aussi, retombe sur la capture pleine page.
    """
    # Essai 1 : Playwright avec cadre rouge precis
    if selector:
        try:
            from playwright_capture import get_screenshot_with_highlight
            data_uri, was_targeted = get_screenshot_with_highlight(url, selector)
            if data_uri:
                return data_uri, True
        except Exception:
            pass

    # Essai 2 : Microlink avec selecteur CSS
    if selector:
        targeted = _microlink_screenshot(url, element=selector)
        if targeted:
            return targeted, True

    # Essai 3 : capture pleine page
    fallback = get_screenshot(url)
    return fallback, False


def _microlink_screenshot(url: str, element=None):
    try:
        headers = {}
        try:
            api_key = st.secrets.get("MICROLINK_API_KEY", "")
            if api_key:
                headers["x-api-key"] = api_key
        except Exception:
            pass

        params = {"url": url, "screenshot": "true", "meta": "false"}
        if element:
            # Microlink attend un seul sélecteur CSS — on garde seulement le premier
            params["screenshot.element"] = element.split(",")[0].strip()

        r = req.get("https://api.microlink.io", params=params, headers=headers, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("status") != "success":
            return None
        return data.get("data", {}).get("screenshot", {}).get("url")
    except Exception:
        return None


# ── BLOC AVANT / APRÈS AVEC CAPTURE CIBLÉE ────────────────────────────────────
def render_before_after_block(screenshot_url, error_num, badge_color, before_text, after_text, conseil, was_targeted=False, img_uid="", is_duplicate=False):
    badge_icon = "❌" if badge_color == "#dc3545" else "⚠️"
    uid = img_uid or f"img{error_num}"

    if is_duplicate:
        precision_note = '<div style="font-size:10px;color:#999;margin-top:4px;font-style:italic">📍 Cette zone regroupe plusieurs éléments — le texte ci-dessus décrit précisément le problème</div>'
    elif was_targeted:
        precision_note = '<div style="font-size:10px;color:#7ddf96;margin-top:4px">🎯 Zone exacte capturée</div>'
    else:
        precision_note = '<div style="font-size:10px;color:#999;margin-top:4px;font-style:italic">📍 Vue générale du site</div>'

    return f"""
<div style="margin-bottom:28px">
  <div style="font-size:11px;font-weight:700;color:{badge_color};text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
    {badge_icon} ERREUR {error_num}
  </div>
  <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:start">

    <div>
      <div style="font-size:10px;color:{badge_color};font-weight:700;margin-bottom:6px;text-transform:uppercase">AVANT — Capture réelle de votre site</div>
      <div style="position:relative;border:2px solid {badge_color};border-radius:10px;overflow:hidden;background:#111;cursor:zoom-in" onclick="document.getElementById('modal_{uid}_before').style.display='flex'">
        <img src="{screenshot_url}" style="width:100%;display:block" />
        <div style="position:absolute;top:0;left:0;right:0;background:linear-gradient(180deg,{badge_color}f0,{badge_color}00);padding:10px 12px 28px;color:white;font-size:12px;font-weight:600;line-height:1.5">
          {before_text}
        </div>
        <div style="position:absolute;bottom:6px;right:8px;background:rgba(0,0,0,0.6);color:white;font-size:10px;padding:2px 8px;border-radius:10px">🔍 Cliquer pour zoomer</div>
      </div>
      {precision_note}
    </div>

    <div style="display:flex;align-items:center;font-size:24px;color:#7c6af7;padding:0 4px;align-self:center">→</div>

    <div>
      <div style="font-size:10px;color:#28a745;font-weight:700;margin-bottom:6px;text-transform:uppercase">APRÈS — Correction proposée par SITRA</div>
      <div style="position:relative;border:2px solid #28a745;border-radius:10px;overflow:hidden;background:#111;cursor:zoom-in" onclick="document.getElementById('modal_{uid}_after').style.display='flex'">
        <img src="{screenshot_url}" style="width:100%;display:block;filter:brightness(0.8)" />
        <div style="position:absolute;top:0;left:0;right:0;background:linear-gradient(180deg,#28a745f0,#28a74500);padding:10px 12px 28px;color:white;font-size:12px;font-weight:600;line-height:1.5">
          {after_text}
        </div>
        <div style="position:absolute;bottom:6px;right:8px;background:rgba(0,0,0,0.6);color:white;font-size:10px;padding:2px 8px;border-radius:10px">🔍 Cliquer pour zoomer</div>
      </div>
    </div>

  </div>
  <div style="margin-top:8px;background:rgba(124,106,247,0.1);border-left:3px solid #7c6af7;padding:7px 12px;border-radius:0 6px 6px 0;font-size:12px;color:#b090f7">
    💡 {conseil}
  </div>
</div>

<div id="modal_{uid}_before" onclick="this.style.display='none'" style="display:none;position:fixed;z-index:9999;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);cursor:zoom-out;align-items:center;justify-content:center;padding:20px">
  <img src="{screenshot_url}" style="max-width:95%;max-height:95%;border:3px solid {badge_color};border-radius:8px" />
</div>
<div id="modal_{uid}_after" onclick="this.style.display='none'" style="display:none;position:fixed;z-index:9999;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);cursor:zoom-out;align-items:center;justify-content:center;padding:20px">
  <img src="{screenshot_url}" style="max-width:95%;max-height:95%;border:3px solid #28a745;border-radius:8px" />
</div>
"""


# ── BLOC DE SECOURS (fallback, sans capture du tout) ─────────────────────────
def render_fallback_block(error_num, badge_color, before_text, after_text, conseil):
    badge_icon = "❌" if badge_color == "#dc3545" else "⚠️"
    return f"""
<div style="margin-bottom:24px">
  <div style="font-size:11px;font-weight:700;color:{badge_color};text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
    {badge_icon} ERREUR {error_num} <span style="color:#666;font-weight:400;text-transform:none">(capture indisponible pour ce site)</span>
  </div>
  <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:stretch">
    <div style="background:#1a0808;border:2px solid {badge_color};border-radius:10px;padding:16px;color:white;font-size:13px;line-height:1.6">{before_text}</div>
    <div style="display:flex;align-items:center;font-size:24px;color:#7c6af7;padding:0 4px;align-self:center">→</div>
    <div style="background:#081a08;border:2px solid #28a745;border-radius:10px;padding:16px;color:white;font-size:13px;line-height:1.6">{after_text}</div>
  </div>
  <div style="margin-top:8px;background:rgba(124,106,247,0.1);border-left:3px solid #7c6af7;padding:7px 12px;border-radius:0 6px 6px 0;font-size:12px;color:#b090f7">
    💡 {conseil}
  </div>
</div>
"""
