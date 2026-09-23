import { FileOutput, Printer, X } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import "./reportPreview.css";

const PRINT_MESSAGE = "spike/report-preview/print";

function printableReportDocument(html: string): string {
  const printBridge = `<script>(function(){window.addEventListener("message",function(event){if(event.data==="${PRINT_MESSAGE}"){window.focus();window.print();}});})();<\/script>`;

  return /<\/body\s*>/i.test(html)
    ? html.replace(/<\/body\s*>/i, `${printBridge}</body>`)
    : `${html}${printBridge}`;
}

type ReportPreviewProps = {
  fileName: string;
  html: string;
  onClose: () => void;
  onExport: () => void;
};

export default function ReportPreview({ fileName, html, onClose, onExport }: ReportPreviewProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const previewDocument = useMemo(() => printableReportDocument(html), [html]);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return <div className="report-preview-shade" role="dialog" aria-modal="true" aria-label="Engineering report preview">
    <section className="report-preview">
      <header className="report-preview-toolbar">
        <div>
          <b>Engineering report preview</b>
          <span>{fileName}</span>
        </div>
        <div className="report-preview-actions">
          <button type="button" className="secondary-btn" onClick={() => frameRef.current?.contentWindow?.postMessage(PRINT_MESSAGE, "*")} title="Prints every analyzed net in one sequential document"><Printer size={15} /> Print all nets</button>
          <button type="button" className="secondary-btn" onClick={onExport}><FileOutput size={15} /> Export HTML</button>
          <button type="button" className="canvas-icon" onClick={onClose} title="Close report preview" aria-label="Close report preview"><X size={16} /></button>
        </div>
      </header>
      <iframe
        ref={frameRef}
        className="report-preview-frame"
        title="SPIKE engineering report"
        sandbox="allow-scripts allow-downloads allow-modals"
        srcDoc={previewDocument}
      />
    </section>
  </div>;
}
