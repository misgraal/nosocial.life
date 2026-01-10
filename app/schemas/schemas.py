from pydantic import BaseModel

class checkRequest(BaseModel):
    number: int

class checkResponse(BaseModel):
    result: bool