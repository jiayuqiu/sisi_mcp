import sqlite3
import os

db_path = 'data/sisi.sqlite'
if not os.path.exists(db_path):
    print(f"Error: {db_path} not found")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='ship_cnt_in_pipe';")
result = cursor.fetchone()
if result:
    print(result[0])
else:
    print("Table ship_cnt_in_pipe not found")
conn.close()
