# SPDX-License-Identifier: Apache-2.0
"""Explicit package-pin mapping for native manufacturer approximations."""
from __future__ import annotations

import uuid
import wx

from .manufacturer_executable import prepare_install, source_pins
from .themes import apply_window


class ExecutablePlacementDialog(wx.Dialog):
    """Map every documented package pin before expanding an owned native macro."""

    def __init__(self, parent, owner, record):
        super().__init__(
            parent,
            title="Place executable manufacturer approximation",
            size=(690, 610),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.owner = owner
        self.record = record
        self.SetMinSize((620, 520))
        box = wx.BoxSizer(wx.VERTICAL)
        note = wx.StaticText(
            self,
            label=(
                f"{record['manufacturer']} {record['part_number']}\n"
                "Part-specific SPIKE approximation · native backend · qualified: false\n"
                "Placement retains the full X-instance pin mapping in circuit source, then shows the\n"
                "expanded native equivalent circuit on the canvas. It does not create a compact package glyph."
            ),
        )
        note.Wrap(630)
        box.Add(note, 0, wx.ALL | wx.EXPAND, 12)

        book = wx.Notebook(self)
        box.Add(book, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 12)
        pins_page = wx.ScrolledWindow(book)
        pins_page.SetScrollRate(0, 12)
        pins_box = wx.BoxSizer(wx.VERTICAL)
        pins_page.SetSizer(pins_box)
        grid = wx.FlexGridSizer(cols=2, hgap=10, vgap=8)
        grid.AddGrowableCol(1)
        self.nodes = {}
        self.pin_labels = []
        prefix = "manufacturer_" + uuid.uuid4().hex[:8] + "_{n}_"
        pin_by_name = {pin["name"]: pin for pin in record["pins"]}
        for name in source_pins(record):
            pin = pin_by_name[name]
            label = wx.StaticText(
                pins_page,
                label=f"Pin {pin['number']} · {name} ({pin['role']}) → net",
            )
            control = wx.TextCtrl(pins_page, value=prefix + name.lower())
            self.pin_labels.append(label)
            self.nodes[name] = control
            grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 1, wx.EXPAND)
        pins_box.Add(grid, 0, wx.ALL | wx.EXPAND, 12)
        hint = wx.StaticText(
            pins_page,
            label=(
                "Every package pin is required and order is fixed. No supply, ground, reference, or unused pin is guessed.\n"
                "{n} isolates multiple instances; names without {n} intentionally share a net. Ground is 0."
            ),
        )
        hint.Wrap(610)
        pins_box.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)
        book.AddPage(pins_page, "Package pins", True)

        limits_page = wx.Panel(book)
        limits_box = wx.BoxSizer(wx.VERTICAL)
        limits_page.SetSizer(limits_box)
        limits = (
            f"Valid use\n{record['validity']['operating_conditions']}\n\n"
            "Limitations\n" + "\n".join("• " + item for item in record["validity"]["limitations"]) +
            f"\n\nOfficial source\n{record['source']['url']}"
        )
        limits_box.Add(
            wx.TextCtrl(limits_page, value=limits, style=wx.TE_MULTILINE | wx.TE_READONLY),
            1,
            wx.ALL | wx.EXPAND,
            8,
        )
        book.AddPage(limits_page, "Validity and source")
        pins_page.FitInside()

        count_row = wx.BoxSizer(wx.HORIZONTAL)
        count_row.Add(wx.StaticText(self, label="Instances"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 8)
        self.count = wx.SpinCtrl(self, min=1, max=100, initial=1)
        count_row.Add(self.count, 0, wx.ALL, 8)
        box.Add(count_row, 0, wx.LEFT | wx.RIGHT, 8)
        self.error = wx.StaticText(self, label="")
        box.Add(self.error, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 12)
        buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        self.FindWindow(wx.ID_OK).SetLabel("Insert expanded native circuit")
        self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON, self.accept)
        box.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 12)
        self.SetSizer(box)
        apply_window(self, owner.palette)
        self.CentreOnParent()

    def mapping(self):
        return {name: control.GetValue() for name, control in self.nodes.items()}

    def accept(self, event=None):
        try:
            prepare_install(self.owner.doc, self.record, self.mapping(), count=self.count.GetValue())
            self.EndModal(wx.ID_OK)
        except (ValueError, KeyError, TypeError) as error:
            self.error.SetLabel(str(error))
            self.error.Wrap(620)
            self.Layout()


__all__ = ["ExecutablePlacementDialog"]
