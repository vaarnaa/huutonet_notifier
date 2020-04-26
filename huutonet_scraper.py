'''
Created on 21 Apr 2020

@author: Antero
'''

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
    print("Exiting program")
    sys.exit()



def main():
    
    # Form connection to database
    conn = db_commands.create_connection(DB_PATH)
    
    
    print("*****")
    print("*****")
    print("Search from huuto.net")
    print("*****")
    print("*****")
    
    # Ask search terms
    while(True):
        try:
            terms_input = str(input("Enter search terms delimited by space\n"))
            terms = terms_input.split()
            if len(terms) == 1 and (terms[0]).lower() == "c":
                exit_program(conn)
            break
        except Exception as e:
            print("Encountered error" + str(e) + "in input. Enter search terms delimited by space. Exit program with \"c\".")
    if not terms:
        exit_program(conn)
        
        
        
    # Check if user wants to add min or max price to search
    while(True):
        try:
            ask_price = str(input("Do you wish to enter min or max price? (yes/no)\n"))
            if ask_price and (ask_price.lower() == "yes"
                              or ask_price.lower() == "y"
                              or ask_price.lower() == "no"
                              or ask_price.lower() == "n"):
                break
            else:
                print("Only \"yes\", \"y\", \"no\" and \"n\" are accepted answers!")
        except Exception as e:
            print("Failed to read input with error: " + str(e))
     
     
    # Check if user wants to include minimum price to search
    price_min = None
    if ask_price and (ask_price.lower() == "yes" or ask_price.lower() == "y"):
        while(not price_min):
            try:
                price_min = str(input("Enter min price (integer) or leave empty\n"))
                if price_min is None:
                    break
                else:
                    price_min = int(price_min)
                    print("Price min: " + str(price_min))
            except Exception as e:
                print("Failed to read input with error: " + str(e))
                
                
    # Check if user wants to include maximum price to search
    price_max = None  
    if ask_price and (ask_price.lower() == "yes" or ask_price.lower() == "y"):
        while(not price_max):
            try:
                price_max = str(input("Enter max price (integer) or leave empty\n"))
                if price_max is None:
                    break
                else:
                    price_max = int(price_max) 
                    print("Price max: " + str(price_max))
            except Exception as e:
                print("Failed to read input with error: " + str(e))
            
    # Form search url and db_table
    search_url = HUUTONET_SEARCH_URL
    db_table = ""
    for term in terms:
        search_url += term
        db_table += term
        if len(terms) > 1 and term is not terms[-1]:
            search_url += "+"
            db_table += "+"
            
    print("Creating table " + db_table)
    db_commands.execute_sql(conn, db_commands.create_table_sql(db_table))
            
    if ask_price:
        if price_min:
            search_url += "/price_min/" + str(price_min)
        if price_max:
            search_url += "/price_max/" + str(price_max)
    print("\nSearch url: " + search_url)
    
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
            
            # Create connection
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
            print_results_input = str(input("\nFound " + str(len(search_results)) + " results. Do you wish to print them? (yes/no)\n"))
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
            
    # Get seller names through item links
    search_results = []
    reqs = (grequests.get(link) for link in links)
    results = grequests.map(reqs)
    for i in range(len(results)):
        if isGoodResponse(results[i]):
            soup_page = BeautifulSoup(results[i].text, 'html.parser')
            sellers.append(soup_page.find('div', class_='mini-profile').find('a', href=True).text.strip())
            info_table = soup_page.find('table', class_='info-table').find_all('tr')
                
            # Find item info from table and add to db
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
            sql = db_commands.insert_into_table_sql(db_table, item_ids[i], titles[i] , sellers[i],\
                                                    prices[i], conditions[i], locations[i],\
                                                    str(begin_dates[i]), str(end_dates[i]))
            inserted = db_commands.execute_sql(conn, sql)
            if inserted:
                print("New item added: "+str(item_ids[i]))
            conn.commit()
            
    conn.commit()
    if conn:
        conn.close()
        
    
    
    
if __name__ == "__main__":
    main()