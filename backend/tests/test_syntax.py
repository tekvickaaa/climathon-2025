import ast
import pathlib
import unittest


class SyntaxTest(unittest.TestCase):
    def test_main_syntax(self):
        # Ensure `main.py` parses as valid Python (does not import dependencies)
        p = pathlib.Path(__file__).resolve().parents[1] / "main.py"
        src = p.read_text(encoding='utf-8')
        ast.parse(src)


if __name__ == "__main__":
    unittest.main()
