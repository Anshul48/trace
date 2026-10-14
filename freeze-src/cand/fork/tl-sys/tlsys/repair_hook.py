"""Real repair-hook composition: adapt a repair-enabled TLStore to RepairHook.

The store's repair_step returns {enabled, spent, checked, debt, ...} in
384-coordinate vector-row budget units; the service report shape uses
{processed, remaining, hook, ...}. This adapter maps the shapes without
changing either seam's semantics. Hook failures propagate (publication
validates the resulting hierarchy before making it visible), per the
RepairHook contract: a flaky repair blocks publication loudly, never
silently.
"""
from __future__ import annotations

from typing import Mapping


class TLStoreRepairHook:
    """RepairHook over a TLStore opened with local_repair=True.

    budget is forwarded in repair vector-row units. Returns a service-shape
    report dict; the raw repair receipt is nested under "repair" for audit.
    """

    def __init__(self, tlstore):
        self.tlstore = tlstore

    def repair_step(self, budget: int) -> Mapping:
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
            raise ValueError("budget must be a nonnegative integer")
        receipt = self.tlstore.repair_step(budget)
        receipt = dict(receipt)
        if not receipt.get("enabled", False):
            return {"processed": 0, "remaining": 0, "hook": "tlstore-repair-disabled",
                    "repair": receipt}
        return {"processed": int(receipt.get("checked", 0)),
                "remaining": int(receipt.get("debt", 0)),
                "spent": int(receipt.get("spent", 0)),
                "hook": "tlstore-repair",
                "repair": receipt}
