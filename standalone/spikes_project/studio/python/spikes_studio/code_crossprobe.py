# SPDX-License-Identifier: Apache-2.0
"""Bounded source-editor styling and schematic cross-probing helpers."""
from __future__ import annotations

import re


MAX_TEXT = 256 * 1024
MAX_TOKENS = 20_000
_TOKEN = re.compile(r"inputs\s*\[\s*\d+\s*\]|outputs\s*\[\s*\d+\s*\]|[A-Za-z0-9_.$:/+\-]+", re.I)


def _data(document):
    value = getattr(document, "data", document)
    return value if isinstance(value, dict) else {}


def _controller_data(controller, document):
    value = controller
    if value is None:
        value = _data(document).get("controller_setup")
    value = getattr(value, "config", value)
    return value if isinstance(value, dict) else {}


def resolve_references(text, doc, controller=None):
    """Resolve exact, case-insensitive source tokens without changing inputs.

    Returned component values are stable document component IDs. Controller
    pin values are pin names. Malformed document fragments are ignored.
    """
    if not isinstance(text, str):
        return {"nets": set(), "components": set(), "pins": set()}
    text = text[:MAX_TEXT]
    tokens = [match.group(0) for match in _TOKEN.finditer(text)]
    if len(tokens) > MAX_TOKENS:
        tokens = tokens[:MAX_TOKENS]
    plain = {re.sub(r"\s+", "", token).casefold() for token in tokens}

    components = [part for part in _data(doc).get("components", []) if isinstance(part, dict)]
    refs = {}
    nodes = {}
    by_ref = {}
    for part in components:
        ident, ref = part.get("id"), part.get("ref")
        if isinstance(ref, str) and isinstance(ident, str):
            refs.setdefault(ref.casefold(), set()).add(ident)
            by_ref[ref.casefold()] = part
        for node in part.get("nodes", []):
            if isinstance(node, str):
                nodes.setdefault(node.casefold(), node)
    found_components = set().union(*(refs.get(token, set()) for token in plain)) if plain else set()
    found_nets = {canonical for folded, canonical in nodes.items() if folded in plain}

    config = _controller_data(controller, doc)
    pins = [pin for pin in config.get("pins", []) if isinstance(pin, dict)]
    input_pins = [pin for pin in pins if str(pin.get("mode", "")).upper() in ("AI", "DI")]
    output_pins = [pin for pin in pins if str(pin.get("mode", "")).upper() in ("AO", "DO")]
    found_pins = set()
    for index, pin in enumerate(input_pins):
        name = pin.get("name")
        if not isinstance(name, str):
            continue
        endpoints = {str(pin.get(key, "")).casefold() for key in ("node", "reference")}
        if name.casefold() in plain or f"inputs[{index}]" in plain or plain.intersection(endpoints - {""}):
            found_pins.add(name)
            if name.casefold() in plain or f"inputs[{index}]" in plain:
                found_nets.update(nodes[value] for value in endpoints if value in nodes)
    for index, pin in enumerate(output_pins):
        name, source = pin.get("name"), pin.get("source")
        if not isinstance(name, str):
            continue
        endpoints = set()
        if isinstance(source, str):
            endpoints.add(source.casefold())
            part = by_ref.get(source.casefold())
            if part:
                endpoints.update(str(node).casefold() for node in part.get("nodes", []) if isinstance(node, str))
        if name.casefold() in plain or f"outputs[{index}]" in plain or plain.intersection(endpoints):
            found_pins.add(name)
            if name.casefold() in plain or f"outputs[{index}]" in plain:
                found_nets.update(nodes[value] for value in endpoints if value in nodes)
                found_components.update(refs.get(source.casefold(),set()) if isinstance(source,str) else set())
    return {"nets": found_nets, "components": found_components, "pins": found_pins}


