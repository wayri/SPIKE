# SPDX-License-Identifier: Apache-2.0
"""Sourced product identities, deliberately not executable electrical models."""
from copy import deepcopy
import json
from urllib.parse import urlparse

from .resources import resource_dir
from .fuzzy_search import ranked


CONTRACT = 'spikes/manufacturer-discovery/v1'
ALIASES = {'Analog Devices': 'ADI Linear Technology Maxim', 'Texas Instruments': 'TI',
           'Monolithic Power Systems': 'MPS', 'Wolfspeed': 'Cree',
           'Nordic Semiconductor': 'nRF Nordic', 'STMicroelectronics': 'ST STMicro',
           'Lattice Semiconductor': 'Lattice CPLD FPGA',
           'onsemi': 'ON Semiconductor Fairchild', 'Nexperia': 'NXP discrete logic',
           'ROHM Semiconductor': 'ROHM'}


def validate(payload):
    tags=[payload[key] for key in ('contract','schema') if key in payload] if isinstance(payload,dict) else []
    if not tags or any(tag != CONTRACT for tag in tags):
        raise ValueError('Unsupported manufacturer discovery catalog')
    rows = payload.get('records')
    if not isinstance(rows, list) or len(rows) > 20000:
        raise ValueError('Manufacturer discovery inventory exceeds its limit')
    ids, identities = set(), set()
    for row in rows:
        for field in ('id', 'manufacturer', 'part_number', 'category', 'description', 'checked_on'):
            if not isinstance(row.get(field), str) or not row[field].strip() or len(row[field]) > 1000:
                raise ValueError('Invalid discovery field: ' + field)
        identity = (row['manufacturer'].casefold(), row['part_number'].casefold())
        if row['id'] in ids or identity in identities:
            raise ValueError('Duplicate manufacturer product identity')
        ids.add(row['id']); identities.add(identity)
        for field in ('product_url', 'model_url'):
            value = row.get(field)
            if value is None and field == 'model_url':
                continue
            parsed = urlparse(value) if isinstance(value, str) else None
            if not parsed or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Discovery links must be HTTPS URLs without credentials')
        source_urls = row.get('source_urls', [])
        if not isinstance(source_urls, list) or len(source_urls) > 20:
            raise ValueError('Discovery source links must be a bounded list')
        for value in source_urls:
            parsed = urlparse(value) if isinstance(value, str) else None
            if not parsed or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Discovery links must be HTTPS URLs without credentials')
        if row.get('model_status') not in ('source_identified_not_qualified', 'model_not_reviewed'):
            raise ValueError('A product listing cannot approve model execution')
        if row['model_status'] == 'source_identified_not_qualified' and not row.get('model_url'):
            raise ValueError('An identified model requires its source link')
    return payload


def load_catalog():
    path = resource_dir('library') / 'manufacturer-discovery-v1.json'
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Manufacturer discovery catalog exceeds 16 MiB')
    return deepcopy(validate(json.loads(path.read_text(encoding='utf-8'))))


def search(records, text='', manufacturer=None, category=None):
    if not isinstance(text, str) or len(text) > 512:
        raise ValueError('Search is limited to 512 characters')
    rows = [row for row in records if (not manufacturer or row['manufacturer'] == manufacturer)
            and (not category or row['category'] == category)]
    rows.sort(key=lambda row: (row['manufacturer'].casefold(), row['part_number'].casefold()))
    return ranked(rows, text, text=lambda row: ' '.join(row[key] for key in
                  ('manufacturer', 'part_number', 'category', 'description')) + ' ' + ALIASES.get(row['manufacturer'], ''))
