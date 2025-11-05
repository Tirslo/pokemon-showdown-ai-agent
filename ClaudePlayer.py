import json
import time
from datetime import datetime
from typing import Optional, List

from poke_env.player import Player
from poke_env.environment.battle import Battle
from poke_env.environment.move import Move
from poke_env.environment.pokemon import Pokemon
from poke_env.data.gen_data import GenData

from helpers import move_type_damage_wrapper

import boto3
import re
from pymongo import MongoClient


# AWS Bedrock clients
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name="ap-southeast-2"  # adjust as needed
)

bedrock_embeddings = boto3.client(
    service_name="bedrock-runtime",
    region_name="ap-southeast-2"
)


class ClaudePlayer(Player):

    def __init__(
        self,
        mongo_uri: str,
        db_name: str = "pokemon_ai",
        collection_name: str = "battle_logs",
        embedding_model_id: str = "amazon.titan-embed-text-v2:0",
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.gen = GenData.from_format("gen1ou")
        self.embedding_model_id = embedding_model_id

        # MongoDB setup
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client[db_name]
        self.collection = self.db[collection_name]
        self.wins_collection = self.db["wins"]  # ✅ New collection for win/loss

    # ----------------------------
    # Embedding & Memory Functions
    # ----------------------------

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding using Amazon Titan."""
        try:
            body = json.dumps({"inputText": text})
            response = bedrock_embeddings.invoke_model(
                body=body,
                modelId=self.embedding_model_id,
                accept="application/json",
                contentType="application/json"
            )
            response_body = json.loads(response.get("body").read())
            return response_body["embedding"]
        except Exception as e:
            print(f"⚠️ Embedding error: {e}")
            return None

    
    def _get_battle_context(self, battle: Battle) -> str:
        """Concise, normalized context for embedding and retrieval."""
        my_team_hp = []
        for pkmn in battle.team.values():
            my_team_hp.append(f"{pkmn.species.lower()}:{pkmn.current_hp_fraction:.2f}")
        return (
            f"Active: {battle.active_pokemon.species.lower()}, "
            f"Opponent: {battle.opponent_active_pokemon.species.lower()}, "
            f"MyHP: {battle.active_pokemon.current_hp_fraction:.2f}, "
            f"OpponentHP: {battle.opponent_active_pokemon.current_hp_fraction:.2f}, "
            f"AvailableMoves: {[m.id for m in battle.available_moves]}, "
            f"AvailableSwitches: {[p.species.lower() for p in battle.available_switches]}"
        )

    
    def _get_battle_memories(self, battle: Battle, k: int = 3) -> str:
        """Retrieve top-k similar past decisions using Atlas Vector Search."""
        query_text = self._get_battle_context(battle)  
        embedding = self._get_embedding(query_text)
        if not embedding:
            return "No memory available (embedding failed)."

        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "embedding",
                        "queryVector": embedding,
                        "numCandidates": 100,
                        "limit": k
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "thought": "$llm_decision_raw.thought",
                        "action_type": 1,
                        "action_name": 1,
                        "turn": 1,
                        "battle_id": 1,
                        "fallback_used": 1,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                }
            ]

            results = list(self.collection.aggregate(pipeline))
            if not results:
                return "No relevant past experiences found."

            memory_lines = []
            for res in results:
                thought = res.get("thought", "No reasoning.")
                action_type = res["action_type"]
                action_name = res["action_name"]
                score = res["score"]
                fallback = "(fallback)" if res.get("fallback_used") else ""
                memory_lines.append(
                    f"- Similarity {score:.3f} {fallback} → {thought} → Action: {action_type} '{action_name}'"
                )
            return "\n".join(memory_lines)

        except Exception as e:
            print(f"⚠️ Vector search error: {e}")
            return "Failed to retrieve memories."

    def _log_action_to_mongodb(
        self,
        battle: Battle,
        battle_state_str: str,
        decision: dict | None,
        action_type: str,
        action_name: str,
        fallback_used: bool
    ):
        """Log turn to MongoDB with embedding for future retrieval."""
        try:
            context = self._get_battle_context(battle)  
            embedding = self._get_embedding(context)

            log_entry = {
                "timestamp": datetime.utcnow(),
                "battle_id": battle.battle_tag,
                "turn": battle.turn,
                "player_username": battle.player_username,
                "opponent_username": battle.opponent_username,
                "observation": battle_state_str,
                "llm_decision_raw": decision,
                "action_type": action_type,
                "action_name": action_name,
                "fallback_used": fallback_used,
                "active_pokemon": battle.active_pokemon.species,
                "opponent_active": battle.opponent_active_pokemon.species,
                "embedding": embedding,
            }

            self.collection.insert_one(log_entry)
            print(f"💾 MEMORY LOGGED → Turn {battle.turn}, Action: {action_type} '{action_name}' {'(fallback)' if fallback_used else ''}")

        except Exception as e:
            print(f"⚠️ Failed to log to MongoDB: {e}")

    # ----------------------------
    # Battle Logic (Unchanged Core)
    # ----------------------------

    def _find_pokemon_by_name(self, battle: Battle, pokemon_name: str) -> Optional[Pokemon]:
        normalized_name = pokemon_name.lower()
        for pkmn in battle.available_switches:
            if pkmn.species.lower() == normalized_name:
                return pkmn
        return None

    def _find_move_by_name(self, battle: Battle, move_name: str) -> Optional[Move]:
        normalized_name = move_name.lower().replace(" ", "").replace("-", "")
        for move in battle.available_moves:
            if move.id == normalized_name:
                return move
        for move in battle.available_moves:
            if move.name.lower() == move_name.lower():
                return move
        return None

    def _format_battle_state(self, battle: Battle) -> str:
        # ... (unchanged, so omitted for brevity) ...
        # (Keep your existing _format_battle_state implementation)
        active_pkmn = battle.active_pokemon
        active_pkmn_type_str = " / ".join(t.name for t in active_pkmn.types)
        active_pkmn_info = (
            f"Your active Pokemon: {active_pkmn.species}\n"
            f"Type: {active_pkmn_type_str}\n"
            f"HP: {active_pkmn.current_hp_fraction * 100:.1f}% ({'Fainted' if active_pkmn.fainted else 'Active'})\n"
            f"Status: {active_pkmn.status.name if active_pkmn.status else 'None'}\n"
            f"Boosts: {active_pkmn.boosts}\n"
        )

        opponent_pkmn = battle.opponent_active_pokemon
        opponent_type_str = " / ".join(t.name for t in opponent_pkmn.types)
        opponent_pkmn_info = (
            f"Opponent's active Pokemon: {opponent_pkmn.species}\n"
            f"Type: {opponent_type_str}\n"
            f"HP: {opponent_pkmn.current_hp_fraction * 100:.1f}% ({'Fainted' if opponent_pkmn.fainted else 'Active'})\n"
            f"Status: {opponent_pkmn.status.name if opponent_pkmn.status else 'None'}\n"
            f"Boosts: {opponent_pkmn.boosts}\n"
        )

        your_team_info = "Your full team status:\n"
        for pkmn in battle.team.values():
            hp_pct = pkmn.current_hp_fraction * 100
            status = pkmn.status.name if pkmn.status else "None"
            fainted_str = " (Fainted)" if pkmn.fainted else ""
            active_str = " [ACTIVE]" if pkmn == battle.active_pokemon else ""
            your_team_info += f"- {pkmn.species}: HP {hp_pct:.1f}%{fainted_str}, Status: {status}{active_str}\n"

        opponent_team_info = "Opponent's known Pokémon:\n"
        known_opponent_pokemon = set()
        known_opponent_pokemon.add(battle.opponent_active_pokemon.species)
        for pkmn in battle.opponent_team.values():
            if pkmn.species not in known_opponent_pokemon:
                known_opponent_pokemon.add(pkmn.species)
        for species in sorted(known_opponent_pokemon):
            opponent_team_info += f"- {species}\n"

        opponent_type_list = []
        opp = battle.opponent_active_pokemon
        if opp.type_1:
            opponent_type_list.append(opp.type_1.name)
            if opp.type_2:
                opponent_type_list.append(opp.type_2.name)

        opponent_type_advantage_info = move_type_damage_wrapper(
            battle.active_pokemon, self.gen.type_chart, opponent_type_list
        ) or "No opponent type advantage."

        available_moves_info = "Available moves:\n"
        if battle.available_moves:
            for move in battle.available_moves:
                effectiveness = move_type_damage_wrapper(
                    battle.opponent_active_pokemon, self.gen.type_chart, [move.type.name]
                ) or "Neutral effectiveness"
                available_moves_info += (
                    f"- {move.id} (Type: {move.type.name}, BP: {move.base_power}, "
                    f"Acc: {move.accuracy}, PP: {move.current_pp}/{move.max_pp}, "
                    f"Cat: {move.category.name}) - {effectiveness}\n"
                )
        else:
            available_moves_info += "- None (Must switch or Struggle)\n"

        available_switches_info = "Available switches (non-fainted, not active):\n"
        if battle.available_switches:
            for pkmn in battle.available_switches:
                available_switches_info += (
                    f"- {pkmn.species} (HP: {pkmn.current_hp_fraction * 100:.1f}%, "
                    f"Status: {pkmn.status.name if pkmn.status else 'None'})\n"
                )
        else:
            available_switches_info += "- None\n"

        state_parts = [
            "📋 YOUR TEAM STATUS:\n" + your_team_info.strip(),
            "⚡ YOUR ACTIVE POKÉMON:\n" + active_pkmn_info.strip(),
            "🛡️ TYPE ADVANTAGE:\n" + opponent_type_advantage_info,
            "💥 OPPONENT ACTIVE:\n" + opponent_pkmn_info.strip(),
            "🌐 OPPONENT KNOWN TEAM:\n" + opponent_team_info.strip(),
            "⚔️ AVAILABLE MOVES:\n" + available_moves_info.strip(),
            "🔁 AVAILABLE SWITCHES:\n" + available_switches_info.strip()
        ]

        separator = "\n" + "-" * 40 + "\n"
        return separator.join(state_parts)

    # ----------------------------
    # LLM Decision with Memory
    # ----------------------------

    async def _get_llm_decision(self, battle_state: str, battle: Battle) -> Optional[dict]:
      
        past_memories = self._get_battle_memories(battle, k=3)
        print(f"\n🧠 RETRIEVED MEMORIES (k={len(past_memories.splitlines())}):")
        if past_memories.startswith("No relevant") or past_memories.startswith("Failed"):
            print(f"  🚫 {past_memories}")
        else:
            for line in past_memories.splitlines():
                print(f"  ➤ {line}")

        system_prompt = """
You are an expert Pokémon battle strategist. Use both the current battle state and past experiences to make optimal decisions.
Prioritize actions that succeeded in similar situations. Avoid strategies that failed (marked as 'fallback').
""".strip()

        user_prompt = f"""
--- PAST EXPERIENCES (most relevant first) ---
{past_memories}

--- CURRENT BATTLE STATE ---
{battle_state}

--- INSTRUCTIONS ---
Respond with ONLY a valid JSON object. No extra text, markdown, or explanation.

Valid formats:
{{"thought":"<1-4 sentence reasoning>", "move":"<exact move name>"}}
OR
{{"thought":"<1-4 sentence reasoning>", "switch":"<exact pokemon species>"}}

Begin your response now.
""".strip()

        try:
            prompt_config = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
            }

            body = json.dumps(prompt_config)
            modelId = "apac.anthropic.claude-sonnet-4-20250514-v1:0"

            response = bedrock_runtime.invoke_model(
                body=body,
                modelId=modelId,
                accept="application/json",
                contentType="application/json"
            )

            raw_body = response["body"].read().decode("utf-8")
            response_body = json.loads(raw_body)
            raw_message = response_body["content"][0]["text"].strip()

            json_match = re.search(r"\{.*\}", raw_message, re.DOTALL)
            if not json_match:
                print("❌ No JSON in LLM response")
                return None

            json_str = json_match.group(0)
            return json.loads(json_str)

        except Exception as e:
            print(f"💥 LLM error: {e}")
            return None

    # ----------------------------
    # Main Action Loop
    # ----------------------------

    async def choose_move(self, battle: Battle) -> str:
        battle_state_str = self._format_battle_state(battle)
        
        print(f"\n" + "="*60)
        print(f"🔥 TURN {battle.turn} | BATTLE ID: {battle.battle_tag}")
        print("="*60)
        print("📊 OBSERVATION:")
        print(battle_state_str)

        decision = await self._get_llm_decision(battle_state_str, battle)

        if decision:
            thought = decision.get("thought", "No reasoning provided.")
            print(f"\n🧠 LLM THOUGHT:\n{thought}")

            if "move" in decision:
                move_name = decision["move"]
                chosen_move = self._find_move_by_name(battle, move_name)
                if chosen_move and chosen_move in battle.available_moves:
                    print(f"\n✅ LLM ACTION: Using move '{chosen_move.id}'")
                    order = self.create_order(chosen_move)
                    self._log_action_to_mongodb(battle, battle_state_str, decision, "move", chosen_move.id, False)
                    return order
                else:
                    print(f"⚠️ Invalid move: '{move_name}' — falling back.")

            elif "switch" in decision:
                pokemon_name = decision["switch"]
                chosen_switch = self._find_pokemon_by_name(battle, pokemon_name)
                if chosen_switch and chosen_switch in battle.available_switches and not chosen_switch.fainted:
                    print(f"\n✅ LLM ACTION: Switching to '{chosen_switch.species}'")
                    order = self.create_order(chosen_switch)
                    self._log_action_to_mongodb(battle, battle_state_str, decision, "switch", chosen_switch.species, False)
                    return order
                else:
                    print(f"⚠️ Invalid switch: '{pokemon_name}' — falling back.")

        # Fallback
        print(f"\n🔄 FALLBACK: Choosing random move/switch...")
        available_options = battle.available_moves + battle.available_switches
        if available_options:
            order = self.choose_random_move(battle)
        else:
            order = self.choose_default_move(battle)

        # Log fallback
        if isinstance(order, Move):
            action_type, action_name = "move", order.id
        elif isinstance(order, Pokemon):
            action_type, action_name = "switch", order.species
        else:
            action_type, action_name = "default", "struggle"

        self._log_action_to_mongodb(battle, battle_state_str, decision, action_type, action_name, True)
        print(f"✅ Fallback action logged: {action_type} '{action_name}'")
        return order
