from app.db.app import get_user_root_folder

def create_users_folder(user_id):
    print(get_user_root_folder(user_id))