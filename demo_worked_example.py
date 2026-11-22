"""Prints the Phase 2 worked example through the real code. Run: python demo_worked_example.py"""
from splitmate.core.calculator import distribute
from splitmate.core.lifecycle import complete_transaction, derive_status
from splitmate.core.money import format_amount, format_rupiah
from tests.helpers import make_group, make_worked_example

group, tx = make_group(), make_worked_example()
print(f"Status before confirming: {derive_status(tx)}")
print(f"Sambal Ijo, Rp10.000 shared by 3: {distribute(10000, [1, 1, 1])}\n")

complete_transaction(tx, group, "2026-11-18T13:20:00")
names = {m.member_id: m.name for m in tx.members_snapshot}
print(f"{'Member':<8}{'Items':>9}{'Service':>9}{'Tax':>8}{'Rounding':>10}{'Total':>10}")
for p in tx.payments:
    print(f"{names[p.member_id]:<8}{format_amount(p.subtotal):>9}{format_amount(p.service_share):>9}"
          f"{format_amount(p.tax_share):>8}{format_amount(p.rounding_share):>10}{format_amount(p.total):>10}")
print(f"{'Total':<8}{format_amount(tx.subtotal):>9}{format_amount(tx.service_charge):>9}"
      f"{format_amount(tx.tax):>8}{format_amount(tx.rounding_adjustment):>10}{format_amount(sum(p.total for p in tx.payments)):>10}")
print(f"\nReceipt total {format_rupiah(tx.grand_total)}; status {tx.status}")
