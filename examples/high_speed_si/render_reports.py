# SPDX-License-Identifier: Apache-2.0
"""Render actual bounded SI/PI evidence, with no fabricated spatial fields."""
from pathlib import Path
import hashlib, html, json, shutil, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib import colors
from reportlab.lib.units import mm
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/high-speed-si/reports'
OUT.mkdir(parents=True,exist_ok=True)
STYLE=getSampleStyleSheet()
STYLE['Normal'].fontSize=10; STYLE['Normal'].leading=14
STYLE['Heading1'].textColor=colors.HexColor('#15394a')
plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.2,'figure.facecolor':'white'})
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def esc(x): return html.escape(str(x))
def fmt(x): return f'{x:.6g}' if isinstance(x,(float,int)) else str(x)
def para(x): return Paragraph(esc(x),STYLE['Normal'])
def table(rows):
    t=Table([[para(c) for c in row] for row in rows],colWidths=[82*mm,92*mm],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5f0f2')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#ccd9de'))]))
    return t
def footer(canvas,doc):
    canvas.setFont('Helvetica',8); canvas.setFillColor(colors.HexColor('#596d77'))
    canvas.drawString(18*mm,12*mm,'SPIKE | Experimental numerical studies | Not hardware qualification')
    canvas.drawRightString(192*mm,12*mm,str(doc.page))
class ReportDoc(SimpleDocTemplate):
    def afterFlowable(self,flowable):
        if isinstance(flowable,Paragraph) and flowable.style.name=='Heading1':
            text=flowable.getPlainText();key='section-'+hashlib.sha256(text.encode()).hexdigest()[:16]
            self.canv.bookmarkPage(key);self.canv.addOutlineEntry(text,key,0)
            self.notify('TOCEntry',(0,text,self.page,key))

def pdf(name,title,sections):
    story=[Paragraph('SPIKE ENGINEERING STUDIES',STYLE['Heading2']),Paragraph(title,STYLE['Title']),Spacer(1,8*mm),para('Executed reference-model results. Geometry illustrations and network quantities retain different meanings. Setup assumptions, independent checks and limits are recorded below.'),Spacer(1,8*mm),Paragraph('Contents',STYLE['Heading2'])]
    toc=TableOfContents();toc.levelStyles=[STYLE['Normal']];story += [toc]
    story += [PageBreak()]
    for index,(heading,body,rows,images) in enumerate(sections):
        if index:story += [PageBreak()]
        story += [Paragraph(esc(heading),STYLE['Heading1']),para(body),Spacer(1,4*mm)]
        if rows: story += [table(rows),Spacer(1,4*mm)]
        for image in images:
            from PIL import Image as PILImage
            with PILImage.open(image) as im: w,h=im.size
            story += [Image(str(image),width=174*mm,height=174*mm*h/w),Spacer(1,4*mm)]
        story += [Spacer(1,6*mm)]
    ReportDoc(str(OUT/name),pagesize=(210*mm,297*mm),leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=20*mm,title=title,author='SPIKE').multiBuild(story,onFirstPage=footer,onLaterPages=footer)
def protocol_sections():
    summary=read(ROOT/'examples/high_speed_si/protocol_results/summary.json')
    sections=[]; plotdata=[]
    for case in summary['cases']:
        result=read(ROOT/f'examples/high_speed_si/protocol_results/{case["id"]}.json')
        request=result['request']; td=result['time_domain']['receivers'][0]; trace=result['loaded_transfers'][0]['trace']
        fig,ax=plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
        f=[v['frequency_hz']/1e9 for v in trace]
        ax[0].plot(f,[v['magnitude_db'] for v in trace],color='#137d8b'); ax[0].set(xlabel='Frequency (GHz)',ylabel='Loaded gain (dB V/V)',title='Loaded source-to-receiver transfer')
        for eye in td.get('traces',[])[:120]: ax[1].plot(eye['phase_ui'],eye['voltage_v'],color='#186d9c',alpha=.12,lw=.6)
        ax[1].set(xlabel='Phase (UI)',ylabel='Receiver voltage (V)',title='Computed finite-record NRZ eye')
        img=OUT/(case['id']+'.png'); fig.savefig(img,dpi=150);plt.close(fig)
        rows=[['Parameter / observation','Value'],['Aggregate payload (Gb/s)',fmt(case['aggregate_payload_rate_bps']/1e9) if case.get('aggregate_payload_rate_bps') else 'Not defined (no protocol framing)'],['Lane baud (GBd)',fmt(case['lane_symbol_rate_baud']/1e9)],['Architecture lanes / simulated lanes',f'{case["architecture_lane_count"]} / {case["simulated_lane_count"]}'],['Saved base-grid eye height (V)',fmt(case['loaded_eye']['eye_height_v'])],['Finest-grid eye height (V)',fmt(case['refinements'][-1]['eye_height_v'])],['Line R / L / C per metre',f'{request["channel"]["resistance_ohm_per_m"]} ohm / {request["channel"]["inductance_h_per_m"]*1e9:g} nH / {request["channel"]["capacitance_f_per_m"]*1e12:g} pF'],['Loss tangent',fmt(request['channel']['loss_tangent'])],['Source / load resistance (ohm)',f'{request["sources"][0]["resistance_ohm"]} / {request["receivers"][0]["resistance_ohm"]}'],['Receiver capacitance (pF)',fmt(request['receivers'][0]['capacitance_f']*1e12)],['Source rise time (ps)',fmt(request['sources'][0]['rise_time_s']*1e12)],['Insertion loss near Nyquist (dB)',fmt(case['insertion_loss_near_nyquist_db'])],['Final refinement delta (V)',fmt(case['successive_eye_change_v'][-1])],['Reference-check outcome',case['status']],['Analytic transfer / matched-eye tolerance','1e-10 absolute / 1e-10 V'],['Final successive eye-change gate','< 0.005 V (not an accuracy error bound)'],['Recorded check outcomes',', '.join(name + ': ' + ('pass' if passed else 'FAIL') for name,passed in case['checks'].items())],['Complex transfer max absolute error',fmt(case['max_complex_loaded_transfer_error'])]]
        body=f"{case['label']}. Original uniform differential RLGC, {request['channel']['length_m']*1000:g} mm at {request['temperature_c']:g} C. Source levels {request['sources'][0]['low_v']:g} / {request['sources'][0]['high_v']:g} V; receiver thresholds {request['receivers'][0]['vil_v']:g} / {request['receivers'][0]['vih_v']:g} V. PRBS7, {request['bit_count']} bits; saved frequency grid {request['channel']['frequency_points']} points to {request['channel']['frequency_stop_hz']/1e9:.6g} GHz. Loaded-eye plots use the saved base grid. Independent ABCD checks and successive refinement test this reference line. No PCS/FEC/BER, BASE-T, compliance mask or nonlinear PHY is modeled; 100G uses one uncoupled lane."

        sections.append((case['label'],body,rows,[img]))
        plotdata.append({'id':case['id'],'label':case['label'],'frequency_ghz':f,'gain_db':[v['magnitude_db'] for v in trace], 'waveform':td.get('waveform',[])[:8192],'eye':td.get('traces',[])[:120], 'metrics':rows})
    return sections,plotdata,summary

