import json
from poke_env.player import Player
from poke_env.environment.battle import Battle
from poke_env.environment.move import Move
from poke_env.environment.pokemon import Pokemon
from poke_env.data.gen_data import GenData
from smolagents import Tool, CodeAgent, ToolCallingAgent, AmazonBedrockServerModel

from helpers import move_type_damage_wrapper

class FormatBattleStateTool(Tool):
    name = "format_battle_state"
    description = "Formats the current battle state into a comprehensive string for analysis."
    inputs = {
        "battle": {
            "type": "Battle",
            "description": "The current battle state to format."
        }
    }
    output_type = "string"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gen = GenData.from_format("gen1ou")

    def forward(self, battle: Battle) -> str:
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

        return state_str.strip()


class FindMoveByNameTool(Tool):
    name = "find_move_by_name"
    description = "Finds a move object by name from available moves in the battle."
    inputs = {
        "battle": {
            "type": "Battle", 
            "description": "The current battle state."
        },
        "move_name": {
            "type": "string",
            "description": "The name of the move to find."
        }
    }
    output_type = "Move"

    def forward(self, battle: Battle, move_name: str) -> Move | None:
        """Finds the Move object corresponding to the given name."""
        normalized_name = move_name.lower().replace(" ", "").replace("-", "")
        for move in battle.available_moves:
            if move.id == normalized_name:
                return move
        # Fallback
        for move in battle.available_moves:
             if move.id == move_name.lower():
                 return move
             if move.name.lower() == move_name.lower():
                return move
        return None


class FindPokemonByNameTool(Tool):
    name = "find_pokemon_by_name"
    description = "Finds a Pokemon object by species name from available switches."
    inputs = {
        "battle": {
            "type": "Battle",
            "description": "The current battle state."
        },
        "pokemon_name": {
            "type": "string", 
            "description": "The species name of the Pokemon to find."
        }
    }
    output_type = "Pokemon"

    def forward(self, battle: Battle, pokemon_name: str) -> Pokemon | None:
        """Finds the Pokemon object corresponding to the given species name."""
        normalized_name = pokemon_name.lower()
        for pkmn in battle.available_switches:
            if pkmn.species.lower() == normalized_name:
                return pkmn
        return None


class SmolAgentPlayer(Player):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gen = GenData.from_format("gen1ou")

        # Initialize SmoLAgents model
        model = AmazonBedrockServerModel(
            model_id="apac.anthropic.claude-sonnet-4-20250514-v1:0"
        )

        # Define system prompt for Pokemon battles
        system_prompt = """
        You are a skilled Pokemon battle AI agent. Your goal is to win battles through strategic decision-making.
        
        When analyzing battle states, consider:
        - Type advantages/disadvantages and damage calculations
        - Current boosts/debuffs on each Pokemon
        - Entry hazards and field conditions
        - Setup opportunities for bigger damage later
        - Revenge killing opportunities
        - Health preservation vs KO opportunities
        
        Use the available tools to analyze the battle state and make decisions.
        Always return your decision as JSON in this exact format:
        {"thought": "step-by-step reasoning (max 4 sentences)", "move": "move_name"} 
        OR
        {"thought": "step-by-step reasoning (max 4 sentences)", "switch": "pokemon_species_name"}
        """

        self.agent = ToolCallingAgent(
            tools=[
                FormatBattleStateTool(),
                FindMoveByNameTool(), 
                FindPokemonByNameTool()
            ],
            model=model,
            system_prompt=system_prompt
        )

    async def choose_move(self, battle: Battle) -> str:
        print(f"\n--- Turn {battle.turn} ---")
        
        try:
            # Create prompt for the agent
            prompt = f"""
            Analyze the current Pokemon battle (turn {battle.turn}) and choose the best action.
            
            1. First, use format_battle_state tool to get the current battle information
            2. Analyze the situation considering type advantages, HP, status, and strategic options
            3. Decide whether to use a move or switch Pokemon
            4. Return your decision as JSON: {{"thought": "reasoning", "move": "move_name"}} or {{"thought": "reasoning", "switch": "pokemon_name"}}
            
            Battle object: {battle}
            """
            
            print("Prompting SmoLAgents for best action...\n")
            
            # Run the agent
            result = self.agent.run(prompt)
            
            print("SmoLAgents responded!\n")
            print(f"Agent result: {result}\n")
            
            # Parse the result to extract JSON decision
            decision = self._parse_agent_response(result)
            
            if decision:
                print("AGENT THOUGHT:\n", decision.get("thought", "No thought provided"))
                print("\n")
                
                if "move" in decision:
                    move_name = decision["move"]
                    chosen_move = self._find_move_by_name(battle, move_name)
                    if chosen_move and chosen_move in battle.available_moves:
                        print(f"AGENT ACTION: Using move {chosen_move.id}")
                        return self.create_order(chosen_move)
                    else:
                        print(f"Warning: Agent chose unavailable/invalid move '{move_name}'. Falling back.")
                
                elif "switch" in decision:
                    pokemon_name = decision["switch"]
                    chosen_switch = self._find_pokemon_by_name(battle, pokemon_name)
                    if chosen_switch and chosen_switch in battle.available_switches:
                        print(f"AGENT ACTION: Switching to {chosen_switch.species}")
                        return self.create_order(chosen_switch)
                    else:
                        print(f"Warning: Agent chose unavailable/invalid switch '{pokemon_name}'. Falling back.")
        
        except Exception as e:
            print(f"Error with SmoLAgents: {e}")
        
        # Fallback if agent fails or returns invalid action
        print("Fallback: Choosing random move/switch.")
        available_options = battle.available_moves + battle.available_switches
        if available_options:
            return self.choose_random_move(battle)
        else:
            return self.choose_default_move(battle)

    def _parse_agent_response(self, response: str) -> dict | None:
        """Parse the agent's response to extract JSON decision."""
        try:
            # If the response is already a dict
            if isinstance(response, dict):
                return response
                
            # Try to parse as JSON directly
            if isinstance(response, str):
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    # Try to extract JSON from the response using regex
                    import re
                    json_match = re.search(r'\{[^}]*"(?:thought|move|switch)"[^}]*\}', response)
                    if json_match:
                        return json.loads(json_match.group())
                    
                    # Alternative: look for JSON-like patterns
                    lines = response.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line.startswith('{') and line.endswith('}'):
                            try:
                                return json.loads(line)
                            except json.JSONDecodeError:
                                continue
            
            print(f"Could not parse agent response: {response}")
            return None
            
        except Exception as e:
            print(f"Error parsing agent response: {e}")
            return None

    def _find_pokemon_by_name(self, battle: Battle, pokemon_name: str) -> Pokemon | None:
        """Finds the Pokemon object corresponding to the given species name."""
        normalized_name = pokemon_name.lower()
        for pkmn in battle.available_switches:
            if pkmn.species.lower() == normalized_name:
                return pkmn
        return None

    def _find_move_by_name(self, battle: Battle, move_name: str) -> Move | None:
        """Finds the Move object corresponding to the given name."""
        normalized_name = move_name.lower().replace(" ", "").replace("-", "")
        for move in battle.available_moves:
            if move.id == normalized_name:
                return move
        for move in battle.available_moves:
             if move.id == move_name.lower():
                 return move
             if move.name.lower() == move_name.lower():
                return move
        return None