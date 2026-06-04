import json
import os
import time
import unittest

CONFIG = {
    "mode": os.getenv("QIWI_MODE", "mock"),
    "base_url": os.getenv("QIWI_BASE_URL", "https://edge.qiwi.com"),
    "token": os.getenv("QIWI_TOKEN", "mock-token"),
    "wallet": os.getenv("QIWI_WALLET", "79139999999"),
    "recipient": os.getenv("QIWI_RECIPIENT_WALLET", "+79139999998"),
}

# Mock responses keep the tests runnable without a live token or working API.
FIXTURES = {
    "history": {
        "data": [
            {
                "txnId": 11233344692,
                "type": "OUT",
                "status": "SUCCESS",
                "sum": {"amount": 1, "currency": 643},
                "total": {"amount": 1, "currency": 643},
                "provider": {"id": 99, "shortName": "QIWI Wallet"},
            }
        ]
    },
    "balance": {
        "accounts": [
            {
                "alias": "qw_wallet_rub",
                "hasBalance": True,
                "balance": {"amount": 10.5, "currency": 643},
                "currency": 643,
            }
        ]
    },
    "created_payment": {
        "id": "1717350000000",
        "terms": "99",
        "fields": {"account": "+79139999998"},
        "sum": {"amount": 1, "currency": "643"},
        "transaction": {"id": "11982501857", "state": {"code": "Accepted"}},
    },
    "transaction": {
        "txnId": 11982501857,
        "type": "OUT",
        "status": "SUCCESS",
        "trmTxnId": "1717350000000",
        "sum": {"amount": 1, "currency": 643},
        "total": {"amount": 1, "currency": 643},
        "provider": {"id": 99, "shortName": "QIWI Wallet"},
    },
}

