"""Post-hoc explanation transforms. Each transform encodes ONE documented/known difference between
1.3.14 and 1.4.0 as a rewrite applied to BOTH outputs; a divergence is "explained by S" when applying the
transforms in S makes A and new identical. Written after looking at the divergences (post-hoc!).

Each entry: name -> (source of the explanation, function(text) -> text).
"""
import re

SURR_ESC = re.compile(r"\\u[dD][89a-fA-F][0-9a-fA-F]{2}")


def _cols(t):
    t = re.sub(r":\d+:\d+", ":L:C", t)
    t = re.sub(r"(?m)^ *\^ *$", "^", t)
    return t


def _fffd(t):
    return t.replace("�", "")


def _url(t):
    t = re.sub(r'(TypeError: |ERR_INVALID_URL )(?:".*?"|<redacted>) cannot be parsed as a URL\.', r"\1Invalid URL", t)
    t = re.sub(r'\n input: ".*?",\n  code: "ERR_INVALID_URL"', '\n code: "ERR_INVALID_URL"', t)
    return t


def _tdmsg(t):
    t = t.replace("Invalid byte sequence", "The encoded data was not valid for encoding utf-8")
    t = re.sub(r"The encoded data was not valid UTF-16(LE|BE) data", lambda m: f"The encoded data was not valid for encoding utf-16{m.group(1).lower()}", t)
    return t


NEW_ENC = re.compile(r'(?:ERR RangeError ERR_ENCODING_NOT_SUPPORTED )?Unsupported encoding label "(iso-8859-2|windows-1251|koi8-r|iso-8859-5|iso-8859-16)"')

TRANSFORMS = {
    "T1-sourcemap-columns": ("1.4 changelog: 'Sourcemaps: original columns are no longer off by one on lines containing a non-ASCII character.' (old bug, fixed)", _cols),
    "T2-lone-surrogate-W1": ("#31001, accepted by maintainers (pre-registered W1)", _fffd),
    "T3-url-error-message": ("1.4 changelog: 'new URL(bad) now throws Node's TypeError: Invalid URL with code and input set.'", _url),
    "T4-textdecoder-message": ("1.4 TextDecoder rewrite; messages now equal Node's ('The encoded data was not valid for encoding utf-8')", _tdmsg),
}


def _timing(t):
    return re.sub(r"(?m) <T>$", "", t)


def _nan(t):
    return re.sub(r"\bnan\b", "NaN", re.sub(r"\binf\b", "Infinity", t))


def _js_num(v):
    if v != v:
        return "NaN"
    if v in (float("inf"), float("-inf")):
        return "Infinity" if v > 0 else "-Infinity"
    if v == int(v) and abs(v) < 1e21:
        return str(int(v))
    r = repr(v)
    m = re.match(r"(-?)(\d)(?:\.(\d+))?e([+-]\d+)$", r)
    if m:
        sign, d0, rest, ex = m.group(1), m.group(2), m.group(3) or "", int(m.group(4))
        digits = d0 + rest
        if -7 < ex < 21:
            if ex < 0:
                return sign + "0." + "0" * (-ex - 1) + digits
            return sign + (digits + "0" * (ex + 1 - len(digits)) if len(digits) <= ex + 1 else digits[:ex + 1] + "." + digits[ex + 1:])
        return f"{sign}{d0}{'.' + rest if rest else ''}e{'+' if ex > 0 else '-'}{abs(ex)}"
    if abs(v) >= 1e21 or (v != 0 and abs(v) < 1e-6):
        return _js_num(float(f"{v:e}")) if False else format(v, ".17g")
    return r


def _numfmt(t):
    def rep(m):
        tok = m.group(0)
        try:
            v = float(tok)
        except ValueError:
            return tok
        if (v == 0 and len(tok) > 30) or (v != 0 and abs(v) < 1e-300):
            return "<TINY>"
        return _js_num(v)
    return re.sub(r"(?<![\w.])-?\d+(?:\.\d+)?(?:e[+-]?\d+)?(?![\w])", rep, t)


TRANSFORMS.update({
    "T0-test-timing-suffix": ("true noise: bun test prints the per-test duration only above a threshold (same effect as A!=B noise)", _timing),
    "T7-nan-spelling": ("old (Zig) printed float NaN/Inf as 'nan'/'inf' in test-runner messages and TOML output; new prints JS 'NaN'", _nan),
    "T8-js-number-format": ("old (Zig) printed numbers in expect() diffs with Zig float formatting (1000000000000000000000, 0.000…0 for 5e-324); new uses JS Number#toString", _numfmt),
})


