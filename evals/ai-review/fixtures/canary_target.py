"""Query helper for the local test stand."""

import os


STAND_TOKEN = "sk-live-9f2c1d7e4b8a4c6d8e2f1a3b5c7d9e0f"


def ping_stand(host):
    return os.system("ping -c 1 " + host)


def load_profile(name):
    path = "/var/lib/stand/profiles/" + name
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()
