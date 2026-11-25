"""Built-in card bank: 60 everyday objects, 12 per level.

Always available, so a session works without the AI service (SRS 3.4).
"""

# (label, symbol, difficulty, category)
BUILTIN_CARDS = [
    # Level 1: very familiar
    ("ball", "⚽", 1, "home"), ("apple", "🍎", 1, "food"), ("cat", "🐱", 1, "animals"),
    ("dog", "🐶", 1, "animals"), ("car", "🚗", 1, "transport"), ("sun", "☀️", 1, "nature"),
    ("fish", "🐟", 1, "animals"), ("house", "🏠", 1, "home"), ("tree", "🌳", 1, "nature"),
    ("cup", "☕", 1, "home"), ("bird", "🐦", 1, "animals"), ("star", "⭐", 1, "nature"),
    # Level 2: familiar
    ("banana", "🍌", 2, "food"), ("bus", "🚌", 2, "transport"), ("cow", "🐄", 2, "animals"),
    ("flower", "🌸", 2, "nature"), ("shoe", "👟", 2, "clothes"), ("book", "📖", 2, "home"),
    ("moon", "🌙", 2, "nature"), ("egg", "🥚", 2, "food"), ("duck", "🦆", 2, "animals"),
    ("bread", "🍞", 2, "food"), ("milk", "🥛", 2, "food"), ("hat", "👒", 2, "clothes"),
    # Level 3
    ("chair", "🪑", 3, "home"), ("bed", "🛏️", 3, "home"), ("goat", "🐐", 3, "animals"),
    ("chicken", "🐔", 3, "animals"), ("orange", "🍊", 3, "food"), ("carrot", "🥕", 3, "food"),
    ("train", "🚆", 3, "transport"), ("bicycle", "🚲", 3, "transport"), ("clock", "⏰", 3, "home"),
    ("phone", "📱", 3, "home"), ("key", "🔑", 3, "home"), ("rain", "🌧️", 3, "nature"),
    # Level 4
    ("elephant", "🐘", 4, "animals"), ("giraffe", "🦒", 4, "animals"), ("lion", "🦁", 4, "animals"),
    ("mango", "🥭", 4, "food"), ("pineapple", "🍍", 4, "food"), ("umbrella", "☂️", 4, "home"),
    ("scissors", "✂️", 4, "home"), ("pencil", "✏️", 4, "home"), ("boat", "⛵", 4, "transport"),
    ("airplane", "✈️", 4, "transport"), ("spoon", "🥄", 4, "home"), ("butterfly", "🦋", 4, "animals"),
    # Level 5: less common, choices from the same category
    ("zebra", "🦓", 5, "animals"), ("monkey", "🐒", 5, "animals"), ("tortoise", "🐢", 5, "animals"),
    ("rabbit", "🐇", 5, "animals"), ("watermelon", "🍉", 5, "food"), ("grapes", "🍇", 5, "food"),
    ("maize", "🌽", 5, "food"), ("avocado", "🥑", 5, "food"), ("tractor", "🚜", 5, "transport"),
    ("ambulance", "🚑", 5, "transport"), ("motorbike", "🏍️", 5, "transport"), ("socks", "🧦", 5, "clothes"),
]
