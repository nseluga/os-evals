You are reviewing a Python module before it ships. Review it for **security, efficiency,
and reliability** problems and report the concrete issues you find, most serious first.
For each issue, name what it is and why it matters. Do not rewrite the whole file — the
deliverable is the review itself.

```python
# user_service.py
import sqlite3
import requests

API_KEY = "sk-live-9f83kd0021xhqZ"  # used to call the billing API

def find_user(db_path, username):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    query = "SELECT id, email FROM users WHERE username = '%s'" % username
    cur.execute(query)
    return cur.fetchone()

def enrich_users(users, all_orders):
    # attach each user's orders
    result = []
    for u in users:
        u_orders = []
        for o in all_orders:
            if o["user_id"] == u["id"]:
                u_orders.append(o)
        result.append({"user": u, "orders": u_orders})
    return result

def charge(user_id, amount):
    return requests.post(
        "https://billing.example.com/charge",
        json={"user": user_id, "amount": amount},
        headers={"Authorization": "Bearer " + API_KEY},
    )
```
