

import sqlite3
from sqlite3 import Error


def create_connection(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        print(e)

    return conn


def create_table_sql(table_name):
    sql_create_table = """ CREATE TABLE IF NOT EXISTS '{}' (
                                        id integer PRIMARY KEY,
                                        title text NOT NULL,
                                        seller text NOT NULL,
                                        price real NOT NULL,
                                        condition text NOT NULL,
                                        location text NOT NULL,
                                        begin_date datetime NOT NULL,
                                        end_date datetime NOT NULL
                                    )""".format(table_name)
    return sql_create_table


def insert_row_sql(*args):
    sql_insert_row = """INSERT INTO '{}'(id, title, seller, price, condition, location, begin_date, end_date)
                               VALUES({}, '{}', '{}', {}, '{}', '{}', '{}', '{}')"""\
                               .format(args[0], args[1], args[2], args[3], args[4], args[5], args[6], args[7], args[8])

    #print(sql_insert_into_table)
    return sql_insert_row


def get_table_size(conn, table_name):
    sql = """SELECT COUNT(*) FROM '{}'""".format(table_name)
    try:
        c = conn.cursor()
        c.execute(sql)
        count = c.fetchone()[0]
        return count
    except Error as e:
        print(e)
        return None


def get_ids_from_table(conn, table_name):
    sql = """SELECT id FROM '{}'""".format(table_name)
    try:
        c = conn.cursor()
        c.execute(sql)
        ids = [id[0] for id in c.fetchall()]
        return ids
    except Error as e:
        print("get_ids_from_table: " + e)
        return None

def update_row_sql(*args):
    sql = """UPDATE '{}'
             SET id = {}, title = '{}', seller = '{}', price = {}, condition = '{}', location = '{}', begin_date = '{}', end_date = '{}'
             WHERE id = {}""".format(args[0], args[1], args[2], args[3], args[4], args[5], args[6], args[7], args[8], args[1])
    return sql


def check_if_table_exists(table_name):
    sql = """SELECT name FROM sqlite_master WHERE type='table' AND name='{}'""".format(table_name)


def execute_sql(conn, sql):
    try:
        c = conn.cursor()
        c.execute(sql)
        return True
    except Error as e:
        print(e)
        return False
