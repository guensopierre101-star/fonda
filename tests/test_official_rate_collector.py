import importlib.util
import unittest

spec = importlib.util.spec_from_file_location("collector", "scripts/fetch_all_official_rates.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)

class OfficialRateCollectorTests(unittest.TestCase):
    def test_csv_observation_is_parsed(self):
        original = collector.urllib.request.urlopen
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return b"observation_date,DFEDTARU\n2026-10-08,4.25\n"
        collector.urllib.request.urlopen = lambda *args, **kwargs: FakeResponse()
        try:
            result = collector.collect({
                "currency":"USD","bank":"Federal Reserve","indicator":"Test rate",
                "kind":"csv","url":"https://example.invalid/test.csv",
                "source":"https://www.federalreserve.gov/","date":"observation_date","value":"DFEDTARU"
            })
            self.assertEqual(result["value_percent"], 4.25)
            self.assertEqual(result["observation_date"], "2026-10-08")
            self.assertEqual(result["status"], "verified")
        finally:
            collector.urllib.request.urlopen = original

    def test_missing_values_are_not_fabricated(self):
        original = collector.urllib.request.urlopen
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"observation_date,DFEDTARU\n2026-10-08,.\n"
        collector.urllib.request.urlopen = lambda *args, **kwargs: FakeResponse()
        try:
            with self.assertRaises(ValueError):
                collector.collect({
                    "currency":"USD","bank":"Federal Reserve","indicator":"Test rate",
                    "kind":"csv","url":"https://example.invalid/test.csv",
                    "source":"https://www.federalreserve.gov/","date":"observation_date","value":"DFEDTARU"
                })
        finally:
            collector.urllib.request.urlopen = original

    def test_unvalidated_sources_are_marked_unavailable(self):
        source = next(s for s in collector.SOURCES if s["currency"] == "JPY")
        with self.assertRaises(RuntimeError):
            collector.collect(source)

if __name__ == "__main__":
    unittest.main()
