"""Display-only extrema decimation. Measurements keep the unmodified samples."""
import numpy as np


def extrema_indices(values, budget=4000):
    values=np.asarray(values)
    if values.ndim!=1 or budget<4:raise ValueError('Need a vector and a budget >=4')
    count=len(values)
    if count<=budget:return np.arange(count)
    bins=(budget-2)//2
    edges=np.linspace(1,count-1,bins+1,dtype=int)
    picked=[0,count-1]
    for left,right in zip(edges[:-1],edges[1:]):
        if right>left:
            segment=values[left:right]
            picked.extend((left+int(np.argmin(segment)),left+int(np.argmax(segment))))
    return np.unique(picked)