def generic_sections(title,summary,path):
    rows=[['Evidence key','Returned value']]
    for key,val in summary.items():
        if isinstance(val,(str,int,float,bool)) and not any(term in key for term in ['artifact','sha256','runtime','machine','directory','scope','occurrence']): rows.append([key,fmt(val)])
    return [(title,'Actual solver output is retained alongside requests and checks. Scalar metrics below are source-bound; no complete PCB or cable field qualification is implied.',rows,[]) ]

def scene_geometry():
    raw=read(ROOT/'output/high-speed-si/interboard-field-complete/geometry.json')
    boxes=[]
    for board in raw['boards']:
        for b in board['boxes']: boxes.append({**b,'name':board['id']+'.'+b['id']})
    return boxes

def field_grid(capture, quantity, frame_index):
    """Reshape the retained x-major, z-fastest native sample ordering."""
    frame = capture[quantity][frame_index]
    values = np.linalg.norm(np.asarray(frame['real']) + 1j * np.asarray(frame['imag']), axis=1)
    shape = tuple(len(capture['positions'][axis]) for axis in ('x', 'y', 'z'))
    if tuple(capture['shape']) != shape or len(values) != np.prod(shape):
        raise ValueError('Native field shape does not match saved coordinates')
    return values.reshape(shape)


def projected_field_geometry(geometry, horizontal, vertical, depth, position):
    """Context rectangles retain actual model coordinates; projections are explicit."""
    result = []
    for box in geometry:
        start, stop = box['start_mm'], box['stop_mm']
        cut = min(start[depth], stop[depth]) <= position <= max(start[depth], stop[depth])
        result.append({'name': box['name'], 'kind': box['kind'], 'cut': cut,
                       'x': min(start[horizontal], stop[horizontal]),
                       'y': min(start[vertical], stop[vertical]),
                       'width': abs(stop[horizontal] - start[horizontal]),
                       'height': abs(stop[vertical] - start[vertical])})
    return result


