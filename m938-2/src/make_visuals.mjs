// m938-2 — visibility-safe POD art pipeline.
// Renders each Thai design for BOTH a light garment (dark ink) and a dark
// garment (light ink) so the art never disappears on a black tee, plus a
// realistic tee mockup for each. Output: out/print/*.png, out/mockups/*.jpg
import sharp from 'sharp';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const OUT = join(ROOT, 'out'), PRINT = join(OUT, 'print'), MOCK = join(OUT, 'mockups');
for (const d of [OUT, PRINT, MOCK]) mkdirSync(d, { recursive: true });

const W = 3600, H = 4800;                 // 12x16in @300dpi
const FONT = "Kanit, 'Noto Sans Thai', sans-serif";
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

const GARMENTS = {
  white: { label: 'WHITE',  hex: '#ffffff', shade: '#e9eaee', ink: '#141414' },
  black: { label: 'BLACK',  hex: '#1a1a1c', shade: '#0d0d0f', ink: '#f4f2ec' },
};

function printSvg(d, ink) {
  const cx = W / 2, tW = W * 0.82, sW = W * 0.60;
  const ty = H * 0.44, ly = ty + H * 0.035, sy = ly + H * 0.055;
  const bw = W * 0.90, bh = H * 0.26;           // subtle frame = sticker/patch feel
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <g text-anchor="middle" font-family="${FONT}">
    <rect x="${cx-bw/2}" y="${H*0.32}" width="${bw}" height="${bh}" rx="${W*0.03}"
          fill="none" stroke="${ink}" stroke-width="${W*0.004}" opacity="0.85"/>
    <text x="${cx}" y="${ty}" font-size="${H*0.055}" font-weight="700" fill="${ink}"
          textLength="${tW}" lengthAdjust="spacingAndGlyphs">${esc(d.title)}</text>
    <line x1="${cx-W*0.24}" y1="${ly}" x2="${cx+W*0.24}" y2="${ly}" stroke="${ink}" stroke-width="${W*0.006}"/>
    <text x="${cx}" y="${sy}" font-size="${H*0.026}" font-weight="400" fill="${ink}"
          textLength="${sW}" lengthAdjust="spacingAndGlyphs">${esc(d.sub)}</text>
  </g>
</svg>`;
}

function tightSvg(d, ink) {
  const w = 1600, h = 1100, cx = w / 2;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <g text-anchor="middle" font-family="${FONT}">
    <rect x="90" y="140" width="${w-180}" height="${h-280}" rx="40" fill="none" stroke="${ink}" stroke-width="5" opacity="0.85"/>
    <text x="${cx}" y="520" font-size="150" font-weight="700" fill="${ink}"
          textLength="${w*0.74}" lengthAdjust="spacingAndGlyphs">${esc(d.title)}</text>
    <line x1="${cx-300}" y1="590" x2="${cx+300}" y2="590" stroke="${ink}" stroke-width="10"/>
    <text x="${cx}" y="730" font-size="72" font-weight="400" fill="${ink}"
          textLength="${w*0.56}" lengthAdjust="spacingAndGlyphs">${esc(d.sub)}</text>
  </g>
</svg>`;
}

function mockupSvg(artB64, g, w = 1200, h = 1500) {
  const cx = w/2, cw = w*0.34, ch = cw*1.15, ix = cx-cw/2, iy = h*0.34;
  const body = `M ${w*0.30} ${h*0.16} L ${w*0.42} ${h*0.125} L ${w*0.50} ${h*0.20}
    L ${w*0.58} ${h*0.125} L ${w*0.70} ${h*0.16} L ${w*0.80} ${h*0.31} L ${w*0.71} ${h*0.37}
    L ${w*0.71} ${h*0.94} L ${w*0.29} ${h*0.94} L ${w*0.29} ${h*0.37} L ${w*0.20} ${h*0.31} Z`;
  return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
      width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <defs>
    <radialGradient id="bg" cx="50%" cy="38%" r="75%">
      <stop offset="0%" stop-color="#fbfbfc"/><stop offset="100%" stop-color="#dcdee4"/>
    </radialGradient>
    <linearGradient id="fab" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${g.hex}"/><stop offset="100%" stop-color="${g.shade}"/>
    </linearGradient>
    <filter id="sh" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="18" stdDeviation="26" flood-color="#000" flood-opacity="0.28"/>
    </filter>
  </defs>
  <rect width="${w}" height="${h}" fill="url(#bg)"/>
  <g filter="url(#sh)">
    <path d="${body}" fill="url(#fab)" stroke="#00000030" stroke-width="3"/>
    <path d="M ${w*0.42} ${h*0.125} Q ${cx} ${h*0.235} ${w*0.58} ${h*0.125}" fill="none" stroke="#00000040" stroke-width="6"/>
    <path d="M ${w*0.29} ${h*0.37} L ${w*0.29} ${h*0.94} M ${w*0.71} ${h*0.37} L ${w*0.71} ${h*0.94}"
          stroke="#00000018" stroke-width="4" fill="none"/>
  </g>
  <image x="${ix}" y="${iy}" width="${cw}" height="${ch}" opacity="0.97" xlink:href="data:image/png;base64,${artB64}"/>
  <text x="${cx}" y="${h*0.975}" text-anchor="middle" font-family="${FONT}" font-size="34"
        fill="#6b7280">${g.label}</text>
</svg>`;
}

const designs = JSON.parse(readFileSync(join(ROOT, 'designs.json'), 'utf8'));
const rows = [];
for (const d of designs) {
  for (const [key, g] of Object.entries(GARMENTS)) {
    const print = await sharp(Buffer.from(printSvg(d, g.ink)), { limitInputPixels: false }).png().toBuffer();
    writeFileSync(join(PRINT, `${d.slug}__${key}.png`), print);
    const tight = await sharp(Buffer.from(tightSvg(d, g.ink))).png().toBuffer();
    const mock = await sharp(Buffer.from(mockupSvg(tight.toString('base64'), g))).jpeg({ quality: 90 }).toBuffer();
    writeFileSync(join(MOCK, `${d.slug}__${key}.jpg`), mock);
    rows.push({ slug: d.slug, title: d.title, sub: d.sub, garment: key, label: g.label, ink: g.ink });
  }
  console.log('rendered', d.slug);
}
writeFileSync(join(OUT, 'visuals.json'), JSON.stringify(rows, null, 2));
console.log('done', rows.length, 'renders');
