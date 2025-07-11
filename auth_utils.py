import os
import json
import typer
from rich.console import Console
from rich.panel import Panel
from google_auth_oauthlib.flow import InstalledAppFlow
import google.auth.transport.requests
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2.credentials import Credentials

console = Console()
# Use firebase_cli_app as the root for config and token files
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'token.json')

ADMIN_EMAILS = [
    'sharmanshu0103@gmail.com'
]

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
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, scopes)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
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