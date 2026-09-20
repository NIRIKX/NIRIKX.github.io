"""
Visite NIRIKX avec un vrai navigateur (via Playwright) et, si l'appli
s'est endormie (Streamlit Cloud gratuit la met en veille apres un moment
sans visite), clique sur le bouton de reveil et attend qu'elle redemarre.

Un simple curl/wget ne suffit pas : quand l'appli dort, l'URL renvoie
une page statique "Zzzz..." avec un bouton a cliquer pour la relancer -
sans clic reel (donc sans navigateur), l'appli ne se reveille jamais,
meme si la requete elle-meme "reussit".
"""

from playwright.sync_api import sync_playwright

URL = "https://mon-audit-seo-fehcwhwv93dpppsti9f5gi.streamlit.app"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        contenu = page.content()
        if "gone to sleep" in contenu or "Zzzz" in contenu:
            print("L'appli dort, tentative de reveil...")
            try:
                page.get_by_role("button", name="Yes, get this app back up!").click(timeout=10000)
                # Le redemarrage peut prendre du temps, on attend que la
                # page de veille disparaisse (jusqu'a 90s).
                page.wait_for_selector("text=Zzzz", state="detached", timeout=90000)
                print("Appli reveillee.")
            except Exception as e:
                print(f"Impossible de confirmer le reveil (peut-etre deja reveillee) : {e}")
        else:
            print("Appli deja eveillee, rien a faire.")

        browser.close()


if __name__ == "__main__":
    main()
