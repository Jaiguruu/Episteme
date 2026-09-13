"""Star import and conditional import."""

from pkg.module1 import *

try:
    import ujson as json
except ImportError:
    import json


def parse(text):
    return json.loads(text)
