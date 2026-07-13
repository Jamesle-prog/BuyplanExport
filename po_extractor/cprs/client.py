"""CPRS API client — every endpoint, grouped by tag.

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

class _HealthApi:
    """health endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def check(self):
        """GET /health"""
        return self._t.request("GET", "/health", params=None, body=None, binary=False)


class _VersionApi:
    """version endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def version(self):
        """GET /version — Current system version and latest release notes"""
        return self._t.request("GET", "/version", params=None, body=None, binary=False)

    def changelog(self):
        """GET /version/changelog — Full release history (newest first)"""
        return self._t.request("GET", "/version/changelog", params=None, body=None, binary=False)


class _AuthApi:
    """Auth endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def login(self, body):
        """POST /auth/login"""
        return self._t.request("POST", "/auth/login", params=None, body=_body(body), binary=False)

    def me(self):
        """GET /auth/me"""
        return self._t.request("GET", "/auth/me", params=None, body=None, binary=False)

    def change_password(self, body):
        """POST /auth/change-password"""
        return self._t.request("POST", "/auth/change-password", params=None, body=_body(body), binary=False)

    def update_user(self, id, body):
        """PATCH /auth/users/{id}"""
        return self._t.request("PATCH", f"/auth/users/{id}", params=None, body=_body(body), binary=False)

    def list(self):
        """GET /auth/users"""
        return self._t.request("GET", "/auth/users", params=None, body=None, binary=False)

    def create(self, body):
        """POST /auth/users"""
        return self._t.request("POST", "/auth/users", params=None, body=_body(body), binary=False)


class _DocumentsApi:
    """Documents endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def upload(self):
        """POST /documents/upload"""
        return self._t.request("POST", "/documents/upload", params=None, body=None, binary=False)

    def find_all(self, clientId=None, documentType=None, status=None, page=None, limit=None):
        """GET /documents"""
        return self._t.request("GET", "/documents", params={"clientId": clientId, "documentType": documentType, "status": status, "page": page, "limit": limit}, body=None, binary=False)

    def find_one(self, id):
        """GET /documents/{id}"""
        return self._t.request("GET", f"/documents/{id}", params=None, body=None, binary=False)

    def override_type(self, id, body):
        """PATCH /documents/{id}/classify"""
        return self._t.request("PATCH", f"/documents/{id}/classify", params=None, body=_body(body), binary=False)

    def get_version_history(self, id):
        """GET /documents/{id}/versions"""
        return self._t.request("GET", f"/documents/{id}/versions", params=None, body=None, binary=False)

    def extract_update_history(self, id):
        """POST /documents/{id}/extract-history"""
        return self._t.request("POST", f"/documents/{id}/extract-history", params=None, body=None, binary=False)


class _ClientsApi:
    """Clients endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def find_all(self, active=None):
        """GET /clients"""
        return self._t.request("GET", "/clients", params={"active": active}, body=None, binary=False)

    def find_one(self, id):
        """GET /clients/{id}"""
        return self._t.request("GET", f"/clients/{id}", params=None, body=None, binary=False)

    def get_warehouses(self, id):
        """GET /clients/{id}/warehouses"""
        return self._t.request("GET", f"/clients/{id}/warehouses", params=None, body=None, binary=False)

    def get_accounts(self, id):
        """GET /clients/{id}/accounts"""
        return self._t.request("GET", f"/clients/{id}/accounts", params=None, body=None, binary=False)

    def get_suppliers(self, id):
        """GET /clients/{id}/suppliers"""
        return self._t.request("GET", f"/clients/{id}/suppliers", params=None, body=None, binary=False)


