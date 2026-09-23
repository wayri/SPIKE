"""Portable workspace preferences, separate from circuit semantics."""
from copy import deepcopy

CONTRACT='spikes/workspace/v1'
PRESETS={
    'Power electronics':dict(page='Schematic',split=True,browser=True,properties=True),
    'Analog / RF':dict(page='Frequency',split=False,browser=True,properties=True),
    'Controls / dashboard':dict(page='Dashboard',split=False,browser=True,properties=False),
}


def preset(name):
    if name not in PRESETS:raise ValueError('Unknown workspace preset')
    return dict(contract=CONTRACT,name=name,**deepcopy(PRESETS[name]))


def validate(data, pages=None):
    if not isinstance(data,dict) or data.get('contract')!=CONTRACT:raise ValueError('Unsupported workspace format')
    if set(data)-{'contract','name','page','split','browser','properties'}:raise ValueError('Unknown workspace field')
    if not isinstance(data.get('name'),str) or not 1<=len(data['name'])<=120:raise ValueError('Workspace needs a bounded name')
    if not isinstance(data.get('page'),str) or not 1<=len(data['page'])<=120:raise ValueError('Workspace needs a page name')
    if pages is not None and data['page'] not in pages:raise ValueError('This workspace page is unavailable: '+data['page'])
    if any(type(data.get(key)) is not bool for key in ('split','browser','properties')):raise ValueError('Workspace pane flags must be boolean')
    return deepcopy(data)
