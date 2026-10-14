"""Offline check that answer() sends the retrieved passages to Claude and returns its text."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from initializer import answer


class AnswerTest(unittest.TestCase):
    def test_answer_uses_retrieved_passages_and_returns_text(self):
        indexer = MagicMock()
        indexer.search_two_stage.return_value = [
            {"paper_id": "2609.35732v1", "page_number": 3, "text": "Caching cuts agent cost by 40%.", "score": 0.8}
        ]
        client = MagicMock()
        client.messages.create.return_value = SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Use caching [2609.35732v1 p.3].")]
        )

        text, passages = answer(indexer, "How do we cut agent cost?", client=client)

        self.assertEqual(text, "Use caching [2609.35732v1 p.3].")
        self.assertEqual(passages, indexer.search_two_stage.return_value)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("[2609.35732v1 p.3]\nCaching cuts agent cost by 40%.", prompt)
        self.assertIn("How do we cut agent cost?", prompt)


if __name__ == "__main__":
    unittest.main()
