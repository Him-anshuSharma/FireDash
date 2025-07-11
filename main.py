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
    print("[bold red]Required packages not found. Please install google-auth-oauthlib, firebase-admin, requests, and rich.[/bold red]")
    raise

app = typer.Typer()
CONFIG_PATH = 'config.json'
ADMIN_EMAILS = [
    # Add your admin emails here, or load from env/config
    'sharmanshu0103@gmail.com'
]

TOKEN_PATH = "token.json"

def show_instructions():
    print("[bold cyan]\n📘 Follow these steps to generate required credentials:\n[/bold cyan]")
    print("[bold]1. Create Google OAuth Client:[/bold]")
    print("   👉 Go to https://console.cloud.google.com/apis/credentials")
    print("   → Create a project (or choose existing one)")
    print("   → Go to 'Credentials' > 'Create Credentials' > 'OAuth client ID'")
    print("   → Choose 'Desktop App'")
    print("   → Download `client_secrets.json`")
    print("\n[bold]2. Get Firebase Admin SDK Key:[/bold]")
    print("   👉 Go to https://console.firebase.google.com/")
    print("   → Select your project > Settings (gear icon) > Service Accounts")
    print("   → Click 'Generate new private key'")
    print("   → Download `serviceAccountKey.json`\n")

def get_json_path(prompt_text: str):
    while True:
        path = input(f"{prompt_text} (absolute or relative path): ").strip()
        # Expand ~ and environment variables
        resolved_path = os.path.expandvars(os.path.expanduser(path))
        print(f"DEBUG: Checking path: '{resolved_path}'")
        if os.path.exists(resolved_path):
            try:
                with open(resolved_path, 'r') as f:
                    json.load(f)
                return resolved_path
            except json.JSONDecodeError:
                print("❌ Not a valid JSON file. Please try again.")
        else:
            print("❌ File not found. Please try again.")

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
        print("❌ Failed to fetch user info.")
        raise typer.Exit()
    userinfo = resp.json()
    email = userinfo.get("email")
    print(f"\n👤 Logged in as: [bold green]{email}[/bold green]")
    if email not in ADMIN_EMAILS:
        print("[bold red]❌ Access denied. Not an admin.[/bold red]")
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

