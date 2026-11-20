#!/usr/bin/env python3
"""deck.md -> deck.html (one 16:9 slide per '---' section) -> deck.pdf via headless Chrome. Stdlib only."""
import html, re, subprocess
from pathlib import Path

HERE = Path(__file__).parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def block(md):
    out, lines, i = [], md.strip().splitlines(), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            j = i + 1
            while not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>"); i = j + 1; continue
        if l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s\-:|]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f"<table><tr>{head}</tr>{body}</table>"); continue
        if l.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>"); continue
        m = re.match(r"^(#{1,3}) (.*)", l)
        if m:
            n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif l.startswith("> "):
            out.append(f"<blockquote>{inline(l[2:])}</blockquote>")
        elif l.strip():
            out.append(f"<p>{inline(l)}</p>")
        i += 1
    return "\n".join(out)


slides = [s for s in (HERE / "deck.md").read_text().split("\n---\n") if s.strip()]
css = """@page{size:13.333in 7.5in;margin:0}*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;color:#1d2327}
.s{width:13.333in;height:7.5in;padding:.55in .75in;page-break-after:always;position:relative;overflow:hidden;background:#fbfaf7}
.s:first-child{background:#1d2327;color:#fff}.s:first-child h2{color:#f2b134}.s:first-child blockquote{background:#2b3238;color:#fff}
.s::after{content:attr(data-n);position:absolute;bottom:.3in;right:.5in;font-size:11px;color:#9aa0a6}
h1{font-size:44px;margin:.6in 0 .1in}h2{font-size:27px;margin:0 0 .18in;color:#1f4f8f}h3{font-size:20px}
p,li{font-size:17px;line-height:1.42}li{margin:.05in 0}ul{padding-left:.3in;margin:.08in 0}
blockquote{margin:.2in 0;padding:.16in .22in;border-left:5px solid #f2b134;background:#fff4dc;font-size:19px}
table{border-collapse:collapse;width:100%;margin:.12in 0;font-size:14.5px}th,td{border-bottom:1px solid #e3dfd5;padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef2f7;color:#1f4f8f}b{color:inherit}code{background:#efede7;padding:1px 4px;border-radius:3px;font-size:.9em}
pre{background:#1d2327;color:#e8eaed;padding:.16in .2in;border-radius:8px;font-size:13.5px;line-height:1.45;white-space:pre-wrap}"""
body = "\n".join(f'<section class="s" data-n="{k + 1} / {len(slides)}">{block(s)}</section>' for k, s in enumerate(slides))
(HERE / "deck.html").write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>SMB Cash-Flow Copilot</title><style>{css}</style></head><body>{body}</body></html>")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={HERE / 'SMB_CashFlow_Copilot_deck.pdf'}", (HERE / "deck.html").as_uri()],
               check=True, capture_output=True)
print("slides:", len(slides), "->", HERE / "SMB_CashFlow_Copilot_deck.pdf")
