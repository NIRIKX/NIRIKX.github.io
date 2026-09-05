"""
Sitra - Moteur d'analyse réel de sites web
Remplace tous les random() par de vraies vérifications
"""

import requests
import time
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import re
import ssl
import socket


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

TIMEOUT = 15

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


def appeler_mistral(headers, data, timeout=30, max_tentatives=3):
    """
    Envoie une requete a l'API Mistral, avec des nouvelles tentatives
    automatiques (delai croissant) en cas de limite de debit (429).
    Le forfait gratuit de Mistral a une limite basse, facilement
    atteinte quand plusieurs appels partent coup sur coup - plutot que
    d'echouer immediatement, on patiente et on reessaie.
    """
    delai = 3
    reponse = requests.post(MISTRAL_URL, headers=headers, json=data, timeout=timeout)
    for _ in range(max_tentatives - 1):
        if reponse.status_code != 429:
            break
        time.sleep(delai)
        delai *= 2
        reponse = requests.post(MISTRAL_URL, headers=headers, json=data, timeout=timeout)
    return reponse


def detect_secteur_et_concurrents(url: str, html: str) -> dict:
    """Détecte le secteur du site avec l'IA et trouve des concurrents à comparer"""
    try:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)[:3000]
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else ""

        # Détection du secteur via Mistral
        secteur_detecte = None
        secteurs_ex_aequo_signal = None
        try:
            import requests as req
            # On récupère la clé depuis les variables d'environnement
            import os
            api_key = os.environ.get("MISTRAL_API_KEY", "")
            if api_key:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                prompt = f"""Analyse ce contenu de site web et réponds UNIQUEMENT avec le secteur parmi cette liste exacte :
Restaurant / Food, E-commerce, Artisan / Services, Santé / Médical, Immobilier, Éducation / Formation, Beauté / Bien-être, Juridique / Finance, Tech / Digital, Sport / Mode, Tourisme / Voyage, Autre

Titre du site : {title_text}
Contenu : {text[:1000]}

Réponds avec UNIQUEMENT le nom du secteur, rien d'autre."""

                data = {
                    "model": "mistral-large-latest",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20
                }
                r = appeler_mistral(headers, data, timeout=15)
                secteur_ia = r.json()["choices"][0]["message"]["content"].strip()
                secteurs_valides = ["Restaurant / Food", "E-commerce", "Artisan / Services", "Santé / Médical",
                                   "Immobilier", "Éducation / Formation", "Beauté / Bien-être", "Juridique / Finance",
                                   "Tech / Digital", "Sport / Mode", "Tourisme / Voyage", "Autre"]
                if secteur_ia in secteurs_valides:
                    secteur_detecte = secteur_ia
        except Exception:
            pass

        # Fallback : détection par mots-clés si l'IA échoue
        if not secteur_detecte:
            text_lower = text.lower()
            secteurs = {
                "Restaurant / Food": ["restaurant", "plat", "cuisine", "food", "pizza", "burger", "reservation"],
                "E-commerce": ["acheter", "panier", "boutique", "shop", "produit", "livraison", "commander"],
                "Artisan / Services": ["artisan", "devis", "chantier", "renovation", "plombier", "electricien"],
                "Santé / Médical": ["médecin", "docteur", "consultation", "santé", "cabinet", "clinique"],
                "Immobilier": ["immobilier", "appartement", "maison", "louer", "vente", "agence"],
                "Éducation / Formation": ["formation", "cours", "apprendre", "école", "université"],
                "Beauté / Bien-être": ["coiffeur", "salon", "beauté", "spa", "massage", "soin"],
                "Juridique / Finance": ["avocat", "comptable", "juridique", "finance", "conseil"],
                "Tech / Digital": ["développement", "web", "application", "digital", "software"],
                "Sport / Mode": ["sport", "mode", "vêtement", "chaussure", "fitness", "nike", "adidas"],
                "Tourisme / Voyage": ["voyage", "hotel", "réservation", "tourisme", "destination"],
                "Autre": []
            }
            scores = {s: sum(1 for m in mots if m in text_lower) for s, mots in secteurs.items()}
            meilleur_score = max(scores.values())
            secteurs_ex_aequo = [s for s, sc in scores.items() if sc == meilleur_score]
            if meilleur_score == 0:
                # Aucun mot-cle trouve, dans aucun secteur : signal nul,
                # mieux vaut "Autre" qu'un secteur choisi au hasard.
                secteur_detecte = "Autre"
            else:
                secteur_detecte = secteurs_ex_aequo[0]
                if len(secteurs_ex_aequo) > 1:
                    # Plusieurs secteurs a egalite mais avec un vrai signal
                    # (ex : un site de vetements en ligne matche a la fois
                    # "E-commerce" et "Sport / Mode") : on garde ce secteur
                    # comme reference, mais on regroupe plus bas les
                    # concurrents de tous les secteurs a egalite plutot que
                    # de tout jeter dans "Autre".
                    secteurs_ex_aequo_signal = secteurs_ex_aequo

        concurrents_types = {
            "Restaurant / Food": ["tripadvisor.fr", "lafourchette.com", "deliveroo.fr", "ubereats.com", "yelp.fr"],
            "E-commerce": ["amazon.fr", "cdiscount.com", "fnac.com", "rueducommerce.fr", "darty.com"],
            "Artisan / Services": ["pages-jaunes.fr", "habitatpresto.com", "houzz.fr", "travaux.com", "quotatis.fr"],
            "Santé / Médical": ["doctolib.fr", "ameli.fr", "sante.fr", "qare.fr", "livi.fr"],
            "Immobilier": ["seloger.com", "leboncoin.fr", "logic-immo.com", "pap.fr", "bienici.com"],
            "Éducation / Formation": ["openclassrooms.com", "coursera.org", "udemy.com", "cned.fr", "studi.com"],
            "Beauté / Bien-être": ["treatwell.fr", "fresha.com", "planity.com", "wecasa.fr"],
            "Juridique / Finance": ["captain-contrat.com", "legalstart.fr", "shine.fr", "qonto.com"],
            "Tech / Digital": ["malt.fr", "upwork.com", "clutch.co", "codeur.com", "fiverr.com"],
            "Sport / Mode": ["zalando.fr", "vinted.fr", "asos.com", "spartoo.com"],
            "Tourisme / Voyage": ["booking.com", "tripadvisor.fr", "airbnb.fr", "abritel.fr"],
            # "Autre" = secteur non determine avec confiance : pas de vrais
            # concurrents a proposer, mieux vaut ne rien suggerer que des
            # sites generiques (Google, Wikipedia...) qui ne sont concurrents
            # de personne.
            "Autre": [],
        }

        if secteurs_ex_aequo_signal:
            concurrents = []
            for s in secteurs_ex_aequo_signal:
                for c in concurrents_types.get(s, []):
                    if c not in concurrents:
                        concurrents.append(c)
        else:
            concurrents = concurrents_types.get(secteur_detecte, [])
        return {
            "secteur": secteur_detecte,
            "concurrents": concurrents,
        }
    except Exception:
        return {"secteur": "Autre", "concurrents": []}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def fetch_site(url: str) -> dict:
    """
    Récupère le contenu d'un site et mesure le temps de réponse.
    Retourne un dict avec html, status_code, response_time, error, final_url
    """
    result = {
        "html": None,
        "status_code": None,
        "response_time": None,
        "error": None,
        "final_url": url,
        "is_https": url.startswith("https://"),
    }

    try:
        start = time.time()
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        result["response_time"] = round(time.time() - start, 2)
        result["status_code"] = r.status_code
        result["final_url"] = r.url
        result["is_https"] = r.url.startswith("https://")

        if r.status_code == 200:
            result["html"] = r.text
        else:
            result["error"] = f"Le site a répondu avec le code HTTP {r.status_code}"

    except requests.exceptions.SSLError:
        result["error"] = "Erreur SSL : certificat invalide ou expiré"
        result["is_https"] = False
    except requests.exceptions.ConnectionError:
        result["error"] = "Impossible de contacter le site (DNS ou connexion refusée)"
    except requests.exceptions.Timeout:
        result["error"] = f"Le site n'a pas répondu en moins de {TIMEOUT}s"
    except Exception as e:
        result["error"] = str(e)

    return result


