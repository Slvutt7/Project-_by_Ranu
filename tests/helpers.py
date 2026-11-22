"""Shared fixtures: the worked example from the Phase 2 design document."""
from __future__ import annotations

from splitmate.core.models import Assignment, Group, Item, Member, SplitMode, Status, Transaction

DINA, RAKA, SARI = "mem_a1b2c3d4", "mem_c3d4e5f6", "mem_e5f6a7b8"
STAMP = "2026-11-18T13:05:00"


def make_group() -> Group:
    return Group(
        "grp_7f3a9c21", "Lunch Squad", False, "2026-11-10T12:30:00",
        [
            Member(DINA, "Dina", True, "2026-11-10T12:30:00"),
            Member(RAKA, "Raka", True, "2026-11-10T12:31:00"),
            Member(SARI, "Sari", True, "2026-11-10T12:31:30"),
        ],
    )


def make_worked_example(assign_last_item: bool = True) -> Transaction:
    """Rp113.000 items + 5.650 service + 11.865 tax - 15 rounding = Rp130.500."""
    last_assignments = [Assignment(SARI)] if assign_last_item else []
    return Transaction(
        transaction_id="trx_5d2e8a10",
        group_id="grp_7f3a9c21",
        name="Warung Padang Sederhana",
        transaction_date="2026-11-18",
        paid_by=RAKA,
        items=[
            Item("itm_01", "Nasi Rendang", 28000, 1, SplitMode.EQUAL, [Assignment(DINA)]),
            Item("itm_02", "Ayam Pop", 25000, 1, SplitMode.EQUAL, [Assignment(RAKA)]),
            Item("itm_03", "Es Teh", 6000, 3, SplitMode.BY_QUANTITY,
                 [Assignment(DINA, 1), Assignment(RAKA, 1), Assignment(SARI, 1)]),
            Item("itm_04", "Sambal Ijo", 10000, 1, SplitMode.EQUAL,
                 [Assignment(DINA), Assignment(RAKA), Assignment(SARI)]),
            Item("itm_05", "Sate Padang", 32000, 1, SplitMode.EQUAL, last_assignments),
        ],
        service_charge=5650,
        tax=11865,
        rounding_adjustment=-15,
        grand_total=130500,
        created_at=STAMP,
        updated_at=STAMP,
    )