def render_field_slices(capture, quantity, frame_index, output, geometry=None):
    grid = field_grid(capture, quantity, frame_index)
    coords = {axis: np.asarray(capture['positions'][axis]) * 1000 for axis in ('x', 'y', 'z')}
    _, iy, iz = np.unravel_index(np.argmax(grid), grid.shape)
    maximum = float(grid.max())
    exponent = int(np.floor(np.log10(maximum))) if maximum > 0 else 0
    scale = 10. ** exponent
    symbol, unit = ('E', 'V/m') if quantity == 'electric_field' else ('H', 'A/m')
    fig, axes = plt.subplots(2, 1, figsize=(11, 9.2), layout='constrained')
    definitions = {'x': 'along traces / near to far', 'y': 'transverse to traces', 'z': 'board stack height'}
    geometry = scene_geometry() if geometry is None else geometry
    for ax, horizontal, vertical, values, title in [
        (axes[0], 'x', 'y', grid[:, :, iz].T, f'XY slice at Z = {coords["z"][iz]:.3f} mm'),
        (axes[1], 'x', 'z', grid[:, iy, :].T, f'XZ slice at Y = {coords["y"][iy]:.3f} mm'),
    ]:
        plot = ax.pcolormesh(coords[horizontal], coords[vertical], values / scale,
                             shading='gouraud', rasterized=True, cmap='inferno', vmin=0, vmax=maximum / scale if maximum else 1)
        h, v = 'xyz'.index(horizontal), 'xyz'.index(vertical)
        d = next(index for index in range(3) if index not in (h, v))
        position = coords['xyz'[d]][iz if d == 2 else iy]
        for box in projected_field_geometry(geometry, h, v, d, position):
            color = '#8debd7' if box['kind'] == 'dielectric' else '#ffffff'
            ax.add_patch(Rectangle((box['x'], box['y']), box['width'], box['height'],
                                  facecolor=color + ('12' if box['cut'] else '00'), edgecolor=color, linewidth=1.2,
                                  linestyle='-' if box['cut'] else '--', zorder=3))
            if vertical == 'z' and box['kind'] == 'dielectric':
                ax.text(box['x'] + 1, box['y'] + box['height']/2, box['name'],
                        color=color, fontsize=10, va='center', zorder=4,
                        bbox={'facecolor': '#102632', 'alpha': .8, 'pad': 2, 'edgecolor': 'none'})
        ax.set(xlabel=horizontal.upper()+' (mm) · '+definitions[horizontal],
               ylabel=vertical.upper()+' (mm) · '+definitions[vertical], title=title)
        ax.text(.02, .97, 'Translucent board/trace diagram · solid: section · dashed: projection',
                transform=ax.transAxes, va='top', color='white', fontsize=9,
                bbox={'facecolor':'#102632','alpha':.85,'pad':3,'edgecolor':'none'})
        ax.tick_params(labelsize=12)
        ax.xaxis.label.set_size(12); ax.yaxis.label.set_size(12)
        bar = fig.colorbar(plot, ax=ax, pad=.025)
        bar.set_label(f'Raw DFT |{symbol}| (x 10^{exponent} {unit})', fontsize=12)
        bar.ax.tick_params(labelsize=12)
    frequency = capture[quantity][frame_index]['frequency_hz'] / 1e9
    fig.suptitle(f'{quantity.replace("_", " ").capitalize()} at {frequency:g} GHz\n'
                 f'Saved grid {grid.shape[0]} × {grid.shape[1]} × {grid.shape[2]} · display color interpolation only\n'
                 'Origin: board A top-plane center (Z = 0); +Z toward board B', fontsize=14)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main():
    sections,protocols,summary=protocol_sections()
    intro=('Setup and interpretation','Five loaded-channel studies execute the same public SI worker method used by the desktop. Models are original numerical fixtures, not measured Ethernet boards. 1G means 1000BASE-X host serial reference; 10G means 10.3125 GBd NRZ; 100G means a 4 x 25.78125 GBd architecture represented by one uncoupled lane. LVDS and generic SerDes use explicit reference rates. No Ethernet standards compliance is evaluated.',[],[])
    closing=('Conclusions and reproduction','Inspect the reported refinement outcomes before using eye numbers. Open the saved native result JSON in HF / SI > Source-to-receiver workflow > Load setup/result. Each .spike package restores its latest channel result. Reproduce with examples/high_speed_si/run_protocol_cases.py. Replace authored RLGC, endpoint models and losses with characterized hardware data for a real design.',[],[])
    review_rows=[['Study / recorded status','Finest-grid eye opening (V)'],*[[case['label']+' / '+case['status'],fmt(case['refinements'][-1]['eye_height_v'])] for case in summary['cases']]]
    review_section=('Result review summary','Open the bookmarked study to inspect its setup, loaded transfer, eye and independent checks. The table reports refined eye openings; the plots use saved base-grid traces. Passing reference checks is not an Ethernet compliance result. No compliance mask, BER or hardware acceptance margin has been specified.',review_rows,[])
    pdf('protocol-si.pdf','Ethernet, LVDS and SerDes channel studies',[review_section,intro,*sections,closing])
    harnessroot=ROOT/'examples/high_speed_si/harness'
    harness_summary=read(harnessroot/'summary.json') if (harnessroot/'summary.json').exists() else {'status':'pending','scope':'Harness run not complete'}
    evidence=harnessroot/'evidence'
    validation=read(evidence/'validation.json') if (evidence/'validation.json').exists() else {}
    harness_graph=read(evidence/'rlgc-request.json') if (evidence/'rlgc-request.json').exists() else {}
    harness_pi=read(evidence/'pi-result.json') if (evidence/'pi-result.json').exists() else {}
    harness_sections=generic_sections('Harness PI and coupled SI',harness_summary,harnessroot)
    if validation:
        pi=validation['pi']; si=validation['si']; response=si['frequency_response']
        fig,ax=plt.subplots(figsize=(9,3.8),layout='constrained')
        for key,label in [('differential_next_db','Differential NEXT'),('differential_fext_db','Differential FEXT')]:
            ax.plot([r['frequency_hz']/1e9 for r in response],[max(-160,r[key]) for r in response],label=label)
        ax.set(xlabel='Frequency (GHz)',ylabel='Mixed-mode S magnitude (dB)',title='Actual coupled harness response (display floor -160 dB)');ax.legend()
        img=OUT/'harness-crosstalk.png';fig.savefig(img,dpi=150);plt.close(fig)
        rows=[['Observation','Returned value'],['Remote load voltage (V)',fmt(pi['load_voltage_v'])],['Wire loss (W)',fmt(pi['wire_loss_w'])],['Voltage oracle absolute error (V)',fmt(pi['load_voltage_abs_error_v'])],['Power closure residual (W)',fmt(pi['native_element_power_sum_w'])],['Peak differential NEXT (V/V)',fmt(si['peak_differential_next']['magnitude_v_per_v'])],['Peak differential FEXT (V/V)',fmt(si['peak_differential_fext']['magnitude_v_per_v'])],['Sampled maximum singular value',fmt(si['maximum_sampled_singular_value'])],['Reciprocity max absolute error',fmt(si['reciprocity_max_abs'])]]
        harness_sections.append(('Setup, actual results and checks','Two explicitly distinct board occurrences linked by a 0.6 m straight harness. A 12 V source supplies a remote 4 A current sink through separate power/return wires. Four signal conductors have explicit cross-section coordinates and ideal-plane references, with 50-ohm single-ended ports / 100-ohm differential normalization. Coupling is computed from a supplied geometry-derived approximate RLGC matrix; no copper-field or twisted-cable qualification is implied.',rows,[img]))
    pdf('harness-multiboard.pdf','Harness and multiboard PI / SI',harness_sections+[('Limits and next steps','Explicit board ownership and return paths are required. Supplied round-wire or RLGC models do not establish arbitrary twisted/shielded cable accuracy. The public uniform-harness SI workflow is available in the desktop. Coupled MTL runs through the integrated worker but currently has no dedicated desktop panel. Review request, contact models, geometry and reference checks in the companion data folder.',[],[])])
    fieldroot=ROOT/'output/high-speed-si/interboard-field-complete'
    execution=read(fieldroot/'execution.json') if (fieldroot/'execution.json').exists() else {'status':'pending'}
    field=read(fieldroot/'field-result.json') if (fieldroot/'field-result.json').exists() else {}
    screen=read(fieldroot/'screening.json') if (fieldroot/'screening.json').exists() else {}
    fields=[]
    if field:
        s=np.asarray(field['s_real'])+1j*np.asarray(field['s_imag']); fig,ax=plt.subplots(figsize=(9,3.4),layout='constrained')
        for row,label in [(1,'S21 board A transmission'),(2,'S31 crossboard near'),(3,'S41 crossboard far')]:ax.plot(np.asarray(field['frequency_hz'])/1e9,20*np.log10(np.maximum(abs(s[:,row,0]),1e-15)),label=label)
        ax.set(xlabel='Frequency (GHz)',ylabel='S magnitude (dB)',title='Actual openEMS four-excitation network'); ax.legend(fontsize=8)
        p=OUT/'interboard-coupling.png';fig.savefig(p,dpi=150);plt.close(fig);fields=[p]
    field_sections=generic_sections('Execution and numerical screens',{**{k:v for k,v in execution.items() if isinstance(v,(str,float,int,bool))},**{k:v for k,v in field.items() if isinstance(v,(str,float,int,bool))},'screen_passed':screen.get('screen_passed','not available')},fieldroot)
    field_sections[0]=(field_sections[0][0],field_sections[0][1]+' Four independent 50-ohm port excitations on two explicit substrate boxes, 4 mm air gap; 0.2 to 3 GHz. This band does not qualify 10G/100G links. Mesh/PML/duration refinement and hardware correlation remain separate requirements.',field_sections[0][2],[])
    if field:
        loaded=read(fieldroot/'loaded-field-crosstalk.json')
        peaks={name:max(row['magnitude'] for row in response['trace']) for name,response in loaded['frequency_response'].items()}
        field_sections.append(('Four-port response and loaded interference','Actual independent excitations give S21 transmission and crossboard S31/S41 responses. The loaded circuit uses explicit 50-ohm terminations. These are different quantities: the plot shows S magnitudes, while the table shows loaded transfer V/V. Existing numerical gates allow 0.02 passivity excess and 0.02 absolute reciprocity error; passing them is not physical convergence.',[['Quantity','Peak loaded transfer (V/V)'],*[[name,fmt(value)] for name,value in peaks.items()]],fields))
    capture_path=ROOT/'examples/high_speed_si/field/actual_capture/field-samples.json'
    if capture_path.exists():
        capture=read(capture_path);axes=capture['positions']
        rows=[['Capture / observation','Value'],['Native Cartesian volume',str(capture['shape'])],['Frequency frames (GHz)','0.5, 1.5, 2.5'],['Excited port','A.near'],['Normalization','Raw unnormalized Gaussian-pulse DFT; not 1 V or 1 W steady-state fields']]
        images=[]
        for quantity,unit in [('electric_field','V/m'),('magnetic_field','A/m')]:
            frame=capture[quantity][1]
            values=np.linalg.norm(np.asarray(frame['real'])+1j*np.asarray(frame['imag']),axis=1)
            image=OUT/(quantity+'-slices.png')
            render_field_slices(capture,quantity,1,image)
            images.append(image)
            rows.append(['Maximum complex vector norm ('+unit+')',fmt(float(values.max()))])
        plt.imsave(OUT/'native-volume-fields.png', np.concatenate([plt.imread(image) for image in images], axis=0))
        field_sections.append(('Native electric and magnetic capture slices','Each full-width figure shows two orthogonal slices through the maximum saved vector norm at 1.5 GHz. Coordinates and slice positions are in mm. Colors interpolate between saved samples for display only; no additional solver resolution is implied. Translucent outlines show the actual modeled substrates and conductors: solid outlines intersect the slice, dashed outlines are projections. X is along the traces, Y is transverse, and Z is stack height from board A top-plane center (Z = 0), increasing toward board B. The common color scale for both slices is labeled with its explicit power-of-ten multiplier. Use the HTML slice controls to inspect other positions and frequencies. A separate completed one-port field solve retains 3,864 native cell-interpolated positions per frequency. These amplitudes are unnormalized Gaussian-pulse Fourier coefficients, not calibrated steady-state field strengths.',rows,images))
    pdf('interboard-fields.pdf','Interboard SI interference field study',field_sections+[('Conclusions','A completed field run and a numerical sanity screen have different meanings. Failed screens remain visible; do not generate qualified eye or compliance claims from failed field networks. Native port histories and complete four-port response are retained.',[],[])])
    data={'protocols':protocols,'protocol_summary':summary,'harness':harness_summary,'harness_validation':validation,'harness_geometry':harness_graph,'harness_pi':harness_pi,'field':field,'screen':screen,'geometry':scene_geometry()}
    optional=ROOT/'examples/high_speed_si/field/actual_capture/field-samples.json'
    if optional.exists():
        data['field_samples']=read(optional)
        f=data['field_samples'];axes=f['positions'];data['field_samples']['points_mm']=[[x*1000,y*1000,z*1000] for x in axes['x'] for y in axes['y'] for z in axes['z']]
    if (evidence/'assembly-view.json').exists():data['harness_assembly']=read(evidence/'assembly-view.json')
    (OUT/'data.json').write_text(json.dumps(data,allow_nan=False),encoding='utf-8')
    write_html(data,sections)
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'examples/high_speed_si/protocol_results/summary.json',*OUT.glob('*.pdf'),*[OUT/name for name in ('electric_field-slices.png','magnetic_field-slices.png','native-volume-fields.png') if (OUT/name).exists()],OUT/'index.html',OUT/'data.json']}
    (OUT/'manifest.json').write_text(json.dumps({'contract':'spike/study-report-evidence/v1','artifact_sha256':hashes,'production_qualified':False,'scope':'Original channel/harness/box-field numerical studies'},indent=2),encoding='utf-8')
    print(json.dumps({'reports':str(OUT),'protocol_check_status':summary['status'],'field_status':execution.get('status'),'field_screen':screen.get('screen_passed')},indent=2))

