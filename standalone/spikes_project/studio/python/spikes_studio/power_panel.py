"""Editable power topology with separate planning budgets and real SPICE stage files."""
from copy import deepcopy
import json
import wx
from .power_tree import new_stage,budgets,read_model,compile_tree,validate
from .document import write_json

class PowerCanvas(wx.Panel):
    def __init__(self,panel,parent):
        super().__init__(parent);self.panel=panel;self.zoom=1.;self.offset=[30.,30.];self.hits=[];self.drag=None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT);self.Bind(wx.EVT_PAINT,self.paint);self.Bind(wx.EVT_LEFT_DOWN,self.select)
        self.Bind(wx.EVT_MOUSEWHEEL,self.wheel);self.Bind(wx.EVT_MIDDLE_DOWN,lambda e:self.pan(e,True));self.Bind(wx.EVT_MIDDLE_UP,lambda e:self.pan(e,False));self.Bind(wx.EVT_MOTION,self.motion)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST,lambda e:setattr(self,'drag',None))
    def paint(self,event):
        p=self.panel.owner.palette;dc=wx.AutoBufferedPaintDC(self);dc.SetBackground(wx.Brush(p['canvas']));dc.Clear();self.hits=[]
        stages=self.panel.owner.doc.data['power_tree']['stages'];by_id={s['id']:s for s in stages};rows={};positions={}
        report=budgets(self.panel.owner.doc.data['power_tree'],self.panel.maximum.GetValue())['stages']
        for s in stages:
            depth=0;parent=s['parent']
            while parent:depth+=1;parent=by_id[parent]['parent']
            row=rows.get(depth,0);rows[depth]=row+1;positions[s['id']]=(depth*265,row*140)
        def pt(x,y):return wx.Point(round(x*self.zoom+self.offset[0]),round(y*self.zoom+self.offset[1]))
        dc.SetPen(wx.Pen(p['accent'],2))
        for s in stages:
            if s['parent']:
                a=positions[s['parent']];b=positions[s['id']];start=pt(a[0]+225,a[1]+50);end=pt(b[0],b[1]+50);mid=(start.x+end.x)//2
                dc.DrawLines([start,wx.Point(mid,start.y),wx.Point(mid,end.y),end])
        dc.SetFont(wx.Font(max(7,round(10*self.zoom)),wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
        for s in stages:
            x,y=positions[s['id']];rect=wx.Rect(pt(x,y),pt(x+225,y+105));self.hits.append((rect,s['id']));r=report[s['id']]
            dc.SetPen(wx.Pen(p['danger'] if r['over_limit'] else p['accent'] if s['id']==self.panel.selected else p['grid'],2))
            dc.SetBrush(wx.Brush(p['selected'] if s['id']==self.panel.selected else p['panel']));dc.DrawRoundedRectangle(rect,6)
            dc.SetTextForeground(p['fg']);model='SPICE attached' if s['model'] else 'Ideal source' if s['kind']=='source' else 'Ideal I load' if s['kind']=='load' else 'Budget only'
            label=f"{s['name'][:22]}\n{s['kind']} · {r['output_v']:g} V · {r['output_a']:.3g} A\nPin {r['input_w']:.3g} W · loss {r['loss_w']:.3g} W\n{model}"
            dc.DrawLabel(label,wx.Rect(rect.x+8,rect.y+7,rect.width-16,rect.height-14))
        if not stages:
            dc.SetTextForeground(p['muted']);dc.DrawText('Add a supply, then converters and loads.\nMiddle-drag to pan · Wheel to zoom',30,30)
    def select(self,event):
        for rect,ident in self.hits:
            if rect.Contains(event.GetPosition()):self.panel.select_stage(ident);return
    def wheel(self,event):
        point=event.GetPosition();world=[(point.x-self.offset[0])/self.zoom,(point.y-self.offset[1])/self.zoom]
        self.zoom=max(.3,min(2.5,self.zoom*(1.15 if event.GetWheelRotation()>0 else 1/1.15)))
        self.offset=[point.x-world[0]*self.zoom,point.y-world[1]*self.zoom];self.Refresh()
    def pan(self,event,start):
        self.drag=event.GetPosition() if start else None
        if start:self.CaptureMouse()
        elif self.HasCapture():self.ReleaseMouse()
    def motion(self,event):
        if self.drag is not None:
            point=event.GetPosition();self.offset[0]+=point.x-self.drag.x;self.offset[1]+=point.y-self.drag.y;self.drag=point;self.Refresh()

class PowerPanel(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.selected=None;self.signature=None;self.pending_model=None
        box=wx.BoxSizer(wx.VERTICAL);row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS&~wx.EXTEND_LAST_ON_EACH_LINE)
        def btn(label,fn):
            b=wx.Button(self,label=label);b.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(fn));row.Add(b,0,wx.ALL,3)
        btn('Add supply',lambda:self.add('source'));btn('Add converter',lambda:self.add('converter'));btn('Add load',lambda:self.add('load'))
        btn('Delete selected',self.delete);btn('Fit tree',self.reset_view);btn('Compile to circuit…',self.compile)
        btn('Export budgets…',self.export);self.maximum=wx.CheckBox(self,label='Maximum demand');self.maximum.Bind(wx.EVT_CHECKBOX,lambda e:self.update_report());row.Add(self.maximum,0,wx.ALL,7);box.Add(row,0,wx.EXPAND)
        note=wx.StaticText(self,label='Budgets are NOT simulation results. Converters need real .SUBCKT files to compile. Review imported pin bindings. Compilation uses typical load currents; Maximum demand changes only the budget report.');note.Wrap(1000);box.Add(note,0,wx.ALL,6)
        split=wx.SplitterWindow(self);self.canvas=PowerCanvas(self,split);form=wx.ScrolledWindow(split);form.SetScrollRate(0,12);fbox=wx.BoxSizer(wx.VERTICAL)
        self.list=wx.Choice(form);self.list.Bind(wx.EVT_CHOICE,lambda e:self.select_stage(self.list_ids[self.list.GetSelection()]));fbox.Add(self.list,0,wx.EXPAND|wx.ALL,8)
        grid=wx.FlexGridSizer(cols=2,hgap=7,vgap=7);grid.AddGrowableCol(1,1);self.fields={}
        specs=[('name','Stage name'),('voltage_v','Nominal output [V]'),('current_a','Load typical [A]'),('max_current_a','Load maximum [A]'),('efficiency','Efficiency [0..1]'),('quiescent_a','Input quiescent [A]'),('limit_a','Output limit [A]')]
        for key,label in specs:
            grid.Add(wx.StaticText(form,label=label),0,wx.ALIGN_CENTER_VERTICAL);control=wx.TextCtrl(form);grid.Add(control,1,wx.EXPAND);self.fields[key]=control
        grid.Add(wx.StaticText(form,label='Upstream stage'));self.parent_choice=wx.Choice(form);grid.Add(self.parent_choice,1,wx.EXPAND)
        fbox.Add(grid,0,wx.EXPAND|wx.ALL,8);self.model_label=wx.StaticText(form,label='No model');fbox.Add(self.model_label,0,wx.ALL,8)
        attach=wx.Button(form,label='Attach / replace .SUBCKT file…');attach.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.attach));fbox.Add(attach,0,wx.EXPAND|wx.ALL,5)
        detach=wx.Button(form,label='Detach model');detach.Bind(wx.EVT_BUTTON,lambda e:(setattr(self,'pending_model',None),self.describe_model()));fbox.Add(detach,0,wx.EXPAND|wx.ALL,5)
        fbox.Add(wx.StaticText(form,label='Ordered port bindings (JSON)\n{in} = parent rail; {out} = this rail; {gnd} = 0'),0,wx.ALL,8)
        self.bindings=wx.TextCtrl(form,style=wx.TE_MULTILINE,size=(-1,75));fbox.Add(self.bindings,0,wx.EXPAND|wx.ALL,8)
        apply=wx.Button(form,label='Apply stage');apply.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.apply));fbox.Add(apply,0,wx.EXPAND|wx.ALL,8)
        form.SetSizer(fbox);split.SplitVertically(self.canvas,form,620);split.SetMinimumPaneSize(270);box.Add(split,1,wx.EXPAND)
        self.report=wx.TextCtrl(self,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,105));box.Add(self.report,0,wx.EXPAND|wx.ALL,6);self.SetSizer(box)
    def refresh(self):
        tree=self.owner.doc.data['power_tree'];signature=repr(tree)
        if signature==self.signature:return
        self.signature=signature;self.list_ids=[s['id'] for s in tree['stages']];self.list.Set([s['name'] for s in tree['stages']])
        self.selected=self.selected if self.selected in self.list_ids else self.list_ids[0] if self.list_ids else None
        if self.selected:self.select_stage(self.selected)
        self.update_report()
    def select_stage(self,ident):
        self.selected=ident;stage=next(s for s in self.owner.doc.data['power_tree']['stages'] if s['id']==ident)
        self.list.SetSelection(self.list_ids.index(ident))
        for key,control in self.fields.items():control.SetValue(str(stage[key]))
        for key in ('current_a','max_current_a'):self.fields[key].Enable(stage['kind']=='load')
        for key in ('voltage_v','efficiency','quiescent_a'):self.fields[key].Enable(stage['kind']!='load')
        if stage['kind']=='load':self.fields['voltage_v'].SetValue(str(next(s['voltage_v'] for s in self.owner.doc.data['power_tree']['stages'] if s['id']==stage['parent'])))
        candidates=[s for s in self.owner.doc.data['power_tree']['stages'] if s['id']!=ident and s['kind']!='load'];self.parent_ids=[None]+[s['id'] for s in candidates]
        self.parent_choice.Set(['(root supply)']+[s['name'] for s in candidates]);self.parent_choice.SetSelection(self.parent_ids.index(stage['parent']));self.parent_choice.Enable(stage['kind']!='source')
        self.pending_model=deepcopy(stage['model']);self.describe_model();self.canvas.Refresh()
    def describe_model(self):
        model=self.pending_model;self.model_label.SetLabel(('Model '+model['name']+' · ports: '+', '.join(model['ports'])) if model else 'No attached subcircuit')
        self.model_label.Wrap(290);self.bindings.SetValue(json.dumps(model['bindings']) if model else '[]')
        self.bindings.Enable(bool(model))
    def add(self,kind):
        parent=self.selected if kind!='source' else None
        stage=new_stage(kind,parent);tree=deepcopy(self.owner.doc.data['power_tree']);tree['stages'].append(stage);validate(tree)
        self.selected=stage['id'];self.owner.doc.commit(lambda d:d.__setitem__('power_tree',tree));self.owner.refresh_document();self.reset_view()
    def apply(self):
        if not self.selected:raise ValueError('Select a stage first')
        tree=deepcopy(self.owner.doc.data['power_tree']);s=next(s for s in tree['stages'] if s['id']==self.selected)
        for key,control in self.fields.items():s[key]=control.GetValue() if key=='name' else float(control.GetValue())
        s['parent']=self.parent_ids[self.parent_choice.GetSelection()];s['model']=deepcopy(self.pending_model)
        if s['model']:s['model']['bindings']=json.loads(self.bindings.GetValue())
        validate(tree);self.owner.doc.commit(lambda d:d.__setitem__('power_tree',tree));self.owner.refresh_document()
    def attach(self):
        if not self.selected:raise ValueError('Select a stage first')
        path=self.owner.choose_path('Attach a self-contained SPICE subcircuit','SPICE model|*.cir;*.lib;*.sp;*.sub;*.txt|All files|*.*')
        if path:self.pending_model=read_model(path);self.describe_model()
    def delete(self):
        if not self.selected:raise ValueError('Select a stage')
        tree=deepcopy(self.owner.doc.data['power_tree'])
        if any(s['parent']==self.selected for s in tree['stages']):raise ValueError('Reparent or delete child stages first')
        tree['stages']=[s for s in tree['stages'] if s['id']!=self.selected];self.owner.doc.commit(lambda d:d.__setitem__('power_tree',tree));self.owner.refresh_document()
    def update_report(self):
        data=budgets(self.owner.doc.data['power_tree'],self.maximum.GetValue());self.report.SetValue(data['basis']+f"\n{data['case']}: total input {data['total_input_w']:.6g} W · conversion losses {data['conversion_loss_w']:.6g} W\n"+'\n'.join(s['name']+' exceeds declared output-current limit' for s in self.owner.doc.data['power_tree']['stages'] if data['stages'][s['id']]['over_limit']))
        self.canvas.Refresh()
    def reset_view(self):
        stages=self.owner.doc.data['power_tree']['stages'];by_id={s['id']:s for s in stages};rows={}
        for stage in stages:
            depth=0;parent=stage['parent']
            while parent:depth+=1;parent=by_id[parent]['parent']
            rows[depth]=rows.get(depth,0)+1
        width=max(rows,default=0)*265+225;height=max(rows.values(),default=1)*140
        size=self.canvas.GetClientSize();self.canvas.zoom=max(.3,min(1.3,(size.width-60)/width,(size.height-60)/height))
        self.canvas.offset=[30.,30.];self.canvas.Refresh()
    def compile(self):
        self.owner.require_clean_directive_source();source=compile_tree(self.owner.doc.data['power_tree'])
        if wx.MessageBox('Replace the current circuit with the compiled power tree? This is undoable. The tree stays in this project.','Compile real stage models',wx.YES_NO|wx.NO_DEFAULT,self)!=wx.YES:return
        self.owner.doc.apply_source(source);self.owner.refresh_document(force_source=True);self.owner.book.SetSelection(2)
    def export(self):
        path=self.owner.choose_path('Export declared power budget','JSON|*.json',True)
        if path:write_json(path,{'tree':self.owner.doc.data['power_tree'],'typical':budgets(self.owner.doc.data['power_tree']),'maximum':budgets(self.owner.doc.data['power_tree'],True)})
