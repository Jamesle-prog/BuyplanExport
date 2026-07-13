"""Generate the CPRS API client + models from CPRS_API.openapi.json.

Reads ``po_extractor/cprs/CPRS_API.openapi.json`` and writes
``po_extractor/cprs/models.py`` and ``po_extractor/cprs/client.py``.

Re-run after dropping in a newer spec:
    python scripts/gen_cprs_client.py

The generated client covers every operation, grouped by tag
(``client.<tag>.<method>(...)``), with typed dataclasses for every component
schema. Request bodies accept a typed model OR a plain dict (the spec leaves
several DTOs undocumented, so dicts must always work).
"""
from __future__ import annotations

import json
import keyword
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPRS = ROOT / "po_extractor" / "cprs"
SPEC = CPRS / "CPRS_API.openapi.json"


# ── naming helpers ────────────────────────────────────────────────────────────

def snake(name: str) -> str:
    s = re.sub(r"[\s\-]+", "_", str(name).strip())
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"__+", "_", s)
    return s.lower().strip("_")


def ident(name: str) -> str:
    s = re.sub(r"\W", "_", str(name))
    if s and s[0].isdigit():
        s = "_" + s
    if keyword.iskeyword(s) or keyword.issoftkeyword(s):
        s = s + "_"
    return s


def ref_name(ref: str) -> str:
    return ref.split("/")[-1]


# ── type mapping ──────────────────────────────────────────────────────────────

def py_type(prop: dict) -> tuple[str, tuple | None]:
    """Return (annotation, nested) where nested is (ModelName, is_list) or None."""
    if "$ref" in prop:
        n = ref_name(prop["$ref"])
        return n, (n, False)
    t = prop.get("type")
    if t == "array":
        items = prop.get("items", {}) or {}
        if "$ref" in items:
            n = ref_name(items["$ref"])
            return f"List[{n}]", (n, True)
        it = items.get("type")
        base = {"string": "str", "number": "float", "integer": "int",
                "boolean": "bool", "object": "dict"}.get(it, "Any")
        return f"List[{base}]", None
    base = {"string": "str", "number": "float", "integer": "int",
            "boolean": "bool", "object": "dict"}.get(t, "Any")
    return base, None


# ── model generation ──────────────────────────────────────────────────────────

MODELS_HEADER = '''"""CPRS API request/response models.

GENERATED from CPRS_API.openapi.json by scripts/gen_cprs_client.py — do not edit
by hand; re-run the generator instead.

Every schema is a dataclass. All fields are optional (the server validates);
required fields are noted in each docstring. ``to_dict()`` emits set fields (plus
any ``extra`` you pass for undocumented DTO fields); ``from_dict()`` parses a
response, recursively building nested models.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields as _dc_fields
from typing import Any, List, Optional


def _ser(v):
    if isinstance(v, CprsModel):
        return v.to_dict()
    if isinstance(v, list):
        return [_ser(x) for x in v]
    return v


@dataclass
class CprsModel:
    """Base for every CPRS DTO. ``extra`` carries fields the spec doesn't
    document (several DTOs are annotated empty server-side)."""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = dict(self.extra or {})
        for f in _dc_fields(self):
            if f.name == "extra":
                continue
            v = getattr(self, f.name)
            if v is not None:
                out[f.name] = _ser(v)
        return out

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            return d
        known = {f.name for f in _dc_fields(cls)} - {"extra"}
        nested = getattr(cls, "_NESTED", {})
        kw, extra = {}, {}
        for k, v in d.items():
            if k in known:
                if k in nested and v is not None:
                    mname, is_list = nested[k]
                    mc = _MODELS.get(mname)
                    if mc is not None:
                        v = ([mc.from_dict(x) for x in v] if is_list
                             else mc.from_dict(v))
                kw[k] = v
            else:
                extra[k] = v
        obj = cls(**kw)
        obj.extra = extra
        return obj
'''


def gen_models(schemas: dict) -> str:
    out = [MODELS_HEADER]
    names = list(schemas.keys())
    for name in names:
        sch = schemas[name]
        props = sch.get("properties", {}) or {}
        required = set(sch.get("required", []) or [])
        nested: dict[str, tuple] = {}
        lines = [f"@dataclass", f"class {name}(CprsModel):"]
        doc = []
        if required:
            doc.append("Required: " + ", ".join(sorted(required)) + ".")
        for pn, pv in props.items():
            if pv.get("enum"):
                doc.append(f"{pn} ∈ {pv['enum']}")
        if not props:
            doc.append("No properties documented in the spec — pass values via "
                       "keyword ``extra=`` or a plain dict to the client method.")
        if doc:
            lines.append('    """' + " ".join(doc) + '"""')
        # fields (sorted: required first for readability, but all optional)
        ordered = sorted(props.items(), key=lambda kv: (kv[0] not in required, kv[0]))
        for pn, pv in ordered:
            ann, nest = py_type(pv)
            fid = ident(pn)
            lines.append(f"    {fid}: Optional[{ann}] = None")
            if nest:
                nested[fid] = nest
        if nested:
            entries = ", ".join(f'"{k}": ("{v[0]}", {v[1]})' for k, v in nested.items())
            lines.append(f"    _NESTED = {{{entries}}}")
        if not props:
            lines.append("    pass" if False else "")  # keep dataclass body valid
        out.append("\n".join(l for l in lines if l != "" or True))
        out.append("")
    # registry
    out.append("")
    out.append("_MODELS = {")
    for name in names:
        out.append(f'    "{name}": {name},')
    out.append("}")
    out.append("")
    out.append("__all__ = [\"CprsModel\"] + list(_MODELS.keys())")
    out.append("")
    return "\n".join(out)