class _ExtractionApi:
    """Extraction endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def extract(self, id):
        """POST /documents/{id}/extract"""
        return self._t.request("POST", f"/documents/{id}/extract", params=None, body=None, binary=False)

    def get_fragments(self, id, fragmentType=None, requiresManualEntry=None, minConfidence=None, page=None, limit=None):
        """GET /documents/{id}/fragments"""
        return self._t.request("GET", f"/documents/{id}/fragments", params={"fragmentType": fragmentType, "requiresManualEntry": requiresManualEntry, "minConfidence": minConfidence, "page": page, "limit": limit}, body=None, binary=False)


class _FragmentsApi:
    """Fragments endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def find_all(self, documentId=None, clientId=None, fragmentType=None, requiresManualEntry=None, minConfidence=None, parserName=None, page=None, limit=None):
        """GET /fragments"""
        return self._t.request("GET", "/fragments", params={"documentId": documentId, "clientId": clientId, "fragmentType": fragmentType, "requiresManualEntry": requiresManualEntry, "minConfidence": minConfidence, "parserName": parserName, "page": page, "limit": limit}, body=None, binary=False)

    def pending_review(self, clientId=None, documentType=None, page=None, limit=None):
        """GET /fragments/pending-review"""
        return self._t.request("GET", "/fragments/pending-review", params={"clientId": clientId, "documentType": documentType, "page": page, "limit": limit}, body=None, binary=False)

    def stats(self, documentId=None):
        """GET /fragments/stats"""
        return self._t.request("GET", "/fragments/stats", params={"documentId": documentId}, body=None, binary=False)

    def find_one(self, id):
        """GET /fragments/{id}"""
        return self._t.request("GET", f"/fragments/{id}", params=None, body=None, binary=False)


class _MappingApi:
    """Mapping endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def map_document(self, id):
        """POST /documents/{id}/map"""
        return self._t.request("POST", f"/documents/{id}/map", params=None, body=None, binary=False)

    def find_requirements(self, clientId=None, domain=None, subtype=None, priorityTier=None, page=None, limit=None):
        """GET /requirements"""
        return self._t.request("GET", "/requirements", params={"clientId": clientId, "domain": domain, "subtype": subtype, "priorityTier": priorityTier, "page": page, "limit": limit}, body=None, binary=False)

    def create(self, body):
        """POST /requirements"""
        return self._t.request("POST", "/requirements", params=None, body=_body(body), binary=False)

    def find_one(self, id):
        """GET /requirements/{id}"""
        return self._t.request("GET", f"/requirements/{id}", params=None, body=None, binary=False)

    def deactivate(self, id, reason=None):
        """DELETE /requirements/{id}"""
        return self._t.request("DELETE", f"/requirements/{id}", params={"reason": reason}, body=None, binary=False)

    def add_condition(self, id, body):
        """POST /requirements/{id}/conditions"""
        return self._t.request("POST", f"/requirements/{id}/conditions", params=None, body=_body(body), binary=False)


class _ReviewApi:
    """Review endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def get_queue(self, clientId=None, domain=None, status=None, maxConfidence=None, page=None, limit=None):
        """GET /review/queue"""
        return self._t.request("GET", "/review/queue", params={"clientId": clientId, "domain": domain, "status": status, "maxConfidence": maxConfidence, "page": page, "limit": limit}, body=None, binary=False)

    def stats(self, clientId=None):
        """GET /review/stats"""
        return self._t.request("GET", "/review/stats", params={"clientId": clientId}, body=None, binary=False)

    def decide(self, id, body):
        """POST /review/mappings/{id}/decide"""
        return self._t.request("POST", f"/review/mappings/{id}/decide", params=None, body=_body(body), binary=False)

    def requeue(self, id):
        """POST /review/mappings/{id}/requeue"""
        return self._t.request("POST", f"/review/mappings/{id}/requeue", params=None, body=None, binary=False)

    def history(self, id):
        """GET /review/mappings/{id}/history"""
        return self._t.request("GET", f"/review/mappings/{id}/history", params=None, body=None, binary=False)

    def batch_decide(self, body):
        """POST /review/batch-decide"""
        return self._t.request("POST", "/review/batch-decide", params=None, body=_body(body), binary=False)

    def auto_approve(self, body):
        """POST /review/auto-approve"""
        return self._t.request("POST", "/review/auto-approve", params=None, body=_body(body), binary=False)


