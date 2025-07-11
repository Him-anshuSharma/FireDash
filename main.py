import os
import json
import typer
from rich import print
import warnings
warnings.filterwarnings("ignore", message="Scope has changed*")

# If you use Google/Firebase SDKs, import them here
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    import google.auth.transport.requests
    import google.oauth2.id_token
    import requests
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.oauth2.credentials import Credentials
except ImportError:
    console.print("[bold red]Required packages not found. Please install google-auth-oauthlib, firebase-admin, requests, and rich.[/bold red]")
    raise

from rich.table import Table
from rich.console import Console
from rich.panel import Panel
console = Console()

app = typer.Typer()
CONFIG_PATH = 'config.json'
ADMIN_EMAILS = [
    # Add your admin emails here, or load from env/config
    'sharmanshu0103@gmail.com'
]

TOKEN_PATH = "token.json"

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

def get_json_path(prompt_text: str):
    while True:
        path = input(f"{prompt_text} (absolute or relative path): ").strip()
        # Expand ~ and environment variables
        resolved_path = os.path.expandvars(os.path.expanduser(path))
        console.print(f"[dim]DEBUG: Checking path: '{resolved_path}'[/dim]")
        if os.path.exists(resolved_path):
            try:
                with open(resolved_path, 'r') as f:
                    json.load(f)
                return resolved_path
            except json.JSONDecodeError:
                console.print("[bold red]❌ Not a valid JSON file. Please try again.[/bold red]")
        else:
            console.print("[bold red]❌ File not found. Please try again.[/bold red]")

def save_config(oauth_path, admin_key_path):
    with open(CONFIG_PATH, 'w') as f:
        json.dump({
            'client_secrets': oauth_path,
            'service_account': admin_key_path
        }, f)

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}

def authenticate_user(client_secrets_path):
    creds = None
    scopes = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]
    # Try to load existing credentials
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes)
    # If no valid credentials, do the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, scopes)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    # Use the access token to get user info
    headers = {"Authorization": f"Bearer {creds.token}"}
    resp = requests.get("https://openidconnect.googleapis.com/v1/userinfo", headers=headers)
    if resp.status_code != 200:
        console.print("[bold red]❌ Failed to fetch user info.[/bold red]")
        raise typer.Exit()
    userinfo = resp.json()
    email = userinfo.get("email")
    console.print(f"\n👤 Logged in as: [bold green]{email}[/bold green]")
    if email not in ADMIN_EMAILS:
        console.print("[bold red]❌ Access denied. Not an admin.[/bold red]")
        raise typer.Exit()
    return email

def init_firebase(service_account_path):
    cred = credentials.Certificate(service_account_path)
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred)
    return firestore.client()

def print_nested(d, indent=2):
    # Deprecated: Use rich tree instead
    pass