# ── client generation ─────────────────────────────────────────────────────────

CLIENT_HEADER = '''"""CPRS API client — every endpoint, grouped by tag.

GENERATED from CPRS_API.openapi.json by scripts/gen_cprs_client.py — do not edit
by hand; re-run the generator instead.

Usage::

    from po_extractor.cprs import CprsApiClient
    api = CprsApiClient("http://localhost:3100", api_key="…")
    run = api.evaluation.evaluate({"clientId": "…", "channel": "WHOLESALE"})
    print(run.summary.confirmed)

Auth: pass ``api_key`` (sent as ``x-api-key``) and/or ``token`` (sent as
``Authorization: Bearer``). ``login`` + ``set_token`` wire up bearer auth.

Errors: non-2xx responses and network failures raise :class:`CprsError`. This is
the raw API surface — the best-effort, buy-plan-specific helper lives separately
in ``po_extractor/utils/cprs_client.py``.
"""
from __future__ import annotations

from typing import Any, Optional

from .models import *  # noqa: F401,F403 — every DTO
from .models import CprsModel


class CprsError(Exception):
    """Raised on a non-2xx CPRS response or a transport failure."""

    def __init__(self, status: int, message: str, body: Any = None):
        super().__init__(f"CPRS API error {status}: {message}")
        self.status = status
        self.message = message
        self.body = body


def _body(x):
    """Serialize a request body: a model -> dict, a dict -> itself, None -> None."""
    if x is None:
        return None
    if isinstance(x, CprsModel):
        return x.to_dict()
    return x


class _Transport:
    def __init__(self, base_url: str, api_key: str = "", token: str = "",
                 timeout: float = 15.0):
        base = (base_url or "").strip().rstrip("/")
        if base and not base.endswith("/api/v1"):
            base = base + "/api/v1"
        self.base = base
        self.api_key = (api_key or "").strip()
        self.token = (token or "").strip()
        self.timeout = timeout

    def _headers(self, json_body: bool) -> dict:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def request(self, method: str, path: str, params=None, body=None,
                binary: bool = False):
        if not self.base:
            raise CprsError(0, "No CPRS base URL configured")
        import requests
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            r = requests.request(
                method, self.base + path,
                params=params or None,
                json=body if body is not None else None,
                headers=self._headers(json_body=body is not None),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise CprsError(0, str(exc))
        if not (200 <= r.status_code < 300):
            msg = (r.text or "")[:300]
            try:
                j = r.json()
                msg = j.get("message", msg) if isinstance(j, dict) else msg
            except Exception:
                pass
            raise CprsError(r.status_code, msg, getattr(r, "text", None))
        if binary:
            return r.content
        if not r.content:
            return None
        try:
            return r.json()
        except Exception:
            return r.content
'''


def response_model(op: dict) -> tuple | None:
    """Return (ModelName, is_list) if a 2xx JSON response references a schema."""
    for code in ("200", "201"):
        rv = op.get("responses", {}).get(code)
        if not rv:
            continue
        ct = (rv.get("content") or {}).get("application/json")
        if not ct:
            continue
        sch = ct.get("schema", {}) or {}
        if "$ref" in sch:
            return ref_name(sch["$ref"]), False
        if sch.get("type") == "array":
            items = sch.get("items", {}) or {}
            if "$ref" in items:
                return ref_name(items["$ref"]), True
    return None


def is_binary(op: dict) -> bool:
    for code in ("200", "201"):
        rv = op.get("responses", {}).get(code)
        if not rv:
            continue
        cts = set((rv.get("content") or {}).keys())
        if cts and "application/json" not in cts:
            return True
    return False


