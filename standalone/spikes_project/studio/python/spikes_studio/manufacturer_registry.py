"""Reference directory, deliberately separate from executable part records.

Finding a downloadable model is not qualification or redistribution permission.
Only metadata and public source URLs belong in this directory.
"""
from collections import Counter

SOURCES = ({
    'manufacturer': 'Texas Instruments', 'part_number': 'LM358',
    'description': 'Dual operational amplifier; use the exact device/version model, not LM358B assumptions.',
    'product_url': 'https://www.ti.com/product/LM358',
    'model_url': 'https://www.ti.com/lit/zip/SNOM268',
    'model_title': 'LMx58_LM2904 PSpice Model (Rev. C)',
    'checked_on': '2026-09-06',
    'state': 'source_identified_not_qualified',
    'redistribution': 'Not reviewed; model files are not included.',
    'compatibility': 'Not tested against the downloaded archive; no native execution approval.',
    'required_checks': [
        'Review archive-specific license and redistribution terms.',
        'Record archive hash, revision, model names and electrical pin order.',
        'Inventory all dependent subcircuits, expressions and primitive models.',
        'Run parser, operating-point, AC, slew/overload and supply-range tests.',
        'Compare equal-model reference-engine results and document exclusions.',
    ],
},)

# Official product listings checked 2026-09-06. These are acquisition targets,
# not renamed ideal parts or claims of electrical equivalence.
for part,category,title in (
    ('LM393','Jelly-bean comparators','LM393 PSpice Model'),
    ('TL431','References / power','TL431 Family Unencrypted PSpice Transient and AC Model'),
    ('OPA197','Precision analog','OPAx197 PSpice Model'),
    ('SN74HC14','Digital logic','SN74HC14 Behavioral SPICE Model'),
):
    SOURCES += ({**SOURCES[0], 'part_number':part,'description':category,
                 'product_url':'https://www.ti.com/product/'+part,
                 'model_url':'https://www.ti.com/product/'+part+'#design-tools-simulation',
                 'model_title':title},)

LM358_INSPECTION = {
    'historical_context':'Captured before scoped diode .model support was added. That specific restriction is fixed; the complete TI model has not been requalified and other model/expression requirements remain unsupported.',
    'checked_on':'2026-09-06','archive_sha256':'d3b7b2089c35518ab9f0f05290cf7856297e2680a40b0a731640923203a6dcc2',
    'member':'lmx58_lm2904.lib','member_sha256':'467a3e573420d1f5a21fab57b76be0e13073e854f609a73459a191958e314726',
    'declared_pins':['IN+','IN-','VCC','VEE','OUT'],
    'parser_result':'Rejected: .model cards are supported only at top level in this bounded slice.',
    'execution':'Not attempted because parsing failed.',
    'redistribution':'Archive inspected in memory only; no vendor source bundled.',
}


def capability_summary(records):
    """Do not turn parameter-grid count or a vendor name into qualification."""
    counts = Counter(r.get('status') for r in records)
    qualified = sum(bool(r.get('manufacturer')) and
                    r.get('qualification') == 'manufacturer_qualified' and
                    bool(r.get('qualification_evidence')) for r in records)
    return {'presets': len(records),
            'archetypes': len({r.get('family') for r in records}),
            'native': counts['native_subcircuit'],
            'bench_only': counts['equation_bench_only'],
            'manufacturer_qualified': qualified}


def source_report():
    lines = ['Manufacturer model sources — NOT installed components',
             'Public availability does not establish compatibility or permission to redistribute.', '']
    for item in SOURCES:
        lines.extend([f"{item['manufacturer']} · {item['part_number']}",
                      item['description'], item['model_title'],
                      'Verified listing: ' + item['checked_on'],
                      'Product: ' + item['product_url'], 'Model: ' + item['model_url'],
                      item['redistribution'], item['compatibility'], 'Qualification gates:'])
        lines.extend('  • ' + check for check in item['required_checks'])
        lines.append('')
    lines.extend(['Actual LM358 archive inspection:', str(LM358_INSPECTION)])
    return '\n'.join(lines)
