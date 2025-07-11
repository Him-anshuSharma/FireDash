from rich.table import Table
from rich.console import Console
from rich.panel import Panel
console = Console()

def show_instructions():
    panel = Panel.fit(
        "[bold cyan]\n📘 Follow these steps to generate required credentials:\n[/bold cyan]\n"
        "[bold]1. Create Google OAuth Client:[/bold]\n"
        "   👉 Go to https://console.cloud.google.com/apis/credentials\n"
        "   → Create a project (or choose existing one)\n"
        "   → Go to 'Credentials' > 'Create Credentials' > 'OAuth client ID'\n"
        "   → Choose 'Desktop App'\n"
        "   → Download `client_secrets.json`\n\n"
        "[bold]2. Get Firebase Admin SDK Key:[/bold]\n"
        "   👉 Go to https://console.firebase.google.com/\n"
        "   → Select your project > Settings (gear icon) > Service Accounts\n"
        "   → Click 'Generate new private key'\n"
        "   → Download `serviceAccountKey.json`\n",
        title="Setup Instructions",
        border_style="cyan"
    )
    console.print(panel)

def show_collections_table(collections):
    table = Table(title="[bold blue]Available Firestore Collections[/bold blue]", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Collection ID", style="bold yellow")
    for idx, coll in enumerate(collections, 1):
        table.add_row(str(idx), coll.id if hasattr(coll, 'id') else str(coll))
    console.print(table)

def show_documents_table(docs):
    table = Table(title="[bold green]Documents[/bold green]", show_header=True, header_style="bold green")
    table.add_column("#", style="dim", width=4)
    table.add_column("Document ID", style="bold yellow")
    for idx, doc in enumerate(docs, 1):
        table.add_row(str(idx), doc.id if hasattr(doc, 'id') else str(doc))
    console.print(table)

def show_fields_table(data):
    table = Table(title="[bold cyan]Fields[/bold cyan]", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Field Name", style="bold")
    table.add_column("Value", style="yellow")
    if data:
        for idx, (k, v) in enumerate(data.items(), 1):
            if isinstance(v, (str, int, float, bool)) or v is None:
                table.add_row(str(idx), str(k), str(v))
            else:
                table.add_row(str(idx), str(k), "[View]")
    else:
        table.add_row("-", "(none)", "")
    console.print(table)

def show_subcollections_table(subcolls):
    table = Table(title="[bold blue]Subcollections[/bold blue]", show_header=True, header_style="bold blue")
    table.add_column("#", style="dim", width=4)
    table.add_column("Subcollection Name", style="bold")
    if subcolls:
        for idx, subcoll in enumerate(subcolls, 1):
            table.add_row(str(idx), subcoll.id if hasattr(subcoll, 'id') else str(subcoll))
    else:
        table.add_row("-", "(none)")
    console.print(table)

def explore_data(value, path="root"):
    import json
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            value = parsed
        except Exception:
            pass
    if isinstance(value, dict):
        keys = list(value.keys())
        while True:
            table = Table(title=f"[bold magenta]Keys at {path}[/bold magenta]", show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim", width=4)
            table.add_column("Key", style="bold")
            for i, k in enumerate(keys, 1):
                table.add_row(str(i), str(k))
            table.add_row("0", "[Go back]")
            console.print(table)
            try:
                choice = int(input("Select a key to view (or 0 to go back): "))
            except ValueError:
                console.print("Please enter a valid number.")
                continue
            if choice == 0:
                return
            if 1 <= choice <= len(keys):
                k = keys[choice-1]
                explore_data(value[k], path + f"/{k}")
            else:
                console.print("Invalid choice.")
    elif isinstance(value, list):
        import re
        path_parts = [p for p in path.split("/") if p]
        parent = path_parts[-1] if path_parts else path
        parent = re.sub(r"\[.*\]$", "", parent)  # Remove trailing [index] if present
        doc_name = path_parts[-2] if len(path_parts) > 1 else None
        table = Table(title=f"[bold magenta]{parent} ({len(value)} items)[/bold magenta]", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Label", style="bold")
        for i in range(1, len(value)+1):
            label = f"* {parent.upper()}-{i}" if not (doc_name and parent.lower() == doc_name.lower()) else f"* {i}"
            table.add_row(str(i), label)
        table.add_row("0", "[Go back]")
        console.print(table)
        try:
            choice = int(input("Select an item to view (or 0 to go back): "))
        except ValueError:
            console.print("Please enter a valid number.")
            return
        if choice == 0:
            return
        if 1 <= choice <= len(value):
            explore_data(value[choice-1], path + f"/[{choice-1}]")
        else:
            console.print("Invalid choice.")
    else:
        panel = Panel(f"[bold]{path}[/bold]: [green]{value}", title="Value", border_style="green")
        console.print(panel)
        input("Press Enter to continue...") 