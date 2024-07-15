import urllib.request, urllib.error
import requests
import time
import sys
from datetime import datetime
import json
from bs4 import BeautifulSoup
import re

from typing import List

from zipcodes import get_neighborhoods_for_zipcode


# gets a values from a nested object
def get_value_from_config(path, props:list):

    with open(path) as file:
        config_json = json.load(file)

    data = config_json

    for prop in props:
        if len(prop) == 0:
            continue
        #if prop.isdigit(): #why? doesnt work..
        #    prop = int(prop)
        data = data[prop]

    return data


def get_links_to_offers() -> dict:
    html = get_html_from_saga()
    if html == "":
        print("COULD NOT READ HTML FROM SAGA")
        return []

    all_links = []

    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all('a'):
        # print(link.get('href'))
        if "/immobiliensuche/immo-detail/" in link.get("href", ""):
            all_links.append("https://saga.hamburg" + link.get("href", ""))

    # remove duplicates
    all_links = list(set(all_links))

    return {
        "apartments": [link for link in all_links if any(x in link.lower() for x in ["wohnung", "apartment", "zimmer"])],
        "offices":  [link for link in all_links if any(x in link.lower() for x in ["buro", "büro", "gewerbe"])],
        "parking":  [link for link in all_links if any(x in link.lower() for x in ["stellplatz", ""])]
    }


def get_post_address():
    post_address = "https://www.saga.hamburg/immobiliensuche?Kategorie=APARTMENT"
    return post_address


def get_html_from_saga():
    post_address = get_post_address()

    try:
        req = urllib.request.Request(post_address)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:106.0) Gecko/20100101 Firefox/106.0')
        req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8')
        req.add_header('Accept-Language', 'en-US,en;q=0.5')

        r = urllib.request.urlopen(req)

        if not r.code == 200:
            print("could not post to saga")
            print("Error code", r.code)
            print("Error", r.reason)
            return ""
        else:
            return r.read().decode('utf-8')

    except urllib.error.HTTPError as e:
        print("error while posting to saga " + str(e))
        return ""


# posts all information about an offer to telegram
def post_offer_to_telegram(offer_details, chat_id, token):

    def shorten_string(input_string, max_length=28):
        if len(input_string) <= max_length:
            return input_string
        else:
            return input_string[:max_length - 2] + '..'

    def details_to_str(offer_details):
        title_shortened = shorten_string(offer_details.get("title"))
        details_str = f'[{title_shortened}]({offer_details.get("link")})\n' \
                      f"{offer_details.get('rent'):.0f} € | {offer_details.get('space', '?'):.0f} m² | " \
                      f"{offer_details.get('rooms', '?')} Rs | {offer_details.get('date', '?')}"

        if street := offer_details.get("street", None):
            details_str += f" | {street}"
        if zipcode := offer_details.get("zipcode", None):
            neighborhoods = get_neighborhoods_for_zipcode(zipcode)
            details_str += f" | {offer_details.get('zipcode')} {', '.join(neighborhoods)}"

        if rating := offer_details.get("rating", None):
            rating_str = '⭐️' * rating
            details_str = rating_str + ' SAGA: ' + details_str
        else:
            details_str = '⭐ SAGA: ' + details_str
        #descr_shortened = shorten_string(offer_details.get("description"), 120)
        #details_str += f'\n_{descr_shortened}_'

        return details_str

    msg = details_to_str(offer_details)
    send_msg_to_telegram(msg, chat_id, token)


# sends a message to a telegram chat
def send_msg_to_telegram(msg, chat_id, token):
    msg = 'https://api.telegram.org/bot' + token + '/sendMessage?chat_id=' + chat_id + \
          '&disable_web_page_preview=true' + '&parse_mode=Markdown&text=' +msg

    try:
        response = requests.get(msg)
        if not response.status_code == 200:
            print("could not forward to telegram")
            print("Error code", response.status_code, response.text)
            print(msg)
            exit()
            return False
    except requests.exceptions.RequestException as e:
        print("could not forward to telegram" + str(e))
        print("this was the message I tried to send: " + msg)


def is_offer_known(offer: str):
    return offer in open("known_offers.txt").read().splitlines()


