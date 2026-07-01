from fastapi import APIRouter

from app.modules.support.schemas import SupportContactRequest, SupportContactResponse
from app.modules.support.service import SupportService

router = APIRouter(prefix="/support", tags=["support"])
service = SupportService()


@router.post("/contact", response_model=SupportContactResponse)
def contact_support(payload: SupportContactRequest):
    return service.contact(payload)
