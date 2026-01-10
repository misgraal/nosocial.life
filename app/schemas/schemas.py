from pydantic import BaseModel

class loginRequest(BaseModel):
    username: str
    password: str
    confirm_password: str

class loginResponse(BaseModel):
    result: bool