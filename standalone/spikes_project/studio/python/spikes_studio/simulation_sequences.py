"""Persisted, bounded batches of independent simulation profiles."""
from copy import deepcopy
from .simulation_setup import validate_profile,effective_source


def validate(sequences):
    if not isinstance(sequences,list) or len(sequences)>32:raise ValueError('At most 32 simulation sequences')
    names=set()
    for sequence in sequences:
        name=sequence['name']
        if not isinstance(name,str) or not name.strip() or len(name)>128 or name in names:raise ValueError('Sequence names must be nonempty and unique')
        names.add(name)
        if not isinstance(sequence['entries'],list) or len(sequence['entries'])>32:raise ValueError('At most 32 entries per sequence')
        for entry in sequence['entries']:
            if type(entry['enabled']) is not bool:raise ValueError('Enabled must be boolean')
            validate_profile(entry['profile'])
            if entry['profile']['execution']!='batch':raise ValueError('Sequences require finite batch profiles; continuous runs cannot auto-advance')


def plan(source,sequence,selected=None):
    from python.spikes.netlist import parse_netlist
    validate([sequence]);jobs=[]
    for i,entry in enumerate(sequence['entries']):
        if selected is not None and i!=selected or selected is None and not entry['enabled']:continue
        profile=deepcopy(entry['profile']);deck=effective_source(source,profile)
        parse_netlist(deck,native_extensions=True)
        jobs.append({'index':i,'profile':profile,'source':deck})
    if not jobs:raise ValueError('Select an entry or enable at least one simulation')
    return jobs
