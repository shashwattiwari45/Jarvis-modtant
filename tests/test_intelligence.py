import unittest

from jarvis.intelligence import _SearchParser, _clean_result_url


class IntelligenceTests(unittest.TestCase):
    def test_search_parser_extracts_result(self):
        html = '''
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">Example result</a>
        <div class="result__snippet">Current example snippet.</div>
        '''
        parser = _SearchParser()
        parser.feed(html)
        self.assertEqual(len(parser.results), 1)
        self.assertEqual(parser.results[0]["title"], "Example result")

    def test_search_url_unwrap(self):
        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews"
        self.assertEqual(_clean_result_url(wrapped), "https://example.com/news")


if __name__ == "__main__":
    unittest.main()
