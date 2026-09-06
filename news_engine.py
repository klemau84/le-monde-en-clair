from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import requests


TRUSTED = {
    "Reuters": 12, "AFP": 12, "Associated Press": 11, "France 24": 9,
    "BBC": 9, "Le Monde": 8, "Les Echos": 8, "RFI": 8,
    "Courrier international": 8, "Euronews": 7, "Franceinfo": 7,
    "La Croix": 7, "Le Figaro": 7, "Libération": 7, "L'Express": 6,
}

IMPACT = {
    "guerre": 22, "attaque": 18, "cessez-le-feu": 20, "invasion": 22,
    "élection": 18, "président": 12, "gouvernement": 13, "démission": 15,
    "coup d'état": 22, "parlement": 8, "loi": 8, "réforme": 10,
    "sanction": 13, "accord": 10, "sommet": 7, "diplomatie": 8,
    "catastrophe": 20, "séisme": 20, "inondation": 17, "incendie": 14,
    "ouragan": 18, "victime": 11, "évacuation": 12,
    "inflation": 10, "récession": 16, "croissance": 8, "tarif": 8,
    "banque centrale": 13, "chômage": 9, "grève": 10, "manifestation": 10,
    "nucléaire": 16, "climat": 8, "énergie": 8, "intelligence artificielle": 8,
}

CATEGORIES = {
    "Conflits et diplomatie": ["guerre", "attaque", "armée", "cessez-le-feu", "sanction", "diplomatie", "sommet", "missile"],
    "Politique": ["élection", "président", "gouvernement", "ministre", "parlement", "loi", "réforme", "démission"],
    "Économie": ["économie", "inflation", "croissance", "récession", "banque", "chômage", "tarif", "commerce"],
    "Climat et catastrophes": ["climat", "séisme", "inondation", "incendie", "ouragan", "tempête", "canicule"],
    "Société": ["manifestation", "grève", "justice", "santé", "éducation", "immigration"],
    "Sciences et technologie": ["science", "technologie", "espace", "intelligence artificielle", "nucléaire", "recherche"],
}


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    stop = {"avec", "dans", "pour", "une", "des", "les", "sur", "que", "qui", "est", "son", "aux", "par", "plus", "après", "face"}
    return {w for w in re.findall(r"[a-zà-ÿ0-9]+", text.lower()) if len(w) > 3 and w not in stop}


def _published(entry) -> datetime:
    raw = entry.get("published") or entry.get("updated") or ""
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _source(entry, title: str) -> str:
    if entry.get("source", {}).get("title"):
        return entry.source.title.strip()
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return "Source non précisée"


def _bare_title(title: str, source: str) -> str:
    suffix = f" - {source}"
    return title[:-len(suffix)].strip() if title.endswith(suffix) else title.strip()


def _category(text: str) -> str:
    low = text.lower()
    scores = {cat: sum(1 for word in words if word in low) for cat, words in CATEGORIES.items()}
    winner = max(scores, key=scores.get)
    return winner if scores[winner] else "Autres sujets"


def _score(title: str, source: str, published: datetime) -> int:
    low = title.lower()
    base = 32 + min(sum(value for word, value in IMPACT.items() if word in low), 38)
    base += next((value for name, value in TRUSTED.items() if name.lower() in source.lower()), 2)
    hours = max(0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
    base += max(0, int(14 - hours / 12))
    if any(x in low for x in ["voici", "ces", "pourquoi", "incroyable", "astuce", "classement"]):
        base -= 8
    if any(x in low for x in ["football", "match", "ligue", "cinéma", "série", "people", "recette", "tv :"]):
        base -= 18
    return max(1, min(100, base))


def _level(score: int) -> str:
    return "Majeur" if score >= 72 else "Important" if score >= 55 else "À suivre"


def _why(category: str, country: str, level: str) -> str:
    reasons = {
        "Conflits et diplomatie": "Peut modifier les équilibres régionaux, la sécurité ou les relations internationales.",
        "Politique": f"Peut influer sur les décisions publiques et l'orientation politique de {country}.",
        "Économie": "Peut avoir des effets sur l'activité, les prix, l'emploi ou les échanges internationaux.",
        "Climat et catastrophes": "Peut affecter directement les populations, les infrastructures et l'activité économique.",
        "Société": "Traduit une évolution sociale ou une tension susceptible d'avoir des conséquences durables.",
        "Sciences et technologie": "Peut transformer un secteur stratégique ou accélérer une évolution technologique.",
        "Autres sujets": "Sujet retenu pour sa diffusion et son impact potentiel ; ses conséquences restent à préciser.",
    }
    return reasons[category] + (" Sujet classé majeur." if level == "Majeur" else "")


def fetch_country(country: str, query: str, days: int = 7, limit: int = 18) -> list[dict]:
    focus = "gouvernement OR économie OR élection OR conflit OR crise OR diplomatie OR réforme OR climat OR catastrophe OR société OR manifestation"
    search = quote_plus(f'"{query}" ({focus}) when:{days}d')
    url = f"https://news.google.com/rss/search?q={search}&hl=fr&gl=FR&ceid=FR:fr"
    response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 LeMondeEnClair/1.0"})
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    rows = []
    seen = set()
    seen_tokens: list[set[str]] = []
    for entry in feed.entries:
        raw_title = _clean(entry.get("title", ""))
        source = _source(entry, raw_title)
        title = _bare_title(raw_title, source)
        key = re.sub(r"[^a-z0-9]+", " ", title.lower())[:85]
        if not title or key in seen:
            continue
        tokens = _tokens(title)
        if tokens and any(len(tokens & old) / max(1, len(tokens | old)) >= 0.48 for old in seen_tokens):
            continue
        seen.add(key)
        seen_tokens.append(tokens)
        published = _published(entry)
        category = _category(title + " " + _clean(entry.get("summary", "")))
        score = _score(title, source, published)
        if query.lower() in title.lower():
            score = min(100, score + 10)
        level = _level(score)
        rows.append({
            "pays": country, "titre": title, "source": source,
            "lien": entry.get("link", ""), "date": published,
            "categorie": category, "score": score, "niveau": level,
            "pourquoi": _why(category, country, level),
        })
    return sorted(rows, key=lambda x: (x["score"], x["date"]), reverse=True)[:limit]


def fetch_many(countries: pd.DataFrame, days: int = 7, per_country: int = 8) -> pd.DataFrame:
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = {
            executor.submit(fetch_country, row.pays, row.requete, days, per_country): row.pays
            for row in countries.itertuples(index=False)
        }
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception:
                continue
    return pd.DataFrame(rows)
