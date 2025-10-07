# Game Design Document: The Way of the Sage

## 1. Overview

*   **Game Title:** The Way of the Sage (天人之路)
*   **Genre:** Narrative-driven role-playing / strategy simulation.
*   **Target Audience:** Players interested in philosophy, strategy, and unique narrative experiences.
*   **Core Concept:** Players take on the role of a young sage in an ancient village. Instead of using combat or magic, the player uses the wisdom of the I Ching to guide the village through various challenges, aiming to achieve harmony and prosperity. The game focuses on understanding the concept of "change" and making decisions that align with the flow of events.

## 2. Gameplay Mechanics

### 2.1. Core Loop

1.  **Encounter:** An event occurs in the village, or a villager presents a problem (e.g., drought, disputes, strange omens).
2.  **Divination:** The player performs a divination ritual to consult the I Ching. This will be implemented as a mini-game simulating the "three-coin method" to generate a hexagram.
3.  **Interpretation:** The game displays the resulting hexagram, along with its name, judgment, and the text for any changing lines. The player must interpret this philosophical guidance in the context of the current problem.
4.  **Decision:** Based on their interpretation, the player chooses a course of action from several options. The options will be designed to reflect different understandings of the hexagram (e.g., "act decisively," "wait patiently," "seek help from others," "focus on internal reflection").
5.  **Observation:** The player's decision influences the village's state. The consequences might be immediate or unfold over time, teaching the player about the long-term effects of their choices.

### 2.2. Key Features

*   **Dynamic Narrative:** The story evolves based on the player's decisions. The state of the village (e.g., resources, morale, relationships) is constantly changing.
*   **Hexagram System:** The full system of 64 hexagrams forms the core of the game's guidance mechanism. Each hexagram offers a unique perspective on a situation.
*   **Village Management:** The player needs to keep track of the village's key metrics, such as food, water, morale, and health. Decisions will impact these resources.
*   **Character Interaction:** Players will build relationships with various villagers, who will remember the player's advice and react accordingly.

## 3. Story and Setting

*   **World:** The game is set in a mythical, ancient Chinese village nestled in a secluded valley. The environment is beautiful but also subject to the whims of nature.
*   **Player Character:** A young, aspiring sage who has inherited the role of the village's spiritual guide.
*   **Goal:** There is no traditional "win" condition. The goal is to guide the village to a state of balance and harmony, to learn from the I Ching, and to experience the profound philosophy of "change."

## 4. Technical Outline

*   **Engine:** The initial prototype will be a simple command-line application built with Python.
*   **Data:** The 64 hexagrams and their associated texts will be stored in a structured JSON file for easy access.
*   **Game State:** The village's status will be managed through a simple data structure (e.g., a Python dictionary).

This document serves as the foundational blueprint for the development of "The Way of the Sage." It will be updated as the project progresses.