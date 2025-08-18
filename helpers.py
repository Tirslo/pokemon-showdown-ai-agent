def calculate_move_type_damage_multiplier(
    type_1, type_2, type_chart, constraint_type_list
):
    TYPE_list = "BUG,DARK,DRAGON,ELECTRIC,FAIRY,FIGHTING,FIRE,FLYING,GHOST,GRASS,GROUND,ICE,NORMAL,POISON,PSYCHIC,ROCK,STEEL,WATER".split(
        ","
    )

    move_type_damage_multiplier_list = []

    if type_2:
        for type in TYPE_list:
            move_type_damage_multiplier_list.append(
                type_chart[type_1][type] * type_chart[type_2][type]
            )
        move_type_damage_multiplier_dict = dict(
            zip(TYPE_list, move_type_damage_multiplier_list)
        )
    else:
        move_type_damage_multiplier_dict = type_chart[type_1]

    effective_type_list = []
    extreme_type_list = []
    resistant_type_list = []
    extreme_resistant_type_list = []
    immune_type_list = []
    for type, value in move_type_damage_multiplier_dict.items():
        if value == 2:
            effective_type_list.append(type)
        elif value == 4:
            extreme_type_list.append(type)
        elif value == 1 / 2:
            resistant_type_list.append(type)
        elif value == 1 / 4:
            extreme_resistant_type_list.append(type)
        elif value == 0:
            immune_type_list.append(type)
        else:  # value == 1
            continue

    if constraint_type_list:
        extreme_type_list = list(
            set(extreme_type_list).intersection(set(constraint_type_list))
        )
        effective_type_list = list(
            set(effective_type_list).intersection(set(constraint_type_list))
        )
        resistant_type_list = list(
            set(resistant_type_list).intersection(set(constraint_type_list))
        )
        extreme_resistant_type_list = list(
            set(extreme_resistant_type_list).intersection(set(constraint_type_list))
        )
        immune_type_list = list(
            set(immune_type_list).intersection(set(constraint_type_list))
        )

    return (
        list(map(lambda x: x.capitalize(), extreme_type_list)),
        list(map(lambda x: x.capitalize(), effective_type_list)),
        list(map(lambda x: x.capitalize(), resistant_type_list)),
        list(map(lambda x: x.capitalize(), extreme_resistant_type_list)),
        list(map(lambda x: x.capitalize(), immune_type_list)),
    )

def move_type_damage_wrapper(pokemon, type_chart, constraint_type_list=None):

    type_1 = None
    type_2 = None
    if pokemon.type_1:
        type_1 = pokemon.type_1.name
        if pokemon.type_2:
            type_2 = pokemon.type_2.name

    move_type_damage_prompt = ""
    (
        extreme_effective_type_list,
        effective_type_list,
        resistant_type_list,
        extreme_resistant_type_list,
        immune_type_list,
    ) = calculate_move_type_damage_multiplier(
        type_1, type_2, type_chart, constraint_type_list
    )

    move_type_damage_prompt = ""
    if extreme_effective_type_list:
        move_type_damage_prompt = (
            move_type_damage_prompt
            + " "
            + ", ".join(extreme_effective_type_list)
            + f"-type attack is extremely-effective (4x damage) to {pokemon.species}."
        )

    if effective_type_list:
        move_type_damage_prompt = (
            move_type_damage_prompt
            + " "
            + ", ".join(effective_type_list)
            + f"-type attack is super-effective (2x damage) to {pokemon.species}."
        )

    if resistant_type_list:
        move_type_damage_prompt = (
            move_type_damage_prompt
            + " "
            + ", ".join(resistant_type_list)
            + f"-type attack is ineffective (0.5x damage) to {pokemon.species}."
        )

    if extreme_resistant_type_list:
        move_type_damage_prompt = (
            move_type_damage_prompt
            + " "
            + ", ".join(extreme_resistant_type_list)
            + f"-type attack is highly ineffective (0.25x damage) to {pokemon.species}."
        )

    if immune_type_list:
        move_type_damage_prompt = (
            move_type_damage_prompt
            + " "
            + ", ".join(immune_type_list)
            + f"-type attack is zero effect (0x damage) to {pokemon.species}."
        )

    return move_type_damage_prompt