def browse_firestore_collection(collection_ref, path="", db=None):
    docs = list(collection_ref.stream())
    if not docs:
        # If this is the users collection, try to fetch user IDs automatically
        if collection_ref.id == 'users':
            try:
                from firebase_admin import auth
                print("No documents found at this level. Checking for user IDs in Firebase Auth...")
                user_ids = []
                page = auth.list_users()
                while page:
                    for user in page.users:
                        user_ids.append(user.uid)
                    page = page.get_next_page() if hasattr(page, 'get_next_page') else None
                print(f"[DEBUG] User IDs from Firebase Auth: {user_ids}")
                # Print all user document IDs from Firestore
                firestore_user_ids = [doc.id for doc in db.collection('users').stream()]
                print(f"[DEBUG] User document IDs in Firestore: {firestore_user_ids}")
                found_any = False
                user_subcolls = []
                for uid in user_ids:
                    subcolls = list(db.collection('users').document(uid).collections())
                    if subcolls:
                        user_subcolls.append((uid, subcolls))
                        found_any = True
                if found_any:
                    print("Available user IDs with subcollections:")
                    for idx, (uid, subcolls) in enumerate(user_subcolls, 1):
                        print(f"{idx}. {uid} (subcollections: {', '.join([s.id for s in subcolls])})")
                    print("0. [Go back]")
                    while True:
                        try:
                            choice = int(input("Select a user by number (or 0 to go back): "))
                        except ValueError:
                            print("Please enter a valid number.")
                            continue
                        if choice == 0:
                            return
                        if 1 <= choice <= len(user_subcolls):
                            user_id, subcolls = user_subcolls[choice-1]
                            print(f"Subcollections for user {user_id}:")
                            for i, subcoll in enumerate(subcolls, 1):
                                print(f"{i}. {subcoll.id}")
                            print("0. [Go back]")
                            try:
                                sub_choice = int(input("Select a subcollection by number (or 0 to go back): "))
                            except ValueError:
                                print("Please enter a valid number.")
                                continue
                            if sub_choice == 0:
                                continue
                            if 1 <= sub_choice <= len(subcolls):
                                subcoll_ref = subcolls[sub_choice-1]
                                browse_firestore_collection(subcoll_ref, path + f"/users/{user_id}/{subcoll_ref.id}", db)
                            else:
                                print("Invalid choice.")
                        else:
                            print("Invalid choice.")
                    return
                else:
                    # No user has subcollections, ask the user if they're sure
                    user_input = input("No user documents with subcollections found. Are you sure there are documents in this collection? (y/n): ").strip().lower()
                    if user_input != 'y':
                        return
                    print("[!] If you do have documents, but they have no fields (only subcollections), Firestore will not return them in queries.\nHow to fix: Add at least one field (e.g., dummy: true) to each document in the Firebase Console.")
                    return
            except Exception as e:
                print(f"[!] Error fetching user IDs: {e}")
                return
        else:
            print("No documents found at this level.")
            user_input = input("Are there documents present in this collection? (y/n): ").strip().lower()
            if user_input == 'y':
                doc_id = input("Enter a document ID to fetch directly (or leave blank to go back): ").strip()
                if doc_id:
                    doc_ref = collection_ref.document(doc_id)
                    doc = doc_ref.get()
                    if doc.exists:
                        print(f"Document {doc_id} data: {doc.to_dict()}")
                        # List subcollections
                        subcolls = list(doc_ref.collections())
                        if subcolls:
                            print("Subcollections:")
                            for i, subcoll in enumerate(subcolls, 1):
                                print(f"{i}. {subcoll.id}")
                            print("0. [Go back]")
                            try:
                                sub_choice = int(input("Select a subcollection by number (or 0 to go back): "))
                            except ValueError:
                                print("Please enter a valid number.")
                                return
                            if sub_choice == 0:
                                return
                            if 1 <= sub_choice <= len(subcolls):
                                subcoll_ref = subcolls[sub_choice-1]
                                browse_firestore_collection(subcoll_ref, path + f"/{doc_id}/{subcoll_ref.id}", db)
                        else:
                            print("No subcollections found for this document.")
                    else:
                        print("Document not found.")
                return
            else:
                print("[!] If you do have documents, but they have no fields (only subcollections), Firestore will not return them in queries.\nHow to fix: Add at least one field (e.g., dummy: true) to each document in the Firebase Console.")
            return
    while True:
        print(f"\nDocuments at {path or '/'}:")
        for idx, doc in enumerate(docs, 1):
            print(f"{idx}. {doc.id}")
        print("0. [Go back]")
        try:
            doc_choice = int(input("Select a document by number (or 0 to go back): "))
        except ValueError:
            print("Please enter a valid number.")
            continue
        if doc_choice == 0:
            return
        if 1 <= doc_choice <= len(docs):
            doc = docs[doc_choice-1]
            doc_ref = collection_ref.document(doc.id)
            data = doc.to_dict()
            # List subcollections and fields
            subcolls = list(doc_ref.collections())
            print(f"\nDocument: {doc.id}")
            print("Fields:")
            field_keys = list(data.keys()) if data else []
            for i, k in enumerate(field_keys, 1):
                print(f"  {i}. {k}")
            sub_offset = len(field_keys)
            if subcolls:
                print("Subcollections:")
                for i, subcoll in enumerate(subcolls, 1):
                    print(f"  {sub_offset + i}. {subcoll.id}")
            print("0. [Go back]")
            try:
                choice = int(input("Select a field to view or a subcollection to enter (or 0 to go back): "))
            except ValueError:
                print("Please enter a valid number.")
                continue
            if choice == 0:
                continue
            if 1 <= choice <= len(field_keys):
                k = field_keys[choice-1]
                v = data[k]
                explore_data(v, path + f"/{k}")
            elif subcolls and (len(field_keys) < choice <= len(field_keys) + len(subcolls)):
                subcoll_idx = choice - len(field_keys) - 1
                subcoll_ref = subcolls[subcoll_idx]
                browse_firestore_collection(subcoll_ref, path + f"/{doc.id}/{subcoll_ref.id}", db)
            else:
                print("Invalid choice.")
        else:
            print("Invalid choice.")

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
            print(f"\nKeys at {path}:")
            for i, k in enumerate(keys, 1):
                print(f"  {i}. {k}")
            print("0. [Go back]")
            try:
                choice = int(input("Select a key to view (or 0 to go back): "))
            except ValueError:
                print("Please enter a valid number.")
                continue
            if choice == 0:
                return
            if 1 <= choice <= len(keys):
                k = keys[choice-1]
                explore_data(value[k], path + f"/{k}")
            else:
                print("Invalid choice.")
    elif isinstance(value, list):
        import re
        path_parts = [p for p in path.split("/") if p]
        parent = path_parts[-1] if path_parts else path
        parent = re.sub(r"\[.*\]$", "", parent)  # Remove trailing [index] if present
        doc_name = path_parts[-2] if len(path_parts) > 1 else None
        print(f"\n{parent} ({len(value)} items):")
        while True:
            for i in range(1, len(value)+1):
                if doc_name and parent.lower() == doc_name.lower():
                    print(f"  [{i}] * {i}")
                else:
                    print(f"  [{i}] * {parent.upper()}-{i}")
            print("0. [Go back]")
            try:
                choice = int(input("Select an item to view (or 0 to go back): "))
            except ValueError:
                print("Please enter a valid number.")
                continue
            if choice == 0:
                return
            if 1 <= choice <= len(value):
                explore_data(value[choice-1], path + f"/[{choice-1}]")
            else:
                print("Invalid choice.")
    else:
        print(f"\nValue at {path}: {value}")
        input("Press Enter to continue...")

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
    print("DEBUG: Authenticated user, initializing Firestore...")
    db = init_firebase(admin_path)
    print("DEBUG: Firestore initialized.")
    # List all collections
    collections = list(db.collections())
    if not collections:
        print("No collections found in Firestore.")
        return
    while True:
        print("Available Firestore collections:")
        for idx, coll in enumerate(collections, 1):
            print(f"  {idx}. {coll.id}")
        print("0. [Exit]")
        try:
            coll_choice = int(input("Select a collection by number (or 0 to exit): "))
        except ValueError:
            print("Please enter a valid number.")
            continue
        if coll_choice == 0:
            return
        if 1 <= coll_choice <= len(collections):
            coll_ref = collections[coll_choice-1]
            browse_firestore_collection(coll_ref, f"/{coll_ref.id}", db)
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    app() 