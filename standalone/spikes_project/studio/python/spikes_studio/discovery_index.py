# SPDX-License-Identifier: Apache-2.0
"""Bounded search index for one immutable installed-library snapshot.

Literal matches have cost 0/1/2 in the shared matcher. Once enough exist to
fill a result page, fuzzy candidates (cost >= 100) cannot enter it.
Other query shapes retain the shared matcher's exact ordering and exclusions.
"""
from collections import OrderedDict
import re

from .fuzzy_search import normalize, ranked


def component_text(record):
    return ' '.join(record[key] for key in ('id', 'name', 'family', 'category'))


def manufacturer_text(record):
    return ' '.join(record[key] for key in ('manufacturer', 'mpn', 'category', 'description'))


class DiscoveryIndex:
    """Keep normalized text and at most 16 ranked pages; never cache documents."""

    def __init__(self, records, text=component_text):
        self.text = text
        self.entries = {}
        for record in records:
            value = normalize(text(record))[:8192]
            self.entries[record['id']] = (value, frozenset(re.findall(r'\w+', value)))
        self.cache = OrderedDict()

    def query(self, records, query, limit):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Discovery page size must be 1..100')
        # Callers supply the current collection, preserving Favorites/Recent
        # membership and order independently of the immutable library snapshot.
        key = (query, limit, tuple(record['id'] for record in records))
        if key in self.cache:
            self.cache.move_to_end(key)
            return list(self.cache[key])
        term = normalize(query).strip()
        result = None
        if len(query) <= 512 and re.fullmatch(r'\w+', term):
            exact = []; words = []; substrings = []
            for record in records:
                value, tokens = self.entries[record['id']]
                if value == term: exact.append(record)
                elif term in tokens: words.append(record)
                elif term in value: substrings.append(record)
            if len(exact) + len(words) + len(substrings) >= limit:
                result = [*exact, *words, *substrings][:limit]
        if result is None:
            result = ranked(records, query, text=lambda record:self.entries[record['id']][0])[:limit]
        self.cache[key] = tuple(result)
        if len(self.cache) > 16:
            self.cache.popitem(last=False)
        return list(result)