class _EvaluationApi:
    """Evaluation endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def evaluate(self, body):
        """POST /evaluate — Resolve the requirement set for an order context (the primary integration)."""
        _r = self._t.request("POST", "/evaluate", params=None, body=_body(body), binary=False)
        return EvaluationRunResponseDto.from_dict(_r)

    def evaluate_po(self, body):
        """POST /evaluate/po — Decode a raw PO into an order context and evaluate it (one-call PO intake)."""
        return self._t.request("POST", "/evaluate/po", params=None, body=_body(body), binary=False)

    def list(self, clientId=None, status=None, page=None, limit=None):
        """GET /evaluation-runs — List stored evaluation runs."""
        return self._t.request("GET", "/evaluation-runs", params={"clientId": clientId, "status": status, "page": page, "limit": limit}, body=None, binary=False)

    def find_one(self, id):
        """GET /evaluation-runs/{id}"""
        return self._t.request("GET", f"/evaluation-runs/{id}", params=None, body=None, binary=False)


class _WarehouseLookupApi:
    """Warehouse Lookup endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def resolve(self, ship_to=None, client_id=None):
        """GET /warehouse-lookup/resolve — Resolve warehouse code from ship-to address"""
        return self._t.request("GET", "/warehouse-lookup/resolve", params={"ship_to": ship_to, "client_id": client_id}, body=None, binary=False)

    def resolve_post(self, body):
        """POST /warehouse-lookup/resolve — Resolve warehouse code (POST body)"""
        return self._t.request("POST", "/warehouse-lookup/resolve", params=None, body=_body(body), binary=False)

    def bulk(self, body):
        """POST /warehouse-lookup/bulk — Bulk resolve — pass all ship-to strings from a PO"""
        return self._t.request("POST", "/warehouse-lookup/bulk", params=None, body=_body(body), binary=False)

    def list_addresses(self, client_id=None):
        """GET /warehouse-lookup/addresses — List all known DC address mappings"""
        return self._t.request("GET", "/warehouse-lookup/addresses", params={"client_id": client_id}, body=None, binary=False)

    def add_address(self, body):
        """POST /warehouse-lookup/addresses — Add a new DC address mapping"""
        return self._t.request("POST", "/warehouse-lookup/addresses", params=None, body=_body(body), binary=False)