def add_offers_to_known_offers(offers: dict):
    for offer_list in offers.values():
        for link in offer_list:
            if not is_offer_known(link):
                print("adding offer to known offers")
                file = open("known_offers.txt", "a+")
                file.write(link)
                file.write("\n")
                file.close()


def trim_whitespace(s):
    # Replace multiple whitespace with a single space
    return re.sub(r'\s+', ' ', s).strip()


def get_zipcode(offer_soup) -> int|None:
    zipcode = None
    text_xl_divs = offer_soup.find_all('div', class_='text-xl')  # address is in "text-xl" class
    if text_xl_divs:
        for div in text_xl_divs:
            print(trim_whitespace(div.string))

            if zipcode_like_strings:=re.findall(r'\d{5}', str(div.string)):
                zipcode = int(zipcode_like_strings[0])  # find zipcode by regex for 5digits
                break

    if not zipcode:
        return None
    
    return zipcode


def get_street(offer_soup) -> int | None:
    street = None
    text_xl_divs = offer_soup.find_all('div', class_='text-xl')  # address is in "text-xl" class
    if text_xl_divs:
        for div in text_xl_divs:
            address = trim_whitespace(div.string)
            print(address)
            if zipcode_like_strings := re.findall(r'\d{5}', str(address)):
                street = address.split(',')[0]
                break
    if not street:
        return None

    return street


def get_date(offer_soup) -> str:
    try:
        # Example date_string 01.06.2024
        date_string = offer_soup.find("td", string="Verfügbar ab").findNext("td").string
        date_string = trim_whitespace(date_string)
        # todo: convert to datetime
        return date_string
    except:
        return None


def get_space(offer_soup) -> float:
    try:
        # Example rent_string 1.002,68 €
        space_string = offer_soup.find("td", string="Wohnfläche ca.").findNext("td").string
        space_string = space_string.replace('m²', '').replace(' ', '')
        space_string = space_string.split(',')[0]  # ignore cm²
        space = space_string.replace('.', '')  # replace 1.000 to be 1000
        return float(space)
    except:
        return None

def get_rent(offer_soup) -> float:
    # Example rent_string 1.002,68 €
    rent_string = offer_soup.find("td", string="Gesamtmiete").findNext("td").string
    rent_string = rent_string.replace('€', '').replace(' ', '')
    rent_string = rent_string.split(',')[0]  # ignore cents
    rent = rent_string.replace('.', '')  # replace 1.000 to be 1000

    return float(rent)


def get_rooms(offer_soup) -> int|None:
    try:
        rooms_string = offer_soup.find("td",string="Zimmer").findNext("td").string
    except AttributeError:
        # no info on rooms (happens for offices)
        return None

    try:
        rooms = int(rooms_string)
    except ValueError:
        # invalid literal for int() with base 10: '2 1/2'  there is "half rooms"
        rooms_string = rooms_string.split(" ")[0]
        rooms = int(rooms_string)

    return rooms


def get_description(offer_soup) -> int|None:
    try:
        descr_string = offer_soup.find(class_="flex flex-col gap-6 wysiwyg").text
        test = 1
    except AttributeError:
        # no info on rooms (happens for offices)
        return None

    descr_string = descr_string.replace('Lagebeschreibung', '')

    descr_string = trim_whitespace(descr_string)
    return descr_string

def get_offer_title(soup, link_to_offer):
    try:
        # get title from html
        title = soup.find_all('h1', class_='py-5', limit=1)[0]
        return title.text
    except:
        # get title from link
        title = link_to_offer.split('/')[-1]
        title = title.replace('-', ' ')
        #offer_id = link_to_offer.split('/')[-2]
        return title


