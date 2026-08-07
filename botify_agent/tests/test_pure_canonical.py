"""Stdlib-only, standalone tests for botify_canonical.py.

Deliberately does NOT import `odoo` — runnable with plain `python3 -m
unittest` in any environment, including one with no Odoo installation (see
docs/odoo/runbook.md "what actually ran"). Golden vectors are identical to
packages/api/src/services/odoo/policy/operationHash.test.ts's, computed
independently via `python3 -c "hashlib.sha256(...)"` — not derived from
either implementation's own output.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "models"))

import botify_canonical as bc  # noqa: E402


class TestCanonicalJson(unittest.TestCase):
    def test_empty_array(self):
        self.assertEqual(bc.canonical_json([]), "[]")
        self.assertEqual(
            bc.sha256hex("[]"),
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        )

    def test_object_key_sort(self):
        self.assertEqual(bc.canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_nested_object(self):
        self.assertEqual(
            bc.canonical_json({"vals": {"name": "Acme", "active": True}}),
            '{"vals":{"active":true,"name":"Acme"}}',
        )

    def test_string_escaping(self):
        self.assertEqual(bc.canonical_json("a\"b\\c"), '"a\\"b\\\\c"')
        self.assertEqual(bc.canonical_json("line\nbreak"), '"line\\u000abreak"')


class TestOperationHashGoldenVectors(unittest.TestCase):
    def test_vector_1_res_partner_write(self):
        oph = bc.operation_hash(
            "res.partner",
            "write",
            ids=[3, 1, 2],
            domain=[],
            kwargs={"vals": {"name": "Acme", "active": True}},
        )
        self.assertEqual(
            oph, "ebb09e9d6a452107250101c6c3bbf1a254bf97d9e18c29894e1cba3b27d291b0"
        )

    def test_vector_2_crm_lead_search_read(self):
        oph = bc.operation_hash(
            "crm.lead",
            "search_read",
            ids=[],
            domain=[["type", "=", "opportunity"]],
            kwargs={"limit": 20, "fields": ["name", "email_from"]},
        )
        self.assertEqual(
            oph, "c89163cbc1acaee38db43b8a70f501587af30273ffee3b9083a03b5f61acf76e"
        )

    def test_id_order_independent(self):
        a = bc.operation_hash("m", "read", ids=[5, 1, 3])
        b = bc.operation_hash("m", "read", ids=[1, 3, 5])
        self.assertEqual(a, b)

    def test_tamper_changes_hash(self):
        base = bc.operation_hash("sale.order", "write", ids=[1], kwargs={"vals": {"amount": 100}})
        tampered = bc.operation_hash(
            "sale.order", "write", ids=[1], kwargs={"vals": {"amount": 100000}}
        )
        self.assertNotEqual(base, tampered)


if __name__ == "__main__":
    unittest.main()
