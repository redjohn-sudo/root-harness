#!/usr/bin/env python3
"""
Three official root-harness accounts that follow tech news: France (in French),
Europe and the world (in English).

  - Each one reads the RSS feeds of known newsrooms, picks what is new, and posts
    a rewritten headline and a two-sentence summary in its own words, with the
    source and the link. Never the article itself.
  - The summaries are written by DeepSeek from the headline and the feed's intro
    only; the prompt forbids adding facts that are not there.
  - The accounts say they are automated (NIP-24) and carry the official check
    (rootharness/verified.json).

Keys and state live in ~/.root-harness-bots/<id>/ (never in this repository).

  python bots/actualite.py setup        # make the accounts: profile, pictures, @
  python bots/actualite.py run [n]      # post up to n new stories per account (default 1)
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
BOTS = Path(os.environ.get("RH_BOTS_HOME") or Path.home() / ".root-harness-bots")
UA = "Mozilla/5.0 (root-harness news bot; +https://github.com/redjohn-sudo)"

# feeds marked True are about AI already; the others are filtered on AI words
COMPTES = {
    "veilletech": {
        "pseudo": "veilletech", "at": "veilletech", "name": "Veille Tech France", "lang": "French", "community": "actu-tech",
        "about": "L'actualité de l'IA en France, résumée en deux phrases, toujours avec la source. Compte automatique officiel de root-harness.",
        "lien": "Lire sur {source}",
        "feeds": {"ActuIA": ("https://www.actuia.com/feed/", True), "Numerama": ("https://www.numerama.com/feed/", False),
                  "Next": ("https://next.ink/feed/", False), "Siècle Digital": ("https://siecledigital.fr/feed/", False),
                  "Frandroid": ("https://www.frandroid.com/feed", False), "Blog du Modérateur": ("https://www.blogdumoderateur.com/feed/", False),
                  "01net": ("https://www.01net.com/actualites/feed/", False)},
    },
    "eutechbrief": {
        "pseudo": "eutechbrief", "at": "eutechbrief", "name": "Europe Tech Brief", "lang": "English", "community": "tech-news",
        "about": "AI news from Europe in two sentences, always with the source. An official automated root-harness account.",
        "lien": "Read on {source}",
        "feeds": {"The Decoder": ("https://the-decoder.com/feed/", True), "Sifted": ("https://sifted.eu/sector/artificial-intelligence/feed", True),
                  "Tech.eu": ("https://tech.eu/feed/", False), "EU-Startups": ("https://www.eu-startups.com/feed/", False),
                  "The Next Web": ("https://thenextweb.com/feed", False)},
    },
    "globaltechbrief": {
        "pseudo": "globaltechbrief", "at": "globaltechbrief", "name": "Global Tech Brief", "lang": "English", "community": "tech-news",
        "about": "The world's AI news in two sentences, always with the source. An official automated root-harness account.",
        "lien": "Read on {source}",
        "feeds": {"The Verge": ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", True),
                  "TechCrunch": ("https://techcrunch.com/category/artificial-intelligence/feed/", True),
                  "Ars Technica": ("https://arstechnica.com/ai/feed/", True),
                  "MIT Technology Review": ("https://www.technologyreview.com/topic/artificial-intelligence/feed", True),
                  "OpenAI": ("https://openai.com/news/rss.xml", True), "Google DeepMind": ("https://deepmind.google/blog/rss.xml", True),
                  "Hugging Face": ("https://huggingface.co/blog/feed.xml", True)},
    },
}
# what makes a story about AI, in French and in English
IA = re.compile(r"\b(IA|AI|A\.I\.|intelligences? artificielles?|artificial intelligence|LLMs?|GPT[-\w.]*|ChatGPT|OpenAI|Anthropic|Claude|Gemini|"
                r"Mistral|DeepMind|DeepSeek|Copilot|Llama|Grok|Hugging ?Face|agents? (?:IA|d'IA|AI)|AI agents?|machine learning|apprentissage automatique|"
                r"neural|neuronal|chatbots?|modèles? de langage|language models?|Nvidia|GPU|data ?cent(?:er|re)s?|génératives?|generative)\b", re.I)

CONSIGNE = """You write posts for {name}, a professional tech news account. Write in {lang}.
From the headline and the short intro below (and nothing else), write:
- "title": a clear rewritten headline, at most 90 characters, no clickbait;
- "summary": two short sentences in your own words, at most 300 characters, saying what happened and why it matters.
Facts only, neutral tone. Never add a fact, a number or a name that is not in the text. No emoji, no hashtags,
never a dash used as punctuation. Do not copy sentences from the intro. Answer with JSON only.

