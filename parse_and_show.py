import json


def print_nested(d, indent=2):
    if isinstance(d, dict):
        for k, v in d.items():
            print(' ' * indent + f"{k}:")
            print_nested(v, indent + 2)
    elif isinstance(d, list):
        for i, item in enumerate(d):
            print(' ' * indent + f"- [{i}]")
            print_nested(item, indent + 2)
    else:
        print(' ' * indent + str(d))