def validation_table(rows):
    return '<table class="validation"><caption>Recorded validation evidence</caption>' + ''.join(
        '<tr><th scope="row">' + esc(label) + '</th><td>' + esc(value) + '</td></tr>'
        for label, value in rows) + '</table>'


def report_guides(data):
    """Explain saved evidence without upgrading a numerical screen to qualification."""
    pi = data.get('harness_validation', {}).get('pi', {})
    si = data.get('harness_validation', {}).get('si', {})
    screen = data.get('screen', {})
    thresholds = screen.get('thresholds', {})
    harness = '<h3>How to read the harness plots</h3><p>Coordinates are millimetres; the 600 mm harness is compressed for display. Probe a conductor for DC current (A) and dissipated power (W). The remote load voltage is in V. Signal wires absent from the DC solve are explicitly unselected.</p><p>NEXT is near-end differential coupling; FEXT is far-end differential coupling, for the saved aggressor/victim port setup. The vertical axis is 20 log10 of the mixed-mode scattering amplitude ratio, in dB. More negative coupling means less coupled amplitude at that frequency under these terminations. -40 dB means an amplitude ratio of 0.01. The -160 dB display floor is a plotting limit; raw data is retained. Ports use 50 ohm single-ended / 100 ohm differential references.</p>'
    harness += validation_table([
        ('Harness check status', data.get('harness_validation', {}).get('status', 'Unavailable')),
        ('DC load voltage / analytic reference (V)', f"{fmt(pi.get('load_voltage_v'))} / {fmt(pi.get('analytical_load_voltage_v'))}"),
        ('DC voltage absolute error (V)', fmt(pi.get('load_voltage_abs_error_v'))),
        ('DC power closure residual (W)', fmt(pi.get('native_element_power_sum_w'))),
        ('SI linear-system relative residual', fmt(si.get('maximum_relative_residual'))),
        ('SI sampled maximum singular value (passive ideal: <= 1)', fmt(si.get('maximum_sampled_singular_value'))),
        ('SI reciprocity maximum absolute error', fmt(si.get('reciprocity_max_abs'))),
    ])
    harness += '<p>These checks test the supplied lumped DC circuit and approximate RLGC harness model. They do not validate an arbitrary real cable, shield or twisted pair. See raw evidence below for the exact pair ordering and setup.</p>'
    field = '<h3>How to read the interboard response</h3><p>The horizontal axis is frequency in GHz. The vertical axis is 20 log10 |Sij| in dB, a dimensionless scattering-wave amplitude ratio with 50 ohm reference impedances. Excitation is port 1 (A.near): S21 goes to A.far, S31 to B.near, and S41 to B.far. 0 dB means unity wave amplitude; -20 dB means 0.1. Lower crossboard curves mean less coupling for this model. These are not loaded receiver voltages or spatial field strengths. Values below -300 dB are floored for display.</p>'
    field += validation_table([
        ('Numerical sanity screen passed', str(screen.get('screen_passed', 'Unavailable'))),
        ('Maximum singular value / allowed passivity excess', f"{fmt(screen.get('maximum_singular_value'))} / {fmt(thresholds.get('passivity_excess'))}"),
        ('Reciprocity absolute error / allowed error', f"{fmt(screen.get('maximum_reciprocity_absolute_error'))} / {fmt(thresholds.get('reciprocity_absolute'))}"),
        ('Temporal completion screen passed', str(screen.get('temporal_completion', {}).get('screen_passed', 'Unavailable'))),
        ('Physical accuracy qualified', str(screen.get('physical_accuracy_qualified', False))),
    ])
    field += '<p class="badge">Sanity checks passed for the retained run, but mesh, PML and duration convergence and measured correlation are not established. Two substrate boxes with a 4 mm gap are not complete PCB assemblies. The 0.2-3 GHz band cannot qualify 10G or 100G links.</p>' if screen.get('screen_passed') else '<p class="badge">The retained numerical screen has not passed. Do not treat this field network as validated.</p>'
    return harness, field


