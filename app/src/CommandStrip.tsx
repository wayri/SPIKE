// SPDX-License-Identifier: Apache-2.0
import { useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import "./CommandStrip.css";

/** A bounded command row. Overflow stays reachable by arrows, scrollbar and keyboard. */
export default function CommandStrip({ children, label, className = "", id, as = "div", trailing }: {
  children: ReactNode;
  label: string;
  className?: string;
  id?: string;
  as?: "div" | "nav";
  trailing?: ReactNode;
}) {
  const generatedId = useId();
  const viewportId = `${id ?? generatedId}-commands`;
  const viewport = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ overflow: false, start: true, end: true });
  const measure = () => {
    const node = viewport.current;
    if (!node) return;
    const remaining = node.scrollWidth - node.clientWidth;
    const next = { overflow: remaining > 1, start: node.scrollLeft <= 1, end: node.scrollLeft >= remaining - 1 };
    setEdges(previous => previous.overflow === next.overflow && previous.start === next.start && previous.end === next.end ? previous : next);
  };
  useLayoutEffect(() => {
    const node = viewport.current;
    if (!node) return;
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    for (const child of node.children) observer.observe(child);
    return () => observer.disconnect();
  }, [children]);
  const move = (direction: number) => {
    const node = viewport.current;
    if (node) node.scrollBy({ left: direction * Math.max(120, node.clientWidth * .7), behavior: "auto" });
  };
  const Tag = as;
  return <Tag id={id} className={`command-strip ${className}`} aria-label={label}>
    <button type="button" className="command-strip-arrow" hidden={!edges.overflow} disabled={edges.start}
      aria-label={`Scroll ${label} left`} aria-controls={viewportId} title={`Previous ${label} commands`} onClick={() => move(-1)}><ChevronLeft size={15} /></button>
    <div ref={viewport} id={viewportId} className="command-strip-viewport" tabIndex={0} role="group" aria-label={`${label} commands`}
      onScroll={measure} onKeyDown={event => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); move(event.key === "ArrowLeft" ? -1 : 1); }
        if (event.key === "Home" || event.key === "End") { event.preventDefault(); event.stopPropagation(); event.currentTarget.scrollTo({ left: event.key === "Home" ? 0 : event.currentTarget.scrollWidth }); }
      }} onFocusCapture={event => {
        const node = event.currentTarget;
        if (!(event.target instanceof HTMLElement) || event.target === node) return;
        const bounds = node.getBoundingClientRect(), target = event.target.getBoundingClientRect();
        if (target.left < bounds.left) node.scrollLeft -= bounds.left - target.left + 4;
        else if (target.right > bounds.right) node.scrollLeft += target.right - bounds.right + 4;
      }}>{children}</div>
    <button type="button" className="command-strip-arrow" hidden={!edges.overflow} disabled={edges.end}
      aria-label={`Scroll ${label} right`} aria-controls={viewportId} title={`More ${label} commands`} onClick={() => move(1)}><ChevronRight size={15} /></button>
    {trailing && <div className="command-strip-trailing">{trailing}</div>}
  </Tag>;
}