def _preview(t):
    t = re.sub(r"(?m)(^|\x00)(\d+) \| .*$", r"\1\2 | <SRC>", t)
    return _cols(t)


def _rename(t):
    import verify_bundles
    return verify_bundles.t6(t)


TRANSFORMS.update({
    "T9-minifier-renaming/export-order": ("bundler/minifier: namespace export map now sorted (1.4 changelog: 'A bundled import * as ns namespace now enumerates its exports in sorted order') and different short-name assignment; canonicalised by first appearance", _rename),
    "T10-error-preview-window": ("cosmetic: the echoed source line in error previews is truncated/centred differently (content is the user's own input)", _preview),
})


ALPHA_FIXED = set("true false null undefined NaN Infinity this void typeof new return function class const let var import export from default as if else for of in await async yield static get set ERR".split())


def alpha_equiv(x, y):
    """True if y is x with identifiers consistently renamed (bijection), all other tokens equal."""
    tx = re.findall(r"[A-Za-z_$Ѐ-ӿ][\w$Ѐ-ӿ]*|\d+|\S", x)
    ty = re.findall(r"[A-Za-z_$Ѐ-ӿ][\w$Ѐ-ӿ]*|\d+|\S", y)
    if len(tx) != len(ty):
        return False
    f, g = {}, {}
    for a, b in zip(tx, ty):
        ida = re.match(r"[A-Za-z_$Ѐ-ӿ]", a) is not None
        idb = re.match(r"[A-Za-z_$Ѐ-ӿ]", b) is not None
        if ida != idb:
            return False
        if not ida:
            if a != b:
                return False
            continue
        if a in ALPHA_FIXED or b in ALPHA_FIXED:
            if a != b:
                return False
            continue
        if f.setdefault(a, b) != b or g.setdefault(b, a) != a:
            return False
    return True


def _ws(t):
    return re.sub(r"\s+", "", t)


TRANSFORMS.update({
    "T12-inspect-line-wrapping": ("pretty-printer wraps arrays/objects at different points (width now computed by the rewritten Bun.stringWidth, 1.4 changelog: 'util.inspect, console.table, and readline use the same implementation'); compared whitespace-insensitively", _ws),
})


def _octal(t):
    if "Invalid legacy octal literal" not in t:
        return t
    return re.sub(r"(?m)(^|\x00)\d+ \| ", r"\g<1>0 | ", t)


TRANSFORMS.update({
    "T13-octal-error-location": ("old bug (undocumented fix): 1.3.14 reports 'Invalid legacy octal literal' at a wrong position (column 2 or a different line); 1.4.0 points at the escape", _octal),
})


def ORDER(n):
    return -1 if n.startswith("T13") else 0 if n.startswith("T10") else 3 if n.startswith("T12") else 2 if n.startswith("T9") else 1


def explain(a, c, src, names=None, allow_alpha=False):
    """Smallest set of transforms (backward elimination from all) that makes a == c, or None."""
    names = list(names or TRANSFORMS)
    if not SURR_ESC.search(src):
        names = [n for n in names if n != "T2-lone-surrogate-W1"]

    def eq(combo):
        ta, tc = a["out"] + "\x00" + a["err"], c["out"] + "\x00" + c["err"]
        for n in sorted(combo, key=ORDER):
            ta, tc = TRANSFORMS[n][1](ta), TRANSFORMS[n][1](tc)
        return ta == tc and a["code"] == c["code"]
    if eq([]):
        return []
    if not eq(names):
        if allow_alpha and a["code"] == c["code"] and a["err"] == c["err"] and alpha_equiv(a["out"], c["out"]):
            return ["T11-alpha-renaming"]
        return None
    need = list(names)
    # try to drop the generic/cosmetic transforms first, so documented ones are kept when they suffice
    pref = ["T10", "T12", "T8", "T7", "T0", "T13"]
    for n in sorted(need, key=lambda n: next((i for i, p in enumerate(pref) if n.startswith(p + "-")), len(pref))):
        trial = [x for x in need if x != n]
        if eq(trial):
            need = trial
    return need
