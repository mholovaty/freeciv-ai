"""
Freeciv constants for use with FreecivClient.

These values are generated from freeciv's specenum headers and
are stable across the 3.x ruleset series.

Usage::

    from freeciv_ai.constants import Actions, Directions

    # Move unit north
    client.move_unit(unit_id, Directions.N)

    # Check if a unit can move to a tile
    prob = client.can_do_action(unit_id, Actions.UNIT_MOVE, tile_idx)
    if prob >= 0:
        client.do_action(unit_id, Actions.UNIT_MOVE, tile_idx)

    # Attack a unit
    client.do_action(unit_id, Actions.ATTACK, target_unit_id)

    # Found a city
    client.do_action(unit_id, Actions.FOUND_CITY, tile_idx, name="Rome")
"""


class Directions:
    """
    enum direction8 values.  Pass to FreecivClient.move_unit().
    """
    N  = 0   # North (DIR8_NORTH)
    NE = 1   # North-East
    E  = 2   # East
    SE = 3   # South-East
    S  = 4   # South
    SW = 5   # South-West
    W  = 6   # West
    NW = 7   # North-West


class TileKnown:
    """
    Tile visibility returned in freeciv_tile_t.known.
    """
    UNKNOWN       = 0   # never seen
    KNOWN_UNSEEN  = 1   # seen before but currently fogged
    KNOWN_SEEN    = 2   # currently visible


