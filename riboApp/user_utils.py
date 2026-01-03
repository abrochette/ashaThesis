"""
User-specific file path utilities for isolating user data
"""
import os
from django.contrib.auth.models import AnonymousUser

def get_user_id(user):
    """Get a safe user identifier for file paths"""
    if user is None or isinstance(user, AnonymousUser):
        return "anonymous"
    return f"user_{user.id}"

def get_user_parquet_folder(user):
    """Get user-specific parquet folder path"""
    user_id = get_user_id(user)
    return f"media/parquetFiles/{user_id}/"

def get_user_mrna_folder(user):
    """Get user-specific mRNA folder path"""
    user_id = get_user_id(user)
    return f"media/mrnaFiles/{user_id}/"

def get_user_pickle_folder(user):
    """Get user-specific pickle cache folder path"""
    user_id = get_user_id(user)
    return f"media/parquetPickles/{user_id}/"

def get_user_mrna_pickle_folder(user):
    """Get user-specific mRNA pickle cache folder path"""
    user_id = get_user_id(user)
    return f"media/mrnaPickles/{user_id}/"

def ensure_user_folders(user):
    """Create user-specific folders if they don't exist"""
    folders = [
        get_user_parquet_folder(user),
        get_user_mrna_folder(user),
        get_user_pickle_folder(user),
        get_user_mrna_pickle_folder(user),
    ]
    for folder in folders:
        os.makedirs(folder, exist_ok=True)

