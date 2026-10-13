# SPDX-License-Identifier: Apache-2.0
"""Text/directive classification and transactional canvas placement."""
from copy import deepcopy
from .directives import valid_text, OFF


def classify(text,enabled=True):
    if not isinstance(text,str) or not text.strip() or len(text)>65536:raise ValueError('Enter text (maximum 64 KiB)')
    lines=text.strip().splitlines();first=lines[0].strip()
    disabled=first.startswith(OFF) or first.startswith('*') and first[1:].lstrip().startswith('.')
    if disabled:
        lines=[line.strip()[len(OFF):] if line.strip().startswith(OFF) else line.strip()[1:].lstrip() if line.strip().startswith('*') else line.strip() for line in lines]
        enabled=False
    if not lines[0].lstrip().startswith('.'):
        if len(text)>8192:raise ValueError('Canvas notes are limited to 8192 characters')
        return dict(kind='note',text=text.strip(),enabled=False)
    cards=[]
    for line in lines:
        line=line.strip()
        if not line:continue
        if line.startswith('+') and cards:cards[-1]+='\n'+line
        elif line.startswith('.'):cards.append(line)
        else:raise ValueError('Directive blocks contain dot commands and + continuation lines only')
    return dict(kind='directives',cards=[valid_text(card) for card in cards],enabled=bool(enabled))


def place(doc,text,position,enabled=True):
    from .document import Document
    entry=classify(text,enabled)
    candidate=Document(doc.data);x,y=map(float,position);ids=[]
    if entry['kind']=='note':
        ids.append(candidate.edit_annotation(x=x,y=y,text=entry['text'],width=240,height=max(70,24*len(entry['text'].splitlines()))))
    else:
        for index,card in enumerate(entry['cards']):
            ids.append(candidate.edit_directive(text=card,enabled=entry['enabled'],x=x,y=y+85*index))
    doc.commit(lambda data:data.update(deepcopy(candidate.data)))
    return ids


def show(owner,position=None):
    import wx
    from .flat_controls import ActionButton
    from .themes import apply_window
    owner.require_clean_directive_source()
    with wx.Dialog(owner,title='Canvas text / SPICE · T',size=(660,440),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
        box=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(dialog,label='Dot-prefixed text is executable SPICE. Other text is a note.\nMultiple top-level directives are placed as one block. * .command starts commented out.')
        note.Wrap(610);box.Add(note,0,wx.ALL,12)
        text=wx.TextCtrl(dialog,style=wx.TE_MULTILINE);text.SetName('Canvas text or SPICE block');box.Add(text,1,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        enabled=wx.CheckBox(dialog,label='Enable SPICE commands (uncheck to comment out)');enabled.SetValue(True);box.Add(enabled,0,wx.ALL,12)
        error=wx.StaticText(dialog,label='');box.Add(error,0,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        row=wx.BoxSizer(wx.HORIZONTAL)
        cancel=ActionButton(dialog,label='Cancel');cancel.Bind(wx.EVT_BUTTON,lambda event:dialog.EndModal(wx.ID_CANCEL));row.Add(cancel,0,wx.ALL,5)
        accept=ActionButton(dialog,label='Validate / place');row.Add(accept,0,wx.ALL,5);box.Add(row,0,wx.ALIGN_RIGHT|wx.ALL,7)
        def apply(event):
            try:
                # Validate source parsing in an isolated document before arming placement.
                from .document import Document
                place(Document(owner.doc.data),text.GetValue(),position or (100,420),enabled.GetValue())
                dialog.EndModal(wx.ID_OK)
            except Exception as exc:error.SetLabel(str(exc));error.Wrap(610);dialog.Layout()
        accept.Bind(wx.EVT_BUTTON,apply);dialog.SetSizer(box);apply_window(dialog,owner.palette);dialog.CentreOnParent()
        if dialog.ShowModal()!=wx.ID_OK:return
        payload=dict(canvas_text=text.GetValue(),enabled=enabled.GetValue())
    if position is not None:owner.place_designer_tool(payload,position)
    else:
        owner.canvas.plot_drop=None;owner.canvas.wire_mode=False;owner.canvas.probe_mode=None
        owner.canvas.designer_tool=payload;owner.book.SetSelection(owner.editor_page())
        owner.canvas.SetCursor(wx.Cursor(wx.CURSOR_CROSS));owner.canvas.SetFocus()
        owner.SetStatusText('Click schematic to place text / directive block. Escape cancels.')