class Actions:
    """
    gen_action enum values.  Pass as action_id to
    FreecivClient.can_do_action() and FreecivClient.do_action().

    Target kind (determines what target_id means):
      tile-targeted : UNIT_MOVE*, FORTIFY*, FOUND_CITY, BASE*, ROAD*,
                      IRRIGATE*, MINE*, PILLAGE*, CLEAN*, PARADROP*,
                      BOMBARD*, NUKE, CULTIVATE*, PLANT*, TRANSFORM_TERRAIN*
      unit-targeted : ATTACK*, CAPTURE_UNITS, SPY_BRIBE_UNIT,
                      SPY_SABOTAGE_UNIT*, HEAL_UNIT*, WIPE_UNITS
      city-targeted : JOIN_CITY, TRADE_ROUTE, MARKETPLACE, HELP_WONDER,
                      SPY_POISON*, SPY_STEAL_TECH*, SPY_INCITE_CITY*,
                      SPY_INVESTIGATE_CITY*, AIRLIFT, CONQUER_CITY_SHRINK*
      self-targeted : HOME_CITY, HOMELESS, UPGRADE_UNIT, CONVERT,
                      DISBAND_UNIT*, ESCAPE, SPY_ESCAPE, GAIN_VETERANCY
    """
    # Espionage — city-targeted
    ESTABLISH_EMBASSY               = 0
    ESTABLISH_EMBASSY_STAY          = 1
    SPY_INVESTIGATE_CITY            = 2
    INV_CITY_SPEND                  = 3
    SPY_POISON                      = 4
    SPY_POISON_ESC                  = 5
    SPY_STEAL_GOLD                  = 6
    SPY_STEAL_GOLD_ESC              = 7
    SPY_SABOTAGE_CITY               = 8
    SPY_SABOTAGE_CITY_ESC           = 9
    SPY_TARGETED_SABOTAGE_CITY      = 10
    SPY_TARGETED_SABOTAGE_CITY_ESC  = 11
    SPY_SABOTAGE_CITY_PRODUCTION    = 12
    SPY_SABOTAGE_CITY_PRODUCTION_ESC = 13
    SPY_STEAL_TECH                  = 14
    SPY_STEAL_TECH_ESC              = 15
    SPY_TARGETED_STEAL_TECH         = 16
    SPY_TARGETED_STEAL_TECH_ESC     = 17
    SPY_INCITE_CITY                 = 18
    SPY_INCITE_CITY_ESC             = 19

    # Trade / city support
    TRADE_ROUTE                     = 20
    MARKETPLACE                     = 21
    HELP_WONDER                     = 22

    # Espionage — unit-targeted
    SPY_BRIBE_UNIT                  = 23
    SPY_BRIBE_STACK                 = 24
    CAPTURE_UNITS                   = 25
    SPY_SABOTAGE_UNIT               = 26
    SPY_SABOTAGE_UNIT_ESC           = 27

    # City building / joining
    FOUND_CITY                      = 28   # tile-targeted
    JOIN_CITY                       = 29   # city-targeted

    # More espionage
    STEAL_MAPS                      = 30
    STEAL_MAPS_ESC                  = 31
    SPY_NUKE                        = 32
    SPY_NUKE_ESC                    = 33

    # Nuclear
    NUKE                            = 34   # tile-targeted
    NUKE_CITY                       = 35
    NUKE_UNITS                      = 36

    # City control
    DESTROY_CITY                    = 37
    EXPEL_UNIT                      = 38

    # Unit management (self-targeted)
    DISBAND_UNIT_RECOVER            = 39
    DISBAND_UNIT                    = 40
    HOME_CITY                       = 41
    HOMELESS                        = 42
    UPGRADE_UNIT                    = 43
    CONVERT                         = 44

    # Movement
    AIRLIFT                         = 45   # city-targeted
    ATTACK                          = 46   # unit-targeted
    ATTACK2                         = 47
    SUICIDE_ATTACK                  = 48
    SUICIDE_ATTACK2                 = 49

    # Strikes
    STRIKE_BUILDING                 = 50
    STRIKE_PRODUCTION               = 51

    # Conquest
    CONQUER_CITY_SHRINK             = 52
    CONQUER_CITY_SHRINK2            = 53
    CONQUER_CITY_SHRINK3            = 54
    CONQUER_CITY_SHRINK4            = 55

    # Bombardment (tile/stack-targeted)
    BOMBARD                         = 56
    BOMBARD2                        = 57
    BOMBARD3                        = 58
    BOMBARD4                        = 59
    BOMBARD_LETHAL                  = 60
    BOMBARD_LETHAL2                 = 61

    # Worker actions (tile-targeted)
    ROAD                            = 62
    ROAD2                           = 63
    IRRIGATE                        = 64
    IRRIGATE2                       = 65
    MINE                            = 66
    MINE2                           = 67
    BASE                            = 68
    BASE2                           = 69
    PILLAGE                         = 70
    PILLAGE2                        = 71

    # Transport
    TRANSPORT_BOARD                 = 72
    TRANSPORT_BOARD2                = 73
    TRANSPORT_BOARD3                = 74
    TRANSPORT_DEBOARD               = 75
    TRANSPORT_EMBARK                = 76
    TRANSPORT_EMBARK2               = 77
    TRANSPORT_EMBARK3               = 78
    TRANSPORT_EMBARK4               = 79
    TRANSPORT_DISEMBARK1            = 80
    TRANSPORT_DISEMBARK2            = 81
    TRANSPORT_DISEMBARK3            = 82
    TRANSPORT_DISEMBARK4            = 83
    TRANSPORT_LOAD                  = 84
    TRANSPORT_LOAD2                 = 85
    TRANSPORT_LOAD3                 = 86
    TRANSPORT_UNLOAD                = 87

    # More espionage
    SPY_SPREAD_PLAGUE               = 88
    SPY_ATTACK                      = 89

    # Extras conquest
    CONQUER_EXTRAS                  = 90
    CONQUER_EXTRAS2                 = 91
    CONQUER_EXTRAS3                 = 92
    CONQUER_EXTRAS4                 = 93

    # Hut exploration
    HUT_ENTER                       = 94
    HUT_ENTER2                      = 95
    HUT_ENTER3                      = 96
    HUT_ENTER4                      = 97
    HUT_FRIGHTEN                    = 98
    HUT_FRIGHTEN2                   = 99
    HUT_FRIGHTEN3                   = 100
    HUT_FRIGHTEN4                   = 101

    # Healing (unit-targeted)
    HEAL_UNIT                       = 102
    HEAL_UNIT2                      = 103

    # Paradrop (tile-targeted)
    PARADROP                        = 104
    PARADROP_CONQUER                = 105
    PARADROP_FRIGHTEN               = 106
    PARADROP_FRIGHTEN_CONQUER       = 107
    PARADROP_ENTER                  = 108
    PARADROP_ENTER_CONQUER          = 109

    # Misc
    WIPE_UNITS                      = 110  # unit-targeted
    SPY_ESCAPE                      = 111

    # Movement (tile-targeted)
    UNIT_MOVE                       = 112
    UNIT_MOVE2                      = 113
    UNIT_MOVE3                      = 114

    # Teleport (tile-targeted)
    TELEPORT                        = 115
    TELEPORT2                       = 116
    TELEPORT3                       = 117
    TELEPORT_CONQUER                = 118
    TELEPORT_FRIGHTEN               = 119
    TELEPORT_FRIGHTEN_CONQUER       = 120
    TELEPORT_ENTER                  = 121
    TELEPORT_ENTER_CONQUER          = 122

    # Terrain modification (tile-targeted)
    CLEAN                           = 123
    CLEAN2                          = 124
    COLLECT_RANSOM                  = 125

    # Fortification (tile-targeted, self)
    FORTIFY                         = 126
    FORTIFY2                        = 127

    # More terrain modification (tile-targeted)
    CULTIVATE                       = 128
    CULTIVATE2                      = 129
    PLANT                           = 130
    PLANT2                          = 131
    TRANSFORM_TERRAIN               = 132
    TRANSFORM_TERRAIN2              = 133

    # Self-targeted
    GAIN_VETERANCY                  = 134
    ESCAPE                          = 135
    CIVIL_WAR                       = 136
    FINISH_UNIT                     = 137
    FINISH_BUILDING                 = 138

    # User-defined
    USER_ACTION1                    = 139
    USER_ACTION2                    = 140
    USER_ACTION3                    = 141
    USER_ACTION4                    = 142

    # Sentinel
    COUNT                           = 143