def write_html(data,sections):
    plotly=ROOT/'app/node_modules/plotly.js-dist-min/plotly.min.js'
    shutil.copyfile(plotly,OUT/'plotly.min.js')
    licensepath=plotly.parent/'LICENSE';
    if licensepath.exists():shutil.copyfile(licensepath,OUT/'PLOTLY-LICENSE.txt')
    payload=json.dumps(data,allow_nan=False).replace('</','<\\/')
    content=''.join(f'<section id="{case["id"]}"><h2>{esc(case["label"])}</h2><p><a href="../projects/{case['id']}.spike">Saved .spike study</a></p><p>{esc(section[1])}</p><table>'+''.join('<tr>'+''.join(f'<td>{esc(v)}</td>' for v in row)+'</tr>' for row in case['metrics'])+f'</table><h3>Loaded source-to-receiver transfer</h3><p>Frequency is in GHz; gain is 20 log10 |Vreceiver / Vsource| in dB. 0 dB is unity amplitude and -6 dB is approximately half amplitude. This includes the stated source/load impedances; it is not an S21 insertion-loss plot.</p><div class="plot" id="plot-{case["id"]}"></div><output class="measurement" id="readout-plot-{case["id"]}" aria-live="polite">Click a curve to pin its measurement.</output><h3>Receiver eye diagram</h3><p>Phase is in unit intervals (UI): one UI is one lane symbol period. Voltage is in V. Curves overlay the saved finite PRBS record. Compare eye opening and voltage margins against the listed receiver thresholds. The table records analytic transfer checks and refinement; an open eye does not establish BER or Ethernet compliance.</p><div class="plot" id="eye-{case["id"]}"></div><output class="measurement" id="readout-eye-{case["id"]}" aria-live="polite">Click an eye trace to pin phase and voltage.</output></section>' for case,section in zip(data['protocols'],sections))
    harness_guide, field_guide = report_guides(data)
    review = '<h3>Result review navigator</h3><table><thead><tr><th>Study / scope</th><th>Recorded checks</th><th>Design acceptance</th><th>Inspect</th></tr></thead><tbody>'
    for case in data['protocols']:
        status = next((value for key, value in case['metrics'] if key == 'Reference-check outcome'), 'See evidence')
        review += f'<tr><td>{esc(case["label"])}</td><td>{esc(status)}</td><td>No compliance mask / BER limit specified</td><td><a href="#{esc(case["id"])}">Open plots and measurements</a></td></tr>'
    review += '<tr><td>Two-board harness PI / SI</td><td>' + esc(data.get('harness_validation', {}).get('status', 'Unavailable')) + '</td><td>Hardware limits not specified</td><td><a href="#harness">Inspect conductor and checks</a></td></tr>'
    review += '<tr><td>Two-substrate field model</td><td>Numerical screen: ' + esc(data.get('screen', {}).get('screen_passed', 'Unavailable')) + '</td><td>Physical accuracy unqualified</td><td><a href="#assembly">Inspect geometry-linked fields</a></td></tr></tbody></table>'

    nav=''.join(f'<a href="#{x["id"]}">{esc(x["label"])}</a>' for x in data['protocols'])
    template='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SPIKE SI / PI study reports</title><style>body{margin:0;background:#eef3f6;color:#173440;font:15px/1.6 system-ui}nav{position:fixed;inset:0 auto 0 0;width:220px;background:#12313f;color:white;padding:24px;overflow:auto}nav a{display:block;color:#a9e6e8;padding:8px;text-decoration:none}main{margin-left:268px;max-width:1120px;padding:30px}section{background:white;margin:24px 0;padding:28px;border-radius:8px;scroll-margin-top:12px}h1,h2{line-height:1.25}.badge{background:#ffedc6;padding:12px;border-left:4px solid #c58621}table{border-collapse:collapse;width:100%;font-size:14px}td{padding:8px;border-bottom:1px solid #d5e2e8;overflow-wrap:anywhere}tr:first-child{background:#e3f0f2;font-weight:600}.plot{height:420px;min-width:0;width:100%}#scene{height:640px;width:100%;min-width:0}.measurement{display:block;padding:10px;background:#e7f5f7;border-left:3px solid #13728e}caption{text-align:left;font-weight:700;padding:10px 0}th{text-align:left;padding:8px;border-bottom:1px solid #d5e2e8}.validation th{width:55%}h3{margin-bottom:8px}section{min-width:0;box-sizing:border-box}.probe{padding:14px;background:#e7f5f7;white-space:pre-wrap}button,select,input{max-width:100%;box-sizing:border-box;font:inherit;padding:8px;border:1px solid #739baa;border-radius:5px;background:#e6f1f5;color:#173440}.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:12px 0}.controls label{display:flex;gap:8px;align-items:center;flex-wrap:wrap}input{width:100px}#slice-index{width:220px}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #13728e;outline-offset:3px}pre{white-space:pre-wrap;font:12px/1.5 monospace;max-height:500px;overflow:auto}@media(max-width:800px){nav{position:static;width:auto}main{margin:0;padding:14px}section{padding:16px}#scene{height:520px}.plot{height:400px}section{padding:12px}td,th{font-size:13px}}</style><nav><h2>SPIKE studies</h2><a href="#overview">Overview / setup</a>NAV<a href="#assembly">3D assembly and probes</a><a href="#harness">Harness PI / SI</a><a href="#interboard">Interboard interference</a><a href="#limits">Conclusions / limits</a></nav><main><h1>High-speed SI and multiboard PI</h1><p class="badge">Experimental reference models. Actual computed results; no hardware or Ethernet compliance qualification.</p><section id="overview"><h2>Setup and access</h2><p>Five integrated SI worker studies plus a harness and a separate two-substrate interboard field study. Payload bit rate and lane baud are different. 100G models one lane of a four-lane architecture. The field case spans only 0.2–3 GHz.</p><p><a href="protocol-si.pdf">Protocol PDF</a> · <a href="harness-multiboard.pdf">Harness PDF</a> · <a href="interboard-fields.pdf">Interboard PDF</a> · <a href="data.json">Raw report data</a></p><p>Hover a 2D curve for frequency and value with units. Use the plot toolbar to zoom or export a PNG; double-click to reset axes. Click a 3D sample for its saved value. Rotate / zoom the 3D scene; select a native port or field sample to probe. Geometry is an explicit model, not measured board artwork.</p>REVIEW</section>CONTENT<section id="assembly"><h2>3D assembly / exact probes</h2><div class="controls"><button id="reset">Reset camera</button><label>Board display <select id="boards"><option value="both">Both boards</option><option value="A">Board A</option><option value="B">Board B</option></select></label></div><div class="controls"><label>Captured quantity <select id="field-quantity"><option value="electric_field">Electric field complex vector norm</option><option value="magnetic_field">Magnetic field complex vector norm</option><option value="none">Geometry only</option></select></label> <label>Captured frequency <select id="field-frequency"><option value="0">0.5 GHz</option><option value="1">1.5 GHz</option><option value="2">2.5 GHz</option></select></label></div><p>Native cell-interpolated output on a bounded 3D capture grid. Raw unnormalized Gaussian-pulse DFT; not calibrated to 1 V or 1 W steady-state fields. Full raw complex samples retained.</p><div class="controls"><label>Native sample index <input id="sample-index" type="number" value="1932" min="0" max="3863"></label><button id="probe-sample">Probe saved sample</button></div><h3>How to read the captured field</h3><p>Axes use mm. The color scale is the complex vector norm sqrt(sum |component| squared), not one component or a time snapshot. E uses V/m; H uses A/m. SI tick prefixes such as n mean 10^-9. These raw pulse Fourier coefficients are unnormalized: do not compare their amplitudes with steady-state exposure or EMI limits. Choose a shared color range to compare captured frequencies; per-frequency scaling emphasizes local structure. Selecting one board filters geometry, while the capture still covers the full two-board volume.</p><p class="badge">Spatial capture status: executed, unvalidated. Exact samples are retained from native cell-interpolated output; mesh/duration convergence and calibrated field normalization are not established. This capture is separate from the four-excitation S-parameter study below.</p><div class="controls"><label>Field view <select id="field-view"><option value="slice">2D slice (recommended)</option><option value="volume">3D volume</option></select></label><label>Color display <select id="field-smoothing"><option value="smooth">Smooth (display only)</option><option value="native">Native cells</option></select></label><label>Scale <select id="field-scale"><option value="all">Shared across frequencies</option><option value="frequency">Selected frequency</option></select></label><label>Plane <select id="slice-plane"><option value="xy">XY / depth Z</option><option value="xz">XZ / position Y</option><option value="yz">YZ / position X</option></select></label></div><div class="controls"><button id="slice-prev" aria-label="Previous saved slice">Previous slice</button><label>Saved slice <input id="slice-index" type="range" min="0" max="11" value="5"></label><button id="slice-next" aria-label="Next saved slice">Next slice</button><button id="slice-peak">Go to peak</button><output id="slice-position" aria-live="polite"></output></div><p><strong>Coordinate key:</strong> X follows the traces from near to far; Y is transverse; Z is stack height. Origin is board A top-plane center (Z = 0), with +Z toward board B. Translucent cyan substrates and white conductors retain model coordinates. Solid outlines intersect this plane; dashed outlines are projections, not material in this slice. Color smoothing only changes display; hover/click returns a native sample. <output id="field-resolution"></output></p><p>Use the slice slider or arrow keys to move through saved planes. Hover a cell for its value; click it for its exact native vector. Zoom by dragging a rectangle; double-click to reset. The color range stays fixed across slices; shared-frequency mode also keeps the same range when changing frequency. In 3D mode, drag to orbit and use the toolbar to reset the camera.</p><div id="scene"></div><div id="probe-inspector" role="status" aria-live="polite"></div><details><summary>Exact saved probe payload</summary><div id="probe" class="probe">Select a port or solved field sample. No voltage distribution is invented on board surfaces.</div></details></section><section id="harness"><h2>Harness PI / SI evidence</h2><div class="controls"><label>Conductor <select id="wire-choice"><option>pwr</option><option>return</option><option>agg-p</option><option>agg-n</option><option>vic-p</option><option>vic-n</option></select></label><button id="probe-wire">Probe conductor</button></div><div id="harness-scene" style="height:500px"></div><div id="harness-probe" class="probe">Select a conductor to inspect returned wire/port quantities.</div><div id="harness-plot" class="plot"></div><output class="measurement" id="readout-harness-plot" aria-live="polite">Click a curve to pin frequency and coupling.</output>HARNESS_GUIDE<details><summary>Raw harness setup and evidence</summary><pre id="harness-data"></pre></details></section><section id="interboard"><h2>Interboard field response</h2><div id="coupling" class="plot"></div><output class="measurement" id="readout-coupling" aria-live="polite">Click a curve to pin frequency and S magnitude.</output>FIELD_GUIDE<details><summary>Raw field sanity screen</summary><pre id="screen-data"></pre></details></section><section id="limits"><h2>Conclusions and limits</h2><p>Use the native request/result files to reproduce studies in SPIKE. Reference checks establish bounded software behavior. No BER, COM, FEC, nonlinear PHY, arbitrary twisted cable extraction, full imported-board EMI or measured correlation is established. Network-only results cannot provide spatial fields. Actual captured field samples, when available, are separate from the channel eye models.</p></section></main><script src="plotly.min.js"></script><script>const DATA=PAYLOAD;
