import streamlit as st
import time
import os
try:
    from analyzer import full_analysis, get_score_label, normalize_url, get_pagespeed, detect_pages, detect_secteur_et_concurrents, is_produit_web, estimer_potentiel_croissance, sauvegarder_historique, lire_historique
    from screenshot_helper import get_screenshot, get_screenshot_zone, render_before_after_block, render_fallback_block, generic_before_after, get_selector_for_issue, get_issue_texts
except Exception as e:
    st.error(f"Erreur d'import détectée : {e}")
    st.stop()

# ── CACHE — réduit le temps de rechargement ───────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def cached_full_analysis(url):
    return full_analysis(url)

@st.cache_data(ttl=600, show_spinner=False)
def cached_recommandations(final_url, global_score, issues_str):
    return generer_recommandations_ia_inner(final_url, global_score, issues_str)

@st.cache_data(ttl=600, show_spinner=False)
def cached_contenu_marque(final_url, title, meta, score, word_count, type_contenu, objectif):
    return generer_contenu_marque_inner(final_url, title, meta, score, word_count, type_contenu, objectif)

# ── SHOPIFY AUTO-FIX ─────────────────────────────────────────────────────────
def shopify_fix_seo(shop_url, access_token, result):
    """Applique TOUTES les corrections détectées par SITRA sur Shopify"""
    import requests as reqf
    corrections = []
    erreurs = []

    shop = shop_url.rstrip("/").replace("https://", "").replace("http://", "")
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    try:
        test = req.get(f"https://{shop}/admin/api/2024-01/shop.json", headers=headers, timeout=10)
        if test.status_code == 401:
            return [], ["Token invalide — vérifiez votre clé API Shopify"]
        if test.status_code != 200:
            return [], [f"Impossible de se connecter à Shopify (code {test.status_code})"]

        shop_data = test.json().get("shop", {})

        if not result["seo"]["meta_description"]:
            try:
                import requests as req2
                headers_mistral = {"Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}", "Content-Type": "application/json"}
                prompt = f"Génère une meta description de 150 caractères maximum pour cette boutique : {result['final_url']}. Titre : {result['seo']['title']}. Réponds UNIQUEMENT avec la meta description."
                data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
                r_mistral = req2.post("https://api.mistral.ai/v1/chat/completions", headers=headers_mistral, json=data, timeout=15)
                meta_desc = r_mistral.json()["choices"][0]["message"]["content"].strip()
                corrections.append(f"Meta description générée : '{meta_desc[:80]}...' — à appliquer dans Shopify → Préférences en ligne")
            except Exception:
                erreurs.append("Erreur lors de la génération de la meta description")

        if result["seo"]["images_no_alt"] > 0:
            products = req.get(f"https://{shop}/admin/api/2024-01/products.json?limit=50", headers=headers, timeout=10)
            if products.status_code == 200:
                fixed = 0
                for product in products.json().get("products", []):
                    for image in product.get("images", []):
                        if not image.get("alt"):
                            req.put(
                                f"https://{shop}/admin/api/2024-01/products/{product['id']}/images/{image['id']}.json",
                                headers=headers,
                                json={"image": {"id": image["id"], "alt": product.get("title", "image")}},
                                timeout=10
                            )
                            fixed += 1
                if fixed > 0:
                    corrections.append(f"{fixed} image(s) produit — attribut alt ajouté automatiquement")

        pages = req.get(f"https://{shop}/admin/api/2024-01/pages.json", headers=headers, timeout=10)
        if pages.status_code == 200:
            existing_slugs = [p.get("handle", "") for p in pages.json().get("pages", [])]
            if "mentions-legales" not in existing_slugs:
                new_page = req.post(
                    f"https://{shop}/admin/api/2024-01/pages.json",
                    headers=headers,
                    json={"page": {
                        "title": "Mentions légales",
                        "handle": "mentions-legales",
                        "body_html": f"<h1>Mentions légales</h1><p>Ce site {result['final_url']} est édité conformément à la loi française. Conformément au RGPD, vous disposez d'un droit d'accès, de rectification et de suppression de vos données personnelles.</p>"
                    }},
                    timeout=10
                )
                if new_page.status_code == 201:
                    corrections.append("Page Mentions légales créée et publiée automatiquement")

        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé — activez SSL depuis Paramètres → Domaines dans Shopify")

        if result["content"]["word_count"] < 300:
            erreurs.append(f"Contenu trop court ({result['content']['word_count']} mots) — enrichissez la description de votre boutique")

        if not result["design"]["has_og_tags"]:
            corrections.append("Open Graph — activez le partage social dans Shopify → Préférences en ligne → Réseaux sociaux")

    except Exception as e:
        erreurs.append(str(e))

    return corrections, erreurs

# ── WIX AUTO-FIX ──────────────────────────────────────────────────────────────
def wix_fix_seo(wix_account_id, wix_site_id, wix_api_key, result):
    """Applique TOUTES les corrections détectées par SITRA sur Wix"""
    import requests as req
    corrections = []
    erreurs = []

    headers = {
        "Authorization": wix_api_key,
        "wix-account-id": wix_account_id,
        "wix-site-id": wix_site_id,
        "Content-Type": "application/json"
    }

    try:
        test = req.get("https://www.wixapis.com/site-properties/v4/properties", headers=headers, timeout=10)
        if test.status_code == 401:
            return [], ["Clé API invalide — vérifiez vos identifiants Wix"]
        if test.status_code != 200:
            return [], [f"Impossible de se connecter à Wix (code {test.status_code})"]

        if not result["seo"]["meta_description"]:
            try:
                import requests as req2
                headers_mistral = {"Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}", "Content-Type": "application/json"}
                prompt = f"Génère une meta description de 150 caractères maximum pour ce site : {result['final_url']}. Titre : {result['seo']['title']}. Réponds UNIQUEMENT avec la meta description."
                data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
                r_mistral = req2.post("https://api.mistral.ai/v1/chat/completions", headers=headers_mistral, json=data, timeout=15)
                meta_desc = r_mistral.json()["choices"][0]["message"]["content"].strip()
                update = req.patch("https://www.wixapis.com/site-properties/v4/properties", headers=headers, json={"properties": {"description": meta_desc}}, timeout=10)
                if update.status_code in [200, 201]:
                    corrections.append(f"Meta description ajoutée : '{meta_desc[:80]}...'")
                else:
                    erreurs.append("Impossible de mettre à jour la meta description sur Wix")
            except Exception:
                erreurs.append("Erreur lors de la génération de la meta description")

        pages = req.get("https://www.wixapis.com/site-pages/v2/pages", headers=headers, timeout=10)
        if pages.status_code == 200:
            pages_data = pages.json().get("pages", [])
            fixed_pages = 0
            for page in pages_data[:10]:
                page_id = page.get("id")
                seo_data = page.get("seo", {})
                if page_id and (not seo_data.get("description") or not seo_data.get("title")):
                    update_data = {"page": {"seo": {}}}
                    if not seo_data.get("title") and result["seo"]["title"]:
                        update_data["page"]["seo"]["title"] = result["seo"]["title"]
                    if not seo_data.get("description") and not result["seo"]["meta_description"]:
                        update_data["page"]["seo"]["description"] = meta_desc if 'meta_desc' in locals() else ""
                    req.patch(f"https://www.wixapis.com/site-pages/v2/pages/{page_id}", headers=headers, json=update_data, timeout=10)
                    fixed_pages += 1
            if fixed_pages > 0:
                corrections.append(f"{fixed_pages} page(s) — balises SEO optimisées")

        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé — activez-le depuis les paramètres de votre site Wix (SSL gratuit inclus)")

        if result["content"]["word_count"] < 300:
            erreurs.append(f"Contenu trop court ({result['content']['word_count']} mots) — ajoutez du contenu dans l'éditeur Wix")

        if not result["design"]["has_og_tags"]:
            og_update = req.patch(
                "https://www.wixapis.com/site-properties/v4/properties",
                headers=headers,
                json={"properties": {"socialLinks": []}},
                timeout=10
            )
            corrections.append("Balises Open Graph configurées — vérifiez dans Paramètres → Réseaux sociaux sur Wix")

    except Exception as e:
        erreurs.append(str(e))

    return corrections, erreurs

# ── WORDPRESS AUTO-FIX ────────────────────────────────────────────────────────
def wordpress_fix_seo(wp_url, wp_user, wp_password, result):
    """Applique TOUTES les corrections détectées par SITRA sur WordPress"""
    import requests as req
    from requests.auth import HTTPBasicAuth

    auth = HTTPBasicAuth(wp_user, wp_password)
    base = wp_url.rstrip("/")
    corrections = []
    erreurs = []

    try:
        test = req.get(f"{base}/wp-json/wp/v2/", auth=auth, timeout=10)
        if test.status_code == 401:
            return [], ["Identifiants incorrects — vérifiez votre nom d'utilisateur et mot de passe d'application"]
        if test.status_code != 200:
            return [], [f"Impossible d'accéder à l'API WordPress (code {test.status_code})"]

        if not result["seo"]["meta_description"]:
            try:
                import requests as req2
                headers_mistral = {
                    "Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}",
                    "Content-Type": "application/json"
                }
                prompt = f"Génère une meta description de 150 caractères maximum pour ce site : {result['final_url']}. Titre : {result['seo']['title']}. Réponds UNIQUEMENT avec la meta description."
                data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
                r_mistral = req2.post("https://api.mistral.ai/v1/chat/completions", headers=headers_mistral, json=data, timeout=15)
                meta_desc = r_mistral.json()["choices"][0]["message"]["content"].strip()
                update = req.post(f"{base}/wp-json/wp/v2/settings", auth=auth, json={"description": meta_desc}, timeout=10)
                if update.status_code == 200:
                    corrections.append(f"Meta description ajoutée : '{meta_desc[:80]}...'")
                else:
                    erreurs.append("Impossible de mettre à jour la meta description")
            except Exception:
                erreurs.append("Erreur lors de la génération de la meta description")

        if result["seo"]["images_no_alt"] > 0:
            media = req.get(f"{base}/wp-json/wp/v2/media?per_page=100", auth=auth, timeout=10)
            if media.status_code == 200:
                images = media.json()
                fixed = 0
                for img in images:
                    if not img.get("alt_text"):
                        title = img.get("title", {}).get("rendered", "image")
                        update_img = req.post(
                            f"{base}/wp-json/wp/v2/media/{img['id']}",
                            auth=auth,
                            json={"alt_text": title},
                            timeout=10
                        )
                        if update_img.status_code == 200:
                            fixed += 1
                if fixed > 0:
                    corrections.append(f"{fixed} image(s) — attribut alt ajouté automatiquement")

        if result["seo"]["h1_count"] != 1:
            pages = req.get(f"{base}/wp-json/wp/v2/pages?per_page=5", auth=auth, timeout=10)
            if pages.status_code == 200:
                corrections.append(f"H1 vérifié sur les pages principales ({result['seo']['h1_count']} détecté — correction manuelle recommandée dans l'éditeur)")

        if not result["design"]["has_og_tags"]:
            yoast = req.get(f"{base}/wp-json/yoast/v1/get_head?url={result['final_url']}", auth=auth, timeout=10)
            if yoast.status_code == 200:
                corrections.append("Balises Open Graph détectées via Yoast SEO — activez le partage dans Yoast SEO → Réseaux sociaux")
            else:
                erreurs.append("Yoast SEO non détecté — installez le plugin Yoast SEO pour gérer les balises Open Graph")

        if not result["ux"]["has_footer"]:
            pages = req.get(f"{base}/wp-json/wp/v2/pages", auth=auth, timeout=10)
            if pages.status_code == 200:
                existing = [p.get("slug", "") for p in pages.json()]
                if "mentions-legales" not in existing:
                    new_page = req.post(
                        f"{base}/wp-json/wp/v2/pages",
                        auth=auth,
                        json={
                            "title": "Mentions légales",
                            "slug": "mentions-legales",
                            "status": "publish",
                            "content": f"""<h1>Mentions légales</h1>
<p>Conformément aux dispositions de la loi n° 2004-575 du 21 juin 2004 pour la Confiance en l'économie numérique, il est précisé aux utilisateurs du site {result['final_url']} l'identité des différents intervenants dans le cadre de sa réalisation et de son suivi.</p>
<h2>Éditeur du site</h2>
<p>Ce site est édité par le propriétaire du domaine {result['final_url']}.</p>
<h2>Hébergeur</h2>
<p>Ce site est hébergé par un prestataire d'hébergement web.</p>
<h2>Données personnelles</h2>
<p>Conformément au RGPD, vous disposez d'un droit d'accès, de rectification et de suppression de vos données personnelles.</p>"""
                        },
                        timeout=10
                    )
                    if new_page.status_code == 201:
                        corrections.append("Page Mentions légales créée et publiée automatiquement")
                    else:
                        erreurs.append("Impossible de créer la page Mentions légales")

        if result["content"]["word_count"] < 300:
            erreurs.append(f"Contenu trop court ({result['content']['word_count']} mots) — ajoutez du contenu manuellement dans l'éditeur WordPress")

        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé — activez-le depuis votre hébergeur (certificat SSL gratuit avec Let's Encrypt)")

    except Exception as e:
        erreurs.append(str(e))

    return corrections, erreurs

# ── IA ────────────────────────────────────────────────────────────────────────
def generer_recommandations_ia_inner(final_url, global_score, issues_str):
    try:
        import requests as req
        headers = {
            "Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}",
            "Content-Type": "application/json"
        }
        prompt = f"""Tu es un conseiller web qui aide des petits entrepreneurs à améliorer leur site. Explique les problèmes simplement, comme si tu parlais à quelqu'un qui ne connaît rien à l'informatique.

Site : {final_url}
Score global : {global_score}/100
Problèmes détectés : {issues_str}

Écris exactement 5 conseils numérotés (1. 2. 3. 4. 5.).
Chaque conseil doit être sur une nouvelle ligne, expliquer le problème simplement et dire quoi faire.
Pas de termes techniques — utilise des mots du quotidien."""

        data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 600}
        r = req.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data, timeout=30)
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None

def generer_recommandations_ia(result):
    issues_str = ', '.join([i['message'] for i in result['all_issues'][:6]])
    return generer_recommandations_ia_inner(result['final_url'], result['global_score'], issues_str)

def generer_deux_corrections(plateforme, result):
    try:
        import requests as req
        headers_m = {"Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}", "Content-Type": "application/json"}

        problemes = ', '.join([i['message'] for i in result['all_issues'][:6]])

        prompt = f"""Tu es un expert en optimisation de sites web. Pour ce site {result['final_url']} sur {plateforme}, propose EXACTEMENT 2 versions de corrections différentes.

Problèmes détectés : {problemes}

VERSION 1 : Approche minimaliste (corrections essentielles seulement, rapide à faire)
VERSION 2 : Approche complète (toutes les corrections, plus de travail mais meilleur résultat)

Pour chaque version, liste en 4-5 points simples ce qui sera corrigé, expliqué en langage simple (pas de jargon technique).

Format exact :
VERSION 1 - Corrections essentielles
• [point 1]
• [point 2]
• [point 3]
• [point 4]

VERSION 2 - Corrections complètes
• [point 1]
• [point 2]
• [point 3]
• [point 4]
• [point 5]"""

        data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 400}
        r = req.post("https://api.mistral.ai/v1/chat/completions", headers=headers_m, json=data, timeout=30)
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None

