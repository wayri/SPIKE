#include "spike_wx/report_writer.hpp"

#include <fstream>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace spike::wxui {
namespace {

std::string Html(std::string value) {
    std::string output;
    output.reserve(value.size());
    for (const char character : value) {
        switch (character) {
            case '&': output += "&amp;"; break;
            case '<': output += "&lt;"; break;
            case '>': output += "&gt;"; break;
            case '"': output += "&quot;"; break;
            case '\'': output += "&#39;"; break;
            default: output += character; break;
        }
    }
    return output;
}

std::string ScriptJson(const nlohmann::json& value) {
    std::string data = value.dump();
    std::size_t position = 0;
    while ((position = data.find("</", position)) != std::string::npos) {
        data.replace(position, 2, "<\\/");
        position += 3;
    }
    return data;
}

}  // namespace

std::string ReportWriter::LoadPlotlyRuntime(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Offline Plotly runtime was not found at " + path.string());
    std::ostringstream contents;
    contents << input.rdbuf();
    return contents.str();
}

std::string ReportWriter::BuildHtml(
    std::string project_name,
    const nlohmann::json& design,
    const nlohmann::json& setup,
    const nlohmann::json& result,
    const std::string& plotly_runtime) {
    const auto status = result.value("status", "not_run");
    const auto model_status = result.value("model_status", "unsupported");
    std::ostringstream html;
    html << "<!doctype html><html><head><meta charset='utf-8'>"
         << "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:\">"
         << "<title>" << Html(project_name) << " | SPIKE</title><style>"
         << "body{font:13px Segoe UI,Arial;margin:0;background:#0d141a;color:#d9e2ea}header{background:#17232c;color:#f1f6f8;padding:24px 34px;border-bottom:4px solid #f0b34b}header p{color:#78909d}main{max-width:1400px;margin:auto;background:#101820;padding:28px}h2{color:#f5c36b;border-bottom:1px solid #334650;padding-bottom:7px}.status{padding:12px;color:#d9e2ea;background:#1b2a34;border-left:4px solid #f0b34b}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{border:1px solid #334650;background:#111d24;padding:14px}.plot{height:430px}pre{border:1px solid #2b3b46;background:#0f1920;color:#dce8eb;padding:14px;max-height:380px;overflow:auto;white-space:pre-wrap}@media print{body{background:white;color:#17272f}header{background:#13252d}main{max-width:none;background:white;padding:0}.card{background:white}.plot{height:110mm}section{break-inside:avoid}}"
         << "</style><script>" << plotly_runtime << "</script></head><body><header><h1>SPIKE Engineering Analysis Report</h1><p>"
         << Html(project_name) << "</p></header><main><div class='status'><b>" << Html(status)
         << "</b> | " << Html(model_status) << "</div>"
         << "<section><h2>Interactive results</h2><div class='grid'><div class='card'><div id='field' class='plot'></div></div><div class='card'><div id='series' class='plot'></div></div></div></section>"
         << "<section><h2>Setup</h2><pre id='setup'></pre></section>"
         << "<section><h2>Traceability</h2><pre id='trace'></pre></section>"
         << "<script>const design=" << ScriptJson(design) << ";const setup=" << ScriptJson(setup)
         << ";const result=" << ScriptJson(result) << ";"
         << R"JS(
document.getElementById('setup').textContent=JSON.stringify(setup,null,2);
document.getElementById('trace').textContent=JSON.stringify({analysis_id:result.analysis_id,contract:result.contract,provenance:result.provenance,issues:result.issues},null,2);
const visual=((result.fields||{}).visualization||{}), scalar=visual.scalar_fields||{};
const plotLayout={paper_bgcolor:'#111d24',plot_bgcolor:'#0f1920',font:{color:'#b9cbd1'},xaxis:{gridcolor:'#2b3b46',zerolinecolor:'#40545e'},yaxis:{gridcolor:'#2b3b46',zerolinecolor:'#40545e'},margin:{l:62,r:24,t:48,b:56}};
let metric=Object.keys(scalar).find(k=>Array.isArray(scalar[k])&&scalar[k].length);
if(metric){const s=scalar[metric];Plotly.newPlot('field',[{type:'scattergl',mode:'markers',x:s.map(v=>v.x_mm),y:s.map(v=>v.y_mm),marker:{size:7,color:s.map(v=>v.value),colorscale:'Turbo',colorbar:{title:metric}},text:s.map(v=>`${v.net||''} ${v.layer||''}`),hovertemplate:'x=%{x:.4f} mm<br>y=%{y:.4f} mm<br>%{marker.color}<br>%{text}<extra></extra>'}],{...plotLayout,title:metric,xaxis:{...plotLayout.xaxis,title:'x (mm)',scaleanchor:'y'},yaxis:{...plotLayout.yaxis,title:'y (mm)'}})}else{document.getElementById('field').textContent='No spatial scalar field was reported.'}
function findSeries(value){if(Array.isArray(value)&&value.length>1&&value.every(v=>v&&Number.isFinite(v.frequency_hz)&&Number.isFinite(v.magnitude_ohm)))return {kind:'impedance',rows:value};if(Array.isArray(value)&&value.length>1&&value.every(v=>v&&Number.isFinite(v.time_s)&&Number.isFinite(v.temperature_c)))return {kind:'temperature',rows:value};if(value&&typeof value==='object'){for(const v of Object.values(value)){const hit=findSeries(v);if(hit)return hit}}return null}
const z=findSeries(result.networks||result);
const ts=(result.fields||{}).time_series||visual.time_series||{};
if(z&&z.kind==='impedance'){Plotly.newPlot('series',[{x:z.rows.map(v=>v.frequency_hz),y:z.rows.map(v=>v.magnitude_ohm),mode:'lines',line:{color:'#59c8ca'},name:'|Z|'}],{...plotLayout,title:'Impedance',xaxis:{...plotLayout.xaxis,title:'Frequency (Hz)',type:'log'},yaxis:{...plotLayout.yaxis,title:'Magnitude (ohm)',type:'log'}})}
else if(z&&z.kind==='temperature'){Plotly.newPlot('series',[{x:z.rows.map(v=>v.time_s),y:z.rows.map(v=>v.temperature_c),mode:'lines',line:{color:'#f0b34b'},name:'Temperature'}],{...plotLayout,title:'Thermal transient',xaxis:{...plotLayout.xaxis,title:'Time (s)'},yaxis:{...plotLayout.yaxis,title:'Temperature (C)'}})}
else if(Array.isArray(result.sources)&&result.sources.some(v=>Number.isFinite(v.steady_temperature_c))){Plotly.newPlot('series',[{type:'bar',marker:{color:'#f0b34b'},x:result.sources.map(v=>v.id),y:result.sources.map(v=>v.steady_temperature_c),name:'Temperature'}],{...plotLayout,title:'Compact thermal estimate',yaxis:{...plotLayout.yaxis,title:'Temperature (C)'}})}
else if(Array.isArray(result.nodes)&&result.nodes.some(v=>Number.isFinite(v.steady_temperature_c))){Plotly.newPlot('series',[{type:'bar',marker:{color:'#f0b34b'},x:result.nodes.map(v=>v.reference||v.id),y:result.nodes.map(v=>v.steady_temperature_c),name:'Temperature'}],{...plotLayout,title:'Thermal network estimate',yaxis:{...plotLayout.yaxis,title:'Temperature (C)'}})}
else if(Array.isArray(ts.times_s)&&ts.times_s.length){Plotly.newPlot('series',[{x:ts.times_s,y:ts.times_s.map((_,i)=>i),mode:'lines',line:{color:'#59c8ca'},name:'frame'}],{...plotLayout,title:'Transient output frames',xaxis:{...plotLayout.xaxis,title:'Time (s)'},yaxis:{...plotLayout.yaxis,title:'Frame'}})}
else{document.getElementById('series').textContent='No frequency or transient series was reported.'}
)JS"
         << "</script></main></body></html>";
    return html.str();
}

void ReportWriter::WriteFile(const std::filesystem::path& path, const std::string& html) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("Unable to create report " + path.string());
    output.write(html.data(), static_cast<std::streamsize>(html.size()));
    if (!output) throw std::runtime_error("Unable to finish report " + path.string());
}

}  // namespace spike::wxui
