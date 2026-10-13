# SPDX-License-Identifier: Apache-2.0
"""Build the comprehensive PDF from recorded solver benchmark evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, PolyLine, String, Circle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[1]
BLUE = colors.HexColor('#234E70')
GRAY = colors.HexColor('#5B6470')


def number(value, digits=5):
    if value is None:
        return 'not recorded'
    return f'{value:.{digits}g}'


def build(directory: Path):
    directory = directory.resolve()
    paths = {
        'baseline': ROOT / 'docs/validation/SOLVER_ACCURACY_BASELINE_20261012.json',
        'thermal': directory / 'thermal/thermal_benchmark_summary.json',
        'cooling': directory / 'thermal/thermal_cooling_environment_validation.json',
        'thermal_integration': directory / 'thermal/report_integration_summary.json',
        'thermal_transient': directory / 'thermal/transient_thermal_validation.json',
        'thermal_first_failure': directory / 'thermal/transient_full_workflow_failure.json',
        'si_magnetic': directory / 'si-magnetic-final/results.json',
        'pwm': directory / 'pwm/evidence.json',
        'em': directory / 'em/validation-summary.json',
        'em_fields': directory / 'em/spatial/field-reference.json',
    }
    data = {key: json.loads(path.read_text(encoding='utf-8')) for key, path in paths.items()}
    em_execution = {}
    for name in ('base', 'duration', 'pml-distance', 'spatial', 'spatial-duration'):
        run_dir = directory / 'em' / name
        run = json.loads((run_dir / 'bound-result.json').read_text())
        log = (run_dir / 'solver.log').read_text(errors='replace')
        match = re.search(r'Time for\s+(\d+)\s+iterations with\s+([\d.]+)\s+cells\s*:\s*([\d.]+)\s*sec', log)
        em_execution[name] = {'status': run['status'], 'execution': run['execution'],
                              'termination': run['termination'],
                              'trusted_worker_sha256': run.get('trusted_worker_sha256'),
                              'native_log_timing': {'iterations': int(match[1]), 'cells': float(match[2]),
                                                    'seconds': float(match[3])} if match else None}
    data['em_execution'] = em_execution
    # Never silently replace missing current results with an older reference report.
    b, th, sm, pwm, em = (data[k] for k in ('baseline', 'thermal', 'si_magnetic', 'pwm', 'em'))
    circuits = b['executed_reports']['circuit_comparison']
    tc = th['cases']
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('BodyReport', fontName='Helvetica', fontSize=10.5, leading=15,
                              spaceAfter=9, textColor=colors.black))
    styles.add(ParagraphStyle('CellReport', fontName='Helvetica', fontSize=9, leading=12,
                              spaceAfter=0, textColor=colors.black))
    styles.add(ParagraphStyle('SmallReport', fontName='Helvetica', fontSize=8.5, leading=11.5,
                              spaceAfter=7, textColor=GRAY))
    styles.add(ParagraphStyle('TitleReport', fontName='Helvetica-Bold', fontSize=25, leading=30,
                              spaceAfter=17, textColor=colors.black))
    styles.add(ParagraphStyle('HeadingReport', fontName='Helvetica-Bold', fontSize=18, leading=23,
                              spaceAfter=13, textColor=colors.black))
    styles.add(ParagraphStyle('SubReport', fontName='Helvetica-Bold', fontSize=12, leading=16,
                              spaceBefore=8, spaceAfter=7, textColor=colors.black))
    story = []
    def p(text, style='BodyReport'):
        story.append(Paragraph(text, styles[style]))
    def heading(text):
        p(text, 'SubReport')
    def page(title, first=False):
        if not first:
            story.append(PageBreak())
        p(title, 'TitleReport' if first else 'HeadingReport')
    def table(headers, rows, widths):
        cells = [[Paragraph('<b>' + escape(str(v)) + '</b>', styles['CellReport']) for v in headers]]
        cells += [[Paragraph(escape(str(v)), styles['CellReport']) for v in row] for row in rows]
        t = Table(cells, colWidths=widths, repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8EDF2')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LINEBELOW', (0, 0), (-1, 0), .7, BLUE),
            ('LINEBELOW', (0, 1), (-1, -1), .3, colors.HexColor('#D9DEE4')),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))
    def chart(x, series, unit):
        # ReportLab vector plot: one unit per panel, logarithmic error axis.
        d = Drawing(470, 190)
        left, bottom, width, height = 58, 38, 340, 126
        vals = [v for _, values in series for v in values if v > 0]
        low, high = math.floor(math.log10(min(vals))), math.ceil(math.log10(max(vals)))
        if low == high:
            high += 1
        for power in range(low, high + 1):
            yy = bottom + height * (power - low) / (high - low)
            d.add(Line(left, yy, left + width, yy, strokeColor=colors.HexColor('#D9DEE4')))
            d.add(String(5, yy - 3, f'1e{power} {unit}', fontSize=8))
        palette = [BLUE, colors.HexColor('#A15C38'), colors.HexColor('#427960')]
        for index, (name, values) in enumerate(series):
            points = []
            for j, v in enumerate(values):
                xx = left + width * j / max(1, len(x) - 1)
                yy = bottom + height * (math.log10(v) - low) / (high - low)
                points.extend([xx, yy])
                d.add(Circle(xx, yy, 3, fillColor=palette[index], strokeColor=palette[index]))
            d.add(PolyLine(points, strokeColor=palette[index], strokeWidth=1.5))
            d.add(String(left + index * 130, 176, name, fontSize=9, fillColor=palette[index]))
        for j, label in enumerate(x):
            d.add(String(left + width * j / max(1, len(x) - 1) - 12, 19, str(label), fontSize=9))
        story.append(d)

    page('SPIKE solver accuracy and performance report', first=True)
    p('Thermal PI SI EM and coupled electrothermal studies', 'SubReport')
    p('12 October 2026 | Local Windows evidence | Experimental numerical scope', 'SmallReport')
    p('<b>Conclusion.</b> SPIKE demonstrates accurate bounded analytical solutions and useful '
      'cross-program agreement for selected electrical, solid thermal and retained EM cases. '
      'The fresh runs establish working PI/SI-volume thermal coupling, native PWM-volume feedback, '
      'and stationary magnetic-thermal coupling. They do not establish general hardware accuracy '
      'or arbitrary full-wave EM plus SPICE plus thermal feedback.')
    table(['Area', 'Established evidence', 'Qualification boundary'], [
        ['PI and circuit', '15 permanent checks; 9 shared cases in SPIKES, ngspice and LTspice', 'Simple cases; approximate geometry C/G'],
        ['Thermal', 'Fresh CalculiX steady and transient comparisons', 'Synthetic fixtures and retained package replay'],
        ['SI', 'Exact matched lossless-line complex transfer and loading', 'Supplied RLGC; no measured geometry prediction'],
        ['EM', 'Fresh finite-plate capacitance, field and sensitivity checks', 'External openEMS; quasistatic reference scope'],
        ['Coupled studies', 'DC/AC volume, PWM volume and planar magnetic thermal', 'Bounded models; explicit heat mappings'],
    ], [83, 203, 184])
    p('<b>Disagreement retained.</b> The nonuniform PWM thermal comparison differs by '
      f"{number(pwm['nonuniform_cross_solver_difference_k'])} K. Coarse transient thermal meshes "
      'can also fail the cross-engine gate. Passing simple or uniform cases must not conceal these results.')
    p('This report separates fresh execution, earlier execution in this chat, historical evidence, '
      'analytical verification, cross-code agreement and unavailable coupling. No production solver '
      'or default was changed to obtain these results. Raw evidence and machine-readable reports accompany the PDF.')

    page('Scope methodology and acceptance')
    p('The requested scope covers thermal, PI, SI and EM individually, electrical-to-thermal '
      'feedback, SPICE-related thermal paths, and SI/EM-related thermal paths. Accuracy is primary. '
      'Runtime is reported only for the stated fixture and measurement boundary; there is no overall speed ranking.')
    table(['Evidence class', 'What it establishes', 'What it cannot establish'], [
        ['Analytical or manufactured', 'Agreement with a derived mathematical solution', 'Correct physical material and geometry models'],
        ['Discrete oracle', 'Agreement with a stated numerical discretization', 'Continuum accuracy or method independence'],
        ['Cross-program', 'Agreement on matched inputs and observables', 'Freedom from shared model errors'],
        ['Refinement', 'Sensitivity to spatial/time resolution', 'Physical validation without experiment'],
        ['Measurement correlation', 'Predictive agreement with uncertainty-aware observations', 'Not newly established in this report'],
    ], [112, 178, 180])
    heading('Case controls')
    p('Inputs, units, temperatures, phasor convention, sampling times, boundaries, source/load models '
      'and tolerances are retained. Existing harness thresholds are unchanged. New analytical harness '
      'gates are declared in source before execution. Missing data are not zero-filled. Failed cases '
      'and environment errors are preserved; missing or unsupported scenarios do not pass.')
    heading('Convergence and uncertainty')
    p('Temporal and spatial refinement are separate experiments. Balance residuals measure '
      'equation closure rather than physical prediction error. Observed order and Richardson/GCI '
      'reasoning require appropriate smoothness and asymptotic behavior [1]. The EM electric-field '
      'comparison is a scoped correlation rather than demonstrated decreasing field error.')
    p('The workspace has concurrent uncommitted changes. Reports bind to recorded binary/input '
      'hashes and relevant source snapshots. No universal percentage accuracy, confidence interval '
      'or production-qualified operating envelope is inferred.')

    page('PI extraction and circuit comparison')
    analytic = b['executed_reports']['analytical']
    p(f"The earlier run in this chat passed {analytic['summary']['passed']} of "
      f"{analytic['summary']['total']} permanent checks with no skips. Twelve report numeric "
      'reference errors; three test topology, execution or monotonicity. The largest numeric '
      'relative errors were 2.5% for square-sheet resistance and 2.2452% for a wide-microstrip '
      'capacitance limiting case. These are not general PCB field-solver comparisons.')
    rows = []
    for records in zip(*(e['cases'] for e in circuits['engines'])):
        rows.append([records[0]['case']['case_id']] +
                    [number(r['maximum_absolute_error']) for r in records] +
                    [number(records[0]['case']['absolute_tolerance'])])
    table(['Shared case', 'SPIKES V', 'ngspice V', 'LTspice V', 'Gate V'], rows, [166, 76, 76, 76, 76])
    p('All nine scalar cases passed in each engine. The converter, RF and motor cases are ideal '
      'electrical surrogates. Different source-edge and integration settings contribute to the '
      'observed differences. One repetition does not support a speed or robustness ranking.')
    heading('Verified accuracy improvement through timestep selection')
    steps = b['executed_reports']['timestep']['cases'][0]['levels']
    p('For the finite-ramp RC and RL endpoint, requested steps of 1, 0.5 and 0.25 us reduced '
      'SPIKES absolute error from 36.404 to 9.103 to 2.276 uV. Quartering the step improved '
      'this endpoint about sixteenfold; observed order is near two. The production default was unchanged.')
    p('Evidence IDs: baseline analytical, competitive and timestep reports. Full values, cases, '
      'binary hashes and accepted model approximations are embedded in report-data.json.', 'SmallReport')

    page('Solid thermal accuracy and refinement')
    p('Fresh solid thermal results include same-input comparisons with separately installed '
      'CalculiX 2.23, analytical insulated heating and spatial/temporal refinement. '
      'Small steady-slab agreement is substantially tighter than coarse nonuniform transient agreement.')
    spatial = tc['transient_internal_calculix_core']['measured']['spatial_refinement']
    table(['Subdivisions', 'Nodes / tetrahedra', 'SPIKE analytic RMS K', 'CalculiX analytic RMS K', 'Max pairwise K'],
          [[r['subdivisions'], f"{r['nodes']} / {r['tetrahedra']}", number(r['spike_analytic_rms_error_k']),
            number(r['calculix_analytic_rms_error_k']), number(r['comparison']['maximum_absolute_error_k'])]
           for r in spatial], [76, 97, 100, 100, 97])
    p('Both analytic RMS errors decrease with refinement. The coarse comparison fails; '
      'finer comparisons pass the pre-existing per-node gate of 0.05 K plus 5% of the '
      'reference temperature change. Therefore a passing row can exceed 0.05 K in maximum '
      'absolute difference. No threshold was enlarged after seeing the results.')
    solid = data['thermal_integration']['cases'][-1]
    p(f"The fresh steady convection/radiation slab has analytical errors of "
      f"{number(solid['cooling_spike_analytic_error_k'])} K for SPIKE and "
      f"{number(solid['cooling_calculix_analytic_error_k'])} K for CalculiX. "
      f"Contact temperature discrepancy is {number(solid['contact_temperature_difference_k'])} K; "
      f"the relative internal cooling heat-balance residual is {number(solid['cooling_heat_balance_relative_residual'])}.")
    heading('Uniform history and retained package replay')
    p(f"The PWM uniform thermal replay agrees with CalculiX to "
      f"{number(pwm['calculix_uniform_maximum_difference_k'])} K over 81 frames. "
      f"The fresh retained board/package replay has {pwm['retained_board_package_replay']['nodes']} nodes "
      f"and {pwm['retained_board_package_replay']['tetrahedra']} tetrahedra; maximum CalculiX versus "
      f"prepared-step history difference is {number(pwm['retained_board_package_replay']['fresh_calculix_maximum_difference_k'])} K.")
    p('The separately rerun retained STEP multibody transient pipeline also passed: '
      '288 nodes and five frames, 0.0108044 K maximum and 0.00391687 K RMS internal/CalculiX '
      'difference. Its first isolated mesher run failed to find NumPy; a bounded trusted '
      'package-path override resolved that environment failure without a production code change.')
    p('The retained package replay uses the prescribed package heat from its original case. '
      'It is not a fully coupled PWM loss prediction on that package mesh. Temperature precision '
      'and heat-capacity discretization affect cross-engine comparison; a small uniform error '
      'does not certify nonuniform fields, real materials, airflow or hardware.')
    p('The cooling orchestrator overall status remains blocked because OpenFOAM was not requested. '
      'Its solid comparisons passed; no fresh CFD result is inferred from them.', 'SmallReport')

    page('PI and SI coupling to thermal volumes')
    p('Actual execution couples explicit linear circuit resistors to retained 3D thermal volumes. '
      'Heat distribution weights conserve resistor watts; temperatures can update resistance within '
      'the reviewed law. This is steady averaged heating. The backend selected for these fresh '
      'circuit runs was SPIKE Python MNA with SciPy SuperLU; it was not the owned C++ backend.')
    case_keys = ['pi_dc_internal', 'pi_dc_temperature_feedback_internal', 'si_ac_rms_internal',
                 'si_ac_peak_internal', 'pi_dc_calculix_thermal_replay']
    table(['Case', 'Resistor loss W', 'Max temperature K', 'Iterations', 'Median seconds'], [
        [k.replace('_internal', '').replace('_thermal_replay', '').replace('_', ' '),
         number(tc[k]['loss_balance']['electrical_resistor_loss_w']),
         number(max(v['maximum_k'] for v in tc[k]['occurrence_temperatures_k'].values()), 8),
         tc[k]['iterations'], number(tc[k]['timing']['median_s'])] for k in case_keys], [165, 83, 92, 54, 76])
    dc = tc['pi_dc_internal']['independent_oracle']
    p(f"Independent DC loss is 144/6.3 = {number(dc['expected_power_w'], 10)} W; absolute error is "
      f"{number(dc['absolute_error_w'])} W. At 1 kHz, the 1 V RMS source produces "
      '0.07957718735 W; a 1 V peak source produces half that. These checks verify the phasor '
      'convention and conservative electrical-to-thermal mapping.')
    feedback = tc['pi_dc_temperature_feedback_internal']
    p(f"With positive temperature feedback, final power changes to "
      f"{number(feedback['loss_balance']['electrical_resistor_loss_w'], 10)} W. "
      f"Final unrelaxed temperature defect is {number(feedback['last_iteration']['unrelaxed_temperature_defect_k'])} K "
      f"and power defect is {number(feedback['last_iteration']['power_defect_w'])} W. "
      'Checking Ohm law from returned resistances is a consistency check, not an independent '
      'solution of the entire nonlinear spatial fixed point.')
    cc = tc['pi_dc_calculix_thermal_replay']
    p(f"Replacing only the thermal solve with CalculiX gives a maximum nodal difference of "
      f"{number(cc['internal_comparison']['maximum_nodal_temperature_difference_k'])} K. "
      'The electrical circuit is still SPIKE internal MNA. The adapter does not report a global '
      'CalculiX thermal balance, so that field stays unknown.')

    page('SI transmission and magnetic thermal coupling')
    si = sm['si']
    p('The SI fixture supplies lossless RLGC for a 0.37 m, 50 ohm matched line over 2049 '
      'frequencies from DC to 5 GHz. The independent oracle is S21 = exp(-j*2*pi*f*delay), '
      'with delay 1.85 ns. This tests transmission/network algebra, not geometry extraction.')
    table(['Observable', 'Measured maximum error', 'Acceptance'], [
        ['Complex S21', number(si['metrics']['maximum_complex_s21_absolute_error']), '1e-10 absolute'],
        ['Loaded output voltage', number(si['metrics']['maximum_loaded_voltage_absolute_error_v']) + ' V', '1e-10 V'],
        ['Matched reflection magnitude', number(si['metrics']['maximum_s11_magnitude']), 'Informational'],
        ['Matched TDR impedance', number(si['metrics']['maximum_tdr_impedance_error_ohm']) + ' ohm', 'Informational'],
    ], [200, 145, 125])
    heading('Planar magnetic field and thermal feedback')
    mag = sm['magnetostatic']
    p('An independently manufactured unit-square magnetic potential has exact energy 0.1 J. '
      'Energy errors at 4, 8 and 16 subdivisions are 0.00625, 0.0015625 and 0.000390625 J, '
      'giving fourfold improvement per doubling. This synthetic permeability case verifies '
      'the formulation and spatial convergence; it is not a real magnetic material benchmark.')
    mt = sm['magnetic_thermal']
    w = mt['winding_heat_closed_form']
    p(f"Actual returned winding nodal temperature histories match uniform closed-form heating "
      f"within {number(w['maximum_temperature_error_k'])} K. Conductivity-law error is "
      f"{number(w['maximum_conductivity_error_s_m'])} S/m. Eddy heating closes against stored thermal "
      'energy and decreases endpoint differences under coupling timestep refinement.')
    p('The mixed-field refinement norm is dimensionless after explicit 1 Wb/m and 1 K scaling '
      'and uses a 64-step internal numerical reference. It is not an external exact solution. '
      'No FEMM/Maxwell/Elmer or measured magnetic comparison was executed. Stationary planar '
      'eddy heating does not establish rotating machinery, full-wave heating or 3D end effects.')

    page('Retained EM accuracy and stopping sensitivity')
    p('Five fresh openEMS cases vary interior resolution, duration and air margin around two '
      'finite conducting plates in a 14 mm air cavity. A separately written electrostatic '
      'Laplace solve supplies the quasistatic reference. Capacitance comparison uses 250 MHz; '
      'the air-gap vector comparison uses 500 MHz with consistent complex port normalization.')
    table(['Observable', 'Measured result', 'Declared limit', 'Outcome'],
          [[('extended duration capacitance relative error' if key == 'time_refined_capacitance_relative_error'
             else key.replace('_', ' ')), number(value), number(em['limits'][key]),
            'pass' if em['checks'][key] else 'fail'] for key, value in em['metrics'].items()],
          [234, 79, 79, 78])
    fields = data['em_fields']
    p(f"Maximum air-gap complex E-vector discrepancy is "
      f"{100*fields['maximum_relative_complex_vector_error']:.4f}% and RMS discrepancy is "
      f"{100*fields['rms_relative_complex_vector_error']:.4f}% against the finite-box reference. "
      'The 5% field gate is local to selected interior gap samples; it does not qualify '
      'arbitrary field peaks, radiation or magnetic-field accuracy.')
    heading('Important stopping and loss limits')
    p('<b>The 80000-step coarse duration run did not reach its requested -90 dB decay.</b> '
      'It plateaued near -81.74 dB and hit the timestep cap. Its process completed and '
      'its response-sensitivity gate passed; its strict stopping criterion failed. '
      'Default cases have no structured decay success flag, so their retained native logs '
      'are the stopping evidence. Small real '
      'impedances can include negative numerical residuals, so dissipative conductor loss '
      'is unresolved. There is no two-way full-wave thermal feedback in this route.')
    p('Independent capacitance refinement also has electrode-edge singularities. A small '
      'linear-system residual is not a spatial error estimate. Current evidence binds to '
      'this finite-cage geometry, ideal conducting assumptions and reported frequency range.')
    p('The inherited JSON key time_refined_capacitance_relative_error refers to the '
      'spatial-duration case, which changes run duration and decay criteria at the same '
      'mesh. It does not establish independent FDTD timestep refinement.', 'SmallReport')

    page('Native PWM volume electrothermal accuracy')
    p('The fresh experiment advances 80 PWM cycles at 20 kHz with native owned switching '
      'MNA and a retained insulated six-tetrahedron thermal solid. Winding, both switches '
      'and load deposit physical heat; only winding resistance feeds temperature back '
      'into this bounded electrical model. Heat capacity is artificially 0.01 J/K.')
    table(['Electrical step us', 'Current error A', 'Output error V', 'Temperature error K'],
          [[step, number(row['inductor_current_a']), number(row['output_voltage_v']), number(row['temperature_k'])]
           for step, row in zip([2, 1, .5], pwm['electrical_refinement_component_errors'])],
          [112, 119, 119, 120])
    chart(['2 us', '1 us', '0.5 us'], [('Temperature error',
          [v['temperature_k'] for v in pwm['electrical_refinement_component_errors']])], 'K')
    p('All three physical-unit finest-step gates pass: 0.005 A, 0.002 V and 0.005 K. '
      'Each step halving improves error more than 1.5 times. The independent event-aligned '
      'RK4 reference itself agrees under 0.1 to 0.05 us refinement to 2.75e-14 in the '
      'reported maximum component difference.')
    p('Thermal windows of 8, 4 and 2 cycles approach the one-cycle result: endpoint norm '
      'differences are 4.8843e-4, 7.7805e-5 and 1.5308e-5. The norm uses 1 A, 1 V and 1 K '
      'scales; it is a fixture metric. Numerical backward-Euler dissipation is kept separate '
      'from physical device heat. CalculiX replays accepted window heat; it does not '
      'independently solve the switching circuit.')

    page('Disagreements unsupported combinations and risk')
    p(f"The nonuniform thermal cross-code maximum difference is "
      f"<b>{number(pwm['nonuniform_cross_solver_difference_k'])} K</b>; agreement remains false. "
      'Separate matrix oracles identify consistent-P1 versus centroid capacity rules. '
      'Both engines can match their own discrete equations while disagreeing with each other. '
      'The correct next step is a continuum/refinement error budget, not a relaxed gate.')
    table(['Scenario', 'Current capability', 'Evidence or gap'], [
        ['PI DC plus 3D thermal', 'Two-way experimental steady coupling', 'Fresh loss/mapping/thermal checks'],
        ['SI plus 3D thermal', 'One sinusoidal frequency and average resistor heat', 'Fresh RMS/peak checks; no broadband feedback'],
        ['Native SPIKES plus volume thermal', 'Bounded PWM model with winding feedback', 'Fresh independent ODE and thermal replay'],
        ['External ngspice plus thermal', 'Staged electrical loss to thermal handoff', 'One-way; no temperature feedback benchmark'],
        ['Planar magnetic plus thermal', 'Stationary eddy heat and conductivity feedback', 'Fresh analytic/refinement evidence only'],
        ['Full-wave EM plus SPICE plus thermal', 'No general integrated feedback route', 'Unsupported as a general qualified scenario'],
    ], [135, 174, 161])
    p('No measured PCB temperature, VNA/TDR geometry prediction, nonlinear semiconductor '
      'hardware correlation, or commercial multiphysics full-feedback run was established. '
      'External programs agreeing on synthetic data cannot replace these measurements.')
    p('Environment failures and any unresolved native stopping failures are preserved in '
      'the evidence manifest. Solver availability, execution, numerical accuracy and release '
      'qualification remain separate. Knowledgeable human numerical review is required before release.')

    page('Runtime evidence and measurement limits')
    table(['Operation', 'Recorded wall time', 'Timing boundary'], [
        ['PI DC volume coupling', number(tc['pi_dc_internal']['timing']['median_s']) + ' s', 'Median of 5 internal calls'],
        ['PI with temperature feedback', number(tc['pi_dc_temperature_feedback_internal']['timing']['median_s']) + ' s', 'Median of 5 internal calls'],
        ['SI RMS volume coupling', number(tc['si_ac_rms_internal']['timing']['median_s']) + ' s', 'Median of 5 internal calls'],
        ['PI with CalculiX thermal', number(tc['pi_dc_calculix_thermal_replay']['timing']['median_s']) + ' s', 'One coupled call; external process included'],
        ['SI 2049 point line network', number(si['timing_s']['network']) + ' s', 'One in-process operation'],
        ['SI loaded response', number(si['timing_s']['loaded_response']) + ' s', 'One in-process operation'],
        ['SI time-domain processing', number(si['timing_s']['time_domain']) + ' s', 'One in-process operation'],
    ], [186, 97, 187])
    p('The runs share a workstation with other benchmark processes. Internal and external '
      'timing boundaries differ; meshes and outputs differ across domains. No peak-memory, '
      'large-board scaling, thread-scaling or throughput benchmark was established. These '
      'numbers describe fixture usability, not commercial solver speed parity.')
    table(['openEMS case', 'Cells', 'Iterations', 'Native loop seconds'], [
        [name, int(row['native_log_timing']['cells']), row['native_log_timing']['iterations'],
         row['native_log_timing']['seconds']] for name, row in em_execution.items() if row['native_log_timing']],
        [160, 100, 100, 110])
    p('Native-loop times exclude reference construction, process startup, field extraction '
      'and report generation. Five-case completion is not five stopping-converged cases.', 'SmallReport')
    page('Simulation setup and usability assessment')
    heading('Current user workflow')
    p('The source-defined desktop route is Thermal, retained volume setup, then PI / SI '
      'circuit and volume thermal coupling. Users choose a saved circuit and thermal engine, '
      'inspect resistor/volume IDs, specify every heat distribution and temperature law, '
      'and use Prepare, Run and Save. A request JSON editor remains part of the setup.')
    p('There is no universal group of checkboxes that enables arbitrary multiphysics. '
      'Existing package/contact checkboxes are specific selections. The advanced PWM and '
      'magnetic-thermal paths need their own admitted requests. UI source inspection '
      'establishes controls, not a fresh live usability test.')
    p('A future guided setup should select supported physics and direction of coupling, '
      'then require sources, loads, cooling, material laws and reviewed heat maps. Unsupported '
      'combinations should expose their missing route instead of appearing executable.')
    table(['Setup item', 'Current requirement', 'Simplification opportunity'], [
        ['Physics selection', 'PI DC or SI single frequency for volume coupling', 'Offer only implemented coupling combinations'],
        ['Electrical model', 'Saved explicit circuit, sources, loads and returns', 'Guided source/load controls with model scope'],
        ['Heat mapping', 'Every resistor mapped once with normalized cell weights', 'Reviewed component/body selection and coverage display'],
        ['Temperature feedback', 'Explicit coefficient, reference and valid temperature range', 'Material-law form with envelope validation'],
        ['Cooling and contacts', 'Reviewed boundaries, contact resistance and matched faces', 'Guided contacts and cooling controls'],
        ['Execution and persistence', 'Prepare, Run, Save; edits invalidate prior results', 'One supported wizard preserving these admission steps'],
    ], [94, 186, 190])
    p('This is a proposed usability improvement, not an implemented feature or a new '
      'physics capability. Acceptance should include incomplete mappings, incompatible '
      'models, unavailable runtimes, stale results, cancellation and saved-project reopening. '
      'A live wide/narrow-window setup exercise remains separate from numerical benchmark success.')

    page('Improvement priorities and publication references')
    table(['Priority', 'Concrete next action', 'Acceptance evidence'], [
        ['1', 'Resolve nonuniform thermal error budget and discretization comparability', 'Matched continuum/time/mesh refinement; preserve failed row'],
        ['2', 'Extend circuit comparison beyond endpoint scalars', 'Common-time full waveform and AC/device-model cases'],
        ['3', 'Establish geometry-derived SI and magnetic external accuracy', 'Matched independent solver setup and measured coupons'],
        ['4', 'Qualify loss and stopping-sensitive EM observables', 'Conductor-loss reference, field refinement and decay status'],
        ['5', 'Simplify supported coupling setup', 'Guided model/heat mapping; prepare/run/save/reopen acceptance'],
        ['6', 'Measure production-scale performance', 'Fixed accuracy budgets; repeated timing, memory and scaling'],
    ], [52, 207, 211])
    p('Published sources guide methodology and future case selection. The executed fixtures '
      'here are independently authored; no external implementation or benchmark mesh was copied. '
      'The following references are not claimed as newly executed NAFEMS or hardware benchmarks.')
    refs = [
        ('1', 'NASA NPARC spatial convergence and Richardson/GCI assumptions', 'https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html'),
        ('2', 'ngspice electrothermal tutorial and temperature-dependent model context', 'https://ngspice.sourceforge.io/ngspice-electrothermal-tutorial.html'),
        ('3', 'MOOSE NAFEMS T3 transient thermal verification candidate', 'https://mooseframework.inl.gov/moose/modules/heat_transfer/nafems_t3_verif.html'),
        ('4', 'Rosa and Grover analytical inductance lineage, DOI 10.6028/bulletin.185', 'https://doi.org/10.6028/bulletin.185'),
        ('5', 'COMSOL NAFEMS conduction and radiation verification candidate', 'https://doc.comsol.com/6.4/doc/com.comsol.help.models.mph.heat_radiation_1d/heat_radiation_1d.html'),
    ]
    for identifier, title, url in refs:
        p(f'[{identifier}] <link href="{escape(url)}" color="#234E70">{escape(title)}</link>', 'SmallReport')
    p('Project authority: docs/SOLVER_STATUS.md, CONTRIBUTING.md and docs/SOLVER_ACCURACY_PROGRAM.md. '
      'Historical SU2/CFD and broader qualification reports remain separately dated; they '
      'are not counted as fresh runs in this report.', 'SmallReport')

    page('Reproduction and evidence inventory')
    p('Run from the repository root with the recorded local environments and separately '
      'installed runtimes. Use new output directories to preserve evidence. Report-data.json '
      'contains the complete compact result records; report-manifest.json binds their bytes '
      'and the PDF to source and raw-evidence paths.')
    commands = [
        '.venv/Scripts/python.exe scripts/validate_retained_assembly_em.py --output output/new-em',
        '.venv/Scripts/python.exe scripts/validate_retained_em_field_scaling.py output/new-em/spatial',
        '.venv/Scripts/python.exe examples/converter/run_pwm_volume_validation.py --library build-peec-native/spikes_c_api.dll --output-dir output/new-pwm',
        'build/qualification-py311/Scripts/python.exe scripts/benchmark_thermal_coupling_accuracy.py --output output/new-thermal.json --internal-repetitions 5 --include-transient-core',
        'build/qualification-py311/Scripts/python.exe scripts/benchmark_si_magnetic_accuracy.py --output-dir output/new-si-magnetic',
        'python scripts/benchmark_circuit_timestep_accuracy.py --library build-spikes-sine-20261012/Release/spikes_c_api.dll --output output/new-timestep',
    ]
    for command in commands:
        p(escape(command), 'SmallReport')
    heading('Evidence files')
    for key, path in paths.items():
        p(f'<b>{escape(key)}</b> | {escape(str(path.relative_to(ROOT)).replace(chr(92), "/"))}', 'SmallReport')
    p('The two owned circuit DLLs used in earlier scalar and PWM-volume runs have different '
      'hashes and are not treated as identical builds. Native-module routing and Python '
      'versions differ between benchmark families. The full underlying EM fields and '
      'external thermal histories are retained locally; portable sharing requires the '
      'raw evidence as well as the compact manifest.')
    p('Publication should bind to an immutable source/build release, semantic engine '
      'versions, independently reviewed fixtures and uncertainty-aware measurements. '
      'This local report is an engineering accuracy assessment, not release certification.')
    p('Verification performed for this extension: 9 focused circuit-volume tests, 10 '
      'SI/magnetic-thermal tests, and 10 PWM/independent-EM tests executed successfully '
      'across separate invocations. An initial native class skip was resolved by supplying '
      'its explicit DLL setting. Architecture checks passed. Full Python discovery, '
      'frontend/Rust builds and installed GUI acceptance were not repeated.', 'SmallReport')

    data_path = directory / 'report-data.json'
    data_path.write_text(json.dumps({'contract': 'spike/comprehensive-accuracy-report-data/v1',
        'generated_utc': datetime.now(timezone.utc).isoformat(), 'all_solver_qualified': False,
        'reports': data}, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    output = directory / 'SPIKE_solver_accuracy_and_performance_report.pdf'
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#D9DEE4'))
        canvas.line(54, 43, 558, 43)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(GRAY)
        canvas.drawString(54, 29, 'SPIKE | Experimental numerical evidence | 12 October 2026')
        canvas.drawRightString(558, 29, str(doc.page))
        canvas.restoreState()
    document = SimpleDocTemplate(str(output), pagesize=letter, rightMargin=71, leftMargin=71,
                                 topMargin=48, bottomMargin=58, title='SPIKE solver accuracy and performance report',
                                 author='SPIKE engineering benchmark program')
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    manifests = {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in [*paths.values(), data_path, output, Path(__file__)]}
    (directory / 'report-manifest.json').write_text(json.dumps({
        'contract': 'spike/comprehensive-accuracy-report-manifest/v1',
        'repository_root': str(ROOT), 'sha256': manifests,
        'claims': {'all_solver_qualified': False, 'new_hardware_correlation': False}},
        indent=2) + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-directory', type=Path, required=True)
    build(parser.parse_args().evidence_directory)
