"""CPRS API request/response models.

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

@dataclass
class LoginDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class ChangePasswordDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class UpdateUserDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class CreateUserDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class OverrideTypeDto(CprsModel):
    """Required: documentType."""
    documentType: Optional[str] = None
    reason: Optional[str] = None

@dataclass
class CreateRequirementDto(CprsModel):
    """Required: clientId, domain, priorityTier, structuredOutput, subtype, title."""
    clientId: Optional[str] = None
    domain: Optional[str] = None
    priorityTier: Optional[float] = None
    structuredOutput: Optional[dict] = None
    subtype: Optional[str] = None
    title: Optional[str] = None
    effectiveFrom: Optional[str] = None
    effectiveTo: Optional[str] = None
    runtimeInputField: Optional[str] = None
    runtimeInputRequired: Optional[bool] = None

@dataclass
class AddConditionDto(CprsModel):
    """Required: fieldName, operator, valueJson."""
    fieldName: Optional[str] = None
    operator: Optional[str] = None
    valueJson: Optional[dict] = None
    conditionGroup: Optional[float] = None

@dataclass
class ReviewDecisionDto(CprsModel):
    """Required: decision, reviewer. decision ∈ ['approved', 'corrected', 'rejected', 'deferred']"""
    decision: Optional[str] = None
    reviewer: Optional[str] = None
    approvedValue: Optional[dict] = None
    reason: Optional[str] = None

@dataclass
class BatchDecideDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class AutoApproveDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class CreateOrderContextDto(CprsModel):
    """Required: channel, clientId. channel ∈ ['WHOLESALE', 'RETAIL', 'ECOMM', 'OFF_PRICE', 'INTERNATIONAL']"""
    channel: Optional[str] = None
    clientId: Optional[str] = None
    accountCode: Optional[str] = None
    accountId: Optional[str] = None
    contextFields: Optional[dict] = None
    coo: Optional[str] = None
    deliveryGroup: Optional[str] = None
    deliveryMonth: Optional[str] = None
    destinationWarehouseId: Optional[str] = None
    garmentCategory: Optional[str] = None
    poNumber: Optional[str] = None
    programme: Optional[str] = None
    qty: Optional[float] = None
    season: Optional[str] = None
    shipMode: Optional[str] = None
    styleId: Optional[str] = None
    warehouseCode: Optional[str] = None

@dataclass
class EvaluationSummaryDto(CprsModel):
    """Required: confirmed, conflict, missing_mandatory_context, not_applicable, pending_input, total."""
    confirmed: Optional[float] = None
    conflict: Optional[float] = None
    missing_mandatory_context: Optional[float] = None
    not_applicable: Optional[float] = None
    pending_input: Optional[float] = None
    total: Optional[float] = None

@dataclass
class EvaluationResultItemDto(CprsModel):
    """Required: appliedPriorityTier, domain, images, resultJson, scope, status, subtype, title, winningRequirementId. status ∈ ['confirmed', 'pending_input', 'conflict', 'not_applicable', 'missing_mandatory_context'] scope ∈ ['brand', 'corporate']"""
    appliedPriorityTier: Optional[float] = None
    domain: Optional[str] = None
    images: Optional[List[dict]] = None
    resultJson: Optional[dict] = None
    scope: Optional[str] = None
    status: Optional[str] = None
    subtype: Optional[str] = None
    title: Optional[str] = None
    winningRequirementId: Optional[str] = None

@dataclass
class EvaluationRunResponseDto(CprsModel):
    """Required: evaluationRunId, orderContextId, results, status, summary."""
    evaluationRunId: Optional[str] = None
    orderContextId: Optional[str] = None
    results: Optional[List[EvaluationResultItemDto]] = None
    status: Optional[str] = None
    summary: Optional[EvaluationSummaryDto] = None
    _NESTED = {"results": ("EvaluationResultItemDto", True), "summary": ("EvaluationSummaryDto", False)}

@dataclass
class EvaluatePoDto(CprsModel):
    """channel ∈ ['WHOLESALE', 'RETAIL', 'ECOMM', 'OFF_PRICE', 'INTERNATIONAL']"""
    account: Optional[str] = None
    accountCode: Optional[str] = None
    brand: Optional[str] = None
    channel: Optional[str] = None
    clientId: Optional[str] = None
    contextFields: Optional[dict] = None
    coo: Optional[str] = None
    garmentCategory: Optional[str] = None
    poNumber: Optional[str] = None
    shipTo: Optional[str] = None
    style: Optional[str] = None
    warehouseCode: Optional[str] = None

@dataclass
class LookupDto(CprsModel):
    """Required: ship_to."""
    ship_to: Optional[str] = None
    client_id: Optional[str] = None

@dataclass
class BulkLookupDto(CprsModel):
    """Required: addresses."""
    addresses: Optional[List[str]] = None
    client_id: Optional[str] = None

@dataclass
class AddAddressDto(CprsModel):
    """Required: account_code, dc_name, warehouse_id."""
    account_code: Optional[str] = None
    dc_name: Optional[str] = None
    warehouse_id: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    client_id: Optional[str] = None
    country: Optional[str] = None
    is_crossdock: Optional[bool] = None
    is_poe: Optional[bool] = None
    match_keywords: Optional[List[str]] = None
    notes: Optional[str] = None
    state_province: Optional[str] = None
    zip_postal: Optional[str] = None

@dataclass
class CreateVocabTermDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class UpdateVocabTermDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class CreateSynonymDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class UpdateClientConfigDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class UpdateRequirementDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class DeactivateRequirementDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class ExportDto(CprsModel):
    """Required: answer, question."""
    answer: Optional[str] = None
    question: Optional[str] = None
    clientName: Optional[str] = None
    generatedAt: Optional[str] = None

@dataclass
class AskDto(CprsModel):
    """Required: question."""
    question: Optional[str] = None
    clientId: Optional[str] = None
    fileContextId: Optional[str] = None

@dataclass
class ApplySuggestionDto(CprsModel):
    """No properties documented in the spec — pass values via keyword ``extra=`` or a plain dict to the client method."""


@dataclass
class FiberInputDto(CprsModel):
    """Required: fiber."""
    fiber: Optional[str] = None
    percent: Optional[float] = None
    section: Optional[str] = None

@dataclass
class CheckWashingLabelDto(CprsModel):
    clientId: Optional[str] = None
    contentLine: Optional[str] = None
    fibers: Optional[List[FiberInputDto]] = None
    _NESTED = {"fibers": ("FiberInputDto", True)}


_MODELS = {
    "LoginDto": LoginDto,
    "ChangePasswordDto": ChangePasswordDto,
    "UpdateUserDto": UpdateUserDto,
    "CreateUserDto": CreateUserDto,
    "OverrideTypeDto": OverrideTypeDto,
    "CreateRequirementDto": CreateRequirementDto,
    "AddConditionDto": AddConditionDto,
    "ReviewDecisionDto": ReviewDecisionDto,
    "BatchDecideDto": BatchDecideDto,
    "AutoApproveDto": AutoApproveDto,
    "CreateOrderContextDto": CreateOrderContextDto,
    "EvaluationSummaryDto": EvaluationSummaryDto,
    "EvaluationResultItemDto": EvaluationResultItemDto,
    "EvaluationRunResponseDto": EvaluationRunResponseDto,
    "EvaluatePoDto": EvaluatePoDto,
    "LookupDto": LookupDto,
    "BulkLookupDto": BulkLookupDto,
    "AddAddressDto": AddAddressDto,
    "CreateVocabTermDto": CreateVocabTermDto,
    "UpdateVocabTermDto": UpdateVocabTermDto,
    "CreateSynonymDto": CreateSynonymDto,
    "UpdateClientConfigDto": UpdateClientConfigDto,
    "UpdateRequirementDto": UpdateRequirementDto,
    "DeactivateRequirementDto": DeactivateRequirementDto,
    "ExportDto": ExportDto,
    "AskDto": AskDto,
    "ApplySuggestionDto": ApplySuggestionDto,
    "FiberInputDto": FiberInputDto,
    "CheckWashingLabelDto": CheckWashingLabelDto,
}

__all__ = ["CprsModel"] + list(_MODELS.keys())
