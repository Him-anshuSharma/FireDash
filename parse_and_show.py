import json
from rich.tree import Tree
from rich.console import Console

def print_nested(d, indent=2):
    # Deprecated: Use print_rich_tree instead
    pass

def print_rich_tree(data, label="root"):
    console = Console()
    def add_to_tree(tree, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                branch = tree.add(f"[bold]{k}[/bold]")
                add_to_tree(branch, v)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                branch = tree.add(f"[cyan]- [{i}]")
                add_to_tree(branch, item)
        else:
            tree.add(f"[green]{obj}")
    root = Tree(f"[bold magenta]{label}")
    add_to_tree(root, data)
    console.print(root)