def analyze_seo(soup: BeautifulSoup, url: str) -> dict:
    """Analyse SEO réelle : title, meta, H1, H2, images alt, etc."""
    issues = []
    score = 100

    # Title
    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    if not title_text:
        issues.append("❌ Pas de balise <title> — essentiel pour le référencement Google")
        score -= 20
    elif len(title_text) < 10:
        issues.append(f"⚠️ Titre trop court ({len(title_text)} caractères) — vise 50-60 caractères")
        score -= 10
    elif len(title_text) > 70:
        issues.append(f"⚠️ Titre trop long ({len(title_text)} caractères) — Google le tronque après 60")
        score -= 5

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    meta_content = meta_desc.get("content", "").strip() if meta_desc else ""
    if not meta_content:
        issues.append("❌ Pas de meta description — impacte fortement le taux de clic Google")
        score -= 15
    elif len(meta_content) < 50:
        issues.append(f"⚠️ Meta description trop courte ({len(meta_content)} chars) — vise 120-160 caractères")
        score -= 8
    elif len(meta_content) > 170:
        issues.append(f"⚠️ Meta description trop longue ({len(meta_content)} chars) — Google la tronque")
        score -= 3

    # H1
    h1_tags = soup.find_all("h1")
    if not h1_tags:
        issues.append("❌ Pas de balise H1 — Google utilise le H1 pour comprendre le sujet principal")
        score -= 15
    elif len(h1_tags) > 1:
        issues.append(f"⚠️ {len(h1_tags)} balises H1 détectées — il ne doit y en avoir qu'une seule")
        score -= 5

    # H2 structure
    h2_tags = soup.find_all("h2")
    if not h2_tags:
        issues.append("⚠️ Aucun H2 — structure le contenu avec des sous-titres pour le SEO")
        score -= 5

    # Images sans alt
    images = soup.find_all("img")
    images_no_alt = [img for img in images if img.get("alt") is None]
    if images_no_alt:
        pct = int(len(images_no_alt) / max(len(images), 1) * 100)
        issues.append(f"⚠️ {len(images_no_alt)}/{len(images)} images sans attribut alt ({pct}%) — Google ne peut pas les indexer")
        score -= min(10, len(images_no_alt) * 2)

    # Canonical
    canonical = soup.find("link", rel="canonical")
    if not canonical:
        issues.append("⚠️ Pas de balise canonical — peut causer du contenu dupliqué")
        score -= 3

    # Viewport meta (mobile)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if not viewport:
        issues.append("❌ Pas de meta viewport — le site ne sera pas responsive sur mobile")
        score -= 10

    # Lang attribute
    html_tag = soup.find("html")
    lang = html_tag.get("lang", "") if html_tag else ""
    if not lang:
        issues.append("⚠️ Pas d'attribut lang sur <html> — Google ne sait pas quelle langue cibler")
        score -= 3

    score = max(0, min(100, score))

    return {
        "score": score,
        "title": title_text,
        "meta_description": meta_content,
        "h1_count": len(h1_tags),
        "h2_count": len(h2_tags),
        "images_total": len(images),
        "images_no_alt": len(images_no_alt),
        "has_canonical": canonical is not None,
        "has_viewport": viewport is not None,
        "has_lang": bool(lang),
        "issues": issues,
    }


