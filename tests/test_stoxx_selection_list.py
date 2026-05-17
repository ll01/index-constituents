import importlib.util
import pathlib
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "get-constituents.py"


def load_module():
    spec = importlib.util.spec_from_file_location("get_constituents", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StoxxSelectionListTest(unittest.TestCase):
    def test_finds_latest_stoxx_selection_list_url_from_data_page(self):
        module = load_module()
        response = mock.Mock(
            text="""
            <a href='https://www.stoxx.com/documents/stoxxnet/Documents/Reports/STOXXSelectionList/2026/May/slpublic_sxxp_20260501.csv'>csv</a>
            """
        )
        response.raise_for_status = mock.Mock()

        with mock.patch.object(module.requests, "get", return_value=response):
            url = module.get_stoxx_selection_list_url("sxxp")

        self.assertEqual(
            "https://www.stoxx.com/documents/stoxxnet/Documents/Reports/STOXXSelectionList/2026/May/slpublic_sxxp_20260501.csv",
            url,
        )

    def test_selection_list_filters_current_members_and_returns_symbols_and_names(self):
        module = load_module()
        response = mock.Mock(
            text=(
                "Creation_Date;Index_Symbol;Index_Name;RIC;Instrument_Name;Index Membership\r\n"
                "20260501;SXXP;STOXX Europe 600;ASML.AS;ASML HLDG;Large\r\n"
                "20260501;SXXP;STOXX Europe 600;ROPC.S;ROCHE PS;Mid\r\n"
                "20260501;SXXP;STOXX Europe 600;RYA.I;RYANAIR;Small\r\n"
                "20260501;SXXP;STOXX Europe 600;FOO.L;Not a member;\r\n"
            )
        )
        response.raise_for_status = mock.Mock()

        with mock.patch.object(module.requests, "get", return_value=response):
            result = module.get_constituents_from_stoxx_selection_list("https://example.test/list.csv")

        self.assertEqual(["Symbol", "Name"], list(result.columns))
        self.assertEqual(
            [
                {"Symbol": "ASML.AS", "Name": "ASML HLDG"},
                {"Symbol": "ROPC.SW", "Name": "ROCHE PS"},
                {"Symbol": "RYA.IR", "Name": "RYANAIR"},
            ],
            result.to_dict(orient="records"),
        )


if __name__ == "__main__":
    unittest.main()
