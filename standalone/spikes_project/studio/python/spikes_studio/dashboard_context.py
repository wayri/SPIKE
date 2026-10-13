# SPDX-License-Identifier: Apache-2.0
"""Dashboard item-specific editing menus; never controls hardware."""
from copy import deepcopy
import uuid
import wx
from .context_menus import ContextMenu
from .dashboard import snap,update_widget


def duplicate(data,ident):
    result=deepcopy(data);row=deepcopy(next(r for r in result['widgets'] if r['id']==ident))
    row.update(id=uuid.uuid4().hex,x=min(20000,row['x']+20),y=min(20000,row['y']+20));result['widgets'].append(row)
    return result,row['id']


def build(panel,row):
    owner=panel.owner;menu=ContextMenu(owner);design=panel.mode=='Design';selected=row is not None
    menu.add('Dashboard design mode',lambda:set_mode(panel,'Design'),checked=design)
    menu.add('Dashboard run mode',lambda:set_mode(panel,'Run'),checked=not design)
    menu.separator()
    if selected:
        title=menu.menu.Append(wx.ID_ANY,(row['title'] or row['kind'])[:60]);title.Enable(False)
        def properties():
            panel.inspector_button.SetValue(True);panel.toggle_inspector();panel.fields['title'].SetFocus()
        menu.add('Properties / bindings…',properties,design,'Properties are editable in Design mode')
        menu.add('Duplicate item',lambda:duplicate_selected(panel),design,'Switch to Design mode')
        menu.add('Connect to another item…',panel.begin_connect,design,'Switch to Design mode')
        menu.add('Remove attached connectors',panel.unlink,design and any(row['id'] in (c['from'],c['to']) for c in panel.data().get('connections',[])),'No attached connectors, or not in Design mode')
        arrange=menu.submenu('Arrange')
        arrange.add('Bring to front',lambda:reorder(panel,True),design)
        arrange.add('Send to back',lambda:reorder(panel,False),design)
        arrange.add('Snap to grid',lambda:panel.commit(update_widget(panel.data(),row['id'],x=snap(row['x']),y=snap(row['y']))),design)
        menu.add('DUT pin mapping (disconnected)…',panel.map_dut,design,'Data-only draft; no hardware access')
        if row['kind']=='Source control':
            from .run_control import InteractiveRun
            session=owner.active_run
            live=not design and isinstance(session,InteractiveRun) and session.state in ('running','paused')
            menu.add('Apply entered simulation value',panel.command,live,'Requires Run mode and an active continuous simulation')
        menu.add('Delete item\tDel',panel.delete,design,'Switch to Design mode')
        menu.separator()
    add=menu.submenu('Add instrument / diagram')
    from .dashboard import INSTRUMENT_ACTIONS
    for kind,label,tooltip in INSTRUMENT_ACTIONS:add.add(label,lambda k=kind:panel.add(k),design,tooltip)
    menu.separator()
    menu.add('Undo dashboard / project edit\tCtrl+Z',lambda:(owner.doc.undo(),owner.refresh_document()),bool(owner.doc.undo_stack))
    menu.add('Redo dashboard / project edit\tCtrl+Y',lambda:(owner.doc.redo(),owner.refresh_document()),bool(owner.doc.redo_stack))
    menu.add('Show inspector',lambda:toggle_inspector(panel),checked=panel.inspector_button.GetValue())
    return menu


def set_mode(panel,mode):panel.mode_choice.SetStringSelection(mode);panel.change_mode()
def toggle_inspector(panel):panel.inspector_button.SetValue(not panel.inspector_button.GetValue());panel.toggle_inspector()
def duplicate_selected(panel):
    data,ident=duplicate(panel.data(),panel.selected);panel.commit(data);panel.select(next(r for r in panel.data()['widgets'] if r['id']==ident))
def reorder(panel,front):
    data=deepcopy(panel.data());row=next(r for r in data['widgets'] if r['id']==panel.selected);data['widgets'].remove(row)
    data['widgets'].append(row) if front else data['widgets'].insert(0,row);panel.commit(data)


def context(panel,event):
    screen=event.GetPosition()
    if screen!=wx.DefaultPosition:
        position=panel.canvas.ScreenToClient(screen);point=panel.canvas.CalcUnscrolledPosition(position)
        row=next((r for r in reversed(panel.data()['widgets']) if wx.Rect(int(r['x']),int(r['y']),int(r['width']),int(r['height'])).Contains(point)),None)
        panel.select(row)
    panel.connect_from=None;build(panel,panel.selected_row()).popup(panel.canvas)