def analyze_ux(soup: BeautifulSoup, url: str) -> dict:
    """Analyse UX : navigation, CTA, contact, lisibilité, formulaires"""
    issues = []
    score = 100

    # Menu / navigation
    nav_tags = soup.find_all(["nav", "header"])
    has_nav = len(nav_tags) > 0
    if not has_nav:
        issues.append("⚠️ Pas de balise <nav> ou <header> détectée — structure de navigation manquante")
        score -= 8

    # Liens dans la nav
    nav_links = []
    for nav in nav_tags:
        nav_links.extend(nav.find_all("a"))
    if len(nav_links) == 0:
        issues.append("⚠️ Aucun lien dans la navigation principale")
        score -= 5
    elif len(nav_links) > 10:
        issues.append(f"⚠️ Navigation surchargée ({len(nav_links)} liens) — simplifie à 5-7 éléments max")
        score -= 5

    # Boutons CTA
    buttons = soup.find_all("button") + soup.find_all("a", class_=re.compile(r"btn|button|cta", re.I))
    if not buttons:
        issues.append("❌ Aucun bouton d'action (CTA) détecté — comment les visiteurs passent à l'action ?")
        score -= 15
    
    # Contact
    page_text = soup.get_text().lower()
    has_contact = any(word in page_text for word in ["contact", "email", "e-mail", "@", "téléphone", "telephone", "whatsapp"])
    if not has_contact:
        issues.append("❌ Aucune information de contact visible — les visiteurs ne peuvent pas vous joindre")
        score -= 12

    # Formulaires
    forms = soup.find_all("form")
    forms_no_label = 0
    for form in forms:
        inputs = form.find_all("input", type=lambda t: t not in ["hidden", "submit", "button"])
        labels = form.find_all("label")
        if len(inputs) > len(labels):
            forms_no_label += 1
    if forms_no_label > 0:
        issues.append(f"⚠️ {forms_no_label} formulaire(s) avec des champs sans label — problème d'accessibilité")
        score -= 5

    # Mentions légales / footer
    footer = soup.find("footer")
    has_footer = footer is not None
    if not has_footer:
        issues.append("⚠️ Pas de pied de page — les mentions légales et contacts doivent y figurer")
        score -= 8
    else:
        footer_text = footer.get_text().lower()
        if not any(word in footer_text for word in ["mentions légales", "mention", "cgv", "politique", "privacy", "legal"]):
            issues.append("⚠️ Mentions légales non détectées — obligatoires en France (RGPD)")
            score -= 8

    # Texte lisible (longueur paragraphes)
    paragraphs = soup.find_all("p")
    long_paragraphs = [p for p in paragraphs if len(p.get_text()) > 600]
    if long_paragraphs:
        issues.append(f"⚠️ {len(long_paragraphs)} paragraphe(s) très long(s) — divise-les pour faciliter la lecture")
        score -= 5

    score = max(0, min(100, score))

    return {
        "score": score,
        "has_nav": has_nav,
        "nav_links_count": len(nav_links),
        "buttons_count": len(buttons),
        "has_contact": has_contact,
        "forms_count": len(forms),
        "has_footer": has_footer,
        "long_paragraphs": len(long_paragraphs),
        "issues": issues,
    }


def analyze_content(soup: BeautifulSoup) -> dict:
    """Analyse du contenu : fautes basiques, clarté, lisibilité"""
    issues = []
    score = 100

    text = soup.get_text(" ", strip=True)
    words = text.split()
    word_count = len(words)

    if word_count < 100:
        issues.append(f"⚠️ Contenu très court ({word_count} mots) — Google préfère les pages avec 300+ mots")
        score -= 15
    elif word_count < 300:
        issues.append(f"⚠️ Contenu assez court ({word_count} mots) — vise au moins 400-600 mots sur la page d'accueil")
        score -= 8

    # Détection fautes courantes (français/anglais)
    common_mistakes_fr = [
        (r'\bsa\b(?=\s+(?:va|fait|marche|passe))', "confusion sa/ça"),
        (r'\bdon[ck]\b', "donk → donc"),
        (r'\bpourquoi\s+que\b', "pourquoi que → pourquoi"),
        (r'\bà\s+cause\s+que\b', "à cause que → parce que"),
    ]

    mistakes_found = []
    text_lower = text.lower()
    for pattern, desc in common_mistakes_fr:
        if re.search(pattern, text_lower):
            mistakes_found.append(desc)

    if mistakes_found:
        issues.append(f"⚠️ Erreurs de langue potentielles détectées : {', '.join(mistakes_found)}")
        score -= 8

    # Répétitions excessives
    if word_count > 0:
        from collections import Counter
        word_freq = Counter(w.lower().strip('.,;:!?') for w in words if len(w) > 5)
        most_common = word_freq.most_common(3)
        overused = [(w, c) for w, c in most_common if c / word_count > 0.05]
        if overused:
            issues.append(f"⚠️ Mots très répétés : {', '.join([f'{w} ({c}x)' for w,c in overused])} — varie le vocabulaire")
            score -= 5

    # Majuscules excessives
    caps_words = [w for w in words if w.isupper() and len(w) > 3]
    if len(caps_words) > 5:
        issues.append(f"⚠️ {len(caps_words)} mots en majuscules — évite de crier sur tes visiteurs")
        score -= 5

    score = max(0, min(100, score))

    return {
        "score": score,
        "word_count": word_count,
        "issues": issues,
    }


