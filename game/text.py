"""Text helpers shared by the pygame-free campaign and the screens."""


def plural(n: int, one: str, few: str, many: str) -> str:
    """Russian plural: 1 ЛОГОВО, 2 ЛОГОВА, 5 ЛОГОВ."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many
