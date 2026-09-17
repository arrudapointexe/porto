import sqlite3

conn = sqlite3.connect('piso.db')
cursor = conn.cursor()

# Get tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", tables)

for table in tables:
    table_name = table[0]
    cursor.execute(f"PRAGMA table_info({table_name});")
    print(f"\nColumns for {table_name}:")
    print(cursor.fetchall())
    
    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
    print(f"Row count: {cursor.fetchone()[0]}")

conn.close()
