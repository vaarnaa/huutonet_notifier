

import sys
import os
import grequests
import requests
from datetime import datetime
import json
import smtplib
from email.message import EmailMessage
from email.headerregistry import Address
from email.utils import make_msgid
import ssl

import env
import db_commands

MAX_PAGES = 20
DB_PATH = './testDB.db'
HUUTONET_API_ROOT = "https://api.huuto.net/1.1/"
QUERY_FILE_PATH = 'queries.txt'

# Get environment variables
gmail_user = env.USER_EMAIL
gmail_password = env.USER_PASSWORD




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


def extract_item_data(item, data):
    data["item_id"] = int(item["id"])
    data["title"] = item["title"]
    data["seller"] = item["seller"]
    data["condition"] = item["condition"]
    data["price"] = float(item["currentPrice"])
    data["location"] = "{} {}".format(item["location"], item["postalCode"])
    data["begin_date"] = str(datetime.strptime(item["listTime"], '%Y-%m-%dT%H:%M:%S%z')).split("+")[0]
    data["end_date"] = str(datetime.strptime(item["closingTime"], '%Y-%m-%dT%H:%M:%S%z')).split("+")[0]


def add_items_to_db(conn, table_name, search_url_items):
    reqs = [grequests.get(url)  for url in search_url_items[table_name]]
    responses = grequests.map(reqs)
    old_ids = db_commands.get_ids_from_table(conn, table_name)

    inserted_item_indexes = []
    updated_item_indexes = []
    inserted_links = []
    i = 0
    d = datetime.now()
    d_strftime = str(d.strftime("%Y-%m-%dT%H:%M:%S"))

    for res in responses:
        if not is_good_response(res):
            continue
        item = res.json()
        data = {}
        extract_item_data(item, data)

        # Add new item to db
        if not old_ids or data["item_id"] not in old_ids:
            sql = db_commands.insert_row_sql(table_name, data["item_id"], data["title"] , data["seller"],\
                                             data["price"], data["condition"], data["location"],\
                                             data["begin_date"], data["end_date"], d_strftime)
            inserted = db_commands.execute_sql(conn, sql)
            if inserted:
                inserted_links.append(item["links"]["alternative"])
                inserted_item_indexes.append(i)

        # Update old value with current values
        else:
            sql = db_commands.update_row_sql(table_name, data["item_id"], data["title"] , data["seller"],\
                                             data["price"], data["condition"], data["location"],\
                                             data["begin_date"], data["end_date"], d_strftime)
            updated = db_commands.execute_sql(conn, sql)
        i += 1

    # For debugging:
    table_size = db_commands.get_table_size(conn, table_name)
    if table_size:
        print("\n\n\'{}\' table size before deletes: {}".format(table_name,table_size))

    # Remove items from db that no longer exist
    deleted = db_commands.delete_removed_items(conn, table_name, d_strftime)
    if deleted:
        print("Items deleted since last query: {}".format(str(deleted)))
    else:
        print("No items removed from huutonet since last query.")

    return inserted_links


def send_email(dict_links):

    # Form email body
    query_title = "New notifcations from huutonet for query: "
    body = ""

    for table_name in dict_links:
        body += query_title + "\'"+ table_name + "\'\n"
        links = dict_links[table_name]
        for link in links:
            body += str(link) + "\n"
        body += "\n"

    sender_email = gmail_user
    receiver_emails = [gmail_user]
    subject = "Huutonet notifications"
    port = 465

    email_text = """From: %s\nTo: %s\nSubject: %s\n\n%s
    """ % (sender_email, ", ".join(receiver_emails), subject, body)

    try:
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL("smtp.gmail.com", port, context=context)
        server.login(sender_email, gmail_password)
        server.sendmail(sender_email, receiver_emails, email_text)
        str_receiver_emails = ", ".join(receiver_emails)
        string = "\nNew items added to tables:\n {}\n".format("\n ".join([key for key in dict_links]))
        print(string)
        print("Email sent to: {}\n".format(str_receiver_emails))
    except Exception as exception:
        print(exception)
    finally:
        server.quit()



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


    #
    # Arguments are used as a file name for querying
    #

    if arguments:
        query_file = sys.argv[1]
        print("Query file: {}\n".format(query_file))
        if not query_file:
            exit_program(conn)

        with open(query_file, "r") as file:
            for line in file:
                query = "+".join(line.strip().split())
                print("Query: {}".format(query))

                # Form search url and table_name
                search_url = "{}items/words/{}/limit/500".format(HUUTONET_API_ROOT, query)
                table_name = query

                print("Searching results for: {}".format(search_url))

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
                    print("Query count for {} exceeds 500. Please elaborate your search with more key words in query file.".format(query))
                    exit_program(conn)

                created = db_commands.execute_sql(conn, db_commands.create_table_sql(table_name))
                if created:

                    print("Created table: {}\n".format(table_name))
                else:
                    print("Failed to create table {}\n".format(table_name))

        conn.commit()


    #
    # Querying and updating tables in db. If ran with bash script without arguments,
    # sends notifaction by email about new items
    #

    # Get tables in db:
    table_names = db_commands.get_tables(conn)
    print("Tables in db: {}".format(str(table_names)))

    # Form search urls for each table
    search_urls = []
    for table_name in table_names:
        search_url = "{}items/words/{}/limit/500".format(HUUTONET_API_ROOT, table_name) # limiting search results to max=500
        search_urls.append(search_url)

    # request items for each table and add together
    reqs = (grequests.get(url) for url in search_urls)
    responses = grequests.map(reqs)
    search_url_items = {}
    for res in responses:
        if not is_good_response(res):
            continue
        data = res.json()
        items = data["items"]
        table_name = data["links"]["hits"].split("=")[1]
        if "&" in table_name:
            table_name = table_name.split("&")[0]
        search_url_items[table_name] = [item["links"]["self"] for item in items]

    # request items data for each table and insert/update data in table
    added_items = {}
    for table_name in table_names:
        inserted_links = add_items_to_db(conn, table_name, search_url_items)
        if inserted_links:
            added_items[table_name] = inserted_links

    if conn:
        conn.commit()

    # Send email about new items
    if not arguments and added_items:
        send_email(added_items)

    if conn:
        conn.close()



if __name__ == "__main__":
    main()
