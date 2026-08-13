"""Site-wide rules for Twitch categories that must never enter game rankings."""


# Block by Twitch ID as the primary guard because category names can change.
EXCLUDED_TWITCH_CATEGORY_IDS = frozenset({
    "29452",  # Virtual Casino
})


# Exact normalized-name fallback for categories without a reliable Twitch ID.
# Matching stays exact so legitimate games that merely contain these words are
# not removed accidentally.
EXCLUDED_TWITCH_CATEGORY_TITLES = frozenset({
    "Virtual Casino",
    "Slots",
    "Casino",
    "Gambling",
})
