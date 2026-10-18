# SPDX-License-Identifier: Apache-2.0
"""Persistent schematic Mini plot attachment contract checks."""
import sys
from pathlib import Path
import unittest


ROOT=Path(__file__).resolve().parents[2]
STUDIO=ROOT/'studio'/'python'
if str(STUDIO) not in sys.path:sys.path.insert(0,str(STUDIO))

from spikes_studio.document import Document
from spikes_studio.plot_workspace import (add_attached_plot,attachment_node,
                                          attachment_point,signal_color)


class InstrumentAttachmentTests(unittest.TestCase):
    def document(self):
        return Document.from_netlist("Attachment fixture\nV1 in 0 1\nR1 in out 1k\n.tran 1u 10u\n.end\n")

    def test_terminal_attachment_follows_move_rotation_and_persists(self):
        doc=self.document();part=doc.data['components'][1]
        ident=add_attached_plot(doc,part['id'],0,(400,250))
        item=next(row for row in doc.data['instruments'] if row['id']==ident)
        self.assertEqual(attachment_node(doc,item),'in')
        self.assertEqual(attachment_point(doc,item),(part['x']-55,part['y']))
        doc.move({part['id']:(300,420)})
        self.assertEqual(attachment_point(doc,item),(245.0,420.0))
        doc.rotate([part['id']])
        self.assertEqual(attachment_point(doc,item),(300.0,365.0))
        reopened=Document(doc.data);saved=reopened.data['instruments'][0]
        self.assertEqual((saved['anchor'],saved['pin_index']),(part['id'],0))
        self.assertEqual(attachment_point(reopened,saved),(300.0,365.0))

    def test_exact_wire_point_is_stable_while_card_can_move(self):
        doc=self.document();part=doc.data['components'][1]
        add_attached_plot(doc,part['id'],1,(500,260),attach_point=(222.5,333.25))
        item=doc.data['instruments'][0]
        self.assertEqual(attachment_point(doc,item),(222.5,333.25))
        doc.commit(lambda data:data['instruments'][0].update(x=700.0,y=600.0))
        self.assertEqual(attachment_point(doc,item),(222.5,333.25))
        doc.undo();self.assertEqual(attachment_point(doc,doc.data['instruments'][0]),(222.5,333.25))

    def test_creation_rejects_stale_terminal_without_partial_commit(self):
        doc=self.document();part=doc.data['components'][0];revision=doc.data['revision']
        with self.assertRaisesRegex(ValueError,'existing component terminal'):
            add_attached_plot(doc,part['id'],99,(100,100))
        self.assertEqual(doc.data['instruments'],[]);self.assertEqual(doc.data['revision'],revision)

    def test_color_is_net_deterministic_and_palette_sensitive(self):
        doc=self.document()
        dark={'canvas':'#191c20','accent':'#75a8de'};light={'canvas':'#ffffff','accent':'#2863a2'}
        self.assertEqual(signal_color(doc,'OUT',dark),signal_color(doc,'out',dark))
        self.assertNotEqual(signal_color(doc,'out',dark),signal_color(doc,'out',light))
        self.assertEqual(signal_color(doc,None,dark),dark['accent'])

    def test_legacy_anchor_and_expression_fallbacks_remain_readable(self):
        doc=self.document();part=doc.data['components'][1]
        legacy={'anchor':part['id'],'expression':'V(in)','x':900,'y':700}
        self.assertEqual(attachment_point(doc,legacy),(float(part['x']),float(part['y'])))
        detached={'anchor':'removed','expression':'V(out)','x':900,'y':700}
        self.assertEqual(attachment_node(doc,detached),'out')
        self.assertNotEqual(attachment_point(doc,detached),(900.0,700.0))


if __name__=='__main__':unittest.main()
