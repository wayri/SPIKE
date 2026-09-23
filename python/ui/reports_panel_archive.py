"""
Reports Panel
Generate and export professional simulation reports
"""
import wx
import wx.html
import wx.html2

class ReportsPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Toolbar
        toolbar = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_generate = wx.Button(self, label="📊 Generate Report")
        self.btn_export_pdf = wx.Button(self, label="📄 Export PDF")
        self.btn_export_html = wx.Button(self, label="🌐 Export HTML")
        self.btn_print = wx.Button(self, label="🖨 Print")
        
        toolbar.Add(self.btn_generate, 0, wx.RIGHT, 5)
        toolbar.Add(self.btn_export_pdf, 0, wx.RIGHT, 5)
        toolbar.Add(self.btn_export_html, 0, wx.RIGHT, 5)
        toolbar.Add(self.btn_print, 0, wx.RIGHT, 10)
        
        toolbar.AddStretchSpacer()
        
        toolbar.Add(wx.StaticText(self, label="Template:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.choice_template = wx.Choice(self, choices=["Standard Report", "Executive Summary", "Detailed Analysis", "Custom"])
        self.choice_template.SetSelection(0)
        toolbar.Add(self.choice_template, 0, wx.ALIGN_CENTER_VERTICAL)
        
        main_sizer.Add(toolbar, 0, wx.EXPAND | wx.ALL, 5)
        
        # Report preview (HTML viewer)
        try:
            self.report_viewer = wx.html2.WebView.New(self)
            self.load_sample_report()
        except:
            # Fallback to simple HTML window
            self.report_viewer = wx.html.HtmlWindow(self)
            self.report_viewer.SetPage(self.get_sample_html())
        
        main_sizer.Add(self.report_viewer, 1, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(main_sizer)
        
    def load_sample_report(self):
        """Load a sample report"""
        html = self.get_sample_html()
        self.report_viewer.SetPage(html, "")
        
    def get_sample_html(self):
        """Generate sample HTML report"""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .header h1 {
            margin: 0;
            font-size: 32px;
        }
        .header p {
            margin: 5px 0 0 0;
            opacity: 0.9;
        }
        .section {
            background: white;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .section h2 {
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-top: 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }
        th {
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
        }
        td {
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }
        tr:hover {
            background: #f9f9f9;
        }
        .metric {
            display: inline-block;
            background: #e8eaf6;
            padding: 15px 20px;
            margin: 10px 10px 10px 0;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .metric-label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }
        .metric-value {
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }
        .warning {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
        }
        .success {
            background: #d4edda;
            border-left: 4px solid #28a745;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔌 SPIKE Simulation Report</h1>
        <p>Power Integrity Analysis • ebrake1.kicad_pcb</p>
        <p>Generated: February 9, 2026 21:43:53</p>
    </div>
    
    <div class="section">
        <h2>📊 Executive Summary</h2>
        <div class="metric">
            <div class="metric-label">Total Nets Analyzed</div>
            <div class="metric-value">102</div>
        </div>
        <div class="metric">
            <div class="metric-label">Power Dissipation</div>
            <div class="metric-value">2.4 W</div>
        </div>
        <div class="metric">
            <div class="metric-label">Max Temp Rise</div>
            <div class="metric-value">15°C</div>
        </div>
        <div class="metric">
            <div class="metric-label">PDN Impedance</div>
            <div class="metric-value">1.2 mΩ</div>
        </div>
    </div>
    
    <div class="section">
        <h2>⚡ Power Net Analysis</h2>
        <table>
            <tr>
                <th>Net Name</th>
                <th>Voltage (V)</th>
                <th>Current (A)</th>
                <th>Resistance (mΩ)</th>
                <th>Status</th>
            </tr>
            <tr>
                <td>24V</td>
                <td>24.00</td>
                <td>3.5</td>
                <td>1.2</td>
                <td>✓ Pass</td>
            </tr>
            <tr>
                <td>GND</td>
                <td>0.00</td>
                <td>-</td>
                <td>0.8</td>
                <td>✓ Pass</td>
            </tr>
            <tr>
                <td>3V3</td>
                <td>3.30</td>
                <td>1.2</td>
                <td>2.1</td>
                <td>⚠ Review</td>
            </tr>
        </table>
    </div>
    
    <div class="section">
        <h2>🔍 Critical Findings</h2>
        <div class="warning">
            <strong>⚠ High Current Density Warning</strong><br>
            Net: 24V at location (45.2, 67.8) mm<br>
            Current Density: 125.4 A/mm²<br>
            Recommendation: Increase trace width or add copper pour
        </div>
        <div class="success">
            <strong>✓ Excellent Ground Plane Coverage</strong><br>
            Net: GND shows uniform distribution<br>
            Average impedance: 0.8 mΩ, Max voltage drop: 12 mV
        </div>
    </div>
    
    <div class="section">
        <h2>📝 Recommendations</h2>
        <ol>
            <li>Add decoupling capacitors near high-current loads (U1, U3)</li>
            <li>Consider via stitching between ground planes for thermal management</li>
            <li>Review trace widths on power nets (24V, 12V) - increase to 0.5mm minimum</li>
            <li>Add thermal reliefs to large copper pours to improve solderability</li>
        </ol>
    </div>
    
    <div class="section">
        <h2>🔧 Simulation Parameters</h2>
        <table>
            <tr><td><strong>Mesh Resolution</strong></td><td>0.05 mm</td></tr>
            <tr><td><strong>Copper Thickness</strong></td><td>0.035 mm (1 oz)</td></tr>
            <tr><td><strong>Solver Type</strong></td><td>PEEC (Partial Element Equivalent Circuit)</td></tr>
            <tr><td><strong>Analysis Mode</strong></td><td>DC Power Distribution</td></tr>
            <tr><td><strong>Simulation Time</strong></td><td>2.3 seconds</td></tr>
        </table>
    </div>
</body>
</html>
"""
