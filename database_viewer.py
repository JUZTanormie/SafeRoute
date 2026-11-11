"""Optional desktop viewer for records in SafeRoute's configured SQLite database."""

import sqlite3
import tkinter as tk
from tkinter import ttk

from database import DATABASE_NAME, create_database


create_database()
connection = sqlite3.connect(str(DATABASE_NAME))
try:
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, location, category, severity, description, timestamp, author, status
        FROM community_reports
        WHERE is_demo = 0
        ORDER BY timestamp DESC, id DESC
    """)
    reports = cursor.fetchall()
finally:
    connection.close()

root = tk.Tk()
root.title("SafeRoute — Community Report Database")
root.geometry("1120x520")
root.configure(bg="#0b1220")

tk.Label(
    root,
    text="Community Reports",
    bg="#0b1220",
    fg="#e7eefc",
    font=("Segoe UI", 20, "bold"),
).pack(anchor="w", padx=22, pady=(18, 4))

tk.Label(
    root,
    text=f"SQLite database: {DATABASE_NAME} · demonstration rows excluded",
    bg="#0b1220",
    fg="#93a4c3",
    font=("Segoe UI", 9),
).pack(anchor="w", padx=22, pady=(0, 15))

columns = ("ID", "Location", "Category", "Severity", "Description", "Timestamp", "Author", "Status")
table = ttk.Treeview(root, columns=columns, show="headings")
for column in columns:
    table.heading(column, text=column)

for column, width in {
    "ID": 45,
    "Location": 190,
    "Category": 125,
    "Severity": 70,
    "Description": 310,
    "Timestamp": 145,
    "Author": 115,
    "Status": 110,
}.items():
    table.column(column, width=width, anchor="w")

for report in reports:
    table.insert("", tk.END, values=report)

table.pack(fill="both", expand=True, padx=20, pady=(0, 18))
root.mainloop()
