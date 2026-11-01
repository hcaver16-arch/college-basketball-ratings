"""Presentation-only projected seed lines and site labels for regional brackets."""
from tournament_brackets import _seeding_order

def region_seed_positions():
    return _seeding_order(16)

def seeded_label(team, region_game_index, side, teams):
    """Use seeded position in the illustrative region, not national overall order."""
    if team not in teams:
        return str(team)
    positions=region_seed_positions()
    seed=positions[2*region_game_index + (0 if side==0 else 1)]
    return f"({seed}) {team}"

def region_site(region_name, league):
    if league=="Men's":
        from tournament_locations_v145 import MEN_REGIONS
        if region_name in MEN_REGIONS:
            city,venue,dates=MEN_REGIONS[region_name]
            return f"{city} · {venue} · {dates}", "Official regional host; team placement hypothetical"
    return "Regional site not yet assigned to this illustrative region", "Women's regional host cities are Philadelphia and Las Vegas; this region does not have a verified assignment"

def game_site_label(round_index, region_name, league):
    """Label each game with its actual round-specific venue certainty."""
    if round_index < 2:
        return "First-weekend site: TBD"
    if league == "Men's":
        from tournament_locations_v145 import MEN_REGIONS
        if region_name in MEN_REGIONS:
            city,venue,_ = MEN_REGIONS[region_name]
            return f"Regional site: {city} · {venue}"
    return "Regional site: not assigned to this region"
