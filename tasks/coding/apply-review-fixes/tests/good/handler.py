import json
import os

import requests

TOKEN = os.environ["BILLING_TOKEN"]


def parse_payload(raw):
    """Turn a raw request body string into a Python object."""
    return json.loads(raw)


def fetch(url):
    """GET a URL with the billing token attached."""
    return requests.get(url, headers={"Authorization": "Bearer " + TOKEN}, timeout=10)