class _ExportApi:
    """Export endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def download_excel(self, runId):
        """GET /export/runs/{runId}/excel"""
        return self._t.request("GET", f"/export/runs/{runId}/excel", params=None, body=None, binary=True)

    def download_pdf(self, runId):
        """GET /export/runs/{runId}/pdf"""
        return self._t.request("GET", f"/export/runs/{runId}/pdf", params=None, body=None, binary=True)

    def get_requirements(self, clientId=None, domain=None, accountCode=None):
        """GET /export/requirements  (required query: clientId)"""
        return self._t.request("GET", "/export/requirements", params={"clientId": clientId, "domain": domain, "accountCode": accountCode}, body=None, binary=False)

    def get_summary(self, runId):
        """GET /export/runs/{runId}/summary"""
        return self._t.request("GET", f"/export/runs/{runId}/summary", params=None, body=None, binary=False)


class _AdminApi:
    """Admin endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def get_stats(self):
        """GET /admin/stats"""
        return self._t.request("GET", "/admin/stats", params=None, body=None, binary=False)

    def list_vocab(self, domain=None):
        """GET /admin/vocabulary"""
        return self._t.request("GET", "/admin/vocabulary", params={"domain": domain}, body=None, binary=False)

    def create_vocab(self, body):
        """POST /admin/vocabulary"""
        return self._t.request("POST", "/admin/vocabulary", params=None, body=_body(body), binary=False)

    def update_vocab(self, id, body):
        """PATCH /admin/vocabulary/{id}"""
        return self._t.request("PATCH", f"/admin/vocabulary/{id}", params=None, body=_body(body), binary=False)

    def deactivate_vocab(self, id):
        """DELETE /admin/vocabulary/{id}"""
        return self._t.request("DELETE", f"/admin/vocabulary/{id}", params=None, body=None, binary=False)

    def list_synonyms(self, clientId=None, domain=None):
        """GET /admin/synonyms"""
        return self._t.request("GET", "/admin/synonyms", params={"clientId": clientId, "domain": domain}, body=None, binary=False)

    def create_synonym(self, body):
        """POST /admin/synonyms"""
        return self._t.request("POST", "/admin/synonyms", params=None, body=_body(body), binary=False)

    def delete_synonym(self, id):
        """DELETE /admin/synonyms/{id}"""
        return self._t.request("DELETE", f"/admin/synonyms/{id}", params=None, body=None, binary=False)

    def list_clients(self):
        """GET /admin/clients"""
        return self._t.request("GET", "/admin/clients", params=None, body=None, binary=False)

    def get_client_config(self, id):
        """GET /admin/clients/{id}/config"""
        return self._t.request("GET", f"/admin/clients/{id}/config", params=None, body=None, binary=False)

    def update_client_config(self, id, body):
        """PATCH /admin/clients/{id}/config"""
        return self._t.request("PATCH", f"/admin/clients/{id}/config", params=None, body=_body(body), binary=False)

    def list_requirements(self, clientId=None, domain=None, subtype=None, priorityTier=None, activeOnly=None, page=None, limit=None):
        """GET /admin/requirements"""
        return self._t.request("GET", "/admin/requirements", params={"clientId": clientId, "domain": domain, "subtype": subtype, "priorityTier": priorityTier, "activeOnly": activeOnly, "page": page, "limit": limit}, body=None, binary=False)

    def update_requirement(self, id, body):
        """PATCH /admin/requirements/{id}"""
        return self._t.request("PATCH", f"/admin/requirements/{id}", params=None, body=_body(body), binary=False)

    def deactivate_requirement(self, id, body):
        """POST /admin/requirements/{id}/deactivate"""
        return self._t.request("POST", f"/admin/requirements/{id}/deactivate", params=None, body=_body(body), binary=False)


class _SearchApi:
    """Search endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def search_requirements(self, clientId=None, domain=None, subtype=None, keyword=None, priorityTier=None, warehouseCode=None, accountCode=None, activeOnly=None, page=None, limit=None, include=None):
        """GET /search/requirements"""
        return self._t.request("GET", "/search/requirements", params={"clientId": clientId, "domain": domain, "subtype": subtype, "keyword": keyword, "priorityTier": priorityTier, "warehouseCode": warehouseCode, "accountCode": accountCode, "activeOnly": activeOnly, "page": page, "limit": limit, "include": include}, body=None, binary=False)

    def search_fragments(self, documentId=None, clientId=None, fragmentType=None, warehouseCode=None, trimType=None, keyword=None, requiresManualEntry=None, page=None, limit=None):
        """GET /search/fragments"""
        return self._t.request("GET", "/search/fragments", params={"documentId": documentId, "clientId": clientId, "fragmentType": fragmentType, "warehouseCode": warehouseCode, "trimType": trimType, "keyword": keyword, "requiresManualEntry": requiresManualEntry, "page": page, "limit": limit}, body=None, binary=False)

    def search_documents(self, clientId=None, documentType=None, status=None, keyword=None, page=None, limit=None):
        """GET /search/documents"""
        return self._t.request("GET", "/search/documents", params={"clientId": clientId, "documentType": documentType, "status": status, "keyword": keyword, "page": page, "limit": limit}, body=None, binary=False)

    def trace_requirement(self, id):
        """GET /search/requirements/{id}/trace"""
        return self._t.request("GET", f"/search/requirements/{id}/trace", params=None, body=None, binary=False)

    def trace_fragment(self, id):
        """GET /search/fragments/{id}/trace"""
        return self._t.request("GET", f"/search/fragments/{id}/trace", params=None, body=None, binary=False)


class _AuditApi:
    """Audit endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def get_requirement_history(self, id):
        """GET /audit/requirements/{id}"""
        return self._t.request("GET", f"/audit/requirements/{id}", params=None, body=None, binary=False)

    def get_document_lineage(self, id):
        """GET /audit/documents/{id}"""
        return self._t.request("GET", f"/audit/documents/{id}", params=None, body=None, binary=False)

    def get_review_decisions(self, clientId=None, reviewer=None, decision=None, domain=None, from_=None, to=None, page=None, limit=None):
        """GET /audit/review-decisions"""
        return self._t.request("GET", "/audit/review-decisions", params={"clientId": clientId, "reviewer": reviewer, "decision": decision, "domain": domain, "from": from_, "to": to, "page": page, "limit": limit}, body=None, binary=False)

    def get_mapping_timeline(self, id):
        """GET /audit/mappings/{id}"""
        return self._t.request("GET", f"/audit/mappings/{id}", params=None, body=None, binary=False)

    def get_evaluation_history(self, clientId=None, warehouseCode=None, accountCode=None, page=None, limit=None):
        """GET /audit/evaluation-runs"""
        return self._t.request("GET", "/audit/evaluation-runs", params={"clientId": clientId, "warehouseCode": warehouseCode, "accountCode": accountCode, "page": page, "limit": limit}, body=None, binary=False)


