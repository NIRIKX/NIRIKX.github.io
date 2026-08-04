"""
Sitra - Module de capture precise via Playwright
Bloque les widgets tiers, scrolle jusqu'a l'element,
et dessine un cadre rouge autour pour montrer exactement ou est l'erreur.
"""

import io
import base64
import streamlit as st

@st.cache_resource(show_spinner=False)
def _ensure_playwright_browser():
    """Télécharge le navigateur Chromium de Playwright s'il n'est pas déjà présent.
    Streamlit Cloud installe bien le paquet Python 'playwright' (via requirements.txt)
    mais ne lance jamais 'playwright install' — sans ça, le navigateur lui-même
    n'existe pas et chaque appel échoue silencieusement. Grâce à @st.cache_resource,
    ce téléchargement ne se fait qu'une seule fois par session de l'app, pas à
    chaque analyse."""
    import subprocess
    import sys
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            timeout=180,
        )
        return True
    except Exception:
        return False

@st.cache_data(ttl=3600, show_spinner=False)
def get_screenshot_with_highlight(url: str, selector: str = None):
    try:
        _ensure_playwright_browser()
        from playwright.sync_api import sync_playwright
        import PIL.Image
        import PIL.ImageDraw

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            # Bloque les domaines de widgets tiers qui affichent des popups
            blocked_domains = [
                "zenchef.com", "thefork.com", "lafourchette.com",
                "widget.zenchef.com", "booking.zenchef.com",
                "cookiebot.com", "onetrust.com", "cookiepro.com",
                "intercom.io", "zendesk.com", "crisp.chat",
                "tawk.to", "livechat.com", "drift.com",
                "hotjar.com", "clarity.ms"
            ]

            def block_route(route):
                url_r = route.request.url
                if any(d in url_r for d in blocked_domains):
                    route.abort()
                else:
                    route.continue_()

            page = context.new_page()
            page.route("**/*", block_route)

            try:
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
            except Exception:
                browser.close()
                return None, False

            # Masque aussi via CSS les elements qui restent
            try:
                page.add_style_tag(content="""
                    [class*="zenchef"], [id*="zenchef"],
                    [class*="widget"], [class*="popup"],
                    [class*="modal"]:not(nav), [class*="overlay"],
                    [class*="cookie"], [id*="cookie"],
                    [class*="chat"], [id*="chat"],
                    [class*="intercom"], [id*="intercom"],
                    iframe[src*="zenchef"], iframe[src*="booking"],
                    iframe[src*="widget"] {
                        display: none !important;
                        visibility: hidden !important;
                    }
                """)
                page.wait_for_timeout(300)
            except Exception:
                pass

            bbox = None
            was_targeted = False

            if selector:
                # Cas special images : cherche la plus grande image sans alt
                if "img" in selector.lower():
                    try:
                        images = page.query_selector_all("img")
                        best = None
                        best_area = 0
                        # D'abord cherche une grande image sans attribut alt
                        for img_el in images:
                            try:
                                if not img_el.is_visible():
                                    continue
                                box = img_el.bounding_box()
                                if box and box["width"] > 150 and box["height"] > 100:
                                    area = box["width"] * box["height"]
                                    alt = img_el.get_attribute("alt") or ""
                                    if not alt.strip() and area > best_area:
                                        best_area = area
                                        best = (img_el, box)
                            except Exception:
                                continue
                        # Si aucune sans alt, prend la plus grande visible
                        if not best:
                            best_area = 0
                            for img_el in images:
                                try:
                                    if not img_el.is_visible():
                                        continue
                                    box = img_el.bounding_box()
                                    if box and box["width"] > 150 and box["height"] > 100:
                                        area = box["width"] * box["height"]
                                        if area > best_area:
                                            best_area = area
                                            best = (img_el, box)
                                except Exception:
                                    continue
                        if best:
                            best[0].scroll_into_view_if_needed()
                            page.wait_for_timeout(400)
                            bbox = best[0].bounding_box()
                            was_targeted = True
                        else:
                            # Aucune vraie balise <img> trouvee : beaucoup de sites
                            # utilisent une image de fond CSS (background-image) pour
                            # les grandes bannieres/photos d'illustration
                            try:
                                zone = page.evaluate("""
                                    () => {
                                        let best = null, bestArea = 0;
                                        document.querySelectorAll('*').forEach(el => {
                                            const style = getComputedStyle(el);
                                            if (style.backgroundImage && style.backgroundImage !== 'none') {
                                                const r = el.getBoundingClientRect();
                                                if (r.width > 150 && r.height > 100) {
                                                    const area = r.width * r.height;
                                                    if (area > bestArea) {
                                                        bestArea = area;
                                                        best = {x: r.x, y: r.y, width: r.width, height: r.height};
                                                    }
                                                }
                                            }
                                        });
                                        return best;
                                    }
                                """)
                                if zone:
                                    page.evaluate(f"window.scrollTo(0, Math.max(0, {zone['y']} - 100))")
                                    page.wait_for_timeout(300)
                                    bbox = zone
                                    was_targeted = True
                            except Exception:
                                pass
                    except Exception:
                        pass
                else:
                    # Autres elements
                    selectors = [s.strip() for s in selector.split(",")]
                    for sel in selectors:
                        try:
                            element = page.query_selector(sel)
                            if element and element.is_visible():
                                element.scroll_into_view_if_needed()
                                page.wait_for_timeout(400)
                                box = element.bounding_box()
                                if box and box["width"] > 0 and box["height"] > 0:
                                    bbox = box
                                    was_targeted = True
                                    break
                        except Exception:
                            continue

            screenshot_bytes = page.screenshot(full_page=False)
            browser.close()

        img = PIL.Image.open(io.BytesIO(screenshot_bytes))
        img_w, img_h = img.width, img.height

        if bbox:
            draw = PIL.ImageDraw.Draw(img)
            pad = 10
            x1 = max(0, int(bbox["x"]) - pad)
            y1 = max(0, int(bbox["y"]) - pad)
            x2 = min(img_w - 1, int(bbox["x"] + bbox["width"]) + pad)
            y2 = min(img_h - 1, int(bbox["y"] + bbox["height"]) + pad)
            if x2 <= x1: x2 = min(img_w - 1, x1 + 50)
            if y2 <= y1: y2 = min(img_h - 1, y1 + 50)

            for i in range(4):
                rx1, ry1 = max(0, x1-i), max(0, y1-i)
                rx2, ry2 = min(img_w-1, x2+i), min(img_h-1, y2+i)
                if rx2 > rx1 and ry2 > ry1:
                    draw.rectangle([rx1, ry1, rx2, ry2], outline=(220, 53, 69), width=2)

            tri = 22
            tx2, ty2 = min(img_w-1, x1+tri), min(img_h-1, y1+tri)
            if tx2 > x1 and ty2 > y1:
                draw.polygon([(x1, y1), (tx2, y1), (x1, ty2)], fill=(220, 53, 69)) 

            # Recadre autour de la zone ciblee — sinon la vignette (90px de haut,
            # cote SITRA) ne montre que le tout haut de la capture entiere,
            # et le cadre rouge peut se retrouver hors champ
            marge = 120
            crop_x1 = max(0, x1 - marge)
            crop_y1 = max(0, y1 - marge)
            crop_x2 = min(img_w, x2 + marge)
            crop_y2 = min(img_h, y2 + marge)
            if crop_x2 > crop_x1 and crop_y2 > crop_y1:
                img = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        return data_uri, was_targeted

    except Exception:
        return None, False
