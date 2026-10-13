# SPDX-License-Identifier: Apache-2.0
"""Bounded session navigation; browsing history never changes circuit history."""
class NavigationHistory:
    def __init__(self,limit=128):
        if type(limit) is not int or not 2<=limit<=256:raise ValueError('Navigation history limit must be 2..256')
        self.entries=[];self.position=-1;self.limit=limit
    @property
    def can_back(self):return self.position>0
    @property
    def can_forward(self):return self.position+1<len(self.entries)
    def visit(self,target):
        if not isinstance(target,tuple) or len(target)!=2 or target[0] not in ('tool','workspace') or type(target[1]) is not int or target[1]<0:raise ValueError('Invalid navigation target')
        if self.position>=0 and self.entries[self.position]==target:return
        self.entries=self.entries[:self.position+1]+[target]
        if len(self.entries)>self.limit:self.entries=self.entries[-self.limit:]
        self.position=len(self.entries)-1
    def back(self):
        if not self.can_back:return None
        self.position-=1;return self.entries[self.position]
    def forward(self):
        if not self.can_forward:return None
        self.position+=1;return self.entries[self.position]