def analyze_design(soup: BeautifulSoup, url: str) -> dict:
    """Analyse design : couleurs, polices, images, cohérence visuelle"""
    issues = []
    score = 100

    # Favicon
    favicon = soup.find("link", rel=lambda r: r and "icon" in r)
    if not favicon:
        issues.append("⚠️ Pas de favicon — un détail qui renforce l'identité de la marque")
        score -= 5

    # Inline styles excessifs
    inline_styles = soup.find_all(style=True)
    if len(inline_styles) > 30:
        issues.append(f"⚠️ {len(inline_styles)} éléments avec des styles inline — utilise un fichier CSS dédié")
        score -= 5

    # Images
    images = soup.find_all("img")
    images_no_size = [img for img in images if not (img.get("width") or img.get("height"))]
    if images_no_size and len(images_no_size) > len(images) * 0.5:
        issues.append(f"⚠️ {len(images_no_size)} images sans dimensions — peut causer des sauts de mise en page")
        score -= 5

    # Polices (détection via link Google Fonts ou @font-face)
    google_fonts = soup.find_all("link", href=re.compile(r"fonts\.google|fonts\.gstatic"))
    custom_fonts = bool(google_fonts)

    # Open Graph (partage réseaux sociaux)
    og_title = soup.find("meta", property="og:title")
    og_image = soup.find("meta", property="og:image")
    if not og_title:
        issues.append("⚠️ Pas de balise og:title — le partage sur réseaux sociaux sera peu attrayant")
        score -= 8
    if not og_image:
        issues.append("⚠️ Pas de og:image — aucune image affichée lors du partage sur Facebook/LinkedIn")
        score -= 8

    # Extraction des couleurs dominantes (depuis les styles inline et attributs)
    color_candidates = []
    for tag in soup.find_all(style=True):
        colors = re.findall(r'#([0-9a-fA-F]{3,6})\b|rgba?\([\d,\s.]+\)', tag.get("style", ""))
        color_candidates.extend(colors[:3])

    score = max(0, min(100, score))

    return {
        "score": score,
        "has_favicon": favicon is not None,
        "has_google_fonts": custom_fonts,
        "has_og_tags": og_title is not None,
        "issues": issues,
        "detected_colors": color_candidates[:5],
    }


def analyze_performance(response_time: float, html: str, is_https: bool) -> dict:
    """Analyse performance : vitesse, HTTPS, taille page"""
    issues = []
    score = 100

    # HTTPS
    if not is_https:
        issues.append("❌ Le site n'utilise pas HTTPS — Google pénalise les sites non sécurisés")
        score -= 25

    # Temps de réponse
    if response_time is None:
        score -= 10
    elif response_time > 3:
        issues.append(f"❌ Temps de réponse très lent : {response_time}s — les visiteurs partent après 3s")
        score -= 20
    elif response_time > 1.5:
        issues.append(f"⚠️ Temps de réponse moyen : {response_time}s — vise moins de 1s")
        score -= 10
    elif response_time < 0.5:
        pass  # excellent

    # Taille du HTML
    html_size_kb = len(html.encode("utf-8")) / 1024 if html else 0
    if html_size_kb > 500:
        issues.append(f"⚠️ Page HTML lourde : {html_size_kb:.0f}KB — optimise le code")
        score -= 8
    elif html_size_kb > 200:
        issues.append(f"⚠️ Page HTML assez lourde : {html_size_kb:.0f}KB")
        score -= 4

    # Scripts bloquants
    if html:
        soup_check = BeautifulSoup(html, "lxml")
        blocking_scripts = soup_check.find_all("script", src=True)
        head = soup_check.find("head")
        scripts_in_head = []
        if head:
            scripts_in_head = head.find_all("script", src=True)
        if len(scripts_in_head) > 5:
            issues.append(f"⚠️ {len(scripts_in_head)} scripts dans le <head> — peuvent ralentir le chargement")
            score -= 5

    score = max(0, min(100, score))

    return {
        "score": score,
        "is_https": is_https,
        "response_time": response_time,
        "html_size_kb": round(html_size_kb, 1),
        "issues": issues,
    }


def full_analysis(url: str) -> dict:
    """
    Lance l'analyse complète d'un site.
    Retourne un dict structuré avec tous les résultats.
    """
    url = normalize_url(url)
    if not url:
        return {"error": "URL invalide"}

    # Fetch
    fetch = fetch_site(url)

    if fetch["error"] and not fetch["html"]:
        return {
            "url": url,
            "error": fetch["error"],
            "is_https": fetch["is_https"],
            "response_time": fetch["response_time"],
            "status_code": fetch["status_code"],
        }

    html = fetch["html"] or ""
    soup = BeautifulSoup(html, "lxml")

    # Analyses
    seo = analyze_seo(soup, url)
    ux = analyze_ux(soup, url)
    content = analyze_content(soup)
    design = analyze_design(soup, url)
    performance = analyze_performance(fetch["response_time"], html, fetch["is_https"])

    # Score global pondéré
    global_score = round(
        seo["score"] * 0.30 +
        ux["score"] * 0.25 +
        content["score"] * 0.15 +
        design["score"] * 0.15 +
        performance["score"] * 0.15
    )

    # Toutes les issues triées par catégorie
    all_issues = []
    for cat, data in [("SEO", seo), ("UX", ux), ("Contenu", content), ("Design", design), ("Performance", performance)]:
        for issue in data.get("issues", []):
            all_issues.append({"category": cat, "message": issue})

    return {
        "url": url,
        "final_url": fetch["final_url"],
        "status_code": fetch["status_code"],
        "response_time": fetch["response_time"],
        "is_https": fetch["is_https"],
        "global_score": global_score,
        "seo": seo,
        "ux": ux,
        "content": content,
        "design": design,
        "performance": performance,
        "all_issues": all_issues,
        "total_issues": len(all_issues),
        "error": None,
    }


def get_score_label(score: int) -> tuple:
    if score >= 90:
        return "Excellent", "vert", "#28a745"
    elif score >= 75:
        return "Bon", "jaune", "#ffc107"
    elif score >= 55:
        return "A ameliorer", "orange", "#fd7e14"
    else:
        return "Critique", "rouge", "#dc3545"


