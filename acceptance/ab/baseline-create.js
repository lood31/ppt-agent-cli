const pptxgen = require("pptxgenjs");
const fs = require("fs");

const [contentPath, outputPath] = process.argv.slice(2);
if (!contentPath || !outputPath) throw new Error("usage: node baseline-create.js CONTENT.json OUTPUT.pptx");
const content = JSON.parse(fs.readFileSync(contentPath, "utf8"));
const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "ppt-agent acceptance benchmark";
pptx.subject = "Controlled A/B fixture";
pptx.title = content.title;
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN"
};

const C = { ink: "172033", paper: "F7F3EA", coral: "E76F51", teal: "2A9D8F", gold: "E9C46A", muted: "64748B", white: "FFFFFF" };
const shadow = () => ({ type: "outer", color: "000000", blur: 4, offset: 2, angle: 135, opacity: 0.12 });

function base(slide, index, dark = false) {
  slide.background = { color: dark ? C.ink : C.paper };
  slide.addText(String(index + 1).padStart(2, "0"), { x: 12.2, y: 6.9, w: 0.55, h: 0.25, fontFace: "Consolas", fontSize: 10, color: dark ? "A8B2C5" : C.muted, margin: 0, align: "right" });
}
function title(slide, text, dark = false) {
  slide.addText(text, { x: 0.75, y: 0.55, w: 11.8, h: 0.75, fontSize: 30, bold: true, color: dark ? C.white : C.ink, margin: 0, breakLine: false });
}
function bodyRuns(items) {
  return items.map((text, i) => ({ text, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfterPt: 14 } }));
}

content.slides.forEach((item, index) => {
  const slide = pptx.addSlide();
  const dark = index === 0 || index === content.slides.length - 1;
  base(slide, index, dark);
  if (index === 0) {
    slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 0.24, h: 7.5, fill: { color: C.coral }, line: { color: C.coral } });
    slide.addText(item.title, { x: 1.0, y: 2.25, w: 10.8, h: 1.0, fontSize: 42, bold: true, color: C.white, margin: 0 });
    slide.addText(item.body[0], { x: 1.0, y: 3.45, w: 9.4, h: 0.5, fontSize: 21, color: "CBD5E1", margin: 0 });
    slide.addShape(pptx.ShapeType.arc, { x: 10.7, y: 1.1, w: 1.8, h: 1.8, adjustPoint: 0.32, rotate: 25, fill: { color: C.teal, transparency: 10 }, line: { color: C.teal } });
    return;
  }
  title(slide, item.title, dark);
  if (index === 2) {
    const xs = [0.8, 3.95, 7.1, 10.25];
    item.body.forEach((text, i) => {
      slide.addShape(pptx.ShapeType.ellipse, { x: xs[i], y: 2.35, w: 0.68, h: 0.68, fill: { color: i % 2 ? C.coral : C.teal }, line: { color: C.white, transparency: 100 } });
      slide.addText(String(i + 1), { x: xs[i], y: 2.5, w: 0.68, h: 0.25, fontSize: 15, bold: true, align: "center", color: C.white, margin: 0 });
      slide.addText(text, { x: xs[i] - 0.4, y: 3.25, w: 2.6, h: 1.15, fontSize: 16, bold: true, color: C.ink, margin: 0.05, valign: "top" });
      if (i < 3) slide.addShape(pptx.ShapeType.chevron, { x: xs[i] + 1.25, y: 2.48, w: 1.05, h: 0.36, fill: { color: C.gold }, line: { color: C.gold } });
    });
  } else if (index === 3) {
    item.body.forEach((text, i) => {
      const x = 0.9 + i * 6.15;
      slide.addShape(pptx.ShapeType.rect, { x, y: 1.75, w: 5.55, h: 3.9, fill: { color: C.white }, line: { color: i ? C.teal : C.coral, width: 3 }, shadow: shadow() });
      slide.addText(i ? "B  ppt-agent" : "A  原 pptx skill", { x: x + 0.35, y: 2.15, w: 4.8, h: 0.45, fontSize: 20, bold: true, color: i ? C.teal : C.coral, margin: 0 });
      slide.addText(text, { x: x + 0.35, y: 3.0, w: 4.75, h: 1.6, fontSize: 18, color: C.ink, margin: 0, breakLine: false, valign: "mid" });
    });
  } else if (index === 4) {
    item.body.forEach((text, i) => {
      const x = 0.85 + i * 4.15;
      slide.addShape(pptx.ShapeType.rect, { x, y: 2.05, w: 3.65, h: 3.05, fill: { color: i === 0 ? C.ink : C.white }, line: { color: i === 0 ? C.ink : "D9D5CB", width: 1 }, shadow: shadow() });
      const parts = text.split(" ");
      slide.addText(parts.shift(), { x: x + 0.3, y: 2.55, w: 3.05, h: 0.85, fontSize: 35, bold: true, color: i === 0 ? C.gold : C.coral, align: "center", margin: 0 });
      slide.addText(parts.join(" "), { x: x + 0.35, y: 3.65, w: 2.95, h: 0.85, fontSize: 16, color: i === 0 ? C.white : C.ink, align: "center", margin: 0 });
    });
  } else if (index === 6) {
    slide.addShape(pptx.ShapeType.rect, { x: 0.95, y: 1.65, w: 11.45, h: 4.5, fill: { color: C.ink }, line: { color: C.ink }, shadow: shadow() });
    slide.addText("“", { x: 1.3, y: 1.65, w: 0.7, h: 0.9, fontFace: "Georgia", fontSize: 52, color: C.gold, margin: 0 });
    slide.addText(item.body.join("\n"), { x: 2.05, y: 2.25, w: 9.4, h: 2.55, fontSize: 22, color: C.white, margin: 0, breakLine: false, valign: "mid" });
  } else if (dark) {
    slide.addText(item.body[0], { x: 1.0, y: 2.55, w: 10.5, h: 1.3, fontSize: 30, color: C.gold, bold: true, margin: 0, align: "center", valign: "mid" });
  } else {
    slide.addShape(pptx.ShapeType.rect, { x: 0.85, y: 1.65, w: 0.14, h: 4.7, fill: { color: C.coral }, line: { color: C.coral } });
    slide.addText(bodyRuns(item.body), { x: 1.4, y: 1.75, w: 7.2, h: 4.4, fontSize: 20, color: C.ink, margin: 0.08, breakLine: false, valign: "mid" });
    slide.addShape(pptx.ShapeType.arc, { x: 9.35, y: 2.05, w: 2.55, h: 2.55, adjustPoint: 0.3, rotate: 35, fill: { color: C.teal }, line: { color: C.teal } });
    slide.addShape(pptx.ShapeType.ellipse, { x: 10.15, y: 2.85, w: 0.95, h: 0.95, fill: { color: C.gold }, line: { color: C.gold } });
  }
});

pptx.writeFile({ fileName: outputPath });
