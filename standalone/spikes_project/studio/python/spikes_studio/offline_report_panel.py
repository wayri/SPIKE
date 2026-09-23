"""Offline read-only WebView; never expose arbitrary browser callbacks to Python."""
from pathlib import Path
import tempfile
import wx


class OfflineReportPanel(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.report=None;self.generation=0
        self._temporary=tempfile.TemporaryDirectory(prefix='spikes-report-')
        self.report_path=Path(self._temporary.name)/'report.html'
        box=wx.BoxSizer(wx.VERTICAL);bar=wx.BoxSizer(wx.HORIZONTAL)
        self.refresh_button=wx.Button(self,label='Refresh acquired snapshot')
        self.export_button=wx.Button(self,label='Export offline HTML…');self.export_button.Disable()
        bar.Add(self.refresh_button,0,wx.ALL,6);bar.Add(self.export_button,0,wx.ALL,6)
        box.Add(bar,0,wx.EXPAND)
        self.status=wx.StaticText(self,label='No snapshot. Run a circuit or load acquired results first.')
        box.Add(self.status,0,wx.EXPAND|wx.ALL,6)
        self.web=None;self.box=box
        self.placeholder=wx.StaticText(self,label='Refresh to render an offline snapshot of the selected run. This does not start a web server.')
        box.Add(self.placeholder,1,wx.EXPAND|wx.ALL,12)
        self.SetSizer(box)
        self.refresh_button.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.refresh_snapshot))
        self.export_button.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.export))
        self.Bind(wx.EVT_WINDOW_DESTROY,self.destroy)

    def create_webview(self):
        if self.web:return
        try:
            import wx.html2 as webview
            if not webview.WebView.IsBackendAvailable(webview.WebViewBackendDefault):raise RuntimeError('No supported native WebView runtime')
            # A unique writable profile avoids WebView2 executable-directory and
            # cross-process profile locks. No user browser profile is touched.
            import os
            if os.name=='nt':os.environ['WEBVIEW2_USER_DATA_FOLDER']=str(Path(self._temporary.name)/'webview-profile')
            self.web=webview.WebView.New(self,url=self.report_path.as_uri())
            self.web.Bind(webview.EVT_WEBVIEW_NAVIGATING,self.navigate)
            self.web.Bind(webview.EVT_WEBVIEW_NEWWINDOW,lambda e:e.Veto())
            self.web.Bind(webview.EVT_WEBVIEW_ERROR,self.web_error)
            self.placeholder.Hide();self.box.Add(self.web,1,wx.EXPAND);self.Layout()
        except Exception as exc:
            self.placeholder.SetLabel('Embedded report unavailable: '+str(exc)+'\nOffline HTML export is still available.')

    def destroy(self,event):
        if event.GetEventObject() is self:
            self.generation+=1
            try:self._temporary.cleanup()
            except OSError:pass  # WebView may release its file after the native child closes.
        event.Skip()

    def navigate(self,event):
        from urllib.parse import urlsplit
        from urllib.request import url2pathname
        url=event.GetURL();allowed=url=='about:blank';parsed=urlsplit(url)
        if parsed.scheme=='file' and parsed.netloc in ('','localhost') and not parsed.query:
            # Only the generated report, never a local document path from chart text.
            allowed=Path(url2pathname(parsed.path)).resolve()==self.report_path.resolve()
        if not allowed:
            self.status.SetLabel('Blocked report navigation: '+url[:180]);event.Veto()

    def web_error(self,event):self.status.SetLabel('Embedded chart error: '+event.GetString()+'; offline export remains available.')

    def refresh_snapshot(self):
        if self.owner.math is None:raise ValueError('Acquire simulation results first')
        if self.owner.job_running:raise ValueError('Stop acquisition before preparing an interactive report snapshot')
        engine=self.owner.math
        expressions=[t[0] for t in self.owner.traces if t[0] not in self.owner.hidden_traces] or list(engine.signals)[:8]
        title=self.owner.doc.data['title']+' · '+self.owner.run_choice.GetStringSelection()
        provenance=dict((self.owner.result or {}).get('provenance',{}))
        palette=dict(self.owner.palette);self.generation+=1;generation=self.generation
        self.refresh_button.Disable()
        def work():
            from .offline_report import snapshot,write_report
            report=snapshot(engine,expressions,title=title,provenance=provenance,palette=palette)
            write_report(self.report_path,report)
            return report
        def done(report):
            if generation!=self.generation:return
            self.report=report;self.export_button.Enable();self.refresh_button.Enable()
            self.status.SetLabel(f"Acquired snapshot · {len(report['traces'])} traces · {report['capture']['samples']:,} original samples · offline, read-only")
            existing=self.web is not None
            self.create_webview()
            if existing:self.web.Reload()
        # Completion is marshalled by the existing background-job coordinator.
        self.owner.background(work,done,'Preparing offline report…')
        self.refresh_button.Enable()

    def export(self):
        if self.report is None:raise ValueError('Refresh the acquired snapshot first')
        path=self.owner.choose_path('Export offline interactive report','HTML report (*.html)|*.html',True)
        if path:
            from .offline_report import write_report
            write_report(path,self.report)
