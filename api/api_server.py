import os
import uuid
import time
import threading
from fastapi import FastAPI, HTTPException, Path, Body, Header, UploadFile, File, Depends
from pydantic import BaseModel
from typing import Any, Dict, Optional
import firebase_admin
from firebase_admin import credentials, auth, firestore

SERVICE_ACCOUNTS_DIR = os.path.join(os.path.dirname(__file__), 'service_accounts')
os.makedirs(SERVICE_ACCOUNTS_DIR, exist_ok=True)

app = FastAPI()

# Background cleanup task to delete service account files older than 1 hour
def cleanup_service_accounts():
    now = time.time()
    for filename in os.listdir(SERVICE_ACCOUNTS_DIR):
        file_path = os.path.join(SERVICE_ACCOUNTS_DIR, filename)
        if os.path.isfile(file_path):
            file_age = now - os.path.getmtime(file_path)
            if file_age > 3600:  # 1 hour
                os.remove(file_path)
    threading.Timer(3600, cleanup_service_accounts).start()
cleanup_service_accounts()

class DocumentModel(BaseModel):
    data: Dict[str, Any]

class RenameModel(BaseModel):
    new_name: str

def verify_token(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    id_token = authorization.split(" ", 1)[1]
    try:
        # Use default app for auth verification
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_firestore_client(service_account_id: str):
    if not service_account_id:
        raise HTTPException(status_code=400, detail="Missing X-Service-Account-ID header.")
    # Find the file
    for filename in os.listdir(SERVICE_ACCOUNTS_DIR):
        if filename.startswith(service_account_id):
            file_path = os.path.join(SERVICE_ACCOUNTS_DIR, filename)
            break
    else:
        raise HTTPException(status_code=404, detail="Service account file not found.")
    app_name = f"app_{service_account_id}"
    # Reuse app if it exists, otherwise create it
    try:
        app_instance = firebase_admin.get_app(app_name)
    except ValueError:
        cred = credentials.Certificate(file_path)
        app_instance = firebase_admin.initialize_app(cred, name=app_name)
    return firestore.client(app_instance)

@app.post("/service-account/upload")
def upload_service_account(file: UploadFile = File(...)):
    # Save with unique ID
    unique_id = str(uuid.uuid4())
    filename = f"{unique_id}_{int(time.time())}.json"
    file_path = os.path.join(SERVICE_ACCOUNTS_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    return {"service_account_id": unique_id}

@app.post("/collection")
def create_collection(
    payload: Dict[str, str] = Body(...),
    authorization: str = Header(...),
    service_account_id: str = Header(None, alias="X-Service-Account-ID")
):
    user_id = verify_token(authorization)
    db = get_firestore_client(service_account_id)
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Missing collection name.")
    dummy_doc_id = "_init_"
    db.collection(name).document(dummy_doc_id).set({"created": True, "created_by": user_id})
    return {"message": f"Collection '{name}' created with dummy document by user {user_id}."}

@app.delete("/collection/{collection_name}")
def delete_collection_endpoint(
    collection_name: str,
    authorization: str = Header(...),
    service_account_id: str = Header(None, alias="X-Service-Account-ID")
):
    user_id = verify_token(authorization)
    db = get_firestore_client(service_account_id)
    coll_ref = db.collection(collection_name)
    docs = list(coll_ref.stream())
    for doc in docs:
        doc.reference.delete()
    return {"message": f"Collection '{collection_name}' deleted by user {user_id}.", "docs_deleted": len(docs)}

@app.post("/collection/{collection_name}/document")
def add_document(
    collection_name: str,
    doc: DocumentModel,
    authorization: str = Header(...),
    service_account_id: str = Header(None, alias="X-Service-Account-ID")
):
    user_id = verify_token(authorization)
    db = get_firestore_client(service_account_id)
    doc_ref = db.collection(collection_name).document()
    doc_ref.set({**doc.data, "created_by": user_id})
    return {"message": f"Document created in '{collection_name}' by user {user_id}", "doc_id": doc_ref.id}

@app.put("/collection/{collection_name}/document/{doc_id}")
def update_document(
    collection_name: str,
    doc_id: str,
    doc: DocumentModel,
    authorization: str = Header(...),
    service_account_id: str = Header(None, alias="X-Service-Account-ID")
):
    user_id = verify_token(authorization)
    db = get_firestore_client(service_account_id)
    doc_ref = db.collection(collection_name).document(doc_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc_ref.set({**doc.data, "updated_by": user_id}, merge=True)
    return {"message": f"Document '{doc_id}' updated in '{collection_name}' by user {user_id}"}

@app.delete("/collection/{collection_name}/document/{doc_id}")
def delete_document(
    collection_name: str,
    doc_id: str,
    authorization: str = Header(...),
    service_account_id: str = Header(None, alias="X-Service-Account-ID")
):
    user_id = verify_token(authorization)
    db = get_firestore_client(service_account_id)
    doc_ref = db.collection(collection_name).document(doc_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc_ref.delete()
    return {"message": f"Document '{doc_id}' deleted from '{collection_name}' by user {user_id}"}

@app.get("/collection/{collection_name}")
def list_documents(
    collection_name: str,
    authorization: str = Header(...),
    service_account_id: str = Header(None, alias="X-Service-Account-ID")
):
    user_id = verify_token(authorization)
    db = get_firestore_client(service_account_id)
    coll_ref = db.collection(collection_name)
    docs = [ {"id": doc.id, **doc.to_dict()} for doc in coll_ref.stream() ]
    return {"documents": docs, "requested_by": user_id}

@app.post("/collection/{collection_name}/rename")
def rename_collection(
    collection_name: str,
    payload: RenameModel,
    authorization: str = Header(...),
    service_account_id: str = Header(None, alias="X-Service-Account-ID")
):
    user_id = verify_token(authorization)
    db = get_firestore_client(service_account_id)
    new_name = payload.new_name
    if not new_name:
        raise HTTPException(status_code=400, detail="Missing new collection name.")
    src_coll_ref = db.collection(collection_name)
    new_coll_ref = db.collection(new_name)
    for doc in src_coll_ref.stream():
        new_coll_ref.document(doc.id).set(doc.to_dict())
    for doc in src_coll_ref.stream():
        doc.reference.delete()
    return {"message": f"Collection '{collection_name}' renamed to '{new_name}' by user {user_id}"} 