import json
import random
from divination import perform_divination

# --- Village State Management ---
village_state = {
    "food": 50,
    "morale": 50,
    "health": 50,
}

def display_village_status():
    """Displays the current status of the village."""
    print("\n--- Village Status ---")
    print(f"Food: {village_state['food']}/100")
    print(f"Morale: {village_state['morale']}/100")
    print(f"Health: {village_state['health']}/100")
    print("----------------------")


def load_hexagram_data():
    """Loads the I Ching data from the JSON file."""
    with open("i_ching_data.json", "r", encoding="utf-8") as f:
        return json.load(f)["hexagrams"]

# --- Event System ---
def load_events_data():
    """Loads the event data from the JSON file."""
    with open("events.json", "r", encoding="utf-8") as f:
        return json.load(f)["events"]

def trigger_event(events):
    """Selects a random event and presents it to the player."""
    event = random.choice(events)
    print("\n--- A New Event Unfolds ---")
    print(event["description_zh"])
    print(event["description_en"])
    print("-----------------------------")
    return event

def get_player_choice(event):
    """Gets the player's choice for the current event."""
    print("\nWhat is your counsel, Sage?")
    for i, choice in enumerate(event["choices"]):
        print(f"{i + 1}: {choice['text_zh']} ({choice['text_en']})")

    while True:
        try:
            player_input = input("Enter the number of your choice: ")
            choice_index = int(player_input) - 1
            if 0 <= choice_index < len(event["choices"]):
                return event["choices"][choice_index]
            else:
                print("Invalid choice. Please enter a number from the list.")
        except ValueError:
            print("Invalid input. Please enter a number.")

trigram_dispositions = {
    "111": "heaven", "000": "earth", "100": "thunder", "011": "wind",
    "010": "water",  "101": "fire",  "001": "mountain", "110": "lake"
}

def apply_consequences(choice, primary_hexagram, transformed_hexagram):
    """
    Applies the consequences of the player's choice, factoring in the
    wisdom of the I Ching.
    """
    effects = choice["effects"].copy()
    choice_disposition = choice["disposition"]
    bonus = 10  # Bonus points for aligning with the hexagram's message

    # Determine the trigrams of the primary hexagram
    lower_trigram_bin = "".join(map(str, primary_hexagram["lines_binary"][:3]))
    upper_trigram_bin = "".join(map(str, primary_hexagram["lines_binary"][3:]))

    primary_dispositions = {
        trigram_dispositions.get(lower_trigram_bin),
        trigram_dispositions.get(upper_trigram_bin)
    }

    # Also consider the transformed hexagram if it exists
    if transformed_hexagram:
        lower_transformed_bin = "".join(map(str, transformed_hexagram["lines_binary"][:3]))
        upper_transformed_bin = "".join(map(str, transformed_hexagram["lines_binary"][3:]))
        primary_dispositions.add(trigram_dispositions.get(lower_transformed_bin))
        primary_dispositions.add(trigram_dispositions.get(upper_transformed_bin))

    print("\n--- The Consequences Unfold ---")

    # Check if the choice aligns with the hexagram's disposition
    if choice_disposition in primary_dispositions:
        print("Your choice aligns with the wisdom of the hexagram! The outcome is enhanced.")
        for key in effects:
            if effects[key] > 0:
                effects[key] += bonus
            elif effects[key] < 0:
                effects[key] = max(effects[key] + bonus, 0) # Bonus mitigates negative effects
    else:
        print("You have chosen a path that diverges from the hexagram's counsel. The outcome is as expected.")

    for key, value in effects.items():
        change = value - choice["effects"][key] # Calculate the bonus effect
        total_change = value

        original_value = village_state[key]
        village_state[key] += total_change
        village_state[key] = max(0, min(100, village_state[key])) # Clamp
        actual_change = village_state[key] - original_value

        if actual_change > 0:
            print(f"Your decision has increased {key} by {actual_change}.")
        elif actual_change < 0:
            print(f"Your decision has decreased {key} by {abs(actual_change)}.")

    print("-----------------------------")


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
    """Main game loop for The Way of the Sage."""
    print("Welcome to The Way of the Sage (天人之路).")

    # Load all game data at the start
    hexagram_data = load_hexagram_data()
    events_data = load_events_data()

    # Game loop runs continuously
    while True:
        # 1. Display current village status
        display_village_status()

        # 2. A new event occurs
        current_event = trigger_event(events_data)

        # 3. The sage performs divination for guidance
        print("\nYou take a deep breath and cast the coins to seek the wisdom of the I Ching...")
        divination_lines = perform_divination()
        primary_hexagram = get_hexagram_from_lines(divination_lines, hexagram_data)
        transformed_hexagram = get_transformed_hexagram(divination_lines, hexagram_data)

        # 4. The results are revealed
        display_results(primary_hexagram, transformed_hexagram, divination_lines)

        # 5. The player makes a choice
        player_choice = get_player_choice(current_event)

        # 6. The consequences are applied
        apply_consequences(player_choice, primary_hexagram, transformed_hexagram)

        # 7. Check for game over conditions (optional, can be added later)
        if village_state["food"] <= 0 or village_state["morale"] <= 0 or village_state["health"] <= 0:
            print("\n--- The Story Ends ---")
            print("The village has fallen into ruin. Your journey as its sage is over.")
            if village_state["food"] <= 0:
                print("The people starved.")
            if village_state["morale"] <= 0:
                print("The people lost hope and scattered.")
            if village_state["health"] <= 0:
                print("Plague and illness consumed the village.")
            break

        # 8. Wait for player to continue
        input("\nPress Enter to reflect and move on to the next season...")

if __name__ == "__main__":
    main()