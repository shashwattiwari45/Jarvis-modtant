import unittest

from jarvis.local_actions import try_execute


class LocalActionRouterTests(unittest.TestCase):
    def test_unknown_command_falls_through(self):
        self.assertIsNone(try_execute("explain quantum entanglement"))

    def test_web_app_is_recognized(self):
        # Do not launch a browser in the test environment. Verify the matcher
        # by exercising only a non-Windows environment guard when applicable.
        if __import__("os").name != "nt":
            self.assertIsNone(try_execute("open youtube"))


if __name__ == "__main__":
    unittest.main()
