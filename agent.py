from dotenv import load_dotenv
load_dotenv()
import os
import asyncio
from poke_env import AccountConfiguration, LocalhostServerConfiguration
from poke_env.teambuilder import Teambuilder

from ClaudePlayer import ClaudePlayer

team_1 = """
Squirtle  
Ability: No Ability  
Level: 100
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
- Surf  
- Body Slam  
- Blizzard  
- Seismic Toss

Charmander  
Ability: No Ability
Level: 100 
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
- Body Slam  
- Fire Blast  
- Mega Kick  
- Slash

Nidoking  
Ability: No Ability  
Level: 100  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
- Earthquake  
- Body Slam  
- Thunderbolt  
- Ice Beam

Fearow  
Ability: No Ability  
Level: 100  
EVs: 252 HP / 252 Atk / 252 Def / 252 SpA / 252 SpD / 252 Spe  
- Drill Peck  
- Agility  
- Double-Edge  
- Mirror Move
"""

class LLMTeam(Teambuilder):
    def __init__(self, teams):
        self.teams = [self.join_team(self.parse_showdown_team(team)) for team in teams]

    def yield_team(self):
        return self.teams[0]


async def main():
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri is None:
        raise ValueError("MONGO_URI environment variable is not set.")

    player = ClaudePlayer(
        # log_level=20,
        account_configuration=AccountConfiguration("caveman_llm_bot1", "0N5hrMtmIeikv8m"),
        mongo_uri=mongo_uri,
        server_configuration=LocalhostServerConfiguration,
        battle_format="gen1ou",
        team=LLMTeam([team_1]),
    )

    await player.send_challenges("human_player1", n_challenges=1)
    # await player.accept_challenges('caveman_h00man', 1)


if __name__ == "__main__":
    asyncio.run(main())