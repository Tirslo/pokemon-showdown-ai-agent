import json
from poke_env.player import Player
from poke_env.environment.battle import Battle
from poke_env.environment.move import Move
from poke_env.environment.pokemon import Pokemon
from poke_env.data.gen_data import GenData
from smolagents import Tool, CodeAgent, AmazonBedrockServerModel

from helpers import move_type_damage_wrapper

import boto3

bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name="ap-southeast-1",
)

class ClaudePlayer(Player):

    def __init__(self, *args, **kwargs):
        # Pass account_configuration and other Player args/kwargs to the parent
        super().__init__(*args, **kwargs)

        # self.gen = GenData.from_format(self.battle_format)
        self.gen = GenData.from_format("gen1ou")  # HACK

    def _find_pokemon_by_name(self, battle: Battle, pokemon_name: str) -> Pokemon | None:
        """Finds the Pokemon object corresponding to the given species name."""
        # Normalize name for comparison
        normalized_name = pokemon_name.lower()
        for pkmn in battle.available_switches:
            if pkmn.species.lower() == normalized_name:
                return pkmn
        return None

    def _find_move_by_name(self, battle: Battle, move_name: str) -> Move | None:
        """Finds the Move object corresponding to the given name."""
        # Normalize name for comparison (lowercase, remove spaces/hyphens)
        normalized_name = move_name.lower().replace(" ", "").replace("-", "")
        for move in battle.available_moves:
            if move.id == normalized_name: # move.id is already normalized
                return move
        # Fallback: try matching against the display name if ID fails (less reliable)
        for move in battle.available_moves:
             if move.id == move_name.lower(): # Handle cases like "U-turn" vs "uturn"
                 return move
             if move.name.lower() == move_name.lower():
                return move
        return None

    def _format_battle_state(self, battle: Battle) -> str:
        """Formats the current battle state into a string for the LLM."""

        # Own active Pokemon details
        active_pkmn = battle.active_pokemon
        active_pkmn_type_str = " / ".join(t.name for t in active_pkmn.types)
        active_pkmn_info = f"Your active Pokemon: {active_pkmn.species}\n" \
                           f"Type: {active_pkmn_type_str}\n" \
                           f"HP: {active_pkmn.current_hp_fraction * 100:.1f}%\n" \
                           f"Status: {active_pkmn.status.name if active_pkmn.status else 'None'}\n" \
                           f"Boosts: {active_pkmn.boosts}\n"

        # Opponent active Pokemon details
        opponent_pkmn = battle.opponent_active_pokemon
        opponent_active_pokemon_type_str = " / ".join(t.name for t in opponent_pkmn.types)
        opponent_pkmn_info = f"Opponent's active Pokemon: {opponent_pkmn.species}\n" \
                             f"Type: {opponent_active_pokemon_type_str}\n" \
                             f"HP: {opponent_pkmn.current_hp_fraction * 100:.1f}%\n" \
                             f"Status: {opponent_pkmn.status.name if opponent_pkmn.status else 'None'}\n" \
                             f"Boosts: {opponent_pkmn.boosts}\n"

        opponent_type_list = []
        if battle.opponent_active_pokemon.type_1:
            type_1 = battle.opponent_active_pokemon.type_1.name
            opponent_type_list.append(type_1)

            if battle.opponent_active_pokemon.type_2:
                type_2 = battle.opponent_active_pokemon.type_2.name
                opponent_type_list.append(type_2)

        opponent_type_advantage_info = move_type_damage_wrapper(
            battle.active_pokemon, self.gen.type_chart, opponent_type_list
        )

        if opponent_type_advantage_info is None or opponent_type_advantage_info == "":
            opponent_type_advantage_info = "No opponent type advantage."

        # Available moves
        available_moves_info = "Available moves:\n"
        if battle.available_moves:
            for move in battle.available_moves:

                effectiveness = move_type_damage_wrapper(battle.opponent_active_pokemon, self.gen.type_chart, [move.type.name])

                if effectiveness is None or effectiveness == "":
                    effectiveness = "Neutral effectiveness"

                available_moves_info += f"- {move.id} (Type: {move.type.name}, Base Power: {move.base_power}, Accuracy: {move.accuracy}, PP: {move.current_pp}/{move.max_pp}, Category: {move.category.name}) - {effectiveness}\n"
        else:
             available_moves_info += "- None (Must switch or Struggle)\n"

        # Available switches
        available_switches_info = "Available switches:\n"
        if battle.available_switches:
            for pkmn in battle.available_switches:
                 available_switches_info += f"- {pkmn.species} (HP: {pkmn.current_hp_fraction * 100:.1f}%, Status: {pkmn.status.name if pkmn.status else 'None'})\n"
        else:
            available_switches_info += "- None\n"

        # Combine information
        state_str = f"{active_pkmn_info}\n" \
                    f"{opponent_type_advantage_info}\n\n" \
                    f"{opponent_pkmn_info}\n\n" \
                    f"{available_moves_info}\n" \
                    f"{available_switches_info}\n"
                    # f"Weather: {battle.weather}\n" \
                    # f"Terrains: {battle.fields}\n" \
                    # f"Your Side Conditions: {battle.side_conditions}\n" \
                    # f"Opponent Side Conditions: {battle.opponent_side_conditions}\n"

        return state_str.strip()

    async def _get_llm_decision(self, battle_state: str) -> dict | None:
        """Sends state to LLM and gets back the function call decision."""
        
        try:
            system_prompt = """
            You are a skilled Pokemon battle AI. Your goal is to win the battle. 
            Based on the current battle state, decide the best action: either use an available move or switch to an available Pokémon.

            Your decision should factor in:

                Type advantages/disadvantages
                Current boosts/debuffs on each Pokemon
                Entry hazards on the field
                Potential to set up for bigger damage later
                Revenge killing opportunities
                Preserving your own Pokemon's health, but not at the cost of missing KO opportunities
            """


            battle_state_prompt = f"Current Battle State:\n{battle_state}\n\n"

            cot_prompt = """Choose the best action by thinking step by step. Your thought should no more than 4 sentences. Your output MUST be a JSON like: {"thought":"<step-by-step-thinking>", "move":"<move_name>"} if you decide to use a move or {"thought":"<step-by-step-thinking>", "switch":"<switch_pokemon_name>"} if you decide to switch Pokemon\n"""

            user_prompt = battle_state_prompt + cot_prompt

            prompt_config = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                        ],
                    }
                ],
            }

            body = json.dumps(prompt_config)

            modelId = "apac.anthropic.claude-sonnet-4-20250514-v1:0"
            accept = "application/json"
            contentType = "application/json"

            print("\nPrompting LLM for best action...\n")
            response = bedrock_runtime.invoke_model(
                body=body, modelId=modelId, accept=accept, contentType=contentType
            )
            print("LLM Responded!!\n")
            response_body = json.loads(response.get("body").read())

            message = response_body.get("content")[0].get("text")
            # print(f"LLM Raw Content: {message}\n")

            try: 
                # Attempt to parse the message
                decision = json.loads(message)
                return decision
            except json.JSONDecodeError:
                print(f"Error decoding JSON from LLM response: {message}")
                return None

        except Exception as e:
            print(f"Error during LLM call: {e}")

            return None

    async def choose_move(self, battle: Battle) -> str:

       # 1. Format battle state
        battle_state_str = self._format_battle_state(battle)
        print(f"\n--- Turn {battle.turn} ---") # Debugging
        print("OBSERVATION (Augmented with information from Pokemon Database):\n") 
        print(battle_state_str) # Debugging

        # 2. Get decision from LLM
        decision = await self._get_llm_decision(battle_state_str)

        # 3. Parse decision and create order
        if decision:
            print("LLM THOUGHT:\n", decision.get("thought", "No thought provided"))
            print("\n")
            if "move" in decision:
            # If the decision contains a move
                move_name = decision["move"]
                chosen_move = self._find_move_by_name(battle, move_name)
                if chosen_move and chosen_move in battle.available_moves:
                    print(f"LLM ACTION: Using move {chosen_move.id}")
                    return self.create_order(chosen_move)
                else:
                    print(f"Warning: LLM chose unavailable/invalid move '{move_name}'. Falling back.")

            elif "switch" in decision:
                # If the decision contains a switch
                pokemon_name = decision["switch"]
                chosen_switch = self._find_pokemon_by_name(battle, pokemon_name)
                if chosen_switch and chosen_switch in battle.available_switches:
                    print(f"LLM ACTION: Switching to {chosen_switch.species}")
                    return self.create_order(chosen_switch)
                else:
                    print(f"Warning: LLM chose unavailable/invalid switch '{pokemon_name}'. Falling back.")

        # 4. Fallback if API fails, returns invalid action, or no function call
        print("Fallback: Choosing random move/switch.")
        # Ensure options exist before choosing randomly
        available_options = battle.available_moves + battle.available_switches
        if available_options:
             # Use the built-in random choice method from Player for fallback
             return self.choose_random_move(battle)
        else:
             # Should only happen if forced to Struggle
             return self.choose_default_move(battle)