class _AiassistApi:
    """AiAssist endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def upload(self):
        """POST /ai/upload"""
        return self._t.request("POST", "/ai/upload", params=None, body=None, binary=False)

    def export(self, format, body):
        """POST /ai/export/{format}"""
        return self._t.request("POST", f"/ai/export/{format}", params=None, body=_body(body), binary=False)

    def ask(self, body):
        """POST /ai/ask"""
        return self._t.request("POST", "/ai/ask", params=None, body=_body(body), binary=False)

    def suggest_classification(self, id):
        """GET /ai/documents/{id}/suggest-classification"""
        return self._t.request("GET", f"/ai/documents/{id}/suggest-classification", params=None, body=None, binary=False)

    def suggest_mapping(self, id):
        """GET /ai/fragments/{id}/suggest-mapping"""
        return self._t.request("GET", f"/ai/fragments/{id}/suggest-mapping", params=None, body=None, binary=False)

    def suggest_extraction(self, id):
        """GET /ai/fragments/{id}/suggest-extraction"""
        return self._t.request("GET", f"/ai/fragments/{id}/suggest-extraction", params=None, body=None, binary=False)

    def explain_requirement(self, id):
        """GET /ai/requirements/{id}/explain"""
        return self._t.request("GET", f"/ai/requirements/{id}/explain", params=None, body=None, binary=False)

    def explain_checklist(self, runId):
        """GET /ai/evaluation-runs/{runId}/explain"""
        return self._t.request("GET", f"/ai/evaluation-runs/{runId}/explain", params=None, body=None, binary=False)

    def apply_mapping_suggestion(self, id, body):
        """POST /ai/fragments/{id}/apply-suggestion"""
        return self._t.request("POST", f"/ai/fragments/{id}/apply-suggestion", params=None, body=_body(body), binary=False)


class _ManualimagesApi:
    """ManualImages endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def render_red_sticker(self, code=None, pms=None, customer=None):
        """GET /manual-images/render/red-sticker"""
        return self._t.request("GET", "/manual-images/render/red-sticker", params={"code": code, "pms": pms, "customer": customer}, body=None, binary=False)

    def list(self, clientId=None, sheet=None, tag=None, limit=None):
        """GET /manual-images"""
        return self._t.request("GET", "/manual-images", params={"clientId": clientId, "sheet": sheet, "tag": tag, "limit": limit}, body=None, binary=False)

    def sheets(self, clientId=None):
        """GET /manual-images/sheets"""
        return self._t.request("GET", "/manual-images/sheets", params={"clientId": clientId}, body=None, binary=False)

    def get_one(self, id):
        """GET /manual-images/{id}"""
        return self._t.request("GET", f"/manual-images/{id}", params=None, body=None, binary=False)

    def get_file(self, id):
        """GET /manual-images/{id}/file"""
        return self._t.request("GET", f"/manual-images/{id}/file", params=None, body=None, binary=True)


