import random

def cast_line():
    """
    Simulates a single toss of three coins to determine one line of a hexagram.
    - Heads is assigned a value of 3 (Yang).
    - Tails is assigned a value of 2 (Yin).

    The sum of the three coins determines the line's nature:
    - 6 (3x Tails): Old Yin (changing line)
    - 7 (2x Tails, 1x Heads): Young Yang (stable line)
    - 8 (2x Heads, 1x Tails): Young Yin (stable line)
    - 9 (3x Heads): Old Yang (changing line)
    """
    coins = [2, 3]  # 2 for Tails (Yin), 3 for Heads (Yang)
    toss_result = sum(random.choice(coins) for _ in range(3))
    return toss_result

def perform_divination():
    """
    Performs a full divination by casting six lines to form a hexagram.
    The lines are generated from bottom to top (line 1 to line 6).

    Returns:
        list[int]: A list of six numbers (6, 7, 8, or 9), representing the hexagram.
    """
    hexagram_lines = [cast_line() for _ in range(6)]
    return hexagram_lines

if __name__ == "__main__":
    print("Performing I Ching divination using the three-coin method...")

    lines = perform_divination()

    print("\nThe six lines of the hexagram, from bottom (line 1) to top (line 6), are:")
    print(lines)

    # Provide a simple interpretation of the line types
    line_meanings = {
        6: "Old Yin (Changing Yin ⚋ x)",
        7: "Young Yang (Stable Yang ⚊)",
        8: "Young Yin (Stable Yin ⚋)",
        9: "Old Yang (Changing Yang ⚊ x)"
    }

    print("\nLine-by-line interpretation:")
    for i, line_value in enumerate(lines, 1):
        print(f"Line {i}: {line_meanings[line_value]}")