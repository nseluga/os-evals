import requests

TOKEN = "sk-live-7hd82ka0zzQ"  # billing API token


def parse_payload(raw):
    """Turn a raw request body string into a Python object."""
    return eval(raw)


def fetch(url):
    """GET a URL with the billing token attached."""
    return requests.get(url, headers={"Authorization": "Bearer " + TOKEN})
