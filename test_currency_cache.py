import unittest
from unittest.mock import Mock, patch

import requests

import main


def response(status, body):
    result = requests.Response()
    result.status_code = status
    result.json = Mock(return_value=body)
    return result


class CurrencyRefreshTests(unittest.TestCase):
    def setUp(self):
        for setting in (patch.dict(main.CURRENCY_CACHE, clear=True),
                        patch.object(main, "CURRENCY_ISSUES", {}),
                        patch.object(main._time, "sleep")):
            setting.start()
            self.addCleanup(setting.stop)

    def test_unconfigured_upbit_skips_signing_and_logs_once(self):
        with patch.dict(main.CURRENCY_FETCHERS, {"upbit": main.fetch_upbit_currencies}, clear=True), \
                patch.object(main, "UPBIT_SECRET", None), patch.object(main.jwt, "encode") as sign, \
                patch.object(main._SESSION, "get") as get, patch("builtins.print") as log:
            main.refresh_currency_cache()
            main.refresh_currency_cache()
        sign.assert_not_called()
        get.assert_not_called()
        self.assertEqual(log.call_count, 1)
        self.assertIn("API 키", log.call_args.args[0])

    def test_public_timeout_then_success_updates_cache_without_warning(self):
        body = {"success": True, "data": [{"name": "btc", "depositStatus": "launched",
                                          "withdrawalStatus": "launched", "withdrawalTxFee": "0.01"}]}
        with patch.dict(main.CURRENCY_FETCHERS, {"korbit": main.fetch_korbit_currencies}, clear=True), \
                patch.object(main._SESSION, "get", side_effect=[requests.ReadTimeout(), response(200, body)]) as get, \
                patch("builtins.print") as log:
            main.refresh_currency_cache()
        self.assertEqual(get.call_count, 2)
        self.assertEqual(main.get_currency_info("korbit", "BTC"), {"dep": True, "wd": True, "fee": 0.01})
        log.assert_not_called()

    def test_repeated_http_error_keeps_cache_then_reports_recovery(self):
        old = {"BTC": {"dep": False}}
        main.CURRENCY_CACHE["coinone"] = old
        ok = {"result": "success", "currencies": [{"symbol": "btc", "deposit_status": "normal"}]}
        with patch.dict(main.CURRENCY_FETCHERS, {"coinone": main.fetch_coinone_currencies}, clear=True), \
                patch.object(main._SESSION, "get", side_effect=[response(403, {}), response(403, {}), response(200, ok)]), \
                patch("builtins.print") as log:
            main.refresh_currency_cache()
            main.refresh_currency_cache()
            self.assertIs(main.CURRENCY_CACHE["coinone"], old)
            self.assertEqual(log.call_count, 1)
            self.assertIn("HTTP 403", log.call_args.args[0])
            main.refresh_currency_cache()
        self.assertIn("복구", log.call_args.args[0])
        self.assertTrue(main.get_currency_info("coinone", "BTC")["dep"])

    def test_retry_stops_after_second_timeout(self):
        with patch.dict(main.CURRENCY_FETCHERS, {"korbit": main.fetch_korbit_currencies}, clear=True), \
                patch.object(main._SESSION, "get", side_effect=requests.ReadTimeout) as get, \
                patch("builtins.print") as log:
            main.refresh_currency_cache()
        self.assertEqual(get.call_count, 2)
        self.assertIn("ReadTimeout", log.call_args.args[0])
        self.assertNotIn("korbit", main.CURRENCY_CACHE)
