import os
import uuid
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, KYCRecord
from app.schemas import KYCSubmitRequest, KYCOut
from app.deps import get_current_user
from app.services.kyc import KycService

router = APIRouter(prefix="/api/kyc", tags=["KYC Verification"])

def record_to_out(record: KYCRecord) -> KYCOut:
    return KYCOut(
        id=record.id,
        status=record.status,
        full_name_on_pan=record.full_name_on_pan,
        pan_masked=record.pan_number_masked,
        address=record.address,
        passport_number=record.passport_number,
        selfie_file_path=record.selfie_file_path,
        document_file_path=record.document_file_path,
        rejection_reason=record.rejection_reason,
        verified_at=record.verified_at,
        verified_by=record.verified_by
    )

@router.get("/status", response_model=Optional[KYCOut])
def get_kyc_status(user: User = Depends(get_current_user)):
    if not user.kyc_record:
        return None
    return record_to_out(user.kyc_record)

@router.post("/submit", response_model=KYCOut)
def submit_kyc(
    payload: KYCSubmitRequest,
    auto_approve: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        record = KycService.submit_kyc(
            db=db,
            user=user,
            pan_number=payload.pan_number,
            full_name_on_pan=payload.full_name_on_pan,
            address=payload.address,
            passport_number=payload.passport_number,
            auto_approve_in_sandbox=(settings.TEST_MODE and auto_approve)
        )
        return record_to_out(record)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/upload-docs")
async def upload_kyc_documents(
    selfie: Optional[UploadFile] = File(None),
    document: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    selfie_path = None
    doc_path = None

    if selfie:
        ext = os.path.splitext(selfie.filename)[1] or ".jpg"
        selfie_name = f"selfie_{user.id}_{uuid.uuid4().hex[:8]}{ext}"
        selfie_dest = os.path.join(settings.UPLOAD_DIR, selfie_name)
        with open(selfie_dest, "wb") as f:
            shutil.copyfileobj(selfie.file, f)
        selfie_path = selfie_name

    if document:
        ext = os.path.splitext(document.filename)[1] or ".pdf"
        doc_name = f"doc_{user.id}_{uuid.uuid4().hex[:8]}{ext}"
        doc_dest = os.path.join(settings.UPLOAD_DIR, doc_name)
        with open(doc_dest, "wb") as f:
            shutil.copyfileobj(document.file, f)
        doc_path = doc_name

    record = db.query(KYCRecord).filter(KYCRecord.user_id == user.id).first()
    if record:
        if selfie_path:
            record.selfie_file_path = selfie_path
        if doc_path:
            record.document_file_path = doc_path
        db.commit()

    return {
        "success": True,
        "selfie_file": selfie_path,
        "document_file": doc_path,
        "message": "Documents uploaded successfully."
    }

@router.post("/sandbox-auto-approve", response_model=KYCOut)
def sandbox_auto_approve(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not settings.TEST_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sandbox auto-approval is only permitted in TEST MODE."
        )

    if not user.kyc_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please submit your KYC details before requesting verification."
        )

    record = KycService.approve_kyc(
        db,
        user.kyc_record.id,
        approved_by="SandboxKycProvider (One-Click Test Approval)"
    )
    return record_to_out(record)

