

import sys
import grequests
import requests
from datetime import datetime
import json

import db_commands

MAX_PAGES = 20
DB_PATH = './testDB.db'
HUUTONET_API_ROOT = "https://api.huuto.net/1.1/"
#g_table_name = ""


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


def add_items_to_db(conn, table_name, dict_search_url_items):
    reqs = [grequests.get(url)  for url in dict_search_url_items[table_name]]
    responses = grequests.map(reqs)
    old_ids = db_commands.get_ids_from_table(conn, table_name)

    inserted_item_indexes = []
    updated_item_indexes = []
    i = 0
    for res in responses:
        if not is_good_response(res):
            continue
        item = res.json()

        item_id = int(item["id"])
        title = item["title"]
        seller = item["seller"]
        condition = item["condition"]
        price = float(item["currentPrice"])
        location = "{} {}".format(item["location"], item["postalCode"])
        begin_date = datetime.strptime(item["listTime"], '%Y-%m-%dT%H:%M:%S%z')
        end_date = datetime.strptime(item["closingTime"], '%Y-%m-%dT%H:%M:%S%z')

        d = datetime.now()
        d_strftime = d.strftime("%Y-%m-%dT%H:%M:%S%z") + str("+03:00")

        # Found new item --> add to db (and notify user)
        if not old_ids or int(item["id"]) not in old_ids:
            sql = db_commands.insert_row_sql(table_name, item_id, title , seller,\
                                             price, condition, location,\
                                             str(begin_date), str(end_date), str(d_strftime))
            inserted = db_commands.execute_sql(conn, sql)
            if inserted:
                inserted_item_indexes.append(i)
                #print("Insertion succeeded for id {}".format(item_id))

        # Update old value with current values
        else:
            sql = db_commands.update_row_sql(table_name, item_id, title , seller,\
                                             price, condition, location,\
                                             str(begin_date), str(end_date), str(d_strftime))
            updated = db_commands.execute_sql(conn, sql)
            if updated:
                updated_item_indexes.append(i)
                #print("Update succeeded for id {}".format(item_id))
        i += 1

    table_size = db_commands.get_table_size(conn, table_name)
    if table_size:
        print("\n\n{} table size: {}".format(table_name,table_size))

    # For items removed from huutonet:
    # --> Find all rows that were not inserted/updated and delete them
    deleted = db_commands.delete_removed_items(conn, table_name)
    if deleted:
        print("Delete success: " + str(deleted))
    else:
        print("No items removed from huutonet since last query for table: {}".format(table_name))

    print("\nInserted item indexes: {}".format(str(inserted_item_indexes)))
    print("Updated item indexes: {}".format(str(updated_item_indexes)))



def main():
    #global g_table_name



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



    #
    # Arguments are used for searching huutonet and as table_names in db for
    # storing search results
    #

    if arguments:
        query = "+".join(sys.argv[1:])
        print("Query: " + str(query))
        if not query:
            exit_program(conn)

        # Form search url and table_name
        search_url = HUUTONET_API_ROOT + "items/words/"
        table_name = query
        search_url += query + "/limit/500"


        print("\nSearching results for: {}".format(search_url))

        # request items
        res = requests.get(url = search_url)
        if not is_good_response(res):
            exit_program(conn)
        data = res.json()
        if "errors" in data:
            print(data["errors"][0]["messages"][0])
            exit_program(conn)
        items = data["items"]
        if len(items) == 500:
            print("Query count exceeds 500. Please elaborate your search with more key words.")
            exit_program(conn)

        # ask whether to add items to db
        items_to_db = ask_to_add_items(len(items), table_name)
        if not items_to_db:
            exit_program(conn)

        print("\nCreating table {}\n".format(table_name))
        db_commands.execute_sql(conn, db_commands.create_table_sql(table_name))
        conn.commit()
        exit_program(conn)




    # Update search results for all tables in db

    # Get tables in db:
    table_names = db_commands.get_tables(conn)
    print("Tables: {}".format(str(table_names)))

    # Form search urls for each table
    search_urls = []
    for table_name in table_names:
        search_url = HUUTONET_API_ROOT + "items/words/" + table_name +"/limit/500" # limiting search results to max=500
        search_urls.append(search_url)


    # request items for each table and add together
    reqs = (grequests.get(url) for url in search_urls)
    responses = grequests.map(reqs)
    dict_search_url_items = {}
    for res in responses:
        if not is_good_response(res):
            continue
        data = res.json()
        items = data["items"]
        table_name = data["links"]["hits"].split("=")[1]
        if "&" in table_name:
            table_name = table_name.split("&")[0]
        search_url_items = [item["links"]["self"] for item in items]
        dict_search_url_items[table_name] = search_url_items

    # request items data for each table and insert/update data in table
    reqs = []
    for table_name in table_names:
        add_items_to_db(conn, table_name, dict_search_url_items)

    conn.commit()
    if conn:
        conn.close()




if __name__ == "__main__":
    main()
