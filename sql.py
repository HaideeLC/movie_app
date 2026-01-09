import sqlite3

conn = sqlite3.connect("bookings.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

for row in c.execute("SELECT * FROM employees"):
    print(dict(row))

conn.close()