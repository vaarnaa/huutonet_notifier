

import sys
import grequests
from bs4 import BeautifulSoup
from datetime import datetime


import db_commands

MAX_PAGES = 20
DB_PATH = './testDB.db'
HUUTONET_URL = "https://www.huuto.net"
HUUTONET_SEARCH_URL = HUUTONET_URL + "/haku/words/"


def isGoodResponse(resp):
    content_type = resp.headers['Content-Type'].lower()
    return (resp.status_code == 200
            and content_type is not None
            and content_type.find('html') > -1)


def exit_program(conn):
    if conn:
        conn.close()
    print("\nExiting program")
    sys.exit()


def ask_search_terms():
    while(True):
        try:
            terms_input = str(input("\nEnter search terms delimited by space. Exit program with \"exit\".\n"))
            terms = terms_input.split()
            if not terms:
                continue
            elif len(terms) == 1 and (terms[0]).lower() == "exit":
                return None
            else:
                return terms
        except Exception as e:
            print("\nEncountered error" + str(e) + "in input.")



def main():

    # Form connection to database
    conn = db_commands.create_connection(DB_PATH)

    arguments = sys.argv[1:]

    print("\n\n")
    print("****                         ****")
    print("***                           ***")
    print("**                             **")
    print("*                               *")
    print("      Search from huuto.net      ")
    print("*                               *")
    print("**                             **")
    print("****                          ***")
    print("****                         ****")
    print("\n")

    # Ask search terms
    if not arguments:
        terms = ask_search_terms()
        if not terms:
            exit_program(conn)

    # Form search url and table_name
    search_url = HUUTONET_SEARCH_URL
    table_name = ""
    for term in terms:
        search_url += term
        table_name += term
        if len(terms) > 1 and term is not terms[-1]:
            search_url += "+"
            table_name += "+"

    print("\nSearching results for: " + search_url)

    # Request first page
    req = grequests.get(search_url)
    res = grequests.map([req])
    res = res[0]

    if not isGoodResponse(res):
        print("Encountered error searching url: " + search_url)
        exit_program(conn)

    # Create a BeautifulSoup object
    soup = BeautifulSoup(res.text, 'html.parser')

    # Check how many search result pages and request all pages
    pages = soup.find(id='pagination')
    if pages:
        list_items = pages.find_all('li')
        num_pages = len(list_items) - 2
        print ("\nNumber of search result pages: ", str(num_pages))
        if num_pages > MAX_PAGES:
            print("Number of search result pages exceeds " + str(MAX_PAGES) + ". Shutting down program.")
            exit_program(conn)

    # Enter all results to list
    search_results = soup.find_all('div', class_='grid-element-container')
    if pages:
        search_urls = []
        for num in range(2, num_pages + 1):

            # Create search urls
            search_url_page = search_url
            search_url_page += "/page/" + str(num)
            search_urls.append(search_url_page)

        reqs = (grequests.get(url) for url in search_urls)
        results = grequests.map(reqs)
        for res in results:
            if isGoodResponse(res):
                soup_pages = BeautifulSoup(res.text, 'html.parser')
                search_results_pages = soup_pages.find_all('div', class_='grid-element-container')
                search_results += search_results_pages

    print("Number of search results: " + str(len(search_results)))

    # Iterate over results
    result_num = 1
    while(True):
        try:
            print_results_input = str(input("\nFound " + str(len(search_results)) + " results. Do you wish to add them to table {}? (yes/no)\n".format(table_name)))
            if print_results_input and (print_results_input.lower() == "yes"
                                        or print_results_input.lower() == "y"):
                break
            elif print_results_input and (print_results_input.lower() == "no"
                                        or print_results_input.lower() == "n"):
                exit_program(conn)
            else:
                print("Only \"yes\", \"y\", \"no\" and \"n\" are accepted answers!")
        except Exception as e:
            print("Failed to read input with error: " + str(e))


    print("Creating table " + table_name)
    db_commands.execute_sql(conn, db_commands.create_table_sql(table_name))

    # Go over results and insert into database
    titles = []
    locations = []
    begin_dates = []
    end_dates = []
    prices = []
    links = []
    conditions = []
    item_ids = []
    sellers = []

    for result in search_results:
        try:
            title = result.find('div', class_='item-card__title').text.strip()
            titles.append(title)
            link = HUUTONET_URL + result.find('a', class_='item-card-link')['href'].strip()
            links.append(link)
        except Exception as e:
            print("Encountered error" + str(e) + " when parsing search results")

    # Get item ids in database
    old_ids = db_commands.get_ids_from_table(conn, table_name)

    # Get seller names through item links
    search_results = []
    reqs = (grequests.get(link) for link in links)
    results = grequests.map(reqs)
    for i in range(len(results)):
        if isGoodResponse(results[i]):
            soup_page = BeautifulSoup(results[i].text, 'html.parser')
            sellers.append(soup_page.find('div', class_='mini-profile').find('a', href=True).text.strip())
            info_table = soup_page.find('table', class_='info-table').find_all('tr')

            # Find item info from info_table
            for tr in info_table:
                tds = tr.find_all('td')
                if 'hinta' in tds[0].text.lower():
                    price = tds[1].text.strip()
                    price = price.split()[0].replace(",", ".") # remove euro sign and replace possible comma with dot
                    prices.append(float(price))
                elif 'Sijainti' in tds[0]:
                    locations.append(tds[1].text.strip())
                elif 'Kunto' in tds[0]:
                    conditions.append(tds[1].text.strip())
                elif 'Lisätty' in tds[0]:
                    begin_date_str = tds[1].text.strip()
                    begin_date = datetime.strptime(begin_date_str, '%d.%m.%Y %H:%M')
                    begin_dates.append(begin_date)
                elif 'Sulkeutuu' in tds[0]:
                    end_date_str = tds[1].text.strip()
                    end_date = datetime.strptime(end_date_str, '%d.%m.%Y %H:%M')
                    end_dates.append(end_date)
                elif 'Kohdenumero' in tds[0]:
                    item_ids.append(int(tds[1].text.strip()))

            # Found new item --> add to db (and notify user)
            if not old_ids or old_ids and item_ids[i] not in old_ids:
                print("New id: " + str(item_ids[i]))
                sql = db_commands.insert_row_sql(table_name, item_ids[i], titles[i] , sellers[i],\
                                                 prices[i], conditions[i], locations[i],\
                                                 str(begin_dates[i]), str(end_dates[i]))
                inserted = db_commands.execute_sql(conn, sql)
                if inserted:
                    print("Insertion succeeded!")

            # Update old value with current values
            else:
                sql = db_commands.update_row_sql(table_name, item_ids[i], titles[i] , sellers[i],\
                                                 prices[i], conditions[i], locations[i],\
                                                 str(begin_dates[i]), str(end_dates[i]))
                updated = db_commands.execute_sql(conn, sql)
                if updated:
                    print("Update succeeded for id " + str(item_ids[i]))

    table_size = db_commands.get_table_size(conn, table_name)
    if table_size:
        print("{} table size: ".format(table_name) + str(table_size))

    conn.commit()
    if conn:
        conn.close()




if __name__ == "__main__":
    main()