def is_produit_web(result: dict) -> bool:
    """
    Devine si le site analyse est un produit web (SaaS, appli, outil en ligne)
    ou un site vitrine classique (restaurant, artisan, commerce local).
    """
    titre = (result.get("seo", {}).get("title") or "").lower()
    meta = (result.get("seo", {}).get("meta_description") or "").lower()
    url = (result.get("final_url") or result.get("url") or "").lower()
    texte = f"{titre} {meta} {url}"

    mots_cles_produit = [
        "saas", "app", "application", "dashboard", "tableau de bord",
        "essai gratuit", "free trial", "pricing", "tarifs", "abonnement",
        "api", "plateforme", "outil en ligne", "logiciel", "software",
        "login", "connexion", "sign up", "s'inscrire", "demo", "démo",
        "analyse", "analyseur", "audit", "scanner", "générateur", "generateur",
        "intelligence artificielle", "automatis",
    ]
    mots_cles_vitrine = [
        "restaurant", "menu", "reservation", "réservation", "coiffeur",
        "salon", "artisan", "plombier", "electricien", "électricien",
        "boulangerie", "cabinet", "clinique", "medecin", "médecin",
        "avocat", "notaire", "boutique", "magasin", "commerce", "atelier",
    ]

    score_produit = sum(1 for mot in mots_cles_produit if mot in texte)
    score_vitrine = sum(1 for mot in mots_cles_vitrine if mot in texte)

    # En cas d'egalite (y compris 0-0, aucun mot trouve), on penche vers
    # "produit web" plutot que "vitrine" — un vrai site vitrine (restaurant,
    # coiffeur...) mentionne presque toujours son metier, alors qu'un outil
    # ne se decrit pas toujours avec des mots evidents.
    return score_produit >= score_vitrine

def extraire_signaux_concrets(html: str) -> list:
    """
    Cherche dans le texte reel du site des chiffres deja publies par le
    site lui-meme (nombre de clients, annee de creation, avis, tarifs).
    Sert a ancrer l'estimation IA dans des donnees reelles plutot que de
    la laisser deviner un chiffre d'affaires dans le vide.
    """
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        texte = soup.get_text(" ", strip=True)
    except Exception:
        return []

    signaux = []

    for m in re.finditer(r'(\d[\d\s]{0,6})\s*\+?\s*(clients?|utilisateurs?|abonn[ée]s?|membres?|entreprises?)', texte, re.I):
        signaux.append(f"{m.group(1).strip()} {m.group(2)}")

    for m in re.finditer(r'depuis\s+(19|20)\d{2}', texte, re.I):
        signaux.append(m.group(0))

    for m in re.finditer(r'\d{1,2}\s*ans?\s*d.exp[ée]rience', texte, re.I):
        signaux.append(m.group(0))

    for m in re.finditer(r'\d[.,]\d\s*/\s*5|\d+\s*avis', texte, re.I):
        signaux.append(m.group(0))

    for m in re.finditer(r'(?:à partir de\s*)?\d+[\.,]?\d*\s*€\s*(?:/\s*(?:mois|an|mo|jour))?', texte, re.I):
        signaux.append(m.group(0))

    signaux_uniques = []
    for s in signaux:
        s = s.strip()
        if s and s not in signaux_uniques:
            signaux_uniques.append(s)
    return signaux_uniques[:10]

def extraire_montant(texte: str) -> float:
    """
    Extrait un nombre (entier ou decimal) depuis un texte libre genere
    par l'IA. Retourne 0 si aucun chiffre n'est trouve.
    """
    if not texte:
        return 0
    nettoye = texte.replace("€", "").replace(" ", "").replace("\u00a0", "").replace(",", ".")
    match = re.search(r'\d+\.?\d*', nettoye)
    return float(match.group()) if match else 0