class _WashinglabelApi:
    """WashingLabel endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def check(self, body):
        """POST /washing-label/check"""
        return self._t.request("POST", "/washing-label/check", params=None, body=_body(body), binary=False)


class _ProductionsubmissionApi:
    """ProductionSubmission endpoints."""
    def __init__(self, t: _Transport):
        self._t = t

    def upload(self):
        """POST /production-submission/upload"""
        return self._t.request("POST", "/production-submission/upload", params=None, body=None, binary=False)

    def list(self, clientId=None, styleNo=None, po=None, season=None, type_=None, limit=None):
        """GET /production-submission"""
        return self._t.request("GET", "/production-submission", params={"clientId": clientId, "styleNo": styleNo, "po": po, "season": season, "type": type_, "limit": limit}, body=None, binary=False)

    def compare(self, aId=None, bId=None):
        """GET /production-submission/compare"""
        return self._t.request("GET", "/production-submission/compare", params={"aId": aId, "bId": bId}, body=None, binary=False)

    def get_one(self, id):
        """GET /production-submission/{id}"""
        return self._t.request("GET", f"/production-submission/{id}", params=None, body=None, binary=False)

    def get_file(self, id):
        """GET /production-submission/{id}/file"""
        return self._t.request("GET", f"/production-submission/{id}/file", params=None, body=None, binary=False)

    def patch_fields(self, id):
        """PATCH /production-submission/{id}/fields"""
        return self._t.request("PATCH", f"/production-submission/{id}/fields", params=None, body=None, binary=False)

    def recheck(self, id):
        """POST /production-submission/{id}/recheck"""
        return self._t.request("POST", f"/production-submission/{id}/recheck", params=None, body=None, binary=False)


class CprsApiClient:
    """Full CPRS API client. Access endpoints via tag groups, e.g.
    ``client.evaluation.evaluate(...)``, ``client.clients.get_warehouses(id)``."""

    def __init__(self, base_url: str, api_key: str = "", token: str = "", timeout: float = 15.0):
        self._t = _Transport(base_url, api_key, token, timeout)
        self.health = _HealthApi(self._t)
        self.version = _VersionApi(self._t)
        self.auth = _AuthApi(self._t)
        self.documents = _DocumentsApi(self._t)
        self.clients = _ClientsApi(self._t)
        self.extraction = _ExtractionApi(self._t)
        self.fragments = _FragmentsApi(self._t)
        self.mapping = _MappingApi(self._t)
        self.review = _ReviewApi(self._t)
        self.evaluation = _EvaluationApi(self._t)
        self.warehouse_lookup = _WarehouseLookupApi(self._t)
        self.export = _ExportApi(self._t)
        self.admin = _AdminApi(self._t)
        self.search = _SearchApi(self._t)
        self.audit = _AuditApi(self._t)
        self.ai_assist = _AiassistApi(self._t)
        self.manual_images = _ManualimagesApi(self._t)
        self.washing_label = _WashinglabelApi(self._t)
        self.production_submission = _ProductionsubmissionApi(self._t)

    @property
    def base(self) -> str:
        return self._t.base

    def set_token(self, token: str) -> None:
        """Attach a bearer token (e.g. from ``auth.login``) to later calls."""
        self._t.token = (token or "").strip()


def cprs_api_from_settings(store):
    """Build a CprsApiClient from an app-settings store, or None if unset."""
    from ..store.app_settings_store import KEY_CPRS_BASE_URL, KEY_CPRS_API_KEY
    base = store.get(KEY_CPRS_BASE_URL, "")
    if not (base or "").strip():
        return None
    return CprsApiClient(base, store.get(KEY_CPRS_API_KEY, ""))
