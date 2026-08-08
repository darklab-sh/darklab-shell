# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed app-owned context for structured run-output classification."""

from dataclasses import dataclass

from services.assessments.nuclei_takeover_observations import ReviewedNucleiTakeoverTemplate


@dataclass(frozen=True)
class RunOutputSignalContext:
    nuclei_takeover_template: ReviewedNucleiTakeoverTemplate | None = None

    def __post_init__(self) -> None:
        template = self.nuclei_takeover_template
        if template is not None and type(template) is not ReviewedNucleiTakeoverTemplate:
            raise ValueError("invalid Nuclei takeover signal context")


def output_signal_classifier_kwargs(
    context: RunOutputSignalContext | None,
) -> dict[str, object]:
    context = validated_run_output_signal_context(context)
    if context is None:
        return {}
    if context.nuclei_takeover_template is None:
        return {}
    return {"nuclei_takeover_template": context.nuclei_takeover_template}


def validated_run_output_signal_context(
    context: RunOutputSignalContext | None,
) -> RunOutputSignalContext | None:
    if context is not None and type(context) is not RunOutputSignalContext:
        raise ValueError("invalid run output signal context")
    return context


__all__ = [
    "RunOutputSignalContext",
    "output_signal_classifier_kwargs",
    "validated_run_output_signal_context",
]
