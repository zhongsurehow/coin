import unittest
from unittest.mock import patch
import game

class TestGameLogic(unittest.TestCase):

    def setUp(self):
        """Reset the village state before each test."""
        game.village_state = {
            "food": 50,
            "morale": 50,
            "health": 50,
        }
        # Load the actual game data for realistic testing
        self.hexagram_data = game.load_hexagram_data()

    def test_consequence_with_matching_changing_line(self):
        """
        Tests if a choice matching a changing line's theme receives a bonus.
        """
        # --- Test Data Setup ---
        # Hexagram 1 (The Creative), Line 2: "action"
        primary_hexagram = self.hexagram_data[0]
        # Divination result with a changing line at the second position (9)
        lines = [7, 9, 7, 7, 7, 7]
        # A choice whose disposition is "action"
        choice = {
            "disposition": "action",
            "effects": {"food": 10, "morale": -5, "health": 0}
        }

        # --- Execute the function ---
        # We use patch to suppress the print output during the test
        with patch('builtins.print') as mocked_print:
            game.apply_consequences(choice, primary_hexagram, lines)

        # --- Assertions ---
        # The base effect for food is +10. The bonus is +15. Expected food = 50 + 10 + 15 = 75
        self.assertEqual(game.village_state["food"], 75)
        # The base effect for morale is -5. The bonus mitigates it by +15. Expected morale = 50 - 5 + 15 = 60
        self.assertEqual(game.village_state["morale"], 60)
        # Health should be unchanged
        self.assertEqual(game.village_state["health"], 50)

        # Check if the correct feedback message was generated
        mocked_print.assert_any_call("Your action resonates with the wisdom of the changing line #2 (Nine in the second place means: Dragon appearing in the field. It furthers one to see the great man.).\nThe path is clear, and the outcome is greatly enhanced!")

    def test_consequence_with_mismatching_changing_line(self):
        """
        Tests if a choice that does NOT match a changing line's theme receives no bonus.
        """
        # Hexagram 1 (The Creative), Line 2: "action"
        primary_hexagram = self.hexagram_data[0]
        lines = [7, 9, 7, 7, 7, 7] # Changing line at position 2
        # A choice with "patience", which does not match "action"
        choice = {
            "disposition": "patience",
            "effects": {"food": 10, "morale": -5, "health": 0}
        }

        with patch('builtins.print'):
            game.apply_consequences(choice, primary_hexagram, lines)

        # --- Assertions ---
        # No bonus should be applied. Expected food = 50 + 10 = 60
        self.assertEqual(game.village_state["food"], 60)
        # No bonus. Expected morale = 50 - 5 = 45
        self.assertEqual(game.village_state["morale"], 45)
        self.assertEqual(game.village_state["health"], 50)

    def test_consequence_with_no_changing_lines(self):
        """
        Tests if a choice with no changing lines results in base effects only.
        """
        primary_hexagram = self.hexagram_data[0]
        lines = [7, 7, 7, 7, 7, 7] # No changing lines
        choice = {
            "disposition": "action",
            "effects": {"food": 10, "morale": -5, "health": 0}
        }

        with patch('builtins.print'):
            game.apply_consequences(choice, primary_hexagram, lines)

        # --- Assertions ---
        # No bonus. Expected food = 50 + 10 = 60
        self.assertEqual(game.village_state["food"], 60)
        # No bonus. Expected morale = 50 - 5 = 45
        self.assertEqual(game.village_state["morale"], 45)
        self.assertEqual(game.village_state["health"], 50)

    def test_state_clamping(self):
        """
        Tests if village state values are correctly clamped between 0 and 100.
        """
        primary_hexagram = self.hexagram_data[0]
        lines = [7, 7, 7, 7, 7, 7] # No changing lines for simplicity

        # Test upper bound
        game.village_state["food"] = 95
        choice_upper = {"disposition": "action", "effects": {"food": 20}}
        with patch('builtins.print'):
            game.apply_consequences(choice_upper, primary_hexagram, lines)
        self.assertEqual(game.village_state["food"], 100)

        # Test lower bound
        game.village_state["morale"] = 5
        choice_lower = {"disposition": "action", "effects": {"morale": -20}}
        with patch('builtins.print'):
            game.apply_consequences(choice_lower, primary_hexagram, lines)
        self.assertEqual(game.village_state["morale"], 0)

if __name__ == '__main__':
    unittest.main()