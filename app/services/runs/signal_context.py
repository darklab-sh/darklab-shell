# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed app-owned context for structured run-output classification."""

from dataclasses import dataclass

from services.assessments.dalfox_xss_observations import ReviewedDalfoxXssContext
from services.assessments.nuclei_takeover_observations import ReviewedNucleiTakeoverTemplate
from services.nuclei.template_cache import NucleiTemplateCacheSnapshot


@dataclass(frozen=True)
class RunOutputSignalContext:
    nuclei_takeover_template: ReviewedNucleiTakeoverTemplate | None = None
    nuclei_template_snapshot: NucleiTemplateCacheSnapshot | None = None
    dalfox_xss_context: ReviewedDalfoxXssContext | None = None
    dalfox_oast_validation: bool = False

    def __post_init__(self) -> None:
        if (self.nuclei_takeover_template is not None
                and type(self.nuclei_takeover_template) is not ReviewedNucleiTakeoverTemplate):
            raise ValueError("invalid Nuclei takeover signal context")
        if self.nuclei_template_snapshot is not None and type(self.nuclei_template_snapshot) is not NucleiTemplateCacheSnapshot:
            raise ValueError("invalid Nuclei template snapshot context")
        if self.dalfox_xss_context is not None and type(self.dalfox_xss_context) is not ReviewedDalfoxXssContext:
            raise ValueError("invalid Dalfox XSS signal context")
        if type(self.dalfox_oast_validation) is not bool:
            raise ValueError("invalid Dalfox OAST signal context")
        if self.dalfox_oast_validation and self.dalfox_xss_context is not None:
            raise ValueError("conflicting Dalfox signal contexts")


def output_signal_classifier_kwargs(
    context: RunOutputSignalContext | None,
) -> dict[str, object]:
    context = validated_run_output_signal_context(context)
    if context is None:
        return {}
    values = {
        "nuclei_takeover_template": context.nuclei_takeover_template,
        "nuclei_template_snapshot": context.nuclei_template_snapshot, "dalfox_xss_context": context.dalfox_xss_context,
        "dalfox_oast_validation": context.dalfox_oast_validation,
    }
    return {
        key: value
        for key, value in values.items()
        if value is not None and value is not False
    }


def validated_run_output_signal_context(
    context: RunOutputSignalContext | None,
) -> RunOutputSignalContext | None:
    if context is not None and type(context) is not RunOutputSignalContext:
        raise ValueError("invalid run output signal context")
    return context


__all__ = ["RunOutputSignalContext", "output_signal_classifier_kwargs", "validated_run_output_signal_context"]
