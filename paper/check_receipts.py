#!/usr/bin/env python3
"""check_receipts.py — no-number-without-receipt check (stdlib only).

Scans an HTML file for numeric results. Every result number must sit inside
<span class="n" data-receipt="ID">...</span> with ID present in receipts.json,
whose file must exist with matching sha256 and must contain the value.

FAIL rules:
  (i)   span.n without data-receipt, or id missing from receipts.json
  (ii)  receipt file missing, or sha256 mismatch
  (iii) span text != receipt value, or value not in receipted file text
        (for .json files a JSON key lookup via line_or_key also accepts;
        fraction keys like "A.hits/A.n" join components with "/")
  (iv)  bare decimal/fraction/percentage/multidigit in body text outside
        receipted spans, outside the allow-list:
        years 19xx/20xx, citation [n], hash hex runs, section numbers
        (headings + Section/Figure/Table references), equation labels
        (n)/(Eq. n), and any element with a data-allow attribute.
        <style>, <script> subtrees are exempt (code, not prose).
  (v)   svg text numbers: any percentage, fraction, decimal or
        multi-digit integer in a text node under <svg> must equal,
        character for character, the text of a data-receipt span
        elsewhere in the document, else SVG-UNRECEIPTED.
Banned-word lint: any phrase from banned.txt (one per line,
case-insensitive) in body text fails.

Usage:
  python3 check_receipts.py [HTML] [--receipts PATH] [--banned PATH]
Defaults (relative to this script): src/dummy.html, src/receipts.json,
banned.txt. Exit 0 on pass, 1 on any failure.
"""
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_HTML = HERE / "src" / "dummy.html"
DEFAULT_RECEIPTS = HERE / "src" / "receipts.json"
DEFAULT_BANNED = HERE / "banned.txt"