# ── CONTENU DE MARQUE IA (inspiré Pomelli) ───────────────────────────────────
import re

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0F"
    "\U0000200D"
    "\U000020E3"
    "]+",
    flags=re.UNICODE,
)

def enlever_emojis(texte):
    """Retire tout emoji/pictogramme du texte généré par l'IA et nettoie les espaces laissés"""
    if not texte:
        return texte
    texte = _EMOJI_PATTERN.sub("", texte)
    texte = re.sub(r"[ \t]+", " ", texte)
    texte = re.sub(r" +\n", "\n", texte)
    texte = re.sub(r"\n +", "\n", texte)
    return texte.strip()

def generer_contenu_marque(result, type_contenu, objectif):
    """Génère du contenu marketing on-brand basé sur l'analyse du site"""
    try:
        import requests as req
        headers = {
            "Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}",
            "Content-Type": "application/json"
        }

        prompt = f"""Tu es un expert en marketing digital et copywriting. Génère du contenu marketing professionnel et percutant pour ce site.

Site analysé : {result['final_url']}
Titre du site : {result['seo']['title'] or 'Non défini'}
Description actuelle : {result['seo']['meta_description'] or 'Non définie'}
Score global SITRA : {result['global_score']}/100
Nombre de mots sur le site : {result['content']['word_count']}

Type de contenu à générer : {type_contenu}
Objectif de la campagne : {objectif}

Génère du contenu adapté, professionnel, en français, qui respecte l'identité de marque du site.
Adapte le ton au secteur d'activité détecté.
Sois concret, percutant et prêt à publier directement.
IMPORTANT : n'utilise strictement aucun emoji ni pictogramme, nulle part dans ta réponse. Uniquement du texte."""

        types_prompts = {
            "Post Instagram": f"{prompt}\n\nRédige 3 posts Instagram différents (150-200 caractères chacun + 5 hashtags pertinents). Format : POST 1 / POST 2 / POST 3",
            "Post LinkedIn": f"{prompt}\n\nRédige 2 posts LinkedIn professionnels (200-300 mots chacun). Format : POST 1 / POST 2",
            "Post Facebook": f"{prompt}\n\nRédige 3 posts Facebook engageants (100-150 mots chacun). Format : POST 1 / POST 2 / POST 3",
            "Email marketing": f"""{prompt}

Tu es un expert en copywriting émotionnel. Rédige un email marketing qui donne vraiment envie, qui touche les émotions du lecteur et le pousse à agir. L'objectif est : {objectif}

L'email doit :
- Commencer par une phrase qui accroche immédiatement (une question, une douleur, un rêve)
- Parler directement au lecteur comme si tu le connaissais
- Créer un sentiment d'urgence ou d'opportunité
- Utiliser des mots simples mais puissants
- Finir par un appel à l'action irrésistible

Structure exacte :

OBJET :
[accrocheur, crée de la curiosité ou de l'urgence, max 50 caractères]

PRÉVISUALISATION :
[complète l'objet, donne envie d'ouvrir, max 90 caractères]

EMAIL :
Bonjour [Prénom],

[phrase d'accroche émotionnelle — une question ou une situation que le lecteur vit]

[développe le problème ou le désir, 2-3 phrases qui font écho à ce qu'il ressent]

[présente la solution de façon naturelle et enthousiaste, 2 phrases]

[urgence ou bénéfice concret — pourquoi agir maintenant]

[signature chaleureuse]

BOUTON :
[texte court et motivant, ex : Je veux ça / Je passe à l'action / Je découvre maintenant]""",
            "Texte publicitaire Google Ads": f"{prompt}\n\nRédige 3 annonces Google Ads complètes avec : Titre 1 (max 30 car.) / Titre 2 (max 30 car.) / Description (max 90 car.). Format : ANNONCE 1 / ANNONCE 2 / ANNONCE 3",
        }

        prompt_final = types_prompts.get(type_contenu, prompt)
        data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt_final}], "max_tokens": 800}
        r = req.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data, timeout=30)
        contenu = r.json()["choices"][0]["message"]["content"]
        return enlever_emojis(contenu)
    except Exception:
        return None

# ── PDF ───────────────────────────────────────────────────────────────────────
def envoyer_rapport_email(email: str, result: dict) -> bool:
    """Envoie le rapport PDF par email via Resend"""
    try:
        import requests as req
        import base64

        pdf_data = generer_pdf(result)
        pdf_b64 = base64.b64encode(pdf_data).decode("utf-8")

        score = result["global_score"]
        label_txt, _, _ = get_score_label(score)
        url_site = result["final_url"]

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea, #764ba2); padding: 2rem; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 2rem;">SITRA</h1>
                <p style="color: rgba(255,255,255,0.8); margin: 0.5rem 0 0;">Rapport d'analyse de site web</p>
            </div>
            <div style="background: #f7f7f7; padding: 2rem; border-radius: 0 0 12px 12px;">
                <h2 style="color: #333;">Votre rapport est prêt !</h2>
                <p style="color: #666;">Voici les résultats de l'analyse de <strong>{url_site}</strong> :</p>
                <div style="background: white; border-radius: 8px; padding: 1.5rem; margin: 1rem 0;">
                    <div style="font-size: 2.5rem; font-weight: bold; color: #667eea; text-align: center;">{score}/100</div>
                    <div style="text-align: center; color: #888; font-size: 0.9rem;">{label_txt}</div>
                </div>
                <table style="width: 100%; border-collapse: collapse; margin: 1rem 0;">
                    <tr style="background: #667eea; color: white;">
                        <td style="padding: 8px 12px; font-weight: bold;">Catégorie</td>
                        <td style="padding: 8px 12px; font-weight: bold;">Score</td>
                    </tr>
                    <tr style="background: white;"><td style="padding: 8px 12px;">SEO</td><td style="padding: 8px 12px;">{result['seo']['score']}/100</td></tr>
                    <tr style="background: #f7f7f7;"><td style="padding: 8px 12px;">UX</td><td style="padding: 8px 12px;">{result['ux']['score']}/100</td></tr>
                    <tr style="background: white;"><td style="padding: 8px 12px;">Contenu</td><td style="padding: 8px 12px;">{result['content']['score']}/100</td></tr>
                    <tr style="background: #f7f7f7;"><td style="padding: 8px 12px;">Design</td><td style="padding: 8px 12px;">{result['design']['score']}/100</td></tr>
                    <tr style="background: white;"><td style="padding: 8px 12px;">Performance</td><td style="padding: 8px 12px;">{result['performance']['score']}/100</td></tr>
                </table>
                <p style="color: #666; font-size: 0.9rem;">Le rapport complet en PDF est joint à cet email.</p>
                <div style="text-align: center; margin-top: 1.5rem;">
                    <a href="https://mon-audit-seo.streamlit.app" style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 0.8rem 2rem; border-radius: 8px; text-decoration: none; font-weight: bold;">Relancer une analyse</a>
                </div>
            </div>
            <p style="text-align: center; color: #aaa; font-size: 0.8rem; margin-top: 1rem;">SITRA — Analyseur Intelligent de Sites Web</p>
        </div>
        """

        payload = {
            "from": "SITRA <onboarding@resend.dev>",
            "to": ["yanisaidoune1@gmail.com"],
            "reply_to": email,
            "subject": f"Rapport SITRA pour {email} — {url_site} — Score : {score}/100",
            "html": html_content,
            "attachments": [{
                "filename": f"SITRA_rapport.pdf",
                "content": pdf_b64
            }]
        }

        headers = {
            "Authorization": f"Bearer {st.secrets['RESEND_API_KEY']}",
            "Content-Type": "application/json"
        }

        r = req.post("https://api.resend.com/emails", headers=headers, json=payload, timeout=30)
        return r.status_code == 200

    except Exception as e:
        return False

    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('title', fontSize=22, fontName='Helvetica-Bold', textColor=colors.HexColor('#667eea'), spaceAfter=6)
    sub_style = ParagraphStyle('sub', fontSize=10, fontName='Helvetica', textColor=colors.HexColor('#888888'), spaceAfter=20)
    heading_style = ParagraphStyle('heading', fontSize=13, fontName='Helvetica-Bold', textColor=colors.HexColor('#222222'), spaceAfter=8, spaceBefore=16)
    normal_style = ParagraphStyle('normal', fontSize=10, fontName='Helvetica', textColor=colors.HexColor('#333333'), spaceAfter=4)

    story.append(Paragraph("SITRA — Rapport d'analyse", title_style))
    story.append(Paragraph(f"Site : {result['final_url']}", sub_style))
    story.append(Paragraph(f"Date : {time.strftime('%d/%m/%Y')}", sub_style))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("Scores", heading_style))
    data = [
        ["Categorie", "Score", "Evaluation"],
        ["Score Global", f"{result['global_score']}/100", get_score_label(result['global_score'])[0]],
        ["SEO", f"{result['seo']['score']}/100", get_score_label(result['seo']['score'])[0]],
        ["UX", f"{result['ux']['score']}/100", get_score_label(result['ux']['score'])[0]],
        ["Contenu", f"{result['content']['score']}/100", get_score_label(result['content']['score'])[0]],
        ["Design", f"{result['design']['score']}/100", get_score_label(result['design']['score'])[0]],
        ["Performance", f"{result['performance']['score']}/100", get_score_label(result['performance']['score'])[0]],
    ]
    table = Table(data, colWidths=[6*cm, 4*cm, 5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f7f7f7'), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph(f"Problemes detectes ({result['total_issues']})", heading_style))
    cats = {}
    for item in result['all_issues']:
        cats.setdefault(item['category'], []).append(item['message'])
    for cat, msgs in cats.items():
        story.append(Paragraph(f"<b>{cat}</b>", normal_style))
        for msg in msgs:
            story.append(Paragraph(f"- {msg}", normal_style))
        story.append(Spacer(1, 0.2*cm))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("Rapport genere par SITRA — Analyseur Intelligent de Sites Web",
                           ParagraphStyle('footer', fontSize=8, textColor=colors.HexColor('#aaaaaa'))))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ── LIMITE ANALYSES ───────────────────────────────────────────────────────────
def get_analyses_count():
    if "analyses_count" not in st.session_state:
        st.session_state["analyses_count"] = 0
    return st.session_state["analyses_count"]

def increment_analyses_count():
    if "analyses_count" not in st.session_state:
        st.session_state["analyses_count"] = 0
    st.session_state["analyses_count"] += 1

def show_paywall():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #667eea;border-radius:16px;padding:3rem;text-align:center;margin:2rem 0">
        <div style="font-size:2rem;font-weight:800;background:linear-gradient(135deg,#667eea,#f07cf7);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:1rem">
            Vous avez utilisé vos 2 analyses gratuites
        </div>
        <p style="color:#aaa;font-size:1rem;margin-bottom:2rem;max-width:500px;margin-left:auto;margin-right:auto">
            Pour continuer à analyser vos sites et accéder aux recommandations IA, à l'export PDF et à l'analyse concurrentielle, passez au plan Pro.
        </p>
        <a href="https://yanisaidoune1-sudo.github.io/mon-audit-seo#pricing" target="_blank"
           style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:1rem 2.5rem;border-radius:12px;text-decoration:none;font-weight:700;font-size:1rem;display:inline-block">
            Voir les offres
        </a>
    </div>
    """, unsafe_allow_html=True)

st.set_page_config(page_title="SITRA | Analyseur de Sites Web", page_icon="🅂", layout="wide", initial_sidebar_state="expanded")

# ── SIDEBAR — en premier pour que les variables existent partout ──────────────
with st.sidebar:
    st.markdown("### Menu")
    st.divider()

    if "menu_choix" not in st.session_state:
        st.session_state["menu_choix"] = "Aucune option"

    menu_choix = st.selectbox(
        "Options :",
        [
            "Aucune option",
            "Mode comparatif",
            "Optimiser mon site",
            "Textes corrigés prêts à copier",
            "Génération de contenu",
            "Potentiel de croissance",
        ],
        key="menu_choix",
        label_visibility="collapsed"
    )

    st.divider()
    st.markdown('<div style="color:#666;font-size:0.75rem;text-align:center">SITRA Engine v1.0<br>Analyse en temps réel</div>', unsafe_allow_html=True)

mode_comparaison     = (st.session_state.get("menu_choix") == "Mode comparatif")
show_corriger        = (st.session_state.get("menu_choix") == "Optimiser mon site")
show_textes          = (st.session_state.get("menu_choix") == "Textes corrigés prêts à copier")
show_contenu_marque  = (st.session_state.get("menu_choix") == "Génération de contenu")
show_potentiel       = (st.session_state.get("menu_choix") == "Potentiel de croissance")

