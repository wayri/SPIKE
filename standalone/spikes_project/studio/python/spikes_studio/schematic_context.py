# SPDX-License-Identifier: Apache-2.0
"""Grouped schematic menus reuse command availability and clicked geometry."""
from .context_menus import ContextMenu


def build(canvas,event,point):
    owner=canvas.owner;menu=ContextMenu(owner)
    def command(target,ident):
        spec=owner.commands.commands[ident];reason=owner.commands.reason(ident);key=owner.keymap.bindings.get(ident,'')
        target.add(spec.label+('\t'+key if key else ''),lambda:owner.commands.execute(ident),not reason,reason or spec.description)
    selected=next((p for p in owner.doc.data['components'] if p['id'] in canvas.selected),None)
    if selected:
        title=menu.menu.Append(-1,f"{selected['ref']} - {len(canvas.selected)} selected");title.Enable(False)
        command(menu,'edit.properties');menu.separator()
    edit=menu.submenu('Edit / selection')
    for ident in ('edit.undo','edit.redo','edit.copy','edit.paste','edit.select_all','edit.box_select','edit.lasso_select'):command(edit,ident)
    transform=menu.submenu('Move / transform')
    for ident in ('edit.move','edit.drag','edit.rotate','edit.mirror_horizontal','edit.mirror_vertical'):command(transform,ident)
    place=menu.submenu('Place / annotate')
    command(place,'edit.wire');command(place,'view.component_catalog')
    place.add('Text / SPICE block here…\tT',lambda:owner.canvas_text(point))
    for label,kind in [('Note…','note'),('Rectangle','rect'),('Ellipse','ellipse')]:place.add(label,lambda k=kind:owner.place_designer_tool({'annotation':k},point))
    place.add('SPICE directive here…',lambda:owner.edit_directive(position=point))
    probes=menu.submenu('Probe / instruments')
    for ident in ('probe.voltage','probe.differential','probe.current','probe.power'):command(probes,ident)
    probes.add('Schematic readouts / mini plots…',owner.manage_instruments)
    attachment=canvas.plot_attachment(event.GetPosition())
    if attachment:
        from .net_labels import show as label_show
        probes.add('Attach scoped net label here…',lambda:label_show(owner,attachment))
        def attach():
            import wx
            canvas.plot_drop=attachment;canvas.SetCursor(wx.Cursor(wx.CURSOR_CROSS));owner.SetStatusText('Click where the attached plot should appear. Escape cancels.')
        probes.add('Drop mini plot attached here…',attach)
    view=menu.submenu('View / navigation')
    view.add('Wire hops',owner.toggle_wire_hops,checked=owner.doc.data['metadata'].get('wire_hops',False))
    for ident in ('view.fit_schematic','view.net_navigator','view.hierarchy','view.parent_sheet','view.flat_schematic','view.code_canvas','view.split_side_by_side','view.split_top_bottom','view.directives'):command(view,ident)
    if selected and ':' in selected['ref']:
        from .hierarchy_views import open_sheet
        menu.add('Open containing subsheet',lambda:open_sheet(owner,selected['ref'].rpartition(':')[0]))
    if selected:
        from .schematic_feedback import configure_control
        menu.add('Configure direct click control…',lambda:configure_control(owner,selected))
    from .editor_geometry import nearest_route_point,route
    parts={p['id']:p for p in owner.doc.data['components']};junctions={j['id']:j for j in owner.doc.data['junctions']}
    wire=next((w for w in canvas.visible_wires() if nearest_route_point(route(parts,w,junctions),point)[2]<=10/canvas.zoom),None)
    if wire:
        from .junction_edit import show as add_junction
        menu.add('Add junction on clicked wire',lambda:add_junction(owner,wire,point),not owner.job_running,'Stop simulation before editing wiring')
        from .wire_models import edit as wire_edit
        menu.add('Clicked wire: hidden R / L / C…',lambda:wire_edit(owner,wire))
    return menu
