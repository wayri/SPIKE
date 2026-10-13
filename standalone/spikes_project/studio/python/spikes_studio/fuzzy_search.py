# SPDX-License-Identifier: Apache-2.0
"""Bounded search-only matching. Never rewrites identifiers or executes results.

Exact/token/substring matches precede typo matches. Short or wholly numeric
terms remain literal. Quoted phrases and exclusions are always literal.
"""
from functools import lru_cache
import re
import shlex
import unicodedata


def normalize(value):
    return unicodedata.normalize('NFKC',str(value)).casefold()


def _numeric(term):
    return term.isnumeric() or re.fullmatch(r'[+]?\d+(?:[.,]\d+)*(?:e[+-]?\d+)?',term) is not None


@lru_cache(maxsize=8192)
def _words(text):
    return tuple(dict.fromkeys(re.findall(r'\w+',text)))


def _distance(a,b,limit):
    """Banded optimal-string-alignment distance, including adjacent swaps."""
    if abs(len(a)-len(b))>limit:return limit+1
    previous=list(range(len(b)+1));older=None
    for i,ca in enumerate(a,1):
        current=[limit+1]*(len(b)+1);current[0]=i
        for j in range(max(1,i-limit),min(len(b),i+limit)+1):
            current[j]=min(current[j-1]+1,previous[j]+1,previous[j-1]+(ca!=b[j-1]))
            if older is not None and j>1 and ca==b[j-2] and a[i-2]==b[j-1]:
                current[j]=min(current[j],older[j-2]+1)
        if min(current)>limit:return limit+1
        older,previous=previous,current
    return previous[-1]


@lru_cache(maxsize=8192)
def _typo_cost(term,word):
    if not 4<=len(word)<=64 or word.isnumeric():return None
    limit=1 if len(term)<8 else 2
    distance=_distance(term,word,limit)
    if any(c.isdigit() for c in term) and len(word)>len(term) and word[len(term):].isalpha():
        distance=min(distance,_distance(term,word[:len(term)],limit))
    return 100+20*distance+abs(len(term)-len(word)) if distance<=limit else None


@lru_cache(maxsize=8192)
def _term_score(term,text):
    if term==text:return 0
    if term in _words(text):return 1
    if term in text:return 2
    if not 4<=len(term)<=64 or _numeric(term):return None
    best=None
    for word in _words(text):
        # Part-number suffixes denote packages. Match a typo in the typed stem,
        # without treating the suffix as an extra user spelling error.
        candidate=_typo_cost(term,word)
        if candidate is not None:
            best=candidate if best is None else min(best,candidate)
    return best


@lru_cache(maxsize=256)
def _terms(query):
    try:parts=shlex.split(query)
    except ValueError:parts=query.split() # An unfinished quote is ordinary live input.
    return tuple(parts)


def score(text,query):
    """Return an integer match cost or None; all positive terms must match.

    Query limit is 512 characters / 32 terms, candidate limit 8192 characters.
    Oversized live input yields no search results, not an expensive scan.
    """
    if not isinstance(query,str):raise TypeError('Search query must be text')
    if len(query)>512:return None
    query=normalize(query).strip();text=normalize(text)[:8192]
    if not query:return 0
    if query==text and not query.startswith('-'):return 0
    terms=_terms(query)
    if len(terms)>32:return None
    total=0
    for term in terms:
        if term.startswith('-') and len(term)>1:
            if term[1:] in text:return None
            continue
        if ' ' in term:
            if term not in text:return None
            total+=2;continue
        pieces=re.findall(r'\w+',term)
        if pieces and not _numeric(term) and (len(pieces)>1 or pieces[0]!=term):
            costs=[_term_score(piece,text) for piece in pieces]
            if any(cost is None for cost in costs):return None
            total+=sum(costs);continue
        cost=_term_score(term,text)
        if cost is None:return None
        total+=cost
    return total


def matches(text,query):return score(text,query) is not None


def ranked(items,query,*,text=str):
    found=[]
    for index,item in enumerate(items):
        cost=score(text(item),query)
        if cost is not None:found.append((cost,index,item))
    return [item for _,_,item in sorted(found,key=lambda row:row[:2])]
