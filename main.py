import pandas as pd
import json
from bs4 import BeautifulSoup
import requests as r
import re
import random
from urllib.parse import unquote

STOPWORDS = {'of', 'the', 'a', 'i', 'and'}

def normalize(s):
    s = re.sub(r'\([^)]*\)', '', s)           # strip parenthetical native name
    s = unquote(s).replace('_', ' ').lower()
    words = re.findall(r'[a-z]+', s)
    return [w for w in words if w not in STOPWORDS]

def words_in_url(sentence, url, threshold=0.5):
    url_words = set(normalize(url))
    sentence_words = normalize(sentence)
    if not sentence_words:
        return False
    matches = sum(1 for w in sentence_words
                  if any(w[:6] == uw[:6] for uw in url_words))
    return matches / len(sentence_words) >= threshold

def safe_get(session_headers, url, retries=1):
    """GET with basic error handling. Returns response or None."""
    if not url:
        return None
    try:
        resp = r.get(url, headers=session_headers, timeout=10)
        if resp.status_code == 200:
            return resp
        print(f"    [warn] status {resp.status_code} for {url}")
        return None
    except r.RequestException as e:
        print(f"    [error] request failed for {url}: {e}")
        return None

def get_href(td):
    """Safely pull an <a href> from a <td>, or None."""
    if td is None:
        return None
    a = td.find('a')
    if a is None:
        return None
    return a.get('href')

headers = {
    "User-Agent": "wikipedia-parlement-scraper/1.0 (contact: celian.chauveau@gmail.com)"
}

BASE = "https://en.wikipedia.org"

def absolutize(href):
    if not href:
        return None
    if href.startswith('http'):
        return href
    if href.startswith('//'):
        return 'https:' + href
    if href.startswith('/'):
        return BASE + href
    return href

url = "https://en.wikipedia.org/wiki/List_of_legislatures_by_country"
all_urls = {}

response = safe_get(headers, url)

if response is not None:
    soup = BeautifulSoup(response.content, "html.parser")
    tooltips = soup.find(
        "section",
        attrs={"aria-labelledby": "Legislatures_of_sovereign_states_(Member_and_observer_states_of_the_United_Nations)"}
    )

    if tooltips is None:
        print("[fatal] could not find legislatures section, aborting")
    else:
        last_country = None
        for s in tooltips.select('table tbody tr'):
            cells = s.find_all('td')
            if not cells:
                continue

            text0 = cells[0].get_text().strip()

            try:
                if last_country:
                    href = absolutize(get_href(cells[0]))
                    all_urls[last_country]["chambers"].append({
                        "name": text0,
                        "url": href
                    })
                    last_country = None

                elif len(cells) > 1 and cells[1].get('rowspan') == '2':
                    if len(cells) > 2:
                        href = absolutize(get_href(cells[2]))
                        entry = {"chambers": [{
                            "name": cells[2].get_text().strip(),
                            "url": href
                        }]}
                        last_country = text0
                        all_urls[text0] = entry

                elif cells[0].get('colspan') == '2':
                    if all_urls:
                        previous_country = next(reversed(all_urls))
                        href = absolutize(get_href(cells[0]))
                        all_urls[previous_country]["chambers"].append({
                            "name": text0,
                            "url": href
                        })

                elif len(cells) > 1 and cells[1].find('a'):
                    href = absolutize(get_href(cells[1]))
                    entry = {"chambers": [{
                        "name": cells[1].get_text().strip(),
                        "url": href
                    }]}
                    all_urls[text0] = entry

            except (IndexError, KeyError, AttributeError) as e:
                print(f"  [warn] skipping malformed row for '{text0}': {e}")
                continue

with open("hey.json", "w", encoding="utf-8") as f:
    json.dump(all_urls, f, indent=4, ensure_ascii=False)

print(f"Found {len(all_urls)} countries. Starting chamber scrape...")

# ---------------------------------------------------------------
# Chamber-level scrape
# ---------------------------------------------------------------

for country, data in list(all_urls.items()):
    print(country)
    for chamber in data["chambers"]:
        table = []
        chamber["composition_svg"] = None
        chamber["infobox_groups"] = []
        chamber["composition"] = []

        if not chamber.get("url"):
            print(f"  [skip] no url for chamber: {chamber.get('name')}")
            continue

        chamber_response = safe_get(headers, chamber["url"])
        if chamber_response is None:
            continue

        chamber_soup = BeautifulSoup(chamber_response.content, "html.parser")

        # --- composition / election tables ---
        chamber_tooltips = chamber_soup.find_all(
            "section", attrs={"aria-labelledby": lambda x: x and "composition" in x.lower()}
        )
        for section in chamber_tooltips:
            if section.find("table"):
                table.append(section)

        election_tooltips = chamber_soup.find_all(
            "section", attrs={"aria-labelledby": lambda x: x and "election" in x.lower()}
        )
        for section in election_tooltips:
            if section.find("table"):
                table.append(section)

        # --- infobox ---
        infobox = chamber_soup.find("table", class_="infobox")

        if infobox is None:
            print(f"  [warn] no infobox for {chamber.get('name')} ({chamber['url']})")
            chamber["composition"] = table
            continue

        # --- SVG matching ---
        try:
            svg_links = infobox.find_all('a', href=lambda h: h and h.lower().endswith('.svg'))
        except Exception as e:
            print(f"  [warn] svg search failed for {chamber.get('name')}: {e}")
            svg_links = []

        for a_tag in svg_links:
            src = a_tag.get('href')
            if src and words_in_url(chamber.get("name", ""), src):
                chamber["composition_svg"] = src
                break

        # --- groups list ---
        labels = infobox.select("tbody tr th.infobox-label")

        for label in labels:
            if "groups" not in label.get_text(strip=True).lower():
                continue

            row = label.find_parent("tr")
            if row is None:
                continue

            value = row.find("td")
            if value is None:
                continue

            for li in value.select("li"):
                try:
                    a_tag = li.find("a")
                    if a_tag:
                        party = a_tag.get_text(strip=True)
                        full_name = a_tag.get("title") or party
                    else:
                        party = li.get_text(strip=True)
                        full_name = party

                    legend = li.find("span", class_="legend-color")
                    color = "#000000"
                    if legend and legend.get('style'):
                        bg = re.search(r"background-color\s*:\s*([^;]+)", legend['style'])
                        if bg:
                            color = bg.group(1)

                    numbers = re.findall(r"\d+", li.get_text(" ", strip=True))
                    seats = int(numbers[0]) if numbers else None

                    chamber["infobox_groups"].append({
                        "party": party,
                        "full_name": full_name,
                        "seats": seats,
                        "color": color
                    })
                except Exception as e:
                    print(f"  [warn] skipping malformed group row: {e}")
                    continue

        chamber["composition"] = table

with open("hey.json", "w", encoding="utf-8") as f:
    json.dump(all_urls, f, indent=4, ensure_ascii=False)

print('JSON is updated')