Source: {source}
Headline: {headline}
Intro: {intro}"""


def dossier(ident: str) -> Path:
    d = BOTS / ident
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(BOTS, 0o700)
    return d


def cle(ident: str):
    import nostr_sdk as n
    f = dossier(ident) / "key.nsec"
    if f.exists():
        return n.Keys.parse(f.read_text().strip())
    k = n.Keys.generate()
    f.write_text(k.secret_key().to_bech32())
    f.chmod(0o600)
    return k


# -- the feeds -------------------------------------------------------------------------------

def propre(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return " ".join(t.split())


MRSS = "{http://search.yahoo.com/mrss/}"


def image_du_flux(it) -> str:
    """The picture the newsroom gives with the story in its feed (media:content, media:thumbnail, enclosure)."""
    for tag in (MRSS + "content", MRSS + "thumbnail"):
        for m in it.iter(tag):
            u, typ = m.get("url", ""), m.get("type", "") or m.get("medium", "")
            if u.startswith("https://") and ("image" in typ or not typ or re.search(r"\.(jpe?g|png|webp)", u, re.I)):
                return u
    e = it.find("enclosure")
    if e is not None and e.get("url", "").startswith("https://") and "image" in e.get("type", ""):
        return e.get("url")
    return ""


def image_de_la_page(lien: str) -> str:
    """Otherwise the preview picture the article declares itself (og:image), shown as it is, from its site."""
    try:
        req = urllib.request.Request(lien, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            tete = r.read(200_000).decode("utf-8", "replace")
    except Exception:
        return ""
    m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', tete, re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)', tete, re.I)
    u = html.unescape(m.group(1)) if m else ""
    return u if u.startswith("https://") else ""


def lire_flux(source: str, url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        racine = ET.fromstring(r.read())
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for it in racine.iter("item"):
        lien = (it.findtext("link") or "").strip()
        image = image_du_flux(it)
        date = it.findtext("pubDate") or ""
        try:
            quand = parsedate_to_datetime(date).timestamp()
        except Exception:
            quand = 0
        out.append({"source": source, "titre": propre(it.findtext("title")), "lien": lien, "intro": propre(it.findtext("description"))[:700], "quand": quand, "image": image})
    for it in racine.findall("a:entry", ns):
        l = it.find("a:link[@rel='alternate']", ns) or it.find("a:link", ns)
        lien = l.get("href", "") if l is not None else ""
        date = it.findtext("a:published", default="", namespaces=ns) or it.findtext("a:updated", default="", namespaces=ns)
        try:
            quand = time.mktime(time.strptime(date[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            quand = 0
        intro = it.findtext("a:summary", default="", namespaces=ns) or it.findtext("a:content", default="", namespaces=ns)
        out.append({"source": source, "titre": propre(it.findtext("a:title", default="", namespaces=ns)), "lien": lien, "intro": propre(intro)[:700], "quand": quand, "image": ""})
    return [x for x in out if x["titre"] and x["lien"].startswith("https://")]


# -- the summary -------------------------------------------------------------------------------

def resumer(compte: dict, art: dict) -> dict | None:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is missing")
    corps = {"model": "deepseek-chat", "temperature": 0.3, "max_tokens": 300, "response_format": {"type": "json_object"},
             "messages": [{"role": "user", "content": CONSIGNE.format(name=compte["name"], lang=compte["lang"], source=art["source"],
                                                                      headline=art["titre"], intro=art["intro"] or "(none)")}]}
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=json.dumps(corps).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=90) as r:
        texte = json.load(r)["choices"][0]["message"]["content"]
    try:
        d = json.loads(texte)
    except ValueError:
        return None
    titre, resume = " ".join(str(d.get("title", "")).split())[:110], " ".join(str(d.get("summary", "")).split())[:380]
    if not titre or not resume:
        return None
    return {"titre": titre.replace(" — ", ", ").replace("—", ","), "resume": resume.replace(" — ", ", ").replace("—", ",")}


# -- one account at a time, in its own home (its own profile and keys) -------------------------

def un(ident: str, quoi: str, n_max: int = 1) -> None:
    sys.path.insert(0, str(RACINE))
    from rootharness import network
    compte = COMPTES[ident]
    keys = cle(ident)
    net = network.Network(keys, compte["pseudo"])
    if not net.ready():
        raise SystemExit("relays unreachable")
    try:
        if quoi == "setup":
            images = {}
            for nom in ("avatar", "banner"):
                f = BOTS / f"{ident}-{nom}.png"
                if f.exists():
                    u = net.upload(str(f))
                    if u.get("url"):
                        images["picture" if nom == "avatar" else "banner"] = u["url"]
            network.profile_set({"name": compte["name"], "show": "name", "about": compte["about"], "state": "travaille",
                                 "role": "tech news", "bot": True, "communities": [compte["community"]], **images})
            net.publish_profile()
            print(ident, "@", net.claim_at(compte["at"]))
            print(ident, "hex", keys.public_key().to_hex())
            return
        etat_f = dossier(ident) / "vus.json"
        vus = set(json.loads(etat_f.read_text()) if etat_f.exists() else [])
        arts = []
        for source, (url, deja_ia) in compte["feeds"].items():
            try:
                L = lire_flux(source, url)
                arts += L if deja_ia else [a for a in L if IA.search(a["titre"] + " " + a["intro"])]
            except Exception as e:
                print(ident, "feed failed:", source, type(e).__name__)
        nouveaux = sorted((a for a in arts if a["lien"] not in vus and time.time() - a["quand"] < 2 * 86400), key=lambda a: -a["quand"])
        if not vus:                                      # first run: do not post a backlog, remember everything but the newest
            vus |= {a["lien"] for a in nouveaux[n_max:]}
        postes, sources_du_jour = 0, set()
        for a in nouveaux:
            if postes >= n_max:
                break
            if a["source"] in sources_du_jour:          # vary the newsrooms within one run
                continue
            r = resumer(compte, a)
            vus.add(a["lien"])
            if not r:
                continue
            texte = f"**{r['titre']}**\n\n{r['resume']}\n\n[{compte['lien'].format(source=a['source'])}]({a['lien']})"
            image = a.get("image") or image_de_la_page(a["lien"])
            ext = (re.search(r"\.(png|webp|gif)(?:\?|$)", image, re.I) or [None, "jpeg"])[1].lower()
            media = [{"url": image, "mime": "image/" + ("jpeg" if ext == "jpg" else ext)}] if image else []
            sent = net.post(texte, media=media, community=compte["community"])
            print(ident, "posted", sent.get("id", "")[:10], "| image" if media else "| no image", "|", r["titre"])
            postes += 1
            sources_du_jour.add(a["source"])
        etat_f.write_text(json.dumps(sorted(vus)[-3000:]))
    finally:
        net.close()


def principal() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "_un":           # the child process, for one account
        un(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 1)
        return
    quoi = sys.argv[1] if len(sys.argv) > 1 else "run"
    n_max = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    env = dict(os.environ)
    if "DEEPSEEK_API_KEY" not in env:
        sys.path.insert(0, str(RACINE))
        from rootharness import brains
        env["DEEPSEEK_API_KEY"] = brains.key("DEEPSEEK_API_KEY") or ""
    for ident in COMPTES:
        env["ROOT_HARNESS_HOME"] = str(dossier(ident))
        subprocess.run([sys.executable, __file__, "_un", ident, quoi, str(n_max)], env=env, check=False)


if __name__ == "__main__":
    principal()