def gen_client(spec: dict) -> str:
    paths = spec.get("paths", {})
    # group operations by tag
    by_tag: dict[str, list] = {}
    for path, methods in paths.items():
        rel = path[len("/api/v1"):] if path.startswith("/api/v1") else path
        for m, op in methods.items():
            if m not in ("get", "post", "put", "patch", "delete"):
                continue
            tag = (op.get("tags") or ["default"])[0]
            by_tag.setdefault(tag, []).append((m, rel, op))

    out = [CLIENT_HEADER]
    tag_attrs = []      # (attr, ClassName)
    for tag in by_tag:
        cls = "_" + re.sub(r"\W", "", tag.title().replace(" ", "")) + "Api"
        attr = snake(tag)
        tag_attrs.append((attr, cls))
        out.append(f"class {cls}:")
        out.append(f'    """{tag} endpoints."""')
        out.append("    def __init__(self, t: _Transport):")
        out.append("        self._t = t")
        out.append("")
        used: dict[str, int] = {}
        for m, rel, op in by_tag[tag]:
            opid = op.get("operationId", "")
            base_name = snake(opid.split("_", 1)[1] if "_" in opid else opid) or m
            name = base_name
            if name in used:                 # disambiguate collisions within a tag
                used[base_name] += 1
                name = f"{base_name}_{m}"
                if name in used:
                    name = f"{base_name}_{used[base_name]}"
            used.setdefault(name, 0)
            used[base_name] = used.get(base_name, 0)

            path_params = re.findall(r"\{(\w+)\}", rel)
            query = [p for p in op.get("parameters", []) if p.get("in") == "query"]
            has_body = "requestBody" in op
            body_req = op.get("requestBody", {}).get("required", False)

            # signature
            args = ["self"]
            for pp in path_params:
                args.append(ident(pp))
            if has_body:
                args.append("body" + ("" if body_req else "=None"))
            for q in query:
                args.append(f"{ident(q['name'])}=None")
            sig = ", ".join(args)

            # docstring
            summary = op.get("summary") or ""
            qreq = [q["name"] for q in query if q.get("required")]
            doc = f"{m.upper()} {rel}" + (f" — {summary}" if summary else "")
            if qreq:
                doc += f"  (required query: {', '.join(qreq)})"

            # path expression
            pathexpr = '"' + rel + '"'
            if path_params:
                fpath = rel
                for pp in path_params:
                    fpath = fpath.replace("{" + pp + "}", "{" + ident(pp) + "}")
                pathexpr = 'f"' + fpath + '"'

            # params dict
            if query:
                items = ", ".join(f'"{q["name"]}": {ident(q["name"])}' for q in query)
                params_expr = "{" + items + "}"
            else:
                params_expr = "None"

            binary = is_binary(op)
            call = (f'self._t.request("{m.upper()}", {pathexpr}, '
                    f'params={params_expr}, '
                    f'body={"_body(body)" if has_body else "None"}, '
                    f'binary={binary})')

            out.append(f"    def {name}({sig}):")
            out.append(f'        """{doc}"""')
            rmodel = response_model(op)
            if rmodel and not binary:
                mname, is_list = rmodel
                out.append(f"        _r = {call}")
                if is_list:
                    out.append(f"        return [{mname}.from_dict(x) for x in (_r or [])]")
                else:
                    out.append(f"        return {mname}.from_dict(_r)")
            else:
                out.append(f"        return {call}")
            out.append("")
        out.append("")

    # top-level client
    out.append("class CprsApiClient:")
    out.append('    """Full CPRS API client. Access endpoints via tag groups, e.g.')
    out.append('    ``client.evaluation.evaluate(...)``, ``client.clients.get_warehouses(id)``."""')
    out.append("")
    out.append("    def __init__(self, base_url: str, api_key: str = \"\", "
               "token: str = \"\", timeout: float = 15.0):")
    out.append("        self._t = _Transport(base_url, api_key, token, timeout)")
    for attr, cls in tag_attrs:
        out.append(f"        self.{attr} = {cls}(self._t)")
    out.append("")
    out.append("    @property")
    out.append("    def base(self) -> str:")
    out.append("        return self._t.base")
    out.append("")
    out.append("    def set_token(self, token: str) -> None:")
    out.append('        """Attach a bearer token (e.g. from ``auth.login``) to later calls."""')
    out.append("        self._t.token = (token or \"\").strip()")
    out.append("")
    out.append("")
    out.append("def cprs_api_from_settings(store):")
    out.append('    """Build a CprsApiClient from an app-settings store, or None if unset."""')
    out.append("    from ..store.app_settings_store import KEY_CPRS_BASE_URL, KEY_CPRS_API_KEY")
    out.append("    base = store.get(KEY_CPRS_BASE_URL, \"\")")
    out.append("    if not (base or \"\").strip():")
    out.append("        return None")
    out.append("    return CprsApiClient(base, store.get(KEY_CPRS_API_KEY, \"\"))")
    out.append("")
    return "\n".join(out)


def main() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    schemas = spec.get("components", {}).get("schemas", {})
    (CPRS / "models.py").write_text(gen_models(schemas), encoding="utf-8")
    (CPRS / "client.py").write_text(gen_client(spec), encoding="utf-8")
    n_ops = sum(1 for _p, ms in spec.get("paths", {}).items()
                for _m in ms if _m in ("get", "post", "put", "patch", "delete"))
    print(f"generated: {len(schemas)} models, {n_ops} operations "
          f"(spec v{spec.get('info', {}).get('version')})")


if __name__ == "__main__":
    main()
