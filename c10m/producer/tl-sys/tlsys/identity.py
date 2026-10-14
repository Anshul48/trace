"""Atom/holon identity (S-02-grounded, S-04 Q2.1/Q15.1(c) carried marks).

tlsys-v2 atom identity (revision-bound; S-02 section 1 settled terms):
  atom_id = blake3-256 (hex) over:
    u64be(len(tag)) || tag="tl-atom-tlsys-v2" ||
    u64be(len(doc_id)) || doc_id (utf-8) ||
    revision_id (16 raw bytes, RFC 9562 network order) ||
    u64be(len(config)) || atomizer_config (utf-8) ||
    byte_start (u64be) || byte_end (u64be) ||
    u64be(len(bytes)) || raw chunk bytes (UTF-8, unnormalized)
  Binds content + source/revision identity + byte span + the
  atomizer's output-affecting configuration, per the S-02 atomizer
  determinism settlement. Deterministic: identical bound inputs
  reproduce the identical atom without duplicates.
  Open (per the closure itself): S-02 section 2a exact canonical hash
  encoding ("remains for section 2a"); this preimage is documented
  here and stays stable until 2a ratifies or replaces it.
  Copies: no import path exists in scope, so copy-preserves-identity
  has no carrier yet (trigger: first import/copy feature; the
  revision_id field is its mechanism).
holon_ref = "holon:<doc_id>:<gen_triple>"              (per-doc holon)
gen id    = "<birth>:<epoch>:<seq>"                     (candidate triple; FULL
            identity always -- Q14.1 amendment: never bare sequence)

No bare-span-hash verification anywhere (Q15.1(c) refusal).
"""

try:
    import blake3 as _blake3
except ImportError:  # pragma: no cover
    _blake3 = None


# Identity-scheme stamp. Bumped whenever atom-ID construction changes;
# committed metas + ingest manifests carry it, and readers refuse to
# mix schemes (rebuild scratch stores; no migration).
ATOM_SCHEME = "tlsys-v2-revision"

# Atomizer output-affecting configuration id (S-02: binds the complete
# output-affecting configuration). Chunking geometry only: the encoder
# affects descriptors, which are NOT atom-identity inputs.
ATOMIZER_CONFIG = "tlsys-chunk-c200-o50-v1"


def _u64(n) -> bytes:
    return int(n).to_bytes(8, "big")


def _lp(b: bytes) -> bytes:
    return _u64(len(b)) + b


def atom_id(content_bytes, doc_id, byte_span, revision_id,
            atomizer_config=ATOMIZER_CONFIG) -> str:
    """Occurrence-bound atom id (tlsys v2). byte_span: (b0, b1) UTF-8
    byte offsets into the immutable source revision bytes;
    revision_id: UUID string (16 raw bytes in the preimage)."""
    if _blake3 is None:
        raise RuntimeError("blake3 required (tl-sys venv); refusing silent hash swap")
    import uuid as _uuid
    b0, b1 = byte_span
    rev = _uuid.UUID(str(revision_id)).bytes  # network order, 16 bytes
    preimage = (_lp(b"tl-atom-tlsys-v2") + _lp(doc_id.encode("utf-8"))
                + rev + _lp(str(atomizer_config).encode("utf-8"))
                + _u64(b0) + _u64(b1) + _lp(bytes(content_bytes)))
    return _blake3.blake3(preimage).hexdigest()


def canonical_json_bytes(value) -> bytes:
    """RFC 8785 (JCS) subset for the S-02 section 2a value profile.

    Profile: string / integer / boolean / null / array / object;
    integers restricted to +/-(2^53-1); no fractional numbers.
    Object keys sort by UTF-8 bytes (== UTF-16 code-unit order for
    BMP keys without surrogates; lone surrogates rejected).
    Floats, out-of-range ints, and non-string keys raise instead
    of silently coercing.
    """
    def enc(v):
        if v is None:
            return b"null"
        if v is True:
            return b"true"
        if v is False:
            return b"false"
        if isinstance(v, int) and not isinstance(v, bool):
            if abs(v) > 2 ** 53 - 1:
                raise ValueError(
                    f"canonical JSON: integer {v} outside "
                    "+/-(2^53-1); use a canonical decimal string")
            return str(v).encode("ascii")
        if isinstance(v, float):
            raise ValueError(
                "canonical JSON: fractional numbers forbidden "
                "(fixed-point integers or decimal strings)")
        if isinstance(v, str):
            for ch in v:
                if 0xD800 <= ord(ch) <= 0xDFFF:
                    raise ValueError(
                        "canonical JSON: lone surrogate forbidden")
            out = ['"']
            for ch in v:
                o = ord(ch)
                if ch == '"' or ch == "\\":
                    out.append("\\" + ch)
                elif o < 0x20:
                    out.append({"\\b": "\\b", "\\f": "\\f", "\\n": "\\n",
                                "\\r": "\\r", "\\t": "\\t"}.get(
                        ch, "\\u%04x" % o))
                else:
                    out.append(ch)
            out.append('"')
            return "".join(out).encode("utf-8")
        if isinstance(v, (list, tuple)):
            return b"[" + b",".join(enc(x) for x in v) + b"]"
        if isinstance(v, dict):
            for k in v:
                if not isinstance(k, str):
                    raise ValueError(
                        "canonical JSON: object keys must be strings")
            items = sorted(v.items(),
                           key=lambda kv: kv[0].encode("utf-8"))
            return (b"{" + b",".join(enc(k) + b":" + enc(val)
                                    for k, val in items) + b"}")
        raise ValueError(
            f"canonical JSON: unsupported type {type(v).__name__}")

    return enc(value)