def browse_firestore_collection(collection_ref, path="", db=None):
    docs = list(collection_ref.stream())
    if not docs:
        # If this is the users collection, try to fetch user IDs automatically
        if collection_ref.id == 'users':
            try:
                from firebase_admin import auth
                console.print("No documents found at this level. Checking for user IDs in Firebase Auth...")
                user_ids = []
                page = auth.list_users()
                while page:
                    for user in page.users:
                        user_ids.append(user.uid)
                    page = page.get_next_page() if hasattr(page, 'get_next_page') else None
                console.print(f"[DEBUG] User IDs from Firebase Auth: {user_ids}")
                # Print all user document IDs from Firestore
                firestore_user_ids = [doc.id for doc in db.collection('users').stream()]
                console.print(f"[DEBUG] User document IDs in Firestore: {firestore_user_ids}")
                found_any = False
                user_subcolls = []
                for uid in user_ids:
                    subcolls = list(db.collection('users').document(uid).collections())
                    if subcolls:
                        user_subcolls.append((uid, subcolls))
                        found_any = True
                if found_any:
                    console.print("Available user IDs with subcollections:")
                    for idx, (uid, subcolls) in enumerate(user_subcolls, 1):
                        console.print(f"{idx}. {uid} (subcollections: {', '.join([s.id for s in subcolls])})")
                    console.print("0. [Go back]")
                    while True:
                        try:
                            choice = int(input("Select a user by number (or 0 to go back): "))
                        except ValueError:
                            console.print("Please enter a valid number.")
                            continue
                        if choice == 0:
                            return
                        if 1 <= choice <= len(user_subcolls):
                            user_id, subcolls = user_subcolls[choice-1]
                            console.print(f"Subcollections for user {user_id}:")
                            for i, subcoll in enumerate(subcolls, 1):
                                console.print(f"{i}. {subcoll.id}")
                            console.print("0. [Go back]")
                            try:
                                sub_choice = int(input("Select a subcollection by number (or 0 to go back): "))
                            except ValueError:
                                console.print("Please enter a valid number.")
                                continue
                            if sub_choice == 0:
                                continue
                            if 1 <= sub_choice <= len(subcolls):
                                subcoll_ref = subcolls[sub_choice-1]
                                browse_firestore_collection(subcoll_ref, path + f"/users/{user_id}/{subcoll_ref.id}", db)
                            else:
                                console.print("Invalid choice.")
                        else:
                            console.print("Invalid choice.")
                    return
                else:
                    # No user has subcollections, ask the user if they're sure
                    user_input = input("No user documents with subcollections found. Are you sure there are documents in this collection? (y/n): ").strip().lower()
                    if user_input != 'y':
                        return
                    console.print("[!] If you do have documents, but they have no fields (only subcollections), Firestore will not return them in queries.\nHow to fix: Add at least one field (e.g., dummy: true) to each document in the Firebase Console.")
                    return
            except Exception as e:
                console.print(f"[!] Error fetching user IDs: {e}")
                return
        else:
            console.print("No documents found at this level.")
            user_input = input("Are there documents present in this collection? (y/n): ").strip().lower()
            if user_input == 'y':
                doc_id = input("Enter a document ID to fetch directly (or leave blank to go back): ").strip()
                if doc_id:
                    doc_ref = collection_ref.document(doc_id)
                    doc = doc_ref.get()
                    if doc.exists:
                        console.print(f"Document {doc_id} data: {doc.to_dict()}")
                        # List subcollections
                        subcolls = list(doc_ref.collections())
                        if subcolls:
                            console.print("Subcollections:")
                            for i, subcoll in enumerate(subcolls, 1):
                                console.print(f"{i}. {subcoll.id}")
                            console.print("0. [Go back]")
                            try:
                                sub_choice = int(input("Select a subcollection by number (or 0 to go back): "))
                            except ValueError:
                                console.print("Please enter a valid number.")
                                return
                            if sub_choice == 0:
                                return
                            if 1 <= sub_choice <= len(subcolls):
                                subcoll_ref = subcolls[sub_choice-1]
                                browse_firestore_collection(subcoll_ref, path + f"/{doc_id}/{subcoll_ref.id}", db)
                        else:
                            console.print("No subcollections found for this document.")
                    else:
                        console.print("Document not found.")
                return
            else:
                console.print("[!] If you do have documents, but they have no fields (only subcollections), Firestore will not return them in queries.\nHow to fix: Add at least one field (e.g., dummy: true) to each document in the Firebase Console.")
            return
    while True:
        # Replace print-based document listing with rich table
        show_documents_table(docs)
        console.print("[bold][0][/bold] Go back")
        try:
            doc_choice = int(input("Select a document by number (or 0 to go back): "))
        except ValueError:
            console.print("Please enter a valid number.")
            continue
        if doc_choice == 0:
            return
        if 1 <= doc_choice <= len(docs):
            doc = docs[doc_choice-1]
            doc_ref = collection_ref.document(doc.id)
            data = doc.to_dict()
            # List subcollections and fields
            subcolls = list(doc_ref.collections())
            # Use rich tables for document details
            panel = Panel(f"[bold yellow]Document:[/bold yellow] {doc.id}", title="Document Details", border_style="yellow")
            console.print(panel)
            show_fields_table(data)
            show_subcollections_table(subcolls)
            # Document action menu
            action_table = Table(title="[bold blue]Document Actions[/bold blue]", show_header=False)
            action_table.add_column("Key", style="bold magenta", width=4)
            action_table.add_column("Action", style="bold")
            action_table.add_row("A", "View/Edit Fields or Subcollections")
            action_table.add_row("B", "Rename (copy to new ID)")
            action_table.add_row("Q", "[Go back]")
            console.print(action_table)
            action_choice = input("Select an action: ").strip().upper()
            if action_choice == "Q":
                continue
            elif action_choice == "A":
                # Existing field/subcollection navigation
                field_keys = list(data.keys()) if data else []
                show_fields_table(data)
                show_subcollections_table(subcolls)
                console.print("[bold][0][/bold] Go back")
                try:
                    choice = int(input("Select a field to view or a subcollection to enter (or 0 to go back): "))
                except ValueError:
                    console.print("Please enter a valid number.")
                    continue
                if choice == 0:
                    continue
                if 1 <= choice <= len(field_keys):
                    k = field_keys[choice-1]
                    v = data[k]
                    if is_basic_type(v):
                        panel = Panel(f"[bold]{k}[/bold]: [green]{v}", title="Field Value", border_style="green")
                        console.print(panel)
                        input("Press Enter to continue...")
                    else:
                        explore_data(v, path + f"/{k}")
                elif subcolls and (len(field_keys) < choice <= len(field_keys) + len(subcolls)):
                    subcoll_idx = choice - len(field_keys) - 1
                    subcoll_ref = subcolls[subcoll_idx]
                    browse_firestore_collection(subcoll_ref, path + f"/{doc.id}/{subcoll_ref.id}", db)
                else:
                    console.print("Invalid choice.")
            elif action_choice == "B":
                # Rename (copy to new ID)
                new_id = input("Enter new document ID: ").strip()
                if not new_id:
                    console.print("[bold red]No ID entered. Rename cancelled.[/bold red]")
                    continue
                new_doc_ref = collection_ref.document(new_id)
                if new_doc_ref.get().exists:
                    console.print(f"[bold red]A document with ID '{new_id}' already exists.[/bold red]")
                    continue
                try:
                    rename_document_with_subcollections(doc_ref, new_doc_ref)
                    console.print(Panel(f"Document [bold]{doc.id}[/bold] successfully copied to [bold green]{new_id}[/bold green] (including all subcollections).", title="[bold green]Rename Success[/bold green]", border_style="green"))
                    delete_original = input("Delete the original document? (y/N): ").strip().lower()
                    if delete_original == 'y':
                        doc_ref.delete()
                        console.print(Panel(f"Original document [bold]{doc.id}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                except Exception as e:
                    console.print(Panel(f"[bold red]Rename failed:[/bold red] {e}", title="[bold red]Error[/bold red]", border_style="red"))
            else:
                console.print("Invalid choice.")
        else:
            console.print("Invalid choice.")

def is_basic_type(val):
    return isinstance(val, (str, int, float, bool)) or val is None

def summarize_dict_item(item):
    if not isinstance(item, dict):
        return str(item)
    if 'title' in item:
        return f"title: {item['title']}" + (f" (timestamp: {item.get('timestamp')})" if 'timestamp' in item else "")
    if 'timestamp' in item:
        return f"timestamp: {item['timestamp']}"
    if 'content' in item:
        content = item['content']
        if isinstance(content, str):
            return f"content: {content[:30]}..."
    if item:
        k, v = next(iter(item.items()))
        return f"{k}: {str(v)[:30]}..."
    return "[dict]"

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

def rename_document_with_subcollections(doc_ref, new_doc_ref):
    # Copy fields
    data = doc_ref.get().to_dict()
    if data:
        new_doc_ref.set(data)
    else:
        new_doc_ref.set({}, merge=True)
    # Copy subcollections recursively
    for subcoll in doc_ref.collections():
        for subdoc in subcoll.stream():
            rename_document_with_subcollections(
                subdoc.reference,
                new_doc_ref.collection(subcoll.id).document(subdoc.id)
            )

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
            if is_basic_type(v):
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

# In setup_and_run, pass db to the browser
@app.command()
def setup_and_run():
    """
    One-time setup + interactive Firestore browser
    """
    config = load_config()
    if not config:
        show_instructions()
        oauth_path = get_json_path("\n📂 Upload your [Google OAuth] client_secrets.json")
        admin_path = get_json_path("📂 Upload your [Firebase Admin SDK] serviceAccountKey.json")
        save_config(oauth_path, admin_path)
    else:
        oauth_path = config['client_secrets']
        admin_path = config['service_account']
    authenticate_user(oauth_path)
    console.print("DEBUG: Authenticated user, initializing Firestore...")
    db = init_firebase(admin_path)
    console.print("DEBUG: Firestore initialized.")
    # List all collections
    collections = list(db.collections())
    if not collections:
        console.print("No collections found in Firestore.")
        return
    while True:
        show_collections_table(collections)
        console.print("0. [Exit]")
        try:
            coll_choice = int(input("Select a collection by number (or 0 to exit): "))
        except ValueError:
            console.print("Please enter a valid number.")
            continue
        if coll_choice == 0:
            return
        if 1 <= coll_choice <= len(collections):
            coll_ref = collections[coll_choice-1]
            browse_firestore_collection(coll_ref, f"/{coll_ref.id}", db)
        else:
            console.print("Invalid choice.")

if __name__ == "__main__":
    app() 