import pandas as pd
import json
from bs4 import BeautifulSoup
import requests as r
import re
import random
from urllib.parse import unquote

STOPWORDS = {'of', 'the', 'a', 'i', 'and'}

def normalize(s):
    s = re.sub(r'\([^)]*\)', '', s)          # strip parenthetical native name
    s = unquote(s).replace('_', ' ').lower()  # <-- the fix: underscores -> spaces
    words = re.findall(r'[a-z]+', s)          # letters only, ignores years/numbers
    return [w for w in words if w not in STOPWORDS]

def words_in_url(sentence, url, threshold=0.5):
    url_words = set(normalize(url))
    sentence_words = normalize(sentence)
    if not sentence_words:
        return False
    matches = sum(1 for w in sentence_words
                  if any(w[:6] == uw[:6] for uw in url_words))  # prefix match for Albania/Albanian
    return matches / len(sentence_words) >= threshold

headers = {
    "User-Agent": "wikipedia-parlement-scraper/1.0 (contact: celian.chauveau@gmail.com)"
}

url = "https://en.wikipedia.org/wiki/List_of_legislatures_by_country"

response  = r.get(url, headers=headers, timeout=10)
all_urls = {}

if response.status_code == 200:
    soup = BeautifulSoup(response.content, "html.parser")  
    tooltips = soup.find("section", attrs={"aria-labelledby": "Legislatures_of_sovereign_states_(Member_and_observer_states_of_the_United_Nations)"})
    last_country = None
    for s in tooltips.select('table tbody tr'):
        if s.find('td'):
            hey = s.find_all('td')
            text0 = hey[0].get_text().strip()
            if last_country:
                all_urls[last_country]["chambers"].append(
                    {
                        "name" : hey[0].get_text().strip(),
                        "url" : hey[0].find('a').get('href')
                    }
                )
                last_country = None
            elif(hey[1].get('rowspan') == '2'):
                entry = {
                        "chambers": [{
                            "name" : hey[2].get_text().strip(),
                            "url" : hey[2].find('a').get('href')
                        }]
                    }
                last_country = text0
                all_urls[text0] = entry
            else :
                if(hey[0].get('colspan') == '2'):
                    previous_country = next(reversed(all_urls))

                    all_urls[previous_country]["chambers"].append({
                        "name" : hey[0].get_text().strip(),
                        "url" : hey[0].find('a').get('href')
                    })
                elif(hey[1].find('a')):
                    entry = {
                            "chambers": [{
                                "name" : hey[1].get_text().strip(),
                                "url" : hey[1].find('a').get('href')
                            }]
                        }
                    all_urls[text0] = entry
                    
with open("hey.json", "w", encoding="utf-8") as f:
    json.dump(all_urls, f, indent=4, ensure_ascii=False)

for country, data in list(all_urls.items()):
    print(country)
    for chamber in data["chambers"]:
        table = []
        chamber_response = r.get(chamber["url"], headers=headers, timeout=10)
        chamber["composition_svg"] = None
        chamber["infobox_groups"] = []
        

        if chamber_response.status_code == 200:
            chamber_soup = BeautifulSoup(chamber_response.content, "html.parser")
            chamber_tooltips = chamber_soup.find_all("section", attrs={"aria-labelledby": lambda x: x and "composition" in x.lower()})


            for section in chamber_tooltips: 
                if(section.find("table")):
                    table.append(section)

            election_tooltips = chamber_soup.find_all("section", attrs={"aria-labelledby": lambda x: x and "election" in x.lower()})
            for section in election_tooltips: 
                if(section.find("table")):
                    table.append(section)

            infobox = chamber_soup.find("table", class_="infobox")
            svg_links = infobox.find_all('a', href=lambda h: h and h.lower().endswith('.svg'))

            for img in svg_links:
                src = img['href']
                if(words_in_url(chamber["name"], src)):
                    chamber["composition_svg"] = src
                else:
                    chamber["composition_svg"] = None

            labels = chamber_soup.select("table.infobox tbody tr th.infobox-label")
            
            for label in labels:
                if "groups" in label.get_text(strip=True).lower():
                    row = label.find_parent("tr")
                    value = row.find("td")
                    for li in value.select(" li"):
                        if(li.find("a")):
                            party = li.find("a").get_text(strip=True)
                            full_name = li.find("a")["title"]
                        else:
                            party = li.get_text(strip=True)
                            full_name = party

                        if(li.find("span")):
                            test = li.find("span").get('style')
                            bg = re.search(r"background-color\s*:\s*([^;]+)", test)
                            color = bg.group(1) if bg else None
                        else:
                            color = "#000000"

                        numbers = re.findall(r"\d+", li.get_text(" ", strip=True))

                        seats = int(numbers[0]) if numbers else None

                        entry = {
                            "party": party,
                            "full_name": full_name,
                            "seats": seats,
                            "color": color
                        }

                        chamber["infobox_groups"].append(entry)

            chamber["composition"] = table

with open("hey.json", "w", encoding="utf-8") as f:
    json.dump(all_urls, f, indent=4, ensure_ascii=False)


print('JSON is updated')