class QIWIWalletAPITest(unittest.TestCase):
    playwright = None
    api = None

    @classmethod
    def setUpClass(cls):
        if CONFIG["mode"] != "live":
            return

        cls.assert_live_token_present()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError(
                "Python Playwright is required for live mode. "
                "Run: python3 -m pip install -r requirements.txt"
            ) from error

        # Playwright request context is used as an API client, without opening a browser.
        cls.playwright = sync_playwright().start()
        cls.api = cls.playwright.request.new_context(
            base_url=CONFIG["base_url"],
            extra_http_headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CONFIG['token']}",
            },
        )

    @classmethod
    def tearDownClass(cls):
        if cls.api:
            cls.api.dispose()
        if cls.playwright:
            cls.playwright.stop()

    @staticmethod
    def assert_live_token_present():
        if CONFIG["token"] == "mock-token":
            raise AssertionError("QIWI_TOKEN is required for live mode")

    def get_json(self, method, path, body=None):
        if CONFIG["mode"] == "mock":
            return self.get_mock_json(path, body)

        # Keep live and mock responses in the same shape for the tests below.
        response = getattr(self.api, method)(path, data=body) if body else getattr(self.api, method)(path)
        text = response.text()
        parsed = json.loads(text) if text else {}
        return {"status": response.status, "body": parsed}

    @staticmethod
    def get_mock_json(path, body=None):
        # The mock branch mirrors the endpoints used by the positive and negative checks.
        if "/persons/bad-wallet/" in path:
            return {
                "status": 400,
                "body": {"code": "invalid.person", "message": "Invalid wallet identifier"},
            }

        if "/payments?rows=1" in path:
            return {"status": 200, "body": FIXTURES["history"]}

        if "/accounts" in path:
            return {"status": 200, "body": FIXTURES["balance"]}

        if "/terms/99/payments" in path:
            if not body or "sum" not in body or body["sum"]["amount"] <= 0:
                return {
                    "status": 400,
                    "body": {"code": "invalid.amount", "message": "Payment amount must be greater than 0"},
                }

            if body["id"] == "duplicate-payment-id":
                return {
                    "status": 409,
                    "body": {"code": "payment.exists", "message": "Payment with this id already exists"},
                }

            if not body.get("fields", {}).get("account"):
                return {
                    "status": 400,
                    "body": {"code": "missing.account", "message": "Recipient account is required"},
                }

            return {
                "status": 200,
                "body": {
                    **FIXTURES["created_payment"],
                    "id": body["id"],
                    "fields": {"account": body["fields"]["account"]},
                },
            }

        if "/transactions/" in path:
            return {"status": 200, "body": FIXTURES["transaction"]}

        raise AssertionError(f"Unhandled mock request path: {path}")

    def assert_money(self, value, currency):
        # Shared money assertion for balance and transaction amount checks.
        self.assertIsInstance(value, dict)
        self.assertIsInstance(value.get("amount"), (int, float))
        self.assertEqual(value.get("currency"), currency)
        self.assertGreaterEqual(value["amount"], 0)

    def build_payment(self, amount=1, fields=None, payment_id=None):
        payment_id = payment_id or str(int(time.time() * 1000))
        return {
            "id": payment_id,
            "sum": {"amount": amount, "currency": "643"},
            "paymentMethod": {"type": "Account", "accountId": "643"},
            "comment": f"QA test payment {payment_id}",
            "fields": fields if fields is not None else {"account": CONFIG["recipient"]},
        }

    def create_payment(self):
        result = self.get_json("post", "/sinap/api/v2/terms/99/payments", self.build_payment())
        self.assertEqual(result["status"], 200)
        return result["body"]

    def get_transaction(self, transaction_id):
        result = None

        for _ in range(3):
            result = self.get_json(
                "get",
                f"/payment-history/v2/transactions/{transaction_id}?type=OUT",
            )
            if result["status"] == 200 or CONFIG["mode"] == "mock":
                return result
            time.sleep(1)

        return result

    def test_service_availability_payment_history_responds_with_documented_shape(self):
        result = self.get_json(
            "get",
            f"/payment-history/v2/persons/{CONFIG['wallet']}/payments?rows=1",
        )

        self.assertEqual(result["status"], 200)
        body = result["body"]
        self.assertIn("data", body)
        self.assertIsInstance(body["data"], list)

        if body["data"]:
            payment = body["data"][0]
            self.assertIsInstance(payment.get("txnId"), int)
            self.assertIn(payment.get("type"), ["IN", "OUT", "QIWI_CARD"])
            self.assertIn(payment.get("status"), ["WAITING", "SUCCESS", "ERROR"])

    def test_balance_rub_wallet_account_exists_and_balance_is_greater_than_0(self):
        result = self.get_json(
            "get",
            f"/funding-sources/v2/persons/{CONFIG['wallet']}/accounts",
        )

        self.assertEqual(result["status"], 200)
        accounts = result["body"]["accounts"]
        self.assertIsInstance(accounts, list)

        rub_wallet = next((account for account in accounts if account["alias"] == "qw_wallet_rub"), None)
        self.assertIsNotNone(rub_wallet, "RUB wallet account should be present")
        self.assertTrue(rub_wallet["hasBalance"])
        self.assert_money(rub_wallet["balance"], 643)
        self.assertGreater(rub_wallet["balance"]["amount"], 0)

    def test_payment_creation_transfer_for_exactly_1_rub_is_accepted(self):
        body = self.create_payment()

        self.assertEqual(body["sum"]["amount"], 1)
        self.assertEqual(body["sum"]["currency"], "643")
        self.assertEqual(body["terms"], "99")
        self.assertIsInstance(body["transaction"]["id"], str)
        self.assertIn(body["transaction"]["state"]["code"], ["Accepted", "Completed"])

    def test_payment_execution_created_transaction_can_be_checked_in_payment_history(self):
        created_payment = self.create_payment()
        transaction_id = created_payment["transaction"]["id"]
        result = self.get_transaction(transaction_id)

        self.assertEqual(result["status"], 200)
        body = result["body"]
        self.assertIsInstance(body["txnId"], int)
        self.assertEqual(body["type"], "OUT")
        self.assertIn(body["status"], ["WAITING", "SUCCESS", "ERROR"])
        self.assertEqual(body["provider"]["id"], 99)
        self.assert_money(body["sum"], 643)
        self.assertEqual(body["sum"]["amount"], 1)

    def test_balance_request_rejects_malformed_wallet_identifier(self):
        if CONFIG["mode"] != "mock":
            self.skipTest("Negative contract tests are deterministic mock checks.")

        result = self.get_json("get", "/funding-sources/v2/persons/bad-wallet/accounts")

        self.assertEqual(result["status"], 400)
        body = result["body"]
        self.assertIsInstance(body.get("code"), str)
        self.assertIsInstance(body.get("message"), str)

    def test_payment_creation_rejects_0_amount(self):
        if CONFIG["mode"] != "mock":
            self.skipTest("Negative contract tests are deterministic mock checks.")

        result = self.get_json(
            "post",
            "/sinap/api/v2/terms/99/payments",
            self.build_payment(amount=0),
        )

        self.assertEqual(result["status"], 400)
        self.assertEqual(result["body"]["code"], "invalid.amount")

    def test_payment_creation_rejects_missing_recipient_account(self):
        if CONFIG["mode"] != "mock":
            self.skipTest("Negative contract tests are deterministic mock checks.")

        result = self.get_json(
            "post",
            "/sinap/api/v2/terms/99/payments",
            self.build_payment(fields={}),
        )

        self.assertEqual(result["status"], 400)
        self.assertEqual(result["body"]["code"], "missing.account")

    def test_payment_creation_handles_duplicate_payment_id_as_conflict(self):
        if CONFIG["mode"] != "mock":
            self.skipTest("Negative contract tests are deterministic mock checks.")

        result = self.get_json(
            "post",
            "/sinap/api/v2/terms/99/payments",
            self.build_payment(payment_id="duplicate-payment-id"),
        )

        self.assertEqual(result["status"], 409)
        self.assertEqual(result["body"]["code"], "payment.exists")

if __name__ == "__main__":
    unittest.main(verbosity=2)
