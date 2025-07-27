from typing import Any, Optional
from pydantic import BaseModel

class APIResponse(BaseModel):
    message: str
    data: Optional[Any] = None
    status: str
    success: bool
    code: int
    
    def to_dict(self):
        return {
            "message": self.message,
            "data": self.data,
            "status": self.status,
            "success": self.success,
            "code": self.code
        }