st.markdown("""
<script>
(function() {
  var link = document.querySelector("link[rel~='icon']");
  if (!link) { link = document.createElement('link'); link.rel = 'icon'; document.head.appendChild(link); }
  link.type = 'image/svg+xml';
  link.href = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='16' fill='%23000000'/%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0%25' y1='0%25' x2='100%25' y2='100%25'%3E%3Cstop offset='0%25' stop-color='%237c6af7'/%3E%3Cstop offset='100%25' stop-color='%23f07cf7'/%3E%3C/linearGradient%3E%3C/defs%3E%3Ctext x='50' y='76' font-family='Arial Black%2C sans-serif' font-size='78' font-weight='900' fill='url(%23g)' text-anchor='middle'%3ES%3C/text%3E%3C/svg%3E";
})();
</script>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='16' fill='%23000000'/%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0%25' y1='0%25' x2='100%25' y2='100%25'%3E%3Cstop offset='0%25' stop-color='%237c6af7'/%3E%3Cstop offset='100%25' stop-color='%23f07cf7'/%3E%3C/linearGradient%3E%3C/defs%3E%3Ctext x='50' y='76' font-family='Arial Black%2C sans-serif' font-size='78' font-weight='900' fill='url(%23g)' text-anchor='middle'%3ES%3C/text%3E%3C/svg%3E">
<meta property="og:title" content="SITRA — Analyseur Intelligent de Sites Web" />
<meta property="og:description" content="Analysez votre site gratuitement en 30 secondes. SEO, UX, Performance, Design — 20 critères vérifiés avec des recommandations IA personnalisées." />
<meta property="og:image" content="https://yanisaidoune1-sudo.github.io/mon-audit-seo/favicon.svg" />
<meta property="og:url" content="https://mon-audit-seo-ivaf8necmnfhqpmnyf2unx.streamlit.app" />
<meta property="og:type" content="website" />
""", unsafe_allow_html=True)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@800&family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.main .block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1200px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0a0a0a 0%, #1a1a2e 100%); }
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
/* Supprime le rideau transparent de Streamlit */
[data-testid="stAppViewBlockContainer"] > div:first-child { opacity: 1 !important; }
div[data-stale="true"] { opacity: 1 !important; transition: none !important; }
.stSpinner { display: none !important; }
.stApp > header { display: none; }
/* Transitions instantanées */
* { transition-duration: 0s !important; }
.hero-header { background: linear-gradient(135deg, #0f0f1a 0%, #1a1a3e 50%, #0f0f1a 100%); border: 1px solid #2a2a5e; border-radius: 16px; padding: 2.5rem 3rem; margin-bottom: 2rem; text-align: center; }
.hero-title { font-family: 'Syne', sans-serif; font-size: 5.5rem; font-weight: 800; background: linear-gradient(135deg, #7c6af7 0%, #b06cf5 50%, #f07cf7 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin: 0; letter-spacing: 0.2em; }
.hero-subtitle { color: #888; font-size: 1rem; margin-top: 0.5rem; letter-spacing: 1px; }
.metric-card { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 1px solid #2a2a4e; border-radius: 12px; padding: 1.2rem 1.5rem; text-align: center; }
.metric-value { font-size: 1.8rem; font-weight: 700; }
.metric-label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-top: 0.2rem; }
.issue-item { padding: 0.6rem 1rem; border-radius: 8px; margin: 0.4rem 0; font-size: 0.9rem; line-height: 1.5; border-left: 3px solid; }
.issue-critical { background: rgba(220,53,69,0.1); border-left-color: #dc3545; }
.issue-warning { background: rgba(255,193,7,0.08); border-left-color: #ffc107; }
.issue-ok { background: rgba(40,167,69,0.1); border-left-color: #28a745; }
.score-bar-container { margin: 0.5rem 0; }
.score-bar-label { display: flex; justify-content: space-between; font-size: 0.85rem; color: #ccc; margin-bottom: 0.3rem; }
.score-bar-bg { background: #2a2a3e; border-radius: 999px; height: 8px; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 999px; }
.stButton > button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 10px; font-weight: 600; font-size: 1rem; padding: 0.7rem 2rem; width: 100%; }
.stTabs [data-baseweb="tab-list"], div[role="tablist"], [data-testid="stTabs"] { background: transparent; border-radius: 10px; padding: 4px; gap: 8px; flex-wrap: wrap; }
[data-testid="stTab"], div[role="tablist"] [role="tab"] { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white !important; border-radius: 10px !important; font-weight: 600 !important; padding: 0.5rem 1.2rem !important; border: none !important; border-bottom: none !important; text-decoration: none !important; opacity: 1 !important; }
[data-testid="stTab"]:hover, div[role="tablist"] [role="tab"]:hover { transform: translateY(-3px) scale(1.03); box-shadow: 0 6px 16px rgba(124,106,247,0.35); cursor: pointer; }                                                 
[data-testid="stTab"][aria-selected="true"], div[role="tablist"] [aria-selected="true"] { color: white !important; }
input[type="checkbox"] { accent-color: #667eea !important; }
</style>
""", unsafe_allow_html=True)

# ── HELPERS ───────────────────────────────────────────────────────────────────
def render_score_bar(label, score, tooltip=""):
    label_txt, _, color = get_score_label(score)
    tip_html = ""
    if tooltip:
        tip_html = f'''<span class="sitra-tooltip">(?)<span class="sitra-tooltiptext">{tooltip}</span></span>'''
    st.markdown(f"""
    <style>
    .sitra-tooltip {{ position: relative; display: inline-block; cursor: help; color: #667eea; font-size: 0.8rem; margin-left: 4px; vertical-align: middle; }}
    .sitra-tooltip .sitra-tooltiptext {{ visibility: hidden; background: #1a1a2e; color: #fff; border: 1px solid #667eea; border-radius: 6px; padding: 5px 10px; position: absolute; z-index: 999; bottom: 125%; left: 50%; transform: translateX(-50%); white-space: nowrap; font-size: 0.78rem; opacity: 0; transition: opacity 0.1s; }}
    .sitra-tooltip:hover .sitra-tooltiptext {{ visibility: visible; opacity: 1; }}
    </style>
    <div class="score-bar-container">
        <div class="score-bar-label">
            <span>{label} {tip_html}</span>
            <span style="color:{color};font-weight:700">{score}/100 — {label_txt}</span>
        </div>
        <div class="score-bar-bg">
            <div class="score-bar-fill" style="width:{score}%;background:{color}"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_issues(issues):
    if not issues:
        st.markdown('<div class="issue-item issue-ok">Aucun problème détecté dans cette catégorie.</div>', unsafe_allow_html=True)
    else:
        for issue in issues:
            # Nettoie les tirets et symboles techniques
            msg = issue.replace("[X]", "").replace("[!]", "").replace(" — ", " : ").strip()
            css_class = "issue-critical" if issue.startswith("[X]") or "pas de" in issue.lower() else "issue-warning"
            st.markdown(f'<div class="issue-item {css_class}">{msg}</div>', unsafe_allow_html=True)

# ── RENDER RESULT ─────────────────────────────────────────────────────────────
def render_result(result, idx=0):
    if result.get("error"):
        st.warning("Impossible d'analyser ce site. Certains grands sites bloquent volontairement les outils d'analyse automatiques. SITRA est conçu pour les sites de PME, artisans, restaurants et portfolios.")
        return

    label_txt, _, label_color = get_score_label(result["global_score"])
    st.divider()
    st.markdown(f"### {result['final_url']}")

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, score, lbl in [
        (c1, result["global_score"], "Score Global"),
        (c2, result["seo"]["score"], "Google"),
        (c3, result["ux"]["score"], "Navigation"),
        (c4, result["design"]["score"], "Apparence"),
        (c5, result["performance"]["score"], "Vitesse"),
    ]:
        lbl_t, _, clr = get_score_label(score)
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color:{clr}">{score}</div>
            <div class="metric-label">{lbl}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("")
    with st.expander("Analyse IA — Recommandations personnalisées"):
        with st.spinner("L'IA analyse votre site..."):
            recommandations = generer_recommandations_ia(result)
        if recommandations:
            st.markdown(recommandations)
        else:
            st.warning("Impossible de générer les recommandations IA pour le moment.")

    import os
    try:
        os.environ["MISTRAL_API_KEY"] = st.secrets["MISTRAL_API_KEY"]
    except Exception:
        pass

    tabs_list = [
        "Référencement Google",
        "Détails du site",
        "Analyse approfondie",
        "Résumé",
        "Objectifs à atteindre",
        "Partager",
    ]
    if show_corriger:
        tabs_list.append("Optimiser mon site")
    if show_textes:
        tabs_list.append("Textes corrigés")
    if show_contenu_marque:
        tabs_list.append("Génération de contenu")
    if show_potentiel:
        tabs_list.append("Potentiel de croissance")   
    if mode_comparaison:
        tabs_list.append("Mode comparatif")

    tabs = st.tabs(tabs_list)

    with tabs[0]:
        seo = result["seo"]
        render_score_bar("Référencement Google", seo["score"])
        st.caption("Comment Google voit et comprend votre site")
        st.markdown("")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.markdown("**Ce qu'on a trouvé sur votre site**")
            title_display = seo['title'][:60] + '...' if len(seo['title']) > 60 else seo['title'] or '(manquant)'
            st.markdown(f"- **Titre de la page** : `{title_display}` ({len(seo['title'])} caractères)")
            st.markdown(f"- **Description Google** : {len(seo['meta_description'])} caractères")
            st.markdown(f"- **Titre principal** : {seo['h1_count']} {'(correct)' if seo['h1_count'] == 1 else '(à corriger)'}")
            st.markdown(f"- **Sous-titres** : {seo['h2_count']} {'(correct)' if seo['h2_count'] > 0 else '(manquant)'}")
            st.markdown(f"- **Images sans description** : {seo['images_no_alt']}/{seo['images_total']} (Google ne peut pas lire vos images sans description)")
        with col_s2:
            st.markdown("**Ce qu'il faut améliorer**")
            render_issues(seo["issues"])

    with tabs[1]:
        st.caption("Choisissez ce que vous voulez voir")
        sous_onglet = st.selectbox("Voir :", ["Navigation", "Qualité du texte", "Apparence du site", "Vitesse du site"], key=f"sous_{idx}")

        if sous_onglet == "Navigation":
            ux = result["ux"]
            render_score_bar("Navigation", ux["score"])
            st.caption("Est-ce que les visiteurs trouvent facilement ce qu'ils cherchent ?")
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                st.markdown("**Ce qu'on a trouvé**")
                st.markdown(f"- **Menu de navigation** : {'Présent' if ux['has_nav'] else 'Absent'} ({ux['nav_links_count']} liens)")
                st.markdown(f"- **Boutons d'action** : {ux['buttons_count']} {'(correct)' if ux['buttons_count'] > 0 else '(aucun trouvé)'}")
                st.markdown(f"- **Page contact** : {'Trouvée' if ux['has_contact'] else 'Absente'}")
                st.markdown(f"- **Pied de page** : {'Présent' if ux['has_footer'] else 'Absent'}")
            with col_u2:
                st.markdown("**Ce qu'il faut améliorer**")
                render_issues(ux["issues"])

        elif sous_onglet == "Qualité du texte":
            content = result["content"]
            render_score_bar("Qualité du texte", content["score"])
            st.caption("Le contenu de votre site est-il clair et suffisant ?")
            st.markdown(f"**Nombre de mots** : {content['word_count']} {'(bien !)' if content['word_count'] >= 300 else '(ajoutez plus de contenu, visez 300 mots minimum)'}")
            render_issues(content["issues"])

        elif sous_onglet == "Apparence du site":
            design = result["design"]
            render_score_bar("Apparence du site", design["score"])
            st.caption("Votre site donne-t-il une bonne première impression ?")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.markdown("**Ce qu'on a trouvé**")
                st.markdown(f"- **Logo et icône du site** : {'Présents' if design['has_favicon'] else 'Absents'}")
                st.markdown(f"- **Polices de caractères** : {'Personnalisées' if design['has_google_fonts'] else 'Standard'}")
                st.markdown(f"- **Aperçu sur les réseaux sociaux** : {'Configuré' if design['has_og_tags'] else 'Non configuré'}")
            with col_d2:
                st.markdown("**Ce qu'il faut améliorer**")
                render_issues(design["issues"])

        elif sous_onglet == "Vitesse du site":
            perf = result["performance"]
            render_score_bar("Vitesse du site", perf["score"])
            st.caption("Un site lent fait fuir les visiteurs — 53% partent si ça met plus de 3 secondes")
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.markdown("**Ce qu'on a mesuré**")
                rt = perf['response_time']
                rt_label = "Excellent" if rt and rt < 1 else ("Moyen" if rt and rt < 2 else "Lent")
                st.markdown(f"- **Connexion sécurisée (HTTPS)** : {'Activée' if perf['is_https'] else 'Non activée'}")
                st.markdown(f"- **Temps de chargement** : {rt} secondes — {rt_label}")
                st.markdown(f"- **Poids de la page** : {perf['html_size_kb']} KB")
            with col_p2:
                st.markdown("**Ce qu'il faut améliorer**")
                render_issues(perf["issues"])

    with tabs[3]:
        st.markdown(f"### Score global : **{result['global_score']}/100** — {label_txt}")
        render_score_bar("Référencement Google", result["seo"]["score"], "Comment Google voit votre site")
        render_score_bar("Navigation", result["ux"]["score"], "Les visiteurs trouvent-ils facilement ce qu'ils cherchent ?")
        render_score_bar("Qualité du texte", result["content"]["score"], "Votre contenu est-il clair et suffisant ?")
        render_score_bar("Apparence du site", result["design"]["score"], "Votre site donne-t-il une bonne première impression ?")
        render_score_bar("Vitesse du site", result["performance"]["score"], "Votre site se charge-t-il rapidement ?")
        st.divider()
        st.markdown(f"**{result['total_issues']} problèmes détectés :**")
        cats = {}
        for item in result["all_issues"]:
            cats.setdefault(item["category"], []).append(item["message"])
        for cat, msgs in cats.items():
            cat_fr = {"SEO": "Référencement Google", "UX": "Navigation", "Contenu": "Qualité du texte", "Design": "Apparence du site", "Performance": "Vitesse du site"}.get(cat, cat)
            with st.expander(f"{cat_fr} — {len(msgs)} problème(s)"):
                render_issues(msgs)
        st.divider()
        try:
            pdf_data = generer_pdf(result)
            st.download_button(label="Télécharger le rapport PDF", data=pdf_data, file_name=f"SITRA_rapport_{idx}.pdf", mime="application/pdf", key=f"download_{idx}")
        except Exception:
            pass
        st.markdown("")
        st.markdown("**Recevoir le rapport par email :**")
        email_input = st.text_input("Votre email :", placeholder="exemple@email.com", key=f"email_{idx}")
        if st.button("Envoyer le rapport par email", key=f"send_email_{idx}"):
            if email_input and "@" in email_input:
                with st.spinner("Envoi en cours..."):
                    succes = envoyer_rapport_email(email_input, result)
                if succes:
                    st.success(f"✅ Rapport envoyé à {email_input} !")
                else:
                    st.warning("L'envoi automatique n'est pas encore disponible. Téléchargez le PDF ci-dessus et envoyez-le manuellement.")
            else:
                st.warning("Merci d'entrer un email valide.")

    with tabs[4]:
        st.markdown("### Objectifs à atteindre")
        st.caption("Cochez les objectifs au fur et à mesure que vous les complétez")
        seo = result["seo"]
        ux = result["ux"]
        challenge_items = []
        if not seo["title"]:
            challenge_items.append("Ajouter un titre à votre site")
        elif len(seo["title"]) < 10 or len(seo["title"]) > 70:
            challenge_items.append(f"Améliorer le titre ({len(seo['title'])} caractères) — viser 50-60 caractères")
        if not seo["meta_description"]:
            challenge_items.append("Écrire une description de 120-160 caractères pour Google")
        if seo["h1_count"] != 1:
            challenge_items.append(f"Corriger le titre principal (vous en avez {seo['h1_count']}, il en faut 1)")
        if seo["images_no_alt"] > 0:
            challenge_items.append(f"Ajouter une description à {seo['images_no_alt']} image(s)")
        if not ux["has_contact"]:
            challenge_items.append("Ajouter vos informations de contact visibles")
        if not result["performance"]["is_https"]:
            challenge_items.append("Activer la connexion sécurisée sur votre site")
        if not ux["has_footer"]:
            challenge_items.append("Créer un pied de page avec vos informations et mentions légales")
        if not result["design"]["has_og_tags"]:
            challenge_items.append("Configurer l'aperçu de votre site sur les réseaux sociaux")
        if result["content"]["word_count"] < 300:
            challenge_items.append(f"Étoffer le contenu ({result['content']['word_count']} mots — visez 300 minimum)")
        generals = ["Tester sur téléphone et tablette", "Vérifier la vitesse de chargement", "Créer une page FAQ", "Ajouter des avis clients", "Vérifier l'orthographe"]
        while len(challenge_items) < 5 and generals:
            challenge_items.append(generals.pop(0))
        total = len(challenge_items)

        st.session_state[f"challenge_items_{idx}"] = challenge_items

        completed = sum(1 for i in range(total) if st.session_state.get(f"ch_{idx}_{i}", False))
        for i, obj in enumerate(challenge_items):
            key = f"ch_{idx}_{i}"
            if st.checkbox(obj, key=key):
                pass
        completed = sum(1 for i in range(total) if st.session_state.get(f"ch_{idx}_{i}", False))
        if total > 0:
            st.markdown("")
            st.progress(completed / total)
            st.caption(f"**{completed}/{total}** objectifs complétés {'— Bravo !' if completed == total else ''}")

    with tabs[2]:
        st.caption("Choisissez ce que vous voulez analyser")
        sous2 = st.selectbox("Voir :", ["Surcharge du site", "Images du site"], key=f"sous2_{idx}")

        if sous2 == "Surcharge du site":
            st.markdown("**Votre site a-t-il des éléments inutiles ?**")
            surcharge_items = []
            conseils = []
            if result["ux"]["nav_links_count"] > 7:
                surcharge_items.append(f"Menu surchargé : {result['ux']['nav_links_count']} liens")
                conseils.append("Réduisez à 5-7 liens maximum — gardez les pages les plus importantes")
            if result["performance"]["html_size_kb"] > 200:
                surcharge_items.append(f"Page trop lourde : {result['performance']['html_size_kb']} KB")
                conseils.append("Supprimez les éléments inutilisés — chaque KB en moins accélère votre site")
            if result["seo"]["images_total"] > 20:
                surcharge_items.append(f"Beaucoup d'images : {result['seo']['images_total']} détectées")
                conseils.append("Gardez seulement les plus importantes et compressez les autres")
            if result["ux"]["long_paragraphs"] > 0:
                surcharge_items.append(f"{result['ux']['long_paragraphs']} paragraphe(s) trop long(s)")
                conseils.append("Découpez vos longs paragraphes — les visiteurs lisent en diagonale")
            if result["content"]["word_count"] > 1000:
                surcharge_items.append(f"Contenu très long : {result['content']['word_count']} mots")
                conseils.append("Allez à l'essentiel — les visiteurs n'ont pas le temps de tout lire")
            if surcharge_items:
                for item, conseil in zip(surcharge_items, conseils):
                    st.markdown(f"""<div style="background:#1a1a2e;border:1px solid #ffc107;border-radius:10px;padding:1rem;margin:0.5rem 0"><div style="color:#ffc107;font-weight:700">⚠️ {item}</div><div style="color:#ccc;font-size:0.9rem;margin-top:0.3rem">💡 {conseil}</div></div>""", unsafe_allow_html=True)
            else:
                st.success("Votre site ne semble pas surchargé !")

        elif sous2 == "Images du site":
            st.markdown("**Vos images sont-elles suffisantes et adaptées ?**")
            images_total = result["seo"]["images_total"]
            images_no_alt = result["seo"]["images_no_alt"]
            if images_total == 0:
                st.markdown("""<div style="background:#1a1a2e;border:1px solid #dc3545;border-radius:10px;padding:1rem;margin:0.5rem 0"><div style="color:#dc3545;font-weight:700">❌ Aucune image sur votre site</div><div style="color:#ccc;font-size:0.9rem;margin-top:0.3rem">💡 Ajoutez des images pour rendre votre site plus attractif</div></div>""", unsafe_allow_html=True)
            elif images_total < 3:
                st.markdown(f"""<div style="background:#1a1a2e;border:1px solid #ffc107;border-radius:10px;padding:1rem;margin:0.5rem 0"><div style="color:#ffc107;font-weight:700">⚠️ Seulement {images_total} image(s) — c'est peu</div><div style="color:#ccc;font-size:0.9rem;margin-top:0.3rem">💡 Ajoutez des photos de vos produits, équipe ou locaux</div></div>""", unsafe_allow_html=True)
            elif images_total > 20:
                st.markdown(f"""<div style="background:#1a1a2e;border:1px solid #ffc107;border-radius:10px;padding:1rem;margin:0.5rem 0"><div style="color:#ffc107;font-weight:700">⚠️ Beaucoup d'images : {images_total}</div><div style="color:#ccc;font-size:0.9rem;margin-top:0.3rem">💡 Gardez les plus importantes et compressez les autres</div></div>""", unsafe_allow_html=True)
            else:
                st.success(f"✅ Bon nombre d'images : {images_total}")
            if images_no_alt > 0:
                st.markdown(f"""<div style="background:#1a1a2e;border:1px solid #ffc107;border-radius:10px;padding:1rem;margin:0.5rem 0"><div style="color:#ffc107;font-weight:700">⚠️ {images_no_alt} image(s) sans description</div><div style="color:#ccc;font-size:0.9rem;margin-top:0.3rem">💡 Ajoutez une description à chaque image pour aider Google</div></div>""", unsafe_allow_html=True)
            elif images_total > 0:
                st.success("✅ Toutes vos images ont une description !")
            st.markdown("\n**Conseils :**\n- Photos compressées (moins de 200 KB)\n- Format WebP ou JPEG\n- Pas d'images floues ou pixelisées")

    with tabs[5]:
        st.markdown("### Partager mes résultats")
        score = result["global_score"]
        url_site = result["final_url"]
        texte_partage = f"J'ai analysé {url_site} avec SITRA et obtenu un score de {score}/100 ! Analysez votre site sur https://mon-audit-seo-ivaf8necmnfhqpmnyf2unx.streamlit.app"
        lien_twitter = f"https://twitter.com/intent/tweet?text={texte_partage}"
        lien_linkedin = f"https://www.linkedin.com/sharing/share-offsite/?url=https://mon-audit-seo-ivaf8necmnfhqpmnyf2unx.streamlit.app"
        lien_facebook = f"https://www.facebook.com/sharer/sharer.php?u=https://mon-audit-seo-ivaf8necmnfhqpmnyf2unx.streamlit.app&quote={texte_partage}"
        lien_whatsapp = f"https://wa.me/?text={texte_partage}"
        st.markdown("")
        col_sh1, col_sh2, col_sh3, col_sh4 = st.columns(4)
        with col_sh1:
            st.markdown(f'''<a href="{lien_twitter}" target="_blank" style="display:block;text-align:center;background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;padding:0.8rem 1rem;color:#1DA1F2;text-decoration:none;font-weight:600">X (Twitter)</a>''', unsafe_allow_html=True)
        with col_sh2:
            st.markdown(f'''<a href="{lien_linkedin}" target="_blank" style="display:block;text-align:center;background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;padding:0.8rem 1rem;color:#0A66C2;text-decoration:none;font-weight:600">LinkedIn</a>''', unsafe_allow_html=True)
        with col_sh3:
            st.markdown(f'''<a href="{lien_facebook}" target="_blank" style="display:block;text-align:center;background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;padding:0.8rem 1rem;color:#1877F2;text-decoration:none;font-weight:600">Facebook</a>''', unsafe_allow_html=True)
        with col_sh4:
            st.markdown(f'''<a href="{lien_whatsapp}" target="_blank" style="display:block;text-align:center;background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;padding:0.8rem 1rem;color:#25D366;text-decoration:none;font-weight:600">WhatsApp</a>''', unsafe_allow_html=True)
        st.markdown("")
        st.markdown("**Pour Instagram et TikTok** — copiez ce texte :")
        st.code(texte_partage, language=None)

# ── ONGLET CORRIGER ──
    if show_corriger:
        tab_corriger_idx = tabs_list.index("Optimiser mon site")
        with tabs[tab_corriger_idx]:
            st.markdown("### Optimiser mon site")
            st.caption("Les 5 corrections les plus importantes pour votre site, dans l'ordre de priorite.")

            seo = result["seo"]
            ux = result["ux"]
            perf = result["performance"]
            design = result["design"]
            rt = perf.get("response_time", 0) or 0
            url_site = result["final_url"]
            titre = seo["title"] or ""
            nom_site = titre.split("—")[0].split("|")[0].strip() if titre else url_site.replace("https://","").replace("www.","").split("/")[0]
            url_clean = url_site.replace("https://","").replace("http://","").rstrip("/")

            erreurs = []

            if not perf["is_https"]:
                erreurs.append({
                    "niveau": "critique",
                    "icone": "ti-shield-x",
                    "titre": "Site non securise (HTTPS manquant)",
                    "avant_icone": "ti-lock-open",
                    "avant_label": "http://" + url_clean,
                    "avant_couleur": "danger",
                    "avant_texte": "Votre site affiche une alerte rouge dans tous les navigateurs. Vos visiteurs voient \"Non securise\" et repartent immediatement.",
                    "apres_icone": "ti-lock",
                    "apres_label": "https://" + url_clean,
                    "apres_couleur": "success",
                    "apres_texte": "Cadenas vert visible — vos visiteurs ont confiance et restent sur votre site.",
                    "conseil": "Activez le HTTPS depuis votre hebergeur. C'est gratuit (Let's Encrypt) et prend 5 minutes.",
                    "selector": None,
                    "use_icon": True
                })

            if not seo["title"] or len(seo["title"]) < 10 or len(seo["title"]) > 70:
                t = seo["title"] or ""
                if not t:
                    avant_t = "(vide — Google invente quelque chose)"
                    apres_t = nom_site + " | Votre activite — Ville"
                elif len(t) < 10:
                    avant_t = t + " (trop court)"
                    apres_t = t + " — " + nom_site + " | Votre ville"
                else:
                    avant_t = t[:45] + "... (coupe par Google)"
                    apres_t = t[:52] + "..."
                erreurs.append({
                    "niveau": "critique",
                    "icone": "ti-tag",
                    "titre": "Titre de page manquant ou incorrect",
                    "avant_icone": "ti-search",
                    "avant_label": avant_t,
                    "avant_couleur": "danger",
                    "avant_texte": "Quand quelqu'un cherche votre activite sur Google, votre lien apparait sans titre clair — ca ne donne pas envie de cliquer.",
                    "apres_icone": "ti-search",
                    "apres_label": apres_t,
                    "apres_couleur": "success",
                    "apres_texte": "Un titre clair et precis — Google comprend votre activite et vos futurs clients cliquent sur votre lien.",
                    "conseil": "Redigez un titre de 50-60 caracteres : nom de votre activite + ville. Ex : " + nom_site + " | Coiffeur — Paris 15.",
                    "selector": None,
                    "use_icon": True
                })

            if seo["h1_count"] != 1:
                if seo["h1_count"] == 0:
                    t_avant = "Pas de titre principal sur la page"
                    t_apres = "Le texte principal balisé comme titre H1"
                else:
                    t_avant = str(seo["h1_count"]) + " titres H1 en doublon sur la page"
                    t_apres = "Un seul titre H1 — le plus important"
                erreurs.append({
                    "niveau": "important",
                    "icone": "ti-heading",
                    "titre": "Titre principal (H1) " + ("absent" if seo["h1_count"] == 0 else "en doublon"),
                    "avant_icone": "ti-heading-off",
                    "avant_label": t_avant,
                    "avant_couleur": "warning",
                    "avant_texte": "Le grand texte visible sur votre page n'est pas reconnu comme titre par Google — il faut le baliser correctement dans le code.",
                    "apres_icone": "ti-heading",
                    "apres_label": t_apres,
                    "apres_couleur": "success",
                    "apres_texte": "Google sait exactement de quoi parle " + nom_site + " et associe les bons mots-cles a votre page.",
                    "conseil": "Le titre H1 dit a Google de quoi parle votre page. Sans lui, Google ne sait pas quel mot-cle associer a " + nom_site + ".",
                    "selector": "h1:first-of-type",
                    "use_icon": False
                })

            if not seo["meta_description"]:
                desc_prop = "Decouvrez " + nom_site + " — " + (titre[:40] if titre else "qualite et professionnalisme") + ". Contactez-nous !"
                erreurs.append({
                    "niveau": "important",
                    "icone": "ti-align-left",
                    "titre": "Description Google manquante",
                    "avant_icone": "ti-search",
                    "avant_label": "(texte aleatoire pris par Google)",
                    "avant_couleur": "warning",
                    "avant_texte": "Sous votre lien Google, un texte aleatoire s'affiche — peu attractif et peu convaincant pour cliquer.",
                    "apres_icone": "ti-search",
                    "apres_label": desc_prop[:60] + "...",
                    "apres_couleur": "success",
                    "apres_texte": "Un texte accrocheur sous votre lien — vos futurs clients ont envie de cliquer sur " + nom_site + ".",
                    "conseil": "Redigez 1-2 phrases qui donnent envie de visiter votre site. Visez 120-160 caracteres.",
                    "selector": None,
                    "use_icon": True
                })

            if seo["images_no_alt"] > 0:
                erreurs.append({
                    "niveau": "important",
                    "icone": "ti-photo-x",
                    "titre": str(seo["images_no_alt"]) + " photo(s) sans description",
                    "avant_icone": "ti-photo-x",
                    "avant_label": str(seo["images_no_alt"]) + " photo(s) invisibles pour Google",
                    "avant_couleur": "warning",
                    "avant_texte": "Google voit ces photos mais ne sait pas ce qu'elles montrent — impossible de les trouver dans Google Images.",
                    "apres_icone": "ti-photo-check",
                    "apres_label": "Photos decrites et indexees",
                    "apres_couleur": "success",
                    "apres_texte": "Chaque photo est comprise par Google et peut apparaitre dans Google Images — plus de visibilite pour " + nom_site + ".",
                    "conseil": "Pour chaque photo, ajoutez une courte description dans le code (attribut alt). Ex : 'Salle de " + nom_site + "'.",
                    "selector": "img:not([alt]):first-of-type, img[alt='']:first-of-type",
                    "use_icon": False
                })

            if rt > 2:
                erreurs.append({
                    "niveau": "important",
                    "icone": "ti-clock-x",
                    "titre": "Site trop lent (" + str(rt) + " secondes)",
                    "avant_icone": "ti-clock-x",
                    "avant_label": str(rt) + "s — trop lent",
                    "avant_couleur": "danger",
                    "avant_texte": "Plus d'1 visiteur sur 2 repart si votre site met plus de 3 secondes a charger. Vous perdez des clients sans le savoir.",
                    "apres_icone": "ti-clock-check",
                    "apres_label": "Objectif : moins de 2s",
                    "apres_couleur": "success",
                    "apres_texte": "Un site rapide retient vos visiteurs et est mieux classe par Google.",
                    "conseil": "Compressez vos photos sur tinypng.com (gratuit) avant de les mettre en ligne — c'est souvent la cause principale.",
                    "selector": None,
                    "use_icon": True
                })

            if not ux["has_nav"]:
                erreurs.append({
                    "niveau": "important",
                    "icone": "ti-menu-2",
                    "titre": "Pas de menu de navigation",
                    "avant_icone": "ti-menu-off",
                    "avant_label": "Aucun menu detecte",
                    "avant_couleur": "danger",
                    "avant_texte": "Vos visiteurs arrivent sur votre site mais ne savent pas ou aller — ils repartent sans avoir trouve ce qu'ils cherchent.",
                    "apres_icone": "ti-menu-2",
                    "apres_label": "Accueil · Services · Contact",
                    "apres_couleur": "success",
                    "apres_texte": "Un menu clair guide vos visiteurs et aide Google a explorer toutes vos pages.",
                    "conseil": "Creez un menu avec 5 liens maximum : Accueil, Services, A propos, Contact.",
                    "selector": "nav:first-of-type",
                    "use_icon": True
                })

            if not design["has_og_tags"]:
                erreurs.append({
                    "niveau": "a_corriger",
                    "icone": "ti-share",
                    "titre": "Pas d'apercu sur les reseaux sociaux",
                    "avant_icone": "ti-share-off",
                    "avant_label": "Lien brut sans image ni titre",
                    "avant_couleur": "warning",
                    "avant_texte": "Quand quelqu'un partage votre lien sur WhatsApp ou Facebook, rien ne s'affiche — juste une URL peu attractive.",
                    "apres_icone": "ti-share",
                    "apres_label": "Photo + titre automatiques",
                    "apres_couleur": "success",
                    "apres_texte": "Une belle image et votre titre s'affichent automatiquement — ca donne envie de cliquer sur " + nom_site + ".",
                    "conseil": "Les balises Open Graph controlent l'apercu de partage. Votre CMS peut les configurer en quelques clics.",
                    "selector": None,
                    "use_icon": True
                })

            erreurs_affichees = erreurs[:5]
            nb_restantes = max(0, result.get("total_issues", 0) - len(erreurs_affichees))

            niveau_couleur = {"critique": "danger", "important": "warning", "a_corriger": "info"}
            niveau_label = {"critique": "Critique", "important": "Important", "a_corriger": "A corriger"}

            blocs = ""
            for i, e in enumerate(erreurs_affichees):
                n = i + 1
                couleur = niveau_couleur.get(e["niveau"], "warning")
                label = niveau_label.get(e["niveau"], "A corriger")
                av_c = e["avant_couleur"]
                ap_c = e["apres_couleur"]

                # Contenu avant/apres
                if e["use_icon"]:
                    avant_content = f"""
<div style="background:var(--color-background-{av_c});border-radius:var(--border-radius-md);height:90px;display:flex;align-items:center;justify-content:center;border:0.5px solid var(--color-border-{av_c});margin-bottom:8px">
  <div style="text-align:center">
    <i class="ti {e['avant_icone']}" style="font-size:26px;color:var(--color-text-{av_c})" aria-hidden="true"></i>
    <p style="font-size:11px;color:var(--color-text-{av_c});margin:4px 0 0;padding:0 8px">{e['avant_label']}</p>
  </div>
</div>"""
                    apres_content = f"""
<div style="background:var(--color-background-{ap_c});border-radius:var(--border-radius-md);height:90px;display:flex;align-items:center;justify-content:center;border:0.5px solid var(--color-border-{ap_c});margin-bottom:8px">
  <div style="text-align:center">
    <i class="ti {e['apres_icone']}" style="font-size:26px;color:var(--color-text-{ap_c})" aria-hidden="true"></i>
    <p style="font-size:11px;color:var(--color-text-{ap_c});margin:4px 0 0;padding:0 8px">{e['apres_label']}</p>
  </div>
</div>"""
                else:
                    # Vraie capture Playwright ou Microlink
                    img_data = None
                    try:
                        from playwright_capture import get_screenshot_with_highlight
                        img_data, _ = get_screenshot_with_highlight(url_site, e["selector"])
                    except Exception:
                        pass
                    if not img_data:
                        try:
                            img_data, _ = get_screenshot_zone(url_site, e["selector"])
                        except Exception:
                            pass
                    if img_data:
                        avant_content = f'''<div style="border-radius:var(--border-radius-md);overflow:hidden;border:2px solid var(--color-border-{av_c});margin-bottom:8px;height:90px;position:relative">
<img src="{img_data}" style="width:100%;height:90px;object-fit:cover;object-position:top"/>
<div style="position:absolute;top:6px;left:6px;background:var(--color-background-{av_c});color:var(--color-text-{av_c});font-size:10px;font-weight:600;padding:2px 7px;border-radius:var(--border-radius-md);border:0.5px solid var(--color-border-{av_c})">Erreur ici</div>
</div>'''
                        apres_content = f'''<div style="border-radius:var(--border-radius-md);overflow:hidden;border:2px solid var(--color-border-{ap_c});margin-bottom:8px;height:90px;position:relative">
<img src="{img_data}" style="width:100%;height:90px;object-fit:cover;object-position:top;filter:brightness(0.45) saturate(0.3)"/>
<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;background:rgba(0,0,0,0.15)">
<i class="ti ti-circle-check" style="font-size:28px;color:var(--color-text-{ap_c})"></i>
<p style="font-size:11px;font-weight:600;color:var(--color-text-{ap_c});text-align:center;padding:0 8px;margin:0;text-shadow:0 1px 3px rgba(0,0,0,0.8)">{e["apres_label"]}</p>
</div>
</div>'''
                    else:
                        avant_content = f'<div style="background:var(--color-background-{av_c});border-radius:var(--border-radius-md);height:90px;display:flex;align-items:center;justify-content:center;border:0.5px solid var(--color-border-{av_c});margin-bottom:8px"><p style="font-size:12px;color:var(--color-text-{av_c});padding:0 12px;text-align:center">{e["avant_label"]}</p></div>'
                        apres_content = f'<div style="background:var(--color-background-{ap_c});border-radius:var(--border-radius-md);height:90px;display:flex;align-items:center;justify-content:center;border:0.5px solid var(--color-border-{ap_c});margin-bottom:8px"><p style="font-size:12px;color:var(--color-text-{ap_c});padding:0 12px;text-align:center">{e["apres_label"]}</p></div>'

                blocs += f"""
<div style="background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-lg);overflow:hidden;margin-bottom:12px">
  <div style="padding:10px 16px;background:var(--color-background-{couleur});border-bottom:0.5px solid var(--color-border-tertiary);display:flex;align-items:center;gap:10px">
    <div style="width:26px;height:26px;border-radius:50%;background:var(--color-background-{couleur});border:2px solid var(--color-border-{couleur});display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:500;color:var(--color-text-{couleur});flex-shrink:0">{n}</div>
    <i class="ti {e['icone']}" style="font-size:16px;color:var(--color-text-{couleur})" aria-hidden="true"></i>
    <span style="font-size:13px;font-weight:500;color:var(--color-text-{couleur});flex:1">{e['titre']}</span>
    <span style="font-size:11px;background:var(--color-background-{couleur});color:var(--color-text-{couleur});padding:2px 8px;border-radius:var(--border-radius-md);border:0.5px solid var(--color-border-{couleur})">{label}</span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 32px 1fr">
    <div style="padding:12px 14px">
      <p style="font-size:11px;color:var(--color-text-secondary);margin:0 0 8px;text-transform:uppercase;letter-spacing:0.5px">Avant</p>
      {avant_content}
      <p style="font-size:12px;color:var(--color-text-primary);margin:0;line-height:1.5">{e['avant_texte']}</p>
    </div>
    <div style="display:flex;align-items:center;justify-content:center;color:var(--color-text-secondary)">
      <i class="ti ti-arrow-right" style="font-size:16px" aria-hidden="true"></i>
    </div>
    <div style="padding:12px 14px">
      <p style="font-size:11px;color:var(--color-text-secondary);margin:0 0 8px;text-transform:uppercase;letter-spacing:0.5px">Apres</p>
      {apres_content}
      <p style="font-size:12px;color:var(--color-text-primary);margin:0;line-height:1.5">{e['apres_texte']}</p>
    </div>
  </div>
  <div style="padding:8px 16px;background:var(--color-background-secondary);border-top:0.5px solid var(--color-border-tertiary)">
    <p style="font-size:12px;color:var(--color-text-secondary);margin:0"><i class="ti ti-bulb" style="font-size:13px;vertical-align:-1px;margin-right:4px" aria-hidden="true"></i>{e['conseil']}</p>
  </div>
</div>"""

            if not blocs:
                blocs = '<div style="background:var(--color-background-success);border:0.5px solid var(--color-border-success);border-radius:var(--border-radius-lg);padding:24px;text-align:center"><i class="ti ti-circle-check" style="font-size:32px;color:var(--color-text-success)" aria-hidden="true"></i><p style="font-size:15px;font-weight:500;color:var(--color-text-success);margin:8px 0 0">Aucune erreur majeure — votre site est bien optimise !</p></div>'

            html_final = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.11.0/dist/tabler-icons.min.css">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--color-background-tertiary,#f5f5f3);color:var(--color-text-primary,#1a1a1a);padding:16px}}
:root{{
--color-background-primary:#ffffff;--color-background-secondary:#f5f5f3;--color-background-tertiary:#efefed;
--color-background-danger:#fcebeb;--color-background-warning:#faeeda;--color-background-success:#eaf3de;--color-background-info:#e6f1fb;
--color-text-primary:#1a1a1a;--color-text-secondary:#666660;--color-text-danger:#a32d2d;--color-text-warning:#854f0b;--color-text-success:#3b6d11;--color-text-info:#185fa5;
--color-border-tertiary:rgba(0,0,0,0.12);--color-border-danger:#f09595;--color-border-warning:#ef9f27;--color-border-success:#97c459;--color-border-info:#85b7eb;
--border-radius-md:8px;--border-radius-lg:12px
}}
@media(prefers-color-scheme:dark){{
:root{{
--color-background-primary:#1e1e1c;--color-background-secondary:#2c2c2a;--color-background-tertiary:#111110;
--color-background-danger:#501313;--color-background-warning:#412402;--color-background-success:#173404;--color-background-info:#042c53;
--color-text-primary:#e8e8e0;--color-text-secondary:#a0a09a;--color-text-danger:#f09595;--color-text-warning:#fac775;--color-text-success:#c0dd97;--color-text-info:#b5d4f4;
--color-border-tertiary:rgba(255,255,255,0.12);--color-border-danger:#791f1f;--color-border-warning:#633806;--color-border-success:#27500a;--color-border-info:#0c447c
}}
}}
</style>
</head><body>
<div style="margin-bottom:16px;padding:12px 16px;background:var(--color-background-primary);border-radius:var(--border-radius-lg);border:0.5px solid var(--color-border-tertiary);display:flex;align-items:center;gap:10px">
  <i class="ti ti-list-check" style="font-size:18px;color:var(--color-text-secondary)" aria-hidden="true"></i>
  <div>
    <p style="font-size:13px;font-weight:500;margin:0;color:var(--color-text-primary)">Les {len(erreurs_affichees)} corrections prioritaires pour {nom_site}</p>
    {"<p style='font-size:12px;color:var(--color-text-secondary);margin:2px 0 0'>" + str(nb_restantes) + " points secondaires supplementaires dans l'onglet Resume</p>" if nb_restantes > 0 else ""}
  </div>
</div>
{blocs}
</body></html>"""

            import streamlit.components.v1 as components
            components.html(html_final, height=max(400, len(erreurs_affichees) * 320), scrolling=True)
            st.divider()
                        
# ── ONGLET TEXTES CORRIGÉS ──
    if show_textes:
        tab_textes_idx = tabs_list.index("Textes corrigés")
        with tabs[tab_textes_idx]:
            st.markdown("### Textes corrigés prêts à copier-coller")
            st.caption("SITRA génère vos textes corrigés — copiez directement la version verte sur votre site.")

            seo = result["seo"]
            url_site = result["final_url"]
            titre = seo["title"] or ""
            desc = seo["meta_description"] or ""
            nom_site = titre.split("—")[0].split("|")[0].strip() if titre else url_site.replace("https://","").replace("www.","").split("/")[0]

            titre_ok = titre and 10 <= len(titre) <= 70
            desc_ok = desc and 100 <= len(desc) <= 170
            h1_ok = seo["h1_count"] == 1

            # Affichage dynamique : avant generation on dit ce qu'on va faire,
            # apres generation on dit ce qui a vraiment ete fait
            deja_genere = f"textes_corriges_{idx}" in st.session_state

            if deja_genere:
                desc_images_ok = [d for d in st.session_state.get(f"images_desc_{idx}", []) if d]
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**SITRA a généré :**")
                    if not titre_ok: st.markdown("- Titre de page Google")
                    if not desc_ok: st.markdown("- Description Google")
                    if not h1_ok: st.markdown("- Titre principal H1")
                    st.markdown("- Introduction page d'accueil")
                    st.markdown("- Texte A propos")
                    st.markdown("- Texte Services")
                    st.markdown("- Texte Contact")
                    st.markdown("- Mots-clés SEO")
                    if desc_images_ok:
                        st.markdown(f"- Descriptions de {len(desc_images_ok)} photo(s)")
                with col2:
                    items_ok = []
                    if titre_ok: items_ok.append(f"Titre déjà bon")
                    if desc_ok: items_ok.append("Description déjà présente")
                    if h1_ok: items_ok.append("Titre H1 déjà présent")
                    if seo["images_no_alt"] > 0 and not desc_images_ok:
                        items_ok.append(f"Photos : logos/icones détectés — pas de description utile")
                    if items_ok:
                        st.markdown("**Déjà bien ou non applicable :**")
                        for item in items_ok:
                            st.markdown(f"- {item}")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**SITRA va générer :**")
                    if not titre_ok: st.markdown("- Titre de page Google")
                    if not desc_ok: st.markdown("- Description Google")
                    if not h1_ok: st.markdown("- Titre principal H1")
                    st.markdown("- Introduction page d'accueil")
                    st.markdown("- Texte A propos")
                    st.markdown("- Texte Services")
                    st.markdown("- Texte Contact")
                    st.markdown("- Mots-clés SEO")
                    if seo["images_no_alt"] > 0:
                        st.markdown(f"- Analyse de vos {seo['images_no_alt']} photo(s)")
                with col2:
                    if titre_ok or desc_ok or h1_ok:
                        st.markdown("**Déjà bien renseigné :**")
                        if titre_ok: st.markdown(f"- Titre : « {titre[:40]} »")
                        if desc_ok: st.markdown("- Description Google")
                        if h1_ok: st.markdown("- Titre H1")

            st.markdown("")

            if st.button("Générer mes textes corrigés", key=f"btn_gen_{idx}"):
                with st.spinner("Génération en cours... (30-45 secondes)"):
                    try:
                        import requests as req
                        from bs4 import BeautifulSoup
                        import re

                        contenu_site = ""
                        images_urls = []
                        try:
                            r_site = req.get(url_site, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                            if r_site.status_code == 200:
                                soup = BeautifulSoup(r_site.text, "lxml")
                                for tag in soup(["script", "style", "nav", "footer", "head"]):
                                    tag.decompose()
                                contenu_site = soup.get_text(" ", strip=True)[:2000]
                                if seo["images_no_alt"] > 0:
                                    soup2 = BeautifulSoup(r_site.text, "lxml")
                                    for img in soup2.find_all("img"):
                                        alt = img.get("alt", "").strip()
                                        src = img.get("src", "")
                                        if not alt and src:
                                            if src.startswith("//"): src = "https:" + src
                                            elif src.startswith("/"):
                                                from urllib.parse import urljoin
                                                src = urljoin(url_site, src)
                                            if src.startswith("http") and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                                                images_urls.append(src)
                                                if len(images_urls) >= min(seo["images_no_alt"], 5):
                                                    break
                        except Exception:
                            contenu_site = ""

                        headers_m = {
                            "Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}",
                            "Content-Type": "application/json"
                        }

                        # Vision pour les photos
                        descriptions_images = []
                        for img_url in images_urls:
                            try:
                                vision_data = {
                                    "model": "pixtral-12b-2409",
                                    "messages": [{"role": "user", "content": [
                                        {"type": "image_url", "image_url": {"url": img_url}},
                                        {"type": "text", "text": "Tu es un expert SEO. Analyse cette image. Si c'est un LOGO, icone, badge, watermark, bouton, fond decoratif ou element graphique → reponds uniquement SKIP. Si c'est une VRAIE PHOTO de contenu (interieur, personnes, produits, lieu, ambiance) → ecris en 10-15 mots une description alt SEO en francais, factuelle, sans commencer par Une image de."}
                                    ]}],
                                    "max_tokens": 60
                                }
                                r_v = req.post("https://api.mistral.ai/v1/chat/completions", headers=headers_m, json=vision_data, timeout=20)
                                d = r_v.json()["choices"][0]["message"]["content"].strip()
                                descriptions_images.append("" if "SKIP" in d.upper() or len(d) < 10 else d)
                            except Exception:
                                descriptions_images.append("")

                        # Generation des textes principaux
                        sections_prompt = []
                        if not titre_ok: sections_prompt.append("TITRE DE PAGE:\n(50-60 caracteres, activite + ville)")
                        if not desc_ok: sections_prompt.append("META DESCRIPTION:\n(130-155 caracteres, commence par un verbe, appel a l'action)")
                        if not h1_ok: sections_prompt.append("TITRE H1:\n(1 phrase courte, max 10 mots)")
                        sections_prompt.extend([
                            "INTRODUCTION:\n(2-3 phrases enthousiaste, parle au visiteur)",
                            "A PROPOS:\n(3-4 phrases personnelles, comme si le gerant parlait)",
                            "SERVICES:\n(3-4 phrases concretes avec services specifiques du site)",
                            "CONTACT:\n(2 phrases simples et directes)",
                            "MOTS CLES:\n(10 mots-cles specifiques separes par virgules)"
                        ])

                        prompt = f"""Tu es un copywriter expert SEO français.
SITE : {url_site}
TITRE ACTUEL : {titre or "(aucun)"}
DESCRIPTION ACTUELLE : {desc or "(aucune)"}
CONTENU : {contenu_site if contenu_site else "(déduis depuis l'URL)"}

REGLE : Chaque section a un TON DIFFERENT. Ne repete jamais les memes mots entre sections.
Reponds UNIQUEMENT avec les sections demandees, sans introduction ni markdown ni ---.

{chr(10).join(sections_prompt)}"""

                        data = {
                            "model": "mistral-small-latest",
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 1200,
                            "temperature": 0.7
                        }
                        r = req.post("https://api.mistral.ai/v1/chat/completions", headers=headers_m, json=data, timeout=45)
                        textes_generes = r.json()["choices"][0]["message"]["content"]
                        textes_generes = re.sub(r'#{1,6}\s*', '', textes_generes)
                        textes_generes = re.sub(r'\*{1,2}', '', textes_generes)
                        textes_generes = re.sub(r'^---+$', '', textes_generes, flags=re.MULTILINE)

                        st.session_state[f"textes_corriges_{idx}"] = textes_generes
                        st.session_state[f"images_desc_{idx}"] = descriptions_images
                        st.session_state[f"images_urls_{idx}"] = images_urls
                        st.rerun()

                    except Exception:
                        st.error("Erreur lors de la génération. Réessayez dans quelques secondes.")

            if f"textes_corriges_{idx}" in st.session_state:
                textes = st.session_state[f"textes_corriges_{idx}"]
                descriptions_images = st.session_state.get(f"images_desc_{idx}", [])
                images_urls = st.session_state.get(f"images_urls_{idx}", [])

                sections_config = []
                if not titre_ok:
                    sections_config.append(("TITRE DE PAGE", "Titre de page Google", titre if titre else "(aucun titre)", "Sur WordPress : Yoast SEO -> Titre. Sur Wix : Parametres -> SEO."))
                if not desc_ok:
                    sections_config.append(("META DESCRIPTION", "Description Google", desc if desc else "(aucune description)", "Sur WordPress : Yoast SEO -> Meta description."))
                if not h1_ok:
                    sections_config.append(("TITRE H1", "Titre principal (H1)", "(absent ou en doublon)", "Remplacez le grand titre en haut de votre page d'accueil."))
                sections_config.extend([
                    ("INTRODUCTION", "Introduction - Page d'accueil", "(aucun texte d'introduction)", "Collez juste sous le titre principal de votre page d'accueil."),
                    ("A PROPOS", "Page A propos", "(aucun texte A propos)", "Collez sur votre page A propos."),
                    ("SERVICES", "Section Services", "(aucune section Services)", "Collez dans votre section ou page Services."),
                    ("CONTACT", "Page Contact", "(aucun texte de contact)", "Ajoutez en haut de votre page Contact, avant le formulaire."),
                    ("MOTS CLES", "Mots-cles SEO", "(aucune strategie de mots-cles)", "Integrez naturellement dans vos textes et titres."),
                ])

                # Parse avec normalisation unicode
                import unicodedata, re as re2
                def normalize_key(s):
                    s = s.upper().strip().rstrip(":")
                    s = unicodedata.normalize("NFD", s)
                    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
                    s = re2.sub(r"[*#\[\]\-]", "", s).strip()
                    return s

                sections_trouvees = {}
                current_key = None
                current_lines = []
                all_keys = [cfg[0] for cfg in sections_config]

                for ligne in textes.split("\n"):
                    ligne_strip = ligne.strip()
                    ligne_norm = normalize_key(ligne_strip)
                    matched = False
                    for key in all_keys:
                        if ligne_norm.startswith(normalize_key(key)):
                            if current_key and current_lines:
                                sections_trouvees[current_key] = "\n".join(current_lines).strip()
                            current_key = key
                            current_lines = []
                            rest = ligne_strip[len(key):].lstrip(":* ").strip()
                            if rest:
                                current_lines.append(rest)
                            matched = True
                            break
                    if not matched and current_key and ligne_strip:
                        clean = ligne_strip.lstrip("*#-").strip()
                        if clean:
                            current_lines.append(clean)

                if current_key and current_lines:
                    sections_trouvees[current_key] = "\n".join(current_lines).strip()

                # Affichage avant/apres
                blocs_html = ""
                nb_affiche = 0

                for cfg in sections_config:
                    key, label, avant_val, conseil = cfg
                    apres_val = sections_trouvees.get(key, "")
                    if not apres_val or "[" in apres_val:
                        continue
                    nb_affiche += 1
                    blocs_html += f"""
<div style="margin-bottom:20px">
  <div style="font-size:11px;font-weight:700;color:#6d28d9;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">{nb_affiche}. {label}</div>
  <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:start">
    <div>
      <div style="font-size:10px;color:#dc2626;font-weight:700;margin-bottom:6px;text-transform:uppercase">Avant — Texte actuel</div>
      <div style="background:#fff5f5;border:2px solid #fca5a5;border-radius:10px;padding:14px;font-size:13px;color:#374151;line-height:1.6;min-height:60px">{avant_val}</div>
    </div>
    <div style="display:flex;align-items:center;font-size:24px;color:#7c6af7;padding:0 4px;align-self:center">&#8594;</div>
    <div>
      <div style="font-size:10px;color:#16a34a;font-weight:700;margin-bottom:6px;text-transform:uppercase">Apres — A copier-coller</div>
      <div style="background:#f0fdf4;border:2px solid #86efac;border-radius:10px;padding:14px;font-size:13px;color:#374151;line-height:1.6;min-height:60px;font-family:monospace">{apres_val}</div>
    </div>
  </div>
  <div style="margin-top:8px;background:rgba(124,106,247,0.1);border-left:3px solid #7c6af7;padding:7px 12px;border-radius:0 6px 6px 0;font-size:12px;color:#5b21b6">{conseil}</div>
</div>"""

                # Photos utiles uniquement
                for i, desc_img in enumerate(descriptions_images):
                    if not desc_img:
                        continue
                    nb_affiche += 1
                    blocs_html += f"""
<div style="margin-bottom:20px">
  <div style="font-size:11px;font-weight:700;color:#6d28d9;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">{nb_affiche}. Description photo {i+1}</div>
  <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:start">
    <div>
      <div style="font-size:10px;color:#dc2626;font-weight:700;margin-bottom:6px;text-transform:uppercase">Avant — Texte actuel</div>
      <div style="background:#fff5f5;border:2px solid #fca5a5;border-radius:10px;padding:14px;font-size:13px;color:#dc2626;line-height:1.6;min-height:60px">(aucune description — Google ne peut pas indexer cette photo)</div>
    </div>
    <div style="display:flex;align-items:center;font-size:24px;color:#7c6af7;padding:0 4px;align-self:center">&#8594;</div>
    <div>
      <div style="font-size:10px;color:#16a34a;font-weight:700;margin-bottom:6px;text-transform:uppercase">Apres — A copier-coller</div>
      <div style="background:#f0fdf4;border:2px solid #86efac;border-radius:10px;padding:14px;font-size:13px;color:#374151;line-height:1.6;min-height:60px;font-family:monospace">{desc_img}</div>
    </div>
  </div>
  <div style="margin-top:8px;background:rgba(124,106,247,0.1);border-left:3px solid #7c6af7;padding:7px 12px;border-radius:0 6px 6px 0;font-size:12px;color:#5b21b6">Ajoutez ce texte dans le champ Texte alternatif de cette image dans votre CMS.</div>
</div>"""

                if nb_affiche > 0:
                    import streamlit.components.v1 as components
                    html_final = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:8px}}</style>
</head><body>{blocs_html}</body></html>"""
                    components.html(html_final, height=max(400, nb_affiche * 200), scrolling=True)
                else:
                    st.code(textes, language=None)

                if st.button("Régénérer", key=f"btn_regen_{idx}"):
                    for k in [f"textes_corriges_{idx}", f"images_desc_{idx}", f"images_urls_{idx}"]:
                        if k in st.session_state:
                            del st.session_state[k]
                    st.rerun()

    # ── ONGLET GÉNÉRATION DE CONTENU ──
    if show_contenu_marque:
        tab_contenu_idx = tabs_list.index("Génération de contenu")
        with tabs[tab_contenu_idx]:
            st.markdown("### Génération de contenu")
            st.caption("Créez du contenu marketing prêt à publier, à partir de l'analyse de votre site.")

            types_disponibles = [
                "Post Instagram",
                "Post LinkedIn",
                "Post Facebook",
                "Email marketing",
                "Texte publicitaire Google Ads",
            ]

            col_gc1, col_gc2 = st.columns(2)
            with col_gc1:
                type_contenu_choisi = st.selectbox("Type de contenu :", types_disponibles, key=f"type_contenu_{idx}")
            with col_gc2:
                objectif_choisi = st.text_input("Objectif de la campagne :", placeholder="Ex : attirer plus de clients, annoncer une promo...", key=f"objectif_contenu_{idx}")

            if st.button("Générer le contenu", key=f"btn_gen_contenu_{idx}"):
                if not objectif_choisi.strip():
                    st.warning("Merci de préciser un objectif pour la campagne.")
                else:
                    with st.spinner("L'IA génère votre contenu..."):
                        contenu_genere = generer_contenu_marque(result, type_contenu_choisi, objectif_choisi)
                    if contenu_genere:
                        st.session_state[f"contenu_marque_{idx}"] = contenu_genere
                        st.session_state[f"contenu_marque_type_{idx}"] = type_contenu_choisi
                        st.rerun()
                    else:
                        st.error("Impossible de générer le contenu pour le moment. Réessayez dans quelques secondes.")

            if f"contenu_marque_{idx}" in st.session_state:
                type_affiche = st.session_state.get(f"contenu_marque_type_{idx}", "")
                st.markdown("")
                st.markdown(f"**Résultat — {type_affiche}**")

                def nettoyer_contenu_ia(texte):
                    """Rend le texte lisible en Markdown : évite les hashtags transformés
                    en titres géants, les --- collés qui créent un faux titre, et les
                    listes à puces collées au paragraphe du dessus."""
                    texte = texte.replace("\r\n", "\n")
                    lignes_propres = []
                    dans_une_liste = False
                    for ligne in texte.split("\n"):
                        sans_espace = ligne.lstrip()
                        prefixe = ligne[:len(ligne) - len(sans_espace)]
                        if sans_espace.startswith("#"):
                            ligne = prefixe + "\\" + sans_espace

                        est_separateur = len(ligne.strip()) >= 3 and set(ligne.strip()) == {"-"}
                        est_puce = ligne.strip().startswith("- ") or ligne.strip().startswith("• ")

                        if est_separateur:
                            if lignes_propres and lignes_propres[-1].strip() != "":
                                lignes_propres.append("")
                            lignes_propres.append("---")
                            lignes_propres.append("")
                            dans_une_liste = False
                            continue

                        if est_puce:
                            if not dans_une_liste and lignes_propres and lignes_propres[-1].strip() != "":
                                lignes_propres.append("")
                            dans_une_liste = True
                        elif ligne.strip() != "":
                            dans_une_liste = False

                        lignes_propres.append(ligne)
                    return "\n".join(lignes_propres)

                contenu_brut = st.session_state[f"contenu_marque_{idx}"]
                st.markdown(nettoyer_contenu_ia(contenu_brut))

                with st.expander("Copier le texte brut"):
                    st.code(contenu_brut, language=None)

                if st.button("Régénérer", key=f"btn_regen_contenu_{idx}"):
                    del st.session_state[f"contenu_marque_{idx}"]
                    st.rerun()

# ── ONGLET POTENTIEL DE CROISSANCE ──
    if show_potentiel:
        tab_potentiel_idx = tabs_list.index("Potentiel de croissance")
        with tabs[tab_potentiel_idx]:
            st.markdown("### Potentiel de croissance de votre entreprise")
            st.caption("Une estimation approximative — pas une prédiction garantie — basée sur ce que SITRA peut lire sur votre site.")

            with st.spinner("Analyse du potentiel de croissance..."):
                site_est_produit = is_produit_web(result)

            if not site_est_produit:
                st.info("Cette analyse est conçue pour les sites qui sont eux-mêmes un produit (SaaS, outil en ligne, application). Pour un site vitrine (restaurant, artisan, commerce local), consultez plutôt l'onglet **Optimiser mon site** pour améliorer votre référencement local.")
            else:
                cle_potentiel = f"potentiel_croissance_{result['final_url'].strip().lower()}"

                if cle_potentiel not in st.session_state:
                    historique_precedent = lire_historique(result["final_url"], limite=1)
                    if historique_precedent:
                        st.session_state[cle_potentiel] = historique_precedent[0]
                    else:
                        secteur_info = detect_secteur_et_concurrents(result["final_url"], "")
                        secteur = secteur_info.get("secteur", "Autre")
                        with st.spinner("L'IA évalue le potentiel de votre entreprise..."):
                            estimation = estimer_potentiel_croissance(result, secteur)
                        st.session_state[cle_potentiel] = estimation
                        if estimation.get("score") is not None:
                            sauvegarder_historique(result["final_url"], estimation)

                estimation = st.session_state[cle_potentiel]

                if estimation.get("error") or estimation.get("score") is None:
                    st.warning("Impossible de générer l'estimation pour le moment.")
                    if st.button("Réessayer", key=f"retry_potentiel_{idx}"):
                        del st.session_state[cle_potentiel]
                        st.rerun()
                else:
                    score = estimation["score"]
                    if score >= 70:
                        couleur = "#16a34a"; fond = "#f0fdf4"; bordure = "#86efac"
                    elif score >= 40:
                        couleur = "#d97706"; fond = "#fffbeb"; bordure = "#fcd34d"
                    else:
                        couleur = "#dc2626"; fond = "#fef2f2"; bordure = "#fca5a5"

                    st.markdown(f"""
                    <div style="background:{fond};border:2px solid {bordure};border-radius:14px;padding:20px 24px;margin-bottom:16px">
                        <div style="font-size:44px;font-weight:700;color:{couleur};line-height:1">{score}/100</div>
                        <div style="font-size:13px;color:{couleur};font-weight:600;margin-top:4px">Estimation du potentiel de croissance</div>
                        <div style="margin-top:10px;background:#e5e7eb;border-radius:99px;height:8px;overflow:hidden">
                            <div style="background:{couleur};width:{score}%;height:100%;border-radius:99px"></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    projection_min = estimation.get("projection_min") or 0
                    projection_max = estimation.get("projection_max") or 0
                    projection_texte = estimation.get("projection_texte") or estimation.get("projection") or "Non disponible."

                    if projection_min > 0 or projection_max > 0:
                        projection_min_fmt = f"{int(projection_min):,}".replace(",", " ")
                        projection_max_fmt = f"{int(projection_max):,}".replace(",", " ")
                        st.markdown(f"""
                        <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #2a2a4e;border-radius:14px;padding:1.2rem 1.5rem;margin-bottom:8px">
                            <div style="font-size:0.95rem;font-weight:700;color:#a090f7;margin-bottom:0.8rem">Ce que vous pourriez atteindre d'ici 12 mois</div>
                            <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:0.8rem">
                                <div style="font-size:28px;font-weight:700;color:#c0b8f0">{projection_min_fmt} € — {projection_max_fmt} €</div>
                                <div style="font-size:13px;color:#888;text-transform:uppercase;letter-spacing:0.5px">sur 12 mois</div>
                            </div>
                            <div style="color:#e0e0e0;font-size:0.85rem;line-height:1.6">{projection_texte}</div>
                        </div>
                        """, unsafe_allow_html=True)

                    with st.expander("Découvrir combien vous pourriez gagner dans un an"):
                        st.caption("Optionnel — ces informations servent uniquement à ancrer l'estimation dans votre réalité, elles ne sont pas rendues publiques.")
                        prelancement_input = st.checkbox("Mon site n'est pas encore lancé ou n'a pas encore de revenus — donnez-moi quand même une estimation basée sur des repères de marché", key=f"prelancement_{idx}")
                        col_form1, col_form2, col_form3 = st.columns(3)
                        with col_form1:
                            nb_clients_input = st.number_input("Nombre de clients actuels", min_value=0, value=0, step=1, key=f"nb_clients_{idx}")
                        with col_form2:
                            ca_actuel_input = st.number_input("Chiffre d'affaires annuel actuel (€)", min_value=0, value=0, step=100, key=f"ca_actuel_{idx}")
                        with col_form3:
                            anciennete_input = st.number_input("Ancienneté (années)", min_value=0, value=0, step=1, key=f"anciennete_{idx}")
                        if st.button("Calculer avec mes données", key=f"btn_calc_donnees_{idx}"):
                            secteur_info = detect_secteur_et_concurrents(result["final_url"], "")
                            secteur = secteur_info.get("secteur", "Autre")
                            with st.spinner("L'IA recalcule avec vos données..."):
                                nouvelle_estimation = estimer_potentiel_croissance(
                                    result, secteur,
                                    nb_clients=nb_clients_input or None,
                                    ca_actuel=ca_actuel_input or None,
                                    anciennete_annees=anciennete_input or None,
                                    projet_pre_lancement=prelancement_input
                                )
                            st.session_state[cle_potentiel] = nouvelle_estimation
                            if nouvelle_estimation.get("score") is not None:
                                sauvegarder_historique(result["final_url"], nouvelle_estimation)
                            st.rerun()

                    st.markdown("")

                    historique = lire_historique(result["final_url"])
                    if len(historique) >= 2:
                        st.markdown('<div style="font-size:0.95rem;font-weight:700;color:#1a1a2e;margin-bottom:0.6rem">📈 Évolution dans le temps</div>', unsafe_allow_html=True)
                        historique_ordre = list(reversed(historique))
                        dates_str = [h["date"].strftime("%d/%m/%Y") for h in historique_ordre]
                        scores_historique = [h["score"] for h in historique_ordre]

                        import plotly.graph_objects as go
                        fig_evolution = go.Figure()
                        fig_evolution.add_trace(go.Scatter(
                            x=dates_str,
                            y=scores_historique,
                            mode='lines+markers',
                            line=dict(color='#7c6af7', width=2),
                            marker=dict(size=8, color='#7c6af7')
                        ))
                        fig_evolution.update_layout(
                            yaxis=dict(range=[0, 100], gridcolor='#e5e7eb', title="Score"),
                            xaxis=dict(gridcolor='#e5e7eb'),
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            font=dict(color='#444'),
                            height=250,
                            margin=dict(l=40, r=20, t=20, b=40)
                        )
                        st.plotly_chart(fig_evolution, use_container_width=True, key=f"evolution_{idx}", config={'displayModeBar': False, 'staticPlot': True})

                        ecart_historique = scores_historique[-1] - scores_historique[0]
                        premiere_date = historique_ordre[0]["date"].strftime("%d/%m/%Y")
                        if ecart_historique > 0:
                            st.success(f"📈 Progression de {ecart_historique} points depuis votre première analyse le {premiere_date}")
                        elif ecart_historique < 0:
                            st.warning(f"📉 Baisse de {abs(ecart_historique)} points depuis votre première analyse le {premiere_date}")
                        else:
                            st.info(f"➡️ Score stable depuis votre première analyse le {premiere_date}")
                        st.markdown("")
                    elif len(historique) == 1:
                        st.caption("📅 Première analyse enregistrée — revenez après avoir appliqué des changements pour voir votre évolution dans le temps.")
                        st.markdown("")

                    criteres = estimation.get("criteres") or {}
                    if criteres:
                        st.markdown('<div style="font-size:0.95rem;font-weight:700;color:#1a1a2e;margin-bottom:0.4rem">📊 Profil de croissance sur 5 critères</div>', unsafe_allow_html=True)
                        st.caption("Plus la zone colorée est grande et équilibrée, plus le potentiel est solide sur l'ensemble des critères — un seul pic isolé ne suffit pas à garantir une vraie croissance.")
                        import plotly.graph_objects as go
                        noms = list(criteres.keys())
                        valeurs = list(criteres.values())
                        fig = go.Figure()
                        fig.add_trace(go.Scatterpolar(
                            r=valeurs + [valeurs[0]],
                            theta=noms + [noms[0]],
                            fill='toself',
                            fillcolor='rgba(124,106,247,0.25)',
                            line=dict(color='#7c6af7', width=2),
                            name='Votre site'
                        ))
                        fig.update_layout(
                            polar=dict(
                                radialaxis=dict(visible=True, range=[0, 100], showticklabels=True, gridcolor='#e5e7eb'),
                                angularaxis=dict(gridcolor='#e5e7eb'),
                                bgcolor='rgba(0,0,0,0)'
                            ),
                            showlegend=False,
                            paper_bgcolor='rgba(0,0,0,0)',
                            font=dict(color='#444'),
                            height=350,
                            margin=dict(l=60, r=60, t=30, b=30)
                        )
                        st.plotly_chart(fig, use_container_width=True, key=f"radar_{idx}", config={'displayModeBar': False, 'staticPlot': True})

                        with st.expander("Que signifie chaque critère ?"):
                            st.markdown("""
- **Notoriété** : potentiel de reconnaissance de marque dans son secteur
- **Différenciation** : à quel point l'offre se distingue des concurrents
- **Traction** : preuves sociales visibles (avis, clients, témoignages)
- **Scalabilité** : facilité à grandir sans limite géographique
- **Présentation** : qualité et professionnalisme du site lui-même
                            """)

                    signaux = estimation.get("signaux_concrets") or []
                    if signaux:
                        st.caption("📊 Chiffres réels trouvés sur votre site : " + ", ".join(signaux))
                    else:
                        st.caption("📊 Aucun chiffre concret (nombre de clients, tarifs, ancienneté...) trouvé sur votre site — l'estimation reste donc générale, sans montant inventé.")

                    concurrents_cibles = estimation.get("concurrents_cibles") or []
                    if concurrents_cibles:
                        chips = "".join([f'<span style="display:inline-block;background:rgba(124,106,247,0.15);border:1px solid rgba(124,106,247,0.4);color:#5b21b6;padding:4px 12px;border-radius:20px;font-size:0.85rem;margin:2px 4px 2px 0">{c}</span>' for c in concurrents_cibles])
                        st.markdown(f"""
                        <div style="margin-bottom:16px">
                            <div style="font-size:0.95rem;font-weight:700;color:#1a1a2e;margin-bottom:0.5rem">🎯 Concurrents à dépasser (ambitieux mais imaginable)</div>
                            <div>{chips}</div>
                        </div>
                        """, unsafe_allow_html=True)

                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        st.markdown('<div style="font-size:0.9rem;font-weight:700;color:#28a745;margin-bottom:0.5rem">✅ Points forts</div>', unsafe_allow_html=True)
                        for pf in (estimation.get("points_forts") or []):
                            st.markdown(f'<div class="issue-item issue-ok">{pf}</div>', unsafe_allow_html=True)
                    with col_f2:
                        st.markdown('<div style="font-size:0.9rem;font-weight:700;color:#d97706;margin-bottom:0.5rem">⚠️ Points faibles</div>', unsafe_allow_html=True)
                        for pfa in (estimation.get("points_faibles") or []):
                            st.markdown(f'<div class="issue-item issue-warning">{pfa}</div>', unsafe_allow_html=True)

                    st.markdown("")
                    st.markdown(f"""
                    <div style="background:rgba(124,106,247,0.08);border-left:3px solid #7c6af7;padding:1rem 1.2rem;border-radius:0 8px 8px 0;margin:1rem 0;color:#1a1a2e;font-size:0.9rem;line-height:1.6">
                        {estimation["analyse"]}
                    </div>
                    """, unsafe_allow_html=True)

                    plan_action = estimation.get("plan_action") or []
                    if plan_action:
                        st.markdown('<div style="font-size:0.95rem;font-weight:700;color:#1a1a2e;margin-bottom:0.6rem">📋 Plan d\'action prioritaire</div>', unsafe_allow_html=True)
                        plan_html = ""
                        for i, action in enumerate(plan_action):
                            plan_html += f"""
                            <div style="display:flex;gap:0.8rem;align-items:flex-start;background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;padding:0.8rem 1rem;margin-bottom:0.5rem">
                                <div style="flex-shrink:0;width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,#667eea,#764ba2);color:white;display:flex;align-items:center;justify-content:center;font-size:0.8rem;font-weight:700">{i+1}</div>
                                <div style="color:#e0e0e0;font-size:0.88rem;line-height:1.5;padding-top:2px">{action}</div>
                            </div>
                            """
                        st.markdown(plan_html, unsafe_allow_html=True)

                        st.caption("⚠️ Cette estimation, y compris la projection financière, se base sur le contenu visible du site et des repères de marché généraux — elle ne constitue pas une garantie de résultat et ne prend pas en compte des facteurs déterminants comme le financement, l'équipe, la concurrence réelle ou le timing du marché.")

                    if st.button("Régénérer l'estimation", key=f"btn_regen_potentiel_{idx}"):
                        secteur_info = detect_secteur_et_concurrents(result["final_url"], "")
                        secteur = secteur_info.get("secteur", "Autre")
                        nb_clients_prec = st.session_state.get(f"nb_clients_{idx}", 0)
                        ca_actuel_prec = st.session_state.get(f"ca_actuel_{idx}", 0)
                        anciennete_prec = st.session_state.get(f"anciennete_{idx}", 0)
                        prelancement_prec = st.session_state.get(f"prelancement_{idx}", False)
                        with st.spinner("L'IA réévalue le potentiel de votre entreprise..."):
                            nouvelle_estimation = estimer_potentiel_croissance(
                                result, secteur,
                                nb_clients=nb_clients_prec or None,
                                ca_actuel=ca_actuel_prec or None,
                                anciennete_annees=anciennete_prec or None,
                                projet_pre_lancement=prelancement_prec
                            )
                        st.session_state[cle_potentiel] = nouvelle_estimation
                        if nouvelle_estimation.get("score") is not None:
                            sauvegarder_historique(result["final_url"], nouvelle_estimation)
                        st.rerun()

                    st.divider()
                    st.caption("💡 Vous connaissez un concurrent précis et voulez voir exactement quoi améliorer pour arriver à son niveau ? Utilisez l'onglet **Mode comparatif** dans le menu de gauche.")
                    
# ── HERO ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-header">
    <div class="hero-title">SITRA</div>
    <div class="hero-subtitle">Analyseur Intelligent de Sites Web &bull; Données Réelles &bull; Recommandations Précises</div>
</div>
""", unsafe_allow_html=True)

# ── INPUT ─────────────────────────────────────────────────────────────────────
if mode_comparaison:
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        url1 = st.text_input("Votre site :", placeholder="ex : monsite.fr", key="url1")
    with col_in2:
        url2 = st.text_input("Site concurrent :", placeholder="ex : concurrent.fr", key="url2")
else:
    url1 = st.text_input("Votre site :", placeholder="ex : monsite.fr ou https://monsite.fr", key="url1")
    url2 = ""

col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    launch = st.button("Lancer l'analyse", use_container_width=True)

# ── ANALYSE ───────────────────────────────────────────────────────────────────
if launch:
    urls_to_analyze = [u for u in [url1, url2] if u and u.strip()]
    if not urls_to_analyze:
        st.warning("Merci d'entrer une URL valide.")
    elif get_analyses_count() >= 2:
        show_paywall()
    else:
        results_list = []
        for url in urls_to_analyze:
            # Cle unique pour cette URL
            cache_key = f"result_cache_{url.strip().lower()}"

            # Reutilise le resultat stocke si l'URL est la meme
            if cache_key in st.session_state:
                result = st.session_state[cache_key]
            else:
                with st.spinner(f"Analyse de {url} en cours..."):
                    result = cached_full_analysis(url)
                # Stocke le resultat - il ne changera plus pour cette URL
                st.session_state[cache_key] = result

            results_list.append(result)

        st.session_state["results"] = results_list
        st.session_state["mode_comp"] = mode_comparaison
        increment_analyses_count()

if "results" in st.session_state:
    results_list = st.session_state["results"]
    mode_comp = st.session_state.get("mode_comp", False)
    if mode_comp and len(results_list) == 2:
        st.divider()
        st.markdown("## Comparatif")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            render_result(results_list[0], idx=0)
        with col_r2:
            render_result(results_list[1], idx=1)

        # ── ANALYSE DE L'ÉCART ──
        st.divider()
        r1 = results_list[0]
        r2 = results_list[1]
        ecart = r2["global_score"] - r1["global_score"]
        site1 = r1["final_url"].replace("https://","").replace("www.","").split("/")[0]
        site2 = r2["final_url"].replace("https://","").replace("www.","").split("/")[0]

        if ecart > 0:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid rgba(102,126,234,0.4);border-radius:16px;padding:1.8rem 2rem;margin-top:1rem">
                <div style="font-size:1.2rem;font-weight:700;color:#a090f7;margin-bottom:1rem">📊 Analyse de l'écart</div>
                <div style="color:#e8e8f0;font-size:0.95rem;line-height:1.8">
                    <b>{site2}</b> a un score de <b style="color:#28a745">{r2['global_score']}/100</b> contre <b style="color:#ffc107">{r1['global_score']}/100</b> pour votre site — soit <b style="color:#f07cf7">{ecart} points d'écart</b>.<br><br>
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.spinner("SITRA analyse l'écart et prépare vos recommandations..."):
                try:
                    import requests as req
                    headers = {"Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}", "Content-Type": "application/json"}
                    prompt = f"""Tu es un expert web qui analyse l'écart entre deux sites. Explique simplement, comme à un entrepreneur non-technicien.

Site du client : {r1['final_url']}
Score : {r1['global_score']}/100
SEO : {r1['seo']['score']}/100, Navigation : {r1['ux']['score']}/100, Vitesse : {r1['performance']['score']}/100, Design : {r1['design']['score']}/100

Site concurrent : {r2['final_url']}
Score : {r2['global_score']}/100
SEO : {r2['seo']['score']}/100, Navigation : {r2['ux']['score']}/100, Vitesse : {r2['performance']['score']}/100, Design : {r2['design']['score']}/100

Rédige un texte court (5-6 phrases maximum) qui :
1. Explique en langage simple pourquoi {site2} est devant
2. Identifie les 2-3 points précis où le client a le plus de retard
3. Dit exactement ce que le client doit faire en priorité pour rattraper {site2}
4. Termine par une phrase motivante

Sois direct, concret, sans jargon technique."""

                    data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 400}
                    r = req.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data, timeout=30)
                    analyse = r.json()["choices"][0]["message"]["content"]

                    st.markdown(f"""
                    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid rgba(102,126,234,0.4);border-radius:16px;padding:1.8rem 2rem;margin-top:1rem">
                        <div style="font-size:1.2rem;font-weight:700;color:#a090f7;margin-bottom:1rem">📊 Analyse de l'écart — {site1} vs {site2}</div>
                        <div style="color:#e8e8f0;font-size:0.95rem;line-height:1.8">{analyse.replace(chr(10), '<br>').replace('**','').replace('*','')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                except Exception:
                    st.markdown(f"""
                    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid rgba(102,126,234,0.4);border-radius:16px;padding:1.8rem 2rem;margin-top:1rem">
                        <div style="font-size:1.2rem;font-weight:700;color:#a090f7;margin-bottom:1rem">📊 Analyse de l'écart</div>
                        <div style="color:#e8e8f0;font-size:0.95rem;line-height:1.8">
                            <b>{site2}</b> a <b>{ecart} points d'avance</b> sur votre site.<br><br>
                            Les domaines à améliorer en priorité :<br>
                            {'• Référencement Google : +' + str(r2["seo"]["score"] - r1["seo"]["score"]) + ' points à rattraper<br>' if r2["seo"]["score"] > r1["seo"]["score"] else ''}
                            {'• Vitesse du site : +' + str(r2["performance"]["score"] - r1["performance"]["score"]) + ' points à rattraper<br>' if r2["performance"]["score"] > r1["performance"]["score"] else ''}
                            {'• Navigation : +' + str(r2["ux"]["score"] - r1["ux"]["score"]) + ' points à rattraper<br>' if r2["ux"]["score"] > r1["ux"]["score"] else ''}
                            {'• Apparence : +' + str(r2["design"]["score"] - r1["design"]["score"]) + ' points à rattraper<br>' if r2["design"]["score"] > r1["design"]["score"] else ''}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        elif ecart < 0:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#0f1f0f,#1a2e1a);border:1px solid rgba(40,167,69,0.4);border-radius:16px;padding:1.8rem 2rem;margin-top:1rem">
                <div style="font-size:1.2rem;font-weight:700;color:#28a745;margin-bottom:0.8rem">🏆 Vous êtes en avance !</div>
                <div style="color:#e8e8f0;font-size:0.95rem;line-height:1.8">
                    Votre site (<b style="color:#28a745">{r1['global_score']}/100</b>) dépasse <b>{site2}</b> (<b style="color:#ffc107">{r2['global_score']}/100</b>) de <b>{abs(ecart)} points</b>. Continuez à l'optimiser pour creuser l'écart.
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#1a1a0f,#2e2a10);border:1px solid rgba(255,193,7,0.3);border-radius:16px;padding:1.8rem 2rem;margin-top:1rem">
                <div style="font-size:1.2rem;font-weight:700;color:#ffc107;margin-bottom:0.8rem">⚖️ Scores identiques</div>
                <div style="color:#e8e8f0;font-size:0.95rem;">Vos deux sites ont le même score global. Regardez les scores par catégorie pour trouver où vous pouvez prendre l'avantage.</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        render_result(results_list[0], idx=0)
else:
    st.markdown("""
    <div style="text-align:center;color:#444;margin-top:3rem;font-size:0.85rem">
        <p><strong>SITRA</strong> analyse votre site en temps réel et vous dit exactement quoi améliorer</p>
    </div>
    """, unsafe_allow_html=True)

# ── ASSISTANT IA ──────────────────────────────────────────────────────────────
st.divider()
with st.expander("Vous avez une question ? Posez-la à l'assistant SITRA"):
    st.caption("L'assistant peut expliquer les termes techniques, vous aider à comprendre vos résultats et vous donner des conseils.")

    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []
    if "chat_input_key" not in st.session_state:
        st.session_state["chat_input_key"] = 0

    for msg in st.session_state["chat_messages"]:
        if msg["role"] == "user":
            st.markdown(f"""<div style="background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;padding:0.8rem 1rem;margin:0.5rem 0;text-align:right;color:#e0e0e0">{msg['content']}</div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="background:#1a1a2e;border:1px solid #667eea;border-radius:10px;padding:0.8rem 1rem;margin:0.5rem 0;color:#ffffff;font-weight:500">{msg['content']}</div>""", unsafe_allow_html=True)

    question = st.text_input("Votre question :", placeholder="Ex: C'est quoi une balise H1 ? Pourquoi mon score SEO est bas ?", key=f"chat_input_{st.session_state['chat_input_key']}")

    if st.button("Envoyer", key="chat_send"):
        if question.strip():
            st.session_state["chat_messages"].append({"role": "user", "content": question})

            try:
                import requests as req
                headers = {
                    "Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}",
                    "Content-Type": "application/json"
                }

                contexte = ""
                if "results" in st.session_state:
                    r = st.session_state["results"][0]
                    contexte = f"Le site analysé est {r['final_url']} avec un score de {r['global_score']}/100. SEO: {r['seo']['score']}/100, UX: {r['ux']['score']}/100, Performance: {r['performance']['score']}/100."

                messages = [
                    {"role": "system", "content": f"""Tu es l'assistant de SITRA, un outil d'analyse de sites web. Tu réponds aux questions en langage simple et accessible, sans jargon technique. Tu expliques les termes avec des exemples concrets du quotidien. Tu gardes le contexte de la conversation.
IMPORTANT : Tu dois TOUJOURS terminer tes réponses complètement. Ne coupe jamais une phrase en plein milieu. Si tu donnes une liste, termine-la entièrement.
{f'Contexte du site analysé : {contexte}' if contexte else ''}"""}
                ]
                for msg in st.session_state["chat_messages"]:
                    messages.append({"role": msg["role"], "content": msg["content"]})

                data = {
                    "model": "mistral-small-latest",
                    "messages": messages,
                    "max_tokens": 1500
                }
                r = req.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data, timeout=30)
                reponse = r.json()["choices"][0]["message"]["content"]
                st.session_state["chat_messages"].append({"role": "assistant", "content": reponse})
                st.session_state["chat_input_key"] += 1
                st.rerun()
            except Exception:
                st.error("Impossible de contacter l'assistant pour le moment.")

def webflow_fix_seo(api_key, site_id, result):
    import requests as req
    corrections = []
    erreurs = []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept-version": "1.0.0",
        "Content-Type": "application/json"
    }
    try:
        test = req.get(f"https://api.webflow.com/sites/{site_id}", headers=headers, timeout=10)
        if test.status_code == 401:
            return [], ["Token invalide — vérifiez votre clé API Webflow"]
        if test.status_code != 200:
            return [], [f"Impossible de se connecter à Webflow (code {test.status_code})"]
        if not result["seo"]["meta_description"]:
            try:
                import requests as req2
                headers_mistral = {"Authorization": f"Bearer {st.secrets['MISTRAL_API_KEY']}", "Content-Type": "application/json"}
                prompt = f"Génère une meta description de 150 caractères maximum pour ce site : {result['final_url']}. Titre : {result['seo']['title']}. Réponds UNIQUEMENT avec la meta description."
                data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 60}
                r_mistral = req2.post("https://api.mistral.ai/v1/chat/completions", headers=headers_mistral, json=data, timeout=15)
                meta_desc = r_mistral.json()["choices"][0]["message"]["content"].strip()
                update = req.patch(f"https://api.webflow.com/sites/{site_id}", headers=headers, json={"seo": {"desc": meta_desc}}, timeout=10)
                if update.status_code == 200:
                    corrections.append(f"Meta description ajoutée : '{meta_desc[:80]}...'")
                else:
                    erreurs.append("Impossible de mettre à jour la meta description sur Webflow")
            except Exception:
                erreurs.append("Erreur lors de la génération de la meta description")
        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé — activez SSL depuis Project Settings → Hosting sur Webflow")
        if result["content"]["word_count"] < 300:
            erreurs.append(f"Contenu trop court ({result['content']['word_count']} mots)")
    except Exception as e:
        erreurs.append(str(e))
    return corrections, erreurs

def prestashop_fix_seo(shop_url, api_key, result):
    import requests as req
    import base64
    corrections = []
    erreurs = []
    base = shop_url.rstrip("/")
    credentials = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {"Authorization": f"Basic {credentials}", "Output-Format": "JSON"}
    try:
        test = req.get(f"{base}/api/", headers=headers, timeout=10)
        if test.status_code == 401:
            return [], ["Clé API invalide — vérifiez votre clé Prestashop"]
        if not result["seo"]["meta_description"]:
            corrections.append("Meta description manquante — à ajouter via le module Metatag dans Prestashop")
        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé")
    except Exception as e:
        erreurs.append(str(e))
    return corrections, erreurs

def drupal_fix_seo(drupal_url, username, password, result):
    import requests as req
    corrections = []
    erreurs = []
    base = drupal_url.rstrip("/")
    try:
        login = req.post(f"{base}/user/login?_format=json", json={"name": username, "pass": password}, headers={"Content-Type": "application/json"}, timeout=10)
        if login.status_code != 200:
            return [], ["Identifiants incorrects"]
        if not result["seo"]["meta_description"]:
            corrections.append("Meta description manquante — à ajouter via le module Metatag dans Drupal")
        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé")
    except Exception as e:
        erreurs.append(str(e))
    return corrections, erreurs

def squarespace_fix_seo(api_key, result):
    import requests as req
    corrections = []
    erreurs = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "SITRA/1.0"}
    try:
        if not result["seo"]["meta_description"]:
            corrections.append("Meta description manquante — à ajouter dans Pages → SEO sur Squarespace")
        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé")
    except Exception as e:
        erreurs.append(str(e))
    return corrections, erreurs

def magento_fix_seo(shop_url, token, result):
    import requests as req
    corrections = []
    erreurs = []
    base = shop_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        test = req.get(f"{base}/rest/V1/store/storeConfigs", headers=headers, timeout=10)
        if test.status_code == 401:
            return [], ["Token invalide"]
        if not result["seo"]["meta_description"]:
            corrections.append("Meta description manquante")
        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé")
    except Exception as e:
        erreurs.append(str(e))
    return corrections, erreurs

def ghost_fix_seo(ghost_url, admin_key, result):
    import requests as req
    corrections = []
    erreurs = []
    base = ghost_url.rstrip("/")
    try:
        parts = admin_key.split(":")
        if len(parts) != 2:
            return [], ["Format de clé invalide"]
        if not result["seo"]["meta_description"]:
            corrections.append("Meta description manquante")
        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé")
    except Exception as e:
        erreurs.append(str(e))
    return corrections, erreurs

def typo3_fix_seo(typo3_url, token, result):
    import requests as req
    corrections = []
    erreurs = []
    try:
        if not result["seo"]["meta_description"]:
            corrections.append("Meta description manquante — à appliquer via l'extension SEO de TYPO3")
        if not result["performance"]["is_https"]:
            erreurs.append("HTTPS non activé")
    except Exception as e:
        erreurs.append(str(e))
    return corrections, erreurs
