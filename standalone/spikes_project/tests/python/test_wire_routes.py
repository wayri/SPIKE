from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document
from spikes_studio.editor_geometry import orthogonal_path,route,snap,terminal,wire_preview


class WireRoutes(unittest.TestCase):
    def test_corner_route_move_undo_preserves_electrical_source(self):
        d=Document.from_netlist('Route\nV1 a 0 1\nR1 b 0 1k\n.op\n.end\n')
        a,b=d.data['components'];d.connect((a['id'],0),(b['id'],0),[[50,50],[300,50]])
        wire=d.data['wires'][0];parts={p['id']:p for p in d.data['components']};points=route(parts,wire)
        self.assertEqual(points[0],terminal(parts[a['id']],0));self.assertEqual(points[-1],terminal(parts[b['id']],0))
        self.assertTrue(all(p[0]==q[0] or p[1]==q[1] for p,q in zip(points,points[1:])))
        source=d.data['source'];d.move_wire_route(wire['id'],20,30)
        self.assertEqual(d.data['source'],source);self.assertNotEqual(route(parts,d.data['wires'][0]),points)
        d.undo();self.assertEqual(route(parts,d.data['wires'][0]),points)
        self.assertEqual(Document(d.data).data['wires'],d.data['wires'])

    def test_invalid_corners_are_atomic(self):
        d=Document.from_netlist('Route\nV1 a 0 1\nR1 b 0 1k\n.op\n.end\n')
        a,b=d.data['components'];source=d.data['source']
        with self.assertRaises(ValueError):d.connect((a['id'],0),(b['id'],0),[[float('nan'),2]])
        self.assertEqual(d.data['source'],source);self.assertFalse(d.data['wires'])
        with self.assertRaises(ValueError):d.connect((a['id'],0),(b['id'],0),bend='diagonal')
        self.assertEqual(d.data['source'],source);self.assertFalse(d.data['wires'])

    def test_wire_posture_and_grid_snap_are_deterministic(self):
        self.assertEqual(snap((14.9,-15.0)),(10.0,-20.0))
        horizontal=orthogonal_path((0,0),[(20,30)],'horizontal')
        vertical=orthogonal_path((0,0),[(20,30)],'vertical')
        self.assertEqual(horizontal,[(0,0),(20,0),(20,30)])
        self.assertEqual(vertical,[(0,0),(0,30),(20,30)])
        d=Document.from_netlist('Bend\nV1 a 0 1\nR1 b 0 1k\n.op\n.end\n')
        a,b=d.data['components'];d.connect((a['id'],0),(b['id'],0),[[250,260]],bend='vertical')
        wire=d.data['wires'][0]
        self.assertEqual(wire['bend'],'vertical')
        self.assertTrue(wire['manual'])
        self.assertEqual(Document(d.data).data['wires'][0]['bend'],'vertical')

    def test_terminal_latched_preview_is_the_committed_route(self):
        d=Document.from_netlist('Preview\nV1 a 0 1\nR1 b 0 1k\n.op\n.end\n')
        a,b=d.data['components'];d.move({b['id']:(340,300)})
        parts={p['id']:p for p in d.data['components']};start=(a['id'],0);target=(b['id'],0)
        preview=wire_preview(parts,start,[],(999,999),'vertical',target)
        d.connect(start,target,bend='vertical')
        committed=route({p['id']:p for p in d.data['components']},d.data['wires'][0])
        self.assertEqual(preview,committed)
        horizontal=wire_preview(parts,start,[],(999,999),'horizontal',target)
        self.assertNotEqual(horizontal,preview)

    def test_drag_preserves_route_bends_while_move_re_routes(self):
        d=Document.from_netlist('Move semantics\nV1 a 0 1\nR1 b 0 1k\n.op\n.end\n')
        a,b=d.data['components'];d.connect((a['id'],0),(b['id'],0),[[80,80],[280,80]])
        source=d.data['source'];original=list(map(list,d.data['wires'][0]['waypoints']))
        d.move({a['id']:(a['x']+40,a['y']+20)},preserve_routes=True)
        self.assertTrue(d.data['wires'][0]['waypoints'])
        self.assertNotEqual(d.data['wires'][0]['waypoints'],original)
        self.assertEqual(d.data['source'],source)
        d.undo();a=next(p for p in d.data['components'] if p['id']==a['id'])
        d.move({a['id']:(a['x']+40,a['y']+20)},preserve_routes=False)
        self.assertEqual(d.data['wires'][0]['waypoints'],[])
        self.assertEqual(d.data['source'],source)

    def test_dragging_a_group_translates_its_route(self):
        d=Document.from_netlist('Group drag\nV1 a 0 1\nR1 b 0 1k\n.op\n.end\n')
        a,b=d.data['components'];d.connect((a['id'],0),(b['id'],0),[[80,80],[280,80]])
        old=list(map(tuple,d.data['wires'][0]['waypoints']))
        d.move({a['id']:(a['x']+30,a['y']-10),b['id']:(b['x']+30,b['y']-10)},preserve_routes=True)
        self.assertEqual(list(map(tuple,d.data['wires'][0]['waypoints'])),[(x+30,y-10) for x,y in old])

    def test_branch_splits_wire_into_explicit_source_bound_junction(self):
        d=Document.from_netlist('Branch\nV1 a 0 1\nR1 b 0 1k\nR2 c 0 2k\n.op\n.end\n')
        source,left,target=d.data['components'];d.connect((source['id'],0),(left['id'],0),[[80,100],[280,100]])
        before_branch=d.data['source'];wire=d.data['wires'][0]
        ident=d.branch(wire['id'],(180,100),(target['id'],0),[[340,100]],tolerance=0)
        self.assertEqual(len(d.data['junctions']),1);junction=d.data['junctions'][0]
        self.assertEqual(junction['id'],ident);self.assertEqual(junction['source_terminal'],[source['id'],0])
        self.assertEqual(junction['source_node'],'a');self.assertEqual((junction['x'],junction['y']),(180,100))
        self.assertEqual(len(d.data['wires']),3)
        self.assertEqual(sum([ident] in (w['a'],w['b']) for w in d.data['wires']),3)
        self.assertEqual({p['nodes'][0] for p in d.data['components']},{'a'})
        junctions={ident:junction};parts={p['id']:p for p in d.data['components']}
        for branch in d.data['wires']:
            points=route(parts,branch,junctions)
            self.assertEqual(points[0] if branch['a']==[ident] else points[-1] if branch['b']==[ident] else None,(180,100) if [ident] in (branch['a'],branch['b']) else None)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'branch.spksch';d.save(path);restored=Document.load(path)
            self.assertEqual(restored.data['junctions'],d.data['junctions']);restored.validate()
        d.undo();self.assertFalse(d.data['junctions']);self.assertEqual(len(d.data['wires']),1)
        self.assertEqual(d.data['source'],before_branch)

    def test_unsafe_branch_is_failure_atomic(self):
        d=Document.from_netlist('Guarded branch\n.global rail\nV1 a 0 1\nR1 a 0 1k\nR2 c 0 2k\n.op\n.end\n')
        source,left,target=d.data['components'];d.connect((source['id'],0),(left['id'],0),[[80,100],[280,100]])
        before=d.data.copy();wire=d.data['wires'][0]
        with self.assertRaisesRegex(ValueError,'hierarchy/includes/node directives'):
            d.branch(wire['id'],(180,100),(target['id'],0),tolerance=0)
        self.assertEqual(d.data,before)

    def test_crossings_stay_distinct_without_an_explicit_junction(self):
        d=Document.from_netlist('Crossing\nV1 a 0 1\nR1 a 0 1k\nV2 b 0 2\nR2 b 0 2k\n.op\n.end\n')
        a,b,c,e=d.data['components']
        d.connect((a['id'],0),(b['id'],0),[[200,100]])
        d.connect((c['id'],0),(e['id'],0),[[200,100]])
        self.assertFalse(d.data['junctions'])
        self.assertEqual([p['nodes'][0] for p in d.data['components']],['a','a','b','b'])

    def test_junction_source_terminal_identity_survives_pin_transforms(self):
        d=Document.from_netlist('Transform\nV1 a 0 1\nR1 b 0 1k\nR2 c 0 2k\n.op\n.end\n')
        source,left,target=d.data['components'];d.connect((source['id'],0),(left['id'],0),[[80,100],[280,100]])
        ident=d.branch(d.data['wires'][0]['id'],(180,100),(target['id'],0),tolerance=0)
        position=(d.data['junctions'][0]['x'],d.data['junctions'][0]['y'])
        d.rotate([source['id']]);d.mirror([source['id']],'horizontal');d.validate()
        junction=d.data['junctions'][0]
        self.assertEqual(junction['id'],ident);self.assertEqual(junction['source_terminal'],[source['id'],0])
        self.assertEqual((junction['x'],junction['y']),position)

    def test_source_reconciliation_updates_junction_node_without_reidentifying_pins(self):
        d=Document.from_netlist('Reconcile\nV1 a 0 1\nR1 b 0 1k\nR2 c 0 2k\n.op\n.end\n')
        source,left,target=d.data['components'];d.connect((source['id'],0),(left['id'],0),[[80,100],[280,100]])
        ident=d.branch(d.data['wires'][0]['id'],(180,100),(target['id'],0),tolerance=0)
        d.apply_source('Reconcile\nV1 z 0 1\nR1 z 0 1k\nR2 z 0 2k\n.op\n.end\n')
        self.assertEqual(d.data['junctions'][0]['id'],ident)
        self.assertEqual(d.data['junctions'][0]['source_terminal'],[source['id'],0])
        self.assertEqual(d.data['junctions'][0]['source_node'],'z')
        self.assertEqual(len(d.data['wires']),3);d.validate()
