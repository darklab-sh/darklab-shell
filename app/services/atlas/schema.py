# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas entity type registry.

Atlas can store app-native entity kinds that are not backed by provider intel
lookups. Keep this separate from services.intel.schema.
"""

from __future__ import annotations

from services.intel.schema import INTEL_ENTITY_TYPES


ATLAS_ENTITY_TYPES = frozenset({*INTEL_ENTITY_TYPES, "port"})
