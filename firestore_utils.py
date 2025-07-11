from rich.console import Console
from rich.panel import Panel

console = Console()

def recursive_delete_by_path(db, path, parent_path=None):
    full_path = path if not parent_path else f"{parent_path}/{path}"
    parts = full_path.strip('/').split('/')
    if len(parts) % 2 == 0:
        doc_ref = db.document(full_path)
        try:
            console.print(f"[dim]Deleting document: [bold]{full_path}[/bold]")
            for subcoll in doc_ref.collections():
                subcoll_ref = doc_ref.collection(subcoll.id)
                for subdoc in subcoll_ref.stream():
                    recursive_delete_by_path(db, f"{subcoll.id}/{subdoc.id}", parent_path=full_path)
            doc_ref.delete()
        except Exception as e:
            console.print(Panel(f"[bold red]Error deleting document or subcollections at {full_path}: {e}[/bold red]", title="[bold red]Delete Error[/bold red]", border_style="red"))
    else:
        coll_ref = db.collection(full_path)
        try:
            console.print(f"[dim]Deleting collection: [bold]{full_path}[/bold]")
            docs = list(coll_ref.stream())
            for doc in docs:
                recursive_delete_by_path(db, doc.id, parent_path=full_path)
        except Exception as e:
            console.print(Panel(f"[bold red]Error deleting collection at {full_path}: {e}[/bold red]", title="[bold red]Delete Error[/bold red]", border_style="red"))

def delete_collection(coll_ref, batch_size=20, parent_path=None):
    base_path = coll_ref.id if not parent_path else f"{parent_path}/{coll_ref.id}"
    try:
        docs = list(coll_ref.limit(batch_size).stream())
        deleted = 0
        for doc in docs:
            try:
                doc_path = f"{base_path}/{doc.id}"
                console.print(f"[dim]Deleting document: [bold]{doc_path}[/bold]")
                for subcoll in doc.reference.collections():
                    for subdoc in subcoll.stream():
                        recursive_delete_by_path(coll_ref._client, f"{subcoll.id}/{subdoc.id}", parent_path=doc_path)
                doc.reference.delete()
                console.print(f"[dim]Deleted document [bold]{doc_path}[/bold]")
            except Exception as e:
                console.print(Panel(f"[bold red]Error deleting document {doc_path}: {e}[/bold red]", title="[bold red]Delete Error[/bold red]", border_style="red"))
        if deleted >= batch_size:
            return delete_collection(coll_ref, batch_size, parent_path=parent_path)
        return deleted
    except Exception as e:
        console.print(Panel(f"[bold red]Error streaming collection: {e}[/bold red]", title="[bold red]Delete Error[/bold red]", border_style="red"))
        return 0 