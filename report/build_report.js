/* Builds the BCSE497J final report (DOCX) from report/content/*.md.
 *
 * Page setup follows the template's instructions: A4; margins left 3.81 cm,
 * right/top/bottom 2.54 cm; Times New Roman 12 pt at 1.5 line spacing;
 * chapter heading 16 pt bold, section heading 14 pt caps, subsection 12 pt
 * caps; captions 11 pt; page numbers at the bottom centre (roman for the
 * front matter, arabic from Chapter 1).
 *
 * Content markup (one file per chapter):
 *   # Title {#ch:id}            chapter (numbered automatically)
 *   ## Title {#sec:id}          section, ### subsection
 *   - item / 1. item            bullet / numbered list
 *   ![fig:id](file.png){w=13} Caption        figure (width in cm)
 *   !table[tab:id](json:key){w=a,b,c} Caption  table from assets/tables.json
 *   !table[tab:id]{w=a,b} Caption + following "| a | b |" rows   inline table
 *   ```  code  ```              code listing
 *   $$ text $$                  displayed formula (plain Unicode)
 *   {Macro} number from assets/macros.json; [@fig:id] [@tab:id] [@sec:id] [@ch:id] [@app:id]
 *   *italic*  **bold**  `code`
 *
 * Usage: NODE_PATH=<dir with docx> node report/build_report.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const D = require("docx");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, Footer, AlignmentType,
  HeadingLevel, WidthType, BorderStyle, ShadingType, PageNumber, NumberFormat, TableOfContents, StyleLevel,
  TabStopType, LevelFormat, VerticalAlign, PageBreak,
} = D;

const ROOT = path.resolve(__dirname);
const CONTENT = path.join(ROOT, "content");
const ASSETS = path.join(ROOT, "assets");
const OUT = path.join(ROOT, "out");
const macros = JSON.parse(fs.readFileSync(path.join(ASSETS, "macros.json"), "utf8"));
const tables = JSON.parse(fs.readFileSync(path.join(ASSETS, "tables.json"), "utf8"));
const front = JSON.parse(fs.readFileSync(path.join(CONTENT, "front.json"), "utf8"));

const FONT = "Times New Roman";
const CM = 567; // twips per cm
const TEXT_W = Math.round((21.0 - 3.81 - 2.54) * CM); // usable width in twips
const PX_PER_CM = 96 / 2.54;
const LINE15 = 360;

// ------------------------------------------------------------------ text helpers
function subst(s) {
  return s.replace(/\{([A-Z][A-Za-z]+)\}/g, (m, k) => {
    if (!(k in macros)) throw new Error("unknown macro " + k);
    return macros[k];
  });
}

const labels = {};
function resolveRefs(s) {
  return s.replace(/\[@((?:fig|tab|sec|ch|app):[A-Za-z0-9_-]+)\]/g, (m, k) => {
    if (!(k in labels)) throw new Error("unknown reference " + k);
    return labels[k];
  });
}

function runs(text, base = {}) {
  text = resolveRefs(subst(text));
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, font: FONT, ...base }));
    else if (t.startsWith("*")) out.push(new TextRun({ text: t.slice(1, -1), italics: true, font: FONT, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: "Courier New", ...base, size: base.size ? base.size - 2 : 21 }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: FONT, ...base }));
  return out;
}

const body = (text, opts = {}) => new Paragraph({
  children: runs(text), alignment: AlignmentType.JUSTIFIED,
  spacing: { line: LINE15, after: 120 }, indent: { firstLine: opts.noIndent ? 0 : 720 }, ...opts.p,
});

// ------------------------------------------------------------------ styles
const styles = {
  default: {
    document: { run: { font: FONT, size: 24 }, paragraph: { spacing: { line: LINE15 } } },
  },
  paragraphStyles: [
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: FONT, size: 32, bold: true, color: "000000" },
      paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 0, after: 480, line: 300 }, outlineLevel: 0, keepNext: true } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: FONT, size: 28, bold: false, color: "000000" },
      paragraph: { spacing: { before: 360, after: 180, line: 300 }, outlineLevel: 1, keepNext: true, keepLines: true } },
    { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: FONT, size: 24, bold: false, color: "000000" },
      paragraph: { spacing: { before: 240, after: 120, line: 300 }, outlineLevel: 2, keepNext: true, keepLines: true } },
    { id: "FigureCaption", name: "Figure Caption", basedOn: "Normal", next: "Normal",
      run: { font: FONT, size: 22 }, paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 60, after: 300, line: 240 } } },
    { id: "TableCaption", name: "Table Caption", basedOn: "Normal", next: "Normal",
      run: { font: FONT, size: 22 }, paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 240, after: 120, line: 240 }, keepNext: true } },
    { id: "TOC1", name: "toc 1", basedOn: "Normal", next: "Normal",
      run: { font: FONT, size: 24, bold: true }, paragraph: { spacing: { before: 120, after: 60, line: 276 } } },
    { id: "TOC2", name: "toc 2", basedOn: "Normal", next: "Normal",
      run: { font: FONT, size: 22 }, paragraph: { indent: { left: 360 }, spacing: { before: 0, after: 40, line: 276 } } },
    { id: "TOC3", name: "toc 3", basedOn: "Normal", next: "Normal",
      run: { font: FONT, size: 22 }, paragraph: { indent: { left: 720 }, spacing: { before: 0, after: 40, line: 276 } } },
    { id: "CodeBlock", name: "Code Block", basedOn: "Normal",
      run: { font: "Courier New", size: 16 },
      paragraph: { spacing: { line: 240, before: 0, after: 0 }, indent: { left: 284 } } },
  ],
};

const numbering = {
  config: [{
    reference: "bullets",
    levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
  }],
};

// ------------------------------------------------------------------ front matter
const C = AlignmentType.CENTER;
const p = (text, o = {}) => new Paragraph({ alignment: o.align || C, spacing: { line: o.line || 276, before: o.before || 0, after: o.after || 0 },
  children: [new TextRun({ text, font: FONT, size: o.size || 24, bold: o.bold, italics: o.italics, underline: o.underline ? {} : undefined, allCaps: o.caps })] });
const gap = (n = 1, size = 24) => Array.from({ length: n }, () => new Paragraph({ spacing: { line: 276 }, children: [new TextRun({ text: "", size })] }));
const logo = (wcm = 8.78, hcm = 2.93) => new Paragraph({ alignment: C, children: [new ImageRun({ type: "jpg",
  data: fs.readFileSync(path.join(ASSETS, "vit_logo.jpg")), transformation: { width: wcm * PX_PER_CM, height: hcm * PX_PER_CM } })] });

function coverPage(withIntro) {
  const kids = [];
  if (withIntro) kids.push(p("A project report on", { italics: true, size: 24, after: 240 }));
  else kids.push(...gap(1));
  kids.push(p(front.title.toUpperCase(), { bold: true, size: 40, line: 300, after: 360 }));
  kids.push(p("Submitted in partial fulfillment for the award of the degree of", { italics: true, size: 28, after: 240 }));
  kids.push(p("Bachelor of Technology in " + front.program, { bold: true, size: 44, line: 300, after: 480 }));
  kids.push(p("by", { italics: true, size: 28, after: 240 }));
  for (const m of front.team) kids.push(p(`${m.name} (${m.reg})`, { bold: true, size: 32, caps: true, after: 120 }));
  kids.push(...gap(withIntro ? 3 : 4));
  kids.push(logo());
  kids.push(...gap(1));
  kids.push(p("SCHOOL OF COMPUTER SCIENCE AND ENGINEERING", { bold: true, size: 32, after: 240 }));
  kids.push(p(front.month, { size: 24 }));
  return kids;
}

function declarationPage() {
  const me = front.team[0];
  const justified = (text, after = 240) => new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: LINE15, after }, indent: { firstLine: 720 },
    children: [new TextRun({ text, font: FONT, size: 24 })] });
  return [
    logo(), ...gap(1),
    p("DECLARATION", { bold: true, underline: true, size: 28, after: 480 }),
    justified(`I hereby declare that the thesis entitled “${front.title}” submitted by ${me.name} (${me.reg}), for the award of the degree of Bachelor of Technology in ${front.program}, Vellore Institute of Technology, Chennai is a record of bonafide work carried out by me under the supervision of ${front.guide.name}.`),
    justified("I further declare that the work reported in this thesis has not been submitted and will not be submitted, either in part or in full, for the award of any other degree or diploma in this institute or any other institute or university."),
    ...gap(4),
    new Paragraph({ spacing: { line: 276, after: 240 }, children: [new TextRun({ text: "Place: Chennai", font: FONT, size: 24, bold: true })] }),
    new Paragraph({ spacing: { line: 276 }, tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W }],
      children: [new TextRun({ text: "Date:", font: FONT, size: 24, bold: true }), new TextRun({ text: "\tSignature of the Candidate", font: FONT, size: 24, bold: true })] }),
  ];
}

function certificatePage() {
  const me = front.team[0];
  const line = (a, b, o = {}) => new Paragraph({ spacing: { line: 276, after: o.after ?? 120 }, tabStops: [{ type: TabStopType.LEFT, position: Math.round(TEXT_W * 0.55) }],
    children: [new TextRun({ text: a, font: FONT, size: 24 }), new TextRun({ text: b ? "\t" + b : "", font: FONT, size: 24 })] });
  return [
    logo(),
    p("School of Computer Science and Engineering", { bold: true, size: 26, before: 240, after: 240 }),
    p("CERTIFICATE", { size: 28, bold: true, after: 240 }),
    new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: 312, after: 300 }, indent: { firstLine: 720 }, children: [new TextRun({ font: FONT, size: 24,
      text: `This is to certify that the report entitled “${front.title}” is prepared and submitted by ${me.name} (${me.reg}) to Vellore Institute of Technology, Chennai, in partial fulfilment of the requirement for the award of the degree of Bachelor of Technology in ${front.program} is a bonafide record carried out under my guidance. The project fulfils the requirements as per the regulations of this University and in my opinion meets the necessary standards for submission. The contents of this report have not been submitted and will not be submitted either in part or in full, for the award of any other degree or diploma and the same is certified.` })] }),
    line("Signature of the Guide:"), line(`Name: ${front.guide.name}`), line("Date:", "", { after: 360 }),
    line("Signature of the Examiner", "Signature of the Examiner"), line("Name:", "Name:"), line("Date:", "Date:", { after: 360 }),
    p("Approved by the Head of Department,", { align: AlignmentType.RIGHT, after: 60 }),
    p(`B.Tech. ${front.program}`, { align: AlignmentType.RIGHT, after: 240 }),
    p(`Name: ${front.hod.name}`, { align: AlignmentType.RIGHT, after: 120 }),
    p("Date:", { align: AlignmentType.RIGHT, after: 300 }),
    p("(Seal of the School of Computer Science and Engineering)", { align: AlignmentType.RIGHT, size: 20 }),
  ];
}

function plainHeading(text, o = {}) {
  return new Paragraph({ alignment: o.align || C, spacing: { line: 276, before: 0, after: o.after || 360 },
    children: [new TextRun({ text, font: FONT, size: o.size || 28, bold: true, underline: o.underline ? {} : undefined })] });
}

// front headings listed in the contents (template lists CONTENTS, LIST OF FIGURES, ...)
const frontHeading = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, alignment: AlignmentType.LEFT,
  spacing: { before: 0, after: 360 }, children: [new TextRun({ text, font: FONT, size: 28, bold: true })] });

// ------------------------------------------------------------------ content parsing
const FILES = fs.readdirSync(CONTENT).filter((f) => /^\d\d_.*\.md$/.test(f)).sort();
const docs = FILES.map((f) => ({ file: f, text: fs.readFileSync(path.join(CONTENT, f), "utf8") }));

// pass 1: numbering and labels
(function collect() {
  let ch = 0, sec = 0, sub = 0, fig = 0, tab = 0, app = 0, inApp = false;
  for (const d of docs) {
    for (const raw of d.text.split("\n")) {
      const line = raw.trimEnd();
      let m;
      if ((m = line.match(/^# (.+?)(?:\s*\{#((?:ch|app):[\w-]+)\})?$/))) {
        if (/^Appendices/.test(m[1])) { inApp = true; continue; }
        if (/^References/.test(m[1])) continue;
        ch++; sec = 0; sub = 0; fig = 0; tab = 0;
        if (m[2]) labels[m[2]] = `Chapter ${ch}`;
      } else if ((m = line.match(/^## (.+?)(?:\s*\{#((?:sec|app):[\w-]+)\})?$/))) {
        if (inApp) { app++; fig = 0; tab = 0; if (m[2]) labels[m[2]] = `Appendix ${app}`; continue; }
        sec++; sub = 0; if (m[2]) labels[m[2]] = `Section ${ch}.${sec}`;
      } else if ((m = line.match(/^### (.+?)(?:\s*\{#(sec:[\w-]+)\})?$/))) {
        sub++; if (m[2]) labels[m[2]] = `Section ${ch}.${sec}.${sub}`;
      } else if ((m = line.match(/^!\[(fig:[\w-]+)\]/))) {
        fig++; labels[m[1]] = inApp ? `Figure A${app}.${fig}` : `Figure ${ch}.${fig}`;
      } else if ((m = line.match(/^!table\[(tab:[\w-]+)\]/))) {
        tab++; labels[m[1]] = inApp ? `Table A${app}.${tab}` : `Table ${ch}.${tab}`;
      }
    }
  }
})();

// ------------------------------------------------------------------ renderers
function figure(label, file, wcm, caption) {
  const img = path.join(ASSETS, file);
  const { w, h } = pngSize(img);
  const width = wcm * PX_PER_CM, height = width * h / w;
  return [
    new Paragraph({ alignment: C, keepNext: true, spacing: { before: 240, after: 60, line: 240 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(img), transformation: { width, height } })] }),
    new Paragraph({ style: "FigureCaption", children: [new TextRun({ text: labels[label] + ": ", bold: true, font: FONT, size: 22 }), ...runs(caption, { size: 22 })] }),
  ];
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

function table(label, header, rows, widths, caption) {
  const n = header.length;
  let ws = widths && widths.length === n ? widths : Array(n).fill(1);
  const total = ws.reduce((a, b) => a + b, 0);
  const cols = ws.map((x) => Math.floor(TEXT_W * x / total));
  cols[cols.length - 1] += TEXT_W - cols.reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: "7F7F7F" };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cell = (text, i, head) => new TableCell({
    width: { size: cols[i], type: WidthType.DXA }, borders, verticalAlign: VerticalAlign.CENTER,
    margins: { top: 40, bottom: 40, left: 90, right: 90 },
    shading: head ? { fill: "E7E6E6", type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: [new Paragraph({ spacing: { line: 240, before: 0, after: 0 }, alignment: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
      children: runs(String(text), { size: 20, bold: head || undefined }) })],
  });
  return [
    new Paragraph({ style: "TableCaption", children: [new TextRun({ text: labels[label] + ": ", bold: true, font: FONT, size: 22 }), ...runs(caption, { size: 22 })] }),
    new Table({ width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: cols, alignment: AlignmentType.CENTER,
      rows: [new TableRow({ tableHeader: true, cantSplit: true, children: header.map((h, i) => cell(h, i, true)) }),
        ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) }))] }),
    new Paragraph({ spacing: { line: 240, after: 120 }, children: [] }),
  ];
}

function codeBlock(lines) {
  const border = { style: BorderStyle.SINGLE, size: 6, color: "BFBFBF", space: 4 };
  return lines.map((l, i) => new Paragraph({ style: "CodeBlock", keepLines: true, keepNext: i < lines.length - 1,
    shading: { fill: "F4F4F4", type: ShadingType.CLEAR, color: "auto" },
    border: { left: border, ...(i === 0 ? { top: border } : {}), ...(i === lines.length - 1 ? { bottom: border } : {}) },
    spacing: { line: 240, before: i === 0 ? 120 : 0, after: i === lines.length - 1 ? 200 : 0 },
    children: [new TextRun({ text: l.length ? l : " ", font: "Courier New", size: 16 })] }));
}

function renderDoc(text, state) {
  const out = [];
  const lines = text.split("\n");
  let para = [];
  const flush = () => { if (para.length) { out.push(body(para.join(" "))); para = []; } };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd();
    let m;
    if (!line.trim()) { flush(); continue; }
    if (line.startsWith("<!--")) { flush(); while (i < lines.length && !lines[i].includes("-->")) i++; continue; }
    if ((m = line.match(/^# (.+?)(?:\s*\{#[\w:-]+\})?$/))) {
      flush();
      const title = m[1];
      if (/^(References|Appendices)/.test(title)) {
        state.inApp = /^Appendices/.test(title);
        out.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun({ text: title.toUpperCase(), font: FONT, size: 32, bold: true })] }));
        continue;
      }
      state.ch++; state.sec = 0; state.sub = 0;
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [
        new TextRun({ text: `Chapter ${state.ch}`, font: FONT, size: 24, bold: true }),
        new TextRun({ text: title, font: FONT, size: 32, bold: true, break: 2 }),
      ] }));
      continue;
    }
    if ((m = line.match(/^## (.+?)(?:\s*\{#[\w:-]+\})?$/))) {
      flush();
      if (state.inApp) {
        state.app++;
        out.push(new Paragraph({ heading: HeadingLevel.HEADING_2, pageBreakBefore: state.app > 1, children: [new TextRun({ text: `APPENDIX ${state.app}: ${subst(m[1]).toUpperCase()}`, font: FONT, size: 28 })] }));
        continue;
      }
      state.sec++; state.sub = 0;
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: `${state.ch}.${state.sec} ${subst(m[1]).toUpperCase()}`, font: FONT, size: 28 })] }));
      continue;
    }
    if ((m = line.match(/^### (.+?)(?:\s*\{#[\w:-]+\})?$/))) {
      flush(); state.sub++;
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: `${state.ch}.${state.sec}.${state.sub} ${subst(m[1]).toUpperCase()}`, font: FONT, size: 24 })] }));
      continue;
    }
    if ((m = line.match(/^!\[(fig:[\w-]+)\]\(([^)]+)\)\{w=([\d.]+)\}\s*(.+)$/))) { flush(); out.push(...figure(m[1], m[2], parseFloat(m[3]), m[4])); continue; }
    if ((m = line.match(/^!table\[(tab:[\w-]+)\](?:\(json:(\w+)\))?(?:\{w=([\d.,]+)\})?\s*(.+)$/))) {
      flush();
      const widths = m[3] ? m[3].split(",").map(Number) : null;
      if (m[2]) {
        const t = tables[m[2]];
        if (!t) throw new Error("unknown table " + m[2]);
        out.push(...table(m[1], t.header, t.rows, widths, m[4]));
      } else {
        const rows = [];
        while (i + 1 < lines.length && lines[i + 1].trim().startsWith("|")) {
          i++;
          rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
        }
        out.push(...table(m[1], rows[0], rows.slice(1), widths, m[4]));
      }
      continue;
    }
    if (line.startsWith("```")) {
      flush();
      const code = [];
      while (++i < lines.length && !lines[i].startsWith("```")) code.push(lines[i].replace(/\t/g, "    "));
      out.push(...codeBlock(code));
      continue;
    }
    if ((m = line.match(/^\$\$\s*(.+?)\s*\$\$$/))) {
      flush();
      out.push(new Paragraph({ alignment: C, spacing: { line: LINE15, before: 60, after: 180 }, children: runs(m[1], { italics: true }) }));
      continue;
    }
    if ((m = line.match(/^- (.+)$/))) {
      flush();
      let t = m[1];
      while (i + 1 < lines.length && /^\s{2,}\S/.test(lines[i + 1])) t += " " + lines[++i].trim();
      out.push(new Paragraph({ numbering: { reference: "bullets", level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { line: LINE15, after: 60 }, children: runs(t) }));
      continue;
    }
    if ((m = line.match(/^(\d+)\. (.+)$/))) {
      flush();
      let t = m[2];
      while (i + 1 < lines.length && /^\s{3,}\S/.test(lines[i + 1])) t += " " + lines[++i].trim();
      out.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: LINE15, after: 60 }, indent: { left: 720, hanging: 360 },
        tabStops: [{ type: TabStopType.LEFT, position: 720 }], children: [new TextRun({ text: `${m[1]}.\t`, font: FONT }), ...runs(t)] }));
      continue;
    }
    if ((m = line.match(/^\[(\d+)\]\s+(.+)$/))) { // reference entry
      flush();
      out.push(new Paragraph({ alignment: AlignmentType.LEFT, spacing: { line: 276, after: 160 }, indent: { left: 567, hanging: 567 },
        children: [new TextRun({ text: `[${m[1]}].\t`, font: FONT }), ...runs(m[2])], tabStops: [{ type: TabStopType.LEFT, position: 567 }] }));
      continue;
    }
    if (line.trim() === "@pagebreak") { flush(); out.push(new Paragraph({ children: [new PageBreak()] })); continue; }
    para.push(line.trim());
  }
  flush();
  return out;
}

// ------------------------------------------------------------------ assemble
const footer = (fmt) => new Footer({ children: [new Paragraph({ alignment: C, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 24 })] })] });
const page = (start, fmt) => ({
  size: { width: 11906, height: 16838 },
  margin: { top: Math.round(2.54 * CM), bottom: Math.round(2.54 * CM), right: Math.round(2.54 * CM), left: Math.round(3.81 * CM), footer: 567, header: 567 },
  ...(start ? { pageNumbers: { start, formatType: fmt } } : {}),
});

const abstractText = fs.readFileSync(path.join(CONTENT, "abstract.md"), "utf8").trim().split(/\n\s*\n/);
const ackText = fs.readFileSync(path.join(CONTENT, "acknowledgement.md"), "utf8").trim().split(/\n\s*\n/);
const acronyms = JSON.parse(fs.readFileSync(path.join(CONTENT, "acronyms.json"), "utf8"));

const frontKids = [
  plainHeading("ABSTRACT", { underline: true, after: 480 }),
  ...abstractText.map((t) => (t.startsWith("Keywords:") ? new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: LINE15, before: 240 },
    children: [new TextRun({ text: "Keywords: ", bold: true, font: FONT }), ...runs(t.slice(9).trim())] }) : body(t.replace(/\n/g, " ")))),
  new Paragraph({ children: [new PageBreak()] }),
  plainHeading("ACKNOWLEDGEMENT", { after: 360 }),
  ...ackText.map((t) => body(t.replace(/\n/g, " "), { noIndent: true })),
  ...gap(1),
  new Paragraph({ spacing: { line: 276, after: 200 }, children: [new TextRun({ text: "Place: Chennai", font: FONT, bold: true })] }),
  new Paragraph({ spacing: { line: 276 }, tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W }],
    children: [new TextRun({ text: "Date:", font: FONT, bold: true }), new TextRun({ text: `\t${front.team[0].name}`, font: FONT, bold: true })] }),
  new Paragraph({ children: [new PageBreak()] }),
  frontHeading("CONTENTS"),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-3", preserveNewLineInEntries: true }),
  new Paragraph({ children: [new PageBreak()] }),
  frontHeading("LIST OF FIGURES"),
  new TableOfContents("Figures", { hyperlink: true, stylesWithLevels: [new StyleLevel("Figure Caption", 2)] }),
  new Paragraph({ children: [new PageBreak()] }),
  frontHeading("LIST OF TABLES"),
  new TableOfContents("Tables", { hyperlink: true, stylesWithLevels: [new StyleLevel("Table Caption", 2)] }),
  new Paragraph({ children: [new PageBreak()] }),
  frontHeading("LIST OF ACRONYMS"),
  ...acronymTable(acronyms.acronyms, "Acronym", "Expansion"),
  new Paragraph({ spacing: { before: 360, after: 240, line: 276 }, children: [new TextRun({ text: "LIST OF SYMBOLS", font: FONT, size: 24, bold: true })] }),
  ...acronymTable(acronyms.symbols, "Symbol", "Meaning"),
];

function acronymTable(items, a, b) {
  const cols = [Math.round(TEXT_W * 0.24), TEXT_W - Math.round(TEXT_W * 0.24)];
  const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
  const nb = { top: none, bottom: none, left: none, right: none };
  const row = (x, y, head) => new TableRow({ cantSplit: true, children: [x, y].map((t, i) => new TableCell({ width: { size: cols[i], type: WidthType.DXA }, borders: nb,
    margins: { top: 30, bottom: 30, left: 60, right: 60 },
    children: [new Paragraph({ spacing: { line: 276 }, children: runs(t, { bold: head || undefined }) })] })) });
  return [new Table({ width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: cols, rows: [row(a, b, true), ...items.map(([x, y]) => row(x, y, false))] })];
}

const state = { ch: 0, sec: 0, sub: 0, app: 0, inApp: false };
const mainKids = docs.flatMap((d) => renderDoc(d.text, state));

const doc = new Document({
  creator: front.team[0].name, title: front.title, description: "BCSE497J project report",
  styles, numbering,
  sections: [
    { properties: { page: page() }, children: coverPage(true) },
    { properties: { page: page() }, children: coverPage(false) },
    { properties: { page: page() }, children: declarationPage() },
    { properties: { page: page() }, children: certificatePage() },
    { properties: { page: page(1, NumberFormat.LOWER_ROMAN) }, footers: { default: footer() }, children: frontKids },
    { properties: { page: page(1, NumberFormat.DECIMAL) }, footers: { default: footer() }, children: mainKids },
  ],
});

fs.mkdirSync(OUT, { recursive: true });
const target = path.join(OUT, process.argv[2] || "report.docx");
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(target, buf); console.log("wrote", target, Object.keys(labels).length, "labels"); });
