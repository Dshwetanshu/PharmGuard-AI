"""Report verification: evidence adapter, report parser and semantic checker.

Standard library only. See checker.validate_report.
"""
from src.verification.checker import FABRICATION_CODES, Finding, ValidationResult, validate_report
from src.verification.evidence import Evidence, NormalizedRecord, build_evidence, citation_key

__all__ = ["Evidence", "NormalizedRecord", "build_evidence", "citation_key",
           "validate_report", "ValidationResult", "Finding", "FABRICATION_CODES"]
