from rich.console import Console
from rich.panel import Panel
from firebase_cli_app.core.ui_helpers import show_documents_table, show_fields_table, show_subcollections_table, explore_data
from firebase_cli_app.core.firestore_utils import recursive_delete_by_path, delete_collection
from rich.table import Table
import json
import firebase_admin.firestore as firestore

console = Console()

def browse_firestore_collection(collection_ref, path="", db=None):
    while True:
        console.print(Panel(f"[bold yellow]You are here: [/] [bold green]{path or '/'}[/]", title="Current Firestore Path", border_style="cyan"))
        docs = list(collection_ref.stream())
        if not docs:
            # If no documents, check for user IDs from Firebase Auth and show matching documents
            try:
                from firebase_admin import auth
                console.print("No documents found at this level. Checking for user IDs in Firebase Auth and matching documents...")
                user_ids = []
                page = auth.list_users()
                while page:
                    for user in page.users:
                        user_ids.append(user.uid)
                    page = page.get_next_page() if hasattr(page, 'get_next_page') else None
                matching_docs = []
                for uid in user_ids:
                    doc_ref = collection_ref.document(uid)
                    doc = doc_ref.get()
                    if doc.exists:
                        subcolls = list(doc_ref.collections())
                        matching_docs.append((uid, subcolls))
                if matching_docs:
                    table = Table(title=f"[bold blue]Auth User IDs with Documents in '{collection_ref.id}'[/bold blue]", show_header=True)
                    table.add_column("#", style="bold magenta", width=4)
                    table.add_column("User ID", style="bold")
                    table.add_column("Subcollections", style="bold")
                    for idx, (uid, subcolls) in enumerate(matching_docs, 1):
                        table.add_row(
                            str(idx),
                            uid,
                            ", ".join([s.id for s in subcolls]) if subcolls else "-"
                        )
                    console.print(table)
                    console.print("[bold][0][/bold] Go back")
                    while True:
                        try:
                            choice = int(input("Select a user by number (or 0 to go back): "))
                        except ValueError:
                            console.print("Please enter a valid number.")
                            continue
                        if choice == 0:
                            return
                        if 1 <= choice <= len(matching_docs):
                            uid, subcolls = matching_docs[choice-1]
                            doc_ref = collection_ref.document(uid)
                            data = doc_ref.get().to_dict()
                            subcolls = list(doc_ref.collections())
                            panel = Panel(f"[bold yellow]Document:[/bold yellow] {uid}", title="Document Details", border_style="yellow")
                            console.print(panel)
                            show_fields_table(data)
                            show_subcollections_table(subcolls)
                            input("Press Enter to go back...")
                        else:
                            console.print("Invalid choice.")
                    return
                else:
                    console.print("[bold red]No documents found for any Auth user IDs in this collection.[/bold red]")
                    return
            except Exception as e:
                console.print(f"[!] Error fetching user IDs: {e}")
                return
        # Show documents in a rich table with numbers for selection
        doc_table = Table(title=f"[bold blue]Documents in {path or '/'}[/bold blue]", show_header=True)
        doc_table.add_column("#", style="bold magenta", width=4)
        doc_table.add_column("Document ID", style="bold")
        for idx, doc in enumerate(docs, 1):
            doc_table.add_row(str(idx), doc.id)
        console.print(doc_table)
        while True:
            user_input = input("Enter a document number to view, or press Enter for actions: ").strip()
            if user_input == "":
                # Show document list actions
                doc_action_table = Table(title="[bold blue]Document List Actions[/bold blue]", show_header=False)
                doc_action_table.add_column("Key", style="bold magenta", width=4)
                doc_action_table.add_column("Action", style="bold")
                doc_action_table.add_row("A", "Create New Document")
                doc_action_table.add_row("B", "Delete Document by ID")
                doc_action_table.add_row("C", "Rename (copy) Document by ID")
                doc_action_table.add_row("Q", "[Go back]")
                console.print(doc_action_table)
                doc_action = input("Select a document action (A, B, C, Q): ").strip().upper()
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
                    break
                elif doc_action == "B":
                    del_doc_id = input("Enter document ID to delete: ").strip()
                    if not del_doc_id:
                        console.print("[bold red]No document ID entered.[/bold red]")
                        continue
                    del_doc_ref = collection_ref.document(del_doc_id)
                    if not del_doc_ref.get().exists:
                        console.print(f"[bold red]Document '{del_doc_id}' does not exist.[/bold red]")
                        continue
                    confirm = input(f"[bold red]Are you sure you want to delete document '{del_doc_id}'? (y/N): [/bold red]").strip().lower()
                    if confirm == 'y':
                        recursive_delete_by_path(db, f"{collection_ref.id}/{del_doc_id}")
                        console.print(Panel(f"Document [bold]{del_doc_id}[/bold] deleted (including all subcollections).", title="[bold red]Deleted[/bold red]", border_style="red"))
                    break
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
                        src_doc_ref.set(src_doc_ref.get().to_dict()) # Copy data
                        console.print(Panel(f"Document [bold]{src_doc_id}[/bold] successfully copied to [bold green]{new_doc_id}[/bold green] (including all subcollections).", title="[bold green]Rename Success[/bold green]", border_style="green"))
                        delete_original = input("Delete the original document? (y/N): ").strip().lower()
                        if delete_original == 'y':
                            src_doc_ref.delete()
                            console.print(Panel(f"Original document [bold]{src_doc_id}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                    except Exception as e:
                        console.print(Panel(f"[bold red]Rename failed:[/bold red] {e}", title="[bold red]Error[/bold red]", border_style="red"))
                    break
                else:
                    console.print("Please enter a valid number or action key.")
            else:
                try:
                    doc_choice = int(user_input)
                except ValueError:
                    console.print("Please enter a valid number or press Enter for actions.")
                    continue
                if doc_choice == 0:
                    return
                if 1 <= doc_choice <= len(docs):
                    doc = docs[doc_choice-1]
                    doc_ref = collection_ref.document(doc.id)
                    data = doc.to_dict()
                    subcolls = list(doc_ref.collections())
                    # Remove the Document Details panel
                    # Only show the current path panel and the combined table
                    while True:
                        console.print(Panel(f"[bold yellow]You are here: [/] [bold green]{path}/{doc.id}[/]", title="Current Firestore Path", border_style="cyan"))
                        # Build a combined list of fields (with [View]) and subcollections
                        fields = list(data.items()) if data else []
                        subcolls = list(doc_ref.collections())
                        menu_items = []
                        for idx, (k, v) in enumerate(fields, 1):
                            if isinstance(v, (dict, list)):
                                menu_items.append((f"{k}", "[View]", "field", k))
                            else:
                                menu_items.append((f"{k}", str(v), "field", k))
                        for sidx, subcoll in enumerate(subcolls, len(fields) + 1):
                            menu_items.append((subcoll.id, "(subcollection)", "subcoll", subcoll.id))
                        # Display only the combined table
                        table = Table(title="[bold green]Fields & Subcollections[/bold green]", show_header=True, header_style="bold green")
                        table.add_column("#", style="dim", width=4)
                        table.add_column("Name", style="bold yellow")
                        table.add_column("Value", style="yellow")
                        for idx, (name, value, typ, key) in enumerate(menu_items, 1):
                            table.add_row(str(idx), name, value)
                        if not menu_items:
                            table.add_row("-", "(none)", "")
                        console.print(table)
                        # Prompt for navigation or actions
                        user_input = input("Enter a number to view, or press Enter for actions: ").strip()
                        if user_input == "":
                            # Show action menu
                            action_table = Table(title="[bold blue]Actions[/bold blue]", show_header=False)
                            action_table.add_column("Key", style="bold magenta", width=4)
                            action_table.add_column("Action", style="bold")
                            action_table.add_row("E", "Edit (fields, subcollections, rename)")
                            action_table.add_row("D", "Delete Document")
                            action_table.add_row("Q", "Back")
                            console.print(action_table)
                            while True:
                                action_choice = input("Select an action (E/D/Q): ").strip().upper()
                                if action_choice == "Q":
                                    # Just break out of the actions menu, not the document view
                                    break
                                elif action_choice == "D":
                                    confirm = input(f"Are you sure you want to delete document '{doc.id}'? (y/N): ").strip().lower()
                                    if confirm == 'y':
                                        recursive_delete_by_path(db, f"{collection_ref.id}/{doc.id}")
                                        console.print(Panel(f"Document [bold]{doc.id}[/bold] deleted (including all subcollections).", title="[bold red]Deleted[/bold red]", border_style="red"))
                                        return
                                elif action_choice == "E":
                                    # Edit submenu (same as before)
                                    while True:
                                        edit_table = Table(title="[bold blue]Edit Document[/bold blue]", show_header=False)
                                        edit_table.add_column("Key", style="bold magenta", width=4)
                                        edit_table.add_column("Action", style="bold")
                                        edit_table.add_row("A", "Add Field")
                                        edit_table.add_row("F", "Edit Field")
                                        edit_table.add_row("R", "Rename Document")
                                        edit_table.add_row("B", "Back")
                                        console.print(edit_table)
                                        edit_choice = input("Select an edit action (A/F/R/B): ").strip().upper()
                                        if edit_choice == "B":
                                            break
                                        elif edit_choice == "A":
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
                                        elif edit_choice == "F":
                                            field_name = input("Enter field name to edit/delete: ").strip()
                                            if not field_name or field_name not in data:
                                                console.print("[bold red]Invalid or missing field name.[/bold red]")
                                                continue
                                            subedit = input("[E]dit or [D]elete this field? ").strip().upper()
                                            if subedit == "E":
                                                new_val = input(f"Enter new value for '{field_name}': ")
                                                try:
                                                    doc_ref.update({field_name: json.loads(new_val)})
                                                except Exception:
                                                    doc_ref.update({field_name: new_val})
                                                console.print(Panel(f"Field [bold]{field_name}[/bold] updated.", title="[bold green]Success[/bold green]", border_style="green"))
                                            elif subedit == "D":
                                                doc_ref.update({field_name: firestore.DELETE_FIELD})
                                                console.print(Panel(f"Field [bold]{field_name}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                                            else:
                                                console.print("[bold red]Invalid choice.[/bold red]")
                                        elif edit_choice == "R":
                                            new_id = input("Enter new document ID: ").strip()
                                            if not new_id:
                                                console.print("[bold red]No ID entered. Rename cancelled.[/bold red]")
                                                continue
                                            new_doc_ref = collection_ref.document(new_id)
                                            if new_doc_ref.get().exists:
                                                console.print(f"[bold red]A document with ID '{new_id}' already exists.[/bold red]")
                                                continue
                                            try:
                                                doc_ref.set(doc_ref.get().to_dict()) # Copy data
                                                console.print(Panel(f"Document [bold]{doc.id}[/bold] successfully copied to [bold green]{new_id}[/bold green] (including all subcollections).", title="[bold green]Rename Success[/bold green]", border_style="green"))
                                                delete_original = input("Delete the original document? (y/N): ").strip().lower()
                                                if delete_original == 'y':
                                                    doc_ref.delete()
                                                    console.print(Panel(f"Original document [bold]{doc.id}[/bold] deleted.", title="[bold red]Deleted[/bold red]", border_style="red"))
                                            except Exception as e:
                                                console.print(Panel(f"[bold red]Rename failed:[/bold red] {e}", title="[bold red]Error[/bold red]", border_style="red"))
                                        else:
                                            console.print("[bold red]Invalid edit action key.[/bold red]")
                                else:
                                    console.print("[bold red]Invalid action key.[/bold red]")
                        elif user_input.isdigit() and menu_items:
                            idx = int(user_input) - 1
                            if 0 <= idx < len(menu_items):
                                name, value, typ, key = menu_items[idx]
                                if typ == "field" and (value == "[View]" or isinstance(data[key], (dict, list))):
                                    explore_data(data[key], f"{path}/{doc.id}/{key}")
                                elif typ == "subcoll":
                                    subcoll_ref = doc_ref.collection(key)
                                    browse_firestore_collection(subcoll_ref, f"{path}/{doc.id}/{key}", db)
                                else:
                                    console.print("[bold red]This item is not viewable.", style="red")
                            else:
                                console.print("[bold red]Invalid selection number.[/bold red]")
                        else:
                            console.print("[bold red]Invalid input. Enter a number to view, or press Enter for actions.")
                    # End of document actions menu loop
                else:
                    console.print("Invalid choice.")
            # End of main document menu loop 