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
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
ADMIN_EMAILS = [
    # Add your admin emails here, or load from env/config
    'sharmanshu0103@gmail.com'
]

TOKEN_PATH = "token.json"

from .firestore_utils import recursive_delete_by_path, delete_collection
from .ui_helpers import show_instructions, show_collections_table, show_documents_table, show_fields_table, show_subcollections_table, explore_data
from .auth_utils import authenticate_user, get_json_path, save_config, load_config, init_firebase
from .firestore_browser import browse_firestore_collection

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
        # Add collection-level CRUD menu
        coll_action_table = Table(title="[bold blue]Collection Actions[/bold blue]", show_header=False)
        coll_action_table.add_column("Key", style="bold magenta", width=4)
        coll_action_table.add_column("Action", style="bold")
        coll_action_table.add_row("A", "Create Collection")
        coll_action_table.add_row("B", "Delete Collection")
        coll_action_table.add_row("C", "Rename Collection")
        coll_action_table.add_row("Q", "[Exit]")
        console.print(coll_action_table)
        console.print("[bold][0][/bold] [Exit]")
        user_input = input("Select a collection by number or choose an action (A, B, ...): ").strip().upper()
        # Try number selection first
        try:
            coll_choice = int(user_input)
            if coll_choice == 0:
                return
            if 1 <= coll_choice <= len(collections):
                coll_ref = collections[coll_choice-1]
                browse_firestore_collection(coll_ref, f"/{coll_ref.id}", db)
                # Refresh collections in case of changes
                collections = list(db.collections())
                continue
            else:
                console.print("Invalid choice.")
                continue
        except ValueError:
            pass  # Not a number, try as action letter
        if user_input == "Q":
            return
        elif user_input == "A":
            # Create Collection (by creating a dummy doc)
            new_coll_name = input("Enter new collection name: ").strip()
            if not new_coll_name:
                console.print("[bold red]No collection name entered.[/bold red]")
                continue
            # Create a dummy doc to initialize
            dummy_doc_id = "_init_"
            db.collection(new_coll_name).document(dummy_doc_id).set({"created": True})
            # Do NOT delete the dummy document, so the collection persists
            console.print(Panel(f"Collection [bold]{new_coll_name}[/bold] created.", title="[bold green]Success[/bold green]", border_style="green"))
            collections = list(db.collections())
        elif user_input == "B":
            # Delete Collection
            del_coll_num = input("Enter collection number to delete: ").strip()
            try:
                del_coll_idx = int(del_coll_num) - 1
                if not (0 <= del_coll_idx < len(collections)):
                    console.print("[bold red]Invalid collection number.[/bold red]")
                    continue
                del_coll_ref = collections[del_coll_idx]
            except ValueError:
                # Try by name
                del_coll_ref = None
                for c in collections:
                    if c.id == del_coll_num:
                        del_coll_ref = c
                        break
                if not del_coll_ref:
                    console.print("[bold red]Invalid collection number or name.[/bold red]")
                    continue
            confirm = input(f"Are you sure you want to delete collection '{del_coll_ref.id}' and all its documents? (y/N): ").strip().lower()
            if confirm != 'y':
                continue
            # Batch delete all docs and subcollections by path
            deleted = delete_collection(del_coll_ref, batch_size=20)
            console.print(Panel(f"Collection [bold]{del_coll_ref.id}[/bold] deleted ({deleted} documents removed, including all subcollections).", title="[bold red]Deleted[/bold red]", border_style="red"))
            collections = list(db.collections())
        elif user_input == "C":
            # Rename Collection (copy all docs, then delete old)
            src_coll_num = input("Enter collection number to rename: ").strip()
            try:
                src_coll_idx = int(src_coll_num) - 1
                if not (0 <= src_coll_idx < len(collections)):
                    console.print("[bold red]Invalid collection number.[/bold red]")
                    continue
                src_coll_ref = collections[src_coll_idx]
            except ValueError:
                # Try by name
                src_coll_ref = None
                for c in collections:
                    if c.id == src_coll_num:
                        src_coll_ref = c
                        break
                if not src_coll_ref:
                    console.print("[bold red]Invalid collection number or name.[/bold red]")
                    continue
            new_coll_name = input("Enter new collection name: ").strip()
            if not new_coll_name:
                console.print("[bold red]No new collection name entered.[/bold red]")
                continue
            if any(c.id == new_coll_name for c in collections):
                console.print(f"[bold red]A collection with name '{new_coll_name}' already exists.[/bold red]")
                continue
            # Copy all docs (and subcollections) to new collection
            for doc in src_coll_ref.stream():
                new_doc_ref = db.collection(new_coll_name).document(doc.id)
                new_doc_ref.set(doc.to_dict())
                # Copy subcollections recursively
                for subcoll in doc.reference.collections():
                    for subdoc in subcoll.stream():
                        def copy_subdoc(src, dst):
                            dst.set(src.get().to_dict())
                            for subsub in src.collections():
                                for subsubdoc in subsub.stream():
                                    copy_subdoc(subsubdoc.reference, dst.collection(subsub.id).document(subsubdoc.id))
                        copy_subdoc(subdoc.reference, new_doc_ref.collection(subcoll.id).document(subdoc.id))
            # Delete old collection
            for doc in src_coll_ref.stream():
                doc.reference.delete()
            console.print(Panel(f"Collection [bold]{src_coll_ref.id}[/bold] renamed to [bold green]{new_coll_name}[/bold green].", title="[bold green]Rename Success[/bold green]", border_style="green"))
            collections = list(db.collections())
        else:
            console.print("Please enter a valid number or action key.")

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

if __name__ == "__main__":
    app() 
