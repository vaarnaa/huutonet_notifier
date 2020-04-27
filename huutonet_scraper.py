

import sys
import grequests
import requests
from datetime import datetime
import json

import db_commands

MAX_PAGES = 20
DB_PATH = './testDB.db'
HUUTONET_API_ROOT = "https://api.huuto.net/1.1/"


def is_good_response(res):
    content_type = res.headers['Content-Type'].lower()
    return (res.status_code == 200
            and content_type is not None
            and content_type.strip() == "application/json")


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


def ask_to_add_items(count_items, table_name):
    while(True):
        try:
            print_results_input = str(input("\nFound {} results. Do you wish to add them to table {}? (yes/no)\n".format(count_items, table_name)))
            if print_results_input and (print_results_input.lower() == "yes"
                                        or print_results_input.lower() == "y"):
                return True
            elif print_results_input and (print_results_input.lower() == "no"
                                        or print_results_input.lower() == "n"):
                return False
            else:
                print("Only \"yes\", \"y\", \"no\" and \"n\" are accepted answers!")
        except Exception as e:
            print("Failed to read input with error: " + str(e))



def main():

    # Form connection to database
    conn = db_commands.create_connection(DB_PATH)

    arguments = sys.argv[1:] # used for scripting later

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
    search_url = HUUTONET_API_ROOT + "items/words/"
    table_name = ""
    for term in terms:
        search_url += term
        table_name += term
        if len(terms) > 1 and term is not terms[-1]:
            search_url += "+"
            table_name += "+"

    print("\nSearching results for: {}".format(search_url))

    # request items
    res = requests.get(url = search_url)
    if not is_good_response(res):
        exit_program(conn)
    data = res.json()
    items = data["items"]

    # ask whether to add items to db
    items_to_db = ask_to_add_items(len(items), table_name)
    if not items_to_db:
        exit_program(conn)

    print("\nCreating table {}\n".format(table_name))
    db_commands.execute_sql(conn, db_commands.create_table_sql(table_name))
    conn.commit()

    # Get item ids in database
    old_ids = db_commands.get_ids_from_table(conn, table_name)

    # Go over items data and insert into database
    search_url_items = []
    titles = []
    locations = []
    begin_dates = []
    end_dates = []
    prices = []
    conditions = []
    item_ids = []
    sellers = []

    for item in items:
        search_url_items.append(item["links"]["self"])

    # request items data
    reqs = (grequests.get(url) for url in search_url_items)
    responses = grequests.map(reqs)

    for res in responses:
        if not is_good_response(res):
            continue
        item = res.json()

        item_id = int(item["id"])
        item_ids.append(item_id)

        title = item["title"]
        titles.append(title)

        seller = item["seller"]
        sellers.append(item["seller"])

        condition = item["condition"]
        conditions.append(condition)

        price = float(item["currentPrice"])
        prices.append(price)

        location = "{} {}".format(item["location"], item["postalCode"])
        locations.append(location)

        begin_date = datetime.strptime(item["listTime"], '%Y-%m-%dT%H:%M:%S%z')
        begin_dates.append(begin_date)

        end_date = datetime.strptime(item["closingTime"], '%Y-%m-%dT%H:%M:%S%z')
        end_dates.append(end_date)

        # Found new item --> add to db (and notify user)
        if not old_ids or int(item["id"]) not in old_ids:
            sql = db_commands.insert_row_sql(table_name, item_id, title , seller,\
                                             price, condition, location,\
                                             str(begin_date), str(end_date))
            inserted = db_commands.execute_sql(conn, sql)
            if inserted:
                print("Insertion succeeded for id {}".format(item_id))

        # Update old value with current values
        else:
            sql = db_commands.update_row_sql(table_name, item_id, title , seller,\
                                             price, condition, location,\
                                             str(begin_date), str(end_date))
            updated = db_commands.execute_sql(conn, sql)
            if updated:
                print("Update succeeded for id {}".format(item_id))

    table_size = db_commands.get_table_size(conn, table_name)
    if table_size:
        print("\n{} table size: {}".format(table_name,table_size))

    conn.commit()
    if conn:
        conn.close()




if __name__ == "__main__":
    main()
