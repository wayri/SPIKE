"""Reusable multiresolution min/max index; display queries do not scan full traces.

Only original-sample indices are cached. No numerical measurements are performed
on this representation. Construct once per immutable acquired waveform.
"""
import numpy as np


class WaveformIndex:
    def __init__(self,time,values):
        self.time=np.asarray(time);self.values=np.asarray(values)
        if self.time.ndim!=1 or self.values.shape!=self.time.shape:raise ValueError('Expected equally sized vectors')
        if np.iscomplexobj(self.values):raise ValueError('Select a real-valued signal for plotting')
        self.levels=[];block=256;count=len(self.values)//block
        if count:
            groups=self.values[:count*block].reshape(count,block)
            start=np.arange(count,dtype=np.int64)*block
            low=start+np.argmin(groups,axis=1);high=start+np.argmax(groups,axis=1)
            self.levels.append((block,low,high))
            while len(low)>=2:
                count=len(low)//2
                candidates=np.stack((low[:2*count],high[:2*count]),axis=1).reshape(count,4)
                samples=self.values[candidates];rows=np.arange(count)
                low=candidates[rows,np.argmin(samples,axis=1)];high=candidates[rows,np.argmax(samples,axis=1)]
                block*=2;self.levels.append((block,low,high))

    @property
    def cache_bytes(self):return sum(low.nbytes+high.nbytes for _,low,high in self.levels)

    def indices(self,limits=None,budget=4000):
        from .plotting import extrema_indices
        if type(budget) is not int or budget<8:raise ValueError('Display budget must be an integer >=8')
        left,right=0,len(self.time)
        if limits is not None:
            if len(limits)!=2 or not np.isfinite(limits).all():raise ValueError('Expected two finite viewport limits')
            low,high=sorted(limits)
            left=max(0,int(np.searchsorted(self.time,low))-1)
            right=min(right,int(np.searchsorted(self.time,high,side='right'))+1)
        if right-left<=budget:return np.arange(left,right)
        selected=None
        for level in self.levels:
            selected=level
            if (right-left)//level[0]<=max(1,(budget-6)//2):break
        if selected is None:return left+extrema_indices(self.values[left:right],budget)
        block,minima,maxima=selected
        first=(left+block-1)//block;last=min(right//block,len(minima))
        if first>=last:return left+extrema_indices(self.values[left:right],budget)
        chunks=[np.array([left,right-1]),minima[first:last],maxima[first:last]]
        for start,end in ((left,first*block),(last*block,right)):
            if end>start:
                window=self.values[start:end]
                chunks.append(start+np.array([np.argmin(window),np.argmax(window)]))
        picked=np.unique(np.concatenate(chunks))
        if len(picked)>budget:picked=picked[extrema_indices(self.values[picked],budget)]
        return picked
