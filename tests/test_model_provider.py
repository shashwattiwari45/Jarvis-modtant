import unittest

from cloud.model_provider import parse_provider_json


class ProviderParsingTests(unittest.TestCase):
    def test_parses_json_object(self):
        self.assertEqual(parse_provider_json('{"mode":"chat","reply":"hi"}')['reply'], 'hi')

    def test_wraps_plain_text(self):
        parsed = parse_provider_json("hello")
        self.assertEqual(parsed["mode"], "chat")
        self.assertEqual(parsed["reply"], "hello")

    def test_handles_non_object_json(self):
        self.assertEqual(parse_provider_json("[1, 2]")["reply"], "[1, 2]")


if __name__ == "__main__":
    unittest.main()