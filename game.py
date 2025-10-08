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

def get_transformed_hexagram(lines, hexagram_data):
    """
    Determines the transformed hexagram based on changing lines.
    - 6 (Old Yin) changes to Yang (1).
    - 9 (Old Yang) changes to Yin (0).
    - Stable lines (7, 8) do not change their nature.
    """
    if not any(line in [6, 9] for line in lines):
        return None  # No changing lines, so no transformed hexagram

    transformed_binary_lines = []
    for line in lines:
        if line == 6:  # Old Yin changes to Yang
            transformed_binary_lines.append(1)
        elif line == 9:  # Old Yang changes to Yin
            transformed_binary_lines.append(0)
        elif line == 7:  # Young Yang stays Yang
            transformed_binary_lines.append(1)
        elif line == 8:  # Young Yin stays Yin
            transformed_binary_lines.append(0)

    for hexagram in hexagram_data:
        if hexagram["lines_binary"] == transformed_binary_lines:
            return hexagram
    return None

def display_results(primary_hexagram, transformed_hexagram, lines):
    """Displays the divination results, including primary and transformed hexagrams."""
    if not primary_hexagram:
        print("Could not find a matching hexagram.")
        return

    # Display Primary Hexagram
    print("\n--- Divination Result ---")
    print("\nPrimary Hexagram (本卦): Represents the current situation.")
    print(f"#{primary_hexagram['number']}: {primary_hexagram['name_en']} ({primary_hexagram['name_zh']}) {primary_hexagram['symbol']}")
    print("\nJudgment (卦辭):")
    print(primary_hexagram['judgment_en'])
    print(primary_hexagram['judgment_zh'])

    # Identify and display changing lines
    changing_lines_indices = [i for i, line_value in enumerate(lines) if line_value in [6, 9]]

    if changing_lines_indices:
        print("\nChanging Lines (爻辭): Indicate the nature of the change.")
        for i in changing_lines_indices:
            line_value = lines[i]
            line_type = "Nine" if line_value == 9 else "Six"
            print(f"- Line {i+1} ({line_type}): {primary_hexagram['lines_en'][i]}")
            print(f"  {primary_hexagram['lines_zh'][i]}")

        # Display Transformed Hexagram
        if transformed_hexagram:
            print("\n------------------------")
            print("   (Transforms Into)")
            print("------------------------")
            print("\nTransformed Hexagram (之卦): Represents the future outlook.")
            print(f"#{transformed_hexagram['number']}: {transformed_hexagram['name_en']} ({transformed_hexagram['name_zh']}) {transformed_hexagram['symbol']}")
            print("\nJudgment (卦辭):")
            print(transformed_hexagram['judgment_en'])
            print(transformed_hexagram['judgment_zh'])
        else:
            # This case should ideally not happen if there are changing lines, but it's good practice to handle it.
            print("\nCould not determine the transformed hexagram.")

    else:
        print("\nThere are no changing lines. The situation is stable.")

def main():
    """Main game loop."""
    print("Welcome to The Way of the Sage.")
    print("Consulting the I Ching about your current situation...")

    hexagram_data = load_hexagram_data()
    divination_lines = perform_divination()

    print(f"\nYour divination resulted in the following lines (bottom to top): {divination_lines}")

    primary_hexagram = get_hexagram_from_lines(divination_lines, hexagram_data)
    transformed_hexagram = get_transformed_hexagram(divination_lines, hexagram_data)

    display_results(primary_hexagram, transformed_hexagram, divination_lines)

if __name__ == "__main__":
    main()