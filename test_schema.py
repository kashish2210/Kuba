import sqlite3
import pprint

conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()
try:
    cur.execute("SELECT sql FROM sqlite_master WHERE name='cafe_pos_order'")
    row = cur.fetchone()
    if row:
        print(row[0])
    else:
        print("Table not found")
except Exception as e:
    print('error', e)