def extractor_config_id(spec) -> str:
    """config_ids = H("tl-cfg:v1" || canonical-JSON(effective spec)).

    spec: canonical-JSON-profile dict of effective behavior only
    (implementation/version, resolved defaults, rules, pinned
    model/prompt ids) -- never paths, exec IDs, or mutable aliases.
    """
    if _blake3 is None:
        raise RuntimeError("blake3 required (tl-sys venv); refusing silent hash swap")
    preimage = _lp(b"tl-cfg:v1") + _lp(canonical_json_bytes(spec))
    return _blake3.blake3(preimage).hexdigest()


def relation_id(rel_type, endpoints, qualifiers, extractor_config,
                interchangeable=False) -> str:
    """S-02 section 2a relation identity (hex blake3-256).

    relation_id = H("tl-rel:v1" || type || endpoints ||
                    canonical-qualifiers || extractor_config_id)
    endpoints: [(role-label, endpoint-id-hex)] ordered by
      (role-label bytes, endpoint-ID bytes); interchangeable types
      (declared by the extractor version/config bound into the ID)
      pass [endpoint-id-hex] with interchangeable=True: role labels
      omitted, endpoint IDs sorted ascending. Absent that
      declaration endpoints are ordered (roles required).
    Endpoint IDs are 32 raw bytes in the preimage (64-hex-char
    atom/relation IDs). Qualifiers enter as one length-prefixed
    canonical-JSON field; meaning-essential qualifier changes
    (negation/condition/scope) yield a different identity.
    extractor_config: 64-hex-char config id (see
      extractor_config_id) or a spec dict (hashed here).
    """
    if _blake3 is None:
        raise RuntimeError("blake3 required (tl-sys venv); refusing silent hash swap")
    if not rel_type or not isinstance(rel_type, str):
        raise ValueError("relation type must be a nonempty string")

    def _raw(eid):
        try:
            raw = bytes.fromhex(str(eid))
        except ValueError:
            raise ValueError(f"endpoint id not 64-hex-char: {eid!r}")
        if len(raw) != 32:
            raise ValueError(f"endpoint id not 32 bytes: {eid!r}")
        return raw

    if interchangeable:
        entries = sorted(_raw(e) for e in endpoints)
        if not entries:
            raise ValueError("relation needs >=1 endpoint")
        ep = _u64(len(entries)) + b"".join(entries)
    else:
        pairs = []
        for item in endpoints:
            role, eid = item  # roles required when ordered
            if not role or not isinstance(role, str):
                raise ValueError("ordered endpoints need role labels")
            pairs.append((role.encode("utf-8"), _raw(eid)))
        if not pairs:
            raise ValueError("relation needs >=1 endpoint")
        pairs.sort()
        ep = _u64(len(pairs)) + b"".join(_lp(r) + i for r, i in pairs)
    if isinstance(extractor_config, dict):
        cfg_hex = extractor_config_id(extractor_config)
    else:
        cfg_hex = str(extractor_config)
        if len(bytes.fromhex(cfg_hex)) != 32:
            raise ValueError("extractor_config_id must be 32-byte hex "
                             "or a spec dict")
    preimage = (_lp(b"tl-rel:v1") + _lp(rel_type.encode("utf-8")) + ep
                + _lp(canonical_json_bytes(qualifiers))
                + _lp(cfg_hex.encode("ascii")))
    return _blake3.blake3(preimage).hexdigest()


def holon_ref(doc_id: str, gen_triple: str) -> str:
    return f"holon:{doc_id}:{gen_triple}"


def parse_gen(gen_triple: str):
    birth, epoch, seq = gen_triple.split(":")
    return birth, int(epoch), int(seq)
