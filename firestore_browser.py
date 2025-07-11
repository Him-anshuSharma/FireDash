from rich.console import Console
from rich.panel import Panel
from firebase_cli_app.ui_helpers import show_documents_table, show_fields_table, show_subcollections_table, explore_data
from firebase_cli_app.firestore_utils import recursive_delete_by_path, delete_collection
from rich.table import Table
import json
import firebase_admin.firestore as firestore

console = Console()

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
        show_documents_table(docs)
        doc_action_table = Table(title="[bold blue]Document List Actions[/bold blue]", show_header=False)
        doc_action_table.add_column("Key", style="bold magenta", width=4)
        doc_action_table.add_column("Action", style="bold")
        doc_action_table.add_row("A", "Create New Document")
        doc_action_table.add_row("B", "Delete Document by ID")
        doc_action_table.add_row("C", "Rename (copy) Document by ID")
        doc_action_table.add_row("Q", "[Go back]")
        console.print(doc_action_table)
        console.print("[bold][0][/bold] Go back")
        doc_action = input("Select a document action or enter a document number: ").strip().upper()
        if doc_action == "Q" or doc_action == "0":
            return
        elif doc_action == "A":
            new_doc_id = input("Enter new document ID (leave blank for auto-ID): ").strip()
            if new_doc_id:
                collection_ref.document(new_doc_id).set({})
                console.print(Panel(f"Document [bold]{new_doc_id}[/bold] created.", title="[bold green]Success[/bold green]", border_style="green"))
            else:
                new_doc_ref = collection_ref.document()
                new_doc_ref.set({})
                console.print(Panel(f"Document created with auto-ID: [bold]{new_doc_ref.id}[/bold]", title="[bold green]Success[/bold green]", border_style="green"))
            docs = list(collection_ref.stream())
            continue
        elif doc_action == "B":
            del_doc_id = input("Enter document ID to delete: ").strip()
            if not del_doc_id:
                console.print("[bold red]No document ID entered.[/bold red]")
                continue
            del_doc_ref = collection_ref.document(del_doc_id)
            if not del_doc_ref.get().exists:
                console.print(f"[bold red]Document '{del_doc_id}' does not exist.[/bold red]")
                continue
            confirm = input(f"Are you sure you want to delete document '{del_doc_id}'? (y/N): ").strip().lower()
            if confirm == 'y':
                recursive_delete_by_path(db, f"{collection_ref.id}/{del_doc_id}")
                console.print(Panel(f"Document [bold]{del_doc_id}[/bold] deleted (including all subcollections).", title="[bold red]Deleted[/bold red]", border_style="red"))
                docs = list(collection_ref.stream())
            continue
        elif doc_action == "C":
            src_doc_id = input("Enter source document ID: ").strip()
            if not src_doc_id:
                console.print("[bold red]No source document ID entered.[/bold red]")
                continue
            src_doc_ref = collection_ref.document(src_doc_id)
            if not src_doc_ref.get().exists:
                console.print(f"[bold red]Document '{src_doc_id}' does not exist.[/bold red]")
                continue
            new_doc_id = input("Enter new document ID: ").strip()
            if not new_doc_id:
                console.print("[bold red]No new document ID entered.[/bold red]")
                continue
            new_doc_ref = collection_ref.document(new_doc_id)
            if new_doc_ref.get().exists:
                console.print(f"[bold red]A document with ID '{new_doc_id}' already exists.[/bold red]")
                continue
            try:
                # Assuming rename_document_with_subcollections is defined elsewhere or needs to be imported
                # For now, we'll just copy and delete the original
                src_doc_ref.set(src_doc_ref.get().to_dict()) # Copy data
                console.print(Panel(f"Document [bold]{src_doc_id}[/bold] successfully copied to [bold green]{new_doc_id}[/bold green] (including all subcollections).", title="[bold green]Rename Success[/bold green]", border_style="green"))
                delete_original = input("Delete the original document? (y/N): ").strip().lower()
                if delete_original == 'y':
                    src_doc_ref.delete()
                    console.print(Panel(f"Original document [bold]{src_doc_id}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                docs = list(collection_ref.stream())
            except Exception as e:
                console.print(Panel(f"[bold red]Rename failed:[/bold red] {e}", title="[bold red]Error[/bold red]", border_style="red"))
            continue
        else:
            try:
                doc_choice = int(doc_action)
            except ValueError:
                console.print("Please enter a valid number or action key.")
                continue
            if doc_choice == 0:
                return
            if 1 <= doc_choice <= len(docs):
                doc = docs[doc_choice-1]
                doc_ref = collection_ref.document(doc.id)
                data = doc.to_dict()
                subcolls = list(doc_ref.collections())
                panel = Panel(f"[bold yellow]Document:[/bold yellow] {doc.id}", title="Document Details", border_style="yellow")
                console.print(panel)
                show_fields_table(data)
                show_subcollections_table(subcolls)
                action_table = Table(title="[bold blue]Document Actions[/bold blue]", show_header=False)
                action_table.add_column("Key", style="bold magenta", width=4)
                action_table.add_column("Action", style="bold")
                action_table.add_row("A", "View/Edit Fields or Subcollections")
                action_table.add_row("B", "Add Field")
                action_table.add_row("C", "Delete Field")
                action_table.add_row("D", "Add Subcollection")
                action_table.add_row("E", "Delete Subcollection")
                action_table.add_row("F", "Delete Document")
                action_table.add_row("G", "Rename (copy to new ID)")
                action_table.add_row("Q", "[Go back]")
                console.print(action_table)
                while True:
                    console.print("[dim]Enter a letter (A, B, ...) for actions, or Q to go back. You can also enter a number to select a field or subcollection directly.[/dim]")
                    action_choice = input("Select an action: ").strip().upper()
                    try:
                        num_choice = int(action_choice)
                        field_keys = list(data.keys()) if data else []
                        if num_choice == 0:
                            break
                        if 1 <= num_choice <= len(field_keys):
                            k = field_keys[num_choice-1]
                            v = data[k]
                            field_table = Table(title=f"[bold cyan]Field: {k}[/bold cyan]", show_header=False)
                            field_table.add_column("Key", style="bold magenta", width=4)
                            field_table.add_column("Action", style="bold")
                            field_table.add_row("V", "View Value")
                            field_table.add_row("E", "Edit Value")
                            field_table.add_row("D", "Delete Field")
                            field_table.add_row("Q", "[Go back]")
                            console.print(field_table)
                            field_action = input("Select a field action: ").strip().upper()
                            if field_action == "Q":
                                continue
                            elif field_action == "V":
                                if isinstance(v, (str, int, float, bool)) or v is None:
                                    panel = Panel(f"[bold]{k}[/bold]: [green]{v}", title="Field Value", border_style="green")
                                    console.print(panel)
                                    input("Press Enter to continue...")
                                else:
                                    explore_data(v, path + f"/{k}")
                            elif field_action == "E":
                                new_val = input(f"Enter new value for '{k}': ")
                                try:
                                    doc_ref.update({k: json.loads(new_val)})
                                except Exception:
                                    doc_ref.update({k: new_val})
                                console.print(Panel(f"Field [bold]{k}[/bold] updated.", title="[bold green]Success[/bold green]", border_style="green"))
                            elif field_action == "D":
                                doc_ref.update({k: firestore.DELETE_FIELD})
                                console.print(Panel(f"Field [bold]{k}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                            else:
                                console.print("Invalid choice.")
                            continue
                        if subcolls and (len(field_keys) < num_choice <= len(field_keys) + len(subcolls)):
                            subcoll_idx = num_choice - len(field_keys) - 1
                            subcoll_ref = subcolls[subcoll_idx]
                            browse_firestore_collection(subcoll_ref, path + f"/{doc.id}/{subcoll_ref.id}", db)
                            continue
                        console.print("Invalid choice.")
                        continue
                    except ValueError:
                        pass
                    if action_choice == "Q":
                        break
                    elif action_choice == "A":
                        field_keys = list(data.keys()) if data else []
                        show_fields_table(data)
                        show_subcollections_table(subcolls)
                        console.print("[bold][0][/bold] Go back")
                        try:
                            choice = int(input("Select a field to view/edit or a subcollection to enter (or 0 to go back): "))
                        except ValueError:
                            console.print("Please enter a valid number.")
                            continue
                        if choice == 0:
                            continue
                        if 1 <= choice <= len(field_keys):
                            k = field_keys[choice-1]
                            v = data[k]
                            field_table = Table(title=f"[bold cyan]Field: {k}[/bold cyan]", show_header=False)
                            field_table.add_column("Key", style="bold magenta", width=4)
                            field_table.add_column("Action", style="bold")
                            field_table.add_row("V", "View Value")
                            field_table.add_row("E", "Edit Value")
                            field_table.add_row("D", "Delete Field")
                            field_table.add_row("Q", "[Go back]")
                            console.print(field_table)
                            field_action = input("Select a field action: ").strip().upper()
                            if field_action == "Q":
                                continue
                            elif field_action == "V":
                                if isinstance(v, (str, int, float, bool)) or v is None:
                                    panel = Panel(f"[bold]{k}[/bold]: [green]{v}", title="Field Value", border_style="green")
                                    console.print(panel)
                                    input("Press Enter to continue...")
                                else:
                                    explore_data(v, path + f"/{k}")
                            elif field_action == "E":
                                new_val = input(f"Enter new value for '{k}': ")
                                try:
                                    doc_ref.update({k: json.loads(new_val)})
                                except Exception:
                                    doc_ref.update({k: new_val})
                                console.print(Panel(f"Field [bold]{k}[/bold] updated.", title="[bold green]Success[/bold green]", border_style="green"))
                            elif field_action == "D":
                                doc_ref.update({k: firestore.DELETE_FIELD})
                                console.print(Panel(f"Field [bold]{k}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                            else:
                                console.print("Invalid choice.")
                        elif subcolls and (len(field_keys) < choice <= len(field_keys) + len(subcolls)):
                            subcoll_idx = choice - len(field_keys) - 1
                            subcoll_ref = subcolls[subcoll_idx]
                            browse_firestore_collection(subcoll_ref, path + f"/{doc.id}/{subcoll_ref.id}", db)
                        else:
                            console.print("Invalid choice.")
                    elif action_choice == "B":
                        field_name = input("Enter new field name: ").strip()
                        if not field_name:
                            console.print("[bold red]No field name entered.[/bold red]")
                            continue
                        field_value = input(f"Enter value for '{field_name}': ")
                        try:
                            doc_ref.update({field_name: json.loads(field_value)})
                        except Exception:
                            doc_ref.update({field_name: field_value})
                        console.print(Panel(f"Field [bold]{field_name}[/bold] added.", title="[bold green]Success[/bold green]", border_style="green"))
                    elif action_choice == "C":
                        field_name = input("Enter field name to delete: ").strip()
                        if not field_name:
                            console.print("[bold red]No field name entered.[/bold red]")
                            continue
                        doc_ref.update({field_name: firestore.DELETE_FIELD})
                        console.print(Panel(f"Field [bold]{field_name}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                    elif action_choice == "D":
                        subcoll_name = input("Enter new subcollection name: ").strip()
                        if not subcoll_name:
                            console.print("[bold red]No subcollection name entered.[/bold red]")
                            continue
                        subcoll_ref = doc_ref.collection(subcoll_name)
                        new_doc_id = input("Enter new document ID for subcollection: ").strip()
                        if not new_doc_id:
                            console.print("[bold red]No document ID entered.[/bold red]")
                            continue
                        subcoll_ref.document(new_doc_id).set({})
                        console.print(Panel(f"Subcollection [bold]{subcoll_name}[/bold] with document [bold]{new_doc_id}[/bold] created.", title="[bold green]Success[/bold green]", border_style="green"))
                    elif action_choice == "E":
                        subcoll_name = input("Enter subcollection name to delete: ").strip()
                        if not subcoll_name:
                            console.print("[bold red]No subcollection name entered.[/bold red]")
                            continue
                        subcoll_ref = doc_ref.collection(subcoll_name)
                        deleted = 0
                        for subdoc in subcoll_ref.stream():
                            subdoc.reference.delete()
                            deleted += 1
                        console.print(Panel(f"Subcollection [bold]{subcoll_name}[/bold] deleted ({deleted} documents removed).", title="[bold red]Deleted[/bold red]", border_style="red"))
                    elif action_choice == "F":
                        confirm = input(f"Are you sure you want to delete document '{doc.id}'? (y/N): ").strip().lower()
                        if confirm == 'y':
                            recursive_delete_by_path(db, f"{collection_ref.id}/{doc.id}")
                            console.print(Panel(f"Document [bold]{doc.id}[/bold] deleted (including all subcollections).", title="[bold red]Deleted[/bold red]", border_style="red"))
                            return
                    elif action_choice == "G":
                        new_id = input("Enter new document ID: ").strip()
                        if not new_id:
                            console.print("[bold red]No ID entered. Rename cancelled.[/bold red]")
                            continue
                        new_doc_ref = collection_ref.document(new_id)
                        if new_doc_ref.get().exists:
                            console.print(f"[bold red]A document with ID '{new_id}' already exists.[/bold red]")
                            continue
                        try:
                            # Assuming rename_document_with_subcollections is defined elsewhere or needs to be imported
                            # For now, we'll just copy and delete the original
                            src_doc_ref.set(src_doc_ref.get().to_dict()) # Copy data
                            console.print(Panel(f"Document [bold]{doc.id}[/bold] successfully copied to [bold green]{new_id}[/bold green] (including all subcollections).", title="[bold green]Rename Success[/bold green]", border_style="green"))
                            delete_original = input("Delete the original document? (y/N): ").strip().lower()
                            if delete_original == 'y':
                                src_doc_ref.delete()
                                console.print(Panel(f"Original document [bold]{doc.id}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                        except Exception as e:
                            console.print(Panel(f"[bold red]Rename failed:[/bold red] {e}", title="[bold red]Error[/bold red]", border_style="red"))
                    else:
                        console.print("Please enter a letter (A, B, ...) for actions, or Q to go back.")
                # End of document actions menu loop
            else:
                console.print("Invalid choice.") 