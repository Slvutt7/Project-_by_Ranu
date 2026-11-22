import unittest
from datetime import date

from splitmate.core.dates import format_date, parse_date, parse_iso_date
from splitmate.core.errors import DateParseError, MoneyParseError
from splitmate.core.money import format_amount, format_rupiah, parse_rupiah


class ParseRupiahTests(unittest.TestCase):
    def test_accepted_formats(self):
        cases = {
            "28000": 28000, "28.000": 28000, "28,000": 28000, "Rp 28.000": 28000, "Rp28.000": 28000,
            "rp. 1.250.000": 1250000, "IDR 5.000": 5000, "28.000,00": 28000, "28,000.00": 28000,
            "28000,00": 28000, "  0 ": 0, "1 000": 1000, "10,00": 10,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_rupiah(text), expected)

    def test_cents_rejected(self):
        for text in ("28.50", "28,5", "1.234,56", "10.000,50"):
            with self.subTest(text=text), self.assertRaises(MoneyParseError) as ctx:
                parse_rupiah(text)
            self.assertIn("whole Rupiah", str(ctx.exception))

    def test_garbage_and_empty_rejected(self):
        for text in ("", "   ", "Rp", "abc", "12a", "1..000", "1.00.000", "--5", None):
            with self.subTest(text=text), self.assertRaises(MoneyParseError):
                parse_rupiah(text)

    def test_negative_only_when_allowed(self):
        with self.assertRaises(MoneyParseError):
            parse_rupiah("-15")
        self.assertEqual(parse_rupiah("-15", allow_negative=True), -15)
        self.assertEqual(parse_rupiah("-Rp 15", allow_negative=True), -15)
        self.assertEqual(parse_rupiah("\u221215", allow_negative=True), -15)
        self.assertEqual(parse_rupiah("-0"), 0)

    def test_too_large(self):
        with self.assertRaises(MoneyParseError):
            parse_rupiah("9" * 14)


class FormatRupiahTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(format_amount(130500), "130.500")
        self.assertEqual(format_amount(0), "0")
        self.assertEqual(format_amount(-15), "-15")
        self.assertEqual(format_amount(1234567), "1.234.567")
        self.assertEqual(format_rupiah(130500), "Rp130.500")
        self.assertEqual(format_rupiah(-15), "-Rp15")

    def test_rejects_non_int(self):
        for bad in (1.5, "100", True):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                format_amount(bad)

    def test_round_trip(self):
        for amount in (0, 7, 999, 1000, 28000, 130500, 987654321):
            self.assertEqual(parse_rupiah(format_amount(amount)), amount)
            self.assertEqual(parse_rupiah(format_rupiah(amount)), amount)


class DateTests(unittest.TestCase):
    def test_formats_accepted(self):
        expected = date(2026, 11, 18)
        for text in ("18 Nov 2026", "18/11/2026", "18-11-2026", "2026-11-18", "18 november 2026", "  18 NOV 2026 "):
            with self.subTest(text=text):
                self.assertEqual(parse_date(text), expected)

    def test_indonesian_month_names(self):
        self.assertEqual(parse_date("17 Agu 2026"), date(2026, 8, 17))
        self.assertEqual(parse_date("1 Mei 2026"), date(2026, 5, 1))
        self.assertEqual(parse_date("5 Okt 2026"), date(2026, 10, 5))
        self.assertEqual(parse_date("25 Desember 2026"), date(2026, 12, 25))

    def test_invalid(self):
        for text in ("", "31/02/2026", "32 Nov 2026", "18 Foo 2026", "2026/11/18", "18 Nov 26", "18/11/1800", "tomorrow"):
            with self.subTest(text=text), self.assertRaises(DateParseError):
                parse_date(text)

    def test_leap_day(self):
        self.assertEqual(parse_date("29 Feb 2028"), date(2028, 2, 29))
        with self.assertRaises(DateParseError):
            parse_date("29 Feb 2027")

    def test_display_format(self):
        self.assertEqual(format_date("2026-11-18"), "18 Nov 2026")
        self.assertEqual(format_date(date(2026, 5, 3)), "03 May 2026")

    def test_iso_is_strict(self):
        with self.assertRaises(DateParseError):
            parse_iso_date("18/11/2026")
        self.assertEqual(parse_iso_date("2026-11-18"), date(2026, 11, 18))


if __name__ == "__main__":
    unittest.main()
