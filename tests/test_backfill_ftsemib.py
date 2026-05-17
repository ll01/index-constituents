import importlib.util
import json
import pathlib
import tempfile
import unittest
from datetime import date
from unittest import mock

import pandas as pd


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "backfill-ftsemib.py"


def load_module():
    spec = importlib.util.spec_from_file_location("backfill_ftsemib", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FtseMibBackfillTest(unittest.TestCase):
    def test_iter_month_starts_includes_start_and_end_months(self):
        module = load_module()

        months = list(
            module.iter_month_starts(
                date(2024, 3, 1),
                date(2024, 5, 17),
            )
        )

        self.assertEqual(
            [date(2024, 3, 1), date(2024, 4, 1), date(2024, 5, 1)],
            months,
        )

    def test_get_wikipedia_oldid_url_returns_revision_url_for_month(self):
        module = load_module()
        response = mock.Mock()
        response.raise_for_status = mock.Mock()
        response.json.return_value = {
            "query": {
                "pages": {
                    "123": {
                        "revisions": [
                            {"revid": 987654321},
                        ]
                    }
                }
            }
        }

        with mock.patch.object(module.requests, "get", return_value=response) as get:
            url = module.get_wikipedia_oldid_url(date(2024, 3, 1))

        get.assert_called_once()
        self.assertIn("headers", get.call_args.kwargs)
        self.assertIn("User-Agent", get.call_args.kwargs["headers"])
        response.raise_for_status.assert_called_once()
        self.assertEqual(
            "https://en.wikipedia.org/w/index.php?title=FTSE_MIB&oldid=987654321",
            url,
        )

    def test_backfill_month_skips_existing_outputs_by_default(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp)
            month_dir = output / "2024" / "03"
            month_dir.mkdir(parents=True)
            csv_path = month_dir / "constituents-ftsemib.csv"
            json_path = month_dir / "constituents-ftsemib.json"
            csv_path.write_text("Symbol,Name\nOLD.MI,Old\n", encoding="utf-8")
            json_path.write_text(json.dumps([{"Symbol": "OLD.MI", "Name": "Old"}]), encoding="utf-8")

            with mock.patch.object(module, "get_wikipedia_oldid_url") as oldid:
                result = module.backfill_month(date(2024, 3, 1), output)

            oldid.assert_not_called()
            self.assertEqual("skipped", result)
            self.assertEqual("Symbol,Name\nOLD.MI,Old\n", csv_path.read_text(encoding="utf-8"))

    def test_backfill_month_writes_csv_and_json_for_missing_month(self):
        module = load_module()
        df = pd.DataFrame({"Symbol": ["A2A.MI"], "Name": ["A2A"]})

        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp)
            with (
                mock.patch.object(module, "get_wikipedia_oldid_url", return_value="https://example.test/old"),
                mock.patch.object(module.gc, "get_constituents_from_wikipedia", return_value=df) as parser,
            ):
                result = module.backfill_month(date(2024, 3, 1), output)

            parser.assert_called_once_with(
                "https://example.test/old",
                suffix=".MI",
                headers=module.HEADERS,
            )
            self.assertEqual("saved", result)
            csv_path = output / "2024" / "03" / "constituents-ftsemib.csv"
            json_path = output / "2024" / "03" / "constituents-ftsemib.json"
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())
            self.assertEqual(
                [{"Symbol": "A2A.MI", "Name": "A2A"}],
                json.loads(json_path.read_text(encoding="utf-8")),
            )


if __name__ == "__main__":
    unittest.main()
