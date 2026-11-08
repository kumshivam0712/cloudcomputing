#!/usr/bin/env bash
# Build report/report.pdf from report/report.md (pandoc -> HTML -> headless Chromium print).
#   report/build_pdf.sh [input.md] [output.pdf]
set -euo pipefail
cd "$(dirname "$0")"
in=${1:-report.md}
out=${2:-report.pdf}
html=${out%.pdf}.html
pandoc "$in" --from markdown+pipe_tables+raw_html --to html5 --standalone \
  --css report.css --embed-resources --metadata title="CS3081 Mini Project Report" -o "$html"
node - "$html" "$out" <<'JS'
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [html, pdf] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(html));
  await page.pdf({ path: pdf, format: 'A4', printBackground: true,
    margin: { top: '14mm', bottom: '14mm', left: '13mm', right: '13mm' },
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#666">' +
      '<span class="pageNumber"></span> / <span class="totalPages"></span></div>' });
  await browser.close();
})();
JS
rm -f "$html"
echo "wrote $out"
