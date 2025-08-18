import asyncio

from poke_env import AccountConfiguration, LocalhostServerConfiguration
from poke_env.teambuilder import Teambuilder

from ClaudePlayer import ClaudePlayer
from SmolAgentPlayer import SmolAgentPlayer

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
"""

class LLMTeam(Teambuilder):
    def __init__(self, teams):
        self.teams = [self.join_team(self.parse_showdown_team(team)) for team in teams]

    def yield_team(self):
        return self.teams[0]


async def main():
    player = ClaudePlayer(
        # log_level=20,
        account_configuration=AccountConfiguration("caveman_llm_bot1", "0N5hrMtmIeikv8m"),
        server_configuration=LocalhostServerConfiguration,
        battle_format="gen1ou",
        team=LLMTeam([team_1]),
    )

    await player.send_challenges("human_player1", n_challenges=1)
    # await player.accept_challenges('caveman_h00man', 1)


if __name__ == "__main__":
    asyncio.run(main())