def get_offer_details(link:str) -> dict:
    details = {
        "rent": None,
        "zipcode": None,
        "rooms": None,
        "space": None,
        "link": link,
        "title": None,
        "date": None,
        "description": None,
        "rating": None
    }

    # get details HTML
    req = urllib.request.Request(link)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:106.0) Gecko/20100101 Firefox/106.0')
    req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8')
    req.add_header('Accept-Language', 'en-US,en;q=0.5')

    get_url = urllib.request.urlopen(req)

    get_text = get_url.read().decode("utf-8")
    offer_soup = BeautifulSoup(get_text, "html.parser")

    # get rent price
    details["rent"] = get_rent(offer_soup)

    # get space in square meters
    details["space"] = get_space(offer_soup)

    # get rooms
    details["rooms"] = get_rooms(offer_soup)
    
    # check if zipcode is in zipcode whitelist
    details["zipcode"] = get_zipcode(offer_soup)
    details["street"] = get_street(offer_soup)
    if not details["zipcode"]:
        print(f"COULD NOT GET ADDRESS FOR LINK {link}")


    # get title
    details["title"] = get_offer_title(offer_soup, link)
    # get date
    details["date"] = get_date(offer_soup)
    # get descr
    details["description"] = get_description(offer_soup)
    return details

def rate_offers(offers:list, criteria:dict):
    for offer in offers:
        if zipcode := offer.get('zipcode', None):
            if zipcode in criteria.get('zipcode_preflist', []):
                offer['rating'] = 3
            else:
                offer['rating'] = None
    return offers

# checks if the offer meets the criteria for this chat
def offers_that_match_criteria(links_to_all_offers, criteria, check_if_known=True) -> List[str]:
    matching_offers = []

    # get only offers of matching category (e.g. "apartments")
    offers = links_to_all_offers.get(criteria.get("category", "apartments"), [])

    if not offers:
        return matching_offers

    for offer_link in offers:
        if check_if_known and is_offer_known(offer_link):
            continue    
        print("new offer", offer_link)

        offer_details = get_offer_details(offer_link)

        # check rent price
        rent_until = criteria["rent_until"]       
        if offer_details.get("rent", 0) > rent_until:
            print(f"rent too high: {offer_details.get('rent')}, max={rent_until}")
            continue

        # check min rooms
        min_rooms = criteria.get("min_rooms", None)
        if min_rooms and min_rooms > offer_details.get("rooms", 0):
            print(f"not enough rooms: {offer_details.get('rooms', 0)}, min={min_rooms}")
            continue

        # check min space
        min_space = criteria.get("min_space", None)
        if min_space and min_space > offer_details.get("space", 0):
            print(f"not enough space: {offer_details.get('space', 0)}, min={min_space}")
            continue

        # check if zipcode is in zipcode whitelist
        zipcode_whitelist = criteria["zipcode_whitelist"]
        if zipcode_whitelist:
            if zipcode:= offer_details.get("zipcode", None):
                if zipcode not in zipcode_whitelist:
                    print("Offer not in zipcode whitelist")
                    continue

        # all criteria matched
        print("matching offer found", offer_link)
        matching_offers.append(offer_details)

    return matching_offers


def wait(seconds):
    def dots():
        while True:
            for cursor in '. ':
                yield cursor
    dot = dots()
    frames_per_second = 2
    spins = int(frames_per_second*seconds)
    for _ in range(spins):
        sys.stdout.write(next(dot))  # Write the next spinner character
        sys.stdout.flush()  # Flush the output to the console
        time.sleep(1/frames_per_second)  # Simulate work with sleep
        sys.stdout.write('\b') # Backspace to overwrite the spinner character


def main(path_config):
    chat_ids = get_value_from_config(path_config, ["chats"]).keys()
    token = get_value_from_config(path_config, ["telegram_token"])

    print('chats:', get_value_from_config(path_config, ["chats"]))
    for chat_id in chat_ids:
        if get_value_from_config(path_config, ["chats", chat_id, "debug_group"]):
            send_msg_to_telegram("SAGA Bot started at " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'), chat_id, token)

    while True:
        print("checking for updates ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        current_offers = get_links_to_offers()

        # for each chat: send offer to telegram, if it meets the chat's criteria
        for chat_id in chat_ids:
            criteria = get_value_from_config(path_config, ["chats", chat_id, "criteria"])
            matching_offers = offers_that_match_criteria(current_offers, criteria)

            matching_offers = rate_offers(matching_offers, criteria)

            for offer in matching_offers:
                post_offer_to_telegram(offer, chat_id, token)

        # finally add to known offers
        add_offers_to_known_offers(current_offers)

        # check every 3 minutes
        wait(180)


if __name__ == "__main__":
    main('config.json')
