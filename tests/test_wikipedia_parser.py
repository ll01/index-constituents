import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock

import pandas as pd


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "get-constituents.py"


def load_module():
    selectorlib = types.ModuleType("selectorlib")
    selectorlib.Extractor = mock.Mock()
    fake_useragent = types.ModuleType("fake_useragent")
    fake_useragent.UserAgent = mock.Mock(return_value=mock.Mock(random="test-agent"))

    spec = importlib.util.spec_from_file_location("get_constituents", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(
        sys.modules,
        {"selectorlib": selectorlib, "fake_useragent": fake_useragent},
    ):
        spec.loader.exec_module(module)
    return module


class WikipediaParserTest(unittest.TestCase):
    def test_wikipedia_table_with_ticker_and_security_columns_becomes_constituents(self):
        module = load_module()
        response = mock.Mock(text="<html></html>")
        response.raise_for_status = mock.Mock()
        table = pd.DataFrame(
            {
                "Ticker": ["ENEL", "UCG"],
                "Security": ["Enel", "UniCredit"],
                "Other": ["ignored", "ignored"],
            }
        )

        with (
            mock.patch.object(module.requests, "get", return_value=response) as get,
            mock.patch.object(module.pd, "read_html", return_value=[table]) as read_html,
        ):
            result = module.get_constituents_from_wikipedia(
                "https://en.wikipedia.org/wiki/FTSE_MIB"
            )

        get.assert_called_once()
        response.raise_for_status.assert_called_once()
        read_html.assert_called_once()
        self.assertEqual(["Symbol", "Name"], list(result.columns))
        self.assertEqual(
            [{"Symbol": "ENEL", "Name": "Enel"}, {"Symbol": "UCG", "Name": "UniCredit"}],
            result.to_dict(orient="records"),
        )

    def test_wikipedia_suffix_is_appended_to_symbols(self):
        module = load_module()
        response = mock.Mock(text="<html></html>")
        response.raise_for_status = mock.Mock()
        table = pd.DataFrame({"Symbol": ["AAA", "BBB"], "Company": ["A", "B"]})

        with (
            mock.patch.object(module.requests, "get", return_value=response),
            mock.patch.object(module.pd, "read_html", return_value=[table]),
        ):
            result = module.get_constituents_from_wikipedia(
                "https://example.test/wiki/Test", suffix=".MI"
            )

        self.assertEqual(["AAA.MI", "BBB.MI"], result["Symbol"].tolist())

    def test_wikipedia_suffix_is_not_duplicated(self):
        module = load_module()
        response = mock.Mock(text="<html></html>")
        response.raise_for_status = mock.Mock()
        table = pd.DataFrame({"Symbol": ["AAA.MI", "BBB"], "Company": ["A", "B"]})

        with (
            mock.patch.object(module.requests, "get", return_value=response),
            mock.patch.object(module.pd, "read_html", return_value=[table]),
        ):
            result = module.get_constituents_from_wikipedia(
                "https://example.test/wiki/Test", suffix=".MI"
            )

        self.assertEqual(["AAA.MI", "BBB.MI"], result["Symbol"].tolist())


if __name__ == "__main__":
    unittest.main()
