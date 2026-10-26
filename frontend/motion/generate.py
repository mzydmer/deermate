"""Original DeerMate greeting: transparent, one stroke gesture and one blink."""

import json
from pathlib import Path

COLOR = [0.208, 0.4, 0.31, 1]


def static(value):
    return {"a": 0, "k": value}


def key(time, value):
    return {"t": time, "s": value, "o": {"x": 0.2, "y": 0.75}, "i": {"x": 0.34, "y": 0.94}}


def path(points, closed=False, incoming=None, outgoing=None):
    return {
        "ty": "sh",
        "ks": static(
            {
                "v": points,
                "c": closed,
                "i": incoming or [[0, 0]] * len(points),
                "o": outgoing or [[0, 0]] * len(points),
            }
        ),
    }


def stroke(width=4):
    return {
        "ty": "st",
        "c": {**static(COLOR), "sid": "accentColor"},
        "o": static(100),
        "w": static(width),
        "lc": 2,
        "lj": 2,
    }


def layer(name, shapes):
    return {
        "ty": 4,
        "nm": name,
        "ip": 0,
        "op": 90,
        "st": 0,
        "sr": 1,
        "ks": {
            "o": static(100),
            "r": static(0),
            "p": static([0, 0, 0]),
            "a": static([0, 0, 0]),
            "s": static([100, 100, 100]),
        },
        "shapes": shapes,
    }


def main():
    antlers = []
    for sign in (-1, 1):

        def point(x, y, direction=sign):
            return [64 + direction * x, y]

        for index, points in enumerate(
            [[(18, 51), (27, 37), (27, 20)], [(27, 36), (40, 29)], [(27, 27), (18, 18)]]
        ):
            begin, end = [(0, 15), (14, 23), (18, 27)][index]
            branch = layer(
                "Antler · connected stroke",
                [
                    path([point(x, y) for x, y in points]),
                    stroke(),
                    {
                        "ty": "tm",
                        "s": static(0),
                        "e": {
                            "a": 1,
                            "k": [key(begin, [12 if index == 0 else 0]), key(end, [100])],
                        },
                        "o": static(0),
                        "m": 1,
                    },
                ],
            )
            if index:
                branch["ks"]["o"] = {
                    "a": 1,
                    "k": [key(0, [0]), key(begin, [0]), key(begin + 1, [100])],
                }
            antlers.append(branch)
    face = [
        path([[44, 54], [30, 46], [35, 66], [45, 70]]),
        path([[84, 54], [98, 46], [93, 66], [83, 70]]),
        path(
            [[45, 54], [83, 54], [81, 84], [64, 107], [47, 84]],
            True,
            incoming=[[0, 0], [-14, -9], [0, 0], [9, -3], [0, 12]],
            outgoing=[[14, -9], [0, 0], [-2, 12], [-9, -3], [0, 0]],
        ),
        path([[60, 91], [64, 95], [68, 91]]),
        stroke(),
    ]
    eyes = [
        {
            "ty": "el",
            "p": static([x, 75]),
            "s": {
                "a": 1,
                "k": [
                    key(0, [5, 5]),
                    key(43, [5, 5]),
                    key(45, [5, 1]),
                    key(48, [5, 5]),
                    key(89, [5, 5]),
                ],
            },
        }
        for x in (55, 73)
    ]
    eyes += [{"ty": "fl", "c": {**static(COLOR), "sid": "accentColor"}, "o": static(100), "r": 1}]
    animation = {
        "v": "5.12.2",
        "fr": 30,
        "ip": 0,
        "op": 90,
        "w": 128,
        "h": 128,
        "nm": "DeerMate — a small hello",
        "ddd": 0,
        "assets": [],
        "slots": {"accentColor": {"p": static(COLOR)}},
        "layers": [
            layer("Eyes · one quiet blink", eyes),
            *antlers,
            layer("Face · steady anchor", face),
        ],
    }
    directory = Path(__file__).parent / "public/projects/deermate/scene-1"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "lottie.json").write_text(json.dumps(animation, indent=2) + "\n")
    (directory / "controls.json").write_text(
        json.dumps({"controls": [{"sid": "accentColor", "label": "Brand accent"}]}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
