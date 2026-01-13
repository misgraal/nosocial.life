from dataclasses import dataclass

@dataclass
class LoginResult:
    success: bool

async def login(username: str, password: str) -> LoginResult:
    if username == "test" and password == "test":
        return LoginResult(True)
    else: return LoginResult(False)