_KEYWORDS = {
    "VHDL": "abs access after alias all and architecture array assert attribute begin block body buffer bus case component configuration constant disconnect downto else elsif end entity exit file for function generate generic group guarded if impure in inertial inout is label library linkage literal loop map mod nand new next nor not null of on open or others out package port postponed procedure process pure range record register reject rem report return rol ror select severity shared signal sla sll sra srl subtype then to transport type unaffected units until use variable wait when while with xnor xor",
    "SPICE": ".ac .dc .end .ends .func .global .ic .include .lib .model .nodeset .op .options .param .print .probe .save .step .subckt .temp .tran",
    "C": "auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Bool _Complex _Imaginary",
    "C++": "alignas alignof and and_eq asm auto bitand bitor bool break case catch char char8_t char16_t char32_t class compl concept const consteval constexpr constinit const_cast continue co_await co_return co_yield decltype default delete do double dynamic_cast else enum explicit export extern false float for friend goto if inline int long mutable namespace new noexcept not not_eq nullptr operator or or_eq private protected public register reinterpret_cast requires return short signed sizeof static static_assert static_cast struct switch template this thread_local throw true try typedef typeid typename union unsigned using virtual void volatile wchar_t while xor xor_eq",
    "VERILOG": "always assign automatic begin buf bufif0 bufif1 case casex casez cell cmos config deassign default defparam design disable edge else end endcase endconfig endfunction endgenerate endmodule endprimitive endspecify endtable endtask event for force forever fork function generate genvar highz0 highz1 if ifnone incdir include initial inout input instance integer join large liblist library localparam macromodule medium module nand negedge nmos nor noshowcancelled not notif0 notif1 or output parameter pmos posedge primitive pull0 pull1 pulldown pullup pulsestyle_onevent pulsestyle_ondetect rcmos real realtime reg release repeat rnmos rpmos rtran rtranif0 rtranif1 scalared showcancelled signed small specify specparam strong0 strong1 supply0 supply1 table task time tran tranif0 tranif1 tri tri0 tri1 triand trior trireg unsigned use vectored wait wand weak0 weak1 while wire wor xnor xor",
}


def _colour(value, fallback):
    return value if isinstance(value, str) and value else fallback


def configure_editor(editor, language, palette):
    """Configure a wx.stc editor using built-in lexers and standard styles."""
    import wx
    import wx.stc as stc

    palette = palette or {}
    language = str(language or "").upper()
    language = "C++" if language in ("CPP", "CXX", "C++") else language
    lexer = stc.STC_LEX_SPICE if language == "SPICE" else stc.STC_LEX_VERILOG if language == "VERILOG" else stc.STC_LEX_VHDL if language == "VHDL" else stc.STC_LEX_CPP
    editor.SetLexer(lexer)
    editor.SetKeyWords(0, _KEYWORDS.get(language, _KEYWORDS["C"]))
    fg = _colour(palette.get("fg"), "#202124")
    bg = _colour(palette.get("canvas", palette.get("bg")), "#ffffff")
    muted = _colour(palette.get("muted"), "#687076")
    accent = _colour(palette.get("accent"), "#1769aa")
    string = _colour(palette.get("success"), "#137333")
    editor.StyleSetSpec(stc.STC_STYLE_DEFAULT, f"fore:{fg},back:{bg},face:Consolas,size:10")
    editor.StyleClearAll()
    editor.StyleSetForeground(stc.STC_STYLE_LINENUMBER,wx.Colour(muted))
    editor.StyleSetBackground(stc.STC_STYLE_LINENUMBER,wx.Colour(palette.get('panel',bg)))
    for style in (stc.STC_C_COMMENT, stc.STC_C_COMMENTLINE, stc.STC_C_COMMENTDOC,
                  stc.STC_V_COMMENT, stc.STC_V_COMMENTLINE, stc.STC_V_COMMENTLINEBANG,
                  stc.STC_SPICE_COMMENTLINE):
        editor.StyleSetForeground(style, wx.Colour(muted))
    for style in (stc.STC_C_STRING, stc.STC_C_CHARACTER, stc.STC_V_STRING):
        editor.StyleSetForeground(style, wx.Colour(string))
    for style in (stc.STC_C_NUMBER, stc.STC_V_NUMBER, stc.STC_SPICE_NUMBER):
        editor.StyleSetForeground(style, wx.Colour(accent))
    for style in (stc.STC_C_WORD, stc.STC_C_WORD2, stc.STC_V_WORD, stc.STC_V_WORD2,
                  stc.STC_SPICE_KEYWORD, stc.STC_SPICE_KEYWORD2, stc.STC_SPICE_KEYWORD3):
        editor.StyleSetForeground(style, wx.Colour(accent)); editor.StyleSetBold(style, True)
    editor.IndicatorSetStyle(0, stc.STC_INDIC_ROUNDBOX)
    editor.IndicatorSetForeground(0, wx.Colour(accent))
    editor.IndicatorSetAlpha(0, 45)
    if language=='VHDL':
        for name,color in [('STC_VHDL_COMMENT',muted),('STC_VHDL_COMMENTLINEBANG',muted),('STC_VHDL_STRING',string),('STC_VHDL_NUMBER',accent),('STC_VHDL_KEYWORD',accent)]:
            style=getattr(stc,name,None)
            if style is not None:editor.StyleSetForeground(style,wx.Colour(color))
    return editor


