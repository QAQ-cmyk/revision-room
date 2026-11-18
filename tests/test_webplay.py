import unittest
from unittest.mock import Mock
from webplay import game_url, perform, validate


class WebRouteTests(unittest.TestCase):
    def test_loopback_url_requires_an_explicit_port(self):
        for url in ["https://example.org:80", "http://localhost/", "http://name@localhost:80",
                    "file:///C:/index.html", "http://127.0.0.1:0"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                game_url(url)
        self.assertEqual(game_url("http://[::1]:8000/game"), "http://[::1]:8000/game")

    def test_rejects_invalid_action_and_oversized_wait(self):
        for step in [{"action":"other","label":"x"}, {"action":"hold","label":"x","key":"d","ms":5001}]:
            with self.subTest(step=step), self.assertRaises(ValueError):
                validate({"url":"http://localhost:8000", "route":{"name":"Opening","viewport":[1280,720],"steps":[step]}})

    def test_an_element_below_the_fold_fails_visibility_check(self):
        page = Mock()
        page.viewport_size = {"width":1280, "height":720}
        node = page.locator.return_value
        node.bounding_box.return_value = {"x":0,"y":700,"width":600,"height":45}
        with self.assertRaisesRegex(ValueError, "720"):
            perform(page, {"action":"visible","selector":"footer"})
        node.bounding_box.return_value["y"] = 675
        self.assertIn("1280", perform(page, {"action":"visible","selector":"footer"}))