const layout={margin:{t:25,l:80,r:24,b:110},paper_bgcolor:'#ffffff',plot_bgcolor:'#ffffff',font:{family:'system-ui',size:14,color:'#173440'},legend:{orientation:'h',x:0,y:-.3,xanchor:'left',yanchor:'top'},hovermode:'x unified'};
const axis=text=>({title:{text,standoff:16},automargin:true,tickfont:{size:12},zerolinecolor:'#b3c6ce',showspikes:true,spikemode:'across',spikesnap:'cursor'});
const sceneAxes={xaxis:axis('X (mm)'),yaxis:axis('Y (mm)'),zaxis:axis('Z (mm)')};
for(const c of DATA.protocols){Plotly.newPlot('plot-'+c.id,[{x:c.frequency_ghz,y:c.gain_db,type:'scatter',name:'Loaded transfer',hovertemplate:'%{x:.4g} GHz<br>%{y:.4g} dB V/V<extra>Loaded transfer</extra>'}],{...layout,xaxis:axis('Frequency (GHz)'),yaxis:axis('Gain (dB V/V)')},{responsive:true});Plotly.newPlot('eye-'+c.id,c.eye.map(e=>({x:e.phase_ui,y:e.voltage_v,type:'scatter',mode:'lines',line:{color:'rgba(19,114,142,.17)',width:1},showlegend:false,hovertemplate:'%{x:.4g} UI<br>%{y:.4g} V<extra>Receiver</extra>'})),{...layout,hovermode:'closest',xaxis:axis('Phase (UI)'),yaxis:axis('Receiver voltage (V)')},{responsive:true});}

let selectedSample=null;
const magnitude=(f,i)=>Math.sqrt(f.real[i].reduce((sum,a,j)=>sum+a*a+f.imag[i][j]*f.imag[i][j],0));
function fieldMaximum(q,fi){
 const frames=document.querySelector('#field-scale').value==='all'?DATA.field_samples[q]:[DATA.field_samples[q][fi]];
 let maximum=0;for(const f of frames)for(let i=0;i<f.real.length;i++)maximum=Math.max(maximum,magnitude(f,i));
 return maximum||1;
}
function inspectSample(i,locate=false){
 const q=document.querySelector('#field-quantity').value,fi=Number(document.querySelector('#field-frequency').value),capture=DATA.field_samples;
 if(!capture||q==='none'||!Number.isInteger(i)||i<0||i>=capture.points_mm.length)return;
 selectedSample=i;const f=capture[q][fi],p=capture.points_mm[i],unit=q==='electric_field'?'V/m':'A/m';
 const payload={sample_index:i,position_mm:p,frequency_hz:f.frequency_hz,quantity:q,real_xyz:f.real[i],imag_xyz:f.imag[i],complex_vector_norm:magnitude(f,i),units:unit,scope:'Exact saved native output; raw unnormalized Gaussian-pulse DFT, unvalidated'};
 document.querySelector('#probe').textContent=JSON.stringify(payload,null,2);
 document.querySelector('#sample-index').value=String(i);
 const names=DATA.geometry.filter(b=>p.every((v,j)=>v>=Math.min(b.start_mm[j],b.stop_mm[j])&&v<=Math.max(b.start_mm[j],b.stop_mm[j]))).map(b=>b.name);
 const cells=[['Saved sample',String(i)],['Position X / Y / Z (mm)',p.map(v=>v.toFixed(3)).join(' / ')],['Frequency (GHz)',(f.frequency_hz/1e9).toPrecision(5)],['Model region',names.join(', ')||'Outside modeled solids'],['Complex vector norm ('+unit+')',payload.complex_vector_norm.toExponential(6)],...['X','Y','Z'].map((a,j)=>[a+' real / imaginary ('+unit+')',f.real[i][j].toExponential(6)+' / '+f.imag[i][j].toExponential(6)])];
 const escapeText=v=>String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
 document.querySelector('#probe-inspector').innerHTML='<h3>Probe measurement · raw pulse DFT</h3><table>'+cells.map(([a,b])=>'<tr><th scope="row">'+escapeText(a)+'</th><td>'+escapeText(b)+'</td></tr>').join('')+'</table><p>Native sample, not an interpolated display color. Physical accuracy and field normalization remain unqualified.</p>';
 if(locate){const d=({xy:2,xz:1,yz:0})[document.querySelector('#slice-plane').value],depths=[...new Set(capture.points_mm.map(v=>v[d]))].sort((a,b)=>a-b);document.querySelector('#slice-index').value=String(depths.indexOf(p[d]));}
 scene();
}

