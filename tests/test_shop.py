from __future__ import annotations

import unittest

from boba.core import ToolError
from boba.shop import Shop


class ShopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.shop = Shop.load()

    def test_menu_has_four_drinks(self) -> None:
        self.assertEqual(len(self.shop.items), 4)
        self.assertIn("boba_milk_tea", self.shop.items)
        self.assertEqual(self.shop.items["boba_milk_tea"].base_price_cents, 1200)

    def test_quote_defaults(self) -> None:
        quote = self.shop.quote({"item_id": "boba_milk_tea"})
        self.assertEqual(quote["unit_price"], 12)
        self.assertEqual(quote["total"], 12)
        self.assertEqual(
            quote["options"],
            {"size": "中杯", "ice": "正常冰", "sugar": "全糖", "toppings": []},
        )

    def test_quote_large_with_pearl(self) -> None:
        quote = self.shop.quote(
            {"item_id": "boba_milk_tea", "qty": 2, "size": "large", "toppings": ["pearl"]}
        )
        # 12 基础 + 3 大杯 + 2 珍珠 = 17
        self.assertEqual(quote["unit_price"], 17)
        self.assertEqual(quote["total"], 34)
        self.assertEqual(quote["options"]["toppings"], ["珍珠"])

    def test_add_and_submit_order(self) -> None:
        created = self.shop.create_order("sess_1", "阿珍")
        self.assertEqual(created["order_id"], "B1001")
        self.assertFalse(created["existing"])

        self.shop.add_item(
            "sess_1",
            {"item_id": "boba_milk_tea", "qty": 1, "ice": "less", "sugar": "half"},
        )
        added = self.shop.add_item(
            "sess_1",
            {"item_id": "boba_milk_tea", "qty": 1, "ice": "normal", "sugar": "full"},
        )
        self.assertEqual(added["cups"], 2)
        self.assertEqual(added["total"], 24)

        receipt = self.shop.submit("sess_1")
        self.assertEqual(receipt["status"], "submitted")
        self.assertEqual(receipt["total"], 24)
        self.assertEqual(receipt["eta_minutes"], 6)
        self.assertEqual(len(receipt["lines"]), 2)

        self.assertAlmostEqual(self.shop.inventory["black_tea_ml"], 3600)
        self.assertAlmostEqual(self.shop.inventory["milk_ml"], 2300)
        self.assertAlmostEqual(self.shop.inventory["tapioca_g"], 700)
        self.assertAlmostEqual(self.shop.inventory["sugar_g"], 480)

    def test_create_order_is_idempotent_for_session(self) -> None:
        first = self.shop.create_order("sess_1", "阿珍")
        second = self.shop.create_order("sess_1", "阿珍")
        self.assertEqual(first["order_id"], second["order_id"])
        self.assertTrue(second["existing"])
        self.assertEqual(len(self.shop._orders), 1)

    def test_order_ids_increment(self) -> None:
        self.assertEqual(self.shop.create_order("a")["order_id"], "B1001")
        self.assertEqual(self.shop.create_order("b")["order_id"], "B1002")

    def test_add_after_submit_opens_a_new_draft(self) -> None:
        first = self.shop.add_item("sess_1", {"item_id": "four_seasons", "qty": 1})
        self.shop.submit("sess_1")

        second = self.shop.add_item("sess_1", {"item_id": "four_seasons", "qty": 1})
        self.assertNotEqual(first["order_id"], second["order_id"])
        self.assertEqual(second["status"], "draft")
        self.assertEqual(second["cups"], 1)

    def test_submit_rolls_nothing_back_when_stock_is_short(self) -> None:
        self.shop.add_item("sess_1", {"item_id": "boba_milk_tea", "qty": 2})
        before = dict(self.shop.inventory)
        self.shop.inventory["milk_ml"] = 10

        with self.assertRaisesRegex(ToolError, "原料不够"):
            self.shop.submit("sess_1")

        order = self.shop.resolve_order("sess_1")
        self.assertEqual(order.status, "draft")
        self.assertEqual(self.shop.inventory["milk_ml"], 10)
        self.assertEqual(self.shop.inventory["black_tea_ml"], before["black_tea_ml"])

    def test_invalid_options_are_rejected(self) -> None:
        with self.assertRaisesRegex(ToolError, "冰度"):
            self.shop.add_item(
                "sess_1",
                {"item_id": "boba_milk_tea", "qty": 1, "ice": "extra_cold"},
            )

    def test_unknown_item_is_rejected(self) -> None:
        with self.assertRaisesRegex(ToolError, "菜单上没有"):
            self.shop.quote({"item_id": "unicorn_tea"})

    def test_qty_must_be_positive_integer(self) -> None:
        for bad in (0, -1, 100, "2", True):
            with self.subTest(qty=bad):
                with self.assertRaises(ToolError):
                    self.shop.quote({"item_id": "boba_milk_tea", "qty": bad})

    def test_toppings_consume_inventory(self) -> None:
        self.shop.add_item(
            "sess_1",
            {"item_id": "boba_milk_tea", "qty": 1, "toppings": ["pearl"]},
        )
        self.shop.submit("sess_1")
        # 50g 基底珍珠 + 30g 加料珍珠
        self.assertAlmostEqual(self.shop.inventory["tapioca_g"], 720)

    def test_large_size_scales_ingredients(self) -> None:
        self.shop.add_item(
            "sess_1", {"item_id": "boba_milk_tea", "qty": 1, "size": "large"}
        )
        self.shop.submit("sess_1")
        self.assertAlmostEqual(self.shop.inventory["black_tea_ml"], 4000 - 260)

    def test_cannot_touch_another_sessions_order(self) -> None:
        order_id = self.shop.create_order("owner", "阿珍")["order_id"]
        payload = {"item_id": "four_seasons", "qty": 1, "order_id": order_id}

        with self.assertRaisesRegex(ToolError, "不属于当前会话"):
            self.shop.add_item("intruder", payload)
        with self.assertRaisesRegex(ToolError, "不属于当前会话"):
            self.shop.submit("intruder", order_id)
        with self.assertRaisesRegex(ToolError, "不属于当前会话"):
            self.shop.status("intruder", order_id)

    def test_inventory_check_does_not_consume(self) -> None:
        result = self.shop.check_inventory({"item_id": "cheese_berry", "qty": 99})
        self.assertFalse(result["available"])
        self.assertTrue(result["shortages"])
        self.assertAlmostEqual(self.shop.inventory["cheese_foam_g"], 500)

    def test_order_status_for_session(self) -> None:
        with self.assertRaisesRegex(ToolError, "还没有订单"):
            self.shop.status("sess_missing")
        self.shop.add_item("sess_1", {"item_id": "lemon_tea", "qty": 2})
        status = self.shop.status("sess_1")
        self.assertEqual(status["status"], "draft")
        self.assertEqual(status["cups"], 2)
        self.assertEqual(status["total"], 22)


if __name__ == "__main__":
    unittest.main()
