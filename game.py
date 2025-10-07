import json
from divination import perform_divination

def load_hexagram_data():
    """Loads the I Ching data from the JSON file."""
    with open("i_ching_data.json", "r", encoding="utf-8") as f:
        return json.load(f)["hexagrams"]

def get_hexagram_from_lines(lines, hexagram_data):
    """
    Determines the primary hexagram from the divination result.
    - 6 (Old Yin) and 8 (Young Yin) are treated as Yin (0).
    - 7 (Young Yang) and 9 (Old Yang) are treated as Yang (1).
    """
    binary_lines = []
    for line in lines:
        if line in [6, 8]:  # Yin lines
            binary_lines.append(0)
        elif line in [7, 9]:  # Yang lines
            binary_lines.append(1)

    for hexagram in hexagram_data:
        if hexagram["lines_binary"] == binary_lines:
            return hexagram
    return None

def display_results(hexagram, lines):
    """Displays the divination results to the user."""
    if not hexagram:
        print("Could not find a matching hexagram.")
        return

    print("\n--- Divination Result ---")
    print(f"Hexagram {hexagram['number']}: {hexagram['name_en']} ({hexagram['name_zh']}) {hexagram['symbol']}")
    print("\nJudgment (卦辭):")
    print(hexagram['judgment_en'])
    print(hexagram['judgment_zh'])

    changing_lines = []
    for i, line_value in enumerate(lines):
        if line_value in [6, 9]:
            changing_lines.append((i, line_value))

    if changing_lines:
        print("\nChanging Lines (爻辭):")
        for i, line_value in changing_lines:
            line_type = "Nine" if line_value == 9 else "Six"
            print(f"- Line {i+1} ({line_type}): {hexagram['lines_en'][i]}")
            print(f"  {hexagram['lines_zh'][i]}")
    else:
        print("\nThere are no changing lines.")

def main():
    """Main game loop."""
    print("Welcome to The Way of the Sage.")
    print("Consulting the I Ching about your current situation...")

    hexagram_data = load_hexagram_data()
    divination_lines = perform_divination()

    print(f"\nYour divination resulted in the following lines (bottom to top): {divination_lines}")

    primary_hexagram = get_hexagram_from_lines(divination_lines, hexagram_data)

    display_results(primary_hexagram, divination_lines)

if __name__ == "__main__":
    main()