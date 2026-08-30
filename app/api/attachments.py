import uuid
from pathlib import PurePosixPath
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from app.core.config import MAX_ATTACHMENT_BYTES
from app.core.security import get_current_user_with_subscription_check
from app.core.storage import create_signed_url, delete_file, upload_file
from app.database import engine
from app.models.attachment import Attachment
from app.models.transaction import Transaction
from app.schemas.attachment import AttachmentRead

router = APIRouter(tags=["attachments"])

# Solo lo que de verdad es un comprobante. Nada de ejecutables ni archivos
# arbitrarios: el bucket es privado, pero un adjunto que el usuario luego
# descarga no debe poder ser un binario.
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "application/pdf": "pdf",
}

MAX_ATTACHMENTS_PER_TRANSACTION = 5


def _to_read(attachment: Attachment) -> AttachmentRead:
    return AttachmentRead(
        id=attachment.id,
        transaction_id=attachment.transaction_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        created_at=attachment.created_at,
        url=create_signed_url(attachment.storage_path),
    )


def _get_owned_transaction(session: Session, transaction_id: int, user_id: UUID) -> Transaction:
    transaction = session.exec(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == user_id
        )
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    return transaction


@router.post("/transactions/{transaction_id}/attachments", response_model=AttachmentRead)
async def upload_attachment(
    transaction_id: int,
    file: UploadFile = File(...),
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Formato no admitido. Usa una imagen (JPG, PNG, WEBP, HEIC) o un PDF.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(content) > MAX_ATTACHMENT_BYTES:
        limit_mb = MAX_ATTACHMENT_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=400, detail=f"El archivo supera el límite de {limit_mb:.0f} MB."
        )

    with Session(engine) as session:
        _get_owned_transaction(session, transaction_id, user_id)

        existing = session.exec(
            select(Attachment).where(Attachment.transaction_id == transaction_id)
        ).all()
        if len(existing) >= MAX_ATTACHMENTS_PER_TRANSACTION:
            raise HTTPException(
                status_code=400,
                detail=f"Máximo {MAX_ATTACHMENTS_PER_TRANSACTION} comprobantes por movimiento.",
            )

        extension = ALLOWED_CONTENT_TYPES[file.content_type]
        # La ruta se construye acá, nunca con el nombre que envía el cliente:
        # un `filename` como "../../otro-usuario/x.jpg" no debe poder escapar
        # de su carpeta. El nombre original solo se guarda para mostrarlo.
        storage_path = f"{user_id}/{transaction_id}/{uuid.uuid4().hex}.{extension}"

        upload_file(storage_path, content, file.content_type)

        attachment = Attachment(
            user_id=user_id,
            transaction_id=transaction_id,
            storage_path=storage_path,
            filename=PurePosixPath(file.filename or f"comprobante.{extension}").name[:255],
            content_type=file.content_type,
            size_bytes=len(content),
        )
        session.add(attachment)
        session.commit()
        session.refresh(attachment)
        return _to_read(attachment)


@router.get("/transactions/{transaction_id}/attachments", response_model=List[AttachmentRead])
def list_attachments(
    transaction_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        _get_owned_transaction(session, transaction_id, user_id)
        attachments = session.exec(
            select(Attachment)
            .where(Attachment.transaction_id == transaction_id)
            .order_by(Attachment.created_at)
        ).all()
        return [_to_read(a) for a in attachments]


@router.delete("/attachments/{attachment_id}")
def delete_attachment(
    attachment_id: int,
    user_id: UUID = Depends(get_current_user_with_subscription_check),
):
    with Session(engine) as session:
        attachment = session.get(Attachment, attachment_id)
        if not attachment or attachment.user_id != user_id:
            raise HTTPException(status_code=404, detail="Comprobante no encontrado")

        delete_file(attachment.storage_path)
        session.delete(attachment)
        session.commit()
        return {"message": "Comprobante eliminado."}