def estimer_potentiel_croissance(result: dict, secteur: str = "Autre", nb_clients=None, ca_actuel=None, anciennete_annees=None, projet_pre_lancement: bool = False) -> dict:
    """
    Demande a l'IA une estimation approximative du potentiel de croissance.
    Pour la projection financiere, l'IA fournit les PARAMETRES (tarif moyen,
    fourchette de clients estimee) et EXPLIQUE le raisonnement derriere ces
    parametres. Le calcul arithmetique final (tarif x clients) est fait par
    le code Python, pas par l'IA, pour garantir que le chiffre affiche
    corresponde exactement aux hypotheses enoncees, sans incoherence interne.
    """
    try:
        import requests as req
        import os
        api_key = os.environ.get("MISTRAL_API_KEY", "")
        if not api_key:
            return {"score": None, "criteres": None, "concurrents_cibles": None, "points_forts": None, "points_faibles": None, "plan_action": None, "projection_min": None, "projection_max": None, "projection_texte": None, "analyse": None, "signaux_concrets": [], "error": "Cle API manquante"}

        titre = result.get("seo", {}).get("title", "") or ""
        meta = result.get("seo", {}).get("meta_description", "") or ""
        url = result.get("final_url", "") or ""

        signaux_concrets = []
        try:
            r_site = req.get(url, timeout=TIMEOUT, headers=HEADERS)
            if r_site.status_code == 200:
                signaux_concrets = extraire_signaux_concrets(r_site.text)
        except Exception:
            pass
        signaux_str = ", ".join(signaux_concrets) if signaux_concrets else "aucun chiffre concret trouve sur le site"

        texte_complet = f"{titre} {meta}".lower()
        mots_traction = ["avis", "témoignage", "temoignage", "client depuis", "clients satisfaits",
                          "ils nous font confiance", "vu dans", "partenaire officiel", "certifié", "certifie"]
        signaux_traction = [m for m in mots_traction if m in texte_complet]
        traction_str = ", ".join(signaux_traction) if signaux_traction else "aucun signal de traction detecte"

        donnees_utilisateur = []
        if nb_clients is not None and nb_clients > 0:
            donnees_utilisateur.append(f"{nb_clients} clients actuels")
        if ca_actuel is not None and ca_actuel > 0:
            donnees_utilisateur.append(f"chiffre d'affaires annuel actuel : {ca_actuel} euros")
        if anciennete_annees is not None and anciennete_annees > 0:
            donnees_utilisateur.append(f"{anciennete_annees} annee(s) d'existence")
        donnees_str = ", ".join(donnees_utilisateur) if donnees_utilisateur else "aucune donnee reelle fournie par l'utilisateur"

        if ca_actuel is not None and ca_actuel > 0:
            base_clients_str = f"{nb_clients} clients actuels" if (nb_clients is not None and nb_clients > 0) else "nombre de clients actuels non precise"
            consigne_projection = f"""Ce site genere DEJA un chiffre d'affaires reel de {ca_actuel} euros par an
({base_clients_str}). C'est la VRAIE SITUATION DE DEPART : ne l'ignore surtout pas et
ne calcule pas comme si l'activite partait de zero.
TARIF_MOYEN: [prix mensuel moyen coherent avec le chiffre d'affaires actuel fourni, un seul nombre]
CLIENTS_MIN: [nombre de clients payants estime dans le pire cas realiste a 12 mois, en PARTANT de la situation actuelle, un seul nombre]
CLIENTS_MAX: [nombre de clients payants estime dans le meilleur cas realiste a 12 mois, en PARTANT de la situation actuelle, un seul nombre]
Ces 3 nombres doivent etre COHERENTS entre eux et avec le chiffre d'affaires actuel
fourni. Dans PROJECTION_TEXTE, ecris une VRAIE PETITE HISTOIRE de 5 A 6 PHRASES en
partant EXPLICITEMENT de la situation actuelle du site ({ca_actuel} euros par an),
comme si tu racontais a un ami comment faire grandir ce qu'il a deja construit.

EXEMPLE A IMITER (adapte au site precis, en partant bien du chiffre d'affaires fourni) :
"Avec vos {ca_actuel} euros de chiffre d'affaires actuels, vous avez deja une base
solide sur laquelle construire. Un outil comme le votre se vend generalement entre 30
et 60 euros par mois une fois la confiance etablie. Pour faire grandir ce que vous avez
deja, publier 1 a 2 articles par semaine sur des problemes concrets peut attirer de
nouveaux clients au meme rythme que les precedents. En gardant cette regularite et en
montrant les avis de vos clients actuels, la croissance peut s'accelerer naturellement.
Le potentiel est bien reel, il suffit de continuer sur cette lancee."

Mots du quotidien uniquement, sans argot, sans jargon. Ne calcule pas toi-meme le total
en euros, contente-toi d'expliquer le raisonnement. IMPORTANT : ne mentionne JAMAIS un
prix "par mois" dans ton texte, uniquement des montants sur l'annee entiere ou sans
precision de periode (ex: dire "un prix autour de 700 euros par client sur l'annee"
plutot que "59 euros par mois"), pour eviter toute confusion avec le total annuel
affiche au-dessus de ton texte."""
        elif projet_pre_lancement:
            consigne_projection = """Le site n'a PAS ENCORE de chiffre d'affaires reel (projet en
developpement). Donne les PARAMETRES bases UNIQUEMENT sur des reperes de marche :
TARIF_MOYEN: [prix mensuel moyen realiste en euros pour ce type de produit, un seul nombre]
CLIENTS_MIN: [nombre de clients payants estime dans le pire cas realiste a 12 mois, un seul nombre]
CLIENTS_MAX: [nombre de clients payants estime dans le meilleur cas realiste a 12 mois, un seul nombre]
Ces 3 nombres doivent etre COHERENTS entre eux. Dans PROJECTION_TEXTE, ecris une VRAIE
PETITE HISTOIRE de 5 A 6 PHRASES qui prend le temps d'expliquer, comme si tu racontais a
un ami comment son entreprise pourrait grandir.

EXEMPLE A IMITER (adapte les details a ce site precis) :
"Des outils similaires se vendent entre 30 et 60 euros par mois, un prix que les
clients acceptent parce que ca inclut un vrai suivi et des conseils personnalises. Pour
attirer les premiers clients, publier 1 a 2 articles par semaine sur des problemes
concrets que vos clients recherchent deja sur Google est un bon point de depart. Avec
cette regularite, les 15 a 20 premiers clients viennent souvent du bouche-a-oreille et
des recherches Google directes. Une fois que quelques clients satisfaits laissent des
avis visibles, la confiance grandit et attire plus facilement les clients suivants,
jusqu'a atteindre le haut de la fourchette. Le potentiel est bien reel, il suffit de
s'y mettre serieusement des maintenant."

Mots du quotidien uniquement, sans argot, sans jargon. Ne calcule pas toi-meme le total
en euros, contente-toi d'expliquer le raisonnement."""
        else:
            consigne_projection = """Aucune donnee financiere n'est disponible et l'option projet en
developpement n'est pas cochee. Mets TARIF_MOYEN, CLIENTS_MIN et CLIENTS_MAX a 0, et
dans PROJECTION_TEXTE ecris exactement : "Non disponible — renseignez votre chiffre
d'affaires actuel ou cochez la case projet en developpement pour obtenir une
projection chiffree." """

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        prompt = f"""Tu es un investisseur experimente qui evalue rapidement des entreprises a partir de leur site web.

Site : {url}
Titre : {titre}
Description : {meta}
Secteur detecte : {secteur}
Chiffres et signaux concrets REELLEMENT trouves sur le site : {signaux_str}
Autres signaux de traction : {traction_str}
Donnees reelles fournies par l'utilisateur : {donnees_str}

Identifie toi-meme 2-3 concurrents AMBITIEUX MAIS REALISTES (interdiction de citer des
geants generalistes hors-sujet type Google, Wikipedia, Amazon, sauf si pertinent).

REGLE ABSOLUE SUR L'ARGENT : n'invente JAMAIS un chiffre precis sans base reelle ou sans
que l'option projet en developpement soit cochee.

Note aussi ce site sur 5 CRITERES separes, chacun de 0 a 100 :
- NOTORIETE : potentiel de notoriete/reconnaissance de marque
- DIFFERENCIATION : a quel point l'offre se distingue des concurrents
- TRACTION : preuves sociales visibles (avis, clients, temoignages)
- SCALABILITE : facilite a grandir/se reproduire sans limite geographique
- PRESENTATION : qualite et professionnalisme du site lui-meme

Donne un PLAN D'ACTION de 3 a 5 recommandations concretes et priorisees, autant que pertinent.

{consigne_projection}

Reponds en 12 parties EXACTEMENT, sans markdown, texte brut :
SCORE: [chiffre entre 0 et 100]
CRITERES: [5 chiffres entre 0 et 100 separes par des virgules, dans l'ordre NOTORIETE,DIFFERENCIATION,TRACTION,SCALABILITE,PRESENTATION]
CONCURRENTS: [2-3 concurrents, separes par des virgules]
FORTS: [3 a 5 points forts, separes par des points-virgules]
FAIBLES: [3 a 5 points faibles, separes par des points-virgules]
PLAN: [3 a 5 recommandations, separees par des points-virgules]
TARIF_MOYEN: [nombre, ou 0]
CLIENTS_MIN: [nombre, ou 0]
CLIENTS_MAX: [nombre, ou 0]
PROJECTION_TEXTE: [explication en 2-3 phrases, ou le message non disponible]
ANALYSE: [3-4 phrases, rappelant que c'est une approximation]"""

        data = {"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}], "max_tokens": 750}
        r = appeler_mistral(headers, data, timeout=30)
        contenu = r.json()["choices"][0]["message"]["content"]
        contenu = contenu.replace("**", "").replace("*", "")

        score = 50
        criteres = {"Notoriété": 50, "Différenciation": 50, "Traction": 50, "Scalabilité": 50, "Présentation": 50}
        concurrents_cibles = []
        points_forts = []
        points_faibles = []
        plan_action = []
        tarif_moyen = 0
        clients_min = 0
        clients_max = 0
        projection_texte = "Non disponible."
        analyse = contenu

        try:
            if "SCORE:" in contenu:
                partie_score = contenu.split("SCORE:")[1].split("CRITERES:")[0].strip()
                score = int(''.join(c for c in partie_score if c.isdigit())[:3] or "50")
            if "CRITERES:" in contenu and "CONCURRENTS:" in contenu:
                partie_crit = contenu.split("CRITERES:")[1].split("CONCURRENTS:")[0].strip()
                nombres = [int(''.join(c for c in n if c.isdigit())[:3] or "50") for n in partie_crit.split(",") if n.strip()]
                noms_criteres = ["Notoriété", "Différenciation", "Traction", "Scalabilité", "Présentation"]
                if len(nombres) == 5:
                    criteres = {noms_criteres[i]: max(0, min(100, nombres[i])) for i in range(5)}
            if "CONCURRENTS:" in contenu and "FORTS:" in contenu:
                partie_conc = contenu.split("CONCURRENTS:")[1].split("FORTS:")[0].strip()
                concurrents_cibles = [c.strip(" -,") for c in partie_conc.split(",") if c.strip(" -,")]
            if "FORTS:" in contenu and "FAIBLES:" in contenu:
                partie_forts = contenu.split("FORTS:")[1].split("FAIBLES:")[0].strip()
                points_forts = [p.strip(" -;") for p in partie_forts.split(";") if p.strip(" -;")]
            if "FAIBLES:" in contenu and "PLAN:" in contenu:
                partie_faibles = contenu.split("FAIBLES:")[1].split("PLAN:")[0].strip()
                points_faibles = [p.strip(" -;") for p in partie_faibles.split(";") if p.strip(" -;")]
            if "PLAN:" in contenu and "TARIF_MOYEN:" in contenu:
                partie_plan = contenu.split("PLAN:")[1].split("TARIF_MOYEN:")[0].strip()
                plan_action = [p.strip(" -;") for p in partie_plan.split(";") if p.strip(" -;")]
            if "TARIF_MOYEN:" in contenu and "CLIENTS_MIN:" in contenu:
                partie_tarif = contenu.split("TARIF_MOYEN:")[1].split("CLIENTS_MIN:")[0].strip()
                tarif_moyen = extraire_montant(partie_tarif)
            if "CLIENTS_MIN:" in contenu and "CLIENTS_MAX:" in contenu:
                partie_cmin = contenu.split("CLIENTS_MIN:")[1].split("CLIENTS_MAX:")[0].strip()
                clients_min = extraire_montant(partie_cmin)
            if "CLIENTS_MAX:" in contenu and "PROJECTION_TEXTE:" in contenu:
                partie_cmax = contenu.split("CLIENTS_MAX:")[1].split("PROJECTION_TEXTE:")[0].strip()
                clients_max = extraire_montant(partie_cmax)
            if "PROJECTION_TEXTE:" in contenu and "ANALYSE:" in contenu:
                projection_texte = contenu.split("PROJECTION_TEXTE:")[1].split("ANALYSE:")[0].strip()
            if "ANALYSE:" in contenu:
                analyse = contenu.split("ANALYSE:")[1].strip()
        except Exception:
            pass

        # Le calcul final est fait ici, en Python, pas par l'IA — garantit la
        # coherence entre le texte explicatif et le chiffre affiche.
        projection_min = round(tarif_moyen * clients_min * 12) if tarif_moyen > 0 and clients_min > 0 else 0
        projection_max = round(tarif_moyen * clients_max * 12) if tarif_moyen > 0 and clients_max > 0 else 0

        return {
            "score": max(0, min(100, score)),
            "criteres": criteres,
            "concurrents_cibles": concurrents_cibles,
            "points_forts": points_forts,
            "points_faibles": points_faibles,
            "plan_action": plan_action,
            "projection_min": projection_min,
            "projection_max": projection_max,
            "projection_texte": projection_texte,
            "tarif_moyen": tarif_moyen,
            "clients_min": clients_min,
            "clients_max": clients_max,
            "analyse": analyse,
            "signaux_concrets": signaux_concrets,
            "error": None,
        }
    except Exception as e:
        return {"score": None, "criteres": None, "concurrents_cibles": None, "points_forts": None, "points_faibles": None, "plan_action": None, "projection_min": None, "projection_max": None, "projection_texte": None, "analyse": None, "signaux_concrets": [], "error": str(e)}


def get_connexion_historique():
    """
    Ouvre une connexion a la base de donnees Neon, cree la table
    d'historique si elle n'existe pas, et ajoute les colonnes manquantes
    si la table existait deja avant ces ajouts. Retourne None si la
    connexion echoue.
    """
    try:
        import psycopg2
        import os
        db_url = os.environ.get("NEON_DATABASE_URL", "")
        if not db_url:
            return None
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS historique_potentiel (
                id SERIAL PRIMARY KEY,
                url TEXT NOT NULL,
                date_analyse TIMESTAMP DEFAULT NOW(),
                score INTEGER,
                criteres JSONB,
                concurrents_cibles JSONB,
                points_forts JSONB,
                points_faibles JSONB,
                plan_action JSONB,
                analyse TEXT
            )
        """)
        cur.execute("""
            ALTER TABLE historique_potentiel ADD COLUMN IF NOT EXISTS projection TEXT
        """)
        cur.execute("""
            ALTER TABLE historique_potentiel ADD COLUMN IF NOT EXISTS projection_min NUMERIC
        """)
        cur.execute("""
            ALTER TABLE historique_potentiel ADD COLUMN IF NOT EXISTS projection_max NUMERIC
        """)
        conn.commit()
        cur.close()
        return conn
    except Exception:
        return None


def sauvegarder_historique(url: str, estimation: dict) -> bool:
    """
    Enregistre un nouveau resultat d'estimation dans l'historique permanent.
    Ne bloque jamais l'affichage meme si la sauvegarde echoue.
    """
    conn = get_connexion_historique()
    if not conn:
        return False
    try:
        import json
        url_normalisee = url.strip().lower().replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO historique_potentiel
                (url, score, criteres, concurrents_cibles, points_forts, points_faibles, plan_action, projection, projection_min, projection_max, analyse)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            url_normalisee,
            estimation.get("score"),
            json.dumps(estimation.get("criteres") or {}),
            json.dumps(estimation.get("concurrents_cibles") or []),
            json.dumps(estimation.get("points_forts") or []),
            json.dumps(estimation.get("points_faibles") or []),
            json.dumps(estimation.get("plan_action") or []),
            estimation.get("projection_texte") or "",
            estimation.get("projection_min") or 0,
            estimation.get("projection_max") or 0,
            estimation.get("analyse") or "",
        ))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return False


def lire_historique(url: str, limite: int = 10) -> list:
    """
    Relit les N derniers resultats stockes pour un site donne, du plus
    recent au plus ancien.
    """
    conn = get_connexion_historique()
    if not conn:
        return []
    try:
        url_normalisee = url.strip().lower().replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
        cur = conn.cursor()
        cur.execute("""
            SELECT date_analyse, score, criteres, concurrents_cibles, points_forts, points_faibles, plan_action, projection, projection_min, projection_max, analyse
            FROM historique_potentiel
            WHERE url = %s
            ORDER BY date_analyse DESC
            LIMIT %s
        """, (url_normalisee, limite))
        lignes = cur.fetchall()
        cur.close()
        conn.close()

        historique = []
        for ligne in lignes:
            historique.append({
                "date": ligne[0],
                "score": ligne[1],
                "criteres": ligne[2],
                "concurrents_cibles": ligne[3],
                "points_forts": ligne[4],
                "points_faibles": ligne[5],
                "plan_action": ligne[6],
                "projection_texte": ligne[7],
                "projection_min": ligne[8],
                "projection_max": ligne[9],
                "analyse": ligne[10],
            })
        return historique
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return []

# ── ACCÈS PRO / PREMIUM ──────────────────────────────────────────────────────
EMAILS_FONDATEUR = ["yanisaidoune1@gmail.com"]  # <-- à remplacer par ta vraie adresse email


def get_forfait_actif(email: str) -> str:
    """Retourne 'premium', 'pro' ou 'gratuit' selon l'email fourni."""
    if not email:
        return "gratuit"
    email = email.strip().lower()
    if email in [e.strip().lower() for e in EMAILS_FONDATEUR]:
        return "premium"

    conn = get_connexion_historique()
    if not conn:
        return "gratuit"
    try:
        import datetime
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS acces_forfaits (
                email TEXT PRIMARY KEY,
                forfait TEXT NOT NULL,
                date_expiration DATE NOT NULL,
                date_creation TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.execute("SELECT forfait, date_expiration FROM acces_forfaits WHERE email = %s", (email,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return "gratuit"
        forfait, date_expiration = row
        if date_expiration < datetime.date.today():
            return "gratuit"
        return forfait
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return "gratuit"


def activer_forfait(email: str, forfait: str, jours: int = 30) -> bool:
    """Active ou prolonge un forfait Pro/Premium pour un email donné."""
    if not email or forfait not in ("pro", "premium"):
        return False
    conn = get_connexion_historique()
    if not conn:
        return False
    try:
        import datetime
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS acces_forfaits (
                email TEXT PRIMARY KEY,
                forfait TEXT NOT NULL,
                date_expiration DATE NOT NULL,
                date_creation TIMESTAMP DEFAULT NOW()
            )
        """)
        date_expiration = datetime.date.today() + datetime.timedelta(days=jours)
        cur.execute("""
            INSERT INTO acces_forfaits (email, forfait, date_expiration)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET forfait = EXCLUDED.forfait, date_expiration = EXCLUDED.date_expiration
        """, (email.strip().lower(), forfait, date_expiration))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return False
