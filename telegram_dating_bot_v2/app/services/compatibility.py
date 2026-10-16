from dataclasses import dataclass


@dataclass(frozen=True)
class Compatibility:
    percent: int
    factors: dict[str, float]
    missing: list[str]

    def explanation(self) -> str:
        names = {
            "goals": "Цели знакомства",
            "interests": "Общие интересы",
            "age": "Возрастные предпочтения",
            "city": "Город",
            "preferences": "Предпочтения по полу",
        }
        lines = [f"{names[k]}: {v:.0%}" for k, v in self.factors.items()]
        if self.missing:
            lines.append("Недостаточно данных: " + ", ".join(names[x] for x in self.missing))
        return "\n".join(lines) + "\nУсловная оценка, не вероятность отношений и не согласие на близость."


def eligible(a: dict, b: dict) -> bool:
    def accepts(x, y):
        return (
            x["min_age"] <= y["age"] <= x["max_age"]
            and (
                x["search_city"].casefold() in {"любой", "все"}
                or x["search_city"].casefold() == y["city"].casefold()
            )
            and (x["search_gender"] == "любой" or x["search_gender"] == y["gender"])
        )

    return a["age"] >= 18 and b["age"] >= 18 and accepts(a, b) and accepts(b, a)


def calculate(a: dict, b: dict, weights: dict[str, float] | None = None) -> Compatibility:
    weights = weights or {"goals": 30, "interests": 25, "age": 20, "city": 15, "preferences": 10}
    ia, ib = set(a["interests"]), set(b["interests"])
    values = {
        "goals": None if "пока не определился" in {a["goal"], b["goal"]} else float(a["goal"] == b["goal"]),
        "interests": len(ia & ib) / len(ia | ib) if ia and ib else None,
        "age": float(a["min_age"] <= b["age"] <= a["max_age"] and b["min_age"] <= a["age"] <= b["max_age"]),
        "city": float(a["city"].casefold() == b["city"].casefold()),
        "preferences": float(
            (a["search_gender"] in {"любой", b["gender"]}) and (b["search_gender"] in {"любой", a["gender"]})
        ),
    }
    known = {k: v for k, v in values.items() if v is not None}
    total = sum(weights[k] for k in known)
    score = round(sum(weights[k] * v for k, v in known.items()) / total * 100) if total else 0
    return Compatibility(score, known, [k for k, v in values.items() if v is None])