EXEMPT_TAGS = {"svg", "style", "script"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

RE_FRAC = re.compile(r"\b\d+/\d+\b")
RE_DEC = re.compile(r"\b\d+\.\d+\b")
RE_PCT = re.compile(r"\b\d+\s?%")
RE_INT = re.compile(r"\b\d{2,}\b")
RE_YEAR = re.compile(r"^(19|20)\d{2}$")
RE_HEXTOKEN = re.compile(r"[0-9a-fA-F]+")
RE_SECREF = re.compile(
    r"(?:section|figure|table|chapter|equation|eq\.)\s*$", re.IGNORECASE
)


class BodyScan(HTMLParser):
    """Collects receipt spans and non-exempt body text with line numbers."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # list of (tag, attrs_dict)
        self.in_body = False
        self.spans = []  # dicts: receipt, text, line
        self._span_buf = None
        self._span_line = 0
        self.segments = []  # dicts: text, line, in_heading
        self.svg_segments = []  # dicts: text, line (text nodes under svg)
        self.visible_chunks = []  # (text, line) for banned-word lint

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == "body":
            self.in_body = True
        self.stack.append((t, dict(attrs)))
        if t == "span":
            ad = dict(attrs)
            classes = (ad.get("class") or "").split()
            if "n" in classes:
                self._span_buf = []
                self._span_line = self.getpos()[0]
                self._span_receipt = ad.get("data-receipt")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == "span" and self._span_buf is not None:
            # only close if the top span was the receipt span; HTMLParser
            # is lenient, so pop stack to matching span
            text = "".join(self._span_buf)
            self.spans.append(
                {
                    "receipt": getattr(self, "_span_receipt", None),
                    "text": text,
                    "line": self._span_line,
                    "in_svg": any(t == "svg" for t, _ in self.stack),
                }
            )
            self._span_buf = None
        # pop stack up to matching tag
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == t:
                del self.stack[i:]
                break
        if t == "body":
            self.in_body = False

    def _exempt(self):
        for t, ad in self.stack:
            if t in EXEMPT_TAGS:
                return True
            if "data-allow" in ad:
                return True
            classes = (ad.get("class") or "").split()
            if t == "span" and "n" in classes:
                return True
        return False

    def handle_data(self, data):
        if not self.in_body and not self.stack:
            return
        # record visible text for banned lint (body only, skip exempt code)
        tags = [t for t, _ in self.stack]
        if self.in_body or "body" in tags:
            if not any(t in EXEMPT_TAGS for t in tags):
                if data.strip():
                    self.visible_chunks.append((data, self.getpos()[0]))
        if self._span_buf is not None:
            self._span_buf.append(data)
            return
        if not self.in_body:
            return
        if "svg" in tags:
            if data:
                self.svg_segments.append(
                    {"text": data, "line": self.getpos()[0]}
                )
            return
        if self._exempt():
            return
        if data:
            in_heading = any(t in HEADING_TAGS for t, _ in self.stack)
            self.segments.append(
                {"text": data, "line": self.getpos()[0],
                 "in_heading": in_heading}
            )


def resolve_json_path(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise KeyError(part)
    return cur


def json_lookup_ok(doc, line_or_key, value):
    try:
        if "/" in line_or_key:
            vals = [str(resolve_json_path(doc, p.strip()))
                    for p in line_or_key.split("/")]
            return "/".join(vals) == value
        return str(resolve_json_path(doc, line_or_key.strip())) == value
    except (KeyError, IndexError, ValueError, TypeError):
        return False


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def mask_spans(text, matches):
    masked = list(text)
    for m in matches:
        for i in range(m.start(), m.end()):
            masked[i] = " "
    return "".join(masked)


def check_bare_numbers(segments):
    """Return failure strings for unreceipted numbers in text segments."""
    failures = []
    for seg in segments:
        text = seg["text"]
        line = seg["line"]
        in_heading = seg["in_heading"]
        # Find specific shapes first, mask them, then plain multidigit ints.
        found = []  # (match, kind)
        for rx, kind in ((RE_PCT, "percent"), (RE_FRAC, "fraction"),
                         (RE_DEC, "decimal")):
            for m in rx.finditer(text):
                found.append((m, kind))
        masked = mask_spans(text, [m for m, _ in found])
        for m in RE_INT.finditer(masked):
            found.append((m, "int"))
        for m, kind in sorted(found, key=lambda x: x[0].start()):
            tok = m.group(0)
            core = tok.rstrip().rstrip("%").strip()
            # Allow-list checks.
            if RE_YEAR.match(core):
                continue
            before = text[: m.start()]
            after = text[m.end():]
            # Citation [n]: token directly wrapped in brackets.
            if before.endswith("[") and after.startswith("]"):
                continue
            # Hash hex: token embedded in a hex run of length >= 8.
            s, e = m.start(), m.end()
            while s > 0 and text[s - 1] in "0123456789abcdefABCDEF":
                s -= 1
            while e < len(text) and text[e] in "0123456789abcdefABCDEF":
                e += 1
            if e - s >= 8 and RE_HEXTOKEN.fullmatch(text[s:e] or ""):
                continue
            # Section numbers: headings, or Section/Figure/Table/Eq. refs.
            if in_heading:
                continue
            if RE_SECREF.search(before):
                continue
            # Equation labels: (n) or (Eq. n).
            if re.search(r"\(\s*(Eq\.|Equation)?\s*$", before) and re.match(
                    r"\s*\)", after):
                continue
            ctx = text.strip().replace("\n", " ")
            if len(ctx) > 90:
                ctx = ctx[:87] + "..."
            failures.append(
                "UNRECEIPTED NUMBER %r (%s) at line %d: %s"
                % (tok, kind, line, ctx)
            )
    return failures


def check_svg_numbers(svg_segments, span_texts):
    """Return failure strings for svg numbers with no matching span text."""
    failures = []
    for seg in svg_segments:
        text = seg["text"]
        line = seg["line"]
        # Same shapes and masking order as check_bare_numbers.
        found = []  # (match, kind)
        for rx, kind in ((RE_PCT, "percent"), (RE_FRAC, "fraction"),
                         (RE_DEC, "decimal")):
            for m in rx.finditer(text):
                found.append((m, kind))
        masked = mask_spans(text, [m for m, _ in found])
        for m in RE_INT.finditer(masked):
            found.append((m, "int"))
        for m, kind in sorted(found, key=lambda x: x[0].start()):
            tok = m.group(0)
            if tok in span_texts:
                continue
            ctx = text.strip().replace("\n", " ")
            if len(ctx) > 90:
                ctx = ctx[:87] + "..."
            failures.append(
                "SVG-UNRECEIPTED %r (%s) at line %d: %s"
                % (tok, kind, line, ctx)
            )
    return failures


def run_checks(html_path, receipts_path, banned_path):
    failures = []
    html_p = Path(html_path)
    if not html_p.exists():
        return ["HTML file not found: %s" % html_p], "FAIL: HTML file not found: %s\n" % html_p
    text = html_p.read_text(encoding="utf-8")
    try:
        receipts = json.loads(Path(receipts_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["receipts file not found: %s" % receipts_path], "FAIL: receipts file not found: %s\n" % receipts_path
    except json.JSONDecodeError as e:
        return ["receipts.json invalid: %s" % e], "FAIL: receipts.json invalid: %s\n" % e

    parser = BodyScan()
    parser.feed(text)

    # Rule (i): spans must carry a known receipt id.
    for sp in parser.spans:
        rid = sp["receipt"]
        if not rid:
            failures.append(
                "SPAN WITHOUT RECEIPT at line %d: %r"
                % (sp["line"], sp["text"].strip()[:60])
            )
        elif rid not in receipts:
            failures.append(
                "UNKNOWN RECEIPT %r at line %d" % (rid, sp["line"])
            )

    # Rule (ii): every receipt in the file must resolve with matching sha.
    receipt_text = {}  # rid -> file text or None
    receipt_json = {}  # rid -> parsed json or None
    for rid, rec in receipts.items():
        f = rec.get("file", "")
        want = rec.get("sha256", "")
        p = Path(f)
        if not p.exists():
            failures.append("RECEIPT %s: file does not exist: %s" % (rid, f))
            receipt_text[rid] = None
            continue
        try:
            got = sha256_of(p)
        except OSError as e:
            failures.append("RECEIPT %s: cannot read %s: %s" % (rid, f, e))
            receipt_text[rid] = None
            continue
        if got != want:
            failures.append(
                "RECEIPT %s: sha256 mismatch for %s (want %.12s, got %.12s)"
                % (rid, f, want, got)
            )
        try:
            receipt_text[rid] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            receipt_text[rid] = ""
        if str(p).endswith(".json"):
            try:
                receipt_json[rid] = json.loads(receipt_text[rid])
            except (json.JSONDecodeError, TypeError):
                receipt_json[rid] = None
        else:
            receipt_json[rid] = None

    # Rule (iii): span text must equal the receipt value and be found.
    for sp in parser.spans:
        rid = sp["receipt"]
        if not rid or rid not in receipts:
            continue
        rec = receipts[rid]
        value = str(rec.get("value", ""))
        span_text = sp["text"].strip()
        if span_text != value:
            failures.append(
                "SPAN/VALUE MISMATCH %s at line %d: span %r != value %r"
                % (rid, sp["line"], span_text, value)
            )
            continue
        ftext = receipt_text.get(rid)
        if ftext is None:
            continue  # already reported under rule (ii)
        if value in ftext:
            continue
        doc = receipt_json.get(rid)
        if doc is not None and json_lookup_ok(
                doc, str(rec.get("line_or_key", "")), value):
            continue
        failures.append(
            "VALUE NOT IN FILE %s at line %d: %r not found in %s "
            "(%d chars; key %r)"
            % (rid, sp["line"], value, rec.get("file"),
               len(ftext), rec.get("line_or_key"))
        )

    # Rule (iv): bare numbers outside spans.
    failures.extend(check_bare_numbers(parser.segments))

    # Rule (v): svg text numbers must match a receipt span text.
    span_texts = {sp["text"].strip() for sp in parser.spans
                  if sp["receipt"] and not sp["in_svg"]}
    failures.extend(check_svg_numbers(parser.svg_segments, span_texts))

    # Banned-word lint over visible body text.
    try:
        banned = [ln.strip() for ln in
                  Path(banned_path).read_text(encoding="utf-8").splitlines()]
    except FileNotFoundError:
        failures.append("banned-word file not found: %s" % banned_path)
        banned = []
    banned = [b for b in banned if b]
    for chunk, line in parser.visible_chunks:
        low = chunk.lower()
        for phrase in banned:
            if phrase.lower() in low:
                ctx = chunk.strip().replace("\n", " ")
                if len(ctx) > 90:
                    ctx = ctx[:87] + "..."
                failures.append(
                    "BANNED WORD %r at line %d: %s" % (phrase, line, ctx)
                )

    if failures:
        report = "FAIL: %d problem(s) in %s\n" % (len(failures), html_p)
        report += "\n".join(" - " + f for f in failures) + "\n"
    else:
        report = "OK: %s (%d receipted spans, %d text segments clean)\n" % (
            html_p, len(parser.spans), len(parser.segments))
    return failures, report


def main(argv):
    html_path = str(DEFAULT_HTML)
    receipts_path = str(DEFAULT_RECEIPTS)
    banned_path = str(DEFAULT_BANNED)
    rest = []
    i = 0
    args = list(argv[1:])
    while i < len(args):
        a = args[i]
        if a == "--receipts" and i + 1 < len(args):
            receipts_path = args[i + 1]
            i += 2
        elif a == "--banned" and i + 1 < len(args):
            banned_path = args[i + 1]
            i += 2
        elif a.startswith("--receipts="):
            receipts_path = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--banned="):
            banned_path = a.split("=", 1)[1]
            i += 1
        else:
            rest.append(a)
            i += 1
    if rest:
        html_path = rest[0]
    failures, report = run_checks(html_path, receipts_path, banned_path)
    sys.stdout.write(report)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
