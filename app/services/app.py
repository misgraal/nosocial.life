from dataclasses import dataclass
from app.db.app import *
from config import DISKS
import os

@dataclass
class StartUpResult:
    result: dict

async def home(user_id) -> StartUpResult:
    username = await get_user_username_by_id(user_id)
    for disk in DISKS:
        if os.path.isdir(f"{disk}/{username}") == False:
            os.makedirs(f"{disk}/{username}")
            await add_root_folder(user_id, username, f"{disk}/{username}")

    

