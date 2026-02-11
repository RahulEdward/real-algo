import sqlite3
conn = sqlite3.connect('db/realalgo.db')
cursor = conn.cursor()
# List tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("Tables:", tables)

# Check user table
for t in tables:
    if 'user' in t.lower():
        cursor.execute(f"SELECT * FROM {t} LIMIT 5")
        cols = [d[0] for d in cursor.description]
        print(f"\nTable: {t}")
        print("Columns:", cols)
        for row in cursor.fetchall():
            print(row)
conn.close()
