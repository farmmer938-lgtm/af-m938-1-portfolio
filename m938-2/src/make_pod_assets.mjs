// m938-2 — POD asset pipeline for the Do.ink + Lazada path.
// Turns the 8 Thai-text shirt designs into print-ready PNG (Do.ink spec:
// PNG, transparent background, >=300 DPI) and shirt mockups for the listing.
import sharp from 'sharp';
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, basename } from 'node:path';

const SRC_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = dirname(SRC_DIR); // m938-2/
const SRC = ROOT;              // designs.json lives at the project root
const OUT = join(ROOT, 'out');
const PRINT = join(OUT, 'print');
const MOCK = join(OUT, 'mockups');

// Do.ink DTG print area on a standard adult tee: 12in x 16in at 300 DPI.
const PRINT_W_IN = 12, PRINT_H_IN = 16, DPI = 300;
const PRINT_W = PRINT_W_IN * DPI; // 3600
const PRINT_H = PRINT_H_IN * DPI; // 4800
const SHIRT_COLOR = '#ffffff'; // light garment: the designs are dark-ink text
const SHIRT_BG = '#e6e8ec';    // page bg so a white tee still reads as a shape

function ensureDirs() {
  for (const d of [OUT, PRINT, MOCK]) mkdirSync(d, { recursive: true });
}

// Re-layout the design text into the exact print canvas (transparent bg),
// so the PNG is a true print file, not a scaled copy of the tall source.
function buildPrintSvg(design, w, h) {
  const ink = design.ink || '#111111';
  const titleSize = Math.round(w * 0.135);
  const subSize = Math.round(w * 0.055);
  const cx = w / 2;
  const titleY = h * 0.42;
  const lineY = titleY + titleSize * 0.34;
  const subY = lineY + subSize * 1.6;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <g text-anchor="middle" font-family="Sarabun, 'Noto Sans Thai', sans-serif">
    <text x="${cx}" y="${titleY}" font-size="${titleSize}" font-weight="700" fill="${ink}">${esc(design.title)}</text>
    <line x1="${cx - w * 0.24}" y1="${lineY}" x2="${cx + w * 0.24}" y2="${lineY}" stroke="${ink}" stroke-width="${Math.round(w * 0.006)}"/>
    <text x="${cx}" y="${subY}" font-size="${subSize}" font-weight="400" fill="${ink}">${esc(design.sub)}</text>
  </g>
</svg>`;
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Tight design preview (transparent) for the listing mockup, so the artwork
// reads at thumbnail size instead of drowning in the print-file margins.
function buildPreviewSvg(design, w = 1500, h = 1000) {
  const ink = design.ink || '#111111';
  const cx = w / 2;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <g text-anchor="middle" font-family="Sarabun, 'Noto Sans Thai', sans-serif">
    <text x="${cx}" y="460" font-size="200" font-weight="700" fill="${ink}">${esc(design.title)}</text>
    <line x1="${cx - 300}" y1="540" x2="${cx + 300}" y2="540" stroke="${ink}" stroke-width="9"/>
    <text x="${cx}" y="670" font-size="78" font-weight="400" fill="${ink}">${esc(design.sub)}</text>
  </g>
</svg>`;
}

// Front-facing tee silhouette (original vector, no stock art), design clipped in.
function buildMockupSvg(designPngB64, shirtColor, w = 1000, h = 1200) {
  const cx = w / 2;
  const body = `M ${w*0.30} ${h*0.16}
    L ${w*0.42} ${h*0.13} L ${w*0.50} ${h*0.19} L ${w*0.58} ${h*0.13}
    L ${w*0.70} ${h*0.16} L ${w*0.78} ${h*0.30} L ${w*0.70} ${h*0.35}
    L ${w*0.70} ${h*0.92} L ${w*0.30} ${h*0.92} L ${w*0.30} ${h*0.35}
    L ${w*0.22} ${h*0.30} Z`;
  const cw = w * 0.30, ch = cw * 1.25;
  const ix = cx - cw / 2, iy = h * 0.33;
  return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <rect width="${w}" height="${h}" fill="${SHIRT_BG}"/>
  <path d="${body}" fill="${shirtColor}" stroke="#00000022" stroke-width="3"/>
  <path d="M ${w*0.42} ${h*0.13} Q ${cx} ${h*0.24} ${w*0.58} ${h*0.13}" fill="none" stroke="#00000033" stroke-width="4"/>
  <path d="${body}" fill="none" stroke="#00000018" stroke-width="2"/>
  <image x="${ix}" y="${iy}" width="${cw}" height="${ch}" xlink:href="data:image/png;base64,${designPngB64}"/>
</svg>`;
}

async function main() {
  ensureDirs();
  const designs = JSON.parse(readFileSync(join(SRC, 'designs.json'), 'utf8'));
  const manifest = [];
  for (const d of designs) {
    const printSvg = buildPrintSvg(d, PRINT_W, PRINT_H);
    // SVG already declares 3600x4800 px, so render at 1:1 (no density scaling).
    const png = await sharp(Buffer.from(printSvg), { limitInputPixels: false })
      .png().toBuffer();
    writeFileSync(join(PRINT, `${d.slug}.png`), png);

    // mockup uses a tight preview (not the padded print canvas) so the art reads
    const prev = await sharp(Buffer.from(buildPreviewSvg(d))).png().toBuffer();
    const mockSvg = buildMockupSvg(prev.toString('base64'), SHIRT_COLOR);
    const mock = await sharp(Buffer.from(mockSvg)).jpeg({ quality: 88 }).toBuffer();
    writeFileSync(join(MOCK, `${d.slug}.jpg`), mock);

    manifest.push({ slug: d.slug, title: d.title, print_png: `print/${d.slug}.png`,
      mockup_jpg: `mockups/${d.slug}.jpg`, print_px: [PRINT_W, PRINT_H], dpi: DPI });
  }
  writeFileSync(join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(`built ${manifest.length} designs -> ${OUT}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