function peakSlice(){
 const q=document.querySelector('#field-quantity').value;if(!DATA.field_samples||q==='none')return;
 const f=DATA.field_samples[q][Number(document.querySelector('#field-frequency').value)],points=DATA.field_samples.points_mm;
 let peak=0,maximum=-1;f.real.forEach((vec,i)=>{const norm=vec.reduce((sum,a,j)=>sum+a*a+f.imag[i][j]*f.imag[i][j],0);if(norm>maximum){maximum=norm;peak=i;}});
 const d=({xy:2,xz:1,yz:0})[document.querySelector('#slice-plane').value],positions=[...new Set(points.map(p=>p[d]))].sort((a,b)=>a-b);
 document.querySelector('#slice-index').value=String(positions.indexOf(points[peak][d]));document.querySelector('#field-view').value='slice';inspectSample(peak,true);
}
function fieldSlice(){
 const q=document.querySelector('#field-quantity').value,fi=Number(document.querySelector('#field-frequency').value),f=DATA.field_samples[q][fi],points=DATA.field_samples.points_mm;
 const axes=[0,1,2].map(j=>[...new Set(points.map(p=>p[j]))].sort((a,b)=>a-b));
 const plane=document.querySelector('#slice-plane').value,[h,v,d]=({xy:[0,1,2],xz:[0,2,1],yz:[1,2,0]})[plane];
 const slider=document.querySelector('#slice-index');slider.max=axes[d].length-1;const index=Math.max(0,Math.min(Number(slider.value)||0,Number(slider.max)));slider.value=String(index);
 document.querySelector('#slice-position').textContent='XYZ'[d]+' = '+axes[d][index].toFixed(3)+' mm ('+(index+1)+' / '+axes[d].length+')';
 const values=f.real.map((vec,i)=>Math.sqrt(vec.reduce((sum,a,j)=>sum+a*a+f.imag[i][j]*f.imag[i][j],0)));
 const z=axes[v].map(()=>axes[h].map(()=>null)),custom=axes[v].map(()=>axes[h].map(()=>null));
 points.forEach((p,i)=>{if(p[d]!==axes[d][index])return;const row=axes[v].indexOf(p[v]),column=axes[h].indexOf(p[h]);z[row][column]=values[i];custom[row][column]={sample_index:i,position_mm:p,frequency_hz:f.frequency_hz,quantity:q,units:q==='electric_field'?'V/m':'A/m',real_xyz:f.real[i],imag_xyz:f.imag[i],complex_vector_norm:values[i]};});
 const unit=q==='electric_field'?'V/m':'A/m';
 const shapes=[];
 for(const b of DATA.geometry){
  if(document.querySelector('#boards').value!=='both'&&!b.name.startsWith(document.querySelector('#boards').value+'.'))continue;
  const a=b.start_mm,t=b.stop_mm,cut=Math.min(a[d],t[d])<=axes[d][index]&&axes[d][index]<=Math.max(a[d],t[d]);
  shapes.push({type:'rect',x0:Math.min(a[h],t[h]),x1:Math.max(a[h],t[h]),y0:Math.min(a[v],t[v]),y1:Math.max(a[v],t[v]),
   fillcolor:!cut?'rgba(0,0,0,0)':b.kind==='dielectric'?'rgba(141,235,215,.07)':'rgba(255,255,255,.04)',
   line:{color:b.kind==='dielectric'?'#8debd7':'#ffffff',width:1.5,dash:cut?'solid':'dash'},layer:'above'});
 }
 document.querySelector('#field-resolution').textContent='Saved grid: '+axes.map(a=>a.length).join(' × ')+'; displayed slice: '+axes[h].length+' × '+axes[v].length+' native samples.';
 const marker=selectedSample!==null&&points[selectedSample][d]===axes[d][index]?[{type:'scatter',mode:'markers',x:[points[selectedSample][h]],y:[points[selectedSample][v]],marker:{symbol:'cross',size:16,color:'#27e4df',line:{width:2,color:'#102632'}},name:'Selected native sample',customdata:[{sample_index:selectedSample}],hovertemplate:'Selected saved sample %{customdata.sample_index}<extra></extra>'}]:[];
 Plotly.newPlot('scene',[{type:'heatmap',x:axes[h],y:axes[v],z,customdata:custom,zmin:0,zmax:fieldMaximum(q,fi),zsmooth:document.querySelector('#field-smoothing').value==='native'?false:'best',colorscale:'Inferno',colorbar:{title:{text:'Raw '+(q==='electric_field'?'E':'H')+' ('+unit+')',side:'top'},orientation:'h',len:.75,thickness:14,x:.5,y:1.05,xanchor:'center',yanchor:'bottom',tickformat:'.2e'},hovertemplate:'XYZ %{customdata.position_mm} mm<br>Raw norm %{z:.5e} '+unit+'<extra>Saved sample %{customdata.sample_index}</extra>'},...marker],{...layout,xaxis:axis('XYZ'[h]+' (mm)'),yaxis:axis('XYZ'[v]+' (mm)'),shapes,annotations:[{xref:'paper',yref:'paper',x:0,y:1,text:'Translucent board diagram · solid section / dashed projection',showarrow:false,font:{color:'#fff',size:11},bgcolor:'rgba(16,38,50,.8)',xanchor:'left',yanchor:'top'}],margin:{t:100,l:75,r:20,b:65},dragmode:'zoom',showlegend:false},{responsive:true,displaylogo:false});
 document.querySelector('#scene').on('plotly_click',event=>{inspectSample(event.points[0].customdata.sample_index);});
}
function scene(){if(DATA.field_samples&&document.querySelector('#field-quantity').value!=='none'&&document.querySelector('#field-view').value==='slice'){fieldSlice();return;}let traces=[];for(const b of DATA.geometry){if(document.querySelector('#boards').value!=='both'&&!b.name.startsWith(document.querySelector('#boards').value+'.'))continue;const a=b.start_mm,z=b.stop_mm;traces.push({type:'mesh3d',x:[a[0],z[0],z[0],a[0],a[0],z[0],z[0],a[0]],y:[a[1],a[1],z[1],z[1],a[1],a[1],z[1],z[1]],z:[a[2],a[2],a[2],a[2],z[2],z[2],z[2],z[2]],i:[0,0,4,4,0,0,1,1,2,2,3,3],j:[1,2,5,6,1,5,2,6,3,7,0,4],k:[2,3,6,7,5,4,6,5,7,6,4,7],color:b.kind==='dielectric'?'#51a78d':'#d39d3a',opacity:b.kind==='dielectric'?.35:.8,name:b.name,showlegend:false,hovertext:b.name});}
if(DATA.field_samples&&document.querySelector('#field-quantity').value!=='none'){const q=document.querySelector('#field-quantity').value,idx=Number(document.querySelector('#field-frequency').value),f=DATA.field_samples[q][idx],points=DATA.field_samples.points_mm,values=f.real.map((v,i)=>Math.sqrt(v.reduce((sum,a,j)=>sum+a*a+f.imag[i][j]*f.imag[i][j],0)));traces.push({type:'scatter3d',mode:'markers',x:points.map(p=>p[0]),y:points.map(p=>p[1]),z:points.map(p=>p[2]),customdata:points.map((p,i)=>({sample_index:i,frequency_hz:f.frequency_hz,quantity:q,units:q==='electric_field'?'V/m':'A/m',real_xyz:f.real[i],imag_xyz:f.imag[i],complex_vector_norm:values[i]})),marker:{size:3,opacity:.7,color:values,cmin:0,cmax:fieldMaximum(q,idx),colorscale:'Inferno',colorbar:{title:{text:q==='electric_field'?'Raw E (V/m)':'Raw H (A/m)',side:'top'},orientation:'h',len:.7,thickness:14,x:.5,y:1.02,xanchor:'center',yanchor:'bottom',tickformat:'.2s',tickfont:{size:12},outlinewidth:0}},name:'Raw field samples',showlegend:false,hovertemplate:'X %{x:.3f} mm<br>Y %{y:.3f} mm<br>Z %{z:.3f} mm<br>Raw norm %{marker.color:.4e} '+(q==='electric_field'?'V/m':'A/m')+'<extra>Unnormalized DFT</extra>'});}const positions=[[-15,0,-.5],[15,0,-.5],[-15,0,4.5],[15,0,4.5]];traces.push({type:'scatter3d',mode:'markers+text',x:positions.map(p=>p[0]),y:positions.map(p=>p[1]),z:positions.map(p=>p[2]),text:['A.near','A.far','B.near','B.far'],marker:{size:6,color:'#145ece'},name:'Ports',showlegend:false,textposition:'top center'});
Plotly.newPlot('scene',traces,{...layout,scene:{aspectmode:'data',...sceneAxes,domain:{x:[0,1],y:[0,1]}},legend:{orientation:'h',x:0,y:-.04,yanchor:'top'},margin:{t:105,l:10,r:20,b:40}},{responsive:true});document.querySelector('#scene').on('plotly_click',event=>{const p=event.points[0];if(p.customdata){inspectSample(p.customdata.sample_index);return;}document.querySelector('#probe-inspector').innerHTML='';document.querySelector('#probe').textContent=JSON.stringify({object:p.text||p.data.name,position_mm:[p.x,p.y,p.z],native_field_sample:p.customdata||null,scope:p.customdata?'Actual native cell-interpolated volume sample; raw unnormalized Gaussian-pulse DFT, unvalidated':'Model geometry / port position. Surface voltage is not solved.'},null,2);});}
document.querySelector('#probe-sample').onclick=()=>{const f=DATA.field_samples,q=document.querySelector('#field-quantity').value,frame=Number(document.querySelector('#field-frequency').value),i=Number(document.querySelector('#sample-index').value);if(!f||q==='none'||!Number.isInteger(i)||i<0||i>=f.points_mm.length){document.querySelector('#probe').textContent='Select a captured quantity and a valid saved index (0 to 3863).';return;}inspectSample(i,true);};
document.querySelector('#probe-wire').onclick=()=>{const id=document.querySelector('#wire-choice').value,w=DATA.harness_assembly.harnesses[0].extensions['spike.harness-conductors'].wires.find(w=>w.id===id),n=DATA.harness_pi.native_result.data,key=JSON.stringify(['wire',id])+':R';document.querySelector('#harness-probe').textContent=JSON.stringify({conductor:w,solved_dc_current_a:n.element_current_a[key]??'not selected in DC model',solved_dc_power_w:n.element_power_w[key]??'not selected in DC model',remote_load_voltage_v:DATA.harness_validation.pi.load_voltage_v,scope:'Native terminal / lumped-wire solve; no spatial voltage interpolation'},null,2);};
if(document.querySelector('#field-view').value==='slice')peakSlice();else scene();document.querySelector('#slice-peak').onclick=peakSlice;document.querySelector('#field-view').onchange=scene;document.querySelector('#slice-plane').onchange=scene;document.querySelector('#slice-index').oninput=scene;for(const [id,step] of [['#slice-prev',-1],['#slice-next',1]])document.querySelector(id).onclick=()=>{const slider=document.querySelector('#slice-index');slider.value=String(Math.max(0,Math.min(Number(slider.max),Number(slider.value)+step)));scene();};document.querySelector('#field-scale').onchange=scene;document.querySelector('#field-smoothing').onchange=scene;document.querySelector('#boards').onchange=scene;const refreshProbe=()=>{if(selectedSample!==null&&document.querySelector('#field-quantity').value!=='none')inspectSample(selectedSample);else{document.querySelector('#probe-inspector').innerHTML='';scene();}};document.querySelector('#field-quantity').onchange=refreshProbe;document.querySelector('#field-frequency').onchange=refreshProbe;document.querySelector('#reset').onclick=scene;document.querySelector('#harness-data').textContent=JSON.stringify(DATA.harness,null,2);document.querySelector('#screen-data').textContent=JSON.stringify(DATA.screen,null,2);
if(DATA.harness_assembly){const wires=DATA.harness_assembly.harnesses[0].extensions['spike.harness-conductors'].wires;const ht=wires.map(w=>({type:'scatter3d',mode:'lines+markers',x:[0,600],y:[w.properties.cross_section_position_mm[0],w.properties.cross_section_position_mm[0]],z:[w.properties.cross_section_position_mm[1],w.properties.cross_section_position_mm[1]],name:w.id,line:{width:7,color:w.color},customdata:[w,w]}));ht.push({type:'scatter3d',mode:'markers+text',x:[0,600],y:[0,0],z:[8,8],text:['A terminal','B terminal'],textposition:'top center',showlegend:false,marker:{size:8,color:'#184362'},name:'Explicit terminal boards'});Plotly.newPlot('harness-scene',ht,{...layout,scene:{aspectmode:'manual',aspectratio:{x:5,y:1,z:1},xaxis:axis('Along harness (mm)'),yaxis:axis('Cross-section X (mm)'),zaxis:axis('Height above ideal plane (mm)')}},{responsive:true});document.querySelector('#harness-scene').on('plotly_click',e=>{const w=e.points[0].customdata,n=DATA.harness_pi.native_result.data,element=w?JSON.stringify(['wire',w.id])+':R':null;document.querySelector('#harness-probe').textContent=JSON.stringify({conductor:w||e.points[0].text,solved_dc_current_a:element?n.element_current_a[element]??'not selected in DC model':null,solved_dc_power_w:element?n.element_power_w[element]??'not selected in DC model':null,remote_load_voltage_v:DATA.harness_validation.pi.load_voltage_v,scope:'Terminal / lumped-wire results; no spatial voltage interpolation. Display aspect ratio compresses harness length.'},null,2);});const r=DATA.harness_validation.si.frequency_response;Plotly.newPlot('harness-plot',[['differential_next_db','NEXT'],['differential_fext_db','FEXT']].map(([key,name])=>({x:r.map(x=>x.frequency_hz/1e9),y:r.map(x=>Math.max(-160,x[key])),type:'scatter',name,hovertemplate:'%{x:.4g} GHz<br>%{y:.4g} dB<extra>%{fullData.name}</extra>'})),{...layout,xaxis:axis('Frequency (GHz)'),yaxis:axis('Coupling (dB)')},{responsive:true});}
if(DATA.field.frequency_hz){const curves=[1,2,3].map((r)=>({x:DATA.field.frequency_hz.map(f=>f/1e9),y:DATA.field.s_real.map((s,i)=>20*Math.log10(Math.max(Math.hypot(s[r][0],DATA.field.s_imag[i][r][0]),1e-15))),type:'scatter',hovertemplate:'%{x:.4g} GHz<br>%{y:.4g} dB<extra>%{fullData.name}</extra>',name:['','S21','S31 near','S41 far'][r]}));Plotly.newPlot('coupling',curves,{...layout,xaxis:axis('Frequency (GHz)'),yaxis:axis('S magnitude (dB)')},{responsive:true});}

for(const id of [...DATA.protocols.flatMap(c=>['plot-'+c.id,'eye-'+c.id]),'harness-plot','coupling']){
 const plot=document.querySelector('#'+id);
 plot.on('plotly_click',e=>{
  const p=e.points[0],eye=id.startsWith('eye-'),readout=document.querySelector('#readout-'+id);
  readout.textContent=(p.data.name||'Receiver')+' · '+Number(p.x).toPrecision(6)+(eye?' UI':' GHz')+' · '+Number(p.y).toPrecision(6)+(eye?' V':id==='coupling'||id==='harness-plot'?' dB':' dB V/V')+' · saved plotted point';
 });
}
</script></html>'''
    (OUT/'index.html').write_text(template.replace('NAV',nav).replace('CONTENT',content).replace('REVIEW',review).replace('HARNESS_GUIDE',harness_guide).replace('FIELD_GUIDE',field_guide).replace('PAYLOAD',payload),encoding='utf-8')
if __name__=='__main__':main()