class _CrossProbeBinding:
    def __init__(self, editor, owner, language, controller_provider):
        self.editor, self.owner = editor, owner
        self.language, self.controller_provider = language, controller_provider
        self._later = None
        import wx.stc as stc
        editor.Bind(stc.EVT_STC_UPDATEUI, self._changed)
        import wx
        editor.Bind(wx.EVT_WINDOW_DESTROY,self._destroyed)
        self.refresh()

    def _destroyed(self,event):
        if event.GetEventObject()==self.editor:self.close()
        event.Skip()

    def _changed(self, _event):
        try:
            import wx
            if self._later is not None:
                self._later.Stop()
            self._later = wx.CallLater(60, self.refresh)
        except (RuntimeError, AttributeError):
            pass

    def _selected_source(self):
        selected = self.editor.GetSelectedText()
        if selected:
            self.span=self.editor.GetSelection()
            return selected
        position = self.editor.GetCurrentPos()
        start = self.editor.WordStartPosition(position, True)
        end = self.editor.WordEndPosition(position, True)
        source=self.editor.GetTextRange(start,end)
        if source in ('inputs','outputs'):
            import re
            match=re.match(r'(?:inputs|outputs)\s*\[\s*\d+\s*\]',self.editor.GetTextRange(start,min(self.editor.GetTextLength(),end+24)))
            if match:source=match[0];end=start+len(source)
        self.span=(start,end)
        return source

    def refresh(self, palette=None):
        try:
            if palette is not None:
                configure_editor(self.editor, self.language, palette)
            if not self.editor or not self.owner:
                return
            if not self.editor.HasFocus():return
            try:controller = self.controller_provider() if callable(self.controller_provider) else self.controller_provider
            except (ValueError,TypeError):controller=None
            result = resolve_references(self._selected_source(), self.owner.doc, controller)
            canvas = self.owner.canvas
            canvas.highlighted_nets = set(result["nets"])
            canvas.highlighted_components = set(result["components"])
            canvas.highlighted_controller_pins = set(result["pins"])
            canvas.highlighted_net = next(iter(sorted(result["nets"], key=str.casefold)), None)
            self.editor.SetIndicatorCurrent(0);self.editor.IndicatorClearRange(0,self.editor.GetTextLength())
            if any(result.values()) and self.span[1]>self.span[0]:self.editor.IndicatorFillRange(self.span[0],self.span[1]-self.span[0])
            canvas.Refresh()
        except (RuntimeError, AttributeError, TypeError):
            # A delayed event can legitimately outlive either native window.
            return

    def close(self):
        if self._later is not None:
            try: self._later.Stop()
            except (RuntimeError, AttributeError): pass
        self.editor = self.owner = None


def bind_crossprobe(editor, owner, language, controller_provider=None):
    """Bind live, non-navigating caret/selection cross-highlighting."""
    return _CrossProbeBinding(editor, owner, language, controller_provider)
